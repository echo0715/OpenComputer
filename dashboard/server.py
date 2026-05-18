"""
Task Manager Web Interface.

Displays tasks, allows difficulty adjustment via Claude Code CLI,
and runs tasks in E2B sandboxes with live desktop streaming.

Usage:
    python dashboard/server.py
    python dashboard/server.py --port 8888
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

# ── Paths ────────────────────────────────────────────────────────────────────

DASHBOARD_DIR = Path(__file__).parent
PROJECT_ROOT = DASHBOARD_DIR.parent
TASK_GEN_DIR = PROJECT_ROOT / "task_generator"
TASKS_DIR = TASK_GEN_DIR / "tasks"
RESULTS_DIR = TASK_GEN_DIR / "results"
EVAL_RUNS_DIR = PROJECT_ROOT / "evaluation" / "runs"
REPAIR_RUNS_DIR = PROJECT_ROOT / "evaluation" / "repair" / "runs"
LESSONS_FILE = TASK_GEN_DIR / "LESSONS.md"
VERIFIERS_DIR = PROJECT_ROOT / "verifiers"
SMOKE_DIR = PROJECT_ROOT / "smoke"
SMOKE_RUNS_DIR = SMOKE_DIR / "runs"
SMOKE_TASKS_DIR = SMOKE_DIR / "smoke_tasks"

REPAIR_TIMESTAMP_RE = re.compile(r"_(\d{8})_(\d{6})$")

# ── Add project root to path for imports ─────────────────────────────────────

sys.path.insert(0, str(PROJECT_ROOT))

# ── Flask app ────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder=None)

# In-memory state for running tasks
_running_tasks = {}  # task_id -> {status, stream_url, model, started_at, process}

# Pending task proposals awaiting user approval
_pending_proposals = {}  # task_id -> {original, proposed, suggestion, timestamp}


# ── Helpers ──────────────────────────────────────────────────────────────────

_EVAL_RUNS_DIR_RESOLVED = EVAL_RUNS_DIR.resolve()

def _iter_task_files():
    """Yield (task_dir, task_dict) for every tasks/<id>/task.json."""
    if not TASKS_DIR.exists():
        return
    for task_dir in sorted(TASKS_DIR.iterdir()):
        if not task_dir.is_dir():
            continue
        task_file = task_dir / "task.json"
        if not task_file.exists():
            continue
        try:
            with open(task_file) as fh:
                yield task_dir, json.load(fh)
        except (json.JSONDecodeError, IOError):
            continue


def get_app_list():
    """Get sorted unique list of apps from task subfolders."""
    apps = set()
    for _, t in _iter_task_files():
        app_name = t.get("app")
        if app_name:
            apps.add(app_name)
    return sorted(apps)


def load_all_tasks():
    """Load all tasks grouped by app from task subfolders."""
    result = {}
    for _, t in _iter_task_files():
        app_name = t.get("app")
        if not app_name:
            continue
        result.setdefault(app_name, []).append(t)
    return result


def load_task_by_id(task_id):
    """Load a single task by ID from its task.json file."""
    task_file = TASKS_DIR / task_id / "task.json"
    if task_file.exists():
        try:
            with open(task_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def load_results():
    """Load all results from trajectory folders in evaluation/runs/ and evaluation/repair/runs/."""
    results = {}
    for run_id, run_dir in _iter_eval_run_dirs():
        trajs_root = run_dir / "trajectories"
        for traj_dir in trajs_root.iterdir():
            if not traj_dir.is_dir():
                continue
            traj_file = traj_dir / "trajectory.json"
            if not traj_file.exists():
                continue
            try:
                with open(traj_file) as fh:
                    entry = json.load(fh)
            except (json.JSONDecodeError, IOError):
                continue
            entry["run_id"] = run_id
            entry["traj_subdir"] = traj_dir.name
            entry["source"] = "eval"
            tid = entry.get("task_id")
            if not tid:
                continue
            results.setdefault(tid, []).append(entry)

    if REPAIR_RUNS_DIR.exists():
        for run_dir in sorted(REPAIR_RUNS_DIR.iterdir()):
            if not run_dir.is_dir():
                continue
            entry = _load_repair_trajectory(run_dir)
            if entry is None:
                continue
            entry["run_id"] = run_dir.name
            entry["traj_subdir"] = "trajectory"
            entry["source"] = "repair"
            tid = entry.get("task_id") or _repair_task_id_from_dir(run_dir.name)
            if not tid:
                continue
            results.setdefault(tid, []).append(entry)

    return results


def _iter_eval_run_dirs():
    """Yield (run_id, run_dir) for eval runs, including nested dirs from slashy model names."""
    if not EVAL_RUNS_DIR.exists():
        return

    runs = []
    seen = set()
    for trajs_root in EVAL_RUNS_DIR.rglob("trajectories"):
        if not trajs_root.is_dir():
            continue
        run_dir = trajs_root.parent
        try:
            run_id = run_dir.relative_to(EVAL_RUNS_DIR).as_posix()
        except ValueError:
            continue
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        runs.append((run_id, run_dir))

    for run_id, run_dir in sorted(runs, key=lambda item: item[0], reverse=True):
        yield run_id, run_dir


def _resolve_eval_run_dir(run_id):
    """Resolve a run_id relative to evaluation/runs and reject paths outside it."""
    if not run_id:
        return None
    run_dir = (EVAL_RUNS_DIR / Path(run_id)).resolve()
    try:
        run_dir.relative_to(_EVAL_RUNS_DIR_RESOLVED)
    except ValueError:
        return None
    return run_dir


def _compute_judge_accuracy(judge_data, verification_details):
    """Attach accuracy metadata to a judge result when checker data is available."""
    if not isinstance(judge_data, dict):
        return None

    if judge_data.get("accuracy") is not None:
        return judge_data

    prog_details = verification_details or []
    judge_checks = judge_data.get("checks", []) or []
    matches = 0
    total = min(len(prog_details), len(judge_checks))
    for i in range(total):
        prog_passed = bool(prog_details[i].get("passed", False))
        judge_passed = bool(judge_checks[i].get("passed", False))
        if prog_passed == judge_passed:
            matches += 1

    enriched = dict(judge_data)
    enriched["accuracy"] = (matches / total) if total > 0 else None
    enriched["matches"] = matches
    enriched["total_compared"] = total
    return enriched


def _load_judge_result(run_id, traj_subdir, source="eval", verification_details=None):
    """Load a cached LLM judge result for an eval or repair trajectory."""
    if not run_id:
        return None

    if source == "repair":
        judge_file = REPAIR_RUNS_DIR / run_id / "judge" / "llm_judge.json"
    else:
        if not traj_subdir:
            return None
        run_dir = _resolve_eval_run_dir(run_id)
        if run_dir is None:
            return None
        judge_file = run_dir / "trajectories" / traj_subdir / "llm_judge.json"

    if not judge_file.exists():
        return None

    try:
        with open(judge_file) as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, IOError):
        return None

    return _compute_judge_accuracy(data, verification_details)


def _latest_result(entries, run_id=None):
    """Return the latest result entry, optionally restricted to one run_id."""
    best = None
    for entry in entries:
        if run_id and entry.get("run_id") != run_id:
            continue
        if best is None or entry.get("timestamp", "") > best.get("timestamp", ""):
            best = entry
    return best


def _parse_repair_timestamp(run_name):
    """Extract ISO timestamp from a repair run dir name ending in _YYYYMMDD_HHMMSS."""
    m = REPAIR_TIMESTAMP_RE.search(run_name)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        return dt.isoformat()
    except ValueError:
        return None


def _repair_task_id_from_dir(run_name):
    """Strip trailing _YYYYMMDD_HHMMSS to recover the task id."""
    return REPAIR_TIMESTAMP_RE.sub("", run_name)


def _latest_repair_round(run_dir):
    """Return (round_index, script_result_list) for the highest-index round_* dir."""
    best = (-1, None)
    for d in run_dir.iterdir():
        if not d.is_dir() or not d.name.startswith("round_"):
            continue
        try:
            idx = int(d.name.split("_", 1)[1])
        except (ValueError, IndexError):
            continue
        script = d / "script_result.json"
        if not script.exists():
            continue
        if idx > best[0]:
            try:
                with open(script) as fh:
                    best = (idx, json.load(fh))
            except (json.JSONDecodeError, IOError):
                continue
    return best


def _load_repair_trajectory(run_dir):
    """Load + enrich a repair run's trajectory.json with verification/reward metadata.

    Returns None if the trajectory file is missing.
    """
    traj_file = run_dir / "trajectory" / "trajectory.json"
    if not traj_file.exists():
        return None
    try:
        with open(traj_file) as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, IOError):
        return None

    _, script_result = _latest_repair_round(run_dir)
    if script_result:
        data["verification_details"] = script_result
        passed = sum(1 for c in script_result if c.get("passed"))
        total = len(script_result)
        data["checks_passed"] = passed
        data["checks_total"] = total
        data["reward"] = (passed / total) if total else None

    if not data.get("timestamp"):
        data["timestamp"] = _parse_repair_timestamp(run_dir.name)

    return data


def _list_repair_runs_for_task(task_id):
    """Return a list of (run_name, trajectory_data) for repair runs of a task."""
    out = []
    if not REPAIR_RUNS_DIR.exists():
        return out
    for run_dir in sorted(REPAIR_RUNS_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        if _repair_task_id_from_dir(run_dir.name) != task_id:
            continue
        data = _load_repair_trajectory(run_dir)
        if data is None:
            continue
        out.append((run_dir.name, data))
    return out


def get_models():
    """Get available model names from the registry."""
    try:
        from agents import list_models
        return list_models()
    except ImportError:
        return [
            "claude-sonnet-4-5", "claude-sonnet-4-6", "claude-opus-4-7",
            "kimi-k2.5", "qwen3-vl",
        ]


# ── API Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(DASHBOARD_DIR / "static", "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(DASHBOARD_DIR / "static", filename)


@app.route("/api/apps")
def api_apps():
    return jsonify(get_app_list())


@app.route("/api/runs")
def api_runs():
    """Get list of evaluation runs with metadata (eval + repair)."""
    runs = []
    for run_id, run_dir in _iter_eval_run_dirs():
        traj_dir = run_dir / "trajectories"
        task_count = sum(1 for d in traj_dir.iterdir() if d.is_dir() and (d / "trajectory.json").exists())
        if task_count == 0:
            continue
        run_name = run_dir.name
        model = run_name.rsplit("_", 2)[0] if "_" in run_name else run_name
        config_file = run_dir / "config.json"
        if config_file.exists():
            try:
                with open(config_file) as f:
                    cfg = json.load(f)
                    model = cfg.get("model", model)
            except (json.JSONDecodeError, IOError):
                pass
        runs.append({
            "run_id": run_id,
            "model": model,
            "task_count": task_count,
            "source": "eval",
        })

    if REPAIR_RUNS_DIR.exists():
        for run_dir in sorted(REPAIR_RUNS_DIR.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            data = _load_repair_trajectory(run_dir)
            if data is None:
                continue
            runs.append({
                "run_id": run_dir.name,
                "model": data.get("model") or "unknown",
                "task_count": 1,
                "source": "repair",
            })

    return jsonify(runs)


@app.route("/api/models")
def api_models():
    return jsonify(get_models())


@app.route("/api/tasks")
def api_tasks():
    """Get all tasks, optionally filtered by app and run."""
    app_filter = request.args.get("app")
    run_filter = request.args.get("run")  # "none" = no results, run_id = specific run
    all_tasks = load_all_tasks()
    results = load_results()

    output = []
    for app_name, tasks in all_tasks.items():
        if app_filter and app_name != app_filter:
            continue
        for task in tasks:
            tid = task["id"]
            task_entry = {
                **task,
                "app": app_name,
                "has_env": bool(task.get("env", {}).get("files")),
                "num_checks": len(task.get("verification", [])),
                "last_run": None,
                "runs_by_model": {},
            }
            if run_filter == "none":
                # User chose "No run" — show no results
                pass
            elif tid in results:
                # Group runs by (source, model), keep latest per key
                by_model = {}
                for r in results[tid]:
                    m = r.get("model", "unknown")
                    src = r.get("source", "eval")
                    key = f"{src}:{m}"
                    if key not in by_model or r.get("timestamp", "") > by_model[key].get("timestamp", ""):
                        by_model[key] = {
                            "model": m,
                            "source": src,
                            "run_id": r.get("run_id"),
                            "traj_subdir": r.get("traj_subdir"),
                            "reward": r.get("reward"),
                            "checks_passed": r.get("checks_passed"),
                            "checks_total": r.get("checks_total"),
                            "agent_steps": r.get("agent_steps"),
                            "timestamp": r.get("timestamp"),
                        }
                task_entry["runs_by_model"] = by_model

                if run_filter:
                    # Filter to specific run
                    result_entry = _latest_result(results[tid], run_filter)
                    match = None
                    if result_entry:
                        match = {
                            "model": result_entry.get("model"),
                            "source": result_entry.get("source", "eval"),
                            "run_id": result_entry.get("run_id"),
                            "traj_subdir": result_entry.get("traj_subdir"),
                            "reward": result_entry.get("reward"),
                            "checks_passed": result_entry.get("checks_passed"),
                            "checks_total": result_entry.get("checks_total"),
                            "agent_steps": result_entry.get("agent_steps"),
                            "timestamp": result_entry.get("timestamp"),
                            "judge": _load_judge_result(
                                result_entry.get("run_id"),
                                result_entry.get("traj_subdir"),
                                result_entry.get("source", "eval"),
                                result_entry.get("verification_details"),
                            ),
                        }
                    task_entry["last_run"] = match
                else:
                    # No filter — don't show any run by default
                    pass

            # Attach running state
            if tid in _running_tasks:
                task_entry["running"] = _running_tasks[tid]
            output.append(task_entry)

    return jsonify(output)


@app.route("/api/summary")
def api_summary():
    """Get aggregate reward / accuracy metrics, optionally for one run."""
    run_filter = request.args.get("run")
    all_tasks = load_all_tasks()
    results = load_results()

    task_to_app = {}
    task_counts_by_app = {}
    for app_name, tasks in all_tasks.items():
        task_counts_by_app[app_name] = len(tasks)
        for task in tasks:
            task_to_app[task["id"]] = app_name

    selected = []
    for task_id, app_name in task_to_app.items():
        result_entry = _latest_result(results.get(task_id, []), run_filter if run_filter else None)
        if not result_entry:
            continue
        judge = _load_judge_result(
            result_entry.get("run_id"),
            result_entry.get("traj_subdir"),
            result_entry.get("source", "eval"),
            result_entry.get("verification_details"),
        )
        selected.append({
            "task_id": task_id,
            "app": app_name,
            "reward": result_entry.get("reward"),
            "judge_accuracy": judge.get("accuracy") if judge else None,
        })

    def summarize_rows(rows, task_count):
        reward_values = [r["reward"] for r in rows if isinstance(r.get("reward"), (int, float))]
        accuracy_values = [r["judge_accuracy"] for r in rows if isinstance(r.get("judge_accuracy"), (int, float))]
        return {
            "task_count": task_count,
            "result_count": len(rows),
            "judged_count": len(accuracy_values),
            "avg_reward": (sum(reward_values) / len(reward_values)) if reward_values else None,
            "avg_accuracy": (sum(accuracy_values) / len(accuracy_values)) if accuracy_values else None,
            "pass_rate": (
                sum(1 for value in reward_values if value == 1) / len(reward_values)
            ) if reward_values else None,
        }

    by_app = []
    for app_name in sorted(task_counts_by_app):
        rows = [row for row in selected if row["app"] == app_name]
        app_summary = summarize_rows(rows, task_counts_by_app[app_name])
        by_app.append({
            "app": app_name,
            **app_summary,
        })

    scope = {
        "type": "run" if run_filter else "latest",
        "label": f"Run: {run_filter}" if run_filter else "Latest result per task across all runs",
    }

    return jsonify({
        "scope": scope,
        "overall": summarize_rows(selected, len(task_to_app)),
        "by_app": by_app,
    })


@app.route("/api/tasks/<task_id>")
def api_task_detail(task_id):
    task = load_task_by_id(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    results = load_results()
    task["runs"] = results.get(task_id, [])

    if task_id in _running_tasks:
        task["running"] = _running_tasks[task_id]

    return jsonify(task)


def _save_lesson(lesson):
    """Append a lesson to LESSONS.md if it's non-empty."""
    if not lesson or not isinstance(lesson, str):
        return
    lesson = lesson.strip()
    if not lesson:
        return
    with open(LESSONS_FILE, "a") as f:
        f.write(f"\n- {lesson}\n")


def _parse_adjustment_output(output):
    """Parse Claude's adjustment output into (tasks_list, lesson).

    Handles both the new format {"tasks": [...], "lesson": "..."} and
    the old format (plain array).
    """
    parsed = None
    # Try direct parse
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        pass
    # Try markdown code block
    if parsed is None:
        m = re.search(r'```(?:json)?\s*\n(.*?)\n```', output, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    # Try first { or [ to last } or ]
    if parsed is None:
        for open_ch, close_ch in [('{', '}'), ('[', ']')]:
            start = output.find(open_ch)
            end = output.rfind(close_ch)
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(output[start:end + 1])
                    break
                except json.JSONDecodeError:
                    continue

    if parsed is None:
        return None, None

    # New format: {"tasks": [...], "lesson": "..."}
    if isinstance(parsed, dict) and "tasks" in parsed:
        return parsed["tasks"], parsed.get("lesson")
    # Old format: plain array
    if isinstance(parsed, list):
        return parsed, None
    # Single task object
    if isinstance(parsed, dict) and "id" in parsed:
        return [parsed], None

    return None, None


def _clear_results_for_task(task_id):
    """Remove results for a task from all evaluation runs (task was modified)."""
    # Clear in-memory judge cache for this task
    keys_to_remove = [k for k in _judge_results if k[0] == task_id]
    for k in keys_to_remove:
        del _judge_results[k]

    for _, run_dir in _iter_eval_run_dirs():
        # Remove matching trajectory dirs
        trajs_root = run_dir / "trajectories"
        if trajs_root.exists():
            for d in list(trajs_root.iterdir()):
                if d.is_dir() and (d.name == task_id or d.name.startswith(task_id + "_")):
                    shutil.rmtree(d)


def _find_traj_dirs(run_dir, task_id):
    """Find trajectory dirs for a task_id (handles both old and timestamped naming)."""
    trajs_root = run_dir / "trajectories"
    if not trajs_root.exists():
        return []
    results = []
    for d in sorted(trajs_root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        # Match exact name (old format) or name starting with task_id_ (new format)
        if d.name == task_id or d.name.startswith(task_id + "_"):
            traj_file = d / "trajectory.json"
            if traj_file.exists():
                results.append(d)
    return results


@app.route("/api/tasks/<task_id>/trajectories")
def api_task_trajectories(task_id):
    """List available trajectory runs for a task (eval + repair)."""
    runs = []
    for run_id, run_dir in _iter_eval_run_dirs():
        for traj_dir in _find_traj_dirs(run_dir, task_id):
            try:
                with open(traj_dir / "trajectory.json") as f:
                    data = json.load(f)
                runs.append({
                    "source": "eval",
                    "run_id": run_id,
                    "traj_subdir": traj_dir.name,
                    "model": data.get("model"),
                    "reward": data.get("reward"),
                    "agent_steps": data.get("agent_steps"),
                    "checks_passed": data.get("checks_passed"),
                    "checks_total": data.get("checks_total"),
                    "timestamp": data.get("timestamp"),
                })
            except (json.JSONDecodeError, IOError):
                continue
    for run_name, data in _list_repair_runs_for_task(task_id):
        runs.append({
            "source": "repair",
            "run_id": run_name,
            "traj_subdir": "trajectory",
            "model": data.get("model"),
            "reward": data.get("reward"),
            "agent_steps": data.get("agent_steps"),
            "checks_passed": data.get("checks_passed"),
            "checks_total": data.get("checks_total"),
            "timestamp": data.get("timestamp"),
        })
    return jsonify(runs)


@app.route("/api/trajectory/<path:run_id>/<traj_subdir>")
def api_trajectory(run_id, traj_subdir):
    """Get full trajectory data for a specific run + trajectory subdir.

    Pass ?source=repair to read from evaluation/repair/runs/<run_id>/trajectory/.
    """
    source = request.args.get("source", "eval")
    if source == "repair":
        run_dir = REPAIR_RUNS_DIR / run_id
        data = _load_repair_trajectory(run_dir)
        if data is None:
            return jsonify({"error": "Trajectory not found"}), 404
        for step in data.get("trajectory", []):
            step.pop("screenshot", None)
        return jsonify(data)

    run_dir = _resolve_eval_run_dir(run_id)
    if run_dir is None:
        return jsonify({"error": "Trajectory not found"}), 404
    traj_file = run_dir / "trajectories" / traj_subdir / "trajectory.json"
    if not traj_file.exists():
        return jsonify({"error": "Trajectory not found"}), 404
    with open(traj_file) as f:
        data = json.load(f)
    for step in data.get("trajectory", []):
        step.pop("screenshot", None)
    return jsonify(data)


@app.route("/api/trajectory/<path:run_id>/<traj_subdir>/screenshot/<filename>")
def api_trajectory_screenshot(run_id, traj_subdir, filename):
    """Serve a trajectory screenshot image. ?source=repair routes to repair runs."""
    source = request.args.get("source", "eval")
    if source == "repair":
        ss_dir = REPAIR_RUNS_DIR / run_id / "trajectory" / "screenshots"
    else:
        run_dir = _resolve_eval_run_dir(run_id)
        if run_dir is None:
            return "Not found", 404
        ss_dir = run_dir / "trajectories" / traj_subdir / "screenshots"
    if not (ss_dir / filename).exists():
        return "Not found", 404
    return send_from_directory(ss_dir, filename, mimetype="image/png")


@app.route("/api/tasks/<task_id>/run", methods=["POST"])
def api_run_task(task_id):
    """Launch a task in E2B sandbox. Returns stream URL."""
    task = load_task_by_id(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    body = request.json or {}
    model = body.get("model", "kimi-k2.5")
    run_id = body.get("run_id")  # optional: save to existing run dir
    app_name = task.get("app", "")

    if task_id in _running_tasks and _running_tasks[task_id]["status"] == "running":
        return jsonify({
            "status": "already_running",
            "stream_url": _running_tasks[task_id].get("stream_url"),
        })

    # Clear stale LLM judge cache and agreement data for this task
    keys_to_remove = [k for k in _judge_results if k[0] == task_id]
    for k in keys_to_remove:
        del _judge_results[k]

    # If rerunning into an existing run_id, clear old results.jsonl entry
    # and delete on-disk llm_judge.json so the UI doesn't show stale data
    if run_id:
        _run_dir = _resolve_eval_run_dir(run_id)
        if _run_dir is None:
            _running_tasks.pop(task_id, None)
            return jsonify({"error": "Invalid run_id"}), 400
        _traj_dir = _run_dir / "trajectories" / task_id
        _judge_file = _traj_dir / "llm_judge.json"
        if _judge_file.exists():
            _judge_file.unlink()

    _running_tasks[task_id] = {
        "status": "starting",
        "model": model,
        "started_at": datetime.now().isoformat(),
        "stream_url": None,
    }

    def run_in_background():
        try:
            cmd = [
                sys.executable, "-u", str(PROJECT_ROOT / "evaluation" / "run_eval.py"),
                "--app", app_name,
                "--task", task_id,
                "--model", model,
            ]
            if run_id:
                cmd.extend(["--run-dir", str(_resolve_eval_run_dir(run_id))])
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PROJECT_ROOT),
            )
            _running_tasks[task_id]["pid"] = proc.pid

            # Read output lines to capture stream URL and errors
            output_lines = []
            for line in proc.stdout:
                line = line.strip()
                output_lines.append(line)
                # Keep only the last 100 lines to avoid unbounded memory
                if len(output_lines) > 100:
                    output_lines.pop(0)
                if "Desktop:" in line and "https://" in line:
                    url = line.split("Desktop:")[-1].strip()
                    _running_tasks[task_id]["stream_url"] = url
                    _running_tasks[task_id]["status"] = "running"
                # Capture reward
                if "reward=" in line:
                    try:
                        reward_str = line.split("reward=")[-1].split()[0]
                        _running_tasks[task_id]["reward"] = float(reward_str)
                    except (ValueError, IndexError):
                        pass

            proc.wait()
            _running_tasks[task_id]["exit_code"] = proc.returncode
            if proc.returncode != 0:
                _running_tasks[task_id]["status"] = "error"
                _running_tasks[task_id]["error"] = "\n".join(output_lines[-20:])
            else:
                _running_tasks[task_id]["status"] = "completed"

        except Exception as e:
            _running_tasks[task_id]["status"] = "error"
            _running_tasks[task_id]["error"] = str(e)

    thread = threading.Thread(target=run_in_background, daemon=True)
    thread.start()

    return jsonify({
        "status": "started",
        "task_id": task_id,
        "model": model,
    })


@app.route("/api/tasks/<task_id>/status")
def api_task_status(task_id):
    """Poll running task status."""
    if task_id not in _running_tasks:
        return jsonify({"status": "idle"})
    return jsonify(_running_tasks[task_id])


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def api_delete_task(task_id):
    """Delete a task entirely: task.json, env/, trajectories, results, proposals, caches."""
    task = load_task_by_id(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    app_name = task.get("app", "")

    # Refuse if task is currently running
    running = _running_tasks.get(task_id)
    if running and running.get("status") in ("starting", "running"):
        return jsonify({"error": "Task is currently running; stop it before deleting"}), 409

    # 1. Remove the task folder (task.json + env/ + any other files)
    task_dir = TASKS_DIR / task_id
    if task_dir.exists() and task_dir.is_dir():
        shutil.rmtree(task_dir)

    # 2. Remove trajectories, results.jsonl lines, and judge caches across all runs
    _clear_results_for_task(task_id)

    # 3. Clear transient state
    _pending_proposals.pop(task_id, None)
    _running_tasks.pop(task_id, None)

    return jsonify({"status": "deleted", "task_id": task_id})


@app.route("/api/tasks/<task_id>/convert_criterion", methods=["POST"])
def api_convert_criterion_to_judge(task_id):
    """Convert a single verification criterion into an LLM-as-judge entry via Claude CLI."""
    task = load_task_by_id(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    body = request.json or {}
    try:
        idx = int(body.get("index"))
    except (TypeError, ValueError):
        return jsonify({"error": "criterion index required"}), 400

    verifs = task.get("verification", []) or []
    if idx < 0 or idx >= len(verifs):
        return jsonify({"error": "index out of range"}), 400

    criterion = verifs[idx]
    app_name = task.get("app", "unknown")
    task_json = json.dumps(task, indent=2)
    criterion_json = json.dumps(criterion, indent=2)

    prompt = (
        f"Read the 'LLM-as-Judge Verification' section of task_generator/CLAUDE.md for the exact "
        f"format and rules for LLM-as-judge verification entries.\n"
        f"Read verifiers/{app_name}/README.md to pick an appropriate verifier subcommand whose JSON "
        f"output will give the judge enough structured context to decide pass/fail.\n\n"
        f"You are converting ONE verification criterion of task '{task_id}' (app: {app_name}) into an "
        f"LLM-as-judge entry. Keep every other criterion and every other task field EXACTLY unchanged.\n\n"
        f"Full current task JSON:\n```json\n{task_json}\n```\n\n"
        f"The criterion to convert is at index {idx}:\n```json\n{criterion_json}\n```\n\n"
        f"Requirements for the new entry:\n"
        f"- Must include: \"judge\": \"llm\", a clear yes/no \"prompt\", a \"command\" (verifier "
        f"  subcommand only — no `python3 /home/user/verifiers/<app>.py` prefix), a \"context\" field "
        f"  (prefer \"command_output\"; use \"screenshot\" only for genuinely visual checks), and a "
        f"  \"description\".\n"
        f"- The \"prompt\" must be a precise, unambiguous yes/no question that captures what the original "
        f"  criterion was checking.\n"
        f"- The \"command\" must be a real endpoint listed in the verifier README for '{app_name}'.\n\n"
        f"Output format (exactly this JSON shape, wrapped in a ```json code block):\n"
        f"```json\n{{\n  \"tasks\": [ <full updated task JSON with criterion at index {idx} replaced> ],\n  \"lesson\": null\n}}\n```\n"
    )

    try:
        result = subprocess.run(
            ["claude", "--print",
             "--output-format", "stream-json", "--verbose",
             "--model", "claude-opus-4-7",
             "--dangerously-skip-permissions", prompt],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=600,
        )
        raw_stdout = result.stdout or ""
        stderr = result.stderr.strip() if result.stderr else ""
        if stderr:
            print(f"[convert_criterion] Claude stderr: {stderr[:500]}", flush=True)
        events, final_result = _parse_claude_stream_jsonl(raw_stdout)
        output = (final_result or "").strip()
        if result.returncode != 0:
            return jsonify({
                "status": "error",
                "error": f"Claude exited with code {result.returncode}: {stderr[:500] or output[:500]}",
                "trace": events,
            }), 500

        tasks_list, lesson = _parse_adjustment_output(output)
        if not tasks_list:
            return jsonify({
                "status": "error",
                "error": "Could not parse proposed task JSON from Claude's output",
                "raw_output": output[-3000:],
                "trace": events,
            }), 400

        proposed = tasks_list[0]

        _pending_proposals[task_id] = {
            "original": task,
            "proposed": proposed,
            "lesson": lesson,
            "suggestion": f"Convert criterion #{idx} to LLM-as-judge",
            "timestamp": datetime.now().isoformat(),
            "trace": events,
        }

        return jsonify({
            "status": "proposed",
            "original": task,
            "proposed": proposed,
            "lesson": lesson,
            "trace": events,
        })

    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "error": "Claude Code timed out (10 min limit)"}), 504
    except FileNotFoundError:
        return jsonify({"status": "error", "error": "Claude Code CLI not found"}), 500
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/tasks/<task_id>/delete_criterion", methods=["POST"])
def api_delete_criterion(task_id):
    """Delete a single verification criterion from a task."""
    task = load_task_by_id(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    running = _running_tasks.get(task_id)
    if running and running.get("status") in ("starting", "running"):
        return jsonify({"error": "Task is currently running"}), 409

    body = request.json or {}
    try:
        idx = int(body.get("index"))
    except (TypeError, ValueError):
        return jsonify({"error": "criterion index required"}), 400

    verifs = list(task.get("verification", []) or [])
    if idx < 0 or idx >= len(verifs):
        return jsonify({"error": "index out of range"}), 400
    if len(verifs) <= 1:
        return jsonify({"error": "Task must keep at least one verification check"}), 400

    removed = verifs.pop(idx)
    updated = dict(task)
    updated["verification"] = verifs

    task_dir = TASKS_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    with open(task_dir / "task.json", "w") as f:
        json.dump(updated, f, indent=2)

    _pending_proposals.pop(task_id, None)
    _clear_results_for_task(task_id)

    return jsonify({
        "status": "deleted",
        "task": updated,
        "deleted_index": idx,
        "deleted_check": removed,
    })


@app.route("/api/tasks/<task_id>/approve", methods=["POST"])
def api_approve_task(task_id):
    """Apply a pending task proposal."""
    if task_id not in _pending_proposals:
        return jsonify({"error": "No pending proposal for this task"}), 404

    proposal = _pending_proposals.pop(task_id)
    proposed = proposal["proposed"]
    lesson = proposal.get("lesson")

    # Save lesson if present
    _save_lesson(lesson)

    # Write task.json
    task_dir = TASKS_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    with open(task_dir / "task.json", "w") as f:
        json.dump(proposed, f, indent=2)

    # Clear old results since the task changed
    _clear_results_for_task(task_id)

    return jsonify({"status": "approved", "task": proposed})


@app.route("/api/tasks/<task_id>/reject", methods=["POST"])
def api_reject_task(task_id):
    """Discard a pending task proposal."""
    _pending_proposals.pop(task_id, None)
    return jsonify({"status": "rejected"})


# ── Task generation ──────────────────────────────────────────────────────────

@app.route("/api/judge/<path:run_id>")
def api_get_judge_all(run_id):
    """Get all cached LLM judge results for a run."""
    results = {}
    run_dir = _resolve_eval_run_dir(run_id)
    if run_dir is None:
        return jsonify(results)
    trajs_root = run_dir / "trajectories"
    if trajs_root.exists():
        for d in trajs_root.iterdir():
            if not d.is_dir():
                continue
            judge_file = d / "llm_judge.json"
            if judge_file.exists():
                try:
                    with open(judge_file) as f:
                        judge_data = json.load(f)
                    traj_file = d / "trajectory.json"
                    verification_details = None
                    if traj_file.exists():
                        try:
                            with open(traj_file) as tf:
                                verification_details = json.load(tf).get("verification_details")
                        except (json.JSONDecodeError, IOError):
                            verification_details = None
                    results[d.name] = _compute_judge_accuracy(judge_data, verification_details)
                except (json.JSONDecodeError, IOError):
                    continue
    return jsonify(results)


@app.route("/api/judge/<path:run_id>/<traj_subdir>")
def api_get_judge(run_id, traj_subdir):
    """Get cached LLM judge result if available. ?source=repair uses repair runs."""
    source = request.args.get("source", "eval")
    if source == "repair":
        judge_file = REPAIR_RUNS_DIR / run_id / "judge" / "llm_judge.json"
        verification_details = None
        traj_data = _load_repair_trajectory(REPAIR_RUNS_DIR / run_id)
        if traj_data:
            verification_details = traj_data.get("verification_details")
    else:
        run_dir = _resolve_eval_run_dir(run_id)
        if run_dir is None:
            return jsonify({"status": "none"})
        judge_file = run_dir / "trajectories" / traj_subdir / "llm_judge.json"
        verification_details = None
        traj_file = run_dir / "trajectories" / traj_subdir / "trajectory.json"
        if traj_file.exists():
            try:
                with open(traj_file) as tf:
                    verification_details = json.load(tf).get("verification_details")
            except (json.JSONDecodeError, IOError):
                verification_details = None
    if judge_file.exists():
        try:
            with open(judge_file) as f:
                return jsonify({
                    "status": "done",
                    "result": _compute_judge_accuracy(json.load(f), verification_details),
                })
        except (json.JSONDecodeError, IOError):
            pass
    return jsonify({"status": "none"})


_pending_generated = {}  # key -> {app, tasks, prompt, timestamp}

# LLM judge results cache: (task_id, run_id, traj_subdir) -> judge result dict
_judge_results = {}


# ── LLM Judge ───────────────────────────────────────────────────────────

@app.route("/api/tasks/<task_id>/judge", methods=["POST"])
def api_judge_task(task_id):
    """Run LLM-as-Judge evaluation on a task trajectory."""
    body = request.json or {}
    run_id = body.get("run_id")
    traj_subdir = body.get("traj_subdir")

    if not run_id or not traj_subdir:
        return jsonify({"error": "run_id and traj_subdir required"}), 400

    # Check in-memory cache
    cache_key = (task_id, run_id, traj_subdir)
    if cache_key in _judge_results:
        return jsonify({"status": "done", "result": _judge_results[cache_key]})

    run_dir = _resolve_eval_run_dir(run_id)
    if run_dir is None:
        return jsonify({"error": "Trajectory not found"}), 404
    traj_dir = run_dir / "trajectories" / traj_subdir
    traj_file = traj_dir / "trajectory.json"
    if not traj_file.exists():
        return jsonify({"error": "Trajectory not found"}), 404

    # Load trajectory
    with open(traj_file) as f:
        traj_data = json.load(f)

    # Check on-disk cache
    judge_file = run_dir / "trajectories" / traj_subdir / "llm_judge.json"
    if judge_file.exists():
        try:
            with open(judge_file) as f:
                cached = _compute_judge_accuracy(json.load(f), traj_data.get("verification_details"))
            _judge_results[cache_key] = cached
            return jsonify({"status": "done", "result": cached})
        except (json.JSONDecodeError, IOError):
            pass

    # Load task for verification checklist
    task = load_task_by_id(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    # Build the trajectory summary for the prompt
    steps = traj_data.get("trajectory", [])
    traj_summary_lines = []
    for s in steps:
        reasoning_snippet = (s.get("reasoning") or "")[:300]
        actions = s.get("actions", [])
        action_str = "; ".join(str(a)[:100] for a in actions)
        traj_summary_lines.append(
            f"Step {s['step']}: [screenshot: step_{s['step']:03d}.png] "
            f"reasoning: {reasoning_snippet} | actions: {action_str}"
        )
    traj_summary = "\n".join(traj_summary_lines)

    # Build verification checklist
    verifs = task.get("verification", [])
    checklist_lines = []
    for i, v in enumerate(verifs, 1):
        desc = v.get("description", v.get("command", ""))
        checklist_lines.append(f"{i}. {desc}")
    checklist = "\n".join(checklist_lines)

    # Screenshot directory
    ss_dir = traj_dir / "screenshots"

    # Find all step screenshots
    ss_files = sorted(ss_dir.glob("step_*.png")) if ss_dir.exists() else []
    total_steps = len(ss_files)

    # Final screenshots (last 3 step screenshots + final_*.png)
    final_ss = []
    if total_steps >= 3:
        final_ss = [s.name for s in ss_files[-3:]]
    elif ss_files:
        final_ss = [s.name for s in ss_files]

    # Also include final_before_verify.png and final_after_verify.png if they exist
    for fname in ["final_before_verify.png", "final_after_verify.png"]:
        if (ss_dir / fname).exists():
            final_ss.append(fname)

    final_ss_str = ", ".join(final_ss)

    prompt = (
        f"You are an LLM judge evaluating whether a GUI agent successfully completed a task.\n\n"
        f"Read the file evaluation/llm_judge.md for the full evaluation process and required output format.\n\n"
        f"## Task\n{task.get('task', '')}\n\n"
        f"## Verification Checklist\n{checklist}\n\n"
        f"## Trajectory Summary\n"
        f"The agent took {len(steps)} steps. Here is a summary of each step's reasoning and actions:\n\n"
        f"{traj_summary}\n\n"
        f"## Screenshots\n"
        f"Screenshots are in: {ss_dir}\n"
        f"There are {total_steps} step screenshots (step_001.png through step_{total_steps:03d}.png).\n"
        f"The final screenshots to always check are: {final_ss_str}\n\n"
        f"## Instructions\n"
        f"1. Read the trajectory summary above to identify which steps are most relevant for verifying each checker condition.\n"
        f"2. Read the key screenshots (the ones after the relevant actions) plus the final screenshots listed above.\n"
        f"3. For each checker condition, determine if it passed or failed based on visual evidence.\n"
        f"4. Output ONLY the JSON object as specified in evaluation/llm_judge.md. No markdown fences, no explanation outside the JSON.\n"
    )

    try:
        result = subprocess.run(
            ["claude", "--print",
             "--output-format", "stream-json", "--verbose",
             "--model", "claude-sonnet-4-6",
             "--dangerously-skip-permissions", prompt],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=600,
        )

        raw_stdout = result.stdout or ""
        stderr = result.stderr.strip() if result.stderr else ""
        if stderr:
            print(f"[judge] Claude stderr: {stderr[:500]}", flush=True)
        events, final_result = _parse_claude_stream_jsonl(raw_stdout)
        output = (final_result or "").strip()
        if result.returncode != 0:
            return jsonify({
                "status": "error",
                "error": f"Claude exited with code {result.returncode}: {stderr[:500] or output[:500]}",
                "trace": events,
            }), 500

        # Parse JSON from output
        parsed = None
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            pass
        if parsed is None:
            m = re.search(r'```(?:json)?\s*\n(.*?)\n```', output, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass
        if parsed is None:
            start = output.find('{')
            end = output.rfind('}')
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(output[start:end + 1])
                except json.JSONDecodeError:
                    pass

        if not parsed or "checks" not in parsed:
            return jsonify({
                "status": "error",
                "error": "Could not parse judge output as JSON",
                "raw_output": output[-3000:],
                "trace": events,
            }), 400

        # Compute accuracy vs programmatic checker
        prog_details = traj_data.get("verification_details", [])
        judge_checks = parsed.get("checks", [])
        matches = 0
        total = min(len(prog_details), len(judge_checks))
        for i in range(total):
            prog_passed = prog_details[i].get("passed", False)
            judge_passed = judge_checks[i].get("passed", False)
            if prog_passed == judge_passed:
                matches += 1

        parsed["accuracy"] = matches / total if total > 0 else None
        parsed["matches"] = matches
        parsed["total_compared"] = total

        # Cache result in memory and on disk
        _judge_results[cache_key] = parsed
        judge_file = run_dir / "trajectories" / traj_subdir / "llm_judge.json"
        try:
            with open(judge_file, "w") as f:
                json.dump(parsed, f, indent=2)
        except IOError:
            pass

        return jsonify({"status": "done", "result": parsed, "trace": events})

    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "error": "Claude Code timed out (10 min limit)"}), 504
    except FileNotFoundError:
        return jsonify({"status": "error", "error": "Claude Code CLI not found"}), 500
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def api_generate_tasks():
    """Launch task generation for an app via Claude Code CLI in the background.

    Returns immediately with a gen_key. The caller polls
    /api/generate/status/<gen_key> for live trace events and the parsed
    proposals once generation completes.
    """
    body = request.json or {}
    app_name = body.get("app", "").strip()
    count = body.get("count", 5)
    guidance = body.get("guidance", "").strip()

    if not app_name:
        return jsonify({"error": "No app provided"}), 400

    existing = load_all_tasks().get(app_name, [])
    existing_ids = [t["id"] for t in existing]
    existing_summary = ", ".join(existing_ids) if existing_ids else "none"

    prompt = (
        f"Read task_generator/CLAUDE.md for the full pipeline instructions.\n"
        f"Read verifiers/{app_name}/README.md for available verification endpoints.\n"
        f"Read task_generator/LESSONS.md for past design lessons.\n\n"
        f"Generate {count} NEW complete task JSONs for the app '{app_name}'.\n"
        f"These tasks already exist (do NOT duplicate them): {existing_summary}\n\n"
    )
    if guidance:
        prompt += f"Additional guidance from the user:\n{guidance}\n\n"
    prompt += (
        f"For each task, produce a COMPLETE task.json object with all fields: "
        f"id, app, task, env, verification, metadata. "
        f"Follow Stage 1 (generation) and Stage 4 (criteria refinement) from CLAUDE.md.\n\n"
        f"Output a JSON object: {{\"tasks\": [...], \"lesson\": \"...or null\"}}\n"
        f"Output ONLY the JSON, no explanation, no markdown fences."
    )

    gen_key = f"gen_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cmd = [
        "claude", "--print",
        "--output-format", "stream-json", "--verbose",
        "--model", "claude-opus-4-7",
        "--dangerously-skip-permissions", prompt,
    ]
    try:
        _start_bg_process(gen_key, cmd, cwd=str(PROJECT_ROOT), kind="generate_tasks")
    except FileNotFoundError:
        return jsonify({"status": "error", "error": "Claude Code CLI not found"}), 500
    except Exception as e:  # noqa: BLE001
        return jsonify({"status": "error", "error": str(e)}), 500

    info = _synth_processes.get(gen_key, {})
    info["app_name"] = app_name

    return jsonify({"status": "started", "gen_key": gen_key})


@app.route("/api/generate/status/<gen_key>")
def api_generate_status(gen_key):
    """Poll status + live trace for a background task-generation run.

    Returns events incrementally while running. On completion, lazily parses
    Claude's final output into tasks/lesson, populates _pending_generated, and
    includes them in the response so the caller can render proposals.
    """
    info = _synth_processes.get(gen_key)
    if not info:
        return jsonify({"status": "idle"})

    payload = {
        "status": info["status"],
        "kind": info.get("kind"),
        "started_at": info.get("started_at"),
        "exit_code": info.get("exit_code"),
        "events": info.get("events", [])[-400:],
        "event_count": len(info.get("events", [])),
        "line_count": len(info.get("output_lines", [])),
        "is_claude_stream": info.get("is_claude_stream", False),
    }

    if info["status"] in ("completed", "error") and not info.get("parsed"):
        info["parsed"] = True
        raw = "\n".join(info.get("output_lines", []))
        events, final_result = _parse_claude_stream_jsonl(raw)
        output = (final_result or "").strip()
        tasks_list, lesson = _parse_adjustment_output(output)
        info["tasks"] = tasks_list
        info["lesson"] = lesson
        info["final_output"] = output
        info["all_events"] = events
        if tasks_list:
            _pending_generated[gen_key] = {
                "app": info.get("app_name"),
                "tasks": tasks_list,
                "lesson": lesson,
                "timestamp": datetime.now().isoformat(),
                "trace": events,
            }
        else:
            info["parse_error"] = "Could not parse generated tasks from Claude's output"

    if info.get("parsed"):
        payload["tasks"] = info.get("tasks") or []
        payload["lesson"] = info.get("lesson")
        if info.get("parse_error"):
            payload["parse_error"] = info["parse_error"]
            payload["raw_output"] = (info.get("final_output") or "")[-3000:]

    return jsonify(payload)


@app.route("/api/generate/approve", methods=["POST"])
def api_generate_approve():
    """Accept generated tasks and save them."""
    body = request.json or {}
    gen_key = body.get("gen_key")

    if not gen_key or gen_key not in _pending_generated:
        return jsonify({"error": "No pending generation found"}), 404

    gen = _pending_generated.pop(gen_key)
    app_name = gen["app"]
    new_tasks = gen["tasks"]
    lesson = gen.get("lesson")

    _save_lesson(lesson)

    existing_ids = {t["id"] for t in load_all_tasks().get(app_name, [])}
    added = []

    for task in new_tasks:
        tid = task.get("id")
        if not tid or tid in existing_ids:
            continue

        # Write individual task.json
        task_dir = TASKS_DIR / tid
        task_dir.mkdir(parents=True, exist_ok=True)
        with open(task_dir / "task.json", "w") as f:
            json.dump(task, f, indent=2)

        existing_ids.add(tid)
        added.append(tid)

    total = len(load_all_tasks().get(app_name, []))
    return jsonify({"status": "approved", "added": added, "total": total})


@app.route("/api/generate/reject", methods=["POST"])
def api_generate_reject():
    """Discard generated tasks."""
    body = request.json or {}
    gen_key = body.get("gen_key")
    _pending_generated.pop(gen_key, None)
    return jsonify({"status": "rejected"})


# ── Synthesis: verifiers + smoke + env (read-only browse + actions) ─────────

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_SAFE_FILE_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
_synth_processes = {}  # key -> {status, started_at, output_lines, exit_code, pid, kind, cmd}


def _safe_app_name(name):
    return bool(name) and bool(_SAFE_NAME_RE.match(name))


def _safe_filename(name):
    return bool(name) and bool(_SAFE_FILE_RE.match(name)) and ".." not in name


def _extract_endpoints(app_dir, app_name):
    """Extract CLI subcommand names by parsing <app>.py and README.md.

    Handles three styles:
      1. Dispatch dict: `"name": ("desc", lambda...)`
      2. argparse subparsers: `add_parser("name", ...)`
      3. if/elif chain: `cmd == "name"` (also command, args.command, sys.argv[1])

    Falls back to README `####` header count if the .py file matches none.
    """
    py = app_dir / f"{app_name}.py"
    names = set()
    if py.exists():
        try:
            text = py.read_text(errors="replace")
        except (IOError, OSError):
            text = ""
        # Dispatch dict: key followed by a parenthesized expression that starts with a string
        names.update(re.findall(
            r'^\s*[\'"]([a-z][a-z0-9_-]*)[\'"]\s*:\s*\(\s*[\'"]',
            text, re.MULTILINE))
        # argparse subparsers
        names.update(re.findall(
            r'add_parser\(\s*[\'"]([a-z][a-z0-9_-]*)[\'"]', text))
        # if/elif chain
        names.update(re.findall(
            r'\b(?:cmd|command|action|args\.command|sys\.argv\[1\])\s*==\s*'
            r'[\'"]([a-z][a-z0-9_-]*)[\'"]', text))
    if names:
        return sorted(names)

    # Fallback: parse README command reference headers.
    readme = app_dir / "README.md"
    if readme.exists():
        try:
            text = readme.read_text(errors="replace")
            headers = re.findall(r"^####\s+`?([a-z][a-z0-9_-]*)`?", text, re.MULTILINE)
            if headers:
                return sorted(set(headers))
            rows = re.findall(r"^\|\s*`([a-z][a-z0-9_-]*)`", text, re.MULTILINE)
            if rows:
                return sorted(set(rows))
        except (IOError, OSError):
            pass
    return []


def _count_endpoints(app_dir, app_name):
    return len(_extract_endpoints(app_dir, app_name))


def _summarize_claude_event(ev):
    """Convert a raw claude stream-json event into a compact dashboard summary.

    Returns None for events we don't render (partial deltas, etc.).
    """
    if not isinstance(ev, dict):
        return None
    t = ev.get("type")
    if t == "system":
        if ev.get("subtype") == "init":
            return {
                "type": "system_init",
                "model": ev.get("model"),
                "cwd": ev.get("cwd"),
                "tools": ev.get("tools", []),
                "session_id": ev.get("session_id"),
            }
        return None
    if t == "assistant":
        msg = ev.get("message") or {}
        blocks_out = []
        for block in (msg.get("content") or []):
            bt = block.get("type")
            if bt == "text":
                blocks_out.append({"type": "text", "text": block.get("text", "")})
            elif bt == "thinking":
                blocks_out.append({"type": "thinking", "text": block.get("thinking", "")})
            elif bt == "tool_use":
                blocks_out.append({
                    "type": "tool_use",
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input", {}),
                })
        if not blocks_out:
            return None
        return {"type": "assistant", "blocks": blocks_out, "usage": msg.get("usage")}
    if t == "user":
        msg = ev.get("message") or {}
        results = []
        for block in (msg.get("content") or []):
            if block.get("type") != "tool_result":
                continue
            content = block.get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                parts = []
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        parts.append(c.get("text", ""))
                text = "\n".join(parts)
            else:
                text = ""
            results.append({
                "type": "tool_result",
                "tool_use_id": block.get("tool_use_id"),
                "is_error": bool(block.get("is_error")),
                "text": (text or "")[:8000],
            })
        if not results:
            return None
        return {"type": "tool_result_batch", "results": results}
    if t == "result":
        return {
            "type": "result",
            "subtype": ev.get("subtype"),
            "is_error": bool(ev.get("is_error")),
            "duration_ms": ev.get("duration_ms"),
            "result": ev.get("result"),
            "usage": ev.get("usage"),
            "num_turns": ev.get("num_turns"),
        }
    return None


def _parse_claude_stream_jsonl(text):
    """Parse a stream-json JSONL text dump into (events, final_result_text).

    Use for foreground (blocking) claude calls where we have the full output.
    """
    events = []
    final_result = None
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        ev = _summarize_claude_event(raw)
        if ev is not None:
            events.append(ev)
        if raw.get("type") == "result" and not raw.get("is_error"):
            final_result = raw.get("result")
    return events, final_result


def _is_claude_stream_cmd(cmd):
    """Heuristic: command is `claude ... --output-format stream-json ...`."""
    if not cmd or cmd[0] != "claude":
        return False
    flags = cmd[1:]
    for i, f in enumerate(flags):
        if f == "--output-format" and i + 1 < len(flags) and flags[i + 1] == "stream-json":
            return True
    return False


def _start_bg_process(key, cmd, cwd, kind):
    """Run cmd in a background thread.

    For `claude --output-format stream-json` invocations, parses each line as a
    stream-json event into info["events"]. Raw lines are always also kept in
    info["output_lines"] as a debug fallback.
    """
    is_claude_stream = _is_claude_stream_cmd(cmd)
    info = {
        "status": "starting",
        "started_at": datetime.now().isoformat(),
        "output_lines": [],
        "events": [],
        "is_claude_stream": is_claude_stream,
        "kind": kind,
        "cmd": " ".join(cmd[:6]) + ("..." if len(cmd) > 6 else ""),
    }
    _synth_processes[key] = info

    def _runner():
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=cwd,
            )
            info["pid"] = proc.pid
            info["status"] = "running"
            for line in proc.stdout:
                line = line.rstrip()
                info["output_lines"].append(line)
                if len(info["output_lines"]) > 4000:
                    info["output_lines"].pop(0)
                if is_claude_stream and line.startswith("{"):
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        raw = None
                    if raw is not None:
                        ev = _summarize_claude_event(raw)
                        if ev is not None:
                            info["events"].append(ev)
                            if len(info["events"]) > 2000:
                                info["events"].pop(0)
            proc.wait()
            info["exit_code"] = proc.returncode
            info["status"] = "completed" if proc.returncode == 0 else "error"
        except Exception as e:  # noqa: BLE001
            info["status"] = "error"
            info["output_lines"].append(f"[server error] {e}")

    threading.Thread(target=_runner, daemon=True).start()


def _proc_status_payload(key):
    info = _synth_processes.get(key)
    if not info:
        return {"status": "idle"}
    return {
        "status": info["status"],
        "kind": info.get("kind"),
        "started_at": info.get("started_at"),
        "exit_code": info.get("exit_code"),
        "output": "\n".join(info.get("output_lines", [])[-400:]),
        "line_count": len(info.get("output_lines", [])),
        "events": info.get("events", [])[-400:],
        "event_count": len(info.get("events", [])),
        "is_claude_stream": info.get("is_claude_stream", False),
    }


# ── Verifiers ────────────────────────────────────────────────────────────────

@app.route("/api/synthesis/verifiers")
def api_synthesis_verifiers():
    """List all subdirs of verifiers/ with metadata (existence of files, endpoint count)."""
    out = []
    if not VERIFIERS_DIR.exists():
        return jsonify(out)
    for d in sorted(VERIFIERS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or d.name == "__pycache__":
            continue
        verifier_py = d / f"{d.name}.py"
        readme = d / "README.md"
        test_md = d / "Test.md"
        test_py = d / f"test_{d.name}.py"
        endpoints = _extract_endpoints(d, d.name)
        out.append({
            "app": d.name,
            "has_verifier": verifier_py.exists(),
            "has_readme": readme.exists(),
            "has_test_md": test_md.exists(),
            "has_test_py": test_py.exists(),
            "endpoint_count": len(endpoints),
            "endpoints": endpoints[:12],
            "verifier_mtime": verifier_py.stat().st_mtime if verifier_py.exists() else None,
        })
    return jsonify(out)


@app.route("/api/synthesis/verifiers/<app_name>")
def api_synthesis_verifier_detail(app_name):
    if not _safe_app_name(app_name):
        return jsonify({"error": "Invalid app"}), 400
    app_dir = VERIFIERS_DIR / app_name
    if not app_dir.is_dir():
        return jsonify({"error": "App not found"}), 404
    files = []
    for f in sorted(app_dir.iterdir()):
        if f.is_file():
            files.append({"name": f.name, "size": f.stat().st_size})
    readme = app_dir / "README.md"
    test_md = app_dir / "Test.md"
    verifier_py = app_dir / f"{app_name}.py"
    source = None
    if verifier_py.exists():
        try:
            source = verifier_py.read_text(errors="replace")
        except (IOError, OSError):
            source = None
    endpoints = _extract_endpoints(app_dir, app_name)
    return jsonify({
        "app": app_name,
        "files": files,
        "readme": readme.read_text(errors="replace") if readme.exists() else None,
        "test_md": test_md.read_text(errors="replace") if test_md.exists() else None,
        "verifier_source": source,
        "endpoint_count": len(endpoints),
        "endpoints": endpoints,
    })


@app.route("/api/synthesis/verifiers/<app_name>/file/<path:filename>")
def api_synthesis_verifier_file(app_name, filename):
    if not _safe_app_name(app_name) or not _safe_filename(filename):
        return jsonify({"error": "Invalid path"}), 400
    fpath = (VERIFIERS_DIR / app_name / filename).resolve()
    try:
        fpath.relative_to(VERIFIERS_DIR.resolve())
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400
    if not fpath.is_file():
        return jsonify({"error": "Not found"}), 404
    try:
        return Response(fpath.read_text(errors="replace"), mimetype="text/plain; charset=utf-8")
    except (IOError, OSError):
        return jsonify({"error": "Cannot read file"}), 500


@app.route("/api/synthesis/verifiers/<app_name>/test", methods=["POST"])
def api_synthesis_verifier_test(app_name):
    if not _safe_app_name(app_name):
        return jsonify({"error": "Invalid app"}), 400
    test_py = VERIFIERS_DIR / app_name / f"test_{app_name}.py"
    if not test_py.exists():
        return jsonify({"error": f"test_{app_name}.py not found"}), 404
    key = f"verifier_test:{app_name}"
    if _synth_processes.get(key, {}).get("status") in ("starting", "running"):
        return jsonify({"status": "already_running", "key": key})
    cmd = [sys.executable, "-u", str(test_py)]
    _start_bg_process(key, cmd, str(PROJECT_ROOT), kind="verifier_test")
    return jsonify({"status": "started", "key": key})


@app.route("/api/synthesis/verifiers/<app_name>/test/status")
def api_synthesis_verifier_test_status(app_name):
    if not _safe_app_name(app_name):
        return jsonify({"error": "Invalid app"}), 400
    return jsonify(_proc_status_payload(f"verifier_test:{app_name}"))


@app.route("/api/synthesis/verifiers/<app_name>/create", methods=["POST"])
def api_synthesis_verifier_create(app_name):
    """Create an empty verifier directory for a new app.

    Does NOT launch Claude. The user follows the pipeline (Generate via Claude,
    Run Tests, etc.) from the detail view afterward.
    """
    if not _safe_app_name(app_name):
        return jsonify({"error": "Invalid app"}), 400
    app_dir = VERIFIERS_DIR / app_name
    if app_dir.exists():
        return jsonify({"error": f"App '{app_name}' already exists"}), 409
    try:
        app_dir.mkdir(parents=True, exist_ok=False)
    except OSError as e:
        return jsonify({"error": f"Could not create {app_dir}: {e}"}), 500
    return jsonify({"status": "created", "app": app_name})


@app.route("/api/synthesis/verifiers/<app_name>/generate", methods=["POST"])
def api_synthesis_verifier_generate(app_name):
    if not _safe_app_name(app_name):
        return jsonify({"error": "Invalid app"}), 400
    body = request.json or {}
    instructions = (body.get("instructions") or "").strip()

    app_dir = VERIFIERS_DIR / app_name
    is_new = not (app_dir / f"{app_name}.py").exists()
    parts = ["Read verifiers/CLAUDE.md for the verifier authoring workflow."]
    if is_new:
        parts.append(
            f"Create a new verifier module at verifiers/{app_name}/ with files "
            f"{app_name}.py, README.md, Test.md, and test_{app_name}.py. "
            f"Follow the workflow exactly: design endpoints, document them, "
            f"write Test.md before tests, then implement test_{app_name}.py and run it."
        )
    else:
        parts.append(
            f"Extend the existing verifier at verifiers/{app_name}/. "
            f"First read verifiers/{app_name}/README.md and verifiers/{app_name}/{app_name}.py, "
            f"then add new endpoints, update README.md and Test.md, and add or extend tests."
        )
    if instructions:
        parts.append(f"\nUser instructions:\n{instructions}")
    prompt = "\n\n".join(parts)

    key = f"verifier_gen:{app_name}"
    if _synth_processes.get(key, {}).get("status") in ("starting", "running"):
        return jsonify({"status": "already_running", "key": key})

    # Create the verifier directory eagerly so the new app shows up in the
    # listing and detail view while Claude is still generating files into it.
    if is_new:
        try:
            app_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return jsonify({"error": f"Could not create {app_dir}: {e}"}), 500

    cmd = ["claude", "--print",
           "--output-format", "stream-json", "--verbose",
           "--model", "claude-opus-4-7",
           "--dangerously-skip-permissions", prompt]
    _start_bg_process(key, cmd, str(PROJECT_ROOT), kind="verifier_gen")
    return jsonify({"status": "started", "key": key, "is_new": is_new})


@app.route("/api/synthesis/verifiers/<app_name>/generate/status")
def api_synthesis_verifier_generate_status(app_name):
    if not _safe_app_name(app_name):
        return jsonify({"error": "Invalid app"}), 400
    return jsonify(_proc_status_payload(f"verifier_gen:{app_name}"))


# ── Smoke ────────────────────────────────────────────────────────────────────

_SMOKE_TS_RE = re.compile(r"^(.+?)_(\d{8})_(\d{6})$")


def _list_smoke_runs():
    runs = []
    if not SMOKE_RUNS_DIR.exists():
        return runs
    for d in sorted(SMOKE_RUNS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        m = _SMOKE_TS_RE.match(d.name)
        app_name = m.group(1) if m else d.name
        ts = None
        if m:
            try:
                ts = datetime.strptime(m.group(2) + m.group(3), "%Y%m%d%H%M%S").isoformat()
            except ValueError:
                pass
        task_count = 0
        solved_count = 0
        for sub in d.iterdir():
            if not sub.is_dir() or sub.name == "__pycache__":
                continue
            task_count += 1
            if (sub / "SOLVED.md").exists():
                solved_count += 1
        runs.append({
            "run_id": d.name,
            "app": app_name,
            "timestamp": ts,
            "task_count": task_count,
            "solved_count": solved_count,
            "has_report": (d / "REPORT.md").exists(),
        })
    return runs


@app.route("/api/synthesis/smoke/runs")
def api_synthesis_smoke_runs():
    return jsonify(_list_smoke_runs())


def _list_canonical_smoke_tasks(app_name):
    """Return canonical smoke task ids for an app from smoke/smoke_tasks/<app>/."""
    app_dir = SMOKE_TASKS_DIR / app_name
    if not app_dir.is_dir():
        return []
    ids = []
    for sub in sorted(app_dir.iterdir()):
        if not sub.is_dir() or sub.name == "__pycache__":
            continue
        if (sub / "task.json").exists():
            ids.append(sub.name)
    return ids


def _scan_run_dirs_for_app(app_name):
    """Yield (run_dir, ts_iso) for every run directory belonging to this app."""
    if not SMOKE_RUNS_DIR.exists():
        return
    for d in sorted(SMOKE_RUNS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        m = _SMOKE_TS_RE.match(d.name)
        if not m or m.group(1) != app_name:
            continue
        ts = None
        try:
            ts = datetime.strptime(m.group(2) + m.group(3), "%Y%m%d%H%M%S").isoformat()
        except ValueError:
            pass
        yield d, ts


def _aggregate_smoke_task_statuses(app_name):
    """For one app, return list of {id, status, latest_run_id, latest_ts}.

    Status is one of: 'solved' (any run has SOLVED.md), 'errored' (every run
    that touched it errored), or 'not_run' (no run dir contains it).
    """
    canonical = _list_canonical_smoke_tasks(app_name)
    # task_id -> {"solved": [(ts, run_id)], "errored": [(ts, run_id)], "other": [(ts, run_id)]}
    seen = {tid: {"solved": [], "errored": [], "other": []} for tid in canonical}
    for run_dir, ts in _scan_run_dirs_for_app(app_name):
        for sub in run_dir.iterdir():
            if not sub.is_dir() or sub.name == "__pycache__":
                continue
            tid = sub.name
            if tid not in seen:
                continue
            if (sub / "SOLVED.md").exists():
                seen[tid]["solved"].append((ts, run_dir.name))
            elif (sub / "error.txt").exists():
                seen[tid]["errored"].append((ts, run_dir.name))
            else:
                seen[tid]["other"].append((ts, run_dir.name))

    out = []
    for tid in canonical:
        info = seen[tid]
        if info["solved"]:
            ts, run_id = max(info["solved"], key=lambda x: x[0] or "")
            status = "solved"
        elif info["errored"]:
            ts, run_id = max(info["errored"], key=lambda x: x[0] or "")
            status = "errored"
        elif info["other"]:
            ts, run_id = max(info["other"], key=lambda x: x[0] or "")
            status = "errored"  # touched but neither solved nor errored — treat as error
        else:
            ts, run_id, status = None, None, "not_run"
        out.append({
            "id": tid,
            "status": status,
            "latest_run_id": run_id,
            "latest_ts": ts,
        })
    return out


def _list_smoke_apps():
    """Group smoke state by app, ignoring run boundaries.

    For each app with either canonical smoke tasks or any run history, return:
      {app, total, solved, errored, not_run, latest_ts, tasks: [...]}.
    """
    apps = set()
    if SMOKE_TASKS_DIR.exists():
        for d in SMOKE_TASKS_DIR.iterdir():
            if d.is_dir() and (d.name != "__pycache__"):
                apps.add(d.name)
    if SMOKE_RUNS_DIR.exists():
        for d in SMOKE_RUNS_DIR.iterdir():
            if d.is_dir():
                m = _SMOKE_TS_RE.match(d.name)
                if m:
                    apps.add(m.group(1))

    out = []
    for app_name in sorted(apps):
        tasks = _aggregate_smoke_task_statuses(app_name)
        solved = sum(1 for t in tasks if t["status"] == "solved")
        errored = sum(1 for t in tasks if t["status"] == "errored")
        not_run = sum(1 for t in tasks if t["status"] == "not_run")
        latest_ts = None
        for t in tasks:
            if t.get("latest_ts") and (latest_ts is None or t["latest_ts"] > latest_ts):
                latest_ts = t["latest_ts"]
        out.append({
            "app": app_name,
            "total": len(tasks),
            "solved": solved,
            "errored": errored,
            "not_run": not_run,
            "latest_ts": latest_ts,
            "tasks": tasks,
        })
    # Most recently active apps first; apps with no runs at the end alphabetically.
    active = sorted([a for a in out if a["latest_ts"]],
                    key=lambda a: a["latest_ts"], reverse=True)
    inactive = sorted([a for a in out if not a["latest_ts"]], key=lambda a: a["app"])
    return active + inactive


@app.route("/api/synthesis/smoke/apps")
def api_synthesis_smoke_apps():
    return jsonify(_list_smoke_apps())


@app.route("/api/synthesis/smoke/task/<app_name>/<task_id>")
def api_synthesis_smoke_task(app_name, task_id):
    """Return the latest SOLVED.md (and run id) for a smoke task across all runs."""
    if not _safe_app_name(app_name):
        return jsonify({"error": "Invalid app"}), 400
    if "/" in task_id or ".." in task_id or not task_id:
        return jsonify({"error": "Invalid task_id"}), 400

    latest = None  # (ts, run_id, run_dir, kind)
    for run_dir, ts in _scan_run_dirs_for_app(app_name):
        sub = run_dir / task_id
        if not sub.is_dir():
            continue
        if (sub / "SOLVED.md").exists():
            kind = "solved"
        elif (sub / "error.txt").exists():
            kind = "errored"
        else:
            kind = "other"
        cand = (ts or "", run_dir.name, sub, kind)
        # Prefer solved over errored when ts ties or solved is newer
        if latest is None:
            latest = cand
        else:
            if kind == "solved" and latest[3] != "solved":
                latest = cand
            elif kind == latest[3] and cand[0] > latest[0]:
                latest = cand

    if latest is None:
        return jsonify({
            "app": app_name,
            "task_id": task_id,
            "status": "not_run",
            "solved_md": None,
            "error_text": None,
            "latest_run_id": None,
            "latest_ts": None,
        })

    ts, run_id, sub, kind = latest
    solved_md = None
    error_text = None
    if (sub / "SOLVED.md").exists():
        solved_md = (sub / "SOLVED.md").read_text(errors="replace")
    if (sub / "error.txt").exists():
        error_text = (sub / "error.txt").read_text(errors="replace")
    return jsonify({
        "app": app_name,
        "task_id": task_id,
        "status": "solved" if solved_md else ("errored" if error_text else kind),
        "solved_md": solved_md,
        "error_text": error_text,
        "latest_run_id": run_id,
        "latest_ts": ts or None,
    })


def _load_events_jsonl(path):
    """Load events from a *.events.jsonl file produced by smoke_loop.py."""
    events = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ev = _summarize_claude_event(raw)
                if ev is not None:
                    events.append(ev)
    except (IOError, OSError):
        return None
    return events


def _collect_smoke_traces(base_dir):
    """Find every *.events.jsonl under base_dir and return them as stage entries.

    Each entry has: {stage, path, events, event_count, mtime}. The stage label
    is derived from the parent directory + log basename (e.g. "round_1/repair",
    "judge", "task_gen") so the UI can show a clear stage list.
    """
    if not base_dir.is_dir():
        return []
    out = []
    for p in sorted(base_dir.rglob("*.events.jsonl")):
        try:
            rel = p.relative_to(base_dir).as_posix()
        except ValueError:
            rel = p.name
        stage = rel[:-len(".events.jsonl")] if rel.endswith(".events.jsonl") else rel
        # Strip trailing _cc from common log basenames (judge_cc, comparator_cc, repair_cc).
        stage = re.sub(r"_cc(\.log)?$", "", stage)
        if stage.endswith(".log"):
            stage = stage[:-4]
        # Collapse "<x>/<x>" → "<x>" (e.g. judge/judge → judge).
        parts = stage.split("/")
        if len(parts) >= 2 and parts[-1] == parts[-2]:
            parts.pop()
        stage = "/".join(parts)
        events = _load_events_jsonl(p) or []
        out.append({
            "stage": stage,
            "path": rel,
            "events": events,
            "event_count": len(events),
            "mtime": p.stat().st_mtime if p.exists() else None,
        })
    return out


@app.route("/api/synthesis/smoke/task/<app_name>/<task_id>/traces")
def api_synthesis_smoke_task_traces(app_name, task_id):
    """Return Claude Code traces (one per stage) for the latest run that
    touched this smoke task. Stages include judge, comparator, repair, etc.,
    sourced from *.events.jsonl files written by smoke_loop.py.
    """
    if not _safe_app_name(app_name):
        return jsonify({"error": "Invalid app"}), 400
    if "/" in task_id or ".." in task_id or not task_id:
        return jsonify({"error": "Invalid task_id"}), 400

    latest = None  # (ts, run_dir, sub_dir)
    for run_dir, ts in _scan_run_dirs_for_app(app_name):
        sub = run_dir / task_id
        if not sub.is_dir():
            continue
        if latest is None or (ts or "") > (latest[0] or ""):
            latest = (ts or "", run_dir, sub)

    if latest is None:
        return jsonify({
            "app": app_name, "task_id": task_id,
            "latest_run_id": None, "stages": [],
        })

    ts, run_dir, sub = latest
    stages = _collect_smoke_traces(sub)
    # Also include the per-run task_gen trace (shared across tasks in the run).
    task_gen_events = run_dir / "task_gen.log.events.jsonl"
    if task_gen_events.exists():
        events = _load_events_jsonl(task_gen_events) or []
        stages.insert(0, {
            "stage": "task_gen (run-wide)",
            "path": "../task_gen.log.events.jsonl",
            "events": events,
            "event_count": len(events),
            "mtime": task_gen_events.stat().st_mtime,
        })
    return jsonify({
        "app": app_name,
        "task_id": task_id,
        "latest_run_id": run_dir.name,
        "latest_ts": ts or None,
        "stages": stages,
    })


@app.route("/api/synthesis/smoke/runs/<run_id>")
def api_synthesis_smoke_run_detail(run_id):
    if "/" in run_id or ".." in run_id or not run_id:
        return jsonify({"error": "Invalid run_id"}), 400
    run_dir = (SMOKE_RUNS_DIR / run_id).resolve()
    try:
        run_dir.relative_to(SMOKE_RUNS_DIR.resolve())
    except ValueError:
        return jsonify({"error": "Invalid run_id"}), 400
    if not run_dir.is_dir():
        return jsonify({"error": "Not found"}), 404

    report = None
    if (run_dir / "REPORT.md").exists():
        report = (run_dir / "REPORT.md").read_text(errors="replace")
    log = None
    log_file = run_dir / "task_gen.log"
    if log_file.exists():
        try:
            log_text = log_file.read_text(errors="replace")
            log = log_text[-12000:]  # tail
        except (IOError, OSError):
            pass

    tasks = []
    for sub in sorted(run_dir.iterdir()):
        if not sub.is_dir() or sub.name == "__pycache__":
            continue
        solved_md = None
        if (sub / "SOLVED.md").exists():
            solved_md = (sub / "SOLVED.md").read_text(errors="replace")
        tasks.append({
            "id": sub.name,
            "has_solved": solved_md is not None,
            "solved_md": solved_md,
        })
    return jsonify({
        "run_id": run_id,
        "report": report,
        "log_tail": log,
        "tasks": tasks,
    })


@app.route("/api/synthesis/smoke/run", methods=["POST"])
def api_synthesis_smoke_run():
    body = request.json or {}
    app_name = (body.get("app") or "").strip()
    if not _safe_app_name(app_name):
        return jsonify({"error": "Invalid app"}), 400
    if not (SMOKE_DIR / "smoke_loop.py").exists():
        return jsonify({"error": "smoke/smoke_loop.py not found"}), 404

    extra = []
    if body.get("generate_only"):
        extra.append("--generate-only")
    if body.get("run_only"):
        extra.append("--run-only")
    max_tasks = body.get("max_tasks")
    if max_tasks:
        try:
            extra.extend(["--max-tasks", str(int(max_tasks))])
        except (ValueError, TypeError):
            pass
    max_rounds = body.get("max_rounds")
    if max_rounds:
        try:
            extra.extend(["--max-rounds", str(int(max_rounds))])
        except (ValueError, TypeError):
            pass

    key = f"smoke:{app_name}"
    if _synth_processes.get(key, {}).get("status") in ("starting", "running"):
        return jsonify({"status": "already_running", "key": key})
    cmd = [sys.executable, "-u", str(SMOKE_DIR / "smoke_loop.py"), "--app", app_name, *extra]
    _start_bg_process(key, cmd, str(PROJECT_ROOT), kind="smoke")
    return jsonify({"status": "started", "key": key})


@app.route("/api/synthesis/smoke/status/<app_name>")
def api_synthesis_smoke_status(app_name):
    if not _safe_app_name(app_name):
        return jsonify({"error": "Invalid app"}), 400
    return jsonify(_proc_status_payload(f"smoke:{app_name}"))


# ── Env files for tasks (Stage 4 task_generator) ─────────────────────────────

@app.route("/api/synthesis/env")
def api_synthesis_env_list():
    """List every task that has an env/ folder, with file counts."""
    out = []
    if not TASKS_DIR.exists():
        return jsonify(out)
    for task_dir, task in _iter_task_files():
        env_dir = task_dir / "env"
        if not env_dir.is_dir():
            continue
        files = [f for f in env_dir.iterdir() if f.is_file()]
        env_spec_files = task.get("env", {}).get("files") or []
        out.append({
            "task_id": task.get("id") or task_dir.name,
            "app": task.get("app"),
            "task_text": task.get("task"),
            "metadata": task.get("metadata") or {},
            "verification_count": len(task.get("verification") or []),
            "file_count": len(files),
            "total_size": sum(f.stat().st_size for f in files),
            "file_names": [f.name for f in sorted(files)[:6]],
            "sandbox_paths": [
                {
                    "filename": f.get("filename"),
                    "sandbox_path": f.get("sandbox_path"),
                }
                for f in env_spec_files[:6] if isinstance(f, dict)
            ],
            "has_manifest": (task_dir / "env_manifest.json").exists(),
        })
    return jsonify(out)


@app.route("/api/synthesis/env/<task_id>")
def api_synthesis_env_detail(task_id):
    if not _safe_app_name(task_id):
        return jsonify({"error": "Invalid task_id"}), 400
    task_dir = TASKS_DIR / task_id
    env_dir = task_dir / "env"
    manifest_file = task_dir / "env_manifest.json"
    files = []
    if env_dir.is_dir():
        for f in sorted(env_dir.iterdir()):
            if f.is_file():
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "ext": f.suffix.lower().lstrip("."),
                })
    manifest = None
    if manifest_file.exists():
        try:
            with open(manifest_file) as fh:
                manifest = json.load(fh)
        except (json.JSONDecodeError, IOError):
            manifest = {"_error": "could not parse env_manifest.json"}
    task = load_task_by_id(task_id) or {}
    return jsonify({
        "task_id": task_id,
        "task": task,  # full task.json
        "app": task.get("app"),
        "task_text": task.get("task"),
        "metadata": task.get("metadata") or {},
        "verification": task.get("verification") or [],
        "env_spec": task.get("env") or {},
        "exists": env_dir.is_dir(),
        "files": files,
        "manifest": manifest,
    })


_TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".xml", ".svg", ".html",
              ".yaml", ".yml", ".env", ".ini", ".toml", ".log", ".py"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


@app.route("/api/synthesis/env/<task_id>/file/<path:filename>")
def api_synthesis_env_file(task_id, filename):
    if not _safe_app_name(task_id) or not _safe_filename(filename):
        return jsonify({"error": "Invalid path"}), 400
    env_dir = TASKS_DIR / task_id / "env"
    fpath = (env_dir / filename).resolve()
    try:
        fpath.relative_to(env_dir.resolve())
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400
    if not fpath.is_file():
        return jsonify({"error": "Not found"}), 404
    ext = fpath.suffix.lower()
    if ext in _IMAGE_EXTS:
        return send_from_directory(env_dir, filename)
    if ext in _TEXT_EXTS or fpath.stat().st_size < 200_000:
        try:
            return Response(fpath.read_text(errors="replace"),
                            mimetype="text/plain; charset=utf-8")
        except (IOError, OSError, UnicodeDecodeError):
            pass
    # Binary fallback — let the browser decide
    return send_from_directory(env_dir, filename)


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task Manager Web Interface")
    parser.add_argument("--port", type=int, default=5111)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    print(f"Task Manager: http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=True)

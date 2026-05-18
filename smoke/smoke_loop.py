#!/usr/bin/env python3
"""
Verifier smoke-test pipeline.

Generates small, easy tasks covering all verifier endpoints for an app, then
runs each task through the full repair cycle:

  A. Run GUI agent in a live sandbox
  B. LLM judge produces ground-truth pass/fail from the trajectory
  C. Verifier script runs against the live sandbox
  D. Comparator classifies script↔judge disagreements
  E. Repair agent edits task.json / verifier to fix the script side
  Loop C→E up to --max-rounds times per task.

Run this AFTER verifier unit tests pass (test_<app>.py) and BEFORE generating
real training/benchmark tasks. It confirms verifier endpoints work correctly
with live agent trajectories and auto-fixes checker-side errors.

Usage:
    python smoke/smoke_loop.py --app audacity
    python smoke/smoke_loop.py --app audacity --generate-only
    python smoke/smoke_loop.py --app audacity --run-only
    python smoke/smoke_loop.py --app audacity --max-tasks 10 --max-rounds 3
    python smoke/smoke_loop.py --list-apps
"""

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

try:
    import dotenv
except ModuleNotFoundError:
    dotenv = None

if dotenv is not None:
    dotenv.load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────

SMOKE_DIR = Path(__file__).parent
PROJECT_ROOT = SMOKE_DIR.parent
TASK_GEN_DIR = PROJECT_ROOT / "task_generator"
VERIFIERS_DIR = PROJECT_ROOT / "verifiers"

PROMPTS_DIR = SMOKE_DIR / "prompts"
REPAIR_PROMPTS_DIR = PROJECT_ROOT / "evaluation" / "repair" / "prompts"
SMOKE_TASKS_DIR = SMOKE_DIR / "smoke_tasks"
RUNS_DIR = SMOKE_DIR / "runs"

sys.path.insert(0, str(PROJECT_ROOT))

from computer_env import (
    DEFAULT_DOCKER_CPUS,
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_DOCKER_MEMORY,
    DEFAULT_DOCKER_PLATFORM,
    DEFAULT_DOCKER_READY_TIMEOUT,
    DEFAULT_DOCKER_SHM_SIZE,
    DEFAULT_ENV_BACKEND,
    ensure_backend_support,
)

from evaluation.apps.registry import get_app_spec, list_app_ids
from evaluation.apps.save import auto_save_app
from evaluation.runtime.agent_runner import run_agent_on_task
from evaluation.runtime.sandbox_session import setup_sandbox, upload_verifier
from evaluation.runtime.verification import run_verifier

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_MODEL = os.getenv("SMOKE_MODEL", "kimi-k2.6")
DEFAULT_MAX_ITERATIONS = int(os.getenv("SMOKE_MAX_ITERATIONS", "100"))
DEFAULT_MAX_ROUNDS = int(os.getenv("SMOKE_MAX_ROUNDS", "3"))
DEFAULT_SANDBOX_TIMEOUT = int(os.getenv("SMOKE_SANDBOX_TIMEOUT", "3600"))
DEFAULT_MAX_TASKS = int(os.getenv("SMOKE_MAX_TASKS", "20"))

BACKENDS = {
    "claude": {
        "bin_env": "CLAUDE_BIN",
        "default_bin": "claude",
        # stream-json + verbose makes Claude Code emit one JSON event per line
        # (system init, assistant text/thinking/tool_use, user/tool_result,
        # final result) which we tee into a sibling .events.jsonl file so the
        # dashboard can render a structured trace per stage.
        "build_argv": lambda binary, prompt: [
            binary, "--print",
            "--output-format", "stream-json", "--verbose",
            "--dangerously-skip-permissions",
            prompt,
        ],
        "stream_json": True,
    },
    "codex": {
        "bin_env": "CODEX_BIN",
        "default_bin": "codex",
        "build_argv": lambda binary, prompt: [
            binary, "exec", "--dangerously-bypass-approvals-and-sandbox", prompt,
        ],
        "stream_json": False,
    },
}
DEFAULT_BACKEND = os.getenv("SMOKE_BACKEND", "claude")
_ACTIVE_BACKEND = DEFAULT_BACKEND


def _resolve_backend(name):
    if name not in BACKENDS:
        raise ValueError(f"Unknown backend: {name}. Choose from {list(BACKENDS)}")
    cfg = BACKENDS[name]
    binary = os.getenv(cfg["bin_env"], cfg["default_bin"])
    return name, binary, cfg["build_argv"], cfg.get("stream_json", False)


# ── Prompt / headless-Claude helpers ─────────────────────────────────────────


def render_prompt(prompts_dir, template_name, substitutions):
    template = (prompts_dir / template_name).read_text()
    for key, value in substitutions.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def _summarize_claude_event_line(raw):
    """Return a short human-readable string for a parsed stream-json event.

    Used for live progress lines on the wrapper's stdout — the dashboard's
    smoke log panel surfaces these so the user can see what Claude is doing
    without opening the per-stage trace.
    """
    if not isinstance(raw, dict):
        return None
    t = raw.get("type")
    if t == "system" and raw.get("subtype") == "init":
        return f"init model={raw.get('model')}"
    if t == "assistant":
        msg = raw.get("message") or {}
        bits = []
        for block in (msg.get("content") or []):
            bt = block.get("type")
            if bt == "text":
                snippet = (block.get("text") or "").strip().splitlines()
                if snippet:
                    bits.append(f"text: {snippet[0][:120]}")
            elif bt == "tool_use":
                inp = block.get("input") or {}
                arg = (
                    inp.get("file_path") or inp.get("command")
                    or inp.get("pattern") or inp.get("url") or ""
                )
                arg = str(arg)[:160]
                name = block.get("name", "?")
                bits.append(f"tool {name}{(' ' + arg) if arg else ''}")
        return " | ".join(bits) or None
    if t == "user":
        msg = raw.get("message") or {}
        for block in (msg.get("content") or []):
            if block.get("type") == "tool_result":
                err = " ERR" if block.get("is_error") else ""
                return f"result{err}"
        return None
    if t == "result":
        kind = "error" if raw.get("is_error") else "done"
        dur = raw.get("duration_ms")
        dur_s = f"{dur / 1000:.1f}s" if isinstance(dur, (int, float)) else ""
        return f"{kind}{(' ' + dur_s) if dur_s else ''}"
    return None


def _final_result_from_events(raw_events):
    for raw in reversed(raw_events):
        if isinstance(raw, dict) and raw.get("type") == "result":
            return raw.get("result") or ""
    return ""


def call_claude_code(prompt_text, working_dir, timeout, log_path):
    """Invoke the active headless reasoning backend.

    For the claude backend we use ``--output-format stream-json --verbose`` and
    stream stdout line-by-line: each event line is parsed, persisted as JSONL
    in ``<log_path>.events.jsonl`` (so the dashboard can render a structured
    trace), and a one-line summary is printed to the wrapper's stdout for live
    progress visibility.
    """
    backend_name, binary, build_argv, stream_json = _resolve_backend(_ACTIVE_BACKEND)
    cmd = build_argv(binary, prompt_text)
    label = log_path.stem if log_path else "cc"
    print(f"    [{label}] headless {backend_name}")
    start = time.time()

    raw_stdout_chunks = []
    raw_events = []
    stderr_text = ""
    rc = 1
    timed_out = False

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    events_path = (log_path.with_suffix(log_path.suffix + ".events.jsonl")
                   if (log_path is not None and stream_json) else None)
    events_fp = open(events_path, "w") if events_path is not None else None

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(working_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        deadline = start + timeout if timeout else None
        try:
            for line in proc.stdout:
                raw_stdout_chunks.append(line)
                if stream_json:
                    s = line.strip()
                    if s.startswith("{"):
                        try:
                            ev = json.loads(s)
                        except json.JSONDecodeError:
                            ev = None
                        if ev is not None:
                            raw_events.append(ev)
                            if events_fp is not None:
                                events_fp.write(s + "\n")
                                events_fp.flush()
                            summary = _summarize_claude_event_line(ev)
                            if summary:
                                print(f"      [{label}:{ev.get('type','?')}] {summary}",
                                      flush=True)
                if deadline is not None and time.time() > deadline:
                    proc.kill()
                    timed_out = True
                    break
            rc = proc.wait(timeout=10 if timed_out else None)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = 124
            timed_out = True

        try:
            stderr_text = proc.stderr.read() or ""
        except Exception:  # noqa: BLE001
            stderr_text = ""
    finally:
        if events_fp is not None:
            events_fp.close()

    stdout_raw = "".join(raw_stdout_chunks)
    if timed_out:
        rc = 124
        stderr_text = (stderr_text or "") + f"\n[TIMEOUT after {timeout}s]"

    elapsed = time.time() - start
    print(f"    [{label}] rc={rc} in {elapsed:.1f}s"
          + (f" ({len(raw_events)} events)" if stream_json else ""))

    # For stream-json claude runs, "stdout" returned to callers is the final
    # assistant result text (matching the old --print behavior), not the raw
    # JSONL. The full JSONL is written to events_path and stdout_raw is also
    # inlined below for debugging.
    final_text = (
        _final_result_from_events(raw_events) if stream_json else stdout_raw
    )

    if log_path is not None:
        log_path.write_text(
            f"# returncode: {rc}\n# elapsed: {elapsed:.1f}s\n"
            f"# cwd: {working_dir}\n"
            f"# backend: {backend_name}\n"
            + (f"# events: {len(raw_events)} (see {events_path.name})\n"
               if events_path is not None else "")
            + f"\n## PROMPT\n{prompt_text}\n\n"
            f"## FINAL\n{final_text}\n\n"
            f"## STDOUT_RAW\n{stdout_raw}\n\n"
            f"## STDERR\n{stderr_text}\n"
        )
    return final_text, stderr_text, rc


# ── Verifier helpers ──────────────────────────────────────────────────────────


def run_verifier_batch(sandbox, app_name, checks):
    """Run every verification check against the live sandbox."""
    results = []
    for i, check in enumerate(checks):
        cmd = check.get("command")
        description = check.get("description", cmd or f"check {i}")

        if check.get("judge") == "llm":
            data = run_verifier(sandbox, app_name, cmd) if cmd else None
            results.append({
                "index": i,
                "description": description,
                "mode": "llm_judge",
                "command": cmd,
                "prompt": check.get("prompt"),
                "raw_output": data,
                "passed": None,
            })
            continue

        data = run_verifier(sandbox, app_name, cmd)
        entry = {
            "index": i,
            "description": description,
            "command": cmd,
            "raw_output": data,
        }
        if "eval" in check:
            entry["mode"] = "eval"
            entry["eval_expr"] = check["eval"]
            try:
                result = data  # noqa: F841 -- referenced by eval expression
                entry["passed"] = bool(eval(check["eval"]))  # noqa: S307
            except Exception as e:
                entry["passed"] = False
                entry["error"] = f"eval failed: {e}"
        else:
            key = check.get("key")
            expected = check.get("expected")
            actual = data.get(key) if isinstance(data, dict) else None
            entry["mode"] = "key"
            entry["key"] = key
            entry["expected"] = expected
            entry["actual"] = actual
            entry["passed"] = actual == expected
        results.append(entry)
    return results


def summarize_script_results(script_results):
    passed = sum(1 for r in script_results if r.get("passed") is True)
    failed = sum(1 for r in script_results if r.get("passed") is False)
    skipped = sum(1 for r in script_results if r.get("passed") is None)
    return {"passed": passed, "failed": failed, "skipped_llm_judge": skipped,
            "total": len(script_results)}


def compute_divergences(script_results, llm_judge_result):
    judge_by_index = {
        e.get("index"): e
        for e in llm_judge_result.get("checks", [])
        if e.get("index") is not None
    }
    diffs = []
    for r in script_results:
        if r.get("passed") is None:
            continue
        i = r["index"]
        judge = judge_by_index.get(i)
        if judge is None:
            diffs.append({
                "index": i,
                "description": r.get("description"),
                "script_passed": r.get("passed"),
                "judge_passed": None,
                "judge_reason": "no_judge_entry_for_this_index",
            })
            continue
        if bool(r.get("passed")) != bool(judge.get("passed")):
            diffs.append({
                "index": i,
                "description": r.get("description"),
                "script_passed": r.get("passed"),
                "judge_passed": judge.get("passed"),
                "judge_reason": judge.get("reasoning", ""),
            })
    return diffs


# ── Repair pipeline stages ────────────────────────────────────────────────────


def stage_judge(task_id, app_name, task_dict, traj_dir, judge_dir):
    """Stage B — LLM-as-judge. Produces judge_dir/llm_judge.json."""
    out_path = judge_dir / "llm_judge.json"
    criteria = [
        {
            "index": i,
            "description": c.get("description", ""),
            "llm_judged": c.get("judge") == "llm",
            "prompt": c.get("prompt"),
        }
        for i, c in enumerate(task_dict["verification"])
    ]
    llm_judge_guide = PROJECT_ROOT / "evaluation" / "llm_judge.md"
    prompt = render_prompt(REPAIR_PROMPTS_DIR, "judge.md", {
        "TASK_ID": task_id,
        "APP_NAME": app_name,
        "TASK_DESCRIPTION": task_dict["task"],
        "TRAJECTORY_DIR": str(traj_dir),
        "CRITERIA_JSON": json.dumps(criteria, indent=2),
        "OUTPUT_PATH": str(out_path),
        "LLM_JUDGE_GUIDE": str(llm_judge_guide),
    })
    stdout, stderr, rc = call_claude_code(
        prompt, PROJECT_ROOT,
        timeout=1800, log_path=judge_dir / "judge_cc.log",
    )
    if not out_path.exists():
        raise RuntimeError(
            f"Judge stage did not produce {out_path} (rc={rc}).\n"
            f"stderr tail: {stderr[-800:]}"
        )
    return json.loads(out_path.read_text())


def stage_comparator(task_id, app_name, task_path, script_result_path,
                     llm_judge_path, traj_dir, round_dir):
    """Stage D — classify disagreements. Produces round_dir/disagreements.json."""
    out_path = round_dir / "disagreements.json"
    prompt = render_prompt(REPAIR_PROMPTS_DIR, "comparator.md", {
        "TASK_ID": task_id,
        "APP_NAME": app_name,
        "TASK_PATH": str(task_path),
        "SCRIPT_RESULT_PATH": str(script_result_path),
        "LLM_JUDGE_PATH": str(llm_judge_path),
        "TRAJECTORY_DIR": str(traj_dir),
        "VERIFIER_PATH": str(VERIFIERS_DIR / app_name / f"{app_name}.py"),
        "VERIFIER_README": str(VERIFIERS_DIR / app_name / "README.md"),
        "OUTPUT_PATH": str(out_path),
    })
    stdout, stderr, rc = call_claude_code(
        prompt, PROJECT_ROOT,
        timeout=1200, log_path=round_dir / "comparator_cc.log",
    )
    if not out_path.exists():
        raise RuntimeError(
            f"Comparator stage did not produce {out_path} (rc={rc}).\n"
            f"stderr tail: {stderr[-800:]}"
        )
    return json.loads(out_path.read_text())


def stage_repair(task_id, app_name, task_path, disagreements_path, round_dir,
                 round_num):
    """Stage E — edit verifier / task.json to fix divergences."""
    log_path = round_dir / "repair_log.md"
    prompt = render_prompt(REPAIR_PROMPTS_DIR, "repair.md", {
        "TASK_ID": task_id,
        "APP_NAME": app_name,
        "ROUND_NUM": round_num,
        "TASK_PATH": str(task_path),
        "TASK_DIR": str(task_path.parent),
        "VERIFIER_PATH": str(VERIFIERS_DIR / app_name / f"{app_name}.py"),
        "VERIFIER_README": str(VERIFIERS_DIR / app_name / "README.md"),
        "DISAGREEMENTS_PATH": str(disagreements_path),
        "REPAIR_LOG_PATH": str(log_path),
        "LESSONS_PATH": str(TASK_GEN_DIR / "LESSONS.md"),
    })
    stdout, stderr, rc = call_claude_code(
        prompt, PROJECT_ROOT,
        timeout=1800, log_path=round_dir / "repair_cc.log",
    )
    if log_path.exists():
        return log_path.read_text()
    return f"(no repair_log.md produced; stdout tail)\n\n{stdout[-2000:]}"


# ── SOLVED.md per task ────────────────────────────────────────────────────────


def write_solved_md(task_run_dir, task_id, app_name, task_path, agent_info,
                    initial_criteria_count, rounds_info, final_diffs,
                    llm_judge_result):
    lines = [
        f"# Smoke Repair Report — `{task_id}`",
        "",
        f"- **App:** `{app_name}`",
        f"- **Task file:** `{task_path}`",
        f"- **Agent:** `{agent_info['model']}` — "
        f"{'done' if agent_info['agent_done'] else 'not done'} "
        f"in {agent_info['steps']} steps",
        f"- **Initial criteria count:** {initial_criteria_count}",
        f"- **Rounds run:** {len(rounds_info)}",
    ]
    stopped_judge_wrong = bool(rounds_info) and rounds_info[-1].get("all_judge_wrong")
    if not final_diffs and stopped_judge_wrong:
        lines.append("- **Final state:** ✅ verifier trusted — "
                     "all remaining divergences classified `judge_wrong`")
    elif not final_diffs:
        lines.append("- **Final state:** ✅ verifier agrees with LLM judge")
    else:
        lines.append(f"- **Final state:** ⚠️ {len(final_diffs)} criteria still divergent")
    lines.append("")

    lines.append("## LLM judge (ground truth)")
    for c in llm_judge_result.get("checks", []):
        mark = "✅" if c.get("passed") else "❌"
        lines.append(f"- {mark} #{c.get('index')} — {c.get('description', '')}")
        if c.get("reasoning"):
            lines.append(f"  - reasoning: {c['reasoning'][:300]}")
    if llm_judge_result.get("summary"):
        lines += ["", f"> {llm_judge_result['summary']}"]
    lines.append("")

    lines.append("## Round-by-round")
    for info in rounds_info:
        lines += ["", f"### Round {info['round']}"]
        s = info["script_summary"]
        lines.append(
            f"- Script: **{s['passed']}** pass / **{s['failed']}** fail / "
            f"**{s['skipped_llm_judge']}** llm-judged — total {s['total']}"
        )
        lines.append(f"- Divergences vs judge: **{len(info['diffs'])}**")
        for d in info["diffs"]:
            lines.append(
                f"  - #{d['index']} — {d.get('description', '')}: "
                f"script=`{d.get('script_passed')}` judge=`{d.get('judge_passed')}`"
            )
            if d.get("judge_reason"):
                lines.append(f"    - judge: {d['judge_reason'][:220]}")
        if info.get("disagreement_items"):
            lines += ["", "  **Comparator classifications:**"]
            for item in info["disagreement_items"]:
                lines.append(
                    f"  - #{item.get('index')} → `{item.get('classification')}` "
                    f"(fix scope: `{item.get('fix_scope')}`)"
                )
                if item.get("suggested_fix"):
                    lines.append(f"    - fix: {item['suggested_fix'][:300]}")
        if info.get("repair_summary"):
            lines += [
                "", "<details><summary>Repair log</summary>", "",
                info["repair_summary"], "", "</details>",
            ]

    lines += ["", "## Final state"]
    if not final_diffs and stopped_judge_wrong:
        lines.append(
            "All remaining divergences classified as `judge_wrong`. "
            "Verifier script treated as correct. ✅"
        )
    elif not final_diffs:
        lines.append("All criteria reconciled between verifier script and LLM judge. ✅")
    else:
        lines.append("Unresolved divergences after max rounds:")
        for d in final_diffs:
            lines.append(
                f"- #{d['index']} — {d.get('description', '')}: "
                f"script=`{d.get('script_passed')}` judge=`{d.get('judge_passed')}`"
            )

    (task_run_dir / "SOLVED.md").write_text("\n".join(lines))


# ── Smoke task I/O ────────────────────────────────────────────────────────────


def load_smoke_tasks(app_name):
    """Return list of (task_dict, task_path) for all generated smoke tasks."""
    app_dir = SMOKE_TASKS_DIR / app_name
    tasks = []
    if not app_dir.exists():
        return tasks
    for task_dir in sorted(app_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        task_path = task_dir / "task.json"
        if task_path.exists():
            with open(task_path) as f:
                tasks.append((json.load(f), task_path))
    return tasks


def upload_smoke_env_files(sandbox, task: dict, task_path: Path) -> None:
    """Upload env files from the smoke task's own env/ directory.

    If env/create_env.py exists and any declared file is missing locally, the
    create script is uploaded and executed inside the sandbox to materialise
    the file (mirrors evaluation/runtime/sandbox_session.upload_task_env_files
    so apps whose native format is sandbox-version-specific — e.g. Blender —
    can ship a generator instead of pre-built binaries).
    """
    files = task.get("env", {}).get("files", [])
    if not files:
        return
    env_dir = task_path.parent / "env"
    if not env_dir.exists():
        return

    for entry in files:
        local_path = env_dir / entry["filename"]
        remote_path = entry["sandbox_path"]
        sandbox.commands.run(f"mkdir -p {Path(remote_path).parent}", timeout=5)
        if local_path.exists():
            with open(local_path, "rb") as fh:
                sandbox.files.write(remote_path, fh.read())

    create_env_script = env_dir / "create_env.py"
    if create_env_script.exists():
        missing = any(not (env_dir / e["filename"]).exists() for e in files)
        if missing:
            with open(create_env_script) as handle:
                sandbox.files.write("/tmp/create_env.py", handle.read())
            try:
                sandbox.commands.run("python3 /tmp/create_env.py", timeout=180)
            except Exception:
                pass


# ── Phase 1: task generation ──────────────────────────────────────────────────


def phase_generate(app_name, max_tasks, run_dir):
    """Call headless Claude to read the verifier and generate minimal smoke tasks."""
    app_smoke_dir = SMOKE_TASKS_DIR / app_name
    app_smoke_dir.mkdir(parents=True, exist_ok=True)

    verifier_py = VERIFIERS_DIR / app_name / f"{app_name}.py"
    verifier_readme = VERIFIERS_DIR / app_name / "README.md"
    if not verifier_py.exists():
        raise FileNotFoundError(f"Verifier not found: {verifier_py}")

    prompt = render_prompt(PROMPTS_DIR, "smoke_task_gen.md", {
        "APP_NAME": app_name,
        "VERIFIER_PY": str(verifier_py),
        "VERIFIER_README": str(verifier_readme),
        "SMOKE_TASKS_DIR": str(app_smoke_dir),
        "SMOKE_CLAUDE_MD": str(SMOKE_DIR / "CLAUDE.md"),
        "MAX_TASKS": str(max_tasks),
        "PROJECT_ROOT": str(PROJECT_ROOT),
    })

    print(f"  Phase 1: generating smoke tasks for {app_name} (max {max_tasks})...")
    call_claude_code(
        prompt, PROJECT_ROOT,
        timeout=1800, log_path=run_dir / "task_gen.log",
    )

    tasks = load_smoke_tasks(app_name)
    print(f"  Generated {len(tasks)} smoke task(s)")
    return tasks


# ── Phase 2: run tasks ────────────────────────────────────────────────────────


def run_one_task(
    app_name,
    task_dict,
    task_path,
    model_name,
    max_iterations,
    max_rounds,
    sandbox_timeout,
    task_run_dir,
    env_backend,
    docker_image,
    docker_platform,
    docker_shm_size,
    docker_memory,
    docker_cpus,
    docker_ready_timeout,
):
    """
    Full repair cycle for one smoke task:
      A. Setup sandbox + run agent
      B. LLM judge (once)
      C-E. Verify → compare → repair (up to max_rounds)
      Write SOLVED.md.
    """
    traj_dir = task_run_dir / "trajectory"
    traj_dir.mkdir(parents=True, exist_ok=True)

    task_id = task_dict["id"]
    initial_criteria_count = len(task_dict["verification"])
    agent_info = {"model": model_name, "agent_done": False, "steps": 0}

    sandbox = None
    try:
        # ── Stage A: sandbox + agent ──────────────────────────────────────────
        task_for_setup = copy.deepcopy(task_dict)
        task_for_setup["env"] = {}  # env files live in smoke_tasks/, not task_generator/

        sandbox, stream_url = setup_sandbox(
            app_name, task_for_setup, sandbox_timeout,
            env_backend=env_backend,
            docker_image=docker_image,
            docker_platform=docker_platform,
            docker_shm_size=docker_shm_size,
            docker_memory=docker_memory,
            docker_cpus=docker_cpus,
            docker_ready_timeout=docker_ready_timeout,
        )
        print(f"    Desktop: {stream_url}")

        upload_smoke_env_files(sandbox, task_dict, task_path)

        agent_done, steps, trajectory = run_agent_on_task(
            sandbox, task_dict["task"], model_name, max_iterations, traj_dir,
        )
        agent_info.update({"agent_done": agent_done, "steps": steps})
        print(f"    Agent done={agent_done} in {steps} steps")

        app_spec = get_app_spec(app_name)
        if app_spec.save_shortcut:
            try:
                save_result = auto_save_app(
                    sandbox, app_name, app_spec.save_shortcut,
                    save_window_name=app_spec.save_window_name,
                )
                if not save_result["ok"]:
                    print(f"    Auto-save warning: {save_result['message']}")
            except Exception as e:
                print(f"    Auto-save failed: {e}")

        with open(traj_dir / "trajectory.json", "w") as f:
            json.dump({
                "task_id": task_id, "app": app_name, "model": model_name,
                "task": task_dict["task"], "agent_done": agent_done,
                "agent_steps": steps, "trajectory": trajectory,
            }, f, indent=2, default=str)

        try:
            (traj_dir / "screenshots").mkdir(exist_ok=True)
            with open(traj_dir / "screenshots" / "final_after_agent.png", "wb") as f:
                f.write(sandbox.screenshot())
        except Exception:
            pass

        # ── Stage B: LLM judge (once) ─────────────────────────────────────────
        judge_dir = task_run_dir / "judge"
        judge_dir.mkdir(exist_ok=True)
        print(f"    Stage B: LLM judge...")
        llm_judge_result = stage_judge(task_id, app_name, task_dict, traj_dir, judge_dir)
        llm_judge_path = judge_dir / "llm_judge.json"
        judge_pass = sum(1 for c in llm_judge_result.get("checks", []) if c.get("passed"))
        judge_total = len(llm_judge_result.get("checks", []))
        print(f"    Judge: {judge_pass}/{judge_total} criteria passed")

        # ── Rounds: C (verify) → D (compare) → E (repair) ────────────────────
        rounds_info = []
        final_diffs = []

        for round_num in range(max_rounds):
            round_dir = task_run_dir / f"round_{round_num}"
            round_dir.mkdir(parents=True, exist_ok=True)

            # Re-read task from disk — prior repair round may have edited it
            with open(task_path) as f:
                task_dict = json.load(f)

            print(f"\n    ── Round {round_num} ──")

            # Stage C: run verifier
            script_results = run_verifier_batch(sandbox, app_name, task_dict["verification"])
            script_result_path = round_dir / "script_result.json"
            with open(script_result_path, "w") as f:
                json.dump(script_results, f, indent=2, default=str)
            summary = summarize_script_results(script_results)
            print(f"      Script: {summary['passed']}P / {summary['failed']}F / "
                  f"{summary['skipped_llm_judge']}L (total {summary['total']})")

            diffs = compute_divergences(script_results, llm_judge_result)
            print(f"      Divergences vs judge: {len(diffs)}")

            round_record = {
                "round": round_num,
                "script_summary": summary,
                "diffs": diffs,
                "disagreement_items": [],
                "repair_summary": "",
            }

            if not diffs:
                rounds_info.append(round_record)
                final_diffs = []
                print("      ✅ verifier agrees with judge — stopping")
                break

            # Stage D: comparator
            shutil.copy(llm_judge_path, round_dir / "llm_judge.json")
            print(f"      Stage D: comparator...")
            disagreements = stage_comparator(
                task_id, app_name, task_path, script_result_path,
                round_dir / "llm_judge.json", traj_dir, round_dir,
            )
            round_record["disagreement_items"] = disagreements.get("items", [])
            print(f"      Comparator: {len(round_record['disagreement_items'])} item(s)")

            items = round_record["disagreement_items"]
            if items and all(it.get("classification") == "judge_wrong" for it in items):
                round_record["all_judge_wrong"] = True
                rounds_info.append(round_record)
                final_diffs = []
                print("      ✅ all divergences classified judge_wrong — verifier trusted")
                break

            # Stage E: repair
            print(f"      Stage E: repair...")
            repair_summary = stage_repair(
                task_id, app_name, task_path,
                round_dir / "disagreements.json", round_dir, round_num,
            )
            round_record["repair_summary"] = repair_summary

            # Re-upload verifier (repair may have edited it)
            try:
                upload_verifier(sandbox, app_name)
            except Exception as e:
                print(f"      Re-upload verifier warning: {e}")

            rounds_info.append(round_record)
            final_diffs = diffs

        # If we exhausted rounds without breaking, record the last diffs
        if rounds_info and "all_judge_wrong" not in rounds_info[-1] and final_diffs:
            pass  # final_diffs already set above

        write_solved_md(
            task_run_dir, task_id, app_name, task_path, agent_info,
            initial_criteria_count, rounds_info, final_diffs, llm_judge_result,
        )

    except Exception:
        err = traceback.format_exc()
        print(f"    Error: {err.splitlines()[-1]}")
        (task_run_dir / "error.txt").write_text(err)
    finally:
        if sandbox is not None:
            try:
                sandbox.kill()
            except Exception:
                pass


def phase_run(
    app_name,
    tasks,
    model_name,
    max_iterations,
    max_rounds,
    sandbox_timeout,
    run_dir,
    env_backend=DEFAULT_ENV_BACKEND,
    docker_image=DEFAULT_DOCKER_IMAGE,
    docker_platform=DEFAULT_DOCKER_PLATFORM,
    docker_shm_size=DEFAULT_DOCKER_SHM_SIZE,
    docker_memory=DEFAULT_DOCKER_MEMORY,
    docker_cpus=DEFAULT_DOCKER_CPUS,
    docker_ready_timeout=DEFAULT_DOCKER_READY_TIMEOUT,
):
    for task_dict, task_path in tasks:
        task_id = task_dict["id"]
        task_run_dir = run_dir / task_id
        # Skip tasks that already have a SOLVED.md (completed in a prior run).
        # Errored tasks (error.txt without SOLVED.md) are NOT skipped — retry them.
        if (task_run_dir / "SOLVED.md").exists():
            print(f"\n  ── Task: {task_id} ── (skipped, already completed)")
            continue
        task_run_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n  ── Task: {task_id} ──")
        run_one_task(
            app_name=app_name,
            task_dict=task_dict,
            task_path=task_path,
            model_name=model_name,
            max_iterations=max_iterations,
            max_rounds=max_rounds,
            sandbox_timeout=sandbox_timeout,
            task_run_dir=task_run_dir,
            env_backend=env_backend,
            docker_image=docker_image,
            docker_platform=docker_platform,
            docker_shm_size=docker_shm_size,
            docker_memory=docker_memory,
            docker_cpus=docker_cpus,
            docker_ready_timeout=docker_ready_timeout,
        )


# ── REPORT.md (aggregates all tasks) ─────────────────────────────────────────


def write_report(run_dir, app_name, tasks):
    lines = [f"# Smoke Test Report — `{app_name}`", ""]
    total = len(tasks)
    fully_resolved = 0
    for task_dict, _ in tasks:
        task_id = task_dict["id"]
        solved = run_dir / task_id / "SOLVED.md"
        if solved.exists() and "✅" in solved.read_text().split("**Final state:**")[-1][:60]:
            fully_resolved += 1

    lines += [
        f"- **Tasks run:** {total}",
        f"- **Fully resolved:** {fully_resolved}/{total}",
        "",
        "## Per-task summaries",
        "",
    ]

    for task_dict, _ in tasks:
        task_id = task_dict["id"]
        task_run_dir = run_dir / task_id
        solved_path = task_run_dir / "SOLVED.md"
        error_path = task_run_dir / "error.txt"

        if error_path.exists():
            lines.append(f"### ❌ `{task_id}` — runtime error")
            lines.append("")
            lines.append("```")
            lines.append(error_path.read_text()[-600:])
            lines.append("```")
        elif solved_path.exists():
            # Inline the task's SOLVED.md under a sub-heading
            solved_text = solved_path.read_text()
            # Demote headings by one level (# → ##, ## → ###, etc.) for nesting
            demoted = "\n".join(
                ("#" + line) if line.startswith("#") else line
                for line in solved_text.splitlines()
            )
            lines.append(demoted)
        else:
            lines.append(f"### ⚠️ `{task_id}` — no output (task may still be running)")
        lines.append("")

    report_path = run_dir / "REPORT.md"
    report_path.write_text("\n".join(lines))
    return report_path


# ── CLI ───────────────────────────────────────────────────────────────────────


def main():
    global _ACTIVE_BACKEND

    parser = argparse.ArgumentParser(
        description="Verifier smoke-test pipeline: generate tasks + full repair cycle."
    )
    parser.add_argument("--app", help="App name (e.g. audacity, gimp, chrome)")
    parser.add_argument("--generate-only", action="store_true",
                        help="Only generate smoke tasks; skip running them")
    parser.add_argument("--run-only", action="store_true",
                        help="Skip generation; run already-generated tasks")
    parser.add_argument("--max-tasks", type=int, default=DEFAULT_MAX_TASKS,
                        help=f"Max tasks to generate (default {DEFAULT_MAX_TASKS})")
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS,
                        help=f"Max repair rounds per task (default {DEFAULT_MAX_ROUNDS})")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"GUI agent model (default {DEFAULT_MODEL})")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS,
                        help=f"Max agent steps per task (default {DEFAULT_MAX_ITERATIONS})")
    parser.add_argument("--sandbox-timeout", type=int, default=DEFAULT_SANDBOX_TIMEOUT,
                        help=f"Sandbox lifetime seconds (default {DEFAULT_SANDBOX_TIMEOUT})")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, choices=list(BACKENDS),
                        help="Headless reasoning backend (default claude)")
    parser.add_argument("--backend-env", default=DEFAULT_ENV_BACKEND,
                        help="Sandbox backend: e2b or docker")
    parser.add_argument("--list-apps", action="store_true",
                        help="Print all supported apps and exit")
    parser.add_argument(
        "--resume", nargs="?", const="latest", default=None, metavar="RUN_DIR",
        help="Resume an existing run, skipping tasks that already have SOLVED.md. "
             "Pass a run dir (smoke/runs/<app>_<ts>/) or use bare --resume to "
             "auto-pick the latest run dir for this app. Implies --run-only.",
    )

    parser.add_argument("--docker-image", default=DEFAULT_DOCKER_IMAGE)
    parser.add_argument("--docker-platform", default=DEFAULT_DOCKER_PLATFORM)
    parser.add_argument("--docker-shm-size", default=DEFAULT_DOCKER_SHM_SIZE)
    parser.add_argument("--docker-memory", default=DEFAULT_DOCKER_MEMORY)
    parser.add_argument("--docker-cpus", default=DEFAULT_DOCKER_CPUS)
    parser.add_argument("--docker-ready-timeout", type=int,
                        default=DEFAULT_DOCKER_READY_TIMEOUT)

    args = parser.parse_args()

    if args.list_apps:
        for app_id in list_app_ids():
            print(app_id)
        return

    if not args.app:
        parser.error("--app is required (or use --list-apps)")

    _ACTIVE_BACKEND = args.backend
    app_name = args.app
    ensure_backend_support(args.backend_env, app_name)

    if args.resume:
        # --resume implies --run-only: skip task generation
        args.run_only = True
        if args.resume == "latest":
            candidates = sorted(
                p for p in RUNS_DIR.glob(f"{app_name}_*") if p.is_dir()
            )
            if not candidates:
                parser.error(f"No existing run dir for {app_name} under {RUNS_DIR}")
            run_dir = candidates[-1]
            print(f"  Resuming latest run: {run_dir}")
        else:
            run_dir = Path(args.resume).resolve()
            if not run_dir.exists():
                parser.error(f"Resume run dir does not exist: {run_dir}")
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = RUNS_DIR / f"{app_name}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*72}")
    print(f"  Smoke test: {app_name}")
    print(f"  Model:      {args.model}")
    print(f"  Max rounds: {args.max_rounds}")
    print(f"  Backend:    {args.backend}")
    print(f"  Env:        {args.backend_env}")
    print(f"  Run dir:    {run_dir}")
    print(f"{'='*72}")

    if not args.run_only:
        tasks = phase_generate(app_name, args.max_tasks, run_dir)
    else:
        tasks = load_smoke_tasks(app_name)
        print(f"  Loaded {len(tasks)} existing smoke task(s) for {app_name}")

    if not tasks:
        print("  No tasks available. Exiting.")
        return

    if args.generate_only:
        print(f"  {len(tasks)} task(s) generated under {SMOKE_TASKS_DIR / app_name}")
        print("  Stopping (--generate-only).")
        return

    phase_run(
        app_name=app_name,
        tasks=tasks,
        model_name=args.model,
        max_iterations=args.max_iterations,
        max_rounds=args.max_rounds,
        sandbox_timeout=args.sandbox_timeout,
        run_dir=run_dir,
        env_backend=args.backend_env,
        docker_image=args.docker_image,
        docker_platform=args.docker_platform,
        docker_shm_size=args.docker_shm_size,
        docker_memory=args.docker_memory,
        docker_cpus=args.docker_cpus,
        docker_ready_timeout=args.docker_ready_timeout,
    )

    report_path = write_report(run_dir, app_name, tasks)
    print(f"\n{'='*72}")
    print(f"  Complete. Report: {report_path}")
    print(f"{'='*72}")


if __name__ == "__main__":
    main()

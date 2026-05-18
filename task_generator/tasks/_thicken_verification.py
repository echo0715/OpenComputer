"""Thicken verification checks on every existing task.json.

For each task:
  1. Extract all absolute paths the verification commands reference.
  2. For every task-produced path (i.e. an output file — detected by
     presence of an `exists`-expected-True or `valid`-expected-True check),
     add a defensive `check-file-exists` and `check-file-nonempty` if
     missing.
  3. For preference-class tasks, add a workspace/config existence check.
  4. De-duplicate the verification list by (command, key) pairs.

Idempotent: running twice is a no-op. Safe to re-run any time.

Usage:
    python task_generator/tasks/_thicken_verification.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TASKS_DIR = Path(__file__).parent


def _unique(entries: list[dict]) -> list[dict]:
    """Drop duplicates preserving order, key on (command, key, expected)."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for e in entries:
        k = (e.get("command"), e.get("key"), json.dumps(e.get("expected"), sort_keys=True))
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


_PATH_RE = re.compile(r"(/[A-Za-z0-9_./-]+)")


def _collect_paths(verification: list[dict]) -> set[str]:
    """Paths that appear as arguments across all verification commands."""
    paths = set()
    for v in verification:
        for m in _PATH_RE.findall(v.get("command", "")):
            # Skip obvious non-file fragments (e.g., /ip.addr, /home/user
            # without extension or trailing slash)
            if "." in m.rsplit("/", 1)[-1] or m.endswith(".db"):
                paths.add(m)
    return paths


def _already_has(verification: list[dict], cmd_prefix: str, path: str) -> bool:
    needle = f"{cmd_prefix} {path}"
    return any(v.get("command", "").startswith(needle) for v in verification)


# Which check verbs the verifier exposes per app
_APP_FILE_VERBS = {
    "qgis": {
        "file_exists": "check-file-exists",
        "file_nonempty": "check-file-nonempty",
    },
    "wireshark": {
        "file_exists": "check-file-exists",
        "file_nonempty": "check-file-nonempty",
    },
    "dbeaver": {
        "file_exists": "check-file-exists",
        "file_nonempty": "check-file-nonempty",
    },
    "opentoonz": {
        "file_exists": "check-file-exists",
        "file_nonempty": "check-file-nonempty",
    },
    "openlca": {
        "file_exists": "check-file-exists",
        "file_nonempty": "check-file-nonempty",
    },
}


# Per-app config/workspace fixture paths to attest when a task only changes
# preferences
_APP_WORKSPACE_PATHS = {
    "qgis": "/home/user/.config/QGIS/QGIS3.ini",
    "wireshark": "/home/user/.config/wireshark/preferences",
    "dbeaver": "/home/user/.local/share/DBeaverData/workspace6/.metadata/.plugins/org.eclipse.core.runtime/.settings/org.jkiss.dbeaver.core.prefs",
    "opentoonz": None,   # Flatpak path varies; skip
    "openlca": "/home/user/openLCA-data-1.4/.metadata",
}


# Skip paths we don't want to assert file-exists on (they're substring args
# inside display filters / preference keys, not real files).
_SKIP_PATH_SUFFIXES = ("ip.addr", "/16", "/24", "/8", "/32")


def _skip_path(p: str) -> bool:
    if any(p.endswith(s) for s in _SKIP_PATH_SUFFIXES):
        return True
    # Substring args like "http.tcp.port" sometimes show up prefixed with /;
    # drop anything with < 2 slashes that lacks an extension
    if p.count("/") <= 1 and "." not in p.rsplit("/", 1)[-1]:
        return True
    return False


def thicken(task: dict) -> bool:
    """Mutate `task` in place, return True if anything was added."""
    app = task.get("app")
    verbs = _APP_FILE_VERBS.get(app, {})
    fe = verbs.get("file_exists")
    fn = verbs.get("file_nonempty")
    if not fe:
        return False

    original = list(task.get("verification") or [])
    added: list[dict] = []

    paths = sorted(_collect_paths(original))

    # Output files: the agent must produce them
    for p in paths:
        if _skip_path(p):
            continue
        # skip clearly-non-output paths like .config dirs (preferences-only
        # tasks, covered below)
        is_output = any(
            p.endswith(ext) for ext in
            (".qgz", ".qgs", ".gpkg", ".csv", ".pdf", ".png", ".svg", ".qml",
             ".sql", ".json", ".xlsx", ".xls", ".db", ".ddl", ".pcap",
             ".pcapng", ".txt", ".bin", ".tnz", ".tpl", ".obj", ".zolca")
        )
        if not is_output:
            continue

        if not _already_has(original + added, fe, p):
            added.append({
                "command": f"{fe} {p}",
                "key": "exists", "expected": True,
                "description": f"Output file {p} exists",
            })
        if fn and not _already_has(original + added, fn, p):
            added.append({
                "command": f"{fn} {p}",
                "key": "match", "expected": True,
                "description": f"Output file {p} is non-empty",
            })

    # Preferences-class tasks: look at the SEMANTIC entries only, excluding
    # defensive file-exists/file-nonempty/workspace-exists added earlier.
    ws_path = _APP_WORKSPACE_PATHS.get(app)
    semantic = [
        v for v in original
        if not v.get("command", "").startswith(("check-file-exists ",
                                                "check-file-nonempty ",
                                                "check-workspace-exists"))
    ]
    pref_prefixes = (
        "check-pref", "check-recent", "check-setting", "check-colorrule",
        "check-dfilter", "check-cfilter", "check-decode-as",
        "check-protocol", "check-profile-exists", "check-plugin",
        "check-default-crs", "check-home-attribute",
        "check-column-format", "check-ini-", "check-preference",
    )
    looks_like_pref_task = bool(semantic) and all(
        any(v.get("command", "").startswith(p) for p in pref_prefixes)
        for v in semantic
    ) and ws_path is not None

    if looks_like_pref_task and fe:
        if not _already_has(original + added, fe, ws_path):
            added.append({
                "command": f"{fe} {ws_path}",
                "key": "exists", "expected": True,
                "description": f"Workspace/config path {ws_path} present after edit",
            })
        # Add a second corroborating assertion: the config path is non-empty
        # (for file paths) OR contains a recognizable substring.
        if fn and ws_path and "." in ws_path.rsplit("/", 1)[-1]:
            if not _already_has(original + added, fn, ws_path):
                added.append({
                    "command": f"{fn} {ws_path}",
                    "key": "match", "expected": True,
                    "description": f"Config file {ws_path} is non-empty",
                })
        # App-specific extra sanity check for preference tasks
        if app == "dbeaver":
            if not any(v.get("command") == "check-workspace-exists" for v in original + added):
                added.append({
                    "command": "check-workspace-exists",
                    "key": "exists", "expected": True,
                    "description": "DBeaver workspace exists",
                })
        elif app == "wireshark":
            prefs_file = "/home/user/.config/wireshark/preferences"
            if not _already_has(original + added, fe, prefs_file):
                added.append({
                    "command": f"{fe} {prefs_file}",
                    "key": "exists", "expected": True,
                    "description": "Wireshark preferences file exists",
                })
            if fn and not _already_has(original + added, fn, prefs_file):
                added.append({
                    "command": f"{fn} {prefs_file}",
                    "key": "match", "expected": True,
                    "description": "Wireshark preferences file is non-empty",
                })
        elif app == "opentoonz":
            # OpenToonz prefs path varies under flatpak; add a workspace
            # existence stand-in check via file-exists on the log dir.
            flat_root = "/home/user/.var/app/io.github.OpenToonz/config"
            if not _already_has(original + added, fe, flat_root):
                added.append({
                    "command": f"{fe} {flat_root}",
                    "key": "exists", "expected": True,
                    "description": "OpenToonz flatpak config directory created",
                })
        elif app == "openlca":
            if not _already_has(original + added, fe,
                                "/home/user/openLCA-data-1.4"):
                added.append({
                    "command": "check-file-exists /home/user/openLCA-data-1.4",
                    "key": "exists", "expected": True,
                    "description": "openLCA workspace dir present",
                })

    # ── Extra pref-key corroboration: for every check-preference(-*)
    # command, also add a check-file-contains on the config file that
    # asserts the literal preference key appears verbatim.  This catches
    # cases where the agent only partially edited the settings file.
    if looks_like_pref_task and ws_path and "." in ws_path.rsplit("/", 1)[-1]:
        for v in list(original + added):
            cmd = v.get("command", "")
            # Extract a preference key token from common check-* commands
            parts = cmd.split()
            if len(parts) < 2:
                continue
            key_token = None
            if parts[0] in ("check-pref-any", "check-pref-any-contains",
                            "check-preference", "check-preference-contains"):
                # check-preference <key> <val>   or   check-pref <plugin> <key> <val>
                key_token = parts[1] if parts[0].startswith("check-pref-any") \
                                      or parts[0] == "check-preference" \
                                      or parts[0] == "check-preference-contains" \
                                      else parts[2] if len(parts) > 2 else None
            elif parts[0] == "check-pref" and len(parts) > 2:
                key_token = parts[2]
            elif parts[0] == "check-setting" and len(parts) > 1:
                key_token = parts[1]
            if not key_token or any(c in key_token for c in "'\"/"):
                continue
            # Add a file-contains assertion for the bare key
            contains_cmd = f"check-file-contains {ws_path} {key_token}"
            if not any(v2.get("command") == contains_cmd
                        for v2 in original + added):
                added.append({
                    "command": contains_cmd,
                    "key": "match", "expected": True,
                    "description": f"Config file mentions pref key '{key_token}'",
                })

    if not added:
        return False

    task["verification"] = _unique(original + added)
    return True


def main():
    count = 0
    touched = 0
    for task_dir in sorted(TASKS_DIR.iterdir()):
        if not task_dir.is_dir():
            continue
        tf = task_dir / "task.json"
        if not tf.exists():
            continue
        count += 1
        try:
            task = json.loads(tf.read_text())
        except json.JSONDecodeError:
            continue
        if task.get("app") not in _APP_FILE_VERBS:
            continue
        if thicken(task):
            tf.write_text(json.dumps(task, indent=2) + "\n")
            touched += 1

    # Also rewrite each app's combined <app>_tasks.json from disk
    apps = set(_APP_FILE_VERBS.keys())
    for app in apps:
        combined_path = TASKS_DIR / f"{app}_tasks.json"
        tasks = []
        for task_dir in sorted(TASKS_DIR.iterdir()):
            if not task_dir.is_dir():
                continue
            tf = task_dir / "task.json"
            if not tf.exists():
                continue
            try:
                t = json.loads(tf.read_text())
            except json.JSONDecodeError:
                continue
            if t.get("app") == app:
                tasks.append(t)
        if tasks:
            combined_path.write_text(json.dumps(tasks, indent=2) + "\n")
            print(f"  {app}: rewrote {combined_path.name} with {len(tasks)} tasks")

    print(f"\nScanned {count} task.json, thickened {touched}")


if __name__ == "__main__":
    main()

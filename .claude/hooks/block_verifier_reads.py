#!/usr/bin/env python3
"""PreToolUse hook: enforce task_generator/CLAUDE.md pipeline.

Blocks Read/Grep/Glob/Bash access to verifiers/<app>/ until both
task_generator/tasks/proposals_<app>.json and evaluated_<app>.json
exist. verifiers/CLAUDE.md is always allowed (pipeline doc).
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TASKS_DIR = os.path.join(REPO, "task_generator", "tasks")


def stage_unlocked(app: str) -> bool:
    return os.path.exists(os.path.join(TASKS_DIR, f"proposals_{app}.json")) and \
           os.path.exists(os.path.join(TASKS_DIR, f"evaluated_{app}.json"))


def extract_app(path_or_text: str):
    """Return the app name guarded by this hook, or None if the string
    doesn't touch a task-specific verifier subfolder."""
    if not path_or_text:
        return None
    # Match .../verifiers/<app>/... or verifiers/<app>/... or verifiers/<app>
    for m in re.finditer(r"verifiers/([A-Za-z0-9_.\-]+)", path_or_text):
        app = m.group(1)
        # Allow the top-level pipeline doc itself
        if app in ("CLAUDE.md", "__pycache__"):
            continue
        # Allow bare "verifiers/" prefix with no trailing component
        if not app:
            continue
        return app
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # fail-open on malformed input

    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input", {}) or {}

    candidates = []
    if tool == "Read":
        candidates.append(ti.get("file_path", ""))
    elif tool == "Glob":
        candidates.append(ti.get("pattern", ""))
        candidates.append(ti.get("path", ""))
    elif tool == "Grep":
        candidates.append(ti.get("path", ""))
        # pattern itself can leak verifier content if used as include/glob
        candidates.append(ti.get("glob", ""))
    elif tool == "Bash":
        candidates.append(ti.get("command", ""))
    else:
        sys.exit(0)

    for c in candidates:
        app = extract_app(c)
        if app and not stage_unlocked(app):
            reason = (
                f"Blocked by pipeline hook: reading verifiers/{app}/ is not "
                f"allowed until Stage 1 (proposals) and Stage 2 (evaluation) "
                f"are complete. Create task_generator/tasks/proposals_{app}.json "
                f"and evaluated_{app}.json first, per task_generator/CLAUDE.md."
            )
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }))
            sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()

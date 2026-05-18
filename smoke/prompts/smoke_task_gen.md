# Smoke Task Generation — {{APP_NAME}}

You are running the 4-stage smoke task generation pipeline for the `{{APP_NAME}}` app.
Read `{{SMOKE_CLAUDE_MD}}` for the full pipeline specification. This prompt gives you the
inputs, output paths, and key reminders for each stage.

Smoke tasks are minimal (difficulty 1-2) tasks whose only purpose is to exercise every
verifier endpoint in a live sandbox. One task per endpoint group.

---

## Inputs

- Verifier README: `{{VERIFIER_README}}`
- Verifier source: `{{VERIFIER_PY}}`
- Output root: `{{SMOKE_TASKS_DIR}}/`
- Max tasks: {{MAX_TASKS}}
- Project root: `{{PROJECT_ROOT}}`

---

## Stage 1: Endpoint Mapping

**Read the verifier first** (smoke is verifier-driven, unlike `task_generator`).

1. Read `{{VERIFIER_README}}` — list every endpoint.
2. Read `{{VERIFIER_PY}}` — note exact CLI argument syntax for each subcommand.
3. Group endpoints by the user action that produces the inspectable state.
4. For each group, design one minimal task (difficulty 1-2).
5. Check `{{SMOKE_TASKS_DIR}}/` for existing smoke tasks. Do not duplicate.

Each proposal:

```json
{
  "id": "smoke_{{APP_NAME}}_<descriptor>",
  "app": "{{APP_NAME}}",
  "objective": "What the agent must do (end-state only, not steps)",
  "endpoint_group": ["check-export-codec", "check-export-sample-rate"],
  "input_requirements": ["source.wav — minimal WAV file"],
  "success_criteria": ["exported file exists", "codec is pcm_s16le"],
  "estimated_difficulty": 2
}
```

Save to: `{{SMOKE_TASKS_DIR}}/proposals_{{APP_NAME}}.json`

---

## Stage 2: Coverage Evaluation

Score each proposal on three axes. **Reject if any axis fails.**

| Axis | Accept | Reject |
|------|--------|--------|
| Endpoint coverage | Covers at least one endpoint group not already covered | Duplicate — same group covered by a higher-ranked proposal |
| Simplicity | estimated_difficulty 1-2 | > 2 — too complex for a smoke task |
| Data generatability | >= 4 (synthesizable with Python/ffmpeg/stdlib) | < 4 — needs real-world or proprietary data |

After evaluation, check `uncovered_endpoints`. If any endpoint groups are not covered,
generate additional proposals for them and re-evaluate. Repeat until all endpoints are
covered or explicitly documented as skip-worthy.

Save to: `{{SMOKE_TASKS_DIR}}/evaluated_{{APP_NAME}}.json`

```json
{
  "accepted": [ ...proposals with scores... ],
  "rejected": [ ...proposals with reasons... ],
  "coverage_matrix": {"check-export-codec": "smoke_{{APP_NAME}}_export_wav", ...},
  "uncovered_endpoints": [],
  "summary": {"total": 12, "accepted": 9, "rejected": 3}
}
```

---

## Stage 3: Finalization

For each accepted proposal, write the final `task.json`.

1. Map each success criterion to **exact verifier commands** (copy syntax from `{{VERIFIER_PY}}`).
   - Do NOT include the `python3 /home/user/verifiers/...` prefix.
   - Prefer `check-*` with `key`/`expected`. Use `eval` for computed comparisons.
   - Every check needs a `description`.
2. Write the task description — agent sees only this. State the end-state precisely
   (exact filenames, paths, values). No step-by-step GUI instructions.
3. Add edge-case checks: if task exports a file → also verify it exists; if task renames
   an element → also check the new name; if task changes a setting → also verify the value.

Write to: `{{SMOKE_TASKS_DIR}}/<task_id>/task.json`

```json
{
  "id": "smoke_{{APP_NAME}}_<descriptor>",
  "app": "{{APP_NAME}}",
  "task": "Clear end-state description with exact filenames, paths, values.",
  "env": {
    "files": [
      {"filename": "source.wav", "sandbox_path": "/home/user/Music/source.wav"}
    ]
  },
  "verification": [
    {
      "command": "check-export-format /home/user/Music/out.wav wav",
      "key": "match",
      "expected": true,
      "description": "Exported container is WAV"
    }
  ],
  "metadata": {
    "complexity": 2,
    "estimated_difficulty": 2,
    "endpoint_group": ["check-export-format", "check-export-codec"]
  }
}
```

Also write: `{{SMOKE_TASKS_DIR}}/{{APP_NAME}}_smoke_tasks.json` — JSON array of all final tasks.

---

## Stage 4: Environment Synthesis

For every finalized task with non-empty `env.files`, generate and verify those files.

### Required workflow: Research → Generate → Verify

1. **Research first.** Check `verifiers/{{APP_NAME}}/` and `task_generator/tasks/` for
   existing file-builder patterns to reuse. Do not reinvent what is already known to work.
2. **Actually generate the file.** Run a script so the artifact lands on disk.
   A script that was written but never executed does not count.
3. **Verify the file.** After generation:
   - Confirm it exists and has non-zero size.
   - Parse/open it with the same library the task will use.
   - Assert any content constraints encoded in the task.
   - If verification fails, fix the generator and regenerate.
4. **Record lessons.** If you debugged a broken generator, append a bullet to
   `{{PROJECT_ROOT}}/task_generator/LESSONS.md` under the `{{APP_NAME}}` heading.

### Common patterns

- **WAV audio**: Python `wave` stdlib — 1-2 seconds, mono, 44100 Hz, sine or silence
- **MP3/OGG/FLAC**: use `ffmpeg` to transcode from a generated WAV
- **Images (PNG)**: Pillow (`pip install Pillow`) or minimal stdlib struct approach
- **CSV/JSON/plain text**: write directly
- **App-native project files** (.aup, .svg, .ods, .xcf, etc.): write minimal valid XML/ZIP;
  check `verifiers/{{APP_NAME}}/test_{{APP_NAME}}.py` for existing builders

Keep files minimal: 1-2 seconds of audio, 10-row CSV, 100×100 image. Smoke tasks do not
need rich content — they only need the file to be valid and openable.

Write env files to: `{{SMOKE_TASKS_DIR}}/<task_id>/env/<filename>`

Write manifest to: `{{SMOKE_TASKS_DIR}}/<task_id>/env_manifest.json`

```json
{
  "task_id": "smoke_{{APP_NAME}}_<descriptor>",
  "files": [
    {"filename": "source.wav", "sandbox_path": "/home/user/Music/source.wav", "type": "wav"}
  ]
}
```

---

## Done

When all 4 stages are complete:
- `{{SMOKE_TASKS_DIR}}/proposals_{{APP_NAME}}.json` exists
- `{{SMOKE_TASKS_DIR}}/evaluated_{{APP_NAME}}.json` exists (with empty `uncovered_endpoints`)
- `{{SMOKE_TASKS_DIR}}/<task_id>/task.json` exists for every accepted task
- `{{SMOKE_TASKS_DIR}}/<task_id>/env/` and `env_manifest.json` exist for tasks that need them
- `{{SMOKE_TASKS_DIR}}/{{APP_NAME}}_smoke_tasks.json` exists

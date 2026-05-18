# Smoke Task Generation Pipeline

This document defines how to generate, evaluate, finalize, and synthesize environments
for smoke tasks. Smoke tasks are minimal (difficulty 1-3) tasks whose only purpose is
to exercise every verifier endpoint for an app in a live sandbox, confirming that the
verifier's checker side works correctly before real training/benchmark tasks are generated.

**Key difference from `task_generator/CLAUDE.md`:** smoke tasks are designed
_around the verifier_ (start by reading endpoints, then design tasks to cover them).
Real tasks are designed _around the app_ (ignore the verifier until Stage 3).

## Directory Layout

```
smoke/
├── CLAUDE.md              # This file — pipeline instructions
├── smoke_loop.py          # Automates the full pipeline (generate + run + repair)
├── prompts/
│   └── smoke_task_gen.md  # Headless prompt for the generate phase
└── smoke_tasks/           # Output: one folder per generated smoke task
    └── <app>/
        ├── proposals_<app>.json    # Stage 1 output
        ├── evaluated_<app>.json    # Stage 2 output
        ├── <app>_smoke_tasks.json  # Combined final tasks
        └── <task_id>/
            ├── task.json           # Final smoke task spec
            └── env/                # Input files the agent needs
                └── env_manifest.json
```

---

## Pipeline Overview

```
Stage 1: Map endpoints  →  Stage 2: Evaluate  →  Stage 3: Finalize  →  Stage 4: Synthesize env
 (read verifier,             (coverage +           (write task.json,      (generate +
  design one task            simplicity +           exact verifier         verify input
  per endpoint group)        data generatability)   commands)              files)
```

Key principle: **read the verifier in Stage 1.** Unlike `task_generator` (which forbids
reading the verifier until Stage 3), smoke tasks are explicitly verifier-driven. The goal
is coverage of every endpoint, so the verifier must be consulted from the start.

---

## Difficulty Scale

| Level | Steps | Appropriate for smoke? |
|-------|-------|------------------------|
| 1 | < 5 steps | ✅ Yes |
| 2 | 5-10 linear | ✅ Yes |
| 3 | 11-20, some reasoning | ✅ Yes |
| 4 | 20-40 | ❌ No |
| 5 | > 40 | ❌ No |

**Default range: 1-3. Reject any proposal with estimated difficulty > 3.**

Smoke tasks should be so simple that any competent GUI agent completes them.
Agent failure indicates a sandbox/environment problem, not task difficulty.

---

## Stage 1: Endpoint Mapping

**Goal:** Read the verifier and design one minimal task per endpoint group.

### REQUIRED: Read the verifier first

Unlike `task_generator`, you MUST read the verifier before proposing tasks:

1. Read `verifiers/<app>/README.md` — lists every endpoint, arguments, return values
2. Read `verifiers/<app>/<app>.py` — confirms exact CLI argument syntax

### Procedure

1. List every endpoint exposed by the verifier.
2. Group endpoints by the **user action** that produces the inspectable state.
   Example for Audacity: `check-export-codec`, `check-export-sample-rate`,
   `check-export-channels` all verify an export action → one group.
3. For each group, design **one minimal task** (difficulty 1-3) that causes a real
   agent to put the app into a state where those endpoints return meaningful results.
4. Check `smoke/smoke_tasks/<app>/` for existing smoke tasks. Do not duplicate.
5. Overshoot by ~20% (some will be filtered in Stage 2).

### Proposal schema

Each proposal in the JSON array:

```json
{
  "id": "smoke_<app>_<descriptor>",
  "app": "<app>",
  "objective": "What the agent must do (end-state, not steps)",
  "endpoint_group": ["check-export-codec", "check-export-sample-rate"],
  "input_requirements": ["source.wav — minimal WAV file"],
  "success_criteria": ["exported file exists at path", "codec is pcm_s16le"],
  "estimated_difficulty": 2
}
```

### Output

Save to `smoke/smoke_tasks/<app>/proposals_<app>.json`.

---

## Stage 2: Coverage Evaluation

**Goal:** Filter proposals on coverage, simplicity, and data generatability.

### Scoring axes

#### 1. Endpoint Coverage (required)

Does this task cover at least one endpoint group not already covered by an accepted task?

- **Reject if duplicate**: same endpoint group covered by a higher-ranked proposal

#### 2. Simplicity (accept: 1-3)

Is the task genuinely easy?

- **Reject if difficulty > 3**: task is too complex; split or simplify it
- **Reject if agent needs domain expertise**: smoke tasks must be obvious to any agent

#### 3. Data Generatability (accept: >= 4)

Can all input files be synthesized programmatically?

| Score | Meaning |
|-------|---------|
| 5 | No input files needed, or trivially simple (e.g. plain text) |
| 4 | Simple structured data (minimal WAV, small CSV, simple image) |
| 3 | Needs complex domain data with tricky constraints |
| 1-2 | Needs real-world/proprietary data |

- **Reject if < 4**: we must be able to create all inputs ourselves

### Output

```json
{
  "accepted": [ ...proposals with scores attached... ],
  "rejected": [ ...proposals with rejection reasons... ],
  "coverage_matrix": {
    "check-export-codec": "smoke_audacity_export_wav",
    "check-preference": "smoke_audacity_set_sample_rate"
  },
  "uncovered_endpoints": ["check-some-endpoint"],
  "summary": {"total": 12, "accepted": 9, "rejected": 3}
}
```

Save to `smoke/smoke_tasks/<app>/evaluated_<app>.json`.

### Coverage check

After evaluation, check `uncovered_endpoints`. If any endpoints are not covered by an
accepted task, generate additional proposals for those endpoints and re-evaluate. Do not
finalize until all endpoints have at least one accepted task (or are documented as
skip-worthy in `smoke/smoke_tasks/<app>/skipped_endpoints_<app>.md`).

---

## Stage 3: Finalization

**Goal:** For each accepted proposal, write the final `task.json`.

### Procedure

For each accepted proposal:

1. **Map each success criterion** to exact verifier commands:
   - Copy the subcommand name and arguments from the verifier source exactly.
   - The `command` field must NOT include the `python3 /home/user/verifiers/...` prefix —
     the harness prepends that automatically.
   - Prefer `check-*` commands with `key`/`expected`.
   - Use `eval` for counting or computed comparisons.
   - Include a `description` on every check.

2. **Write the task description** — the agent sees only this text:
   - State the desired end-state, not step-by-step GUI instructions.
   - Include exact filenames, paths, values, setting names.
   - Be unambiguous: the agent must know exactly what "done" looks like.

3. **Add edge-case checks** the criteria might miss:
   - Task says "export file" → also check `file-exists`
   - Task creates a named element → also check the name exactly
   - Task changes a setting → also check the setting value, not just that it changed

4. **Write** `smoke/smoke_tasks/<app>/<task_id>/task.json`.

5. **Write** the combined file `smoke/smoke_tasks/<app>/<app>_smoke_tasks.json`
   containing all final tasks as a JSON array.

### task.json schema

```json
{
  "id": "smoke_<app>_<descriptor>",
  "app": "<app>",
  "task": "Clear end-state description. Exact filenames, paths, values.",
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

---

## Stage 4: Environment Synthesis

**Goal:** Generate the input files each smoke task needs, with verification.

Same rules as `task_generator/CLAUDE.md` Stage 4. Summary:

### Required Workflow: Research → Generate → Verify

1. **Research first.** Check `verifiers/<app>/` for existing file-builder patterns
   (e.g. WAV generation in test files). Reuse known-working patterns.
2. **Actually generate the file.** Run the generator script — the artifact must land
   on disk. A script that was written but not executed does not count.
3. **Verify the file works.** After generation:
   - Confirm it exists and has non-zero size.
   - Parse/open it with the same library the task will use.
   - Assert any content constraints the task encodes (sample rate, duration, etc.).
   - If verification fails, fix the generator and regenerate.
4. **Record lessons.** If you debugged a broken generator, append a bullet to
   `task_generator/LESSONS.md` under the app heading.

### File generation patterns

- **WAV audio**: Python `wave` stdlib — 1-2 seconds, mono, 44100 Hz
- **Images (PNG)**: Pillow or Python `struct` (minimal valid PNG header + IDAT)
- **CSV/JSON/text**: write directly
- **App-native formats** (.aup, .svg, .ods, etc.): write minimal valid XML/ZIP
  matching the exact format the app reads; check `verifiers/<app>/test_<app>.py`
  for existing builders

### Output

For each task with env files:

- `smoke/smoke_tasks/<app>/<task_id>/env/<filename>`
- `smoke/smoke_tasks/<app>/<task_id>/env_manifest.json`:

```json
{
  "task_id": "smoke_audacity_export_wav",
  "files": [
    {"filename": "source.wav", "sandbox_path": "/home/user/Music/source.wav", "type": "wav"}
  ]
}
```

---

## Running the Full Pipeline

### Automated (recommended)

```bash
python smoke/smoke_loop.py --app <app>
```

This runs all 4 stages (via headless Claude) then executes each task in a live sandbox
with the full judge → comparator → repair cycle.

```bash
# Generate only (inspect before running)
python smoke/smoke_loop.py --app <app> --generate-only

# Re-run after editing the verifier
python smoke/smoke_loop.py --app <app> --run-only
```

### Manual (interactive Claude)

1. Read this file (`smoke/CLAUDE.md`) completely.
2. Stage 1: Read verifier → save proposals.
3. Stage 2: Evaluate → save evaluated JSON.
4. Stage 3: Write task.json files.
5. Stage 4: Generate and verify env files.
6. Run `smoke_loop.py --run-only` to execute the tasks.

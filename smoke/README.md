# Smoke Stage

This is the second stage of the pipeline. Its purpose is to **stress-test and debug the verifiers** produced in stage one by running them against real agent trajectories in a live sandbox.

## What It Does

For each app, the smoke loop:

1. Generates a small set of minimal tasks (one per verifier endpoint group).
2. Runs each task in a fresh sandbox with a real GUI agent.
3. Uses Claude Code as an independent **LLM-as-judge** to analyze the trajectories and produce comparable
4. Compares the verifier's output against the judge to surface bugs in the verifier itself, then attempts an automated repair loop.

The output is a per-app report (`smoke/runs/<app>_<timestamp>/REPORT.md`) showing which endpoint groups pass end-to-end and which need further fixes.

## Expected Runtime

Roughly **5–10 minutes per task**, so a full app run typically takes **1–3 hours** depending on how many smoke tasks were generated. Plan accordingly.

## Prerequisites

- The verifier for the target app is already implemented and its unit tests pass:
  ```bash
  python verifiers/<app>/test_<app>.py
  ```
- E2B credentials are configured (`E2B_API_KEY`) and the `desktop-all-apps` template has been built.
- The Claude Code CLI (`claude`) is installed and on `PATH` — it powers the LLM-as-judge stage.

## Configuration

The GUI agent model used inside the sandbox is configurable. Set `SMOKE_MODEL` in `.env` (default: `kimi-k2.6`), or pass `--model` on the CLI:

```bash
SMOKE_MODEL=kimi-k2.6
```

## Running It

Full pipeline (generate + run + repair):

```bash
python smoke/smoke_loop.py --app <app>
```

Generate tasks only (inspect before running):

```bash
python smoke/smoke_loop.py --app <app> --generate-only
```

Re-run existing tasks after editing the verifier:

```bash
python smoke/smoke_loop.py --app <app> --run-only
```

<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/opencomputer-white.svg" />
    <img src="docs/opencomputer.svg" alt="OpenComputer" width="80" align="center" />
  </picture>
  <br />
  OpenComputer — Verifiable Software Worlds for Computer-Use Agents
</h1>

<p align="center">
  <a href="https://echo0715.github.io/OpenComputer" target="_blank" rel="noopener"><strong>🌐 Website</strong></a>
  &nbsp;·&nbsp;
  <a href="https://arxiv.org/pdf/2605.19769" target="_blank" rel="noopener">📄 Paper</a>
  &nbsp;·&nbsp;
  <a href="#synthesis-quick-start">Synthesis Quick Start</a>
  &nbsp;·&nbsp;
  <a href="#evaluation-quick-start">Evaluation Quick Start</a>
  &nbsp;·&nbsp;
  <a href="./LICENSE">License</a>
</p>

<p align="center">
  <a href="./LICENSE"><img alt="License: Apache 2.0" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" /></a>
</p>

We present **OpenComputer**, a verifier-grounded framework for constructing verifiable software worlds for computer-use agents. OpenComputer integrates four components: (1) app-specific state verifiers that expose structured inspection endpoints over real applications, (2) a self-evolving verification layer that improves verifier reliability using execution-grounded feedback, (3) a task-generation pipeline that synthesizes realistic and machine-checkable desktop tasks, and (4) an evaluation harness that records full trajectories and computes auditable partial-credit rewards. In its current form, OpenComputer covers 33 desktop applications and 1,000 finalized tasks spanning browsers, office tools, creative software, development environments, file managers, and communication applications. Experiments show that OpenComputer's hard-coded verifiers align more closely with human adjudication than LLM-as-judge evaluation, especially when success depends on fine-grained application state. Frontier agents struggle with end-to-end completion despite partial progress, and open-source models exhibit sharp drops from their OSWorld-Verified scores, exposing a persistent gap in robust computer automation.

---

## Why "synthetic"

Hand-authored GUI benchmarks don't scale — every task needs a unique workbook, project file, or screen state, and every task needs a verifier that knows where to look. `OpenComputer` automates both sides:

- **Tasks are generated**, not hand-written. The task generator (`task_generator/`) proposes goals, scores them on complexity and how easily their input artifacts can be synthesized, matches each accepted goal to a verifier endpoint, and emits a final `task.json` plus a fully synthesized `env/` directory of input files (CSVs, ODT/ODS/ODP/XLSX docs, PNG/SVG images, project files, configs, …).
- **Environments are reproducible**. Every task ships with the exact files needed to seed the sandbox; the runtime uploads them, launches the right app, and waits for it to be ready before the agent is given control.
- **Verification is programmatic first, LLM-judged second**. Each app has a verifier module exposing `check-*` CLI endpoints that read live IPC state (CDP, D-Bus, UNO, AT-SPI), parse files on disk, or query SQLite profile DBs. An LLM judge backs them up where automatic inspection isn't enough.

---

## Synthesis Quick start

### Prerequisites

```bash
cp .env.example .env
pip install -r requirements.txt
```

Then make sure the following are in place:

| Requirement | Why it's needed | How to set it |
|---|---|---|
| **E2B sandbox** | every stage spins up the `desktop-all-apps` template | set `E2B_API_KEY` in `.env`, then run `python computer_env/provision/e2b/build_all_apps_template.py` once |
| **Reasoning-backend CLI** | drives verifier authoring, smoke judge/comparator/repair, and task generation | install and authenticate `claude` (default) or `codex`. A single `SMOKE_BACKEND` in `.env` selects the CLI for `smoke/smoke_loop.py`(default `claude`);
| **Smoke GUI-agent key** | the in-sandbox agent that actually executes smoke tasks | set the API key matching `SMOKE_MODEL` (default `kimi-k2.6` → `KIMI_API_KEY`). Override `SMOKE_MODEL` to use Claude / GPT / Gemini / etc. and set that family's key instead |
| **LLM-as-judge key** *(optional)* | only used when a verifier check has `judge: llm` | `JUDGE_MODEL` defaults to `gpt-5.4` → `OPENAI_API_KEY`. Override the model to reuse an existing key |

### Pipeline order

The pipeline runs in a strict order — verifier quality gates task quality, and task quality gates evaluation:

1. **Verifier** ([`verifiers/`](./verifiers/README.md)) — generate the per-app `check-*` endpoints used to score tasks.
2. **Smoke** ([`smoke/`](./smoke/README.md)) — exercise each verifier endpoint with a real agent in a live sandbox and repair any bugs.
3. **Task generation** ([`task_generator/`](./task_generator/README.md)) — propose, evaluate, match to the verifier, and synthesize env files for finalized tasks.

The root [`CLAUDE.md`](./CLAUDE.md) is the canonical guide. You can either:

- **Automated:** hand `CLAUDE.md` to a coding agent and let it drive the full loop end-to-end (synthesize verifiers → smoke test → generate tasks → repair task verifiers(optional)).
- **Manual:** step through each stage yourself by following the per-stage READMEs above in order, inspecting output quality between stages.

---


## Evaluation Quick start

### 1. Install

```bash
git clone <this repo>
cd OpenComputer
cp .env.example .env       # fill in backend-related variables + the model API keys you plan to use
pip install -r requirements.txt
```

`requirements.txt` installs the E2B core SDK and Desktop SDK from PyPI, plus `anthropic`, `openai`, `dashscope`, `Pillow`, `httpx`, `python-dotenv`, etc.

### 2. Prepare a backend

Pick **one** backend.

```bash
# E2B (cloud sandbox — recommended; this is the canonical target)
python computer_env/provision/e2b/build_all_apps_template.py

# Docker (local; useful for offline iteration)
bash computer_env/provision/docker/build_image.sh

# remote_docker (AWS or Tencent Cloud worker fleet)
# Follow one of the dedicated provisioning guides:
#   computer_env/provision/aws/README.md
#   computer_env/provision/tencentcloud/README.md
```

All three backends use the same Ubuntu/XFCE desktop stack with the app suite preinstalled. The E2B build pushes a template named `desktop-all-apps`; the Docker backends use an OCI image.

For the full `remote_docker` provisioning flow, directly follow one of:

- [`computer_env/provision/aws/README.md`](./computer_env/provision/aws/README.md)
- [`computer_env/provision/tencentcloud/README.md`](./computer_env/provision/tencentcloud/README.md)

Those provider docs are the source of truth for:

- provider auth verification
- provider prerequisites (`setup_prereqs.py`)
- desktop image build + registry push
- worker launch / stream inspection / termination
- `run_eval.py --env-backend remote_docker` usage and runtime notes

### 3. Run an evaluation

```bash
# Single task
python evaluation/run_eval.py --app chrome --task chrome_form_fill_httpbin --model claude-sonnet-4-6

# All tasks for one app, parallel
python evaluation/run_eval.py --app libreoffice_calc --model gpt-5.4 --parallel 4

# Smoke test one task per app on Docker
python evaluation/run_eval.py --env-backend docker --tasks-per-app 1

# Run against a remote Docker fleet
python evaluation/run_eval.py \
  --env-backend remote_docker \
  --docker-image <remote-registry>/<repo>:latest \
  --tasks-per-app 1 \
  --parallel 2

# Sample N tasks per app
python evaluation/run_eval.py --tasks-per-app 3 --model kimi-k2.6

# Resume a previous run (skips already-completed tasks)
python evaluation/run_eval.py --resume <run_id>

# Point the agent at a local OpenAI-compatible endpoint
python evaluation/run_eval.py --model gui-owl-1.5 --endpoint-port 8001
```

Trajectories, screenshots, and `report.json` land in `evaluation/runs/<run_id>/` (gitignored).

---

## Supported agents

The agent registry (`agents/registry.py`) maps friendly aliases to agent classes and sensible defaults. Pass any alias to `--model`.

| Family | Aliases |
|---|---|
| **Claude** (Anthropic) | `claude-sonnet-4-5`, `claude-sonnet-4`, `claude-sonnet-4-6`, `claude-opus-4`, `claude-opus-4-1`, `claude-opus-4-5`, `claude-opus-4-6`, `claude-3-7-sonnet` |
| **ChatGPT** (OpenAI / Azure) | `chatgpt`, `gpt-5`, `gpt-5.4`, `computer-use-preview`, `azure-chatgpt`, `azure-gpt-5.4`, `azure-computer-use-preview`, `azure-gpt-5.3-chat` |
| **Gemini** (Google AI Studio) | `gemini-3-flash`, `gemini-3-flash-preview`, `gemini-2.5-computer-use` |
| **Kimi** (Moonshot) | `kimi-k2.5`, `kimi-k2.6` |
| **Qwen** (DashScope / OpenAI-compatible) | `qwen3-vl`, `qwen2.5-vl-72b`, `qwen3.5-35b-a3b`, `qwen3.5-27b`, `qwen3.5-9b`, `qwen3.5-4b` |
| **GUI-Owl** | `owl1.5`, `gui-owl-1.5` |
| **EvoCUA** | `evocua-s1`, `evocua-s2` |
| **Specialised CUA models** | `mano`, `opencua`, `dart` |

`python evaluation/run_eval.py --list-models` enumerates everything currently registered. Unknown model IDs are routed by family heuristics (any name containing `claude`, `kimi`, `qwen`, `gemini`, `gpt-`, etc.) so you can also pass full vendor model IDs directly.

---

## Configuration Overview

This section intentionally lists only the top-level variables most users need to run evaluations.
Backend-specific and operator-facing settings are documented in:

- [`computer_env/README.md`](./computer_env/README.md) for sandbox/backend runtime settings
- [`computer_env/provision/aws/README.md`](./computer_env/provision/aws/README.md) for `remote_docker` on AWS
- [`computer_env/provision/tencentcloud/README.md`](./computer_env/provision/tencentcloud/README.md) for `remote_docker` on Tencent Cloud China
- [`evaluation/repair/README.md`](./evaluation/repair/README.md) for repair-only settings
- [`.env.example`](./.env.example) for a starter template

### Common Evaluation Settings

| Variable | Default | Purpose |
|---|---|---|
| `EVAL_MODEL` | `kimi-k2.6` | Default agent for `evaluation/run_eval.py`. |
| `EVAL_MAX_ITERATIONS` | `100` | Max screenshot-action steps per task. |
| `EVAL_SANDBOX_TIMEOUT` | `3600` | Per-task sandbox lifetime in seconds. |
| `JUDGE_MODEL` | `gpt-5.4` | LLM-as-judge model used by verification. |
| `SMOKE_BACKEND` | `claude` | Shared reasoning-backend CLI for `smoke/smoke_loop.py` and `evaluation/repair/repair_loop.py` (`claude` or `codex`). Override per-run with `--backend`. Other `REPAIR_*` knobs live in the repair README. |

---

## Extending OpenComputer

- **New app** or **more tasks for an existing app** → see [Synthesizing your own environment](#synthesizing-your-own-environment) above.
- **New agent** → subclass `agents/base.py:BaseAgent`, parse the model's output into pyautogui code strings (or the special `DONE` / `FAIL` / `WAIT` tokens), and register the alias in `agents/registry.py`. Unknown model IDs are routed by family heuristics, so any name containing `claude`, `kimi`, `qwen`, `gemini`, `gpt-`, etc. will pick up the right agent class even without an explicit registry entry.
- **New backend** → drop a runtime adapter under `computer_env/backends/<name>/` implementing `BaseComputerEnvironment`, register it in `computer_env/factory.py`, and add a `--env-backend <name>` branch in `evaluation/run_eval.py`.

---

## Citation

If you use OpenComputer in your research or find it helpful, please cite:

```bibtex
@misc{wei2026opencomputerverifiablesoftwareworlds,
      title={OpenComputer: Verifiable Software Worlds for Computer-Use Agents}, 
      author={Jinbiao Wei and Qianran Ma and Yilun Zhao and Xiao Zhou and Kangqi Ni and Guo Gan and Arman Cohan},
      year={2026},
      eprint={2605.19769},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2605.19769}, 
}
```

---

## License

OpenComputer is released under the [Apache License 2.0](./LICENSE). 
```
Copyright 2026 Yale NLP Lab

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
```

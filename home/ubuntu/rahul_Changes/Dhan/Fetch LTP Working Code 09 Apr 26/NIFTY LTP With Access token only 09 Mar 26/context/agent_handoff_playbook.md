# Agent Handoff Playbook

Use this document when transferring this project to another AI agent or another laptop.

## Purpose

Ensure both codebases stay aligned on:

- environment setup
- dependency versions
- folder conventions
- runtime behavior
- risk and deployment standards

## Current Baseline (Source of Truth)

- Python: `3.12.x`
- Project venv: `.venv`
- Interpreter path (workspace): `${workspaceFolder}\\.venv\\Scripts\\python.exe`
- Test runner: `unittest`
- Main entrypoint: `main.py` (root)
- App entrypoint also supported: `app/main.py`

## Runtime Behavior (As Implemented)

- Default mode: continuous polling loop
- Poll interval config: `config/settings.json` -> `runtime.poll_interval_seconds`
- Default interval: `10` seconds
- Single-run mode: `python main.py --once`
- Continuous mode forced: `python main.py --loop`
- Interval override: `python main.py --interval 5`

## Logging Expectations

- Each successful LTP write logs:
  - symbol
  - LTP value
  - absolute output file path
- Output file location pattern:
  - `H:\\RK Data\\Algo\\Daily Output\\YYYY-MM-DD\\ltp_output.txt`

## Files That Define Behavior

- Entry points:
  - `main.py`
  - `app/main.py`
- Config model:
  - `app/config/settings.py`
- Runtime config:
  - `config/settings.json`
- LTP write + write-log:
  - `app/infra/file_writer.py`
- Context and long-term rules:
  - `context/session_context.md`
  - `context/agent_handoff_playbook.md` (this file)

## Non-Negotiable Alignment Rules

The other project must match these rules:

1. Same Python major/minor (`3.12.x`).
2. Same venv strategy (one project-level `.venv`).
3. Same interpreter convention in IDE.
4. Same config keys for runtime loop:
   - `runtime.continuous`
   - `runtime.poll_interval_seconds`
5. Same no-secrets-in-git policy.
6. Same run/test commands and expected outcomes.

## Setup Commands (Windows)

Run in repository root:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe main.py --once
```

Expected:

- tests: all pass
- app run: fetch log + output file path printed

## Setup Commands (Linux/VPS Equivalent)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -m unittest discover -s tests -v
python main.py --once
```

## Transfer Checklist (Before Sending to Other Agent)

- [ ] Include full repository (excluding `.venv`, logs, secrets).
- [ ] Include `context/session_context.md`.
- [ ] Include `context/agent_handoff_playbook.md`.
- [ ] Confirm `config/settings.json` has `runtime` section.
- [ ] Confirm `.vscode/settings.json` points to `.venv` interpreter.
- [ ] Confirm tests pass in your source copy.

## Validation Checklist (Other Agent Must Complete)

- [ ] Correct interpreter selected (`.venv`).
- [ ] Dependencies installed from `requirements.txt`.
- [ ] `python main.py --once` works.
- [ ] `python app/main.py --once` works.
- [ ] Loop behavior works (`python main.py` polls every 10s).
- [ ] LTP write log line appears with output path.
- [ ] Unit/integration tests pass.

## Standard Prompt to Send to Other Agent

Copy-paste this exactly:

```text
Please ingest this full repository and align your project to the same environment and runtime standards.

Mandatory alignment targets:
1) Python 3.12.x
2) Project-local .venv only (no global packages)
3) Same interpreter convention in IDE
4) Same runtime behavior:
   - default continuous loop
   - interval from config/settings.json -> runtime.poll_interval_seconds
   - --once / --loop / --interval CLI behavior
5) Same logging behavior for LTP file writes
6) Same no-secrets-in-git discipline

Use these docs as source of truth:
- context/session_context.md
- context/agent_handoff_playbook.md

After reading, produce:
- gap analysis between your code and this code
- exact change plan
- implementation updates
- verification output for run/tests
- list of any unresolved conflicts.
```

## If Something Is Missing

If the other agent reports missing pieces, resolve in this order:

1. Environment mismatch (Python version, venv, interpreter).
2. Dependency mismatch.
3. Config schema mismatch.
4. Entry point mismatch.
5. Runtime behavior mismatch.
6. Logging/observability mismatch.

## Governance for Next 2-3 Months

- Every behavior change must update:
  - `README.md`
  - `context/session_context.md`
  - (if cross-agent relevant) this handoff playbook
- Before any live-money rollout:
  - implement risk caps
  - implement kill-switch
  - implement health checks and restart policy
  - test paper mode first

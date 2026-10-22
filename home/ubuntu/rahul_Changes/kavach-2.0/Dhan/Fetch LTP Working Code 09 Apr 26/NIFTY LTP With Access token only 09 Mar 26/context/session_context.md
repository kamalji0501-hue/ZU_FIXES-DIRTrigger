# Session Context (2026-03-09)

## Current Status

- Project is running successfully.
- Tests are passing.
- Local virtual environment is configured and usable.

## Key Fix Applied

- Updated `app/main.py` to support direct execution with:
  - `python app/main.py`
  - `python main.py`
- Fix prevents `ModuleNotFoundError: No module named 'app'` when running `app/main.py` directly.

## Environment Setup Completed

- Created virtual environment:
  - `.venv`
- Installed dependencies from:
  - `requirements.txt`
- Added VS Code workspace settings file:
  - `.vscode/settings.json`

Configured values:

- `python.defaultInterpreterPath = ${workspaceFolder}\\.venv\\Scripts\\python.exe`
- `python.testing.unittestEnabled = true`
- `python.testing.pytestEnabled = false`

## Verified Commands

- `python main.py` -> success
- `python app/main.py` -> success
- `.venv\\Scripts\\python.exe main.py` -> success
- `.venv\\Scripts\\python.exe -m unittest discover -s tests -v` -> 4 tests passed

## Continuous Polling Update

- Added runtime loop configuration in `config/settings.json`:
  - `runtime.continuous = true`
  - `runtime.poll_interval_seconds = 10`
- App now polls NIFTY LTP continuously every 10 seconds by default.
- Added CLI controls:
  - `--once` to run a single fetch and exit
  - `--loop` to force continuous mode
  - `--interval <seconds>` to override polling interval

## Output Location Policy

- Runtime output is written to:
  - `H:\\RK Data\\Algo\\Daily Output\\YYYY-MM-DD\\ltp_output.txt`

## Notes

- In this terminal, `py` launcher is unavailable; use `python` directly.
- If VS Code prompts for interpreter, select:
  - `.venv\\Scripts\\python.exe`

## Long-Term Engineering Blueprint

This repository is intended for long-term, production-grade algorithmic trading and will eventually run with real money. All future enhancements must prioritize safety, reproducibility, and operational clarity over speed of adding features.

### Primary Objectives

- Keep one clean, scalable codebase for multiple strategies.
- Keep developer setup identical across laptops and AI agents.
- Enable predictable VPS deployment with no hidden local dependencies.
- Enforce risk controls before live capital usage.

### Repository Architecture Standard (Target)

- `strategies/`:
  - one folder per strategy (`nifty_ltp`, `option_chain`, `expiry_strategy`, etc.)
- `core/`:
  - shared broker clients, market data adapters, execution engine, risk checks
- `utils/`:
  - logging, date/time, retries, common helpers
- `config/`:
  - static templates and non-secret defaults
- `runtime/`:
  - logs, outputs, pids, temp runtime files
- `tests/`:
  - unit, integration, and smoke tests
- `context/`:
  - project decisions, runbooks, migration notes, session context

### Environment Management Standard

- Use one project-level `.venv` per repo clone.
- Never use global packages for this project.
- Pin dependencies for reproducibility (move toward `requirements/base.txt` + `requirements/dev.txt`).
- Keep VS Code interpreter fixed to `${workspaceFolder}\\.venv\\Scripts\\python.exe`.

### Cross-Laptop Parity Rules (Very Important)

Both laptops/projects must follow the same standards:

- Same Python major/minor version (currently `3.12.x`).
- Same folder conventions.
- Same dependency pinning policy.
- Same `.env.example` format and env variable names.
- Same logging format and timestamp policy.
- Same test command contracts.
- Same deployment checklist.

When porting changes to the other laptop/repo, include:

- architecture changes
- config schema updates
- dependency version updates
- runbook updates
- risk-control updates

### Security and Secrets Policy

- Never commit secrets, tokens, account identifiers, or private keys.
- Keep credentials only in environment variables or local ignored files.
- Add secret scanning in CI as project matures.
- Rotate API credentials periodically and after any incident.

### Real-Money Risk Controls (Must-Have Before Full Automation)

- Hard max loss per day.
- Hard max position size per symbol and strategy.
- Max orders per minute guardrail.
- Kill-switch flag (manual + automatic).
- Broker/connection health checks before order placement.
- Circuit breaker when price/feed anomalies are detected.
- Full audit logs for signals, orders, responses, and rejections.

### Quality Gates for Every Enhancement

- Unit tests for new logic.
- Integration test for strategy flow where feasible.
- No secret leakage.
- Lint/type checks (add progressively).
- Backward-compatible config migrations.
- Update `context/session_context.md` and `README.md` when behavior changes.

### VPS Deployment Standard

- Fresh clone on VPS.
- Create `.venv`.
- Install pinned requirements.
- Set environment variables from secure source.
- Run as managed service (`systemd`/supervisor), not manual terminal.
- Enable log rotation and restart policy.
- Use paper/sandbox mode before live mode.

### Release Progression Plan

1. Local dev + unit tests.
2. Paper-trading/simulated mode.
3. Small-capital controlled live mode.
4. Gradual scale-up with strict monitoring.

No direct jump to full live deployment.

### Operational Runbook (Minimum)

- Startup checklist:
  - environment selected
  - credentials loaded
  - broker connectivity check
  - market data stream check
- Runtime checklist:
  - heartbeat logs present
  - signal/order latency within threshold
  - no risk limits breached
- Shutdown checklist:
  - graceful stop
  - open position reconciliation
  - log archival

### Recommended Next Enhancements (Priority Order)

1. Introduce `.env.example` and centralized env loader.
2. Add risk module in `core/risk` with hard limits.
3. Add structured logging (JSON optional) and correlation IDs.
4. Add CI pipeline (tests + lint + basic security checks).
5. Add deployment scripts for VPS bootstrap and service start.
6. Add strategy interface contract so all strategies run uniformly.
7. Add healthcheck endpoint/heartbeat writer for monitoring.

### Missing/Gap Checklist (Track Here)

- [ ] CI workflow configured
- [ ] Secret scanning configured
- [ ] Risk guardrails implemented
- [ ] Service manager config (`systemd`/equivalent) committed
- [ ] Backtest data handling policy documented
- [ ] Incident recovery playbook documented
- [ ] Automated alerting (Telegram/Email) integrated for failures

### Decision Rule for Future Changes

When unsure, choose the option that improves:

1. safety (capital protection),
2. reproducibility (same behavior across machines),
3. observability (clear logs/metrics),
4. simplicity (lowest complexity that works),
5. scalability (supports multiple strategies without rewrite).

## Cross-Agent Coordination

- For transferring this project to another AI agent/laptop, use:
  - `context/agent_handoff_playbook.md`
- That file contains:
  - exact alignment rules
  - setup commands
  - validation checklist
  - copy-paste prompt for the other agent

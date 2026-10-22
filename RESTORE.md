# Desk snapshot — restore notes

This branch is a **read-only backup** of a live Zerodha Kavach2 desk.
Live servers were not modified when this snapshot was taken.

## What is included

- `/home/ubuntu/rahul_Changes` (Kavach2 / `run_kavach2.py`)
- `/home/ubuntu/Datafeedbot` + `Datafeedbot_Runtime`
- `/home/ubuntu/Trading_Runtime_Rahul` (runtime data + config layout)
- `vps-health-bot` when present
- systemd unit files under `systemd/`
- `crontab.txt` when present

## What is not included (on purpose)

- Python `.venv` (recreate with `python3 -m venv` + `requirements.txt`)
- Log files (`Logs/`)
- Nested `.git` history
- `ssd_backtest/` and `backtest_engine/` (large, not required to trade)
- **Live broker tokens / JWTs / API secrets** — files are kept, values cleared.
  Fill `Trading_Runtime_Rahul/Credentials` and feeder token files for the **new** user.

## Restore onto a new Ubuntu box

1. Copy trees into place:
   `sudo rsync -a home/ubuntu/ /home/ubuntu/`
2. Recreate venvs for `rahul_Changes` and `Datafeedbot`.
3. Install units: `sudo cp systemd/*.service /etc/systemd/system/ && sudo systemctl daemon-reload`
4. Paste that user's Zerodha/Dhan tokens. Do **not** reuse another desk's tokens.
5. Whitelist the new box public IPv4 on that user's Kite/Dhan app. Force IPv4 if needed.
6. Start `datafeedbot` then `batman-kavach2`. Confirm paper/live mode before trading.

Do not start live trading until tokens, IP whitelist, and lots are confirmed for the new user.

# Incident Fix Verification — 2026-08-06 14:21:21 IST

**Result: FAIL**
- Code/runtime checks: 34/35
- pytest subset: PASS

## Failed checks

- **INC-2026-018** — runtime: log_runtime_root mode-aware: mode=uat log_root=uat runtime=/home/ubuntu/Trading_Runtime_Rahul/Logs/uat/runtime

## All checks

- [PASS] `INC-2026-STAB-01` UAT state path for algo pause — core/algo_control.py
- [PASS] `INC-2026-STAB-02` KAVACH reads mode-aware pause state — bat_telegram/bots/kavach/bot.py
- [PASS] `INC-2026-STAB-03` Failover persisted to disk state — core/nifty_ltp_failover.py
- [PASS] `INC-2026-STAB-04` WS Previous Close skipped — core/dhan_ws_tick.py
- [PASS] `INC-2026-STAB-05` 429 cooldown without failure escalation — core/nifty_ltp_websocket_feed.py
- [PASS] `INC-2026-STAB-06` Transport grace + rate-limit stale skip — core/nifty_ltp_feed.py
- [PASS] `INC-2026-STAB-07` JWT effective expiry gates feed — core/token_store.py
- [PASS] `INC-2026-STAB-08` Lifecycle lock hardening — core/bot_lifecycle.py
- [PASS] `INC-2026-STAB-09` Auth errors no failover — core/nifty_ltp.py
- [PASS] `INC-2026-STAB-10` KAVACH token_watch lazy bootstrap — core/token_watch.py
- [PASS] `INC-2026-STAB-11` Start All aborts on LTP gate fail — core/bot_supervisor.py
- [PASS] `INC-2026-STAB-12` health.json confirms RUNNING — core/bot_health.py
- [PASS] `INC-2026-STAB-13` WS retry after REST lock — core/nifty_ltp_failover.py
- [PASS] `INC-2026-STAB-14` Live price prefers background cache — bat_telegram/bots/drishti/nifty_feed_integration.py
- [PASS] `INC-2026-STAB-15` Lock retry on state writes — core/process_lock.py
- [PASS] `INC-2026-STAB-15` state.save mkdir parent — core/state.py
- [PASS] `INC-2026-016` Fixture expiry auto-roll — backtest_engine/resolver/instrument_master.py
- [PASS] `INC-2026-016` ShadowBroker ledger clear on roll — backtest_engine/shadow/shadow_broker.py
- [PASS] `INC-2026-017` WS transport grace on connect — core/nifty_ltp_websocket_feed.py
- [PASS] `INC-2026-018` diagnose_robot mode-aware logs — scripts/diagnose_robot.py
- [PASS] `INC-2026-019` Ledger clear tied to expiry roll — backtest_engine/shadow/shadow_broker.py
- [PASS] `INC-2026-020` UAT E2E session-scoped log scan — core/runtime_log_scan.py
- [PASS] `INC-2026-021` Feed stabilization reduces alert storm — core/feed_recovery.py
- [PASS] `INC-2026-022` No instant resume on stale_cleared — bat_telegram/bots/drishti/nifty_feed_integration.py
- [PASS] `INC-2026-022` Sustained auto-resume in watchdog — bat_telegram/bots/drishti/nifty_feed_integration.py
- [PASS] `INC-2026-023` Cache replace races do not raise feed-task-killing exceptions — core/nifty_ltp_feed.py
- [PASS] `INC-2026-023` Regression tests cover cache replace lock handling — tests/test_nifty_ltp_feed.py
- [PASS] `INC-2026-016` runtime: fixture rolls past 2026-06-23 — expiry=2026-08-11 rolled=True
- [PASS] `INC-2026-022` runtime: sustained resume blocks <45s — blocked=True stable_s=45
- [PASS] `INC-2026-023` runtime: transient cache lock retries then succeeds — ok=True attempts=3 cache_exists=True
- [PASS] `INC-2026-023` runtime: persistent cache lock returns False without raise — ok=False
- [PASS] `INC-2026-017` runtime: transport grace 30s active — within_grace=True
- [FAIL] `INC-2026-018` runtime: log_runtime_root mode-aware — mode=uat log_root=uat runtime=/home/ubuntu/Trading_Runtime_Rahul/Logs/uat/runtime
- [PASS] `INC-2026-STAB-04` runtime: Previous Close skipped — {'type': 'Previous Close', 'ltp': 0}
- [PASS] `INC-2026-STAB-01` runtime: default_state_path UAT — /home/ubuntu/Trading_Runtime_Rahul/Data/data/uat/batman_state.json
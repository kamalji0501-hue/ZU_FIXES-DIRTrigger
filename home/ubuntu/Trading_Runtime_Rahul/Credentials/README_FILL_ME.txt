Fill for this desk before Live trading:
1) zerodha/zerodha.env + kite_session.json (or paste token in UI TOKEN page)
2) config/.env / order_broker.env as needed (DHAN_CLIENT_CODE etc.)
3) Datafeedbot_Runtime/Credentials dhan.env + zerodha.env for market feed
4) Whitelist this server public IPv4 on Dhan API app; force IPv4 already set
5) Add Google Licenses sheet row with Server ID = http://65.2.152.185:8789/
   then set SUBSCRIPTION_SOURCE=apps_script and refresh
6) Optional: telegram bots.env; remove KAVACH2_TELEGRAM_DISABLED

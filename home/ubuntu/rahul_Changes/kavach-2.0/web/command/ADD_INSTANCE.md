# Command Center — Licenses API driven cards

Command Center builds cards from the **Licenses** Google Sheet via your subscription API.

## How cards appear

1. Poll: `GET {SUBSCRIPTION_API_URL}?action=list&api_key=...`
2. Each sheet row with a **Server ID** becomes one card, in **sheet row order** (1, 2, 3…).
3. New user on the sheet → new card on the next poll (~30s). No manual registry edit.
4. Authorization (lots / dates / status) comes from the sheet.
5. Health + Day PnL come from each desk’s `/api/fleet/desk-snapshot` when reachable.

## One-time: redeploy Apps Script with `action=list`

Paste updated `subscription_delivery/apps_script/Code.gs` into the Apps Script project, then:

**Deploy → Manage deployments → Edit (pencil) → Version: New version → Deploy**

Test:

```bash
curl -sL "$SUBSCRIPTION_API_URL?action=list&api_key=$SUBSCRIPTION_API_KEY" | head
```

Expect: `{"ok":true,"subscriptions":[...]}` in sheet order.

## Optional overrides (copy keys / local)

File: `Trading_Runtime_Rahul/Data/data/shared/command/instance_registry.json`

Only needed for per-desk copy keys or to mark the Command Center host as `local`.  
Card order and names always come from the Licenses API when `action=list` works.

## UI

`http://<command-host>:8789/command`  
Password: same as KD fleet (`KAVACH_FLEET_PASSWORD`).

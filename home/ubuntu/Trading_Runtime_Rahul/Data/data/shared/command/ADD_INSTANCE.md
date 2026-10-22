# Command Center — add an instance

Registry file (on Command Center host):

`Trading_Runtime_Rahul/Data/data/shared/command/instance_registry.json`

## Fields per instance

```json
{
  "id": "inst-name",
  "label": "Display Name",
  "slot": 3,
  "base_url": "http://x.x.x.x:8789",
  "copy_key_env": "FLEET_COPY_KEY_NAME",
  "aws_account": "aws-tag",
  "server_tag": "SRV3",
  "link_type": "public",
  "local": false,
  "enabled": true
}
```

- `slot`: 1–10 (UI position). Slots 8–10 stay empty placeholders by default.
- `local: true` only for the desk running on the Command Center host itself.
- Put the shared copy key in `Credentials/web/kavach_fleet.env` as `FLEET_COPY_KEY_…=…`
- Child desks must already expose `/api/fleet/desk-snapshot` (same as KD fleet).

## Poll load

- State poll ~30s, margin ~300s (see `poll` in registry).
- Monitor-only — no order punches from Command Center.

## UI

Open: `http://<command-host>:8789/command`  
Login: same password as KD Command Center (`KAVACH_FLEET_PASSWORD`).

# Run this desk on a private IP

Branch `CHILD` is the Aman / child code (`13.206.80.173`). The app does not need a static public IP.

Kavach already binds `0.0.0.0:8789` (`KAVACH_WEB_HOST` / `KAVACH_WEB_PORT`). On a new Ubuntu server that means it answers on the instance private IPv4 as soon as the service is up.

The private IPv4 stays for the life of the EC2 instance. The public IPv4 changes every time the instance stops and starts, unless you attach an Elastic IP. Do not put the public IPv4 in the subscription sheet.

## Do not touch the live desks

Aman (`13.206.80.173`) and Anand (`3.6.138.217`) have live positions.

- Do not stop, restart, or reload their services.
- Do not punch, modify, or cancel orders.
- Do not copy their broker credentials, tokens, or `.env` files onto the new server.

## 1. Put the code on the new server

On the new box, as `ubuntu`:

```bash
git clone --branch CHILD --single-branch git@github.com:iwai-0310/master.git /tmp/desk
sudo rsync -a --exclude .git /tmp/desk/ /home/ubuntu/
sudo chown -R ubuntu:ubuntu /home/ubuntu
```

This machine's deploy key for that repo is `~/.ssh/github_new_repo_deploy` (SSH host `github-new-repo`). The new server needs its own deploy key, or clone via a bundle copied over SSH. This key is already used by another machine, and GitHub allows a deploy key on one repo only, so do not copy this private key onto the new server if this laptop must keep push access. Prefer:

```bash
# from this laptop, after you can SSH to the new server
rsync -a --exclude .git /path/to/clone/ ubuntu@NEW:/tmp/desk/
```

## 2. Private IP

On the new server:

```bash
hostname -I | awk '{print $1}'
```

That address is the desk address. Example URL:

```text
http://<private-ip>:8789/
```

Security group:

- TCP 22 from your admin IP only (SSH).
- TCP 8789 from the VPC CIDR only (for example `172.31.0.0/16`), not from `0.0.0.0/0`.

The private IP is not reachable from a home laptop. Open the UI through an SSH tunnel:

```bash
ssh -i /path/to/new-server.pem -L 8789:127.0.0.1:8789 ubuntu@<ssh-target>
```

Then browse to `http://127.0.0.1:8789/`.

If the instance has no public IP at all, use the same tunnel through a bastion, or AWS Systems Manager port forwarding. Do not allocate an Elastic IP unless you decide you want a stable public URL.

## 3. Python venvs

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip
python3 -m venv /home/ubuntu/rahul_Changes/.venv
/home/ubuntu/rahul_Changes/.venv/bin/pip install -r /home/ubuntu/rahul_Changes/requirements.txt
python3 -m venv /home/ubuntu/Datafeedbot/.venv
/home/ubuntu/Datafeedbot/.venv/bin/pip install -r /home/ubuntu/Datafeedbot/requirements.txt
python3 -m venv /home/ubuntu/vps-health-bot/.venv
/home/ubuntu/vps-health-bot/.venv/bin/pip install -r /home/ubuntu/vps-health-bot/requirements.txt
```

## 4. Services, same set as Aman

Aman runs `datafeedbot`, `batman-kavach2`, and `vps-health-bot`. Drishti stays off.

Unit files are in `deploy/systemd/`. They bind the web desk to `0.0.0.0:8789`, so the private IP works with no code change.

```bash
sudo cp /home/ubuntu/deploy/systemd/datafeedbot.service /etc/systemd/system/
sudo cp /home/ubuntu/deploy/systemd/batman-kavach2.service /etc/systemd/system/
sudo mkdir -p /etc/systemd/system/batman-kavach2.service.d
sudo cp /home/ubuntu/deploy/systemd/batman-kavach2.service.d/override.conf /etc/systemd/system/batman-kavach2.service.d/
sudo cp /home/ubuntu/deploy/systemd/vps-health-bot.service /etc/systemd/system/
sudo mkdir -p /home/ubuntu/VPSHealth_Runtime/Data/vps_health
sudo systemctl daemon-reload
sudo systemctl enable --now datafeedbot.service batman-kavach2.service vps-health-bot.service
systemctl is-active datafeedbot.service batman-kavach2.service vps-health-bot.service
```

Check the listener:

```bash
ss -lnt | grep 8789
```

You want `0.0.0.0:8789`.

## 5. Credentials and the sheet

Create these on the new server only, for the new user:

- `Trading_Runtime_Rahul/Credentials/`
- `Datafeedbot_Runtime/Credentials/`
- `Trading_Runtime_Rahul/Credentials/subscription/subscription.env`

`ALGO_SERVER_ID` must be the private-IP URL, with the same text you put in the Google sheet `server_id` column:

```text
ALGO_SERVER_ID=http://<private-ip>:8789/
SUBSCRIPTION_SOURCE=apps_script
```

Also set `SUBSCRIPTION_API_URL` and `SUBSCRIPTION_API_KEY` for the sheet. A trailing slash is fine; the checker strips one trailing slash.

Until that row exists and a refresh succeeds, the UI can show Direction and Batman with empty lots.

## 6. Confirm, and stop there

- Services active on the new server only.
- UI loads through the SSH tunnel.
- No order was sent.
- Aman and Anand services were not restarted.

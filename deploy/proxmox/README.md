# CarCatcher — Proxmox deployment

Matches the homelab convention: an unprivileged Debian **LXC** with Docker Compose
inside, exposed via the shared **nginx (LXC 111)** + **Cloudflare Tunnel** at
`carcatcher.jurtin.de`. SQLite lives on an NFS bind-mount; a host-side systemd
watchdog reboots the container if `/api/health` fails.

## 1. Create the LXC
Unprivileged Debian 12 LXC (e.g. CT 113), 2 GB RAM / 12 GB disk, DHCP on
`192.168.178.0/24`. Install Docker + compose plugin inside it. Note its IP.

## 2. NFS data mount
Bind-mount host storage to the container's `/data` (same model as lunch-planner's
`/mnt/lunch-planner` → `/data`). Set `DATA_DIR` in `.env` to the host path. The DB
ends up at `/data/db/carcatcher.db`; backups at `/data/backups`.

## 3. Deploy the app
```bash
pct enter 113
cd /app && git pull            # or rsync the repo to /app
cp .env.example .env           # then edit real secrets
docker compose up --build -d
```

## 4. Expose via Cloudflare + nginx (on LXC 111)
1. Cloudflare Zero Trust → add ingress: `carcatcher.jurtin.de` →
   `http://<carcatcher-lxc-ip>:8080`.
2. Add DNS CNAME `carcatcher.jurtin.de → <tunnel-id>.cfargotunnel.com`.
3. Add an nginx vhost on LXC 111 proxying `carcatcher.jurtin.de` →
   `http://<carcatcher-lxc-ip>:8080`; `nginx -t` && `systemctl reload nginx`.
4. `systemctl restart cloudflared` on LXC 111.

## 5. DB backup (inside the LXC)
```bash
install -m 755 deploy/proxmox/carcatcher-backup.sh /usr/local/bin/
( crontab -l 2>/dev/null; \
  echo "0 3 * * * DATABASE_PATH=/data/db/carcatcher.db /usr/local/bin/carcatcher-backup.sh >> /data/backups/backup.log 2>&1" ) | crontab -
```

## 6. Watchdog (on the Proxmox host)
```bash
install -m 755 deploy/proxmox/carcatcher-watchdog.sh /usr/local/bin/
cp deploy/proxmox/carcatcher-watchdog.service /etc/systemd/system/
cp deploy/proxmox/carcatcher-watchdog.timer   /etc/systemd/system/
# edit CTID / health URL in the .service first
systemctl daemon-reload
systemctl enable --now carcatcher-watchdog.timer
```

The watchdog curls `http://<lxc-ip>:8080/api/health`; on 3 consecutive failures it
runs `mount -a`, `pct reboot <CTID>`, and emails `kai@jurtin.de`.

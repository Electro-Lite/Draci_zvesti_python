# Draci Zvesti systemd services

These system units run the protected download website and online WebSocket
relay as the `electro` user. Both services bind only to `127.0.0.1`; Cloudflare
Tunnel provides their public HTTPS/WSS endpoints.

## Install

From the repository root:

Stop any manually started website or relay process first so ports 4173 and
47888 aren't already occupied. Then install the units:

```bash
sudo install -m 0644 deploy/systemd/draci-zvesti-web.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/draci-zvesti-online.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/draci-zvesti.target /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now draci-zvesti.target
```

If the repository moves or the account name changes, update `User`, `Group`,
`WorkingDirectory`, `ExecStart`, and `Documentation` before installation.

## Operate

```bash
systemctl status draci-zvesti-web.service draci-zvesti-online.service
journalctl -u draci-zvesti-web.service -u draci-zvesti-online.service -f
sudo systemctl restart draci-zvesti.target
sudo systemctl stop draci-zvesti.target
```

After changing Python code, restart the online service. Static website files
are read on each request and normally don't require a restart.

The tunnel itself remains a separate `cloudflared.service`. Its ingress rules
must map `/game` to `http://127.0.0.1:47888` before mapping the hostname
catch-all to `http://127.0.0.1:4173`.

# Online lobby server

The online mode uses a small WebSocket relay. The server owns lobby discovery and
forwards traffic between two players; game rules remain authoritative on the
lobby host's client.

## Configure clients

Set `Config.lobby_server_url` in `config.py` to the public `wss://` endpoint.
The production default is `wss://draci-zvesti.kluck.uk/game`. Rebuild packaged
clients after changing it.

## Run the server

From the repository root:

```bash
python -m py_game.network.online_server \
  --host 127.0.0.1 \
  --port 47888 \
  --max-clients 200 \
  --max-lobbies 100
```

The relay uses no
game databases or image assets and keeps all lobbies in memory, so restarting
it closes current lobbies and matches.

Lobby passwords are salted and hashed in server memory and are never returned
in lobby listings. Cloudflare terminates public TLS; the relay listens only on
loopback and receives the private HTTP/WebSocket hop from `cloudflared`.

## Cloudflare Tunnel

Run the static download page on port 4173 and the relay on port 47888. Route the
WebSocket path before the website catch-all:

```yaml
ingress:
  - hostname: draci-zvesti.kluck.uk
    path: ^/game(?:/.*)?$
    service: http://127.0.0.1:47888

  - hostname: draci-zvesti.kluck.uk
    service: http://127.0.0.1:4173

  - service: http_status:404
```

Both origin services intentionally use `http://`. The public endpoints remain
`https://` and `wss://` because Cloudflare performs TLS termination. Configuring
either origin as `https://` sends a TLS handshake to a plain HTTP/WebSocket
server and produces Python `Bad request version` messages.

Validate and restart the tunnel after changing its configuration:

```bash
cloudflared tunnel ingress validate
sudo systemctl restart cloudflared
```

For a local relay test, temporarily set:

```python
Config.lobby_server_url = "ws://127.0.0.1:47888/game"
```

# Online lobby server

The online mode uses one WebSocket service for native and browser clients. A
native-created lobby retains the lightweight relay model, with game rules
authoritative on the native host. A browser-created lobby is server-authoritative:
the server reconstructs both submitted decks from trusted card definitions,
runs the existing Python rules engine, validates choices, and emits a separate
private state snapshot for each player.

The browser client is served from the password-protected `/play/` path and uses
the password-protected `/browser-game` WebSocket endpoint. Its decks live in
browser storage; there are no browser accounts and no AI or training
functionality. Native clients continue to use `/game`.

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

The service keeps lobbies and active matches in memory, so restarting it closes
current lobbies and matches. Browser-hosted games read trusted card definitions
from `utils/cards.db`; submitted clients cannot override card stats or abilities.

Browser matches use resumable session tokens stored by the browser. A dropped
transport pauses the match without consuming the active choice timeout. The
server waits 10 seconds before reporting the player as disconnected, keeps the
match available for reconnection, and replays the private state and pending
choice after the player returns. The connected opponent may keep waiting or
explicitly end the match. Restarting the service still invalidates these
in-memory sessions.

Lobby passwords are salted and hashed in server memory and are never returned
in lobby listings. Cloudflare terminates public TLS; the relay listens only on
loopback and receives the private HTTP/WebSocket hop from `cloudflared`.

## Cloudflare Tunnel

Run the static download page on port 4173 and the relay on port 47888. Route
Cloudflare to Caddy on port 4173; Caddy authenticates and proxies
`/browser-game`, while `/game` remains the lightweight native-client relay:

```yaml
ingress:
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

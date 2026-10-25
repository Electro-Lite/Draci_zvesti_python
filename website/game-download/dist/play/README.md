# Browser arena

This buildless frontend provides local deck management and human-only online
play. Decks are stored in the browser; the server reconstructs every submitted
deck from authoritative card IDs and validates every game choice.

Regenerate `catalog.json` after changing `utils/cards.db`, starter decks, or
ability descriptions:

```bash
python website/game-download/tools/build-browser-catalog.py
```

`cards` is a repository-relative symlink to `cards/card_images`. The production
static server must preserve and follow that symlink. The existing Caddy setup
does so and serves this directory at `/play/` because it lives below the
download site's static root.

Production protects both `/play` and the same-origin `/browser-game` WebSocket
with HTTP Basic Authentication. The browser does not store the shared access
password in application storage.

No AI models, training artifacts, training controls, or opponent-private state
are shipped to the browser.

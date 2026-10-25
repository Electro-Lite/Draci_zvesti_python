const PROTOCOL_VERSION = 2;
const APPLICATION_VERSION = "1.0";
const STORAGE_KEY = "draci-zvesti-browser-decks-v1";
const NAME_KEY = "draci-zvesti-browser-name";
const RESUME_TOKEN_KEY = "draci-zvesti-browser-session-v1";
const COLORS = { BLACK: "#9d8fc7", BLUE: "#62a9e8", GREEN: "#54c789", RED: "#ee6d71" };

const state = {
  catalog: [], cards: new Map(), decks: [], activeDeckId: null,
  socket: null, sequence: 0, connected: false, role: null,
  lobbies: [], onlineLobby: null, lobbyState: null, serverStatus: null,
  matchId: null, game: null, request: null, pendingDrop: null,
  pingSent: null, latency: null, interruptionReason: "",
  connectionWaitReason: "", connectionWaitKind: "", waitingAcknowledged: false,
  reconnectTimer: null, connectionLossTimer: null, reconnectAttempts: 0,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function toast(message) {
  const element = $("#toast"); element.textContent = message; element.classList.add("show");
  clearTimeout(toast.timer); toast.timer = setTimeout(() => element.classList.remove("show"), 3200);
}

function safeText(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character],
  );
}
function uid() { return `web_${Date.now().toString(36)}_${crypto.randomUUID().slice(0, 8)}`; }
function activeDeck() { return state.decks.find((deck) => deck.id === state.activeDeckId) || null; }
function cardById(id) { return state.cards.get(id); }
function thumbnailSource(card) { return card?.thumbnail || card?.image || ""; }
function detailSource(card) { return card?.image || card?.thumbnail || ""; }

function preloadCardThumbnails(cards) {
  const load = () => cards.filter((card) => card.type === "PLAYER").forEach((card) => {
    const source = thumbnailSource(card); if (!source) return;
    const image = new Image(); image.decoding = "async"; image.src = encodeURI(source);
  });
  if ("requestIdleCallback" in window) requestIdleCallback(load, { timeout: 1200 }); else setTimeout(load, 0);
}

function deckError(deck) {
  if (!deck) return "Select a deck";
  if (deck.cardIds.length < 10 || deck.cardIds.length > 12) return "Deck must contain 10–12 cards";
  const counts = new Map();
  for (const id of deck.cardIds) {
    const card = cardById(id); if (!card || card.type !== "PLAYER") return `Unknown card: ${id}`;
    counts.set(id, (counts.get(id) || 0) + 1);
    const limit = card.power === 2 ? 1 : 4;
    if (counts.get(id) > limit) return `${card.name} allows at most ${limit} ${limit === 1 ? "copy" : "copies"}`;
  }
  return "";
}

function saveDecks() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.decks));
  renderDecks(); renderOnlineDecks();
}

function loadDecks(presets) {
  try { state.decks = JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; } catch { state.decks = []; }
  state.decks = state.decks.filter((deck) => deck && typeof deck.id === "string" && Array.isArray(deck.cardIds));
  if (!state.decks.length) state.decks = presets.map((deck) => ({ ...deck, id: uid() }));
  state.activeDeckId = state.decks[0]?.id || null;
  saveDecks();
}

function deckDescriptor(deck) {
  const error = deckError(deck); if (error) throw new Error(error);
  return { deck_id: deck.id, deck_name: deck.name.trim() || "Browser deck", card_ids: [...deck.cardIds] };
}

function renderDecks() {
  const list = $("#deck-list"); list.replaceChildren();
  for (const deck of state.decks) {
    const button = document.createElement("button"); button.textContent = `${deck.name || "Unnamed deck"} · ${deck.cardIds.length}`;
    button.classList.toggle("active", deck.id === state.activeDeckId);
    button.onclick = () => { state.activeDeckId = deck.id; renderDecks(); renderOnlineDecks(); };
    list.append(button);
  }
  const deck = activeDeck();
  $("#deck-name").value = deck?.name || ""; $("#deck-name").disabled = !deck;
  $("#deck-count").textContent = `${deck?.cardIds.length || 0}/12`;
  const error = deckError(deck); const status = $("#deck-validation");
  status.textContent = error || "Ready for online play"; status.className = `status-line ${error ? "bad" : "good"}`;
  const container = $("#deck-cards"); container.replaceChildren();
  if (deck) {
    const counts = new Map(); deck.cardIds.forEach((id) => counts.set(id, (counts.get(id) || 0) + 1));
    for (const [id, count] of counts) {
      const card = cardById(id); if (!card) continue;
      const line = document.createElement("div"); line.className = "deck-line";
      line.innerHTML = `<span>${safeText(card.name)}</span><strong>×${count}</strong>`;
      const remove = document.createElement("button"); remove.className = "danger"; remove.textContent = "−";
      remove.onclick = () => { deck.cardIds.splice(deck.cardIds.lastIndexOf(id), 1); saveDecks(); };
      line.append(remove); container.append(line);
    }
  }
  renderCatalog();
}

function renderCatalog() {
  const search = $("#card-search").value.trim().toLocaleLowerCase(); const color = $("#color-filter").value;
  const grid = $("#card-grid"); grid.replaceChildren();
  for (const card of state.catalog.filter((item) => item.type === "PLAYER" && (!color || item.color === color) && (!search || `${item.name} ${item.ability.name} ${item.ability.description}`.toLocaleLowerCase().includes(search)))) {
    const tile = document.createElement("button"); tile.className = "card-tile"; tile.style.setProperty("--card-color", COLORS[card.color]);
    const thumbnail = thumbnailSource(card);
    tile.innerHTML = `${thumbnail ? `<img src="${encodeURI(thumbnail)}" alt="" loading="lazy" decoding="async">` : ""}<strong>${safeText(card.name)}</strong><span>${card.dmg} ATK · ${card.hp} HP · ${safeText(card.color)}</span><span>${safeText(card.ability.name)}</span>`;
    tile.onclick = () => {
      const deck = activeDeck(); if (!deck) return;
      if (deck.cardIds.length >= 12) return toast("Deck already has 12 cards");
      const count = deck.cardIds.filter((id) => id === card.id).length; const limit = card.power === 2 ? 1 : 4;
      if (count >= limit) return toast(`${card.name} allows at most ${limit} ${limit === 1 ? "copy" : "copies"}`);
      deck.cardIds.push(card.id); saveDecks();
    };
    tile.oncontextmenu = (event) => { event.preventDefault(); showCard(card); };
    grid.append(tile);
  }
}

function showCard(card) {
  if (!card) return; const dialog = $("#card-dialog");
  const source = detailSource(card); const image = dialog.querySelector("img"); image.src = source ? encodeURI(source) : ""; image.alt = card.name;
  dialog.querySelector("h2").textContent = card.name;
  dialog.querySelector(".card-stats").textContent = `${card.dmg} attack · ${card.hp} health · ${card.color}`;
  dialog.querySelector("h3").textContent = card.ability?.name || card.ability_name || "";
  dialog.querySelector(".ability-description").textContent = card.ability?.description || card.ability_description || "";
  dialog.showModal();
}

function switchView(view) {
  document.body.dataset.view = view;
  $$(".view").forEach((element) => element.classList.toggle("active", element.id === `${view}-view`));
  $$(".nav-button").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  if (view !== "match") delete document.body.dataset.mana;
  if (view === "online" && !state.connected && state.socket?.readyState !== WebSocket.CONNECTING) connect();
}

function renderOnlineDecks() {
  const select = $("#online-deck"); const previous = select.value; select.replaceChildren();
  for (const deck of state.decks) {
    const option = document.createElement("option"); option.value = deck.id; option.textContent = `${deck.name} (${deck.cardIds.length})${deckError(deck) ? " — invalid" : ""}`; option.disabled = Boolean(deckError(deck)); select.append(option);
  }
  select.value = state.decks.some((deck) => deck.id === previous && !deckError(deck)) ? previous : (state.decks.find((deck) => !deckError(deck))?.id || "");
}

function selectedOnlineDeck() { return state.decks.find((deck) => deck.id === $("#online-deck").value); }
function websocketUrl() { return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/browser-game`; }

function setConnection(label, kind) { const pill = $("#connection-pill"); pill.textContent = label; pill.className = `pill ${kind}`; }

function encodeMessage(message) {
  const body = new TextEncoder().encode(JSON.stringify(message)); const framed = new Uint8Array(body.length + 4); const view = new DataView(framed.buffer); view.setUint32(0, body.length, false); framed.set(body, 4); return framed;
}

function send(type, payload = {}, metadata = {}) {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) throw new Error("Online server is not connected");
  state.socket.send(encodeMessage({ type, sequence: state.sequence++, request_id: metadata.requestId || null, match_id: metadata.matchId || null, payload, protocol_version: PROTOCOL_VERSION, application_version: APPLICATION_VERSION }));
}

function decodeMessages(buffer) {
  const bytes = new Uint8Array(buffer); const view = new DataView(buffer); const messages = []; let offset = 0;
  while (offset + 4 <= bytes.length) { const size = view.getUint32(offset, false); offset += 4; if (size <= 0 || offset + size > bytes.length) throw new Error("Invalid server frame"); messages.push(JSON.parse(new TextDecoder().decode(bytes.slice(offset, offset + size)))); offset += size; }
  if (offset !== bytes.length) throw new Error("Incomplete server frame"); return messages;
}

function connect() {
  if (state.socket?.readyState === WebSocket.OPEN || state.socket?.readyState === WebSocket.CONNECTING) return;
  const name = $("#player-name").value.trim(); if (!name) return toast("Enter a player name");
  localStorage.setItem(NAME_KEY, name); state.sequence = 0; setConnection("Connecting", "connecting"); $("#online-status").textContent = "Connecting to the arena…";
  const socket = new WebSocket(websocketUrl()); state.socket = socket; socket.binaryType = "arraybuffer";
  socket.onopen = () => send("online_hello", { player_name: name, application_version: APPLICATION_VERSION, client_kind: "web", resume_token: localStorage.getItem(RESUME_TOKEN_KEY) || "" }, { requestId: crypto.randomUUID() });
  socket.onmessage = (event) => { try { decodeMessages(event.data).forEach(handleMessage); } catch (error) { toast(error.message); } };
  socket.onclose = () => {
    if (state.socket !== socket) return;
    state.socket = null; state.connected = false; state.pingSent = null; setConnection("Reconnecting", "connecting");
    $("#online-status").textContent = "Connection interrupted. Reconnecting…";
    clearTimeout(state.connectionLossTimer);
    state.connectionLossTimer = setTimeout(() => {
      if (state.connected) return;
      state.connectionWaitReason = "Connection lost. Your match is reserved while you reconnect.";
      state.connectionWaitKind = "self"; state.waitingAcknowledged = false;
      if (state.matchId) { switchView("match"); renderMatch(); }
      setConnection("Offline", "offline");
    }, 10000);
    scheduleReconnect(); renderLobbies(); renderRoom();
  };
  socket.onerror = () => socket.close();
}

function scheduleReconnect() {
  clearTimeout(state.reconnectTimer);
  const delay = Math.min(5000, 750 * (2 ** Math.min(state.reconnectAttempts++, 3)));
  state.reconnectTimer = setTimeout(connect, delay);
}

function shareDeck() {
  const deck = selectedOnlineDeck(); send("select_deck", { deck: deckDescriptor(deck) });
}

function handleMessage(message) {
  const payload = message.payload || {};
  if (message.type === "online_welcome") {
    state.connected = true; state.reconnectAttempts = 0; clearTimeout(state.reconnectTimer); clearTimeout(state.connectionLossTimer);
    if (payload.resume_token) localStorage.setItem(RESUME_TOKEN_KEY, payload.resume_token);
    if (!payload.resumed && state.matchId) { state.interruptionReason = "The previous match could not be restored."; state.request = null; }
    if (state.connectionWaitKind === "self") { state.connectionWaitReason = ""; state.connectionWaitKind = ""; state.waitingAcknowledged = false; }
    setConnection(payload.resumed ? "Reconnected" : "Online", "online"); $("#online-status").textContent = payload.resumed ? "Session restored." : "Connected. Create or join a lobby."; send("list_lobbies"); if (state.matchId) renderMatch(); return;
  }
  if (message.type === "server_status") { state.serverStatus = payload; $("#server-load").textContent = `Server ${payload.load || "—"} · ${payload.connected_players ?? 0}/${payload.max_players ?? "—"} players · ${payload.active_matches ?? 0} matches`; return; }
  if (message.type === "lobby_list") { state.lobbies = payload.lobbies || []; renderLobbies(); return; }
  if (message.type === "online_lobby") {
    state.onlineLobby = payload; state.role = payload.role; $("#online-status").textContent = payload.resumed ? "Lobby session restored." : state.role === "host" ? "Lobby created." : "Joined lobby.";
    if (!payload.resumed && state.role === "guest") send("hello", { player_name: $("#player-name").value.trim(), application_version: APPLICATION_VERSION }, { requestId: crypto.randomUUID() });
    else if (!payload.resumed && payload.server_authoritative) { try { shareDeck(); } catch (error) { toast(error.message); } }
    renderRoom(); return;
  }
  if (message.type === "hello_accepted") { state.lobbyState = payload; try { shareDeck(); } catch (error) { toast(error.message); } renderRoom(); return; }
  if (message.type === "lobby_state") { state.lobbyState = payload; renderRoom(); return; }
  if (message.type === "online_lobby_closed") { const reason = payload.reason || "Lobby closed"; state.role = null; state.onlineLobby = null; state.lobbyState = null; if (state.matchId) interruptMatch(reason); else toast(reason); renderRoom(); return; }
  if (message.type === "start_match") { state.matchId = payload.match_id || message.match_id; if (!payload.resumed) { state.game = null; state.request = null; } state.interruptionReason = ""; state.connectionWaitReason = ""; state.connectionWaitKind = ""; switchView("match"); renderMatch(); return; }
  if (message.type === "state_snapshot") { state.game = payload; state.interruptionReason = ""; renderMatch(); return; }
  if (message.type === "choice_request") { state.request = message; state.game = payload.state || state.game; if (payload.choice_type === "position" && state.pendingDrop != null && (payload.legal_indices || []).includes(state.pendingDrop)) { answer(state.pendingDrop); state.pendingDrop = null; } renderMatch(); return; }
  if (message.type === "match_result") { state.game = payload.state || state.game; state.request = null; state.interruptionReason = payload.aborted ? (payload.reason || "Match interrupted") : ""; renderMatch(); toast(state.interruptionReason || "Match finished"); return; }
  if (message.type === "pong") { if (state.pingSent) state.latency = performance.now() - state.pingSent; state.pingSent = null; renderLatency(); return; }
  if (message.type === "disconnect") { const reason = payload.reason || "The other player disconnected."; if (state.matchId) interruptMatch(reason); else toast(reason); return; }
  if (message.type === "peer_connection_status") {
    if (payload.status === "disconnected") { state.connectionWaitReason = "The other player lost connection. Their place is reserved while they reconnect."; state.connectionWaitKind = "peer"; state.waitingAcknowledged = false; switchView("match"); renderMatch(); toast("Opponent disconnected — match paused"); }
    else if (payload.status === "connected") { state.connectionWaitReason = ""; state.connectionWaitKind = ""; state.waitingAcknowledged = false; renderMatch(); toast("Opponent reconnected"); }
    return;
  }
  if (message.type === "error") { toast(payload.message || "Server rejected the request"); return; }
}

function renderLobbies() {
  const list = $("#lobby-list"); list.replaceChildren();
  if (!state.connected) { list.innerHTML = '<p class="muted">Connect to view lobbies.</p>'; return; }
  if (!state.lobbies.length) { list.innerHTML = '<p class="muted">No open lobbies. Create the first one.</p>'; return; }
  for (const lobby of state.lobbies) {
    const row = document.createElement("div"); row.className = "lobby-row"; row.innerHTML = `<div><strong>${safeText(lobby.name)}</strong><p>${lobby.protected ? "Password protected" : "Public"} · host ${safeText(lobby.host_name)}${lobby.server_authoritative ? " · browser ready" : ""}</p></div>`;
    const join = document.createElement("button"); join.textContent = "Join"; join.onclick = () => { let password = ""; if (lobby.protected) { password = prompt("Lobby password") ?? ""; if (!password) return; } send("join_online_lobby", { lobby_id: lobby.lobby_id, password }, { requestId: crypto.randomUUID() }); };
    row.append(join); list.append(row);
  }
}

function renderRoom() {
  const room = $("#lobby-room"); if (!state.role) { room.hidden = true; return; } room.hidden = false;
  const lobby = state.lobbyState || {}; const host = lobby.host || { name: state.onlineLobby?.host_name }; const guest = lobby.guest;
  room.replaceChildren(); room.innerHTML = `<div class="panel-heading"><h2>${safeText(state.onlineLobby?.name || "Online lobby")}</h2><span>${state.onlineLobby?.server_authoritative ? "Server-authoritative match" : "Native host match"}</span></div><div class="room-players"><div class="room-player"><strong>Host · ${safeText(host.name || "—")}</strong><p>${safeText(host.deck_name || "No deck selected")}</p><span>${host.ready ? "Ready" : "Not ready"}</span></div><div class="room-player"><strong>Guest · ${safeText(guest?.name || state.onlineLobby?.guest_name || "Waiting…")}</strong><p>${safeText(guest?.deck_name || "No deck selected")}</p><span>${guest?.ready ? "Ready" : "Not ready"}</span></div></div>`;
  const actions = document.createElement("div"); actions.className = "room-actions";
  const select = document.createElement("button"); select.className = "secondary"; select.textContent = "Share selected deck"; select.onclick = () => { try { shareDeck(); } catch (error) { toast(error.message); } }; actions.append(select);
  const mine = state.role === "host" ? host : guest; const ready = document.createElement("button"); ready.textContent = mine?.ready ? "Unready" : "Ready"; ready.onclick = () => send("ready", { ready: !mine?.ready }); actions.append(ready);
  if (state.role === "host") { const start = document.createElement("button"); start.textContent = "Start match"; start.disabled = !(host.ready && guest?.ready && host.deck_id && guest?.deck_id); start.onclick = () => send("start_match", {}, { matchId: crypto.randomUUID() }); actions.append(start); }
  const leave = document.createElement("button"); leave.className = "danger"; leave.textContent = state.role === "host" ? "Close lobby" : "Leave lobby"; leave.onclick = () => { send("leave_online_lobby"); state.role = null; state.onlineLobby = null; state.lobbyState = null; renderRoom(); }; actions.append(leave); room.append(actions);
}

function snapshotCard(card) {
  if (!card) return null; const catalog = cardById(card.id); return { ...catalog, ...card, ability: { name: card.ability_name || catalog?.ability?.name || "", description: card.ability_description || catalog?.ability?.description || "" }, image: catalog?.image || null, thumbnail: catalog?.thumbnail || catalog?.image || null };
}

function gameCard(card, { index = null, legal = false, opponent = false, battling = false } = {}) {
  const model = snapshotCard(card); const button = document.createElement("button"); button.className = `game-card${legal ? " legal" : ""}${opponent ? " opponent" : ""}${battling ? " battling" : ""}`; button.style.setProperty("--card-color", COLORS[model.color]); button.draggable = legal && index != null;
  const thumbnail = thumbnailSource(model); button.innerHTML = `${thumbnail ? `<img src="${encodeURI(thumbnail)}" alt="" decoding="async">` : ""}${battling ? '<span class="battle-badge">Battling dragon</span>' : ""}<strong>${safeText(model.name)}</strong><div class="numbers"><span>⚔ ${model.dmg}</span><span>♥ ${model.hp}</span></div>`;
  button.onclick = () => legal && index != null ? answer(index) : showCard(model); button.oncontextmenu = (event) => { event.preventDefault(); showCard(model); };
  if (button.draggable) button.ondragstart = (event) => event.dataTransfer.setData("text/plain", String(index)); return button;
}

function renderMatch() {
  const game = state.game; renderLatency(); applyManaTheme(game?.mana);
  const panel = $("#choice-panel"); panel.replaceChildren();
  if (!game) { $("#match-status").textContent = state.interruptionReason || "Waiting for server-authoritative game state…"; if (state.interruptionReason) renderInterruption(panel); return; }
  $("#match-status").textContent = state.interruptionReason ? `Match interrupted · ${state.interruptionReason}` : game.status === "finished" ? `Match finished · ${game.winner === "local" ? "You won" : game.winner === "opponent" ? "Opponent won" : "Draw"}` : `Round ${game.round} · ${game.turn === "local" ? "Your turn" : "Opponent's turn"} · ${game.mana || "no"} mana`;
  $("#local-stats").textContent = `You · ${game.local.score} points · ${game.local.deck_count} deck · ${game.local.graveyard_count} discarded`;
  $("#opponent-stats").textContent = `Opponent · ${game.opponent.score} points · ${game.opponent.hand_count} hand · ${game.opponent.deck_count} deck · ${game.opponent.graveyard_count} discarded`;
  const dragon = $("#dragon-panel"); dragon.replaceChildren(); if (game.dragon) { const model = snapshotCard(game.dragon); const thumbnail = thumbnailSource(model); const wrap = document.createElement("div"); wrap.className = `dragon-card${game.battle ? " battling" : ""}`; wrap.innerHTML = `${thumbnail ? `<img src="${encodeURI(thumbnail)}" alt="" decoding="async">` : ""}<div><strong>${safeText(model.name)}</strong><p>${model.dmg} attack · ${model.hp} health</p></div>`; dragon.append(wrap); }
  const choice = state.request?.payload?.choice_type; const legal = new Set(state.request?.payload?.legal_indices || []); const board = $("#board"); board.replaceChildren();
  game.board.forEach((card, index) => { const battling = game.battle?.slot === index; const slot = document.createElement("div"); slot.className = `board-slot${choice === "position" || choice === "target" ? (legal.has(index) ? " legal" : "") : ""}${battling ? " battling" : ""}`; slot.innerHTML = `<span class="position">${index + 1}</span>`; if (card) slot.append(gameCard(card, { legal: choice === "target" && legal.has(index), index, opponent: card.owner === "opponent", battling })); if (legal.has(index) && (choice === "position" || choice === "target")) slot.onclick = (event) => { if (event.target === slot || choice === "position") answer(index); }; slot.ondragover = (event) => { if (choice === "play_or_pass") event.preventDefault(); }; slot.ondrop = (event) => { event.preventDefault(); const handIndex = Number(event.dataTransfer.getData("text/plain")); state.pendingDrop = index; answer(handIndex); }; board.append(slot); });
  const hand = $("#hand"); hand.replaceChildren(); game.local.hand.forEach((card, index) => hand.append(gameCard(card, { index, legal: ["play_or_pass", "card", "ability_card"].includes(choice) && legal.has(index) })));
  if (state.interruptionReason) { renderInterruption(panel); return; }
  if (state.connectionWaitReason) { renderConnectionWait(panel); return; }
  const label = document.createElement("strong"); label.textContent = choice ? ({ play_or_pass: "Choose a card or pass", position: "Choose a board position", use_ability: "Use this ability?", ability_card: "Choose a card from your hand", target: "Choose a target", continue: "Dragon battle complete" }[choice] || choice) : (game.turn === "local" ? "Waiting for your next choice…" : "Waiting for opponent…"); panel.append(label);
  if (choice === "play_or_pass") addChoiceButton(panel, "Pass", "pass", "secondary");
  if (choice === "use_ability") { addChoiceButton(panel, "Use ability", true); addChoiceButton(panel, "Skip", false, "secondary"); }
  if (choice === "continue") addChoiceButton(panel, "Continue", true);
}

function applyManaTheme(mana) { if (mana && COLORS[mana]) document.body.dataset.mana = mana.toLowerCase(); else delete document.body.dataset.mana; }
function interruptMatch(reason) { state.interruptionReason = String(reason || "The match was interrupted."); state.request = null; switchView("match"); renderMatch(); toast(state.interruptionReason); }
function renderInterruption(panel) { const label = document.createElement("strong"); label.className = "interruption-message"; label.textContent = state.interruptionReason; panel.append(label); const button = document.createElement("button"); button.textContent = "Return to online lobby"; button.onclick = returnToOnline; panel.append(button); }
function renderConnectionWait(panel) {
  const label = document.createElement("strong"); label.className = "connection-wait-message"; label.textContent = state.waitingAcknowledged ? "Waiting for the other player to reconnect…" : state.connectionWaitReason; panel.append(label);
  if (state.connectionWaitKind === "self") { const reconnect = document.createElement("button"); reconnect.textContent = "Reconnect now"; reconnect.onclick = connect; panel.append(reconnect); return; }
  if (!state.waitingAcknowledged) { const wait = document.createElement("button"); wait.className = "secondary"; wait.textContent = "Keep waiting"; wait.onclick = () => { state.waitingAcknowledged = true; renderMatch(); }; panel.append(wait); }
  const disconnect = document.createElement("button"); disconnect.className = "danger"; disconnect.textContent = "Disconnect"; disconnect.onclick = () => { if (state.connected && state.matchId) send("disconnect", { reason: "The other player ended the match while waiting." }, { matchId: state.matchId }); returnToOnline(); }; panel.append(disconnect);
}
function returnToOnline() { state.matchId = null; state.game = null; state.request = null; state.interruptionReason = ""; state.connectionWaitReason = ""; state.connectionWaitKind = ""; state.waitingAcknowledged = false; switchView("online"); }

function addChoiceButton(parent, text, value, className = "") { const button = document.createElement("button"); button.textContent = text; button.className = className; button.onclick = () => answer(value); parent.append(button); }
function answer(value) { if (!state.request) return; send("player_action", { value }, { requestId: state.request.request_id, matchId: state.request.match_id }); state.request = null; renderMatch(); }
function renderLatency() { $("#latency").textContent = state.latency == null ? "Ping —" : `Ping ${Math.round(state.latency)} ms`; }

function bind() {
  $$(".nav-button").forEach((button) => button.onclick = () => switchView(button.dataset.view));
  $("#new-deck").onclick = () => { const deck = { id: uid(), name: `New deck ${state.decks.length + 1}`, cardIds: [] }; state.decks.push(deck); state.activeDeckId = deck.id; saveDecks(); };
  $("#delete-deck").onclick = () => { const deck = activeDeck(); if (!deck || !confirm(`Delete ${deck.name}?`)) return; state.decks = state.decks.filter((item) => item.id !== deck.id); state.activeDeckId = state.decks[0]?.id || null; saveDecks(); };
  $("#deck-name").onchange = (event) => { const deck = activeDeck(); if (deck) { deck.name = event.target.value.trim() || "Unnamed deck"; saveDecks(); } };
  $("#card-search").oninput = renderCatalog; $("#color-filter").onchange = renderCatalog;
  $("#export-decks").onclick = () => { const blob = new Blob([JSON.stringify({ schemaVersion: 1, decks: state.decks }, null, 2)], { type: "application/json" }); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "draci-zvesti-decks.json"; link.click(); setTimeout(() => URL.revokeObjectURL(link.href), 1000); };
  $("#import-decks").onchange = async (event) => { try { const parsed = JSON.parse(await event.target.files[0].text()); if (!Array.isArray(parsed.decks)) throw new Error("Invalid deck file"); state.decks = parsed.decks.map((deck) => ({ id: uid(), name: String(deck.name ?? "").slice(0, 80) || "Imported deck", cardIds: Array.isArray(deck.cardIds) ? deck.cardIds.filter((id) => state.cards.has(id)).slice(0, 12) : [] })); state.activeDeckId = state.decks[0]?.id || null; saveDecks(); toast("Decks imported"); } catch (error) { toast(error.message); } event.target.value = ""; };
  $("#online-deck").onchange = () => { const deck = state.decks.find((item) => item.id === $("#online-deck").value); if (deck) state.activeDeckId = deck.id; };
  $("#connect-online").onclick = connect; $("#refresh-lobbies").onclick = () => state.connected && send("list_lobbies");
  $("#create-lobby").onclick = () => { try { deckDescriptor(selectedOnlineDeck()); send("create_online_lobby", { name: $("#lobby-name").value.trim(), password: $("#lobby-password").value }, { requestId: crypto.randomUUID() }); } catch (error) { toast(error.message); } };
  $("#leave-match").onclick = () => { if (state.matchId && state.connected) send("disconnect", { reason: "The other player left the match." }, { matchId: state.matchId }); returnToOnline(); };
  $("#close-card-dialog").onclick = () => $("#card-dialog").close(); $("#card-dialog").onclick = (event) => { if (event.target === $("#card-dialog")) $("#card-dialog").close(); };
  window.addEventListener("beforeunload", () => state.socket?.close());
  setInterval(() => { if (state.connected && !state.pingSent) { state.pingSent = performance.now(); send("ping", { sent_at: Date.now() }); } }, 5000);
}

async function init() {
  const response = await fetch("catalog.json", { cache: "no-store" }); if (!response.ok) throw new Error("Card catalogue is unavailable");
  const data = await response.json(); state.catalog = data.cards; state.cards = new Map(data.cards.map((card) => [card.id, card])); preloadCardThumbnails(data.cards); document.body.dataset.view = "decks";
  $("#player-name").value = localStorage.getItem(NAME_KEY) || "Browser player"; loadDecks(data.presets || []); bind(); renderDecks(); renderOnlineDecks(); renderLobbies(); renderRoom();
}

init().catch((error) => { console.error(error); toast(error.message); });

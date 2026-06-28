import sqlite3
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Iterable
from cards.mana import ManaColor
from cards.power import Power
from cards.card_type import CardType
import cards.ability.abilities as abilities_module
from utils.retry_decorator import retry

if TYPE_CHECKING:  # Only used for type hints, not runtime
    from cards.card import Card
    from cards.deck import Deck


class DBUtil():
    _instance = None
    conn_cards = None
    conn_decks = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DBUtil, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Dynamically find the folder containing THIS specific python file
        base_dir = Path(__file__).parent.resolve()

        # Create absolute paths to your databases
        cards_path = base_dir / "cards.db"
        decks_path = base_dir / "decks.db"

        # Connect using the absolute paths as strings
        self.conn_cards = sqlite3.connect(str(cards_path))
        self.conn_decks = sqlite3.connect(str(decks_path))
        self._init_databases()

    def _init_databases(self):
        # Initialize cards table (unchanged)
        cursor = self.conn_cards.cursor()
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS cards (
                            owner TEXT,
                            id TEXT PRIMARY KEY,
                            name TEXT,
                            power INTEGER,
                            color TEXT,
                            hp INTEGER,
                            dmg INTEGER,
                            color_dmg_buff INTEGER,
                            color_hp_buff INTEGER,
                            ability TEXT,
                            image TEXT,
                            type TEXT
                       )
                       ''')
        self.conn_cards.commit()

        cursor = self.conn_decks.cursor()

        # Header: includes the new signature column natively
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS decks (
                            id TEXT PRIMARY KEY,
                            name TEXT,
                            description TEXT,
                            power INTEGER,
                            fitness INTEGER,
                            is_AI BOOLEAN DEFAULT 0,
                            signature TEXT
                       )
                       ''')

        # Lines: includes the new signature column natively
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS deck_lines (
                            deck_id TEXT,
                            card_id TEXT,
                            signature TEXT
                       )
                       ''')

        self.conn_decks.commit()

    def _card_from_row(self, row):
        """Convert a database row to a Card object."""
        from cards.card import Card  # Local import to avoid circular dependencies

        if row is None:
            return None

        power_enum = Power(row[3])
        color_enum = ManaColor[row[4]]
        dmg_buff   = int(row[7]) if row[7] is not None else 0
        hp_buff    = int(row[8]) if row[8] is not None else 0
        color_buf  = (dmg_buff, hp_buff)
        ability    = getattr(abilities_module, row[9])()
        type       = CardType[row[11]] if len(row) > 11 else CardType.PLAYER

        return Card(
            owner       = row[0],
            id          = row[1],
            name        = row[2],
            power       = power_enum,
            color       = color_enum,
            hp          = row[5],
            dmg         = row[6],
            color_buf   = color_buf,
            ability     = ability,
            image       = row[10] if len(row) > 10 else None,
            type        = type
        )

    # ----------------------
    # Card operations
    # ----------------------
    def save_card(self, card):
        try:
            cb = getattr(card, "color_buf", None)
            if cb is None:
                color_dmg_buff = 0
                color_hp_buff  = 0
            else:
                color_dmg_buff = int(cb[0]) if len(cb) > 0 and cb[0] is not None else 0
                color_hp_buff  = int(cb[1]) if len(cb) > 1 and cb[1] is not None else 0
        except Exception:
            color_dmg_buff = 0
            color_hp_buff  = 0

        cursor = self.conn_cards.cursor()

        if not getattr(card, "id", None):
            cursor.execute('SELECT id FROM cards WHERE name = ?', (card.name,))
            existing_ids = [row[0] for row in cursor.fetchall() if row[0].startswith(card.name + "_")]
            numbers = []
            for eid in existing_ids:
                try:
                    numbers.append(int(eid.split("_")[-1]))
                except (IndexError, ValueError):
                    continue
            next_number = max(numbers) + 1 if numbers else 1
            card.id = f"{card.name}_{next_number}"

        cursor.execute('SELECT 1 FROM cards WHERE id = ?', (card.id,))
        exists = cursor.fetchone()

        if exists:
            cursor.execute('''
                           UPDATE cards SET
                                owner            = ?,
                                name             = ?,
                                power            = ?,
                                color            = ?,
                                hp               = ?,
                                dmg              = ?,
                                color_dmg_buff   = ?,
                                color_hp_buff    = ?,
                                ability          = ?,
                                image            = ?,
                                type             = ?
                           WHERE id = ?
                           ''', (
                               card.owner, card.name, card.power, card.color, card.hp, card.dmg,
                               color_dmg_buff, color_hp_buff, card.ability.__class__.__name__,
                               card.image, card.type, card.id
                           ))
        else:
            cursor.execute('''
                           INSERT INTO cards (
                               owner, id, name, power, color, hp, dmg,
                               color_dmg_buff, color_hp_buff, ability, image, type
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ''', (
                               card.owner, card.id, card.name, card.power, card.color, card.hp,
                               card.dmg, color_dmg_buff, color_hp_buff, card.ability.__class__.__name__,
                               card.image, card.type
                           ))
        self.conn_cards.commit()

    @retry
    def load_card(self, card_id: str):
        cursor = self.conn_cards.cursor()
        cursor.execute('''
                       SELECT owner, id, name, power, color, hp, dmg,
                              color_dmg_buff, color_hp_buff, ability, image, type
                       FROM cards WHERE id = ?
                       ''', (card_id,))
        row = cursor.fetchone()
        return self._card_from_row(row) if row else None

    @retry
    def get_all_cards(self):
        cursor = self.conn_cards.cursor()
        cursor.execute('''
                       SELECT owner, id, name, power, color, hp, dmg,
                              color_dmg_buff, color_hp_buff, ability, image, type
                       FROM cards
                       ''')
        rows = cursor.fetchall()
        return [self._card_from_row(row) for row in rows]

    @retry
    def delete_card(self, card_id):
        cursor = self.conn_cards.cursor()
        cursor.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        self.conn_cards.commit()

    # ----------------------
    # Deck operations
    # ----------------------
    def save_deck(self, deck: "Deck"):
        deck.validate()
        cursor = self.conn_decks.cursor()

        deck_id          = getattr(deck, "id", None)
        deck_name        = getattr(deck, "name", None)
        deck_description = getattr(deck, "description", "") or ""
        deck_power       = getattr(deck, "power", 0) or 0
        deck_fitness     = getattr(deck, "fitness", None)

        if deck_fitness is None:
            deck_fitness = getattr(deck, "neat_fitness", 0) or 0

        # --- EXTRACT CARDS ---
        card_ids = []
        if hasattr(deck, "card_ids") and deck.card_ids is not None:
            try:
                card_ids = [str(c) for c in list(deck.card_ids) if c is not None]
            except Exception:
                card_ids = []
        elif hasattr(deck, "cards") and deck.cards is not None:
            items = list(deck.cards)
            extracted = []
            for it in items:
                if isinstance(it, str): extracted.append(it)
                else:
                    cid = getattr(it, "id", None)
                    if cid: extracted.append(cid)
            card_ids = [str(c) for c in extracted if c is not None]
        elif hasattr(deck, "lines") and deck.lines is not None:
            extracted = []
            for it in list(deck.lines):
                if isinstance(it, (list, tuple)) and len(it) >= 2: extracted.append(it[1])
                elif isinstance(it, str): extracted.append(it)
            card_ids = [str(c) for c in extracted if c is not None]
        else:
            try:
                if isinstance(deck, Iterable):
                    extracted = [c for c in list(deck) if isinstance(c, str)]
                    card_ids = [str(c) for c in extracted]
            except Exception:
                card_ids = []

        # --- COMPUTE SIGNATURE ---
        card_str = ",".join(card_ids)
        signature = hashlib.md5(card_str.encode('utf-8')).hexdigest()

        # --- SAVE COMPOSITION (If New) ---
        cursor.execute('SELECT 1 FROM deck_lines WHERE signature = ? LIMIT 1', (signature,))
        if not cursor.fetchone():
            for cid in card_ids:
                cursor.execute('INSERT INTO deck_lines (deck_id, card_id, signature) VALUES (?, ?, ?)', (signature, cid, signature))

        # --- METADATA HANDLING ---
        if not deck_id:
            if not deck_name:
                deck_name = "deck"

            cursor.execute('SELECT id FROM decks WHERE signature = ? AND name = ?', (signature, deck_name))
            existing_row = cursor.fetchone()

            if existing_row:
                deck_id = existing_row[0]
            else:
                cursor.execute('SELECT id FROM decks')
                all_ids = [r[0] for r in cursor.fetchall()]
                existing_similar = [i for i in all_ids if i and i.startswith(deck_name + "_")]
                numbers = []
                for eid in existing_similar:
                    try: numbers.append(int(eid.split("_")[-1]))
                    except Exception: continue
                next_number = max(numbers) + 1 if numbers else 1
                deck_id = f"{deck_name}_{next_number}"

        # --- UPSERT DECK METADATA ---
        cursor.execute('SELECT 1 FROM decks WHERE id = ?', (deck_id,))
        if cursor.fetchone():
            cursor.execute('''
                           UPDATE decks SET
                                name        = ?,
                                description = ?,
                                power       = ?,
                                fitness     = ?,
                                signature   = ?
                           WHERE id = ?
                           ''', (deck_name, deck_description, deck_power, deck_fitness, signature, deck_id))
        else:
            cursor.execute('''
                           INSERT INTO decks (id, name, description, power, fitness, signature)
                           VALUES (?, ?, ?, ?, ?, ?)
                           ''', (deck_id, deck_name, deck_description, deck_power, deck_fitness, signature))

        # --- CLEANUP (Prevent DB Bloat) ---
        cursor.execute('DELETE FROM deck_lines WHERE signature NOT IN (SELECT signature FROM decks)')

        self.conn_decks.commit()

        try:
            if not getattr(deck, "id", None):
                setattr(deck, "id", deck_id)
        except Exception:
            pass

    @retry
    def load_deck(self, deck_id) -> "Deck":
        from cards.deck import Deck

        cursor = self.conn_decks.cursor()

        cursor.execute('''
                       SELECT id, name, description, power, fitness, signature
                       FROM decks WHERE id = ?
                       ''', (deck_id,))
        row = cursor.fetchone()
        if not row:
            return None

        deck = Deck()
        deck.id           = row[0]
        deck.name         = row[1] or ""
        deck.description  = row[2] or ""
        deck.power        = row[3] or 0
        deck.neat_fitness = row[4] or 0

        signature = row[5] if len(row) > 5 and row[5] else row[0]

        cursor.execute('SELECT card_id FROM deck_lines WHERE signature = ? ORDER BY rowid', (signature,))
        card_rows = cursor.fetchall()

        for (card_id,) in card_rows:
            if not card_id:
                continue
            card = self.load_card(card_id)
            if card:
                try:
                    deck.add_card(card)
                except Exception:
                    try:
                        deck.cards.append(card)
                    except Exception:
                        continue

        return deck

    @retry
    def delete_deck(self, deck_id):
        cursor = self.conn_decks.cursor()

        cursor.execute('DELETE FROM decks WHERE id = ?', (deck_id,))
        cursor.execute('DELETE FROM deck_lines WHERE signature NOT IN (SELECT signature FROM decks)')

        self.conn_decks.commit()

    @retry
    def get_all_decks(self):
        cursor = self.conn_decks.cursor()
        cursor.execute('SELECT name FROM decks ORDER BY name')
        rows = cursor.fetchall()
        return [row[0] for row in rows]

    @retry
    def get_all_deck_ids(self):
        cursor = self.conn_decks.cursor()
        cursor.execute('SELECT id FROM decks ORDER BY id')
        rows = cursor.fetchall()
        return [row[0] for row in rows]
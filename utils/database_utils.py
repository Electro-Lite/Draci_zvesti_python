import sqlite3
from typing             import TYPE_CHECKING, Iterable
from cards.mana         import ManaColor
from cards.power        import Power
from cards.card_type    import CardType
import cards.ability.abilities as abilities_module
from utils.retry_decorator import  retry

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
	# two separate sqlite files as before
        self.conn_cards = sqlite3.connect("cards.db")
        self.conn_decks = sqlite3.connect("decks.db")
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

        # Initialize decks header and lines tables
        cursor = self.conn_decks.cursor()

        # Header: store deck id and name (id is primary key)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS decks (
                id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                power INTEGER,
                fitness INTEGER
            )
        ''')

        # Lines: one row per card in a deck (deck_id + card_id).
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deck_lines (
                deck_id TEXT,
                card_id TEXT
            )
        ''')

        self.conn_decks.commit()

    def _card_from_row(self, row):
        """Convert a database row to a Card object."""
        from cards.card import Card  # Local import to avoid circular dependencies

        # row indices:
        # 0 owner, 1 id, 2 name, 3 power, 4 color, 5 hp, 6 dmg,
        # 7 color_dmg_buff, 8 color_hp_buff, 9 ability, 10 image, 11 type
        if row is None:
            return None

        power_enum = Power( row[3])
        color_enum = ManaColor[ row[4] ]
        dmg_buff   = int(row[7]) if row[7] is not None else 0
        hp_buff    = int(row[8]) if row[8] is not None else 0
        color_buf  = (dmg_buff, hp_buff)
        ability    = getattr(abilities_module,  row[9])()
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
        # Safely extract color_buf (expected order: (dmg_buff, hp_buff))
        try:
            cb = getattr(card, "color_buf", None)
            if cb is None:
                color_dmg_buff = 0
                color_hp_buff  = 0
            else:
                # allow list/tuple or other sequence; fall back to 0 if not present or not int
                color_dmg_buff = int(cb[0]) if len(cb) > 0 and cb[0] is not None else 0
                color_hp_buff  = int(cb[1]) if len(cb) > 1 and cb[1] is not None else 0
        except Exception:
            color_dmg_buff = 0
            color_hp_buff  = 0

        cursor = self.conn_cards.cursor()

        # If card.id is None or empty, generate an id based on name + number
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

        # Check if the card with this id already exists
        cursor.execute('SELECT 1 FROM cards WHERE id = ?', (card.id,))
        exists = cursor.fetchone()

        if exists:
            # Update existing card (include buff columns)
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
                card.owner,
                card.name,
                card.power,
                card.color,
                card.hp,
                card.dmg,
                color_dmg_buff,
                color_hp_buff,
                card.ability.__class__.__name__,
                card.image,
                card.type,
                card.id
            ))
        else:
            # Insert new card (include buff columns)
            cursor.execute('''
                INSERT INTO cards (
                    owner, id, name, power, color, hp, dmg,
                    color_dmg_buff, color_hp_buff, ability, image, type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                card.owner,           #0
                card.id,              #1
                card.name,            #2
                card.power,           #3
                card.color,           #4
                card.hp,              #5
                card.dmg,             #6
                color_dmg_buff,       #7
                color_hp_buff,        #8
                card.ability.__class__.__name__,    #9
                card.image,           #10
                card.type             #11
            ))
        self.conn_cards.commit()
    @retry
    def load_card(self, card_id:str):
        """Load a card by ID."""
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
        """Get all cards from the database."""
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
        """Delete a card by ID."""
        cursor = self.conn_cards.cursor()
        cursor.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        self.conn_cards.commit()

    # ----------------------
    # Deck operations
    # ----------------------
    def save_deck(self, deck: "Deck"):
        """
        Save a deck header and its lines.
        - header is stored in `decks` (id, name, description, power, fitness)
        - lines are stored in `deck_lines` (deck_id, card_id) one row per card
        """
        deck.validate()
        cursor = self.conn_decks.cursor()

        # Try to extract deck fields
        deck_id          = getattr(deck, "id",   None)
        deck_name        = getattr(deck, "name", None)
        deck_description = getattr(deck, "description", "") or ""
        deck_power       = getattr(deck, "power", 0) or 0

        # prefer deck.fitness, but fall back to deck.neat_fitness to match your Deck class
        deck_fitness     = getattr(deck, "fitness", None)
        if deck_fitness is None:
            deck_fitness = getattr(deck, "neat_fitness", 0) or 0

        # If no id, generate one similar to card logic using the name
        if not deck_id:
            if not deck_name:
                # As a last resort, create a generic id
                deck_name = "deck"
            # find existing ids that start with name_
            cursor.execute('SELECT id FROM decks')
            all_ids = [r[0] for r in cursor.fetchall()]
            existing_similar = [i for i in all_ids if i and i.startswith(deck_name + "_")]
            numbers = []
            for eid in existing_similar:
                try:
                    numbers.append(int(eid.split("_")[-1]))
                except Exception:
                    continue
            next_number = max(numbers) + 1 if numbers else 1
            deck_id = f"{deck_name}_{next_number}"

        # Upsert header (id, name, description, power, fitness)
        cursor.execute('SELECT 1 FROM decks WHERE id = ?', (deck_id,))
        if cursor.fetchone():
            cursor.execute('''
                UPDATE decks SET 
                    name        = ?,
                    description = ?,
                    power       = ?,
                    fitness     = ?
                WHERE id = ?
            ''', (deck_name, deck_description, deck_power, deck_fitness, deck_id))
        else:
            cursor.execute('''
                INSERT INTO decks (id, name, description, power, fitness)
                VALUES (?, ?, ?, ?, ?)
            ''', (deck_id, deck_name, deck_description, deck_power, deck_fitness))

        # Now handle lines. First remove existing lines for this deck_id
        cursor.execute('DELETE FROM deck_lines WHERE deck_id = ?', (deck_id,))

        # Determine iterable of card ids from the provided deck object.
        # Support multiple shapes:
        # - deck.card_ids -> iterable of str
        # - deck.cards -> iterable of Card objects (with .id) or id strings
        # - deck.lines -> iterable of (deck_id, card_id) tuples (take second)
        # - or deck itself is an iterable of card ids
        card_ids = []

        # 1) explicit card_ids attribute (preferred if present)
        if hasattr(deck, "card_ids") and deck.card_ids is not None:
            try:
                card_ids = [str(c) for c in list(deck.card_ids) if c is not None]
            except Exception:
                card_ids = []

        # 2) cards attribute (Card objects or id strings)
        elif hasattr(deck, "cards") and deck.cards is not None:
            items = list(deck.cards)
            extracted = []
            for it in items:
                if isinstance(it, str):
                    extracted.append(it)
                else:
                    cid = getattr(it, "id", None)
                    if cid:
                        extracted.append(cid)
            card_ids = [str(c) for c in extracted if c is not None]

        # 3) lines attribute (tuples) or generic iterable
        elif hasattr(deck, "lines") and deck.lines is not None:
            extracted = []
            for it in list(deck.lines):
                if isinstance(it, (list, tuple)) and len(it) >= 2:
                    extracted.append(it[1])
                elif isinstance(it, str):
                    extracted.append(it)
            card_ids = [str(c) for c in extracted if c is not None]

        else:
            # as last resort, if deck itself is iterable of strings
            try:
                if isinstance(deck, Iterable):
                    extracted = [c for c in list(deck) if isinstance(c, str)]
                    card_ids = [str(c) for c in extracted]
            except Exception:
                card_ids = []

        # Insert lines (deck_id, card_id). If list is empty, this simply leaves deck_lines cleared.
        for cid in card_ids:
            cursor.execute('INSERT OR IGNORE INTO deck_lines (deck_id, card_id) VALUES (?, ?)', (deck_id, cid))

        self.conn_decks.commit()

        # Keep outward behavior: assign id back to deck object if possible
        try:
            if not getattr(deck, "id", None):
                setattr(deck, "id", deck_id)
        except Exception:
            pass
    @retry
    def load_deck(self, deck_id) -> "Deck":
        """
        Load a deck by id and return a Deck instance with cards populated.
        Returns:
            Deck: deck object with metadata and list of Card objects.
            None if deck not found.
        """
        # local import to avoid circular imports at module load time
        from cards.deck import Deck

        cursor = self.conn_decks.cursor()

        # Load deck header
        cursor.execute('''
            SELECT id, name, description, power, fitness
            FROM decks WHERE id = ?
        ''', (deck_id,))
        row = cursor.fetchone()
        if not row:
            return None

        deck = Deck()
        deck.id          = row[0]
        deck.name        = row[1] or ""
        deck.description = row[2] or ""
        deck.power       = row[3] or 0
        # DB column is "fitness", class field is "neat_fitness"
        deck.neat_fitness = row[4] or 0

        # Load card ids from deck_lines in insertion order (use rowid to be deterministic)
        cursor.execute('SELECT card_id FROM deck_lines WHERE deck_id = ? ORDER BY rowid', (deck_id,))
        card_rows = cursor.fetchall()

        # Fetch Card objects from cards.db and add to deck
        for (card_id,) in card_rows:
            if not card_id:
                continue
            card = self.load_card(card_id)
            if card:
                # deck.add_card enforces type-checking (raises if not a Card instance)
                try:
                    deck.add_card(card)
                except Exception:
                    # fallback: if add_card fails (type mismatch), append directly
                    try:
                        deck.cards.append(card)
                    except Exception:
                        # ignore any problematic card to keep deck loading robust
                        continue

        return deck

    @retry
    def delete_deck(self, deck_id):
        """Delete a deck by id (header + lines)."""
        cursor = self.conn_decks.cursor()
        cursor.execute('DELETE FROM deck_lines WHERE deck_id = ?', (deck_id,))
        cursor.execute('DELETE FROM decks WHERE id = ?', (deck_id,))
        self.conn_decks.commit()
    @retry
    def get_all_decks(self):
        """Retrieves the names of all saved decks, sorted alphabetically.
        Returns:
            list[str]: A list of deck names.
        """
        cursor = self.conn_decks.cursor()
        cursor.execute('SELECT name FROM decks ORDER BY name')
        rows = cursor.fetchall()
        return [row[0] for row in rows]

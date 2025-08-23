import sqlite3

class DBUtil():
    _instance   = None
    conn_cards  = None
    conn_decks  = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DBUtil, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.conn_cards = sqlite3.connect("cards.db")
        self.conn_decks = sqlite3.connect("decks.db")

    def save_card(self, card):
        # Safely extract color_buf (expected order: (dmg_buff, hp_buff))
        try:
            cb = getattr(card, "color_buf", None)
            if cb is None:
                color_dmg_buff = 0
                color_hp_buff = 0
            else:
                # allow list/tuple or other sequence; fall back to 0 if not present or not int
                color_dmg_buff = int(cb[0]) if len(cb) > 0 and cb[0] is not None else 0
                color_hp_buff  = int(cb[1]) if len(cb) > 1 and cb[1] is not None else 0
        except Exception:
            color_dmg_buff = 0
            color_hp_buff = 0

        # Debug: print all values being inserted
        print("Inserting/updating card with values:")
        print("owner:", getattr(card, "owner", None))
        print("id:", getattr(card, "id", None))
        print("name:", getattr(card, "name", None))
        print("power:", getattr(card, "power", None))
        print("color:", getattr(card, "color", None))
        print("hp:", getattr(card, "hp", None))
        print("dmg:", getattr(card, "dmg", None))
        print("hp_buff:", color_hp_buff)
        print("dmg_buff:", color_dmg_buff)
        print("ability:", str(getattr(card, "ability", None)))
        print("image:", getattr(card, "image", None))
        print("type:", getattr(card, "type", None))

        cursor = self.conn_cards.cursor()
        # Ensure the cards table exists (added buff columns)
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
                str(card.ability),
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
                card.owner,         #0
                card.id,            #1
                card.name,          #2
                card.power,         #3
                card.color,         #4
                card.hp,            #5
                card.dmg,           #6
                color_dmg_buff,     #7
                color_hp_buff,      #8
                str(card.ability),  #9
                card.image,         #10
                card.type           #11
            ))
        self.conn_cards.commit()

    def save_deck(self, deck):
        raise NotImplementedError("This method should be implemented to save a deck to the database.")  

    def load_deck(self, deck_id):
        raise NotImplementedError("This method should be implemented to load a deck from the database.")    

    def load_card(self, card_id):
        from cards.card import Card  # Local import to resolve cyclic dependency
        cursor = self.conn_cards.cursor()
        cursor.execute('''
            SELECT owner, id, name, power, color, hp, dmg,
                   color_dmg_buff, color_hp_buff, ability, image, type
            FROM cards WHERE id = ?
        ''', (card_id,))
        row = cursor.fetchone()
        if row:
            # row indices:
            # 0 owner,1 id,2 name,3 power,4 color,5 hp,6 dmg,
            # 7 color_dmg_buff,8 color_hp_buff,9 ability,10 image,11 type
            dmg_buff = int(row[7]) if row[7] is not None else 0
            hp_buff  = int(row[8]) if row[8] is not None else 0
            color_buf = (dmg_buff, hp_buff)

            return Card(
                owner=row[0],
                id=row[1],
                name=row[2],
                power=row[3],
                color=row[4],
                hp=row[5],
                dmg=row[6],
                color_buf=color_buf,
                ability=row[9],
                image=row[10] if len(row) > 10 else None,
                type=row[11] if len(row) > 11 else None
            )
        return None

    def delete_card(self, card_id: str):
        cursor = self.conn_cards.cursor()
        cursor.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        self.conn_cards.commit()

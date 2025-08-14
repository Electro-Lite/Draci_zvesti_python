import sqlite3
from cards.database_utils import DBUtil
class Card:
    owner     = None
    id        = 0
    name      = ""
    power     = None
    color     = ""
    color_buf = []
    hp        = 0
    dmg       = 0
    ability   = ""
    ability_type   = "" #vstup,smrt,passive
    def __init__(self) -> None:
        self.color_buf = [0,0]

@staticmethod
def load_card(card_id):
    cursor = DBUtil().conn_cards
    cursor.execute("SELECT * FROM cards WHERE cards.id = ?", (card_id,))
    row = cursor.fetchone()
    if row:
        card = Card()
        card.owner = row['owner']
        card.id = row['id']
        card.name = row['name']
        card.power = row['power']
        card.color = row['color']
        card.hp = row['hp']
        card.dmg = row['dmg']
        card.ability = row['ability']
        card.ability_type = row['ability_type']
        return card
    return None

@staticmethod
def store_card(card):
    # Simple validation: check required fields
    if not card.id:
        raise ValueError("Card must have a name and id.")
    cursor = DBUtil().conn_cards
    cursor.execute("""
        INSERT INTO cards (owner, id, name, power, color, hp, dmg, ability, ability_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        card.owner,
        card.id,
        card.name,
        card.power,
        card.color,
        card.hp,
        card.dmg,
        card.ability,
        card.ability_type
    ))
    DBUtil().conn_cards.connection.commit()

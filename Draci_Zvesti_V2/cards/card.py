import sqlite3
from utils.database_utils import DBUtil
from cards.card_type import CardType
class Card:
    def __init__(
        self,
        owner=None,
        id=0,
        name="",
        power=None,
        color="",
        color_buf=[0,0], #[dmg, hp]
        hp=0,
        dmg=0,
        ability=None,
        image=None, #path to image
        type= CardType.PLAYER
    ) -> None:
        self.owner = owner
        self.id = id  # database given
        self.name = name
        self.power = power
        self.color = color
        self.color_buf = color_buf if color_buf is not None else [0, 0]
        self.hp = hp
        self.dmg = dmg
        self.ability = ability
        self.image = image
        self.type = type #dragon/player

@staticmethod
def load_card(card_id):
    raise NotImplementedError("Use DBUtil().get_card(card_id) instead.")
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
        return card
    return None

@staticmethod
def store_card(card):
    raise NotImplementedError("Use DBUtil().store_card(card) instead.")
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

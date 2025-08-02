import sqlite3
from cards.database_utils import DBUtil
class card:
    owner     = None
    id        = 0
    name      = ""
    power     = "" #declare enum for this
    color     = ""
    color_buf = []
    hp        = 0
    dmg       = 0
    ability   = ""
    ability_type   = "" #vstup,smrt,passive
    def __init__(self) -> None:
        self.color_buf = [0,0]


def load_card():
    cursor = DBUtil().conn_cards
    raise NotImplementedError("")
    cursor.execute("INSERT INTO users (name, age) VALUES (?, ?)", ("Alice", 30))

def store_card():
    cursor = DBUtil().conn_cards
    raise NotImplementedError("")
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()

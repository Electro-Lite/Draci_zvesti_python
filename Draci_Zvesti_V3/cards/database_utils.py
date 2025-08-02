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
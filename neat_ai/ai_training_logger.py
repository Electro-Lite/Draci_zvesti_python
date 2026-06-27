import sqlite3
from utils.database_utils import DBUtil

class AITrainingLogger(DBUtil):
    # If DBUtil requires args (e.g., db_name, conn_str), you must accept them here.
    def __init__(self):
        self.conn_train = sqlite3.connect("train.db")
        super().__init__()

    def _init_databases(self):
        super()._init_databases()
        cursor = self.conn_train.cursor()

        # Enable Foreign Key constraints support for this connection
        cursor.execute("PRAGMA foreign_keys = ON;")

#################### BUILDER SECTION ######################
        # 1. TRAINING Table
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS training (
                                                               id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                               start_date TEXT NOT NULL,
                                                               config TEXT,
                                                               end_date TEXT
                       );
                       ''')

        # 2. GENOME Table (D.B.T. in diagram)
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS genome (
                                                             guid TEXT PRIMARY KEY,
                                                             -- local_id TEXT, -- I dont remember why I have this
                                                             gen INTEGER NOT NULL,
                                                             deck_id INTEGER NOT NULL,
                                                             score REAL,
                                                             pickle_path TEXT,
                                                             training_id INTEGER NOT NULL,
                                                             FOREIGN KEY (training_id) REFERENCES training(id) ON DELETE CASCADE,
                                                             FOREIGN KEY (deck_id) REFERENCES decks(id)
                           );
                       ''')


        # 3. MATCH DBT Table
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS match_dbt (
                                                                guid TEXT PRIMARY KEY,
                                                                genome_1 TEXT NOT NULL,
                                                                genome_2 TEXT NOT NULL,
                                                                deck_1 TEXT,
                                                                deck_2 TEXT,
                                                                gen INTEGER,
                                                                result REAL, -- last value of: genome_1.score - genome_2.score
                                                                FOREIGN KEY (genome_1) REFERENCES genome(guid),
                                                                FOREIGN KEY (genome_2) REFERENCES genome(guid)
                           );
                       ''')
#################### PLAYER SECTION ######################


        # 4. PC MATCH Table
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS pc_match (
                                                               id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                               gen INTEGER,
                                                               match_dbt_guid TEXT NOT NULL,
                                                               g1_score REAL,
                                                               g2_score REAL,
                                                               FOREIGN KEY (match_dbt_guid) REFERENCES match_dbt(guid) ON DELETE CASCADE
                           );
                       ''')

        self.conn_train.commit()
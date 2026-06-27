import sqlite3
from dataclasses import dataclass, asdict
from typing import Optional
from utils.database_utils import DBUtil
from utils.retry_decorator import retry

###########################################################################
#                             ENTITY CLASSES                              #
###########################################################################

@dataclass
class Training:
    start_date: str
    config: Optional[str] = None
    end_date: Optional[str] = None
    id: Optional[int] = None

@dataclass
class Genome:
    guid: str
    gen: int
    deck_id: int
    training_id: int
    score: Optional[float] = None
    pickle_path: Optional[str] = None

@dataclass
class MatchDBT:
    guid: str
    genome_1: str
    genome_2: str
    deck_1: Optional[str] = None
    deck_2: Optional[str] = None
    gen: Optional[int] = None
    result: Optional[float] = None

@dataclass
class PCMatch:
    match_dbt_guid: str
    gen: Optional[int] = None
    g1_score: Optional[float] = None
    g2_score: Optional[float] = None
    id: Optional[int] = None


###########################################################################
#                          MAIN LOGGER CLASS                              #
###########################################################################

class AITrainingLogger(DBUtil):
    _instance = None

    def __init__(self):
        if not hasattr(self, 'initialized'):
            # check_same_thread=False allows multi-threaded AI workers to log data
            self.conn_train = sqlite3.connect("train.db", check_same_thread=False)

            # Returns rows as dictionary-like objects instead of plain tuples
            self.conn_train.row_factory = sqlite3.Row

            super().__init__()
            self.initialized = True

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AITrainingLogger, cls).__new__(cls)
        return cls._instance

    @retry
    def _init_databases(self):
        super()._init_databases()

        # Pragmas for data integrity and high-concurrency training
        self.conn_train.execute("PRAGMA foreign_keys = ON;")
        self.conn_train.execute("PRAGMA journal_mode = WAL;")

        # Using a context manager automatically commits on success or rolls back on error
        with self.conn_train:
            # 1. TRAINING Table
            self.conn_train.execute('''
                                    CREATE TABLE IF NOT EXISTS training (
                                                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                            start_date TEXT NOT NULL,
                                                                            config TEXT,
                                                                            end_date TEXT
                                    );
                                    ''')

            # 2. GENOME Table
            self.conn_train.execute('''
                                    CREATE TABLE IF NOT EXISTS genome (
                                                                          guid TEXT PRIMARY KEY,
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
            self.conn_train.execute('''
                                    CREATE TABLE IF NOT EXISTS match_dbt (
                                                                             guid TEXT PRIMARY KEY,
                                                                             genome_1 TEXT NOT NULL,
                                                                             genome_2 TEXT NOT NULL,
                                                                             deck_1 TEXT,
                                                                             deck_2 TEXT,
                                                                             gen INTEGER,
                                                                             result REAL,
                                                                             FOREIGN KEY (genome_1) REFERENCES genome(guid),
                                        FOREIGN KEY (genome_2) REFERENCES genome(guid)
                                        );
                                    ''')

            # 4. PC MATCH Table
            self.conn_train.execute('''
                                    CREATE TABLE IF NOT EXISTS pc_match (
                                                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                            gen INTEGER,
                                                                            match_dbt_guid TEXT NOT NULL,
                                                                            g1_score REAL,
                                                                            g2_score REAL,
                                                                            FOREIGN KEY (match_dbt_guid) REFERENCES match_dbt(guid) ON DELETE CASCADE
                                        );
                                    ''')


    ###########################################################################
    #                           TRAINING CRUD                                 #
    ###########################################################################

    @retry
    def save_training(self, training: Training) -> Training:
        with self.conn_train:
            if training.id is None:
                cursor = self.conn_train.execute('''
                                                 INSERT INTO training (start_date, config, end_date)
                                                 VALUES (:start_date, :config, :end_date)
                                                 ''', asdict(training))
                training.id = cursor.lastrowid
            else:
                self.conn_train.execute('''
                                        UPDATE training
                                        SET start_date = :start_date, config = :config, end_date = :end_date
                                        WHERE id = :id
                                        ''', asdict(training))
        return training

    @retry
    def get_training(self, training_id: int) -> Optional[Training]:
        cursor = self.conn_train.execute("SELECT * FROM training WHERE id = ?", (training_id,))
        row = cursor.fetchone()
        return Training(**dict(row)) if row else None

    @retry
    def delete_training(self, training: Training) -> None:
        if training.id is not None:
            with self.conn_train:
                self.conn_train.execute("DELETE FROM training WHERE id = ?", (training.id,))
            training.id = None


    ###########################################################################
    #                           GENOME CRUD                                   #
    ###########################################################################

    @retry
    def save_genome(self, genome: Genome) -> Genome:
        with self.conn_train:
            # True UPSERT: Safely updates without dropping the row and violating FK constraints
            self.conn_train.execute('''
                                    INSERT INTO genome (guid, gen, deck_id, score, pickle_path, training_id)
                                    VALUES (:guid, :gen, :deck_id, :score, :pickle_path, :training_id)
                                        ON CONFLICT(guid) DO UPDATE SET
                                        gen = excluded.gen,
                                                                 deck_id = excluded.deck_id,
                                                                 score = excluded.score,
                                                                 pickle_path = excluded.pickle_path,
                                                                 training_id = excluded.training_id
                                    ''', asdict(genome))
        return genome

    @retry
    def get_genome(self, guid: str) -> Optional[Genome]:
        cursor = self.conn_train.execute("SELECT * FROM genome WHERE guid = ?", (guid,))
        row = cursor.fetchone()
        return Genome(**dict(row)) if row else None

    @retry
    def delete_genome(self, genome: Genome) -> None:
        with self.conn_train:
            self.conn_train.execute("DELETE FROM genome WHERE guid = ?", (genome.guid,))


    ###########################################################################
    #                          MATCH DBT CRUD                                 #
    ###########################################################################

    @retry
    def save_match_dbt(self, match: MatchDBT) -> MatchDBT:
        with self.conn_train:
            self.conn_train.execute('''
                                    INSERT INTO match_dbt (guid, genome_1, genome_2, deck_1, deck_2, gen, result)
                                    VALUES (:guid, :genome_1, :genome_2, :deck_1, :deck_2, :gen, :result)
                                        ON CONFLICT(guid) DO UPDATE SET
                                        genome_1 = excluded.genome_1,
                                                                 genome_2 = excluded.genome_2,
                                                                 deck_1 = excluded.deck_1,
                                                                 deck_2 = excluded.deck_2,
                                                                 gen = excluded.gen,
                                                                 result = excluded.result
                                    ''', asdict(match))
        return match

    @retry
    def get_match_dbt(self, guid: str) -> Optional[MatchDBT]:
        cursor = self.conn_train.execute("SELECT * FROM match_dbt WHERE guid = ?", (guid,))
        row = cursor.fetchone()
        return MatchDBT(**dict(row)) if row else None

    @retry
    def delete_match_dbt(self, match: MatchDBT) -> None:
        with self.conn_train:
            self.conn_train.execute("DELETE FROM match_dbt WHERE guid = ?", (match.guid,))


    ###########################################################################
    #                           PC MATCH CRUD                                 #
    ###########################################################################

    @retry
    def save_pc_match(self, pc_match: PCMatch) -> PCMatch:
        with self.conn_train:
            if pc_match.id is None:
                cursor = self.conn_train.execute('''
                                                 INSERT INTO pc_match (gen, match_dbt_guid, g1_score, g2_score)
                                                 VALUES (:gen, :match_dbt_guid, :g1_score, :g2_score)
                                                 ''', asdict(pc_match))
                pc_match.id = cursor.lastrowid
            else:
                self.conn_train.execute('''
                                        UPDATE pc_match
                                        SET gen = :gen, match_dbt_guid = :match_dbt_guid, g1_score = :g1_score, g2_score = :g2_score
                                        WHERE id = :id
                                        ''', asdict(pc_match))
        return pc_match

    @retry
    def get_pc_match(self, pc_match_id: int) -> Optional[PCMatch]:
        cursor = self.conn_train.execute("SELECT * FROM pc_match WHERE id = ?", (pc_match_id,))
        row = cursor.fetchone()
        return PCMatch(**dict(row)) if row else None

    @retry
    def delete_pc_match(self, pc_match: PCMatch) -> None:
        if pc_match.id is not None:
            with self.conn_train:
                self.conn_train.execute("DELETE FROM pc_match WHERE id = ?", (pc_match.id,))
            pc_match.id = None
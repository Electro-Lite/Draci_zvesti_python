import os
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
    metadata: Optional[str] = None
    description: Optional[str] = None
    id: Optional[int] = None

@dataclass
class Genome:
    guid: str
    gen: int
    deck_id: str
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
    phase: str = "training"
    seed: Optional[int] = None
    seat_swap: bool = False
    p1_game_score: Optional[int] = None
    p2_game_score: Optional[int] = None
    winner_id: Optional[int] = None
    rounds: Optional[int] = None
    starting_player_id: Optional[int] = None
    deck1_controller_gen: Optional[int] = None
    deck2_controller_gen: Optional[int] = None
    p1_card_plays: Optional[str] = None
    p2_card_plays: Optional[str] = None
    p1_active_ability_uses: Optional[str] = None
    p2_active_ability_uses: Optional[str] = None
    id: Optional[int] = None


###########################################################################
#                          MAIN LOGGER CLASS                              #
###########################################################################

class AITrainingLogger(DBUtil):
    _instance = None

    def __init__(self):
        process_id = os.getpid()
        train_db_path = os.environ.get("TRAIN_DB_PATH", "train.db")
        needs_connection = (
            not getattr(self, "initialized", False)
            or getattr(self, "process_id", None) != process_id
            or getattr(self, "train_db_path", None) != train_db_path
        )
        if needs_connection:
            old_connection = getattr(self, "conn_train", None)
            if old_connection is not None:
                try:
                    old_connection.close()
                except sqlite3.Error:
                    pass
            # check_same_thread=False allows multi-threaded AI workers to log data
            self.conn_train = sqlite3.connect(
                train_db_path,
                timeout=30.0,
                check_same_thread=False,
            )

            # Returns rows as dictionary-like objects instead of plain tuples
            self.conn_train.row_factory = sqlite3.Row

            super().__init__()
            self.initialized = True
            self.process_id = process_id
            self.train_db_path = train_db_path

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
        self.conn_train.execute("PRAGMA busy_timeout = 30000;")

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
            self._ensure_column(self.conn_train, "training", "metadata", "TEXT")
            self._ensure_column(self.conn_train, "training", "description", "TEXT")

            # 2. GENOME Table
            self.conn_train.execute('''
                                    CREATE TABLE IF NOT EXISTS genome (
                                                                          guid TEXT PRIMARY KEY,
                                                                          gen INTEGER NOT NULL,
                                                                          deck_id TEXT NOT NULL,
                                                                          score REAL,
                                                                          pickle_path TEXT,
                                                                          training_id INTEGER NOT NULL,
                                                                          FOREIGN KEY (training_id) REFERENCES training(id) ON DELETE CASCADE
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
            self._ensure_column(self.conn_train, "pc_match", "phase", "TEXT DEFAULT 'training'")
            self._ensure_column(self.conn_train, "pc_match", "seed", "INTEGER")
            self._ensure_column(self.conn_train, "pc_match", "seat_swap", "BOOLEAN DEFAULT 0")
            self._ensure_column(self.conn_train, "pc_match", "p1_game_score", "INTEGER")
            self._ensure_column(self.conn_train, "pc_match", "p2_game_score", "INTEGER")
            self._ensure_column(self.conn_train, "pc_match", "winner_id", "INTEGER")
            self._ensure_column(self.conn_train, "pc_match", "rounds", "INTEGER")
            self._ensure_column(self.conn_train, "pc_match", "starting_player_id", "INTEGER")
            self._ensure_column(self.conn_train, "pc_match", "deck1_controller_gen", "INTEGER")
            self._ensure_column(self.conn_train, "pc_match", "deck2_controller_gen", "INTEGER")
            self._ensure_column(self.conn_train, "pc_match", "p1_card_plays", "TEXT")
            self._ensure_column(self.conn_train, "pc_match", "p2_card_plays", "TEXT")
            self._ensure_column(
                self.conn_train,
                "pc_match",
                "p1_active_ability_uses",
                "TEXT",
            )
            self._ensure_column(
                self.conn_train,
                "pc_match",
                "p2_active_ability_uses",
                "TEXT",
            )

            # 5. AI TRAINING DECK Tables
            self.conn_train.execute('''
                                    CREATE TABLE IF NOT EXISTS ai_training_decks (
                                        id TEXT PRIMARY KEY,
                                        training_id INTEGER NOT NULL,
                                        name TEXT,
                                        description TEXT,
                                        power INTEGER,
                                        fitness REAL,
                                        signature TEXT NOT NULL,
                                        FOREIGN KEY (training_id) REFERENCES training(id) ON DELETE CASCADE
                                    );
                                    ''')

            self.conn_train.execute('''
                                    CREATE TABLE IF NOT EXISTS ai_training_deck_lines (
                                        deck_id TEXT NOT NULL,
                                        card_id TEXT NOT NULL,
                                        position INTEGER NOT NULL,
                                        FOREIGN KEY (deck_id) REFERENCES ai_training_decks(id) ON DELETE CASCADE
                                    );
                                    ''')

            self.conn_train.execute('''
                                    CREATE INDEX IF NOT EXISTS idx_ai_training_decks_training_id
                                    ON ai_training_decks(training_id);
                                    ''')

            self.conn_train.execute('''
                                    CREATE INDEX IF NOT EXISTS idx_ai_training_deck_lines_deck_id
                                    ON ai_training_deck_lines(deck_id);
                                    ''')


    ###########################################################################
    #                           TRAINING CRUD                                 #
    ###########################################################################

    @retry
    def save_training(self, training: Training) -> Training:
        with self.conn_train:
            if training.id is None:
                cursor = self.conn_train.execute('''
                                                 INSERT INTO training (
                                                     start_date, config, end_date, metadata, description
                                                 )
                                                 VALUES (
                                                     :start_date, :config, :end_date, :metadata, :description
                                                 )
                                                 ''', asdict(training))
                training.id = cursor.lastrowid
            else:
                self.conn_train.execute('''
                                        UPDATE training
                                        SET start_date = :start_date,
                                            config = :config,
                                            end_date = :end_date,
                                            metadata = :metadata,
                                            description = :description
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
            self.clear_training_data(training_id=training.id)
            training.id = None


    ###########################################################################
    #                       AI TRAINING DECK CRUD                             #
    ###########################################################################

    def _make_training_deck_id(self, training_id: int, deck_name: str, signature: str) -> str:
        base_id = f"T{training_id}_{deck_name or 'deck'}"
        deck_id = base_id
        suffix = 2

        while True:
            cursor = self.conn_train.execute(
                "SELECT signature FROM ai_training_decks WHERE id = ?",
                (deck_id,)
            )
            row = cursor.fetchone()
            if row is None or row["signature"] == signature:
                return deck_id
            deck_id = f"{base_id}_{suffix}"
            suffix += 1

    @retry
    def save_training_deck(self, deck: "Deck", training_id: int) -> "Deck":
        deck.validate()

        deck_name = getattr(deck, "name", None) or "deck"
        deck_description = getattr(deck, "description", "") or ""
        deck_power = getattr(deck, "power", 0) or 0
        deck_fitness = getattr(deck, "fitness", None)

        if deck_fitness is None:
            deck_fitness = getattr(deck, "neat_fitness", 0) or 0

        card_ids = self._extract_deck_card_ids(deck)
        signature = self._deck_signature(card_ids)
        deck_id = getattr(deck, "id", None)

        if not deck_id:
            deck_id = self._make_training_deck_id(training_id, deck_name, signature)

        with self.conn_train:
            self.conn_train.execute('''
                                    INSERT INTO ai_training_decks (
                                        id, training_id, name, description, power, fitness, signature
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(id) DO UPDATE SET
                                        training_id = excluded.training_id,
                                        name = excluded.name,
                                        description = excluded.description,
                                        power = excluded.power,
                                        fitness = excluded.fitness,
                                        signature = excluded.signature
                                    ''', (
                                        deck_id,
                                        training_id,
                                        deck_name,
                                        deck_description,
                                        deck_power,
                                        deck_fitness,
                                        signature
                                    ))
            self.conn_train.execute(
                "DELETE FROM ai_training_deck_lines WHERE deck_id = ?",
                (deck_id,)
            )
            self.conn_train.executemany('''
                                        INSERT INTO ai_training_deck_lines (deck_id, card_id, position)
                                        VALUES (?, ?, ?)
                                        ''', [
                                            (deck_id, card_id, position)
                                            for position, card_id in enumerate(card_ids)
                                        ])

        try:
            setattr(deck, "id", deck_id)
            setattr(deck, "is_ai", True)
        except Exception:
            pass

        return deck

    @retry
    def load_training_deck(self, deck_id: str) -> Optional["Deck"]:
        from cards.deck import Deck

        cursor = self.conn_train.execute('''
                                         SELECT id, name, description, power, fitness
                                         FROM ai_training_decks
                                         WHERE id = ?
                                         ''', (deck_id,))
        row = cursor.fetchone()
        if not row:
            return None

        deck = Deck()
        deck.id = row["id"]
        deck.name = row["name"] or ""
        deck.description = row["description"] or ""
        deck.power = row["power"] or 0
        deck.neat_fitness = row["fitness"] or 0

        cursor = self.conn_train.execute('''
                                         SELECT card_id
                                         FROM ai_training_deck_lines
                                         WHERE deck_id = ?
                                         ORDER BY position, rowid
                                         ''', (deck_id,))

        for card_row in cursor.fetchall():
            card = self.load_card(card_row["card_id"])
            if card:
                deck.add_card(card)

        return deck

    def _training_match_filter(self, training_id: Optional[int]) -> tuple[str, tuple]:
        if training_id is None:
            return "", ()

        filter_sql = '''
            WHERE genome_1 IN (SELECT guid FROM genome WHERE training_id = ?)
               OR genome_2 IN (SELECT guid FROM genome WHERE training_id = ?)
        '''
        return filter_sql, (training_id, training_id)

    def _legacy_training_deck_ids(self, training_id: Optional[int]) -> set[str]:
        deck_ids = set()
        if training_id is None:
            genome_cursor = self.conn_train.execute("SELECT deck_id FROM genome")
            match_cursor = self.conn_train.execute("SELECT deck_1, deck_2 FROM match_dbt")
        else:
            genome_cursor = self.conn_train.execute(
                "SELECT deck_id FROM genome WHERE training_id = ?",
                (training_id,)
            )
            match_cursor = self.conn_train.execute('''
                                                  SELECT deck_1, deck_2
                                                  FROM match_dbt
                                                  WHERE genome_1 IN (
                                                      SELECT guid FROM genome WHERE training_id = ?
                                                  )
                                                     OR genome_2 IN (
                                                      SELECT guid FROM genome WHERE training_id = ?
                                                  )
                                                  ''', (training_id, training_id))

        for row in genome_cursor.fetchall():
            if row["deck_id"]:
                deck_ids.add(str(row["deck_id"]))

        for row in match_cursor.fetchall():
            if row["deck_1"]:
                deck_ids.add(str(row["deck_1"]))
            if row["deck_2"]:
                deck_ids.add(str(row["deck_2"]))

        ai_training_cursor = self.conn_train.execute("SELECT id FROM ai_training_decks")
        ai_training_ids = {str(row["id"]) for row in ai_training_cursor.fetchall()}
        deck_ids -= ai_training_ids

        deck_cursor = self.conn_decks.cursor()
        if training_id is None:
            deck_cursor.execute("SELECT id FROM decks WHERE COALESCE(is_AI, 0) = 1")
            deck_ids.update(str(row[0]) for row in deck_cursor.fetchall() if row[0])

        if not deck_ids:
            return set()

        placeholders = ",".join("?" for _ in deck_ids)
        deck_cursor.execute(f"SELECT id FROM decks WHERE id IN ({placeholders})", list(deck_ids))
        return {str(row[0]) for row in deck_cursor.fetchall()}

    @retry
    def clear_training_data(
            self,
            training_id: Optional[int] = None,
            delete_legacy_decks: bool = True,
            dry_run: bool = False
    ) -> dict[str, int]:
        match_filter, match_params = self._training_match_filter(training_id)
        legacy_deck_ids = self._legacy_training_deck_ids(training_id) if delete_legacy_decks else set()

        if training_id is None:
            counts = {
                "training": self.conn_train.execute("SELECT COUNT(*) FROM training").fetchone()[0],
                "genome": self.conn_train.execute("SELECT COUNT(*) FROM genome").fetchone()[0],
                "match_dbt": self.conn_train.execute("SELECT COUNT(*) FROM match_dbt").fetchone()[0],
                "pc_match": self.conn_train.execute("SELECT COUNT(*) FROM pc_match").fetchone()[0],
                "ai_training_decks": self.conn_train.execute("SELECT COUNT(*) FROM ai_training_decks").fetchone()[0],
                "legacy_decks": len(legacy_deck_ids),
            }
        else:
            match_guid_query = f"SELECT guid FROM match_dbt {match_filter}"
            counts = {
                "training": self.conn_train.execute(
                    "SELECT COUNT(*) FROM training WHERE id = ?",
                    (training_id,)
                ).fetchone()[0],
                "genome": self.conn_train.execute(
                    "SELECT COUNT(*) FROM genome WHERE training_id = ?",
                    (training_id,)
                ).fetchone()[0],
                "match_dbt": self.conn_train.execute(
                    f"SELECT COUNT(*) FROM match_dbt {match_filter}",
                    match_params
                ).fetchone()[0],
                "pc_match": self.conn_train.execute(
                    f"SELECT COUNT(*) FROM pc_match WHERE match_dbt_guid IN ({match_guid_query})",
                    match_params
                ).fetchone()[0],
                "ai_training_decks": self.conn_train.execute(
                    "SELECT COUNT(*) FROM ai_training_decks WHERE training_id = ?",
                    (training_id,)
                ).fetchone()[0],
                "legacy_decks": len(legacy_deck_ids),
            }

        if dry_run:
            return counts

        with self.conn_train:
            if training_id is None:
                self.conn_train.execute("DELETE FROM pc_match")
                self.conn_train.execute("DELETE FROM match_dbt")
                self.conn_train.execute("DELETE FROM genome")
                self.conn_train.execute("DELETE FROM ai_training_deck_lines")
                self.conn_train.execute("DELETE FROM ai_training_decks")
                self.conn_train.execute("DELETE FROM training")
                self.conn_train.execute(
                    "DELETE FROM sqlite_sequence WHERE name IN ('training', 'pc_match')"
                )
            else:
                match_guid_query = f"SELECT guid FROM match_dbt {match_filter}"
                self.conn_train.execute(
                    f"DELETE FROM pc_match WHERE match_dbt_guid IN ({match_guid_query})",
                    match_params
                )
                self.conn_train.execute(
                    f"DELETE FROM match_dbt {match_filter}",
                    match_params
                )
                self.conn_train.execute(
                    "DELETE FROM genome WHERE training_id = ?",
                    (training_id,)
                )
                self.conn_train.execute('''
                                        DELETE FROM ai_training_deck_lines
                                        WHERE deck_id IN (
                                            SELECT id FROM ai_training_decks WHERE training_id = ?
                                        )
                                        ''', (training_id,))
                self.conn_train.execute(
                    "DELETE FROM ai_training_decks WHERE training_id = ?",
                    (training_id,)
                )
                self.conn_train.execute(
                    "DELETE FROM training WHERE id = ?",
                    (training_id,)
                )

        if delete_legacy_decks:
            self.delete_decks(legacy_deck_ids)

        return counts


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
                                                 INSERT INTO pc_match (
                                                     gen, match_dbt_guid, g1_score, g2_score,
                                                     phase, seed, seat_swap, p1_game_score,
                                                     p2_game_score, winner_id, rounds,
                                                     starting_player_id, deck1_controller_gen,
                                                     deck2_controller_gen, p1_card_plays,
                                                     p2_card_plays, p1_active_ability_uses,
                                                     p2_active_ability_uses
                                                 )
                                                 VALUES (
                                                     :gen, :match_dbt_guid, :g1_score, :g2_score,
                                                     :phase, :seed, :seat_swap, :p1_game_score,
                                                     :p2_game_score, :winner_id, :rounds,
                                                     :starting_player_id, :deck1_controller_gen,
                                                     :deck2_controller_gen, :p1_card_plays,
                                                     :p2_card_plays, :p1_active_ability_uses,
                                                     :p2_active_ability_uses
                                                 )
                                                 ''', asdict(pc_match))
                pc_match.id = cursor.lastrowid
            else:
                self.conn_train.execute('''
                                        UPDATE pc_match
                                        SET gen = :gen,
                                            match_dbt_guid = :match_dbt_guid,
                                            g1_score = :g1_score,
                                            g2_score = :g2_score,
                                            phase = :phase,
                                            seed = :seed,
                                            seat_swap = :seat_swap,
                                            p1_game_score = :p1_game_score,
                                            p2_game_score = :p2_game_score,
                                            winner_id = :winner_id,
                                            rounds = :rounds,
                                            starting_player_id = :starting_player_id,
                                            deck1_controller_gen = :deck1_controller_gen,
                                            deck2_controller_gen = :deck2_controller_gen,
                                            p1_card_plays = :p1_card_plays,
                                            p2_card_plays = :p2_card_plays,
                                            p1_active_ability_uses = :p1_active_ability_uses,
                                            p2_active_ability_uses = :p2_active_ability_uses
                                        WHERE id = :id
                                        ''', asdict(pc_match))
        return pc_match

    @retry
    def save_pc_matches(self, pc_matches: list[PCMatch]) -> None:
        if not pc_matches:
            return
        rows = [asdict(pc_match) for pc_match in pc_matches]
        with self.conn_train:
            self.conn_train.executemany('''
                                        INSERT INTO pc_match (
                                            gen, match_dbt_guid, g1_score, g2_score,
                                            phase, seed, seat_swap, p1_game_score,
                                            p2_game_score, winner_id, rounds,
                                            starting_player_id, deck1_controller_gen,
                                            deck2_controller_gen, p1_card_plays,
                                            p2_card_plays, p1_active_ability_uses,
                                            p2_active_ability_uses
                                        )
                                        VALUES (
                                            :gen, :match_dbt_guid, :g1_score, :g2_score,
                                            :phase, :seed, :seat_swap, :p1_game_score,
                                            :p2_game_score, :winner_id, :rounds,
                                            :starting_player_id, :deck1_controller_gen,
                                            :deck2_controller_gen, :p1_card_plays,
                                            :p2_card_plays, :p1_active_ability_uses,
                                            :p2_active_ability_uses
                                        )
                                        ''', rows)

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

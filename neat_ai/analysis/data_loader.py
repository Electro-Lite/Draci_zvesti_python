import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd


PROJECT_ROOT_NAME = "Draci_zvesti_merged"
ANALYSIS_TRAINING_ID: int | None = 10


def set_analysis_training_id(training_id: int | None) -> None:
    """Set a global training filter for all analysis loaders."""
    global ANALYSIS_TRAINING_ID
    ANALYSIS_TRAINING_ID = None if training_id is None else int(training_id)


def get_analysis_training_id() -> int | None:
    """Return the global training filter used by analysis loaders."""
    return ANALYSIS_TRAINING_ID


def get_project_root(start: Path | None = None) -> Path:
    """Find the project root from an analysis module or notebook path."""
    current_dir = (start or Path(__file__)).resolve()
    if current_dir.is_file():
        current_dir = current_dir.parent

    for candidate in (current_dir, *current_dir.parents):
        has_train_db = (candidate / "train.db").exists()
        has_decks_db = (
            (candidate / "utils" / "decks.db").exists()
            or (candidate / "decks.db").exists()
        )
        if has_train_db and has_decks_db:
            return candidate
        if candidate.name == PROJECT_ROOT_NAME:
            return candidate

    raise FileNotFoundError("Could not locate the project root from analysis files.")


def get_db_paths() -> tuple[Path, Path]:
    """Locate the training and deck databases used by the analysis layer."""
    project_root = get_project_root()
    train_db_path = project_root / "train.db"
    decks_db_path = project_root / "utils" / "decks.db"

    if not decks_db_path.exists():
        decks_db_path = project_root / "decks.db"

    return train_db_path, decks_db_path


def _sqlite_path(path: Path) -> str:
    return str(path).replace("'", "''")


def _has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    cursor = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    return any(
        row[1] == column_name
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    )


def deck_source_ctes(
    conn: sqlite3.Connection,
    training_id: int | None = None,
) -> str:
    if training_id is not None:
        if _has_table(conn, "ai_training_decks"):
            return """
                WITH filtered_genomes AS (
                    SELECT guid, gen, deck_id, score, training_id
                    FROM genome
                    WHERE training_id = :analysis_training_id
                ),
                filtered_deck_ids AS (
                    SELECT DISTINCT deck_id
                    FROM filtered_genomes
                    UNION
                    SELECT id AS deck_id
                    FROM ai_training_decks
                    WHERE training_id = :analysis_training_id
                ),
                all_decks AS (
                    SELECT id, name, signature
                    FROM ai_training_decks
                    WHERE training_id = :analysis_training_id
                    UNION ALL
                    SELECT d.id, d.name, d.signature
                    FROM deckdb.decks d
                    JOIN filtered_deck_ids fd
                        ON fd.deck_id = d.id
                    WHERE NOT EXISTS (
                        SELECT 1 FROM ai_training_decks a WHERE a.id = d.id
                    )
                ),
                all_deck_lines AS (
                    SELECT deck_id, card_id, position
                    FROM ai_training_deck_lines
                    WHERE deck_id IN (
                        SELECT id
                        FROM ai_training_decks
                        WHERE training_id = :analysis_training_id
                    )
                    UNION ALL
                    SELECT d.id AS deck_id, dl.card_id, dl.rowid AS position
                    FROM deckdb.decks d
                    JOIN filtered_deck_ids fd
                        ON fd.deck_id = d.id
                    JOIN deckdb.deck_lines dl
                        ON dl.signature = d.signature
                    WHERE NOT EXISTS (
                        SELECT 1 FROM ai_training_decks a WHERE a.id = d.id
                    )
                )
            """

        return """
            WITH filtered_genomes AS (
                SELECT guid, gen, deck_id, score, training_id
                FROM genome
                WHERE training_id = :analysis_training_id
            ),
            filtered_deck_ids AS (
                SELECT DISTINCT deck_id
                FROM filtered_genomes
            ),
            all_decks AS (
                SELECT d.id, d.name, d.signature
                FROM deckdb.decks d
                JOIN filtered_deck_ids fd
                    ON fd.deck_id = d.id
            ),
            all_deck_lines AS (
                SELECT d.id AS deck_id, dl.card_id, dl.rowid AS position
                FROM deckdb.decks d
                JOIN filtered_deck_ids fd
                    ON fd.deck_id = d.id
                JOIN deckdb.deck_lines dl
                    ON dl.signature = d.signature
            )
        """

    if _has_table(conn, "ai_training_decks"):
        return """
            WITH all_decks AS (
                SELECT id, name, signature
                FROM ai_training_decks
                UNION ALL
                SELECT d.id, d.name, d.signature
                FROM deckdb.decks d
                WHERE NOT EXISTS (
                    SELECT 1 FROM ai_training_decks a WHERE a.id = d.id
                )
            ),
            all_deck_lines AS (
                SELECT deck_id, card_id, position
                FROM ai_training_deck_lines
                UNION ALL
                SELECT d.id AS deck_id, dl.card_id, dl.rowid AS position
                FROM deckdb.decks d
                JOIN deckdb.deck_lines dl
                    ON dl.signature = d.signature
                WHERE NOT EXISTS (
                    SELECT 1 FROM ai_training_decks a WHERE a.id = d.id
                )
            )
        """

    return """
        WITH all_decks AS (
            SELECT id, name, signature
            FROM deckdb.decks
        ),
        all_deck_lines AS (
            SELECT d.id AS deck_id, dl.card_id, dl.rowid AS position
            FROM deckdb.decks d
            JOIN deckdb.deck_lines dl
                ON dl.signature = d.signature
        )
    """


@contextmanager
def training_connection(read_only: bool = True) -> Iterator[sqlite3.Connection]:
    """
    Open train.db and attach decks.db as the `deckdb` schema.

    The default read-only connection prevents notebook analysis from mutating the
    training database by accident.
    """
    train_path, decks_path = get_db_paths()
    if read_only:
        conn = sqlite3.connect(f"file:{train_path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(train_path))

    conn.row_factory = sqlite3.Row
    conn.execute(f"ATTACH DATABASE '{_sqlite_path(decks_path)}' AS deckdb")
    try:
        yield conn
    finally:
        conn.close()


def load_master_df() -> pd.DataFrame:
    """
    Pulls data from train.db and decks.db, merging them into a single Master DataFrame.
    Returns a DataFrame with columns: gen, deck_id, score, card_id, signature, etc.
    """
    training_id = get_analysis_training_id()
    params = (
        {"analysis_training_id": training_id}
        if training_id is not None
        else None
    )
    genome_source = "filtered_genomes" if training_id is not None else "genome"

    with training_connection() as conn:
        query = f"""
        {deck_source_ctes(conn, training_id=training_id)}
        SELECT
            g.guid,
            g.gen,
            g.deck_id,
            g.score,
            g.training_id,
            d.id,
            d.name,
            d.name AS deck_name,
            d.signature,
            dl.card_id
        FROM {genome_source} g
        JOIN all_decks d
            ON d.id = g.deck_id
        JOIN all_deck_lines dl
            ON dl.deck_id = d.id
        WHERE g.score IS NOT NULL
        ORDER BY g.gen, g.guid, dl.position
    """
        return pd.read_sql_query(query, conn, params=params)


def load_deck_compositions() -> pd.DataFrame:
    """Return one row per saved deck with its card composition."""
    training_id = get_analysis_training_id()
    params = (
        {"analysis_training_id": training_id}
        if training_id is not None
        else None
    )

    with training_connection() as conn:
        query = f"""
        {deck_source_ctes(conn, training_id=training_id)},
        ordered_lines AS (
            SELECT deck_id, card_id
            FROM all_deck_lines
            ORDER BY deck_id, position
        )
        SELECT
            d.id AS deck_id,
            d.name AS deck_name,
            d.signature,
            COUNT(ol.card_id) AS card_count,
            GROUP_CONCAT(ol.card_id, ', ') AS composition
        FROM all_decks d
        LEFT JOIN ordered_lines ol
            ON ol.deck_id = d.id
        GROUP BY d.id, d.name, d.signature
        ORDER BY d.id
    """
        return pd.read_sql_query(query, conn, params=params)


def load_matchup_df(
    aggregate: bool = True,
    include_inner_generation: bool = False,
    outer_gen: int | None = None,
    inner_gen: int | None = None,
    phase: str | None = "auto",
) -> pd.DataFrame:
    """
    Load deck-vs-deck matchup data.

    By default this returns SQL-aggregated rows instead of materializing every
    `pc_match` sample. Set `aggregate=False` only for targeted debugging.
    """
    filters = []
    params = {}
    training_id = get_analysis_training_id()
    match_joins = ""
    if training_id is not None:
        match_joins = """
            JOIN genome g1
                ON m.genome_1 = g1.guid
            JOIN genome g2
                ON m.genome_2 = g2.guid
        """
        filters.append("g1.training_id = :analysis_training_id")
        filters.append("g2.training_id = :analysis_training_id")
        params["analysis_training_id"] = training_id
    if outer_gen is not None:
        filters.append("m.gen = :outer_gen")
        params["outer_gen"] = outer_gen
    if inner_gen is not None:
        filters.append("p.gen = :inner_gen")
        params["inner_gen"] = inner_gen
    with training_connection() as conn:
        if phase is not None and has_column(conn, "pc_match", "phase"):
            selected_phase = phase
            if phase == "auto":
                base_where = f"WHERE {' AND '.join(filters)}" if filters else "WHERE 1=1"
                holdout_query = f"""
                    SELECT 1
                    FROM pc_match p
                    JOIN match_dbt m ON p.match_dbt_guid = m.guid
                    {match_joins}
                    {base_where}
                      AND COALESCE(p.phase, 'training') = 'holdout'
                    LIMIT 1
                """
                selected_phase = (
                    "holdout"
                    if conn.execute(holdout_query, params).fetchone() is not None
                    else "training"
                )
            filters.append("COALESCE(p.phase, 'training') = :phase")
            params["phase"] = selected_phase
        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

        if aggregate:
            inner_select = ", p.gen AS inner_gen" if include_inner_generation else ""
            inner_group = ", p.gen" if include_inner_generation else ""
            query = f"""
            SELECT
                m.deck_1,
                m.deck_2,
                m.gen,
                m.gen AS outer_gen
                {inner_select},
                COUNT(*) AS sample_count,
                AVG(p.g1_score) AS g1_score,
                AVG(p.g2_score) AS g2_score,
                AVG(p.g1_score) AS avg_g1_score,
                AVG(p.g2_score) AS avg_g2_score
            FROM pc_match p
            JOIN match_dbt m
                ON p.match_dbt_guid = m.guid
            {match_joins}
            {where_sql}
            GROUP BY m.deck_1, m.deck_2, m.gen{inner_group}
            ORDER BY m.gen, m.deck_1, m.deck_2
        """
        else:
            query = f"""
            SELECT
                m.deck_1,
                m.deck_2,
                m.gen,
                m.gen AS outer_gen,
                p.gen AS inner_gen,
                p.g1_score,
                p.g2_score
            FROM pc_match p
            JOIN match_dbt m
                ON p.match_dbt_guid = m.guid
            {match_joins}
            {where_sql}
            ORDER BY m.gen, m.deck_1, m.deck_2, p.gen
        """
        return pd.read_sql_query(query, conn, params=params)


def load_outer_match_df() -> pd.DataFrame:
    """Load outer deck-builder match rows, including self-match placeholders."""
    training_id = get_analysis_training_id()
    params = {}
    match_joins = ""
    where_sql = ""
    if training_id is not None:
        match_joins = """
            JOIN genome g1
                ON m.genome_1 = g1.guid
            JOIN genome g2
                ON m.genome_2 = g2.guid
        """
        where_sql = """
            WHERE g1.training_id = :analysis_training_id
              AND g2.training_id = :analysis_training_id
        """
        params["analysis_training_id"] = training_id

    query = f"""
        SELECT
            m.guid,
            m.genome_1,
            m.genome_2,
            m.deck_1,
            m.deck_2,
            m.gen,
            m.gen AS outer_gen,
            m.result
        FROM match_dbt m
        {match_joins}
        {where_sql}
        ORDER BY m.gen, m.guid
    """
    with training_connection() as conn:
        return pd.read_sql_query(query, conn, params=params or None)


def ensure_analysis_indexes() -> None:
    """
    Create optional SQLite indexes useful for repeated notebook analysis.

    This intentionally is not called automatically because it mutates train.db.
    """
    with training_connection(read_only=False) as conn:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pc_match_guid ON pc_match(match_dbt_guid)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pc_match_gen ON pc_match(gen)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_match_dbt_gen ON match_dbt(gen)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS deckdb.idx_decks_signature ON decks(signature)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS deckdb.idx_deck_lines_signature "
            "ON deck_lines(signature)"
        )
        conn.commit()

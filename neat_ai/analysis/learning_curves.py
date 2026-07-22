import pandas as pd

from .data_loader import (
    deck_source_ctes,
    get_analysis_training_id,
    load_deck_compositions,
    training_connection,
)


LEARNING_CURVE_COLUMNS = [
    "signature",
    "deck_id",
    "deck_name",
    "composition",
    "outer_gen",
    "gen",
    "inner_gen",
    "sample_count",
    "score",
]

HIGH_SKILL_COLUMNS = [
    "signature",
    "deck_id",
    "deck_name",
    "composition",
    "outer_gen",
    "learning_slope",
    "fitness_delta",
    "gens_active",
    "mean_score",
    "sample_count",
]


def _weighted_average_score(df: pd.DataFrame) -> float:
    sample_count = df["sample_count"].sum()
    if sample_count == 0:
        return float("nan")
    return float((df["score"] * df["sample_count"]).sum() / sample_count)


def _linear_slope(df: pd.DataFrame) -> float:
    ordered = df.sort_values("inner_gen")
    x = ordered["inner_gen"].astype(float)
    y = ordered["score"].astype(float)

    if len(ordered) < 2 or x.nunique() < 2:
        return 0.0

    x_delta = x - x.mean()
    denominator = float((x_delta ** 2).sum())
    if denominator == 0:
        return 0.0

    return float((x_delta * (y - y.mean())).sum() / denominator)


def load_deck_learning_curves(
    signature: str | None = None,
    outer_gen: int | None = None,
) -> pd.DataFrame:
    """
    Return inner player-controller learning curves from each deck's perspective.

    `gen` is kept as an alias for `inner_gen` so existing notebook cells can use
    the same x-axis name while the data still makes the generation meaning clear.
    """
    filters = []
    params = {}
    if signature:
        filters.append("d.signature = :signature")
        params["signature"] = signature
    if outer_gen is not None:
        filters.append("ds.outer_gen = :outer_gen")
        params["outer_gen"] = outer_gen
    training_id = get_analysis_training_id()
    match_joins = ""
    match_where = ""
    if training_id is not None:
        params["analysis_training_id"] = training_id
        match_joins = """
            JOIN genome g1
                ON m.genome_1 = g1.guid
            JOIN genome g2
                ON m.genome_2 = g2.guid
        """
        match_where = """
            WHERE g1.training_id = :analysis_training_id
              AND g2.training_id = :analysis_training_id
        """
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    with training_connection() as conn:
        query = f"""
        {deck_source_ctes(conn, training_id=training_id)},
        match_scores AS (
            SELECT
                m.guid,
                m.deck_1,
                m.deck_2,
                m.gen AS outer_gen,
                p.gen AS inner_gen,
                COUNT(*) AS sample_count,
                AVG(p.g1_score) AS avg_g1_score,
                AVG(p.g2_score) AS avg_g2_score
            FROM pc_match p
            JOIN match_dbt m
                ON p.match_dbt_guid = m.guid
            {match_joins}
            {match_where}
            GROUP BY m.guid, m.deck_1, m.deck_2, p.gen
        ),
        deck_scores AS (
            SELECT
                deck_1 AS deck_id,
                outer_gen,
                inner_gen,
                sample_count,
                avg_g1_score AS score
            FROM match_scores
            UNION ALL
            SELECT
                deck_2 AS deck_id,
                outer_gen,
                inner_gen,
                sample_count,
                avg_g2_score AS score
            FROM match_scores
        )
        SELECT
            d.signature,
            MIN(ds.deck_id) AS deck_id,
            MIN(d.name) AS deck_name,
            ds.outer_gen,
            ds.inner_gen AS gen,
            ds.inner_gen,
            SUM(ds.sample_count) AS sample_count,
            SUM(ds.score * ds.sample_count) / SUM(ds.sample_count) AS score
        FROM deck_scores ds
        JOIN all_decks d
            ON d.id = ds.deck_id
        {where_clause}
        GROUP BY d.signature, ds.outer_gen, ds.inner_gen
        ORDER BY d.signature, ds.outer_gen, ds.inner_gen
    """
        curves = pd.read_sql_query(query, conn, params=params or None)

    if curves.empty:
        return pd.DataFrame(columns=LEARNING_CURVE_COLUMNS)

    compositions = load_deck_compositions()[["signature", "composition"]].drop_duplicates(
        "signature"
    )
    curves = curves.merge(compositions, on="signature", how="left")

    return curves[LEARNING_CURVE_COLUMNS]


def get_deck_trajectory(
    signature: str,
    outer_gen: int | None = None,
) -> pd.DataFrame:
    """Return the inner-generation score trajectory for a deck signature."""
    return load_deck_learning_curves(signature=signature, outer_gen=outer_gen)


def get_high_skill_decks(
    min_gens: int = 3,
    min_samples: int = 100,
    outer_gen: int | None = None,
) -> pd.DataFrame:
    """
    Rank deck archetypes by how much their controllers improve during evaluation.

    The slope and delta are computed across inner evaluator generations, not
    outer deck-builder generations.
    """
    curves = load_deck_learning_curves(outer_gen=outer_gen)
    if curves.empty:
        return pd.DataFrame(columns=HIGH_SKILL_COLUMNS)

    rows = []
    for (signature, group_outer_gen), group in curves.groupby(
        ["signature", "outer_gen"],
        sort=False,
    ):
        group = group.sort_values("inner_gen")
        sample_count = int(group["sample_count"].sum())
        gens_active = int(group["inner_gen"].nunique())
        if gens_active < min_gens or sample_count < min_samples:
            continue

        rows.append(
            {
                "signature": signature,
                "deck_id": group["deck_id"].iloc[0],
                "deck_name": group["deck_name"].iloc[0],
                "composition": group["composition"].iloc[0],
                "outer_gen": int(group_outer_gen),
                "learning_slope": _linear_slope(group),
                "fitness_delta": float(group["score"].iloc[-1] - group["score"].iloc[0]),
                "gens_active": gens_active,
                "mean_score": _weighted_average_score(group),
                "sample_count": sample_count,
            }
        )

    if not rows:
        return pd.DataFrame(columns=HIGH_SKILL_COLUMNS)

    result = pd.DataFrame(rows)
    return result.sort_values(
        ["learning_slope", "fitness_delta", "mean_score"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

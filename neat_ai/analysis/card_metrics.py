import pandas as pd

from .data_loader import load_master_df, load_matchup_df


def _genome_card_rows(outer_gen: int | None = None) -> pd.DataFrame:
    """Return one row per genome/card, preserving duplicate count separately."""
    df = load_master_df()

    if df.empty:
        return pd.DataFrame(
            columns=["guid", "gen", "deck_id", "card_id", "score", "copies"]
        )

    if outer_gen is not None:
        df = df[df["gen"] == outer_gen]
        if df.empty:
            return pd.DataFrame(
                columns=["guid", "gen", "deck_id", "card_id", "score", "copies"]
            )

    return (
        df.groupby(["guid", "gen", "deck_id", "card_id"], as_index=False)
        .agg(
            score=("score", "first"),
            copies=("card_id", "size"),
        )
    )


def _empty_tier_list() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "card_id",
            "average_score",
            "times_played",
            "total_decks",
            "pick_rate",
            "total_copies",
            "average_copies",
            "copy_rate",
            "generations_survived",
        ]
    )


def _empty_match_power_rating() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "outer_gen",
            "inner_gen",
            "card_id",
            "power_rating",
            "average_score",
            "times_played",
            "total_decks",
            "pick_rate",
            "total_copies",
            "average_copies",
            "copy_rate",
            "match_samples",
        ]
    )


def get_card_tier_list(outer_gen: int | None = None) -> pd.DataFrame:
    """Calculate per-card score, usage, and copy-count metrics."""
    df = _genome_card_rows(outer_gen=outer_gen)
    if df.empty:
        return _empty_tier_list()

    total_decks = df["guid"].nunique()

    metrics = df.groupby('card_id').agg(
        average_score=('score', 'mean'),
        times_played=('guid', 'nunique'), 
        total_copies=('copies', 'sum'),
        average_copies=('copies', 'mean'),
        generations_survived=('gen', 'nunique')
    ).reset_index()

    metrics["total_decks"] = total_decks
    metrics["pick_rate"] = metrics["times_played"] / total_decks
    metrics["copy_rate"] = metrics["total_copies"] / total_decks
    if outer_gen is not None:
        metrics["outer_gen"] = outer_gen

    return metrics.sort_values(by='average_score', ascending=False)


def get_card_tier_list_by_generation() -> pd.DataFrame:
    """Calculate per-card metrics separately for each deck-builder generation."""
    df = _genome_card_rows()
    if df.empty:
        return _empty_tier_list().assign(outer_gen=pd.Series(dtype="int64"))

    total_decks = (
        df.groupby("gen", as_index=False)
        .agg(total_decks=("guid", "nunique"))
        .rename(columns={"gen": "outer_gen"})
    )
    metrics = (
        df.groupby(["gen", "card_id"], as_index=False)
        .agg(
            average_score=("score", "mean"),
            times_played=("guid", "nunique"),
            total_copies=("copies", "sum"),
            average_copies=("copies", "mean"),
        )
        .rename(columns={"gen": "outer_gen"})
    )
    metrics = metrics.merge(total_decks, on="outer_gen", how="left")
    metrics["pick_rate"] = metrics["times_played"] / metrics["total_decks"]
    metrics["copy_rate"] = metrics["total_copies"] / metrics["total_decks"]
    metrics["generations_survived"] = 1
    return metrics.sort_values(
        ["outer_gen", "average_score"],
        ascending=[True, False],
    ).reset_index(drop=True)


def _add_power_rating(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    # Min-Max Normalization (Scales values between 0 and 1)
    # This prevents a massive fitness score from entirely overwriting popularity.
    score_min = df['average_score'].min()
    score_max = df['average_score'].max()
    df['normalized_score'] = (df['average_score'] - score_min) / (score_max - score_min) if score_max != score_min else 0.5

    pick_min = df['pick_rate'].min()
    pick_max = df['pick_rate'].max()
    df['normalized_pick'] = (df['pick_rate'] - pick_min) / (pick_max - pick_min) if pick_max != pick_min else 0.5

    # Calculate Power Rating (Scale to 100)
    # 70% weight on deck fitness, 30% weight on generation-local pick rate.
    df['power_rating'] = ((df['normalized_score'] * 0.7) + (df['normalized_pick'] * 0.3)) * 100
    df['power_rating'] = df['power_rating'].round(1)
    return df


def _power_rating_columns(df: pd.DataFrame) -> list[str]:
    columns = [
        'card_id',
        'power_rating',
        'average_score',
        'times_played',
        'total_decks',
        'pick_rate',
        'total_copies',
        'average_copies',
        'copy_rate',
    ]
    if "outer_gen" in df.columns:
        columns.insert(0, "outer_gen")
    return columns


def get_card_power_rating(
    min_times_played: int = 3,
    outer_gen: int | None = None,
) -> pd.DataFrame:
    """
    Calculates a 0-100 Power Rating based on a weighted combination of 
    a card's average fitness contribution (70%) and its pick rate (30%).
    """
    df = get_card_tier_list(outer_gen=outer_gen)

    df = df[df['times_played'] >= min_times_played].copy()

    if df.empty:
        return df

    df = _add_power_rating(df)
    df = df.sort_values(by='power_rating', ascending=False)

    return df[_power_rating_columns(df)]


def get_card_power_rating_by_generation(
    min_times_played: int = 1,
) -> pd.DataFrame:
    """Calculate card power ratings independently inside each outer generation."""
    tier_list = get_card_tier_list_by_generation()
    if tier_list.empty:
        return tier_list

    tier_list = tier_list[tier_list["times_played"] >= min_times_played].copy()
    if tier_list.empty:
        return tier_list

    rated = pd.concat(
        [_add_power_rating(group) for _, group in tier_list.groupby("outer_gen")],
        ignore_index=True,
    )

    return rated[_power_rating_columns(rated)].sort_values(
        ["outer_gen", "power_rating"],
        ascending=[True, False],
    ).reset_index(drop=True)


def get_card_match_power_rating(
    outer_gen: int,
    inner_gen: int,
    min_times_played: int = 1,
) -> pd.DataFrame:
    """
    Estimate card power from match scores for one deck-builder generation and
    one evaluator/controller generation.

    `outer_gen` selects when the decks were built. `inner_gen` selects how
    trained the player controllers were when piloting those decks.
    """
    card_rows = _genome_card_rows(outer_gen=outer_gen)
    matchups = load_matchup_df(outer_gen=outer_gen, inner_gen=inner_gen)

    if card_rows.empty or matchups.empty:
        return _empty_match_power_rating()

    perspective_rows = pd.concat(
        [
            matchups.rename(
                columns={"deck_1": "deck_id", "g1_score": "match_score"}
            )[["deck_id", "match_score", "sample_count"]],
            matchups.rename(
                columns={"deck_2": "deck_id", "g2_score": "match_score"}
            )[["deck_id", "match_score", "sample_count"]],
        ],
        ignore_index=True,
    )
    perspective_rows["weighted_score"] = (
        perspective_rows["match_score"] * perspective_rows["sample_count"]
    )
    deck_scores = (
        perspective_rows.groupby("deck_id", as_index=False)
        .agg(
            weighted_score=("weighted_score", "sum"),
            match_samples=("sample_count", "sum"),
        )
    )
    deck_scores["deck_match_score"] = (
        deck_scores["weighted_score"] / deck_scores["match_samples"]
    )

    card_rows = card_rows.merge(deck_scores, on="deck_id", how="inner")
    if card_rows.empty:
        return _empty_match_power_rating()

    total_decks = deck_scores["deck_id"].nunique()
    card_rows["weighted_card_score"] = (
        card_rows["deck_match_score"] * card_rows["match_samples"]
    )
    metrics = (
        card_rows.groupby("card_id", as_index=False)
        .agg(
            weighted_card_score=("weighted_card_score", "sum"),
            match_samples=("match_samples", "sum"),
            times_played=("deck_id", "nunique"),
            total_copies=("copies", "sum"),
            average_copies=("copies", "mean"),
        )
    )
    metrics = metrics[metrics["times_played"] >= min_times_played].copy()
    if metrics.empty:
        return _empty_match_power_rating()

    metrics["average_score"] = (
        metrics["weighted_card_score"] / metrics["match_samples"]
    )
    metrics["total_decks"] = total_decks
    metrics["pick_rate"] = metrics["times_played"] / total_decks
    metrics["copy_rate"] = metrics["total_copies"] / total_decks
    metrics["outer_gen"] = outer_gen
    metrics["inner_gen"] = inner_gen
    metrics = _add_power_rating(metrics)

    return metrics[
        [
            "outer_gen",
            "inner_gen",
            "card_id",
            "power_rating",
            "average_score",
            "times_played",
            "total_decks",
            "pick_rate",
            "total_copies",
            "average_copies",
            "copy_rate",
            "match_samples",
        ]
    ].sort_values("power_rating", ascending=False).reset_index(drop=True)

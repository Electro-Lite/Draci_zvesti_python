import pandas as pd

from .data_loader import load_deck_compositions, load_matchup_df


def _weighted_pair_scores(df: pd.DataFrame) -> pd.DataFrame:
    weighted = df.copy()
    weighted["weighted_g1_score"] = weighted["g1_score"] * weighted["sample_count"]

    grouped = weighted.groupby(["deck_1", "deck_2"], as_index=False).agg(
        weighted_g1_score=("weighted_g1_score", "sum"),
        sample_count=("sample_count", "sum"),
    )
    grouped["g1_score"] = grouped["weighted_g1_score"] / grouped["sample_count"]
    return grouped[["deck_1", "deck_2", "g1_score", "sample_count"]]


def get_matchup_matrix_with_cards(
    outer_gen: int | None = None,
    inner_gen: int | None = None,
    min_samples: int = 1,
):
    """
    Returns the matchup matrix dataframe alongside dictionaries mapping 
    deck IDs to human-readable string representations of their card lines.
    """
    df_matchups = load_matchup_df(outer_gen=outer_gen, inner_gen=inner_gen)
    deck_compositions = load_deck_compositions()

    if min_samples > 1 and not df_matchups.empty:
        df_matchups = df_matchups[df_matchups["sample_count"] >= min_samples]

    if df_matchups.empty or deck_compositions.empty:
        return pd.DataFrame(), {}

    deck_card_map = (
        deck_compositions.set_index("deck_id")["composition"]
        .to_dict()
    )

    matchup_group = _weighted_pair_scores(df_matchups)
    matrix = matchup_group.pivot(
        index="deck_1",
        columns="deck_2",
        values="g1_score",
    ).fillna(0)

    return matrix, deck_card_map


def get_matchup_summary(
    outer_gen: int | None = None,
    inner_gen: int | None = None,
) -> pd.DataFrame:
    """Return weighted matchup scores with deck composition columns."""
    df_matchups = load_matchup_df(outer_gen=outer_gen, inner_gen=inner_gen)
    if df_matchups.empty:
        return df_matchups

    summary = _weighted_pair_scores(df_matchups)
    compositions = load_deck_compositions()[["deck_id", "composition"]]
    summary = summary.merge(
        compositions.rename(
            columns={"deck_id": "deck_1", "composition": "deck_1_composition"}
        ),
        on="deck_1",
        how="left",
    )
    summary = summary.merge(
        compositions.rename(
            columns={"deck_id": "deck_2", "composition": "deck_2_composition"}
        ),
        on="deck_2",
        how="left",
    )
    return summary.sort_values("g1_score", ascending=False).reset_index(drop=True)

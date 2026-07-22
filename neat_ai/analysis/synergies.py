from itertools import combinations

import pandas as pd

from .data_loader import load_master_df


def get_card_synergies(
    percentile: float = 0.85,
    min_co_occurrences: int = 1,
) -> pd.DataFrame:
    """
    Finds card synergies by identifying pairs of cards that frequently co-occur 
    in highly successful decks (above the specified percentile threshold).
    """
    df = load_master_df()
    if df.empty:
        return pd.DataFrame(columns=["card_A", "card_B", "co_occurrences"])

    deck_scores = df[["guid", "signature", "score"]].drop_duplicates()
    threshold = deck_scores["score"].quantile(percentile)
    successful_signatures = deck_scores.loc[
        deck_scores["score"] >= threshold,
        "signature",
    ].unique()

    successful_df = df[df["signature"].isin(successful_signatures)]
    deck_cards = successful_df.groupby("signature")["card_id"].apply(list)

    co_occurrence = {}

    for cards in deck_cards:
        unique_cards = sorted(list(set(cards)))
        for pair in combinations(unique_cards, 2):
            co_occurrence[pair] = co_occurrence.get(pair, 0) + 1

    synergy_list = [
        {'card_A': pair[0], 'card_B': pair[1], 'co_occurrences': count}
        for pair, count in co_occurrence.items()
        if count >= min_co_occurrences
    ]

    synergy_df = pd.DataFrame(synergy_list)

    if not synergy_df.empty:
        synergy_df = synergy_df.sort_values(by='co_occurrences', ascending=False)

    return synergy_df

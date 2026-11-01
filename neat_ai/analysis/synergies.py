"""Model-adjusted card-combination synergy metrics.

Synergy means that a combination performs better than the sum of its cards'
independently estimated contributions. It is not raw co-occurrence among
successful decks.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from .data_loader import load_master_df


RESULT_COLUMNS = [
    "generation_group", "combo_type", "combo", "card_A", "card_B", "card_C",
    "appearances", "total_decks", "combo_pick_rate", "observed_score",
    "additive_expected_score", "excess_score", "constituent_interaction",
    "unique_excess_score", "standard_error", "synergy_score",
]


def _generation_labels(generations: list[int], group_count: int) -> dict[int, str]:
    if not generations:
        return {}
    group_count = max(1, min(int(group_count), len(generations)))
    chunks = np.array_split(np.asarray(generations, dtype=int), group_count)
    prefixes = ["early", "mid", "late"] if group_count == 3 else []
    labels: dict[int, str] = {}
    for index, chunk in enumerate(chunks):
        start, end = int(chunk[0]), int(chunk[-1])
        prefix = prefixes[index] if prefixes else f"group {index + 1}"
        label = f"{prefix} (gen {start})" if start == end else f"{prefix} (gen {start}-{end})"
        labels.update({int(generation): label for generation in chunk})
    return labels


def _deck_table(master: pd.DataFrame, group_count: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"guid", "gen", "deck_id", "score", "card_id"}
    missing = required.difference(master.columns)
    if missing:
        raise ValueError(f"Master data is missing columns: {', '.join(sorted(missing))}")
    decks = master[["guid", "gen", "deck_id", "score"]].drop_duplicates("guid").copy()
    decks = decks.rename(columns={"gen": "outer_gen"}).reset_index(drop=True)
    copies = pd.crosstab(master["guid"], master["card_id"])
    copies = copies.reindex(decks["guid"], fill_value=0).reset_index(drop=True)
    labels = _generation_labels(sorted(decks["outer_gen"].astype(int).unique()), group_count)
    decks["generation_group"] = decks["outer_gen"].astype(int).map(labels)
    return decks, copies


def _additive_predictions(decks: pd.DataFrame, copies: pd.DataFrame, ridge_alpha: float) -> np.ndarray:
    """Fit card-copy main effects plus exact-generation fixed effects."""
    generation_terms = pd.get_dummies(
        decks["outer_gen"].astype(str), prefix="gen", drop_first=True, dtype=float
    )
    matrix = np.column_stack([
        np.ones(len(decks), dtype=float),
        copies.to_numpy(dtype=float),
        generation_terms.to_numpy(dtype=float),
    ])
    target = decks["score"].to_numpy(dtype=float)
    penalty = np.eye(matrix.shape[1], dtype=float) * max(0.0, float(ridge_alpha))
    penalty[0, 0] = 0.0
    coefficients = np.linalg.pinv(matrix.T @ matrix + penalty) @ matrix.T @ target
    return matrix @ coefficients


def _combo_label(combo_type: str, cards: tuple[str, ...]) -> str:
    if combo_type == "duplicate":
        return f"2× {cards[0]}"
    if combo_type == "duplicate_pair":
        return f"2× {cards[0]} + {cards[1]}"
    return " + ".join(cards)


def _candidate_masks(copies: pd.DataFrame, max_combo_size: int):
    present = copies.gt(0)
    active_cards = sorted(str(card) for card in copies.columns if present[card].any())
    for card_a, card_b in combinations(active_cards, 2):
        yield "pair", (card_a, card_b), (present[card_a] & present[card_b]).to_numpy()
    for card in active_cards:
        yield "duplicate", (card,), copies[card].ge(2).to_numpy()
    if max_combo_size < 3:
        return
    for cards in combinations(active_cards, 3):
        mask = present[cards[0]] & present[cards[1]] & present[cards[2]]
        yield "triple", cards, mask.to_numpy()
    for duplicate_card in active_cards:
        doubled = copies[duplicate_card].ge(2)
        for other_card in active_cards:
            if other_card != duplicate_card:
                yield (
                    "duplicate_pair", (duplicate_card, other_card),
                    (doubled & present[other_card]).to_numpy(),
                )


def estimate_card_combo_synergies(
    master: pd.DataFrame,
    group_count: int = 3,
    min_appearances: int = 10,
    max_combo_size: int = 3,
    ridge_alpha: float = 1.0,
    shrinkage: float = 8.0,
) -> pd.DataFrame:
    """Estimate adjusted pair, triple, and duplicate-card interactions.

    Ridge regression first predicts fitness from card copy counts and exact
    outer generation. Combination effects are the remaining residual means,
    shrunk by sample size. Triple effects subtract their three pair effects;
    ``2× A + B`` subtracts both the A/B pair and ``2× A`` duplicate effect.
    Their reported score is capped by total excess, so a combination must beat
    both the additive model and its lower-order interactions.
    """
    if master.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    if max_combo_size not in (2, 3):
        raise ValueError("max_combo_size must be 2 or 3")

    decks, copies = _deck_table(master, group_count)
    decks["additive_expected_score"] = _additive_predictions(decks, copies, ridge_alpha)
    decks["residual"] = decks["score"] - decks["additive_expected_score"]
    rows: list[dict[str, object]] = []

    for group_name, group_indexes in decks.groupby("generation_group", sort=False).groups.items():
        indexes = np.asarray(list(group_indexes), dtype=int)
        group_decks = decks.iloc[indexes].reset_index(drop=True)
        group_copies = copies.iloc[indexes].reset_index(drop=True)
        total_decks = len(group_decks)
        candidates = [
            candidate for candidate in _candidate_masks(group_copies, max_combo_size)
            if int(candidate[2].sum()) >= min_appearances
        ]
        effects: dict[tuple[str, tuple[str, ...]], float] = {}
        pending = []
        for combo_type, cards, mask in candidates:
            appearances = int(mask.sum())
            selected = group_decks.loc[mask]
            excess = float(selected["residual"].mean())
            adjusted = excess * appearances / (appearances + max(0.0, float(shrinkage)))
            effects[(combo_type, cards)] = adjusted
            pending.append((combo_type, cards, {
                "generation_group": group_name,
                "combo_type": combo_type,
                "combo": _combo_label(combo_type, cards),
                "card_A": cards[0],
                "card_B": cards[1] if len(cards) > 1 else None,
                "card_C": cards[2] if len(cards) > 2 else None,
                "appearances": appearances,
                "total_decks": total_decks,
                "combo_pick_rate": appearances / total_decks,
                "observed_score": float(selected["score"].mean()),
                "additive_expected_score": float(selected["additive_expected_score"].mean()),
                "excess_score": excess,
                "standard_error": (
                    float(selected["residual"].std(ddof=1) / np.sqrt(appearances))
                    if appearances > 1 else float("nan")
                ),
            }))

        for combo_type, cards, row in pending:
            constituent = 0.0
            if combo_type == "triple":
                constituent = sum(
                    effects.get(("pair", tuple(sorted(pair))), 0.0)
                    for pair in combinations(cards, 2)
                )
            elif combo_type == "duplicate_pair":
                duplicate_card, other_card = cards
                constituent = effects.get(("duplicate", (duplicate_card,)), 0.0)
                constituent += effects.get(("pair", tuple(sorted((duplicate_card, other_card)))), 0.0)
            unique_excess = effects[(combo_type, cards)] - constituent
            row["constituent_interaction"] = constituent
            row["unique_excess_score"] = unique_excess
            row["synergy_score"] = (
                min(effects[(combo_type, cards)], unique_excess)
                if combo_type in {"triple", "duplicate_pair"}
                else unique_excess
            )
            rows.append(row)

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    result = pd.DataFrame(rows, columns=RESULT_COLUMNS)
    group_order = list(dict.fromkeys(decks["generation_group"].tolist()))
    result["generation_group"] = pd.Categorical(
        result["generation_group"], categories=group_order, ordered=True
    )
    return result.sort_values(
        ["generation_group", "synergy_score", "appearances"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def get_card_combo_synergies(**kwargs) -> pd.DataFrame:
    """Load the selected analysis run and estimate adjusted interactions."""
    return estimate_card_combo_synergies(load_master_df(), **kwargs)


def get_card_synergies(
    percentile: float = 0.85,
    min_co_occurrences: int = 10,
) -> pd.DataFrame:
    """Backward-compatible pair view using adjusted synergy."""
    metrics = get_card_combo_synergies(
        min_appearances=min_co_occurrences,
        max_combo_size=2,
    )
    if metrics.empty:
        return pd.DataFrame(columns=["card_A", "card_B", "co_occurrences", "synergy_score"])
    pairs = metrics[metrics["combo_type"] == "pair"].copy()
    pairs["co_occurrences"] = pairs["appearances"]
    if not pairs.empty and 0.0 < percentile < 1.0:
        pairs = pairs[pairs["synergy_score"] >= pairs["synergy_score"].quantile(percentile)]
    return pairs.sort_values("synergy_score", ascending=False).reset_index(drop=True)

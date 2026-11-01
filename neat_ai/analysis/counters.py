"""Composition-level counter relationships from held-out deck matchups."""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from .data_loader import load_master_df, load_matchup_df


COUNTER_COLUMNS = [
    "counter_card",
    "target_type",
    "target",
    "target_card_A",
    "target_card_B",
    "matchups",
    "game_samples",
    "counter_pick_rate",
    "target_rate",
    "observed_score",
    "additive_expected_score",
    "specific_counter_effect",
    "standard_error",
    "counter_score",
]


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    total = float(weights.sum())
    return float(np.dot(values, weights) / total) if total else float("nan")


def _deck_copies(master: pd.DataFrame) -> pd.DataFrame:
    copies = pd.crosstab(master["deck_id"].astype(str), master["card_id"].astype(str))
    copies.index = copies.index.astype(str)
    return copies


def _perspectives(matchups: pd.DataFrame) -> pd.DataFrame:
    first = matchups[["deck_1", "deck_2", "outer_gen", "sample_count", "g1_score"]].rename(
        columns={"deck_1": "own_deck", "deck_2": "opponent_deck", "g1_score": "score"}
    )
    second = matchups[["deck_2", "deck_1", "outer_gen", "sample_count", "g2_score"]].rename(
        columns={"deck_2": "own_deck", "deck_1": "opponent_deck", "g2_score": "score"}
    )
    result = pd.concat([first, second], ignore_index=True)
    result["own_deck"] = result["own_deck"].astype(str)
    result["opponent_deck"] = result["opponent_deck"].astype(str)
    return result


def _additive_matchup_prediction(
    perspectives: pd.DataFrame,
    own_copies: pd.DataFrame,
    opponent_copies: pd.DataFrame,
    ridge_alpha: float,
) -> np.ndarray:
    generation_terms = pd.get_dummies(
        perspectives["outer_gen"].astype(str), prefix="gen", drop_first=True, dtype=float
    )
    matrix = np.column_stack([
        np.ones(len(perspectives), dtype=float),
        own_copies.to_numpy(dtype=float),
        -opponent_copies.to_numpy(dtype=float),
        generation_terms.to_numpy(dtype=float),
    ])
    target = perspectives["score"].to_numpy(dtype=float)
    weights = np.sqrt(perspectives["sample_count"].clip(lower=1).to_numpy(dtype=float))
    weighted_matrix = matrix * weights[:, None]
    weighted_target = target * weights
    penalty = np.eye(matrix.shape[1], dtype=float) * max(0.0, float(ridge_alpha))
    penalty[0, 0] = 0.0
    coefficients = (
        np.linalg.pinv(weighted_matrix.T @ weighted_matrix + penalty)
        @ weighted_matrix.T
        @ weighted_target
    )
    return matrix @ coefficients


def _target_masks(
    opponent_copies: pd.DataFrame,
    include_builds: bool,
    min_target_appearances: int,
    max_target_builds: int,
):
    present = opponent_copies.gt(0)
    cards = sorted(str(card) for card in opponent_copies.columns if present[card].any())
    for card in cards:
        yield "card", card, card, None, present[card].to_numpy()
    if not include_builds:
        return

    builds = []
    for card_a, card_b in combinations(cards, 2):
        mask = (present[card_a] & present[card_b]).to_numpy()
        appearances = int(mask.sum())
        if appearances >= min_target_appearances:
            builds.append((appearances, f"{card_a} + {card_b}", card_a, card_b, mask))
    for card in cards:
        mask = opponent_copies[card].ge(2).to_numpy()
        appearances = int(mask.sum())
        if appearances >= min_target_appearances:
            builds.append((appearances, f"2× {card}", card, card, mask))
    builds.sort(key=lambda item: (-item[0], item[1]))
    for _appearances, label, card_a, card_b, mask in builds[:max_target_builds]:
        yield "build", label, card_a, card_b, mask


def estimate_card_counters(
    master: pd.DataFrame,
    matchups: pd.DataFrame,
    min_matchups: int = 10,
    min_target_appearances: int = 20,
    max_target_builds: int = 100,
    include_builds: bool = True,
    ridge_alpha: float = 1.0,
    shrinkage: float = 10.0,
) -> pd.DataFrame:
    """Estimate cards that outperform specifically against a card or build.

    The additive model absorbs general own-card strength, opposing-card
    difficulty, exact outer generation, and sample count. The reported
    interaction is additionally double-centered against the counter card's
    residual baseline and the target's residual baseline.
    """
    if master.empty or matchups.empty:
        return pd.DataFrame(columns=COUNTER_COLUMNS)

    deck_copies = _deck_copies(master)
    perspectives = _perspectives(matchups)
    valid = perspectives["own_deck"].isin(deck_copies.index) & perspectives[
        "opponent_deck"
    ].isin(deck_copies.index)
    perspectives = perspectives.loc[valid].reset_index(drop=True)
    if perspectives.empty:
        return pd.DataFrame(columns=COUNTER_COLUMNS)

    own_copies = deck_copies.reindex(perspectives["own_deck"], fill_value=0).reset_index(drop=True)
    opponent_copies = deck_copies.reindex(
        perspectives["opponent_deck"], fill_value=0
    ).reset_index(drop=True)
    predicted = _additive_matchup_prediction(
        perspectives, own_copies, opponent_copies, ridge_alpha
    )
    residual = perspectives["score"].to_numpy(dtype=float) - predicted
    weights = perspectives["sample_count"].clip(lower=1).to_numpy(dtype=float)
    overall_residual = _weighted_mean(residual, weights)
    own_present = own_copies.gt(0)
    rows = []

    for target_type, target, target_a, target_b, target_mask in _target_masks(
        opponent_copies,
        include_builds,
        min_target_appearances,
        max_target_builds,
    ):
        target_baseline = _weighted_mean(residual[target_mask], weights[target_mask])
        for counter_card in own_present.columns:
            counter_mask = own_present[counter_card].to_numpy()
            joint_mask = counter_mask & target_mask
            match_count = int(joint_mask.sum())
            if match_count < min_matchups:
                continue
            counter_baseline = _weighted_mean(residual[counter_mask], weights[counter_mask])
            joint_residual = _weighted_mean(residual[joint_mask], weights[joint_mask])
            interaction = (
                joint_residual - counter_baseline - target_baseline + overall_residual
            )
            adjusted = interaction * match_count / (
                match_count + max(0.0, float(shrinkage))
            )
            selected_residual = residual[joint_mask]
            rows.append({
                "counter_card": str(counter_card),
                "target_type": target_type,
                "target": target,
                "target_card_A": target_a,
                "target_card_B": target_b,
                "matchups": match_count,
                "game_samples": int(weights[joint_mask].sum()),
                "counter_pick_rate": float(counter_mask.mean()),
                "target_rate": float(target_mask.mean()),
                "observed_score": _weighted_mean(
                    perspectives.loc[joint_mask, "score"].to_numpy(dtype=float),
                    weights[joint_mask],
                ),
                "additive_expected_score": _weighted_mean(
                    predicted[joint_mask], weights[joint_mask]
                ),
                "specific_counter_effect": interaction,
                "standard_error": (
                    float(selected_residual.std(ddof=1) / np.sqrt(match_count))
                    if match_count > 1 else float("nan")
                ),
                "counter_score": adjusted,
            })

    if not rows:
        return pd.DataFrame(columns=COUNTER_COLUMNS)
    return pd.DataFrame(rows, columns=COUNTER_COLUMNS).sort_values(
        ["counter_score", "matchups"], ascending=[False, False]
    ).reset_index(drop=True)


def get_card_counters(**kwargs) -> pd.DataFrame:
    """Load the selected run's final holdout evidence and estimate counters."""
    return estimate_card_counters(
        load_master_df(),
        load_matchup_df(phase="holdout"),
        **kwargs,
    )

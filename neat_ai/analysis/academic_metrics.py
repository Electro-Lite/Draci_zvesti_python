from itertools import combinations

import numpy as np
import pandas as pd

from .data_loader import load_deck_compositions, load_master_df, load_matchup_df


GENERATION_GROUP_COLUMN = "generation_group"


def split_generation_groups(values: list[int], group_count: int) -> list[list[int]]:
    """Split sorted generation values into stable, near-even groups."""
    if not values:
        return []

    group_count = max(1, min(group_count, len(values)))
    base_size, remainder = divmod(len(values), group_count)

    groups = []
    start = 0
    for index in range(group_count):
        size = base_size + (1 if index < remainder else 0)
        groups.append(values[start:start + size])
        start += size

    return groups


def generation_group_name(index: int, total: int, start: int, end: int) -> str:
    if total == 3:
        prefix = ["early", "mid", "late"][index]
    elif total == 2:
        prefix = ["early", "late"][index]
    else:
        prefix = f"group {index + 1}"

    if start == end:
        return f"{prefix} (gen {start})"
    return f"{prefix} (gen {start}-{end})"


def add_generation_groups(
    df: pd.DataFrame,
    gen_col: str = "outer_gen",
    group_count: int = 3,
    label_col: str = GENERATION_GROUP_COLUMN,
) -> tuple[pd.DataFrame, list[str]]:
    """Assign generation-group labels to a dataframe."""
    result = df.copy()
    if result.empty or gen_col not in result.columns:
        result[label_col] = pd.Series(dtype="object")
        return result, []

    generations = sorted(int(gen) for gen in result[gen_col].dropna().unique())
    groups = split_generation_groups(generations, group_count)
    labels = [
        generation_group_name(index, len(groups), min(group), max(group))
        for index, group in enumerate(groups)
    ]
    generation_to_label = {
        generation: label
        for label, group in zip(labels, groups)
        for generation in group
    }

    result[label_col] = result[gen_col].map(generation_to_label)
    result[label_col] = pd.Categorical(
        result[label_col],
        categories=labels,
        ordered=True,
    )
    return result, labels


def load_deck_population() -> pd.DataFrame:
    """Return one row per logged deck-builder genome/deck."""
    master = load_master_df()
    if master.empty:
        return pd.DataFrame(
            columns=[
                "guid",
                "outer_gen",
                "deck_id",
                "score",
                "signature",
                "deck_name",
                "composition",
            ]
        )

    return (
        master.groupby(["guid", "gen", "deck_id"], as_index=False)
        .agg(
            score=("score", "first"),
            signature=("signature", "first"),
            deck_name=("deck_name", "first"),
            composition=("card_id", lambda cards: ", ".join(cards)),
        )
        .rename(columns={"gen": "outer_gen"})
    )


def _entropy(counts: pd.Series) -> float:
    total = counts.sum()
    if total <= 0:
        return 0.0

    probabilities = counts[counts > 0] / total
    return float(-(probabilities * np.log2(probabilities)).sum())


def get_meta_entropy_by_generation(group_count: int | None = None) -> pd.DataFrame:
    """
    Measure archetype diversity by outer generation or generation group.

    `effective_archetypes` is 2 ** entropy, a more readable diversity count.
    """
    population = load_deck_population()
    if population.empty:
        return pd.DataFrame()

    if group_count is None:
        population["generation_bucket"] = population["outer_gen"].astype(str)
        group_col = "generation_bucket"
        order_col = "outer_gen"
    else:
        population, group_order = add_generation_groups(
            population,
            group_count=group_count,
        )
        population["generation_bucket"] = population[GENERATION_GROUP_COLUMN]
        group_col = "generation_bucket"
        order_col = group_col

    rows = []
    for bucket, group in population.groupby(group_col, observed=True):
        counts = group["signature"].value_counts()
        entropy = _entropy(counts)
        max_entropy = float(np.log2(len(counts))) if len(counts) > 1 else 0.0
        top_count = int(counts.iloc[0]) if not counts.empty else 0

        rows.append(
            {
                "generation_bucket": bucket,
                "outer_gen": (
                    int(group["outer_gen"].min())
                    if group_count is None
                    else np.nan
                ),
                "gen_start": int(group["outer_gen"].min()),
                "gen_end": int(group["outer_gen"].max()),
                "total_decks": int(group["guid"].nunique()),
                "unique_archetypes": int(counts.size),
                "shannon_entropy": entropy,
                "normalized_entropy": entropy / max_entropy if max_entropy else 0.0,
                "effective_archetypes": float(2 ** entropy),
                "top_archetype_share": top_count / counts.sum() if counts.sum() else 0.0,
                "average_fitness": float(group["score"].mean()),
                "best_fitness": float(group["score"].max()),
            }
        )

    result = pd.DataFrame(rows)
    if group_count is not None:
        result["generation_bucket"] = pd.Categorical(
            result["generation_bucket"],
            categories=group_order,
            ordered=True,
        )
    return result.sort_values(order_col).reset_index(drop=True)


def get_deck_perspective_matchups() -> pd.DataFrame:
    """Return matchups from both deck perspectives."""
    matchups = load_matchup_df()
    if matchups.empty:
        return pd.DataFrame()

    deck_compositions = load_deck_compositions()[
        ["deck_id", "deck_name", "signature", "composition"]
    ]
    deck_lookup = deck_compositions.set_index("deck_id")

    as_deck_1 = matchups[
        ["outer_gen", "deck_1", "deck_2", "g1_score", "sample_count"]
    ].rename(
        columns={
            "deck_1": "deck_id",
            "deck_2": "opponent_deck_id",
            "g1_score": "score",
        }
    )
    as_deck_2 = matchups[
        ["outer_gen", "deck_2", "deck_1", "g2_score", "sample_count"]
    ].rename(
        columns={
            "deck_2": "deck_id",
            "deck_1": "opponent_deck_id",
            "g2_score": "score",
        }
    )

    perspectives = pd.concat([as_deck_1, as_deck_2], ignore_index=True)
    perspectives = perspectives.merge(
        deck_lookup[["signature", "deck_name", "composition"]],
        left_on="deck_id",
        right_index=True,
        how="left",
    )
    perspectives = perspectives.merge(
        deck_lookup[["signature", "deck_name", "composition"]].rename(
            columns={
                "signature": "opponent_signature",
                "deck_name": "opponent_deck_name",
                "composition": "opponent_composition",
            }
        ),
        left_on="opponent_deck_id",
        right_index=True,
        how="left",
    )
    return perspectives


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    weight_sum = weights.sum()
    if weight_sum == 0:
        return np.nan
    return float((values * weights).sum() / weight_sum)


def get_weighted_meta_performance(group_count: int | None = None) -> pd.DataFrame:
    """
    Estimate archetype strength against the observed meta.

    Opponent scores are weighted by opponent archetype prevalence in the same
    outer generation, then by the number of controller match samples.
    """
    perspectives = get_deck_perspective_matchups()
    population = load_deck_population()
    if perspectives.empty or population.empty:
        return pd.DataFrame()

    prevalence = (
        population.groupby(["outer_gen", "signature"], as_index=False)
        .agg(opponent_count=("guid", "nunique"))
    )
    totals = (
        population.groupby("outer_gen", as_index=False)
        .agg(total_decks=("guid", "nunique"))
    )
    prevalence = prevalence.merge(totals, on="outer_gen", how="left")
    prevalence["opponent_meta_share"] = (
        prevalence["opponent_count"] / prevalence["total_decks"]
    )

    scored = perspectives.merge(
        prevalence[["outer_gen", "signature", "opponent_meta_share"]].rename(
            columns={"signature": "opponent_signature"}
        ),
        on=["outer_gen", "opponent_signature"],
        how="left",
    )
    scored["opponent_meta_share"] = scored["opponent_meta_share"].fillna(0.0)
    scored = scored[scored["opponent_meta_share"] > 0].copy()
    if scored.empty:
        return pd.DataFrame()

    scored["weight"] = scored["sample_count"] * scored["opponent_meta_share"]

    if group_count is None:
        scored["generation_bucket"] = scored["outer_gen"].astype(str)
        group_cols = ["outer_gen", "generation_bucket", "signature"]
    else:
        scored, group_order = add_generation_groups(scored, group_count=group_count)
        scored["generation_bucket"] = scored[GENERATION_GROUP_COLUMN]
        group_cols = ["generation_bucket", "signature"]

    rows = []
    for keys, group in scored.groupby(group_cols, observed=True):
        if group_count is None:
            outer_gen, bucket, signature = keys
            gen_start = gen_end = int(outer_gen)
        else:
            bucket, signature = keys
            gen_start = int(group["outer_gen"].min())
            gen_end = int(group["outer_gen"].max())

        rows.append(
            {
                "generation_bucket": bucket,
                "outer_gen": (
                    int(group["outer_gen"].min())
                    if group_count is None and group["outer_gen"].nunique() == 1
                    else np.nan
                ),
                "gen_start": gen_start,
                "gen_end": gen_end,
                "signature": signature,
                "deck_id": group["deck_id"].iloc[0],
                "deck_name": group["deck_name"].iloc[0],
                "composition": group["composition"].iloc[0],
                "weighted_meta_score": _weighted_mean(group["score"], group["weight"]),
                "raw_average_score": _weighted_mean(
                    group["score"],
                    group["sample_count"],
                ),
                "matchup_count": int(len(group)),
                "sample_count": int(group["sample_count"].sum()),
                "opponent_meta_coverage": float(group["opponent_meta_share"].sum()),
            }
        )

    result = pd.DataFrame(rows)
    if group_count is not None and not result.empty:
        result["generation_bucket"] = pd.Categorical(
            result["generation_bucket"],
            categories=group_order,
            ordered=True,
        )

    return result.sort_values(
        ["generation_bucket", "weighted_meta_score"],
        ascending=[True, False],
    ).reset_index(drop=True)


def get_matchup_balance_by_generation(group_count: int | None = None) -> pd.DataFrame:
    """Measure matchup polarization and closeness by generation or group."""
    matchups = load_matchup_df()
    if matchups.empty:
        return pd.DataFrame()

    matchups = matchups.copy()
    matchups["abs_score"] = matchups["g1_score"].abs()
    matchups["weighted_abs_score"] = matchups["abs_score"] * matchups["sample_count"]
    matchups["is_close"] = matchups["abs_score"] <= 1.0

    if group_count is None:
        matchups["generation_bucket"] = matchups["outer_gen"].astype(str)
        group_col = "generation_bucket"
    else:
        matchups, group_order = add_generation_groups(matchups, group_count=group_count)
        matchups["generation_bucket"] = matchups[GENERATION_GROUP_COLUMN]
        group_col = "generation_bucket"

    rows = []
    for bucket, group in matchups.groupby(group_col, observed=True):
        sample_total = group["sample_count"].sum()
        weighted_abs = (
            group["weighted_abs_score"].sum() / sample_total if sample_total else np.nan
        )
        close_rate = _weighted_mean(group["is_close"].astype(float), group["sample_count"])

        rows.append(
            {
                "generation_bucket": bucket,
                "outer_gen": (
                    int(group["outer_gen"].min())
                    if group_count is None and group["outer_gen"].nunique() == 1
                    else np.nan
                ),
                "gen_start": int(group["outer_gen"].min()),
                "gen_end": int(group["outer_gen"].max()),
                "matchup_count": int(len(group)),
                "sample_count": int(sample_total),
                "mean_abs_score": float(weighted_abs),
                "median_abs_score": float(group["abs_score"].median()),
                "max_abs_score": float(group["abs_score"].max()),
                "score_std": float(group["g1_score"].std(ddof=0)),
                "close_matchup_rate": close_rate,
            }
        )

    result = pd.DataFrame(rows)
    if group_count is not None and not result.empty:
        result["generation_bucket"] = pd.Categorical(
            result["generation_bucket"],
            categories=group_order,
            ordered=True,
        )

    sort_col = "outer_gen" if group_count is None else "generation_bucket"
    return result.sort_values(sort_col).reset_index(drop=True)


def get_viable_archetypes_by_generation(
    group_count: int | None = None,
    viability_threshold: float = 0.0,
) -> pd.DataFrame:
    """Count archetypes whose weighted meta score is at or above threshold."""
    performance = get_weighted_meta_performance(group_count=group_count)
    if performance.empty:
        return pd.DataFrame()

    rows = []
    for bucket, group in performance.groupby("generation_bucket", observed=True):
        viable = group[group["weighted_meta_score"] >= viability_threshold]
        rows.append(
            {
                "generation_bucket": bucket,
                "gen_start": int(group["gen_start"].min()),
                "gen_end": int(group["gen_end"].max()),
                "archetype_count": int(group["signature"].nunique()),
                "viable_archetypes": int(viable["signature"].nunique()),
                "viable_share": (
                    viable["signature"].nunique() / group["signature"].nunique()
                    if group["signature"].nunique()
                    else 0.0
                ),
                "best_weighted_meta_score": float(group["weighted_meta_score"].max()),
                "median_weighted_meta_score": float(group["weighted_meta_score"].median()),
            }
        )

    result = pd.DataFrame(rows)
    if isinstance(performance["generation_bucket"].dtype, pd.CategoricalDtype):
        result["generation_bucket"] = pd.Categorical(
            result["generation_bucket"],
            categories=performance["generation_bucket"].cat.categories,
            ordered=True,
        )

    return result.sort_values("generation_bucket").reset_index(drop=True)


def get_card_presence_lift_by_generation(
    group_count: int = 3,
    min_times_played: int = 2,
) -> pd.DataFrame:
    """
    Estimate card value from deck presence, split by generation group.

    This is the currently supported proxy for academic drawn/played win-rate
    metrics; the game loop does not persist draw/play events yet.
    """
    master = load_master_df()
    if master.empty:
        return pd.DataFrame()

    card_rows = (
        master.groupby(["guid", "gen", "deck_id", "score", "card_id"], as_index=False)
        .agg(copies=("card_id", "size"))
        .rename(columns={"gen": "outer_gen"})
    )
    card_rows, group_order = add_generation_groups(card_rows, group_count=group_count)

    baseline = (
        card_rows[["guid", GENERATION_GROUP_COLUMN, "score"]]
        .drop_duplicates()
        .groupby(GENERATION_GROUP_COLUMN, observed=True)
        .agg(
            baseline_score=("score", "mean"),
            total_decks=("guid", "nunique"),
        )
        .reset_index()
    )

    metrics = (
        card_rows.groupby([GENERATION_GROUP_COLUMN, "card_id"], observed=True)
        .agg(
            times_played=("guid", "nunique"),
            average_score_when_present=("score", "mean"),
            total_copies=("copies", "sum"),
            average_copies=("copies", "mean"),
        )
        .reset_index()
    )
    metrics = metrics.merge(baseline, on=GENERATION_GROUP_COLUMN, how="left")
    metrics["presence_lift"] = (
        metrics["average_score_when_present"] - metrics["baseline_score"]
    )
    metrics["pick_rate"] = metrics["times_played"] / metrics["total_decks"]
    metrics = metrics[metrics["times_played"] >= min_times_played]
    metrics[GENERATION_GROUP_COLUMN] = pd.Categorical(
        metrics[GENERATION_GROUP_COLUMN],
        categories=group_order,
        ordered=True,
    )
    return metrics.sort_values(
        [GENERATION_GROUP_COLUMN, "presence_lift"],
        ascending=[True, False],
    ).reset_index(drop=True)


def get_pair_synergy_lift_by_generation(
    group_count: int = 3,
    min_appearances: int = 2,
) -> pd.DataFrame:
    """Estimate card-pair lift versus same-generation baseline."""
    master = load_master_df()
    if master.empty:
        return pd.DataFrame()

    deck_rows = (
        master.groupby(["guid", "gen", "deck_id"], as_index=False)
        .agg(
            score=("score", "first"),
            cards=("card_id", lambda cards: sorted(set(cards))),
        )
        .rename(columns={"gen": "outer_gen"})
    )
    deck_rows, group_order = add_generation_groups(deck_rows, group_count=group_count)

    baseline = (
        deck_rows.groupby(GENERATION_GROUP_COLUMN, observed=True)
        .agg(
            baseline_score=("score", "mean"),
            total_decks=("guid", "nunique"),
        )
        .reset_index()
    )

    pair_rows = []
    for row in deck_rows.itertuples(index=False):
        generation_group = getattr(row, GENERATION_GROUP_COLUMN)
        for card_a, card_b in combinations(row.cards, 2):
            pair_rows.append(
                {
                    GENERATION_GROUP_COLUMN: generation_group,
                    "guid": row.guid,
                    "card_A": card_a,
                    "card_B": card_b,
                    "pair": f"{card_a} + {card_b}",
                    "score": row.score,
                }
            )

    if not pair_rows:
        return pd.DataFrame()

    metrics = (
        pd.DataFrame(pair_rows)
        .groupby([GENERATION_GROUP_COLUMN, "card_A", "card_B", "pair"], observed=True)
        .agg(
            appearances=("guid", "nunique"),
            average_score=("score", "mean"),
        )
        .reset_index()
    )
    metrics = metrics.merge(baseline, on=GENERATION_GROUP_COLUMN, how="left")
    metrics["lift"] = metrics["average_score"] - metrics["baseline_score"]
    metrics["pair_pick_rate"] = metrics["appearances"] / metrics["total_decks"]
    metrics = metrics[metrics["appearances"] >= min_appearances]
    metrics[GENERATION_GROUP_COLUMN] = pd.Categorical(
        metrics[GENERATION_GROUP_COLUMN],
        categories=group_order,
        ordered=True,
    )
    return metrics.sort_values(
        [GENERATION_GROUP_COLUMN, "lift"],
        ascending=[True, False],
    ).reset_index(drop=True)


def get_supported_academic_metrics() -> pd.DataFrame:
    """Document which common CCG metrics are currently supported by logs."""
    return pd.DataFrame(
        [
            {
                "metric": "Meta diversity / Shannon entropy",
                "supported": True,
                "reason": "Deck signatures and outer generations are logged.",
            },
            {
                "metric": "Weighted performance versus meta",
                "supported": True,
                "reason": "Deck matchups and generation-local deck prevalence are logged.",
            },
            {
                "metric": "Matchup balance / polarization",
                "supported": True,
                "reason": "Deck-vs-deck controller scores are logged in pc_match.",
            },
            {
                "metric": "Viable archetype count",
                "supported": True,
                "reason": "Can derive from weighted meta score by generation.",
            },
            {
                "metric": "Card presence lift",
                "supported": True,
                "reason": "Deck composition and genome fitness are logged.",
            },
            {
                "metric": "Card drawn/played win rate",
                "supported": False,
                "reason": "game_loop.py draws and places cards but does not persist those events.",
            },
            {
                "metric": "Ability-use or position statistics",
                "supported": False,
                "reason": "Choice position/use_ability values are not written to train.db.",
            },
            {
                "metric": "Round/mana/dragon event statistics",
                "supported": False,
                "reason": "Rounds, mana state, and dragon battles are runtime-only state today.",
            },
        ]
    )

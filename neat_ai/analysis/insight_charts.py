from itertools import combinations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .academic_metrics import (
    get_card_presence_lift_by_generation,
    get_matchup_balance_by_generation,
    get_meta_entropy_by_generation,
    get_viable_archetypes_by_generation,
    get_weighted_meta_performance,
)
from .data_loader import load_deck_compositions, load_master_df, load_matchup_df
from .learning_curves import get_high_skill_decks, load_deck_learning_curves


GENERATION_GROUP_COLUMN = "generation_group"


def _split_values(values: list[int], group_count: int) -> list[list[int]]:
    group_count = max(1, min(group_count, len(values)))
    base_size, remainder = divmod(len(values), group_count)

    groups = []
    start = 0
    for index in range(group_count):
        size = base_size + (1 if index < remainder else 0)
        groups.append(values[start:start + size])
        start += size

    return groups


def _group_name(index: int, total: int, start: int, end: int) -> str:
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
    """Assign stable generation-group labels and return their display order."""
    if df.empty or gen_col not in df.columns:
        result = df.copy()
        result[label_col] = pd.Series(dtype="object")
        return result, []

    result = df.copy()
    generations = sorted(int(gen) for gen in result[gen_col].dropna().unique())
    if not generations:
        result[label_col] = pd.Series(dtype="object")
        return result, []

    groups = _split_values(generations, group_count)
    labels = [
        _group_name(index, len(groups), min(group), max(group))
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


def _short_text(value: str, limit: int = 90) -> str:
    if value is None:
        return ""
    value = str(value)
    return value if len(value) <= limit else value[:limit - 3] + "..."


def _outer_genome_df() -> pd.DataFrame:
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

    grouped = (
        master.groupby(["guid", "gen", "deck_id"], as_index=False)
        .agg(
            score=("score", "first"),
            signature=("signature", "first"),
            deck_name=("deck_name", "first"),
            composition=("card_id", lambda cards: ", ".join(cards)),
        )
        .rename(columns={"gen": "outer_gen"})
    )
    return grouped


def get_card_meta_timeline(group_count: int = 3) -> pd.DataFrame:
    """Return per-card metrics split into outer-generation groups."""
    master = load_master_df()
    if master.empty:
        return pd.DataFrame()

    card_rows = (
        master.groupby(["guid", "gen", "deck_id", "score", "card_id"], as_index=False)
        .agg(copies=("card_id", "size"))
        .rename(columns={"gen": "outer_gen"})
    )
    card_rows, group_order = add_generation_groups(card_rows, group_count=group_count)

    deck_counts = (
        card_rows[["guid", GENERATION_GROUP_COLUMN]]
        .drop_duplicates()
        .groupby(GENERATION_GROUP_COLUMN, observed=True)
        .agg(total_decks=("guid", "nunique"))
        .reset_index()
    )

    metrics = (
        card_rows.groupby([GENERATION_GROUP_COLUMN, "card_id"], observed=True)
        .agg(
            average_score=("score", "mean"),
            times_played=("guid", "nunique"),
            total_copies=("copies", "sum"),
            average_copies=("copies", "mean"),
            generations_active=("outer_gen", "nunique"),
        )
        .reset_index()
    )
    metrics = metrics.merge(deck_counts, on=GENERATION_GROUP_COLUMN, how="left")
    metrics["pick_rate"] = metrics["times_played"] / metrics["total_decks"]
    metrics["copy_rate"] = metrics["total_copies"] / metrics["total_decks"]
    metrics[GENERATION_GROUP_COLUMN] = pd.Categorical(
        metrics[GENERATION_GROUP_COLUMN],
        categories=group_order,
        ordered=True,
    )
    return metrics.sort_values([GENERATION_GROUP_COLUMN, "average_score"])


def get_card_pair_synergy_timeline(
    group_count: int = 3,
    min_appearances: int = 2,
) -> pd.DataFrame:
    """
    Return pair-level score lift per generation group.

    Lift is the pair deck average score minus the baseline average score for all
    decks in the same generation group.
    """
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
        for card_a, card_b in combinations(row.cards, 2):
            pair_rows.append(
                {
                    GENERATION_GROUP_COLUMN: getattr(row, GENERATION_GROUP_COLUMN),
                    "guid": row.guid,
                    "card_A": card_a,
                    "card_B": card_b,
                    "pair": f"{card_a} + {card_b}",
                    "score": row.score,
                }
            )

    if not pair_rows:
        return pd.DataFrame()

    pairs = pd.DataFrame(pair_rows)
    metrics = (
        pairs.groupby([GENERATION_GROUP_COLUMN, "card_A", "card_B", "pair"], observed=True)
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
    return metrics.sort_values([GENERATION_GROUP_COLUMN, "lift"], ascending=[True, False])


def plot_outer_fitness_distribution(group_count: int = 3) -> go.Figure:
    """Box plot of outer deck-builder fitness per generation."""
    genomes = _outer_genome_df()
    genomes, group_order = add_generation_groups(genomes, group_count=group_count)

    fig = px.box(
        genomes,
        x="outer_gen",
        y="score",
        color=GENERATION_GROUP_COLUMN,
        points="all",
        hover_data=["deck_id", "composition"],
        category_orders={GENERATION_GROUP_COLUMN: group_order},
        title="Outer Deck-Builder Fitness by Generation",
        labels={
            "outer_gen": "Outer deck-builder generation",
            "score": "Final deck-builder genome fitness",
            GENERATION_GROUP_COLUMN: "Generation group",
        },
    )
    fig.update_layout(boxmode="group")
    return fig


def plot_card_meta_timeline(
    metric: str = "average_score",
    group_count: int = 3,
) -> go.Figure:
    """Heatmap showing how card value/usage changes across generation groups."""
    metrics = get_card_meta_timeline(group_count=group_count)
    if metrics.empty:
        return go.Figure()

    group_order = list(metrics[GENERATION_GROUP_COLUMN].cat.categories)
    latest_group = group_order[-1]
    latest_order = (
        metrics[metrics[GENERATION_GROUP_COLUMN] == latest_group]
        .sort_values(metric, ascending=False)["card_id"]
        .tolist()
    )
    remaining = [
        card
        for card in metrics.sort_values(metric, ascending=False)["card_id"].unique()
        if card not in latest_order
    ]
    card_order = latest_order + remaining

    z = (
        metrics.pivot(index="card_id", columns=GENERATION_GROUP_COLUMN, values=metric)
        .reindex(index=card_order, columns=group_order)
    )
    pick_rate = (
        metrics.pivot(index="card_id", columns=GENERATION_GROUP_COLUMN, values="pick_rate")
        .reindex(index=card_order, columns=group_order)
    )
    times_played = (
        metrics.pivot(index="card_id", columns=GENERATION_GROUP_COLUMN, values="times_played")
        .reindex(index=card_order, columns=group_order)
    )
    average_copies = (
        metrics.pivot(index="card_id", columns=GENERATION_GROUP_COLUMN, values="average_copies")
        .reindex(index=card_order, columns=group_order)
    )

    customdata = np.stack(
        [
            pick_rate.fillna(0).to_numpy(),
            times_played.fillna(0).to_numpy(),
            average_copies.fillna(0).to_numpy(),
        ],
        axis=-1,
    )

    fig = go.Figure(
        data=go.Heatmap(
            z=z.to_numpy(),
            x=group_order,
            y=card_order,
            customdata=customdata,
            colorscale="Viridis",
            colorbar={"title": metric.replace("_", " ")},
            hovertemplate=(
                "Card: %{y}<br>"
                "Group: %{x}<br>"
                f"{metric.replace('_', ' ').title()}: " + "%{z:.2f}<br>"
                "Pick rate: %{customdata[0]:.1%}<br>"
                "Decks using card: %{customdata[1]:.0f}<br>"
                "Average copies: %{customdata[2]:.2f}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title="Card Meta Timeline by Generation Group",
        xaxis_title="Outer generation group",
        yaxis_title="Card",
    )
    return fig


def plot_card_pair_synergy_timeline(
    group_count: int = 3,
    top_n_per_group: int = 8,
    min_appearances: int = 2,
) -> go.Figure:
    """Facet bar chart of strongest card-pair lifts per generation group."""
    metrics = get_card_pair_synergy_timeline(
        group_count=group_count,
        min_appearances=min_appearances,
    )
    if metrics.empty:
        return go.Figure()

    group_order = list(metrics[GENERATION_GROUP_COLUMN].cat.categories)
    top_pairs = (
        metrics.sort_values([GENERATION_GROUP_COLUMN, "lift"], ascending=[True, False])
        .groupby(GENERATION_GROUP_COLUMN, observed=True)
        .head(top_n_per_group)
        .copy()
    )

    fig = px.bar(
        top_pairs,
        x="lift",
        y="pair",
        color="average_score",
        facet_col=GENERATION_GROUP_COLUMN,
        facet_col_wrap=1 if len(group_order) > 3 else 3,
        category_orders={GENERATION_GROUP_COLUMN: group_order},
        hover_data={
            "appearances": True,
            "pair_pick_rate": ":.1%",
            "baseline_score": ":.2f",
            "average_score": ":.2f",
            "lift": ":.2f",
        },
        title="Card Pair Synergy Lift by Generation Group",
        labels={
            "lift": "Score lift versus group baseline",
            "pair": "Card pair",
            "average_score": "Pair average score",
            GENERATION_GROUP_COLUMN: "Generation group",
        },
        color_continuous_scale="RdYlGn",
    )
    fig.update_yaxes(matches=None, showticklabels=True)
    fig.update_layout(coloraxis_colorbar={"title": "Avg score"})
    return fig


def plot_deck_archetype_learning_curves(
    group_count: int = 3,
    top_n_per_group: int = 4,
    min_samples: int = 100,
) -> go.Figure:
    """Line charts for high-slope deck archetypes across inner generations."""
    high_skill = get_high_skill_decks(min_samples=min_samples)
    if high_skill.empty:
        return go.Figure()

    high_skill, group_order = add_generation_groups(
        high_skill,
        gen_col="outer_gen",
        group_count=group_count,
    )
    selected = (
        high_skill.sort_values(
            [GENERATION_GROUP_COLUMN, "learning_slope"],
            ascending=[True, False],
        )
        .groupby(GENERATION_GROUP_COLUMN, observed=True)
        .head(top_n_per_group)
        .copy()
    )
    selected["deck_label"] = selected.apply(
        lambda row: f"{row.deck_id}: {_short_text(row.composition, 55)}",
        axis=1,
    )

    curves = load_deck_learning_curves()
    curves = curves.merge(
        selected[
            [
                "signature",
                "outer_gen",
                GENERATION_GROUP_COLUMN,
                "deck_label",
                "learning_slope",
                "fitness_delta",
            ]
        ],
        on=["signature", "outer_gen"],
        how="inner",
    )

    fig = px.line(
        curves,
        x="inner_gen",
        y="score",
        color="deck_label",
        facet_col=GENERATION_GROUP_COLUMN,
        facet_col_wrap=1 if len(group_order) > 3 else 3,
        category_orders={GENERATION_GROUP_COLUMN: group_order},
        hover_data={
            "outer_gen": True,
            "sample_count": True,
            "learning_slope": ":.3f",
            "fitness_delta": ":.2f",
            "composition": True,
        },
        markers=True,
        title="High-Skill Deck Archetype Learning Curves",
        labels={
            "inner_gen": "Inner player-controller generation",
            "score": "Deck-perspective average controller score",
            "deck_label": "Deck archetype",
            GENERATION_GROUP_COLUMN: "Outer generation group",
        },
    )
    fig.update_yaxes(matches=None)
    return fig


def _weighted_average(group: pd.DataFrame, value_col: str) -> float:
    samples = group["sample_count"].sum()
    if samples == 0:
        return np.nan
    return float((group[value_col] * group["sample_count"]).sum() / samples)


def plot_matchup_heatmaps_by_generation_group(
    group_count: int = 3,
    top_decks_per_group: int = 10,
) -> go.Figure:
    """Small-multiple matchup heatmaps, separated by generation group."""
    matchups = load_matchup_df()
    if matchups.empty:
        return go.Figure()

    matchups, group_order = add_generation_groups(matchups, group_count=group_count)
    deck_scores = pd.concat(
        [
            matchups[
                [GENERATION_GROUP_COLUMN, "deck_1", "g1_score", "sample_count"]
            ].rename(columns={"deck_1": "deck_id", "g1_score": "score"}),
            matchups[
                [GENERATION_GROUP_COLUMN, "deck_2", "g2_score", "sample_count"]
            ].rename(columns={"deck_2": "deck_id", "g2_score": "score"}),
        ],
        ignore_index=True,
    )
    deck_scores["weighted_score"] = deck_scores["score"] * deck_scores["sample_count"]
    deck_rank = (
        deck_scores.groupby([GENERATION_GROUP_COLUMN, "deck_id"], observed=True)
        .agg(
            weighted_score=("weighted_score", "sum"),
            sample_count=("sample_count", "sum"),
        )
        .reset_index()
    )
    deck_rank["mean_score"] = deck_rank["weighted_score"] / deck_rank["sample_count"]

    top_decks = (
        deck_rank.sort_values(
            [GENERATION_GROUP_COLUMN, "mean_score"],
            ascending=[True, False],
        )
        .groupby(GENERATION_GROUP_COLUMN, observed=True)
        .head(top_decks_per_group)
    )
    top_by_group = {
        group: group_df["deck_id"].tolist()
        for group, group_df in top_decks.groupby(GENERATION_GROUP_COLUMN, observed=True)
    }

    compositions = load_deck_compositions().set_index("deck_id")["composition"].to_dict()
    fig = make_subplots(
        rows=1,
        cols=len(group_order),
        subplot_titles=group_order,
        horizontal_spacing=0.04,
    )

    for col_index, group in enumerate(group_order, start=1):
        decks = top_by_group.get(group, [])
        group_rows = matchups[
            (matchups[GENERATION_GROUP_COLUMN] == group)
            & (matchups["deck_1"].isin(decks))
            & (matchups["deck_2"].isin(decks))
        ].copy()

        if group_rows.empty:
            matrix = pd.DataFrame(index=decks, columns=decks, dtype=float)
        else:
            pair_scores = (
                group_rows.groupby(["deck_1", "deck_2"])
                .apply(
                    lambda rows: _weighted_average(rows, "g1_score"),
                    include_groups=False,
                )
                .reset_index(name="score")
            )
            matrix = pair_scores.pivot(
                index="deck_1",
                columns="deck_2",
                values="score",
            ).reindex(index=decks, columns=decks)

        hover_text = [
            [
                (
                    f"Playing as: {deck_1}<br>"
                    f"{_short_text(compositions.get(deck_1, ''), 140)}<br><br>"
                    f"Opponent: {deck_2}<br>"
                    f"{_short_text(compositions.get(deck_2, ''), 140)}"
                )
                for deck_2 in matrix.columns
            ]
            for deck_1 in matrix.index
        ]

        fig.add_trace(
            go.Heatmap(
                z=matrix.to_numpy(dtype=float),
                x=matrix.columns.tolist(),
                y=matrix.index.tolist(),
                text=hover_text,
                hovertemplate="%{text}<br>Avg score: %{z:.2f}<extra></extra>",
                coloraxis="coloraxis",
            ),
            row=1,
            col=col_index,
        )

    fig.update_layout(
        title="Top Deck Matchup Heatmaps by Generation Group",
        coloraxis={
            "colorscale": "RdYlGn",
            "colorbar": {"title": "Avg score"},
        },
        height=max(520, 38 * top_decks_per_group),
    )
    fig.update_xaxes(tickangle=45)
    return fig


def plot_meta_entropy_timeline(group_count: int | None = None) -> go.Figure:
    """Show metagame diversity and concentration over training progress."""
    entropy = get_meta_entropy_by_generation(group_count=group_count)
    if entropy.empty:
        return go.Figure()

    x_col = "generation_bucket" if group_count is not None else "outer_gen"
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=entropy[x_col],
            y=entropy["normalized_entropy"],
            mode="lines+markers",
            name="Normalized entropy",
            customdata=entropy[
                ["unique_archetypes", "effective_archetypes", "total_decks"]
            ],
            hovertemplate=(
                "Generation: %{x}<br>"
                "Normalized entropy: %{y:.3f}<br>"
                "Unique archetypes: %{customdata[0]}<br>"
                "Effective archetypes: %{customdata[1]:.2f}<br>"
                "Decks: %{customdata[2]}<extra></extra>"
            ),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=entropy[x_col],
            y=entropy["top_archetype_share"],
            mode="lines+markers",
            name="Top archetype share",
            hovertemplate="Generation: %{x}<br>Top share: %{y:.1%}<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_layout(title="Metagame Diversity and Concentration")
    fig.update_xaxes(title_text="Outer generation" if group_count is None else "Generation group")
    fig.update_yaxes(title_text="Normalized entropy", range=[0, 1.05], secondary_y=False)
    fig.update_yaxes(title_text="Top archetype share", tickformat=".0%", secondary_y=True)
    return fig


def plot_weighted_meta_performance(
    group_count: int = 3,
    top_n_per_group: int = 8,
) -> go.Figure:
    """Rank archetypes by generation-local weighted performance versus the meta."""
    performance = get_weighted_meta_performance(group_count=group_count)
    if performance.empty:
        return go.Figure()

    group_order = list(performance["generation_bucket"].cat.categories)
    top_rows = (
        performance.sort_values(
            ["generation_bucket", "weighted_meta_score"],
            ascending=[True, False],
        )
        .groupby("generation_bucket", observed=True)
        .head(top_n_per_group)
        .copy()
    )
    top_rows["deck_label"] = top_rows.apply(
        lambda row: f"{row.deck_id}: {_short_text(row.composition, 60)}",
        axis=1,
    )

    fig = px.bar(
        top_rows,
        x="weighted_meta_score",
        y="deck_label",
        color="raw_average_score",
        facet_col="generation_bucket",
        facet_col_wrap=1 if len(group_order) > 3 else 3,
        category_orders={"generation_bucket": group_order},
        hover_data={
            "composition": True,
            "sample_count": True,
            "matchup_count": True,
            "raw_average_score": ":.2f",
            "weighted_meta_score": ":.2f",
        },
        title="Weighted Performance Versus Generation-Local Meta",
        labels={
            "weighted_meta_score": "Weighted meta score",
            "deck_label": "Deck archetype",
            "raw_average_score": "Raw avg score",
            "generation_bucket": "Generation group",
        },
        color_continuous_scale="RdYlGn",
    )
    fig.update_yaxes(matches=None, showticklabels=True)
    return fig


def plot_matchup_balance_timeline(group_count: int | None = None) -> go.Figure:
    """Show whether matchups become closer or more polarized over time."""
    balance = get_matchup_balance_by_generation(group_count=group_count)
    if balance.empty:
        return go.Figure()

    x_col = "generation_bucket" if group_count is not None else "outer_gen"
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=balance[x_col],
            y=balance["mean_abs_score"],
            mode="lines+markers",
            name="Mean abs score",
            customdata=balance[["sample_count", "matchup_count", "max_abs_score"]],
            hovertemplate=(
                "Generation: %{x}<br>"
                "Mean abs score: %{y:.2f}<br>"
                "Max abs score: %{customdata[2]:.2f}<br>"
                "Matchups: %{customdata[1]}<br>"
                "Samples: %{customdata[0]}<extra></extra>"
            ),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=balance[x_col],
            y=balance["close_matchup_rate"],
            mode="lines+markers",
            name="Close matchup rate",
            hovertemplate="Generation: %{x}<br>Close rate: %{y:.1%}<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_layout(title="Matchup Balance and Polarization")
    fig.update_xaxes(title_text="Outer generation" if group_count is None else "Generation group")
    fig.update_yaxes(title_text="Mean absolute deck score", secondary_y=False)
    fig.update_yaxes(title_text="Close matchup rate", tickformat=".0%", secondary_y=True)
    return fig


def plot_viable_archetypes_timeline(
    group_count: int = 3,
    viability_threshold: float = 0.0,
) -> go.Figure:
    """Show how many archetypes are non-negative against their local meta."""
    viability = get_viable_archetypes_by_generation(
        group_count=group_count,
        viability_threshold=viability_threshold,
    )
    if viability.empty:
        return go.Figure()

    fig = px.bar(
        viability,
        x="generation_bucket",
        y="viable_share",
        text="viable_archetypes",
        hover_data={
            "archetype_count": True,
            "best_weighted_meta_score": ":.2f",
            "median_weighted_meta_score": ":.2f",
            "viable_share": ":.1%",
        },
        title="Viable Archetype Share by Generation Group",
        labels={
            "generation_bucket": "Generation group",
            "viable_share": "Viable archetype share",
            "viable_archetypes": "Viable archetypes",
        },
        color="viable_share",
        color_continuous_scale="Viridis",
    )
    fig.update_yaxes(tickformat=".0%", range=[0, 1.05])
    fig.update_traces(textposition="outside")
    return fig


def plot_card_presence_lift_timeline(
    group_count: int = 3,
    top_n_per_group: int = 8,
    min_times_played: int = 2,
) -> go.Figure:
    """Show which cards lift deck fitness within each generation group."""
    card_lift = get_card_presence_lift_by_generation(
        group_count=group_count,
        min_times_played=min_times_played,
    )
    if card_lift.empty:
        return go.Figure()

    group_order = list(card_lift["generation_group"].cat.categories)
    top_cards = (
        card_lift.sort_values(
            ["generation_group", "presence_lift"],
            ascending=[True, False],
        )
        .groupby("generation_group", observed=True)
        .head(top_n_per_group)
        .copy()
    )

    fig = px.bar(
        top_cards,
        x="presence_lift",
        y="card_id",
        color="pick_rate",
        facet_col="generation_group",
        facet_col_wrap=1 if len(group_order) > 3 else 3,
        category_orders={"generation_group": group_order},
        hover_data={
            "times_played": True,
            "average_score_when_present": ":.2f",
            "baseline_score": ":.2f",
            "average_copies": ":.2f",
            "pick_rate": ":.1%",
        },
        title="Card Presence Lift by Generation Group",
        labels={
            "presence_lift": "Deck fitness lift over group baseline",
            "card_id": "Card",
            "pick_rate": "Pick rate",
            "generation_group": "Generation group",
        },
        color_continuous_scale="Cividis",
    )
    fig.update_yaxes(matches=None, showticklabels=True)
    return fig


def build_training_insight_figures() -> dict[str, go.Figure]:
    """Build all five generation-aware insight figures."""
    return {
        "outer_fitness_distribution": plot_outer_fitness_distribution(),
        "card_meta_timeline": plot_card_meta_timeline(),
        "card_pair_synergy_timeline": plot_card_pair_synergy_timeline(),
        "deck_archetype_learning_curves": plot_deck_archetype_learning_curves(),
        "matchup_heatmaps_by_generation_group": plot_matchup_heatmaps_by_generation_group(),
    }


def build_academic_metric_figures() -> dict[str, go.Figure]:
    """Build academic-style CCG statistics supported by the current logs."""
    return {
        "meta_entropy_timeline": plot_meta_entropy_timeline(),
        "weighted_meta_performance": plot_weighted_meta_performance(),
        "matchup_balance_timeline": plot_matchup_balance_timeline(),
        "viable_archetypes_timeline": plot_viable_archetypes_timeline(),
        "card_presence_lift_timeline": plot_card_presence_lift_timeline(),
    }

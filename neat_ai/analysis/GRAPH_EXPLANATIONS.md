# Training Analysis Graph Guide

This guide explains what each graph means, how the metric is computed, and which conclusions are safe to draw from the current logs.

## Global Scope

All helper-driven analysis can now be limited to a single training run through the top-level parameter in `neat_ai/analysis/data_loader.py`:

- `ANALYSIS_TRAINING_ID = None`: analyze all trainings together.
- `ANALYSIS_TRAINING_ID = 5`: analyze only training `5`.

You can also set it from Python or a notebook:

```python
from neat_ai.analysis import set_analysis_training_id
set_analysis_training_id(5)
```

Important: notebook cells that execute their own raw SQL do not automatically inherit this filter unless they call the shared loader helpers. At the time of writing, the old `analysis.ipynb` card-power slider setup has already been updated to use the shared loaders.

## Two Generation Axes

The current training data has two different generation concepts:

- `outer_gen`: deck-builder generation. A genome builds a deck, that deck is saved, and the deck is evaluated against other generated decks.
- `inner_gen`: player-controller or evaluator generation. For a fixed pair of decks, NEAT trains controllers that learn how to pilot those decks.

Most CCG statistics must stay separated by `outer_gen` or by `outer_gen` group. A card that looks strong globally may only look strong because it appeared late, after overall deck quality improved.

## Current Data Limits

The game loop currently shuffles decks, draws cards, places cards, uses abilities, resolves mana bonuses, and battles dragons, but those events are not persisted to `train.db`. Because of that, the analysis supports deck-level and composition-level statistics, but not true drawn-card or played-card outcome statistics.

Currently supported:

- Deck fitness by generation.
- Deck-vs-deck matchup scores.
- Deck or archetype prevalence.
- Card presence in generated decks.
- Card pair presence in generated decks.
- Inner evaluator learning curves.

Not currently supported:

- Win rate when a card was drawn.
- Win rate when a card was played.
- Ability-use success rate.
- Position-specific card value.
- Mana-color timing effects.
- Dragon-specific performance.
- Round length and turn-level behavior.

## Insight Charts Notebook

File: `neat_ai/analysis/notebooks/insight_charts.ipynb`

### 1. Outer Deck-Builder Fitness by Generation

Question answered: Is the deck-builder producing better decks over outer generations?

Each point is one logged deck-builder genome or deck. The y-axis is final genome fitness after deck evaluation. The x-axis is `outer_gen`. The box shows the distribution inside one generation: median, spread, and outliers.

How to read it:

- Rising median means the average generated deck is improving.
- Rising maximum with flat median means training finds occasional strong decks but the population is not improving consistently.
- Wide boxes mean very uneven deck quality inside that generation.
- A late-generation outlier is a deck candidate, not proof that the whole meta improved.

Safe interpretation:

- This is a direct deck-builder progress view.
- It says nothing about whether a deck is easy or hard to pilot. That belongs to `inner_gen` analysis.

### 2. Card Meta Timeline by Generation Group

Question answered: Which cards are strong or popular in early, mid, and late deck-builder generations?

This heatmap groups outer generations into stable buckets such as early, mid, and late. Rows are cards. Columns are generation groups. The color is a selected metric, usually:

- `average_score`
- `pick_rate`
- `copy_rate`
- `average_copies`

Key formulas:

- `pick_rate(card) = times_played(card) / total_decks`
- `copy_rate(card) = total_copies(card) / total_decks`
- `average_copies(card) = total_copies(card) / times_played(card)`

How to read it:

- A card bright only in early groups may be an exploration card that gets replaced later.
- A card bright only in late groups may need better support cards or stronger deck-building behavior.
- High `pick_rate` but low `average_score` means the deck-builder likes the card but the resulting decks are not especially successful.
- High `average_score` but low `pick_rate` suggests a possible hidden strong card that needs more samples.

Important limitation:

- This is card presence in decks, not drawn-card or played-card win rate.

### 3. Card Pair Synergy Lift by Generation Group

Question answered: Which two-card combinations lift deck fitness within their own generation group?

The chart ranks pairs by lift relative to the generation-local baseline.

Formula:

- `pair_lift(A,B) = avg_score(decks containing A and B) - avg_score(all decks in same generation group)`

How to read it:

- Positive lift means decks with the pair outperform the local baseline.
- A pair that appears only in late groups may represent a genuinely advanced synergy.
- Low appearance count makes a pair less reliable even if lift is high.
- Pair lift is stronger evidence than raw co-occurrence because it compares against the same-generation baseline.

Important limitation:

- This is deck-building synergy, not proof that the two cards interact in a specific board state.

### 4. High-Skill Deck Archetype Learning Curves

Question answered: Which decks become much better when the player-controller has time to learn them?

Each line is a selected deck archetype. The x-axis is `inner_gen`. The y-axis is average deck-perspective controller score. Facets separate outer generation groups.

Two summary quantities matter:

- `learning_slope`: slope of score over `inner_gen`
- `fitness_delta = final_score - initial_score`

The slope is computed by ordinary least squares on the points inside one deck trajectory:

- `slope = sum((x - mean(x)) * (y - mean(y))) / sum((x - mean(x))^2)`

How to read it:

- High starting score means the deck is easy to pilot.
- Steep upward slope means the deck has a high skill ceiling.
- Flat but high lines are reliable or simple archetypes.
- Low but rising lines may be promising but undertrained.
- Compare lines mainly within the same facet unless you intentionally want cross-generation comparisons.

### 5. Top Deck Matchup Heatmaps by Generation Group

Question answered: Which top decks beat which other top decks within the same generation group?

Each heatmap cell is the average row-deck score against the column deck. Positive values favor the row deck. Negative values favor the column deck. Each facet is a generation group.

For each deck pair, the cell value is a sample-count-weighted average:

- `avg_score(deck_i vs deck_j) = sum(score_k * samples_k) / sum(samples_k)`

How to read it:

- Green row segments show decks that beat many other top decks in that group.
- Red row segments show decks with poor matchups.
- Mixed rows indicate polarized decks: strong into some opponents, weak into others.
- A deck can matter in one generation group and be irrelevant in another.

Safe interpretation:

- This is one of the best views for local metagame structure.
- Do not merge these heatmaps mentally into one global matchup matrix unless the goal is historical overview.

## Academic Metrics Notebook

File: `neat_ai/analysis/notebooks/academic_metrics.ipynb`

### Supported Metrics Table

Question answered: Which academic CCG statistics can this project compute from the current logs?

The table distinguishes currently supported metrics from metrics that still need future instrumentation in `game_loop.py`.

Use this table when presenting results. It makes clear that card presence lift is a proxy, while drawn-card or played-card win rate is not yet available.

### Meta Diversity and Concentration

Question answered: Is training converging to a narrow meta or maintaining many viable archetypes?

The chart shows normalized Shannon entropy and top-archetype share.

Formulas:

- `p_i = count(archetype_i) / total_decks`
- `entropy = -sum(p_i * log2(p_i))`
- `normalized_entropy = entropy / log2(number_of_archetypes)`
- `effective_archetypes = 2^entropy`
- `top_archetype_share = max(count(archetype_i)) / total_decks`

How to read it:

- High normalized entropy means signatures are broadly distributed.
- Low normalized entropy means the population is concentrating around fewer archetypes.
- `effective_archetypes` is a more intuitive diversity count.
- Rising top-archetype share means one archetype is taking more of the field.

Current caveat:

- Many generated decks can have unique signatures, so entropy can stay high until signatures are clustered into broader archetypes.

### Weighted Performance Versus Generation-Local Meta

Question answered: Which archetypes perform best against the opponents that actually exist in the same generation group?

This metric weights deck matchup scores by opponent prevalence in the same outer generation and by the number of controller match samples.

Formulas:

- `opponent_meta_share(j) = opponent_count(j) / total_decks_in_generation`
- `weight(i,j) = sample_count(i,j) * opponent_meta_share(j)`
- `weighted_meta_score(i) = sum(score(i,j) * weight(i,j)) / sum(weight(i,j))`

The chart also shows a raw matchup average:

- `raw_average_score(i) = sum(score(i,j) * sample_count(i,j)) / sum(sample_count(i,j))`

How to read it:

- High weighted meta score means the deck performs well against common local opponents.
- High raw average but lower weighted score means the deck beats rare opponents more than common ones.
- Late-generation strength matters more for the final meta than early-generation domination against weak populations.

### Matchup Balance and Polarization

Question answered: Are matchups getting closer to balanced or becoming more polarized?

The main line is mean absolute matchup score. Lower is closer to neutral. The secondary line is close-matchup rate.

Formulas:

- `abs_score = abs(g1_score)`
- `mean_abs_score = sum(abs_score * sample_count) / sum(sample_count)`
- `close_matchup_rate = sum(1[abs_score <= 1.0] * sample_count) / sum(sample_count)`

How to read it:

- Falling mean absolute score means matchups are becoming less one-sided.
- Rising close-matchup rate means more pairings are near even.
- High maximum absolute score means at least one very polarized matchup remains.
- Polarization is not automatically bad, but too much can imply hard counters and unstable metas.

### Viable Archetype Share

Question answered: How many archetypes are at least non-negative against their generation-local meta?

This chart counts archetypes whose weighted meta score is at or above a chosen threshold. The default threshold is `0.0`.

Formula:

- `viable_share = viable_archetypes / archetype_count`

where a deck is viable if:

- `weighted_meta_score >= viability_threshold`

How to read it:

- High viable share means many decks can compete.
- Low viable share means the meta is narrow.
- High best score with low viable share suggests one or a few decks dominate.
- Raising the threshold makes the definition of viable stricter.

### Card Presence Lift by Generation Group

Question answered: Which cards are associated with better decks within each generation group?

Presence lift compares decks containing a card against the group baseline.

Formula:

- `presence_lift(card) = avg_score(decks containing card) - avg_score(all decks in same generation group)`

Related quantities:

- `pick_rate(card) = times_played(card) / total_decks`
- `average_copies(card) = total_copies(card) / times_played(card)`

How to read it:

- Positive lift means the card appears in better-than-average decks for that group.
- High lift and high pick rate make a strong balance candidate.
- High lift but low pick rate suggests an underexplored card.
- High pick rate but negative lift suggests the deck-builder may be over-selecting it.

Important limitation:

- This is not drawn win rate or played win rate. It is a deck-composition statistic.

## Older Analysis Notebook

File: `neat_ai/analysis/notebooks/analysis.ipynb`

These charts are still useful, but they are less rigorous than the generation-aware notebook above. Use them mainly for inspection and fast iteration.

### 1. Card Power by Deck-Builder and Evaluator Generation

Question answered: Which cards look strong for one deck-builder generation and one evaluator skill level?

This scatter plot uses `outer_gen` and `inner_gen` sliders. Each point is a card. The x-axis is pick rate inside the selected deck-builder generation. The y-axis is average evaluator match score when that card is present. Point size and color encode a 0-100 power rating.

The deck-perspective match score is sample-weighted:

- `deck_match_score = sum(match_score * sample_count) / sum(sample_count)`

Then each card gets:

- `average_score(card) = sum(deck_match_score * match_samples) / sum(match_samples)`

and a mixed power rating:

- `normalized_score = min_max(average_score)`
- `normalized_pick = min_max(pick_rate)`
- `power_rating = 100 * (0.7 * normalized_score + 0.3 * normalized_pick)`

How to read it:

- High y-value but low x-value suggests a strong but uncommon card.
- High x-value but mediocre y-value suggests a card the builder uses often without strong payoff.
- Comparing low `inner_gen` against high `inner_gen` helps distinguish easy cards from cards that reward better play.

### 2. General Card Power Rating Matrix

Question answered: Which cards combine high deck fitness with frequent use across the analyzed scope?

This is the same 70/30 normalized power rating idea, but aggregated across the current scope rather than one specific evaluator generation.

Formula:

- `power_rating = 100 * (0.7 * normalized_average_score + 0.3 * normalized_pick_rate)`

Use it as a broad overview, not final balance evidence.

### 3. Card Tier List by AI Fitness

Question answered: Which cards appear in the highest-fitness generated decks?

The bar chart ranks cards by average deck-builder fitness when present.

How to read it:

- It is easy to scan for obvious candidates.
- It can overstate cards that appear mostly in later generations.
- Prefer the generation-aware card timeline or presence-lift charts for final conclusions.

### 4. Interactive Meta Matchup Heatmap

Question answered: Which decks beat which decks overall?

Rows are decks being evaluated. Columns are opponents. Cell color is average row-deck score.

How to read it:

- It is good for inspecting specific deck IDs and compositions.
- It is less safe than generation-sliced heatmaps because it can mix early and late deck quality.

### 5. Match Win-Rate Trajectory

Question answered: Does a deck archetype improve across inner evaluator generations?

This is now represented more cleanly by the high-skill deck archetype learning curves, because that newer chart explicitly separates `inner_gen` from `outer_gen`.

### 6. Top Card Synergy Pairings

Question answered: Which pairs often co-occur in elite decks?

This counts co-occurrence in high-scoring decks above a percentile threshold.

How to read it:

- It is useful for discovery.
- Pair lift by generation group is stronger evidence because it compares against a baseline instead of only counting elite co-occurrence.

## Presentation Advice

For professors or readers unfamiliar with the project, present the charts in this order:

1. Explain the two-level training process: deck-builder outer generation and player-controller inner generation.
2. State whether the analysis is scoped to all trainings or one `ANALYSIS_TRAINING_ID`.
3. Show outer fitness distribution to establish whether training progresses.
4. Show meta entropy and viable archetypes to discuss diversity.
5. Show weighted meta performance and matchup balance to discuss competitive health.
6. Show card presence lift and pair synergy lift to discuss balance candidates.
7. Show high-skill deck learning curves to distinguish simple strong decks from decks that require learned play.
8. Use the older notebook charts only as supporting inspection views.

Avoid claiming true card drawn or played impact until the game loop logs those events.

# Training Analysis Graph Guide

This guide explains what each graph means, how to read it, and which conclusions are safe to draw from the current logs.

The current training data has two different generation concepts:

- `outer_gen`: deck-builder generation. A genome builds a deck, that deck is saved, and the deck is evaluated against other generated decks.
- `inner_gen`: player-controller/evaluator generation. For a fixed pair of decks, NEAT trains controllers that learn how to pilot those decks.

Most CCG statistics must stay separated by `outer_gen` or generation group. A card that looks strong globally may only be strong because it appeared late, after deck quality improved overall.

## Current Data Limits

The game loop currently shuffles decks, draws cards, places cards, uses abilities, resolves mana bonuses, and battles dragons, but those events are not persisted to `train.db`. Because of that, the analysis can support deck-level and composition-level statistics, but not true drawn/played-card win rates yet.

Currently supported:

- Deck fitness by generation.
- Deck-vs-deck matchup scores.
- Deck/archetype prevalence.
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

### 1. Outer Deck-Builder Fitness

Question answered: Is the deck-builder producing better decks over outer generations?

Each point is one logged deck-builder genome/deck. The y-axis is final genome fitness after deck evaluation. The x-axis is `outer_gen`. The box shows the distribution of deck quality inside a generation: median, spread, outliers, and individual decks.

How to read it:

- Rising median means the average generated deck is improving.
- Rising maximum with flat median means training finds occasional strong decks but the population is not consistently better.
- Wide boxes mean the generation contains very uneven deck quality.
- A late-generation outlier should be inspected as a deck candidate, not automatically treated as proof that the whole meta improved.

### 2. Card Meta Timeline

Question answered: Which cards are strong or popular in early, mid, and late deck-builder generations?

This heatmap groups outer generations into early/mid/late buckets. Rows are cards. Columns are generation groups. The color is the selected metric, usually `average_score`, `pick_rate`, `copy_rate`, or `average_copies`.

How to read it:

- A card bright only in early generations may be a beginner/exploration card that gets replaced later.
- A card bright only in late generations may require better supporting cards or better deck-builder behavior.
- High `pick_rate` but low `average_score` means the AI likes the card but the resulting decks are not especially successful.
- High `average_score` but low `pick_rate` marks a possible hidden strong card needing more samples.

Important limitation: this is card presence in decks, not drawn/played win rate.

### 3. Card Pair Synergy Timeline

Question answered: Which two-card combinations lift deck fitness within their own generation group?

The chart ranks pairs by `lift`: average fitness of decks containing both cards minus the baseline average fitness of all decks in the same generation group.

How to read it:

- Positive lift means decks with the pair outperform the generation baseline.
- A pair that appears in late generations only may be a real advanced synergy, not visible in early data.
- Low appearances make a pair less reliable, even if lift is high.
- Pair lift is stronger than simple co-occurrence because it compares against same-generation baseline quality.

Important limitation: this detects deck-building synergy, not whether the two cards interact during a specific board state.

### 4. High-Skill Deck Archetype Learning Curves

Question answered: Which decks become much better when the player-controller has time to learn them?

Each line is a selected deck archetype. The x-axis is `inner_gen`, the evaluator/controller generation. The y-axis is average deck-perspective controller score. Facets separate outer generation groups.

How to read it:

- High starting score means the deck is easy to pilot.
- Steep upward slope means the deck has high skill ceiling: controllers learn to use it better over inner generations.
- Flat but high lines are reliable/simple archetypes.
- Low but rising lines may be promising but undertrained.
- A line should only be compared within the same facet unless you explicitly want cross-generation meta comparisons.

### 5. Generation-Sliced Matchup Heatmaps

Question answered: Which top decks beat which other top decks within the same generation group?

Each heatmap cell is the average deck-perspective score for the row deck against the column deck. Positive values favor the row deck. Negative values favor the column deck. Each facet is a generation group.

How to read it:

- Green row segments show decks that beat many other top decks in that group.
- Red row segments show decks with bad matchups.
- Mixed rows indicate polarized decks: strong into some opponents, weak into others.
- A deck can be strong in one generation group and irrelevant in another; do not merge these heatmaps unless studying global history.

## Academic Metrics Notebook

File: `neat_ai/analysis/notebooks/academic_metrics.ipynb`

### Supported Metrics Table

Question answered: Which academic CCG statistics can this project compute from the current logs?

The table distinguishes currently supported metrics from metrics that need future instrumentation in `game_loop.py`.

Use this table when presenting results: it makes clear that card presence lift is a proxy, while drawn/played win rate is not yet available.

### Meta Diversity

Question answered: Is training converging to a narrow meta or maintaining many viable archetypes?

The chart shows normalized Shannon entropy and top-archetype share.

How to read it:

- High normalized entropy means deck signatures are broadly distributed.
- Low normalized entropy means the population is concentrating around fewer archetypes.
- `effective_archetypes = 2 ** entropy` gives a human-readable estimate of how many equally common archetypes the current diversity resembles.
- A rising top-archetype share means one archetype is starting to dominate.

Current caveat: because many generated decks have unique signatures, entropy may remain high until signatures are clustered into broader archetypes.

### Weighted Performance Versus Meta

Question answered: Which archetypes perform best against the opponents that actually exist in the same generation group?

This chart weights deck matchup scores by opponent prevalence in the same generation. That makes it closer to academic "win rate versus the meta" than a raw average matchup score.

How to read it:

- High weighted meta score means the deck performs well against common local opponents.
- High raw average but lower weighted score means the deck beats rare opponents more than common ones.
- A deck with high score in late generations is more meaningful for the final meta than one that dominated only early weak opponents.

Generation 1 is excluded from this metric when there is no matching logged genome population for prevalence weighting.

### Matchup Balance

Question answered: Are matchups getting closer to balanced or becoming more polarized?

The main line is mean absolute deck score. Lower is closer to neutral matchups. The secondary line is close-matchup rate.

How to read it:

- Falling mean absolute score means matchups are becoming less one-sided.
- Rising close-matchup rate means more deck pairs are near even.
- High max absolute score means at least one very polarized matchup remains.
- Polarization is not always bad in CCGs, but too much can imply hard counters and unstable metas.

### Viable Archetypes

Question answered: How many archetypes are at least non-negative against their generation-local meta?

The chart counts archetypes whose weighted meta score is above the chosen threshold, default `0.0`.

How to read it:

- High viable share means many decks can compete.
- Low viable share means the meta is narrow.
- A high best score combined with low viable share suggests one or a few decks dominate.
- Raising the threshold makes the definition of "viable" stricter.

### Card Presence Lift

Question answered: Which cards are associated with better decks within each generation group?

Presence lift is average fitness of decks containing the card minus baseline average fitness for that same generation group.

How to read it:

- Positive lift means the card appears in better-than-average decks for that group.
- A card with high lift and high pick rate is a strong balance candidate.
- A card with high lift but low pick rate is a possible underexplored card.
- A card with high pick rate but negative lift may be over-selected by the deck builder.

Important limitation: this is not drawn win rate or played win rate. It is a deck-composition statistic.

## Older Analysis Notebook

File: `neat_ai/analysis/notebooks/analysis.ipynb`

### General Card Power Rating Matrix

Question answered: Which cards combine high deck fitness with frequent use?

The scatter plot compares `times_played` and `average_score`, with point size/color representing a normalized power rating. It is useful for a quick overview, but it is less rigorous than generation-sliced presence lift because it mixes the whole training run.

Use it as an overview, not as final balance evidence.

### Card Tier List by AI Fitness

Question answered: Which cards appear in the highest-fitness generated decks?

The bar chart ranks cards by average deck-builder fitness when present. This is easy to read but can overstate cards that appear mostly in later generations. Prefer the generation-aware card timeline for conclusions.

### Interactive Meta Matchup Heatmap

Question answered: Which decks beat which decks overall?

Rows are decks being evaluated; columns are opponents. Cell color is average row-deck score. This is useful for inspecting specific deck IDs, but generation-sliced heatmaps are safer because global matrices can mix early and late deck quality.

### Match Win-Rate Trajectory

Question answered: Does a deck archetype improve across inner evaluator generations?

This is now better represented by the high-skill deck archetype learning curves, which explicitly separate `inner_gen` from `outer_gen`.

### Top Card Synergy Pairings

Question answered: Which pairs often co-occur in elite decks?

This counts co-occurrence in high-scoring decks. It is useful for discovery, but pair lift by generation group is stronger evidence because it compares against a baseline.

## Presentation Advice

For professors or readers unfamiliar with the project, present the charts in this order:

1. Explain the two-level training process: deck-builder outer generation and player-controller inner generation.
2. Show outer fitness distribution to establish whether training progresses.
3. Show meta entropy and viable archetypes to discuss diversity.
4. Show weighted meta performance and matchup balance to discuss competitive health.
5. Show card presence lift and pair synergy lift to discuss balance candidates.
6. Show high-skill deck learning curves to distinguish simple strong decks from decks that require learned play.

Avoid claiming true card drawn/played impact until the game loop logs those events.

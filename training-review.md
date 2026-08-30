# Training Review: IDs 13-29

## Completed Experiments

IDs 13-16 are the four-seed `replicated-final` experiment with 12 outer and 20
inner generations. IDs 17-20 are the `post-replication` sensitivity experiment
with 10 outer and 35 inner generations. All eight runs completed with balanced
40-game mature holdouts for every outer matchup.

IDs 17-20 took 89-92 minutes each and 6 hours 1 minute in total. Their
populations stayed near the intended 20 genomes, and all 4,812 outer matchups
completed. All runs were recorded from a dirty worktree; this remains a
reproducibility limitation that must be disclosed.

## Controller Conclusions

Most behavioral change occurs before generation 20. From generation 20 to 35,
draw rate changed by only 0.1-0.6 percentage points per seed and mean game
length changed by 0.086-0.127 rounds.

The relative ordering of the four active cards matched generation 35 by
generation 10 in every seed. Coefficient magnitudes still fluctuated after
generation 20, but without a consistent direction. From generation 30 to 35,
their mean absolute movement was still 1.1-2.1 fitness points across the four
seeds. Generation 35 is therefore a comparison point, not a demonstrated
convergence ceiling.

Longer training did not make active cards uniformly useful:

- `Innosuv Fanatik_1` improved with training in seeds 104729 and 196613 but was
  weak in the other two seeds.
- `Paladin_1` remained moderately negative.
- `Strazny_1` and `Zabijak_1` were strongly negative and often became more
  negative with controller experience.

The generation-5 and generation-35 held-out deck rankings still differ
materially. Their correlations were 0.554-0.628 and their mean absolute score
changes were 28.3-29.9 fitness points. Player competence therefore remains a
major part of deck evaluation.

## Deck And Card Conclusions

All four post-replication runs found their highest outer-generation score in
generation 1. Additional outer evolution did not improve the best observed
score, so another long outer run has low expected value.

Exact signature counts overstated deck diversity. In the final generations of
IDs 17-20, exact-signature diversity was 45-95%, while similarity-adjusted
effective diversity was only 14-45%. Decks formed 3, 3, 8, and 6 connected
groups when decks one card change apart were treated as related.

`Draci Fanatik_1` remains the strongest balance signal. It appeared in 90-100%
of final decks, usually at three or four copies, and its copy-count correlation
with deck score was 0.703-0.892. The top decks in every seed used four copies.

Presence lift for other cards is unstable because dominant cards are nearly
universal and correlated deck composition leaves small comparison groups.
Card presence must not be interpreted as successful card or ability use.

## Hardware Utilization

The one-second `vmstat-35gen.log` samples were aligned to the recorded start and
end timestamps of IDs 17-20. During the six-hour training window:

- total CPU utilization averaged 69.8%, with a 70% median and 73% 95th
  percentile;
- user CPU averaged 60.9% and system CPU 9.0%;
- I/O wait averaged 0.002%, no swap was used, and 33.7-44.5 GiB remained free;
- the runnable queue averaged 17.8 tasks and reached 26 at the 95th percentile.

RAM and storage were not bottlenecks. The remaining idle CPU alongside a busy
run queue points to synchronization, process-pool churn, and uneven nested
batches. More generations are feasible; changing worker counts without a
benchmark is not justified by this log.

## Inner-Ceiling-50 Results

IDs 21-24 completed the `inner-ceiling-50` experiment in 12.2-13.8 minutes
each, 53.0 minutes total. Each run contains 20 decks, 120 matchups, ten
same-generation checkpoints from generation 5 through 50, and both directions
of generation-35 versus generation-50 cross-play. All holdouts contain the
expected 20 seeds, 40 games per matchup, and balanced seats.

Generation 50 directly beat generation 35 in all four seeds:

```text
training ID    mean advantage    95% interval
21                  13.85         7.99 to 19.71
22                  17.53        10.15 to 24.91
23                  18.96        12.67 to 25.25
24                  11.04         5.24 to 16.84
pooled              15.35        12.16 to 18.53
```

Generation-50 controllers won 44.3-50.0% of cross-play games and lost
38.2-41.9%; the remainder were draws. The pre-registered rule selected
generation 50 over 35 in all four seeds.

Direct behavior was still changing at generation 50. Across all seeds,
active-ability use fell from generation 35 to 50:

- `Innosuv Fanatik_1`: 12.6% to 12.5%;
- `Paladin_1`: 7.4% to 7.1%;
- `Strazny_1`: 20.5% to 16.9%;
- `Zabijak_1`: 8.6% to 6.8%.

This is consistent with controllers learning to skip situational or harmful
abilities, rather than every active card becoming more useful. A lower ability
activation rate is not evidence of weaker play.

Checkpoint deck-rank correlations are limited by evaluation noise. Splitting
generation-50 holdouts into two disjoint ten-seed halves produced deck-rank
correlations of only 0.638-0.884. Cross-play is therefore the primary
generation decision metric.

The initial deck populations had 15-18 exact signatures but only 5.2-10.0
similarity-adjusted effective decks. `Draci Fanatik_1` appeared in 80-100% of
decks and had copy-count correlations of 0.780-0.934 with score. Every run's
best deck used four copies, independently reproducing the imbalance signal.

## Inner-Ceiling-65 Results

IDs 26-29 completed the `inner-ceiling-65` experiment in 17.4-18.1 minutes
each, 70.9 minutes total. ID 25 was an interrupted launch and is excluded. Each
completed run contains 20 decks, 120 matchups, checkpoints every five
generations, and both directions of generation-50 versus generation-65
cross-play. All expected rows are present: 40 games per checkpoint or
cross-play direction with 20 distinct seeds and balanced seats.

Generation 65 did not pass the pre-registered selection rule:

```text
training ID    mean advantage    95% interval
26                   2.39        -3.60 to  8.39
27                   0.93        -5.01 to  6.87
28                  13.61         6.96 to 20.26
29                  10.66         4.87 to 16.44
pooled                6.90         3.82 to  9.98
```

The pooled estimate favors generation 65, but only two of four independent
seeds exceeded five points with a positive interval. The registered rule
required at least three. The selected pragmatic default is therefore
generation 50. Testing generation 60 after observing this result would be an
unregistered search for a favorable stopping point and would not strengthen the
thesis inference.

Active-ability use continued to become more selective. In direct mixed-
generation games, generation 50 versus 65 use rates were:

```text
Innosuv Fanatik     10.70% -> 10.06%
Paladin              7.07% ->  5.34%
Strazny             16.51% -> 15.89%
Zabijak             11.70% -> 10.56%
```

The generation-65 advantage was not meaningfully associated with deck
composition. After centering within seed, every single-card copy-count
correlation had absolute value below 0.07, and the correlation with deck
distance was -0.013. The conflicting seeds therefore do not support a claim
that only active-card or unusual decks require 65 generations.

The four populations contained 11-14 exact signatures but only 3.49-5.63
similarity-adjusted effective decks. They formed 6-11 archetypes when decks one
card replacement apart were connected. `Draci Fanatik_1` again had a strong
copy-count correlation with held-out deck score (0.749-0.883). Three of four
best decks had four copies; the remaining run did not sample a four-copy top
candidate.

## Configuration Audit

The important cost and inference settings now have direct evidence:

- **Inner generations:** 50 beat 35 in all four direct tests. Generation 65
  beat 50 conclusively in only two of four and failed the registered rule.
- **Outer generations:** the best score occurred in outer generation 1 in all
  four 10-generation runs. More outer evolution adds correlated decks without
  improving the observed winner.
- **Builder population/species:** all ceiling runs produced exactly 20 genomes
  and 2-4 species, inside the 18-24 and 2-6 guards. Historical smaller
  configurations expanded unexpectedly because species floors dominated.
- **Opponents per genome:** replaying the nested matchup schedules with 4, 6,
  8, and 10 opponents showed that 8 opponents could reduce rank correlation
  with the 12-opponent result to 0.887. Twelve is retained for final ranking
  reliability.
- **Holdout pairs:** using only the first ten of 20 paired seeds selected a
  different best deck in three of four ceiling runs. Fifteen pairs still
  selected a different winner in one run. Twenty is retained.
- **Workers:** the hardware log rules out RAM, swap, and storage waits.
  `2 x 12` workers uses the 24 logical CPUs without changing experimental
  semantics. It is not proven throughput-optimal, but worker tuning would not
  make the data more informative.
- **NEAT mutation and compatibility settings:** these were not independently
  factorially optimized. Their observed population health and replicated
  controller improvement provide a pragmatic adequacy check, not a claim of a
  globally optimal NEAT configuration.

## Completed Independent Baseline

IDs 30-69 form the completed `final-deck-discovery` baseline. It uses 40
independent one-generation builder
populations rather than four correlated multi-generation evolutionary runs:

```text
run label: final-deck-discovery
independent seeds: 40, fixed in neat_ai.deck_builder_trainer.DEFAULT_SEEDS
outer generations: 1
builder population: 20
builder species guard: 2-6
opponents per genome: 12
inner generations: 50
inner population: 15
held-out checkpoints: 5, 20, 35, and final 50
direct generation cross-play: disabled
paired holdout seeds: 20 (40 games per checkpoint)
outer workers: 2
inner workers: 12
raw co-evolution game logging: disabled
```

This produced 800 independently initialized decks, 4,800 deck matchups, and
192,000 mature held-out games in approximately 8.6 hours. Disabling raw
training-game logging does not alter
fitness or gameplay and avoids roughly 108 million redundant database rows.
Held-out outcomes, card plays, ability uses, checkpoints, decks, and final
scores remain logged.

This baseline provides broad cross-sectional deck and card evidence, but one
outer generation does not measure builder evolution. Population mean fitness
cannot diagnose outer progress because every duel is zero-sum and all genomes
play the same number of opponents. Outer learning must instead be assessed
through card-frequency shifts, archetype survival, diversity, and matchup
distributions.

## Prepared Final Metagame Experiment

The configured follow-up restores multi-generation outer evolution while
retaining the selected mature-player configuration:

```text
run label: final-meta-evolution
seeds: 667615478, 2069633686, 915632071, 274633778
outer generations: 10
builder population: 20
builder species guard: 2-6
opponents per genome: 12
inner generations: 50
inner population: 15
held-out checkpoints: 5, 20, 35, and final 50
paired holdout seeds: 20 (40 games per checkpoint)
outer workers: 2
inner workers: 12
raw co-evolution game logging: disabled
expected runtime: 8.5-9.5 hours
```

Launch from the repository root:

```bash
source .zvesti_venv/bin/activate
python -m neat_ai.deck_builder_trainer
```

Do not change this configuration between seeds. Stop only for a
population/species guard failure, missing holdout rows, a non-finite score, or
insufficient disk.

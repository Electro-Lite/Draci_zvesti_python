# AI Training Plan

## Purpose

The purpose of the final training is not only to find a strong deck. It is to
test whether simulated players can produce deck-strength and card-balance
insights that agree with tabletop experience closely enough to reduce the need
for large human playtests.

The final experiment must therefore optimize and measure game outcomes, not
only NEAT controller fitness. Controller fitness is useful during learning, but
deck conclusions must be based on held-out games using frozen controllers,
matched random seeds, and reversed player positions.

No training should start until the pre-run requirements in this document are
satisfied.

## Evidence From Existing Training Data

The recommendations below are based on `train.db` and the current game and
training implementation.

- The database contains 95,900,887 controller-game rows, 23,820 deck matchups,
  and 2,671 generated decks.
- Training IDs 5, 7, and 9 are the clean completed runs. Runs 1, 2, and 10 have
  incomplete final generations, run 6 contains no genomes, and run 8 is a
  small test. Incomplete generations must not be included in final comparisons.
- Run 5 configured a builder population of 15 but produced 120 genomes from
  generation 2. Runs 7, 9, and 10 configured a population of 5 but produced 25
  genomes from generation 2. `min_species_size` and excessive initial
  speciation overrode the intended population size.
- Run 7 used 30 outer generations and 10 opponents per genome. Its generation
  mean was broadly flat after the early generations and finished below several
  earlier generations.
- Run 9 used 20 outer generations and 10 opponents per genome. It also peaked
  early and did not show sustained improvement in later generations.
- Inner controller learning improves most during generations 1-15. Across the
  long runs, improvement after generation 20 is small relative to its cost.
  For example, run 10's controller-1 mean moved from -11.085 at generation 1
  to -6.374 at generation 15, then only to -5.173 at generation 35.
- Runtime is consistent when expressed as one outer deck matchup times one
  inner evaluator generation: approximately 0.0002 wall-clock hours. This
  predicts the completed runs reasonably well.
- Generated deck sizes are polarized: 1,204 decks have 10 cards, only 87 have
  11 cards, and 1,380 have 12 cards. This is consistent with the current random
  output activations, positive bias initialization, and a hard 0.5 stop
  threshold, although the historical runs do not isolate those causes.
- `Draci Fanatik` appears in 96-97% of the final-generation decks in runs 5, 7,
  9, and 10, usually with roughly 2-3 copies. Its 9 damage is exceptional in a
  pool where most cards have 1-2 damage. This is a strong imbalance signal that
  the final experiment should explicitly attempt to reproduce.
- Other card rankings are unstable between runs. For example, Paladin is
  strongly positive in run 7, while Zabijak has the highest final-generation
  score lift in run 9 but very low inclusion. Replication is therefore more
  valuable than extending one run to 30 generations.

## Game-Specific Design Constraints

The current card pool has 12 player cards: 9 starter cards and 3 normal cards.
Decks contain 10-12 cards with up to four copies of each current player card.
There are no legendary player cards in `utils/cards.db`, so the complete legal
pool is included by the builder's current `max_power=Power.NORMAL` default.

Players draw five cards initially and three in later rounds. They compete for
six ordered board positions, and the first player to reach score 2 wins. This
makes card order, passing, position, and ability use part of deck strength; a
deck evaluator that cannot learn all of these decisions reliably cannot
represent the game.

The random environment has three mana colors and four shuffled dragons:

- black removes the first board card;
- red removes all cards at 1 HP or less;
- blue reverses the six board positions;
- green has 6 HP and 6 damage without an additional ability.

Consequently, held-out evaluation must balance mana order, dragon order, deck
draw order, seating, and starting player. Overall win rate without this pairing
would mix card strength with environmental luck.

The existing card results are plausible in light of these rules. `Draci
Fanatik` deals 9 damage without requiring a mana match, enough to dominate most
dragon combat. Paladin moves to the first position and Zabijak attacks the card
ahead, so their value is particularly sensitive to whether the controller has
learned ordered-board play. This is another reason to report performance at
both early and mature controller checkpoints.

## Problems That Must Be Addressed Before Final Training

### 1. Player action representation

The current controller uses five scalar outputs. Position, card, and target
selection use modulo and integer conversion, while pass and ability use treat
the same output type as a Boolean. ReLU is unbounded, but Boolean outputs are
penalized when outside `[0, 1]`. This creates a conflict in the representation.

For the final thesis run, use masked categorical outputs:

- 2 outputs: play or pass;
- 12 outputs: hand-card slot;
- 6 outputs: board position;
- 2 outputs: use or skip ability;
- 6 outputs: ability target position.

This gives 28 outputs. Illegal card slots, occupied board positions, and
invalid ability targets must be masked before `argmax`. Invalid actions should
be impossible rather than repaired by selecting the first legal option.

Add the following state inputs that affect human decisions but are currently
missing:

- current round;
- own score;
- opponent score;
- opponent passed flag;
- one-hot active mana instead of ordinal values 1, 2, and 3.

Keeping the existing card-slot representation gives 158 inputs after these
changes. Normalize numeric values to approximately `[0, 1]` or `[-1, 1]`.

### 2. Fitness must reflect player objectives

The primary controller fitness per game should be:

```text
controller_fitness = 100 * result + 10 * score_difference

result =  1 for a win
result =  0 for a draw
result = -1 for a loss
```

Use action penalties only for implementation errors after legal-action masking.
Do not penalize passing itself because passing can be strategically correct.
Average fitness per game rather than summing it so that scores remain
comparable if the number of opponents changes.

The deck-builder fitness must come from held-out match results:

```text
deck_fitness = mean(100 * result + 10 * score_difference)
```

Do not use the last training-generation fitness of a co-evolved controller as
the final deck score.

### 3. Separate controller learning from deck evaluation

For every evaluated deck pair:

1. Train the two controllers for the configured inner generations.
2. Freeze the best controller from each side.
3. Run 20 deterministic seed pairs, once in each seating order: 40 held-out
   games per deck pair.
4. Use only these 40 held-out games for deck-builder fitness.

Also evaluate the best generation-5 controllers on the same 40 games and log
them as `holdout_early`. These rows measure a weaker-player diagnostic only;
they must not contribute to deck-builder fitness.

The paired games must use the same deck shuffles, mana order, and dragon order,
then explicitly swap seats and force the opposite starting player. This
separates deck strength from first-player and random-draw effects.

For an even stronger design, train a small ensemble of general controllers on
many deck types and freeze them before deck-builder training. This removes
deck-specific controller learning as a confound. The configuration below is a
practical plan that remains close to the current nested evaluator.

## Completed Replicated Experiment

Training IDs 13-16 completed with identical settings and different seeds:

```text
run A seed: 104729
run B seed: 130363
run C seed: 155921
run D seed: 196613
outer generations per run: 12
intended builder population: 20
maximum current-generation opponents per genome: 12
inner evaluator generations: 20
inner evaluator population: 15
held-out games per deck pair: 40
outer concurrent deck evaluations: 2
inner workers per deck evaluation: 12
```

The runs took 63.8, 65.5, 66.2, and 70.5 minutes, about 4 hours 26 minutes in
total. Populations remained at 19-21 and species at 2-4. Every matchup contains
all 20 paired holdout seeds and both seat orders. These runs are the replicated
thesis dataset and must retain their original 12/20 configuration in analysis.

All four runs were recorded from a dirty worktree. Their settings, database
hashes, and Git commit are recorded, but the dirty flag limits exact source
reproducibility and must be disclosed in the thesis.

## Completed Post-Replication Experiment

Training IDs 17-20 completed the following sensitivity configuration:

```text
outer generations per run: 10
intended builder population: 20
maximum current-generation opponents per genome: 12
inner evaluator generations: 35
inner evaluator population: 15
held-out games per deck pair: 40
outer concurrent deck evaluations: 2
inner workers per deck evaluation: 12
independent seeds: 104729, 130363, 155921, 196613
```

All four runs completed in 6 hours 1 minute. Their best outer-generation score
occurred in generation 1. Controller outcome and game-length metrics changed
little after generation 20, and active-card ordering matched generation 35 by
generation 10. Longer training exposed card-specific weaknesses but did not
show that active cards become uniformly useful.

## Completed Inner-Ceiling-50 Experiment

The existing data does not demonstrate convergence at generation 35.
Same-generation evaluation cannot detect improvement shared by both
co-evolving players, and active-card coefficients still moved by 1.1-2.1
fitness points from generation 30 to 35. IDs 21-24 therefore performed direct
generation-35 versus generation-50 cross-play:

```text
run label: inner-ceiling-50
seeds: 230003, 262147, 300007, 350003
outer generations per run: 1
intended builder population: 20
maximum current-generation opponents per genome: 12
inner evaluator generations: 50
inner evaluator population: 15
frozen holdout generations: 5, 10, 15, 20, 25, 30, 35, 40, 45, 50
cross-play generations: 35 versus 50 in both deck directions
held-out games per checkpoint and deck pair: 40
outer concurrent deck evaluations: 2
inner workers per deck evaluation: 12
```

The intermediate evaluations freeze the best-so-far controllers and replay the
same paired environments. Holdout rows record per-card plays and active-ability
uses; training rows do not, to control database growth.

The four runs completed in 53.0 minutes. Generation 50 exceeded the
pre-registered five-point threshold with a positive 95% interval in every seed:
mean advantages were 13.85, 17.53, 18.96, and 11.04. The pooled advantage was
15.35 fitness points with a 12.16-18.53 interval. Generation 50 is therefore
preferred to generation 35.

The pre-registered generation-35 versus generation-50 decision was:

- use 50 generations when its mean cross-play advantage exceeds 5 fitness
  points and its 95% interval is above zero in at least three of four seeds;
- retain 35 when the absolute advantage is at most 5 points and its interval
  includes zero in every seed, provided deck ranks and active-use rates are
  also stable;
- treat mixed seeds as inconclusive and add one outer generation only for the
  conflicting seeds rather than launching another long builder experiment.

Ability-use policy continued changing through generation 50, particularly for
`Strazny_1` and `Zabijak_1`. This justifies one final independent
generation-50 versus generation-65 ceiling test:

```text
run label: inner-ceiling-65
seeds: 400009, 450001, 500009, 550007
outer generations per run: 1
inner evaluator generations: 65
frozen holdout generations: every 5 generations from 5 through 65
cross-play generations: 50 versus 65 in both deck directions
all other settings: unchanged from inner-ceiling-50
expected runtime: 65-80 minutes
```

IDs 26-29 completed this experiment in 70.9 minutes. Generation 65 advantages
were 2.39, 0.93, 13.61, and 10.66 points. Only two seeds exceeded five points
with a positive 95% interval, so the pre-registered rule was not met.
Generation 50 is the selected final setting.

### Launch commands

The configured defaults now run the final multi-generation metagame
experiment:

```bash
source .zvesti_venv/bin/activate
python -m neat_ai.deck_builder_trainer
```

The command records the label `final-meta-evolution` and a shared description
of the four-seed, ten-outer-generation experiment on every training row. For a
variant protocol, pass an explicit `--description` stating its purpose so it
cannot later be mistaken for this final collection.

It contains four new pre-registered seeds, 50 inner generations, ten outer
generations, 12 opponents per genome, and 20 paired holdout seeds. Raw
co-evolution rows are disabled, while held-out outcomes and actions at
generations 5, 20, 35, and 50 remain logged. Expected runtime is 8.5-9.5 hours.
Do not run seeds in separate shells because each run already uses all 24
logical CPUs.

## Deck-Builder NEAT Configuration

Use the following as the proposed complete builder configuration:

```ini
# Deck builder: 91 inputs = 12 deck slots * 7 features + 7 candidate features
[NEAT]
fitness_criterion     = max
fitness_threshold     = 9999
pop_size              = 20
reset_on_extinction   = True

[DefaultStagnation]
species_fitness_func = mean
max_stagnation       = 8
species_elitism      = 1

[DefaultReproduction]
elitism            = 1
survival_threshold = 0.30
min_species_size   = 2

[DefaultGenome]
activation_default      = sigmoid
activation_mutate_rate  = 0.0
activation_options      = sigmoid

aggregation_default     = sum
aggregation_mutate_rate = 0.0
aggregation_options     = sum

bias_init_mean          = 0.0
bias_init_stdev         = 1.0
bias_max_value          = 10.0
bias_min_value          = -10.0
bias_mutate_power       = 0.3
bias_mutate_rate        = 0.3
bias_replace_rate       = 0.05

compatibility_disjoint_coefficient = 1.0
compatibility_weight_coefficient   = 0.5

conn_add_prob           = 0.15
conn_delete_prob        = 0.05
enabled_default         = True
enabled_mutate_rate     = 0.01

feed_forward            = True
initial_connection      = full_direct

node_add_prob           = 0.05
node_delete_prob        = 0.02

num_hidden              = 5
num_inputs              = 91
num_outputs             = 2

response_init_mean      = 1.0
response_init_stdev     = 0.0
response_max_value      = 12.0
response_min_value      = 0.0
response_mutate_power   = 0.0
response_mutate_rate    = 0.0
response_replace_rate   = 0.0

weight_init_mean        = 0.0
weight_init_stdev       = 1.0
weight_max_value        = 10.0
weight_min_value        = -10.0
weight_mutate_power     = 0.4
weight_mutate_rate      = 0.5
weight_replace_rate     = 0.05

[DefaultSpeciesSet]
compatibility_threshold = 3.2
```

Reasons for the main changes:

- `pop_size=20` provides useful diversity without the 120-genome explosion in
  run 5.
- `min_species_size=2`, one protected species, and one elite prevent species
  floors and elitism from consuming most of the population.
- A compatibility threshold of 3.2 produces four initial species for both
  planned seeds with this configuration. The operational target remains 2-6
  species, not a specific hard-coded species count.
- Mutation is lower than the current simultaneous 0.5 add/delete and 0.2
  node-add/delete rates. Existing populations remain diverse but do not show
  stable improvement, so preserving useful structures is more important.
- Sigmoid outputs give consistent semantics to candidate score and the
  `continue building` threshold. Zero-mean bias should reduce the observed
  polarization between exactly 10-card and exactly 12-card decks.

## Player-Evaluator NEAT Configuration

This configuration assumes the 158-input, 28-output masked categorical action
representation described above:

```ini
[NEAT]
fitness_criterion     = max
fitness_threshold     = 9999
pop_size              = 15
reset_on_extinction   = True

[DefaultStagnation]
species_fitness_func = mean
max_stagnation       = 10
species_elitism      = 1

[DefaultReproduction]
elitism            = 1
survival_threshold = 0.30
min_species_size   = 2

[DefaultGenome]
activation_default      = tanh
activation_mutate_rate  = 0.05
activation_options      = tanh relu

aggregation_default     = sum
aggregation_mutate_rate = 0.0
aggregation_options     = sum

bias_init_mean          = 0.0
bias_init_stdev         = 1.0
bias_max_value          = 10.0
bias_min_value          = -10.0
bias_mutate_power       = 0.3
bias_mutate_rate        = 0.5
bias_replace_rate       = 0.05

compatibility_disjoint_coefficient = 1.0
compatibility_weight_coefficient   = 0.5

conn_add_prob           = 0.20
conn_delete_prob        = 0.10
enabled_default         = True
enabled_mutate_rate     = 0.01

feed_forward            = True
initial_connection      = fs_neat_hidden

node_add_prob           = 0.10
node_delete_prob        = 0.05

num_hidden              = 1
num_inputs              = 158
num_outputs             = 28

response_init_mean      = 1.0
response_init_stdev     = 0.0
response_max_value      = 12.0
response_min_value      = 0.0
response_mutate_power   = 0.0
response_mutate_rate    = 0.0
response_replace_rate   = 0.0

weight_init_mean        = 0.0
weight_init_stdev       = 1.0
weight_max_value        = 10.0
weight_min_value        = -10.0
weight_mutate_power     = 0.4
weight_mutate_rate      = 0.7
weight_replace_rate     = 0.05

[DefaultSpeciesSet]
compatibility_threshold = 2.6
```

Keep the evaluator population at 15 and use 50 inner generations. The direct
generation-35/50 and generation-50/65 experiments establish this stopping
point. The final collection must not reopen the ceiling decision by searching
generation 55 or 60 after seeing the registered comparison.

If the action representation cannot be changed before training, retain
`num_inputs=152` and `num_outputs=5`, keep ReLU activation, and use the same
population, reproduction, mutation, and 50-generation recommendation above.
Label such a run as a legacy controller experiment; it should not be the main
evidence for claims about realistic player behavior.

## Match Scheduling

For a 20-genome builder population, each genome must play exactly 12 distinct
current-generation opponents. Preserve equal deck-1 and deck-2 appearances.
Randomize the regular pairing graph from the recorded run seed.

For final validation, take the five best distinct deck signatures from each
seed and add the two verified human-designed decks:

- `Starter Blue_1`;
- `Killer Queen_1`.

Use a round robin with 20 seed pairs and reversed seats, producing 40 games per
deck pairing. Keep `Strong Arm_1` out until its header/line identifier mismatch
in `utils/decks.db` has been validated.

Report results both for the trained-controller ceiling and for at least one
weaker controller checkpoint, such as inner generation 5. The difference is a
useful approximation of how deck performance changes with player experience.

## Recorded Experiment Metadata

Each training row must record all of the following, not only the builder config:

- builder and evaluator configurations;
- outer and inner generation counts;
- intended and observed population per generation;
- observed number of species per generation;
- opponent count and held-out game count;
- both run seeds and every held-out game seed;
- worker counts;
- Git commit and dirty-worktree flag;
- hash of `utils/cards.db` and `utils/decks.db`;
- start/end time and termination reason;
- checkpoint used when resuming.

Add an index on `pc_match(match_dbt_guid)` before producing another large
analysis database. Current analysis repeatedly scans nearly 96 million rows.
Prefer storing per-game outcome fields and an aggregated generation summary;
raw controller rows may be retained separately if they are needed.

## Metrics For The Thesis

Primary metrics:

- held-out deck win rate with a 95% confidence interval;
- mean player-score difference;
- first-player advantage;
- card inclusion rate and average copies;
- card score lift within the same outer generation;
- rank agreement between the four independent seeds;
- agreement between AI rankings and the small tabletop calibration set.

Secondary metrics:

- controller win rate by inner generation;
- deck performance at inner generations 5 and 35 as an estimate of floor and
  ceiling;
- effective number of archetypes and top-archetype share;
- matchup polarization;
- ability-use rate and success rate;
- mana-color and dragon-specific performance.

Do not interpret card presence as drawn-card or played-card win rate. Those
statistics require the new event logging described above.

## Pre-Run Checks And Stop Conditions

Run one outer generation as a timing and integrity pilot before the four final
seeds. It is a validation run and must not be merged into the final results.

Continue only if all conditions hold:

- effective builder population is between 18 and 24;
- the builder has 2-6 species after initial stabilization;
- every genome has exactly 12 distinct current-generation opponents;
- each deck match has all expected inner generations and held-out games;
- seat counts are balanced;
- invalid-action count is zero after masking;
- no controller or deck score is null;
- projected four-seed runtime is at most 6 hours;
- available disk space covers at least 1 GB of additional training data.

If there are more than 6 species, raise builder compatibility threshold by 1.0
before the final runs. If there is one species for three consecutive
generations, lower it by 0.5. Do not change thresholds during a final run.

Terminate a run cleanly if the population exceeds 30, expected matchup rows are
missing, outcomes become non-finite, or the projected runtime exceeds 24 hours.
Preserve the partial run but mark it excluded from final analysis.

## Expected Interpretation

The strongest existing card-level hypothesis is that `Draci Fanatik` is
overpowered or at least over-centralizing. The replicated final runs should
test whether its high inclusion and positive lift persist under frozen,
seat-balanced outcome evaluation.

The final thesis claim should be limited to whether AI can reproduce useful
relative balance and matchup signals with a small human calibration set. Even a
high agreement does not prove that AI can replace all player testing, because
human enjoyment, rule comprehension, bluffing, and creativity are not present
in the simulator.

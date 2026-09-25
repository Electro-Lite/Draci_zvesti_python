# Training workbench: implementation contract

Status: current product and behavior contract. The historical Concept 01 SVGs
are visual references only where they agree with this document.

## Experience

The workbench fills the Pygame window. Its wide layout has a mission rail,
editable configuration and evidence panels, and a persistent read-only summary
with Review & launch. Do not show numbered Mission / Configuration / Evidence /
Preflight steps. The header is “Training workbench” and does not advertise
reproducibility.

At 640×480, stack the same content in a keyboard-accessible scroll view and pin
the launch action. Preserve independent drafts while switching missions.
Invalid text stays visible with an inline error; launch requires a valid draft
and explicit confirmation.

## Missions

### Counter-deck training

The user selects one deck under test. A 20-member opponent deck population
evolves specifically to counter it. Subject and counter controller populations
are created once and continue evolving across all counter generations; they are
not restarted for each opponent.

Editable fields are run label, deck under test, counter generations, persistent
controller generations, workers, and seat-balanced games per counter deck.
Results show the selected deck's win rate aggregated across the final counter
population and **Top counter**, the final candidate with the highest counter
win rate (fitness breaks ties).

### Matchup evaluation

The user selects Deck A and Deck B. Their controller populations coevolve
directly while both decks remain fixed. Editable fields are run label, both
decks, controller generations, workers, and even games per checkpoint.

Report Deck A wins, draws, and Deck B wins at generation 1, standard maturity
checkpoints 10/25/40 when reached, and the final generation. Results must never
describe Deck B as a random opponent.

### General deck evolution

Keep the existing seed-based tournament structure. Editable fields are run
label, seed set, outer and inner generations, **Rival decks per candidate**,
evaluator workers, and holdout seed pairs. “Rival decks per candidate” means
the maximum number of other evolved decks each candidate faces per outer
generation. It must be even for seat balance. Do not use the unexplained label
“matches per candidate” in the UI.

## Navigation and launch

The rail contains exactly the three missions plus Training guide, Runs, and
Back. Mouse and keyboard focus can reach every field. Presets update only the
active mission and editing a preset-controlled value marks it Custom.

Review shows every command-affecting value and the workload model. Starting
creates exactly one UI-owned job and opens Runs. Returning from Runs goes back
to setup. Exiting Pygame while a UI-owned job is active requires confirmation.

## Results language

Counter and matchup runs use Overview, Learning, Evaluation, and Conclusions.
General deck evolution uses Overview, Population, Matchups, and Conclusions.
Counter learning plots selected-deck win rate by counter generation. Matchup
learning plots Deck A win rate by controller generation. The counter evaluation
page visibly names Top counter and its win rate.

## Responsive acceptance

- 1600×900 and 1280×720 show all wide panels without overlap.
- 640×480 keeps every setting reachable through scrolling and keyboard focus.
- Draft, summary, review, and launched `TrainingRequest` always agree.
- Counter and matchup evaluation-game counts are even and at least two.
- Workload text is a simulated-game estimate, never an ETA.
- Runs filtering distinguishes all three missions.

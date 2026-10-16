# Training Arena — mission-specific redesign studies

This design-only package separates [live progress](run-progress/README.md) from **completed-run, mission-specific results**. The three result missions intentionally have different information hierarchies and layouts. All SVGs are editable vector artboards; PNGs are previews at 1600×900. The earlier [overview contact sheet](overview.png) shows result studies; deck evolution's current five-page sequence has its own [contact sheet](deck-evolution/feasible-analysis/overview.png). Start implementation with the [current handoff guide](HANDOFF_GUIDE.md).

## Choose within each mission

| Mission | Chosen direction | Other study | Supporting material |
| --- | --- | --- | --- |
| [Counter decks](counter-decks/DESIGN.md) | [Compositions first](counter-decks/01-compositions-first.png): selected deck, selected counter, outcome, candidate ranking visible together | [Investigation board](counter-decks/02-investigation-board.png): rank candidates and see card-count changes | [Full deck inspector](counter-decks/03-deck-inspector.png) is an unselected study, not a Counter 1 action |
| [Matchup evaluation](matchup-evaluation/DESIGN.md) | [Checkpoint study](matchup-evaluation/02-checkpoint-study.png): how the same two decks compare as controllers mature | [Two-sided scoreboard](matchup-evaluation/01-two-sided-scoreboard.png): explicit Deck A / Deck B rates with both deck lists | [Full deck inspector](matchup-evaluation/03-deck-inspector.png) is an unselected study, not a Duel 2 action |
| [Deck evolution](deck-evolution/feasible-analysis/README.md) | [Five-page feasible analysis](deck-evolution/feasible-analysis/overview.png): retrospective run pulse, population, local matchups, composition, research boundary | [Earlier ambitious studies](deck-evolution/DESIGN.md), now superseded | [Measured-data audit](deck-evolution/feasible-analysis/DATA_AUDIT.md) and Jupyter/raw-SQL handoff |

These are independent mission choices: the counter screen need not share a template with the duel or evolution screen. A shared color palette, back-to-runs action, run identity and status are enough to make them feel like one application.

The selected [Counter compositions first](counter-decks/01-compositions-first.png) and [Duel checkpoint study](matchup-evaluation/02-checkpoint-study.png) boards also show run depth: controller population sizes, learning generations, per-candidate or per-genome work, validation/checkpoint games and an approximate total. Learning simulations and measured result samples are explicitly distinguished. Deck evolution now has a separate [evidence-first rethink](deck-evolution/feasible-analysis/README.md) because its relative coevolution scores cannot be read as absolute progress.

The **current** handoffs are organized in [HANDOFF_GUIDE.md](HANDOFF_GUIDE.md): shared in-progress UI, completed-run result routing, existing result layouts, and [deck adoption](deck-adoption/README.md). The older Counter/Duel phase notes may mention partial results or blank placeholders; the current guide and their top-of-file routing overrides supersede those older instructions. The three missions retain independent finished layouts.

## What changed from the first attempt

The first Arena concepts were variants of a common dashboard shell. They are archived in [`../archive/arena-v1`](../archive/arena-v1/). These boards begin with each mission's main question:

- Counter finding: **Which generated deck beat the user-selected deck, and which card copies are in each?** A candidate's own win rate, W/D/L and sample count are kept next to its composition. Pooled selected-deck results are not presented as if they belonged to one counter.
- Duel evaluation: **Which of these two fixed decks won?** Every win rate and count explicitly says Deck A, Deck B or draw. The two deck identities and compositions remain visible or one click away.
- Deck evolution: **What completed, how did the deck population change, and which local results are worth follow-up?** Five pages separate progress, relative population scores, local matchup evidence, stored card composition and the notebook boundary. No absolute improvement or stable win-rate claim is inferred from coevolving fitness.

## Data provenance and realism

The example Starter Blue and Killer Queen card compositions come from the read-only `utils/decks.db` records. Counter G1 #8's **composition** comes from a local counter-run `summary.json`; that historical run had 16 counter wins / 2 draws / 2 selected-deck wins in only 20 games. The chosen Counter 1 artboard shows **illustrative** 800/100/100 outcomes over 1,000 games; Duel 2 likewise uses illustrative 1,000-game checkpoint outcomes. In contrast, the new deck-evolution boards use measured local **DB 13** data, documented in their [audit](deck-evolution/feasible-analysis/DATA_AUDIT.md). A future UI must draw from the selected run and never substitute any wireframe example values.

Current sources can support much of the concept: `counter_deck_trainer.py` writes `subject_cards` and final `counter_matchups` with each candidate's card IDs, names, W/D/L and game count; `matchup_trainer.py` writes both deck IDs/names and checkpoint W/D/L; `TrainingService.database_insights()` loads population fitness, matchup examples and card composition for builder runs. The current `TrainingInsights` omits most final counter candidates, and matchup summaries do not snapshot card lists. Those views would need read-only adapters or deck database lookup; if a historical deck is gone, show that composition is unavailable rather than inventing it.

The old advanced evolution figures were inspired by `neat_ai/analysis/notebooks/insight_charts.ipynb`, `academic_metrics.ipynb`, `definitive_training_analysis.ipynb` and `neat_ai/analysis/GRAPH_EXPLANATIONS.md`. The new feasible-analysis design keeps only bounded run-scoped deck-level analysis in the Arena; expensive controller, holdout and multi-seed work remains a Jupyter/cached-analysis handoff. Avoid querying the raw 8.2 GB game table in the Pygame draw loop.

## States and scale

Pending/running/stopping jobs use the [shared progress screen](run-progress/README.md), never the finished mission analyses. Once completed and its artifact is ready, the live session offers an explicit “Open [mission] results” handoff; completed entries opened later from Runs go directly to their mission results. Failed/stopped/interrupted/historical incomplete runs get terminal status/logs, not finished-result pages. Stop training applies only to a UI-owned running job and retains confirmation. At 1280×720 and 640×480, preserve readable type and card lists via scrolling. Neither chosen Counter 1 nor Duel 2 view has a full-deck inspector action. The comparison target is **1,000 evaluation games per counter candidate or duel checkpoint**; smaller real completed runs remain visible but clearly exploratory. Counter and Evolution finished results gain [Adopt deck](deck-adoption/README.md).

To regenerate the boards, run `python wireframe-design/training-arena-v2/render.py` from the repository root. To render only the two selected boards, append `counter-01 duel-02`. It writes only inside this package and requires `rsvg-convert`.

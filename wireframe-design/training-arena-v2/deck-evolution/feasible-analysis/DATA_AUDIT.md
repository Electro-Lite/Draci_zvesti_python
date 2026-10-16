# Data audit for the five-page rethink

Read-only inspection of local `train.db`, `utils/cards.db`, trainer code and `neat_ai/analysis/GRAPH_EXPLANATIONS.md` on 26 September 2026. No database data was changed. DB 13 (`replicated-final`, seed 104729) is used as a **concrete design example**, not a default selected run. It ran 12 outer generations, 20 inner evaluator generations and 20 holdout seed pairs, ending 23 July 2026. The database file was approximately 8.2 GB at inspection; raw player-controller match aggregation is inappropriate for a Pygame draw loop.

## Measured example values

| Measure | DB 13 observation | Provenance and interpretation |
| --- | ---: | --- |
| Genome rows | 243 | `genome WHERE training_id=13`; 20–21 per outer generation. |
| Stored generated decks | 243 | `ai_training_decks WHERE training_id=13`; compositions in `ai_training_deck_lines`. |
| Scored outer pairs | 1,458 | `match_dbt` GUIDs for T13, all with `result`; Gen 12 had 120 scheduled pairings. These are **pairings**, not game count. |
| Score range, Gen 1 | −59.8 to +58.8 (spread 118.5) | `genome.score`, contemporary relative fitness; rounded endpoints make a 0.1 rounding difference. |
| Score range, Gen 12 | −31.6 to +25.2 (spread 56.8) | Same source, different opponent population. Change is not absolute quality change. |
| Mean fitness | 0 within each generation | Zero-sum pair scoring makes the mean uninformative as a quality-progress signal. |
| Exact deck signatures | 18/20 Gen 1, 16/20 Gen 12 | `ai_training_decks.signature`; exact uniqueness is a weak proxy for archetype diversity. |
| Top final local deck | Gen12_ID191, fitness +25.2 | `genome` Gen 12; 12 scheduled opponents. A local ranking only. |
| Selected deck's example pair scores | +69.5 vs Gen12_ID198, +69.3 vs ID194, +58.8 vs ID205, −33.5 vs ID192 | `match_dbt.result`, converted to Gen12_ID191's row perspective. These are **fitness scores**, never W/D/L or win rates. |
| Draci Fanatik presence | 18/20 → 20/20 decks | Gen 1 vs Gen 12 card IDs in stored deck lists. Mean copies *when present*: 28/18≈1.56 → 67/20=3.35. |
| Novic, Paladin, Panos, Pesak presence | 85→100%, 65→30%, 50→15%, 85→80% | Same generation-scoped stored deck-list counts; each denominator is 20 decks. |

The old Arena service already loads `genome` score ranges and `match_dbt` scores via `TrainingService.database_insights()`, but it also offers globally aggregated card scores and sparse exemplars. The new design would require **run- and generation-scoped** presentation models, background/cached computation, and clear missing-data states. Rendering must not trigger a full-table or raw-game scan.

## Metric semantics and feasibility

- **Live progress:** `neat_ai/deck_builder_trainer.py` emits phase, outer generation, completed/total outer pairings and best relative fitness; `TrainingService.job_telemetry()` exposes these. Before a generation finishes, fitness/ranking may be incomplete. Distinguish a queued deck pairing from simulated controller-learning or holdout games. The nested `train_deck()` work inside each pairing does **not** emit a per-inner-generation live progress stream to this job, so a precise live inner-loop progress bar would require new instrumentation. The 1,458 count is an observed completed-run value, not a generic total for every run.
- **Population trajectory:** scores in `genome` support per-generation counts, min/max/spread, quantiles and exemplars. Because opponents coevolve and scoring is approximately zero-sum, mean fitness near zero and a falling champion value are *not* meaningful absolute-progress claims. A fixed reference cohort would require a new protocol, not a chart rewrite.
- **Diversity:** saved compositions support exact signatures and copy-count distance. An effective-archetype estimate needs an explicit clustering/similarity rule and a stable, reviewable denominator. The current Pygame `TrainingInsights` does not expose that. The new wireframe intentionally uses exact signatures only as a labeled reference, not as proof of healthy diversity.
- **Matchups:** `match_dbt.result` is a deck-relative fitness score for one scheduled deck pair. Its table does not itself store a W/D/L denominator. DB 13's settings specify 20 holdout seed pairs (normally 40 final seat-balanced games/pair), but actual per-pair game evidence requires a separate `pc_match` aggregation and validation. Thus Page 3 labels 40 as **planned** and every pair exploratory relative to the 1,000-game comparison target. A pair not scheduled is “not observed”, not a draw/zero score. Any heatmap must maintain row-deck perspective and sample/coverage labels.
- **Card signals:** deck presence, copy count and generation-local fitness association can be computed from stored compositions. The latter needs comparison-group counts, generation scope and confounding caveats. DB 13's near-universal final Draci Fanatik presence leaves no meaningful final-generation absence group, so do not display a confident presence-lift claim there. True drawn-card, played-card and ability-use outcomes are not available for historical DB 13.
- **Controller learning:** detailed inner-generation curves and held-out W/D/L live in raw `pc_match` and notebook aggregation, not the lightweight Arena insight model. The existing analysis notebooks already cache costly run-scoped queries; reproduce or reuse that only as an explicit background/cached analysis job, never inside rendering. No page should mix inner and outer generation axes without labels.
- **Cross-seed/professor-level claims:** a single selected run cannot establish replication, robust card balance, causal effect, or metagame generalization. The definitive notebook has multi-seed integrity checks, uncertainty descriptions and limitations. The Arena should hand off the selected training ID and scope to those notebooks, not duplicate every method in an interactive game UI.

## Go / no-go

**Go:** small, query-bounded, run-scoped Pages 1–4 with explicit provenance and exploratory warnings. **No-go:** an all-in-one live Pygame professor dashboard that re-aggregates the full 8.2 GB raw-game table or asserts absolute quality, stable win rates from short builder holdouts, or unlogged action-level card effects. If a run lacks even the deck/match rows, show Page 1 status and a notebook handoff rather than simulated charts.

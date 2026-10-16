# Training Arena: review and selectable directions

These are design proposals for the **details of one training run**, separate from the setup workbench. Every number and run name in the SVGs is illustrative sample data. The nine artboards are static wireframes, not screenshots of an actual run. No application code was changed for this package.

## What the current Arena does

The current Pygame Arena has a title, four tabs, and a shared Overview with a progress ring, “Evolution trail” chart, and three lower indicators. Counter-deck training and fixed-deck matchup evaluation share `Overview / Learning / Evaluation / Conclusions`; general deck evolution uses `Overview / Population / Matchups / Conclusions`. The drawing code switches several labels and a few panels based on mission. Data comes from `TrainingTelemetry` for live progress and `TrainingInsights` for analysis of UI jobs or database runs.

Relevant sources: `py_game/menu/training_menu.py` (`_dashboard_pages`, `_draw_performance_page`, `_draw_evaluation_page`, `_draw_matchups_page`, `_draw_conclusions_page`, `draw_training_dashboard`), `py_game/ui/training_dashboard.py`, and `py_game/training_service.py` (`TrainingTelemetry`, `TrainingInsights`, `job_telemetry`, `job_insights`, `database_insights`). The trainers are `neat_ai/counter_deck_trainer.py`, `neat_ai/matchup_trainer.py`, and `neat_ai/deck_builder_trainer.py`.

### Main shortcomings observed

| Observation | Why it matters |
| --- | --- |
| Counter training and fixed-deck matchup share the same four-tab structure. | They answer different questions: “which counter decks beat my selected deck?” versus “how do these two fixed decks compare?”. Conditional headings alone do not make their evidence easy to scan. |
| The common Overview leads with a generic ring and fitness trail. | Fitness is not the primary outcome for every mission. Matchup W/D/L and checkpoint win rates, counter-candidate strength, and builder population quality each deserve different emphasis. |
| Counter training has more detail in `summary.json` than `TrainingInsights` exposes. | The summary records final `counter_matchups`, but the Arena mostly surfaces aggregate W/D/L and one `top_counter`; the other counter candidates are hard to inspect. A candidate table would need a read-only presentation adapter. |
| A running run can have telemetry before analytic insights exist. | Non-Overview pages may show only “Analyzing this run…”, with little indication of what is pending or which phase is active. The current single progress ring can show phase progress without explaining whether it means inner work or whole-run completion. |
| Some conclusions are more general than the underlying comparison. | A counter run evaluates a selected deck against changing opponents; a single “favored/unfavored” verdict based on pooled wins can read like a fixed-deck verdict. Builder card-level mean fitness is association, not causal card effect. |
| The Arena does not foreground data provenance. | UI job summaries, structured telemetry, and historic database records have different fields. A user should see the source, sample count, and when a metric is unavailable rather than infer that missing data means zero. |

The current layout is responsive in geometry, but a non-overlap rectangle test does not by itself prove that charts, legends, and text remain readable at 640×480. Each proposed direction should be checked visually there before implementation.

## Option A — Mission studio

A familiar tabbed Arena with a mission-specific primary metric, chart, facts, and evidence preview. It is closest to the current navigation and would be the smallest conceptual change.

| Mission | Main question | Mission tabs | Visual |
| --- | --- | --- | --- |
| Counter-deck training | Which evolved counter decks pressure the selected deck? | Overview · Counter pool · Controllers · Findings | [PNG](arena-a-counter.png) · [SVG](arena-a-counter.svg) |
| Fixed-deck matchup | How does Deck A fare against Deck B as controllers mature? | Overview · Checkpoints · Outcome · Findings | [PNG](arena-a-matchup.png) · [SVG](arena-a-matchup.svg) |
| General deck evolution | How did population quality and matchups change? | Overview · Population · Matchups · Card signals | [PNG](arena-a-builder.png) · [SVG](arena-a-builder.svg) |

This option is best if maintaining the existing four-page mental model matters. It needs mission-specific tabs and a counter-candidate adapter, but most panels can use current telemetry and insights.

## Option B — Run timeline

A live operations screen. The left column names the actual mission phases; the center separates **current phase progress** from overall run status; the right shows live signals and stop controls. It is designed for running jobs, with a clear transition to completed results.

| Mission | Visible live stages | Visual |
| --- | --- | --- |
| Counter-deck training | Persistent controllers → candidate decks → validation games → counter selection | [PNG](arena-b-counter.png) · [SVG](arena-b-counter.svg) |
| Fixed-deck matchup | Coevolve controllers → freeze checkpoint → seat-balanced games → final outcome | [PNG](arena-b-matchup.png) · [SVG](arena-b-matchup.svg) |
| General deck evolution | Seed run → outer generation → nested controllers → holdout matchups | [PNG](arena-b-builder.png) · [SVG](arena-b-builder.svg) |

This option is best if users spend a lot of time watching active experiments. It must handle nested or repeated phases correctly; the stage list is a cycle/context model, not a one-way completion checklist. The illustrative percentage in the artboards is a **phase** percentage. An implementation must not relabel it as whole-run completion unless that value is separately and reliably calculated.

## Option C — Evidence desk

A completed-run analysis screen: large outcome trend, mission evidence table, headline result, and interpretation guardrails. It makes result provenance and limitations more visible than the current Conclusions page.

| Mission | Evidence table | Visual |
| --- | --- | --- |
| Counter-deck training | Final counter candidates and their win rates against the selected deck | [PNG](arena-c-counter.png) · [SVG](arena-c-counter.svg) |
| Fixed-deck matchup | Deck A win rate at each checkpoint; final W/D/L shown alongside | [PNG](arena-c-matchup.png) · [SVG](arena-c-matchup.svg) |
| General deck evolution | Strong/diverse matchup examples and observed deck-level scores | [PNG](arena-c-builder.png) · [SVG](arena-c-builder.svg) |

This option is best for interpreting completed runs and thesis/research review. It needs a companion live screen or a simplified running state. Candidate counter rows exist in the counter trainer's summary but are not currently mapped into `TrainingInsights`; the other shown evidence is largely available already. Builder card signals should retain the existing non-causal wording.

## Data boundaries for any choice

- Counter-deck training: `skill_evaluations` gives **selected-deck win rate against the counter population by counter generation**. Final candidate rows are in `counter_matchups`; a chart of “best counter win rate by generation” is **not** directly available from the current compact summary, so the artboards use the aggregate trend instead.
- Fixed-deck matchup: `skill_evaluations` gives checkpoint W/D/L; `evaluation` gives final W/D/L. Deck A and Deck B must stay labeled, and games are seat-balanced. Do not present a learning checkpoint as a completed final result.
- General deck evolution: `generation_scores` provides worst/average/best population fitness for database-backed runs; `favorable_matchups`, `difficult_matchups`, `top_cards`, and totals support completed-run details. Historic database records may lack the original request parameters; show “not recorded” rather than reconstructing them.
- Live telemetry can expose phase, outer/checkpoint generation, current batch progress, best score, workers, elapsed time, and sometimes ETA. Avoid a fabricated ETA or final verdict while running. If telemetry is sparse, show the last known event and “waiting for trainer data”.
- Failed, interrupted, cancelled, pending, and analysis-loading states need dedicated messages; partial values must be marked as partial. Stop training belongs only to a UI-owned running job and should retain the existing confirmation.

## How to choose

Choose **A** for a balanced evolution of the current Arena, **B** if live progress is the biggest pain, or **C** if understanding finished results is the priority. A practical combined direction would use **B while running** and **C when completed**, with A's mission-specific tabs as the navigation frame. The choice is left open; these are alternatives for review, not an implementation instruction.

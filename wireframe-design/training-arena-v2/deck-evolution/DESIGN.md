# General deck evolution

> Superseded concept studies. The current, data-audited direction is [feasible-analysis/README.md](feasible-analysis/README.md), with five pages and an explicit notebook boundary. These older boards are retained for reference, not recommended as a literal Arena implementation contract.

Question: **Did the deck population improve, maintain diversity, and reveal credible balance or matchup findings?** A single champion score cannot answer this. The design moves from an accessible story to evidence and method, while keeping outer deck generations separate from inner controller generations.

Two directions:

1. [Research dashboard](01-research-dashboard.png) starts with one cautious plain-language finding, then shows population fitness (best, median, worst), composition-aware diversity, matchup structure and card-balance signals. It suits a beginner or a professor skimming one run. Story, Evidence and Methods are separate depths, not separate missions.
2. [Investigation workbench](02-investigation-workbench.png) starts from research questions: improvement, diversity, card shifts, matchup polarization, controller learning. The illustrated question is “Which cards shifted?” with pick rate versus generation-local presence lift, an observed/limit card, and a compact evidence ledger. It suits deliberate analysis.

The [research evidence board](03-research-evidence.png) shows definitions, denominators, run scope and interpretation limits for the selected run. The [presence-lift explainer](04-metric-explainer.png) demonstrates a beginner explanation beside the formula and sample caveats. The displayed numbers are invented examples; methods and caveats follow the analysis notebooks.

## Evidence layers

| Layer | Question and suggested measure | Source / constraint |
| --- | --- | --- |
| Integrity | Was the run complete, balanced and reproducible? Show seed, run ID, completed outer generations, observed population, holdout coverage and missing-data flags. | `definitive_training_analysis.ipynb` explicitly checks integrity before interpretation. Historical DB runs may lack exact original settings; say “not recorded”. |
| Population | Did typical deck quality improve, or only the best outlier? Plot worst, median, best or a fitness distribution by **outer** generation. | `database_insights()` currently has worst/average/best; median/distribution needs additional aggregation. No claim of meta improvement from champion alone. |
| Diversity | Did decks converge into similar lists? Show similarity-adjusted effective archetypes, top-archetype share and viable share, with exact signatures as a secondary reference. | `academic_metrics.ipynb` and `definitive_training_analysis.ipynb` explain why exact signatures overstate variety. These are beyond current `TrainingInsights`. |
| Matchups | Which deck archetypes beat which local opponents? Use a generation-sliced heatmap, weighted meta performance and balance/polarization metrics. | `insight_charts.ipynb` and `academic_metrics.ipynb`; keep row-deck perspective and sample counts visible. Do not mix early and late groups silently. |
| Cards | Which cards are associated with higher scoring decks? Show generation-local presence lift, pick rate, copy count and sample sizes; pair lift as a deeper page. | Presence is a deck-composition proxy. It is not drawn-card, played-card or ability-use win rate. Near-universal cards leave a small comparison group. |
| Controllers | Are rankings sensitive to player skill? Compare inner-generation learning curves or frozen holdout checkpoints by deck archetype. | Outer and inner axes must never share one unlabeled “generation” axis. Historical runs may not log direct card-use actions. |

The notebook graphs can require expensive aggregation over an 8.2 GB `train.db`; this is a design target, not a suggestion to query that file every frame. A future UI should use background/cached, run-scoped summaries and show analysis-loading, partial and unavailable states. Each displayed academic metric needs a definition, exact population or game denominator, scope (run/seed/outer generation), source, and one interpretation limit. A professor should be able to audit it; a beginner should still get a one-sentence explanation first.

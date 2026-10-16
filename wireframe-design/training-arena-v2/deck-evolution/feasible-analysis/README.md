# Deck evolution — feasible-analysis rethink

This is the **current design direction**, replacing the earlier research-dashboard/workbench proposals for consideration. It is still **design only**: no Pygame, trainer, notebook, or database code was changed. The five SVG artboards are editable, and PNGs are previews. [Overview contact sheet](overview.png).

**Current scope:** these five pages belong to **completed runs only**. Page 1 is retrospective completion/evidence coverage. In-progress runs use the separate [shared progress screen](../../run-progress/README.md); failed/stopped/incomplete runs never enter these results. The finished Population page now shows an Adopt selected deck action; [deck-adoption](../../deck-adoption/README.md) defines its browser, name dialog and save behavior. The underlying five-page analysis stays as designed.

The proposal is deliberately a **hybrid**. The Arena can provide substantial, honest run-scoped analysis from the data already recorded. Heavy controller-level and multi-seed research should remain in cached Jupyter analyses. Making every notebook chart a live Pygame tab is a no-go for this phase, especially against the existing 8.2 GB `train.db`.

The separate live monitor can accurately show **outer generation and completed deck-pairing progress**. It cannot currently show exact progress inside every nested controller-training pairing; that needs new telemetry.

| Page | Question | What it actually uses |
| --- | --- | --- |
| [1. Run pulse](01-run-pulse.png) | What completed, and is this run analyzable? | Completed run metadata and observed genome/match/deck coverage; retrospective only. |
| [2. Population](02-population.png) | Did the population differentiate or converge? | Per-outer-generation score range, population count and exact-signature reference. **Not** an absolute improvement curve. |
| [3. Local matchups](03-local-matchups.png) | Which scheduled opponents favored a selected deck? | Generation-local `match_dbt.result` scores and actual opponent coverage. Scores are **not win rates**; short holdouts are exploratory. |
| [4. Composition](04-composition.png) | Which cards became common? | Stored deck-card IDs, card-copy counts and generation-scoped deck presence. No claim about drawing/playing the card. |
| [5. Research boundary](05-research-boundary.png) | Which questions belong in notebooks or need new logs? | Explicit availability/methodology map and a run-ID handoff. |

Pages 1–4 use **measured local run DB 13** for their example values, not invented results. [Data audit and arithmetic](DATA_AUDIT.md) records the sources and limits. The example is one completed 12-generation run; the implementation must draw from the selected **completed** run and label unavailable measures. Its final-generation deck population has 20 members, but the database holds 243 genome/deck rows over the whole run. These are different denominators.

## The two decisions this design makes

1. **No false quality trend.** Deck fitness is relative to contemporaneous, coevolving opponents. DB 13's best local fitness fell from +58.8 to +25.2 while its score range narrowed from 118.5 to 56.8. That supports a statement about differentiation, not a claim that deck quality improved or worsened. A true absolute-progress chart would require a stable benchmark/evaluation protocol not recorded for this historical run.
2. **No false win rates.** Builder `match_dbt.result` is a deck-relative fitness score; it cannot be relabeled as a win percentage. DB 13 configured 20 holdout seed pairs, roughly 40 final held-out games per scheduled pair—well below the user's 1,000-game target for a stable comparison. The Arena can surface promising/exploratory pairs, then a separate Duel evaluation can test a chosen pair with a larger sample.

The earlier [research dashboard](../01-research-dashboard.png), [investigation workbench](../02-investigation-workbench.png), [research evidence](../03-research-evidence.png), and [metric explainer](../04-metric-explainer.png) remain as **superseded design studies**. Their ambitious metrics can inform notebook research, but they are not the recommended Arena implementation contract.

## If this is still too much

The safe minimum is Page 1 plus a clearly labeled “Open run in analysis notebook” handoff. Pages 2–4 are valuable because they use relatively small run-scoped deck/match tables, but they should be added only with background/cached aggregation and clear data-quality states. Do not query raw `pc_match` during rendering or promise professor-grade results from a single seed.

To regenerate the SVGs and PNGs, run `python wireframe-design/training-arena-v2/deck-evolution/feasible-analysis/render.py` from the repository root; it writes only inside this folder and requires `rsvg-convert`.

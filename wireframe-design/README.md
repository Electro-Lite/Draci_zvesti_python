# AI training menu concepts

**Selected direction:** Concept 01, Training cockpit. The implementation-ready package is [COCKPIT_SPEC.md](COCKPIT_SPEC.md) plus [HANDOFF_PROMPT.md](HANDOFF_PROMPT.md). The player, deck-builder, and launch-review artboards are [01](01-training-cockpit.svg), [01B](01b-cockpit-deck-builder.svg), and [01C](01c-cockpit-launch-review.svg). The older 02 and 03 remain as exploration only.

Three static 1600×900 wireframes explore a full-screen training setup. Open the PNGs for quick review or the SVGs for sharp zooming. [`layout-map.drawio`](layout-map.drawio) is an editable, three-page section map for diagrams.net; it describes the major regions rather than every small control.

| Concept | Image | Main idea | Trade-off |
| --- | --- | --- | --- |
| 01 Cockpit | [PNG](01-training-cockpit.png) · [SVG](01-training-cockpit.svg) | All player-controller settings, preflight, and persistent summary on one screen | Dense at smaller window sizes |
| 02 Workbench | [PNG](02-experiment-workbench.png) · [SVG](02-experiment-workbench.svg) | Separate study design, evidence quality, cost, and review sections for deck-builder work | More technical and best suited to a large screen |
| 03 Guided | [PNG](03-guided-training-flow.png) · [SVG](03-guided-training-flow.svg) | One group of decisions per full-screen stage with a persistent summary | Slower for repeated expert use |

## Basis in the current application

The existing `TrainingMenu` presents setup as a vertical row list, with advanced values revealed on demand. Its request model has two missions: a specific-deck player controller and a deck-builder experiment. The controller path uses a player deck, opponent deck, generations, workers, and games per maturity checkpoint. The builder path uses seeds, outer and inner generations, matches per candidate, evaluator workers, and holdout seed pairs. Both have a run label and presets. The diagrams keep those settings distinct because their workload models differ.

The visual language follows `py_game/theme.py`: dark background and panels, amber selection, green success, blue informational accents. The current app defaults to 1280×720 and supports resized or full-screen display. These 1600×900 boards are design targets rather than a claim that the current menu already uses the layout.

## Original exploration note

The initial exploration recommended the Workbench for research runs. The selected direction is now the Cockpit, with a dedicated builder state that keeps seed choice, nested training, holdouts, and workload visible together.

The wireframes propose direct field editing, a visible preflight summary, and more flexible seed entry. The current menu cycles through fixed options and seed sets, so implementing those interactions would require new UI work. The builder trainer also has an outer-worker setting that the current Pygame request fixes at 2; it is deliberately absent from the mock controls until the request model can expose it. The preflight text illustrates validation state; it does not claim to measure machine capacity.

For smaller windows, stack each horizontal section into a scrollable column, keep the launch action pinned, and retain the summary as a collapsible panel. Preserve numeric bounds from `TrainingRequest.validate()` and label the workload as simulated work rather than a wall-clock ETA.

To regenerate the images after editing the script, run `python wireframe-design/render_wireframes.py` from the repository root. This requires `rsvg-convert`; only this folder is written.

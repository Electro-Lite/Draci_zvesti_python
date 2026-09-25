# Training cockpit: implementation design

Status: approved visual direction. This document defines the intended UI; no application code is changed here.

## Source of truth and scope

Use [01-training-cockpit.svg](01-training-cockpit.svg) as the visual reference for the player mission, [01b-cockpit-deck-builder.svg](01b-cockpit-deck-builder.svg) for the builder mission, and [01c-cockpit-launch-review.svg](01c-cockpit-launch-review.svg) for confirmation. If labels or behavior disagree, this specification takes precedence. The older 02 and 03 concepts are discarded alternatives.

Replace only the **setup presentation and its interactions** in the Pygame AI Training menu. Keep the existing run library, guide, dashboard, job service, trainer commands, artifacts, and stop behavior accessible. No new training algorithm or scientific setting is implied by these visuals. Existing `TrainingRequest`, `TrainingKind`, `TrainingPreset`, `training_workload`, and `evaluation_checkpoints` define the data and calculations.

## Core experience

This is one full-window cockpit with three regions:

1. **Left rail:** mission selector, section shortcuts, Run library, Back, and a Training guide link. The numbered entries are **focus/scroll shortcuts within the same setup screen**, never wizard pages. The first concept image says “Subjects / Training / Evaluation / Review & launch”; implement the simpler semantic groups Mission, Configuration, Evidence, Preflight. The rail does not hide settings.
2. **Center:** directly editable controls, grouped by mission, then workload and preflight. Selecting a preset populates values. Every control remains visible and editable. No “Advanced settings” toggle.
3. **Right:** persistent read-only summary, live validity state, and a prominent Review & launch action. It reflects the current draft, including unsaved text input, and uses the same source values as the launch request.

The content fills the available Pygame window, including full-screen mode. The visual is intentionally denser than the old row list. It should still work in a resized 640×480 window through reflow and scrolling.

## Visual system

Use the existing `py_game/theme.py` palette as the source of truth. The artboards approximate it: background `#0D1219`, panel `#18212B`, raised panel `#202C38`, border `#45586A`, text `#EFF3F7`, muted `#A8B6C5`, amber `#ECB14B`, green `#5BC684`, blue `#6DA9DF`. Amber indicates selection and the primary action; green indicates valid/ready; danger red is reserved for errors. Never use color as the only signal: selected, ready, error and disabled states also have text and/or an icon.

Use `LayoutMetrics` or equivalent responsive geometry. At the 1600×900 reference size: outer margin 42 px; rail x42–328 (286 wide); center x348–1150 (802); summary x1170–1558 (388); 20 px gutters. Main content starts y151 and ends y826. Cards have about 12–14 px corner radius and a slim colored left edge. Titles are around 20 px; field labels around 12–14 px uppercase; values around 17–18 px. Input and button targets should be at least 42 px high where the available size allows. Match the application's font and drawing conventions rather than depending on SVG font availability.

At 1280×720, reduce margins and gutters before shrinking text or targets. Use a narrower rail and summary, and a scrollable center when needed. From roughly 900–1100 px width, move the rail to a compact horizontal header and place the summary below or beside the center according to available room. At 640×480, use a single scrollable column: mission switch at top, controls, workload/preflight, summary, and a pinned launch/footer action. Keep focused controls visible when scrolling; never clip long deck IDs, seed lists, error text, or the launch action. Do not rely on mouse wheel alone: keyboard navigation must reach off-screen controls. Recompute hit boxes on resize and full-screen changes.

## Shared controls and state

The default mission is the current `TrainingKind.PLAYER_DECK`; preserve the current default selections unless a persisted setting already overrides them. The mission switch has exactly two choices: “Train a deck controller” and “Evolve and study decks”. Keep an independent draft for each mission during the menu session, so switching away and back does not erase entered values. The run label can differ by mission. Do not persist drafts to disk unless the existing app already does so.

Show four preset chips: Quick check, Balanced, Deep study, Custom. The first three use the current `PLAYER_PRESETS` and `BUILDER_PRESETS` values exactly. Selecting a preset applies its relevant values immediately and updates the summary/workload. Editing any preset-controlled value makes the active chip Custom. Custom is a state indicator, not a separate preset that resets fields. Mission switches restore that mission's last draft and preset state. Changing run label or deck choice need not mark the numerical preset Custom; changing a numerical or seed-set preset field does.

Direct editing means keyboard entry for numeric fields, with optional arrow or step buttons for common values. Do not limit users to the current small cycle lists. Enter/Tab commits a parseable field; Escape cancels its in-progress edit and restores the last valid value; empty/invalid text remains visible with an inline error until corrected. A single click should focus the field rather than unexpectedly cycle it. The run label should be editable in place or through a clearly attached dialog. Long values should scroll within a focused field or truncate with a way to view the full value.

Use ordinary dropdowns/searchable lists for deck IDs and preset seed sets. The seed control should support entering a comma-separated list of integer seeds as a Custom value, while preserving the existing built-in sets as shortcuts. Show seed count and a compact preview in the collapsed field; show the full list in the editor and launch review. Preserve entered seed order. Do not silently replace an invalid seed token or silently deduplicate a valid list.

## Player-controller mission

The center top card contains run label, player deck, opponent deck, controller generations, workers, and presets. Both decks are chosen from `DBUtil().get_all_deck_ids()`; the same deck may serve as both player and opponent. If the deck list is empty, show an empty state and disable launch with a clear instruction. Do not display invented deck IDs as live values; the artboard labels are sample data.

The lower card contains games per maturity checkpoint, a **read-only** checkpoint sequence from `evaluation_checkpoints(generations)`, deck-selection status, and preflight. Checkpoints are derived; they are not another editable parameter. Update them when generations change. Use `training_workload()` for the headline and details. At the illustrated Balanced settings, 40 generations generate 4,200 training games plus three × 100 evaluation games = about 4,500 simulated games. This is a workload count, not an ETA.

Visible player values and validation:

| Field | Request mapping | Validation |
| --- | --- | --- |
| Run label | `run_label` | Nonblank after trim; at most 64 characters per `TrainingRequest.validate()` |
| Player deck | `deck_id` | Must be selected and present in the deck list |
| Opponent deck | `opponent_deck_id` | Must be selected and present; same as player is allowed |
| Generations | `evaluator_generations` | Integer 1–10,000 |
| Workers | `workers` | Integer 1–128 |
| Games/checkpoint | `evaluation_games` | Integer 1–100,000 |

## Deck-builder mission

Use the same rail and summary shell. Replace deck selectors and evaluation-game field with run label, seed set, outer generations, inner generations, matches per candidate, evaluator workers, and holdout seed pairs. The screenshot shows a four-seed Custom draft: 400009, 450001, 500009, 550007; one outer generation; 50 inner generations; 12 matches; 12 evaluator workers; 20 holdout pairs. The center lower card shows the workload and preflight. The right summary lists seed count, evolution depth, rivals and holdouts, with the exact seed list available in the seed editor and review dialog.

Visible builder values and validation:

| Field | Request mapping | Validation |
| --- | --- | --- |
| Run label | `run_label` | Same as player mission |
| Seed set | `seeds` | At least one integer; preserve order |
| Outer generations | `outer_generations` | Integer 1–1,000 |
| Inner generations | `evaluator_generations` | Integer 1–10,000 |
| Matches/candidate | `matches_per_genome` | Even integer 2–10,000 |
| Evaluator workers | `workers` | Integer 1–128 |
| Holdout seed pairs | `holdout_seed_pairs` | Integer 1–10,000 |

Compute the workload with the existing `training_workload()`: `len(seeds) × outer_generations × 20 × matches_per_genome ÷ 2` outer matchups **plus nested controller training**. The `20` is the current assumed builder population in that helper, not a user control. At the illustrated settings the number is 480 outer matchups. Do not convert this count into an ETA or a total game count. The nested cost is substantial and should remain explicitly named.

The current Pygame command fixes `outer_workers=2`. Show that only as an engine note if useful; it must not look editable. Do not surface trainer-only flags such as checkpoint restoration, population guards, diagnostic checkpoints, crossplay, raw game logging, or run description as functional controls without a separate product decision and request-model support.

## Summary, preflight and launch

Summary values are read-only mirrors of the draft and update on every committed field change. If a focused text field contains an uncommitted edit, show it in the summary only if it parses; otherwise show a pending/invalid state. The summary never silently represents different data from the request that would launch.

Preflight checks must be derived from actual validation, not from imagined system measurements. Valid examples: label nonblank/within length, decks exist, integer ranges, even match count, seed parse, `TrainingRequest.validate()` result. Do not claim “8 workers available” or that hardware resources have been measured. On errors: mark the field, show one concrete message next to it, show “Fix N settings” in the summary, disable Review & launch, and let the user jump to the first issue. Green “Ready to review” appears only when all visible and request-level checks pass. If an external check such as deck loading is slow, show checking state separately; do not block the draw loop.

Clicking Review & launch opens a focused confirmation layer. The review shows mission, run label, every setting that affects the trainer command, exact seeds or deck IDs, workload headline/details, and a plain statement that workload is not wall-clock time. Include Back to settings and Start training. Back/Escape closes the dialog without losing the draft. Start calls the existing training service exactly once after final validation. Show a busy state and prevent repeat activation while starting. On success open the existing Runs view and surface the new job; on failure stay in the cockpit with the error and intact draft. Preserve the existing confirmation and cancellation semantics even if the visual presentation changes.

On a player run, review must include player deck, opponent deck, generations, workers, evaluation games, and checkpoint sequence. On a builder run, review must include all seeds, outer and inner generations, matches per candidate, evaluator workers, holdout pairs, and the fixed outer-worker fact if shown elsewhere. Do not pass the fixed fact as an editable user value.

## Input and navigation

- Mouse: hover and click on all controls; wheel scrolls the hovered content area. Tooltips may explain “generations,” “holdout pairs,” and workload, but essential meanings appear in labels or helper text.
- Keyboard: Tab/Shift+Tab traverse controls in visual order; arrows navigate options/step numeric values when an editor is not active; Enter activates or commits; Escape cancels an edit/dialog before it exits the training menu. The focused item has a visible border. Maintain compatibility with the game's directional/Start/Back keys where practical.
- Rail shortcuts focus and scroll to Mission, Configuration, Evidence, or Preflight. They do not change request values. Run library and Training guide open the existing views; returning to setup restores the draft and reasonable focus/scroll position. Back returns to the previous menu only when no editor or dialog is open.
- Errors are announced visibly and place focus on the first invalid field after the user tries to review. Avoid wraparound cycling of numeric values during direct entry.

## State matrix

| State | Center / right behavior | Primary action |
| --- | --- | --- |
| Valid draft | Live workload, green preflight, exact summary | Review & launch enabled |
| Invalid or incomplete draft | Inline errors, count and first-error jump | Disabled |
| No deck records, player mission | Empty selector explanation; keep other fields editable | Disabled |
| Editing a field | Draft value visible; summary marks pending if unparseable | Disabled until committed/valid |
| Review open | Dim setup, full settings + workload visible in modal | Start training |
| Starting | Busy indicator; one start request only | Disabled |
| Start failed | Return to setup, keep draft, show service error | Review again after correction/retry |
| Start succeeded | Existing Runs view with new job | Existing run actions |

## Acceptance checklist for implementation

- At 1600×900, both missions visually follow the SVGs with all relevant settings and summary visible.
- At 1280×720, the default app size, fields stay readable and operable; at 640×480 no controls overlap or become unreachable, with scrolling and keyboard focus working.
- Presets retain their current values, Custom does not overwrite a draft, mission switches preserve each draft, and the review/request always match the visible configuration.
- Every exposed numeric setting accepts valid values across the `TrainingRequest` range and rejects invalid values with a field-level message. Builder matches reject odd values.
- Player workload/checkpoints and builder workload use existing calculation helpers. No fabricated ETA or hardware availability message appears.
- No launch occurs until explicit Start training in the review; double activation creates only one job. Cancellation and service errors keep the draft.
- Existing Runs, guide, dashboard, return navigation, and training service behavior remain available.

## Relevant code for the implementing AI

`py_game/menu/training_menu.py` (current setup rows, input, launch, library and dashboard); `py_game/ui/training_setup.py` (presets/workload); `py_game/training_service.py` (`TrainingRequest`, validation, command and job lifecycle); `neat_ai/training_plan.py` (checkpoint schedule); `py_game/ui/layout.py`, `py_game/ui/widgets.py`, `py_game/theme.py`, and `py_game/settings.py` (responsive geometry, controls, palette and window limits). The implementation may refactor setup-specific code, but should not replace the run library or dashboard to achieve this design.

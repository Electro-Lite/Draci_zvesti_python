# Prompt for the second AI conversation

Please implement the approved **AI Training cockpit** design in the Pygame application. You already know this codebase, so use the files below as the product and visual contract and inspect the current code before editing.

Design package:

- Player mission visual: `/home/electro/Personal/UPOL/Draci_zvesti_merged/wireframe-design/01-training-cockpit.svg`
- Deck-builder mission visual: `/home/electro/Personal/UPOL/Draci_zvesti_merged/wireframe-design/01b-cockpit-deck-builder.svg`
- Launch-review visual: `/home/electro/Personal/UPOL/Draci_zvesti_merged/wireframe-design/01c-cockpit-launch-review.svg`
- Complete behavior, responsive layout, validation, state, and acceptance criteria: `/home/electro/Personal/UPOL/Draci_zvesti_merged/wireframe-design/COCKPIT_SPEC.md`

The user chose concept 01. Treat `COCKPIT_SPEC.md` as authoritative where the initial SVG is schematic or labels differ. The numbered rail is in-page section navigation, not a wizard. Use the application's existing palette and settings. Make the setup fill the window, expose all mission-relevant controls without an Advanced toggle, preserve the current preset values and training behavior, and keep the Runs, guide, dashboard, and stop flows working.

Implement direct editing for the existing request fields, including numeric values across the current validated ranges and a custom comma-separated builder seed list. Preserve separate in-session drafts when switching missions. Compute the checkpoint list and workload from the existing helpers; do not invent an ETA or claim hardware availability. Keep the current trainer-only/fixed settings out of editable controls. The right summary and confirmation must match the exact request sent to `TrainingService.start()`. Validate visibly before review and launch only after an explicit confirmation. Handle empty deck lists, malformed input, cancellation, launch-in-progress, and service failure without losing the draft.

Make it usable at 1600×900, the default 1280×720, and the supported 640×480 minimum through responsive layout and scrolling. Mouse and keyboard focus must reach every setting. Test the input/state behavior, request mapping, confirmation and single-launch behavior, and layout at those sizes. Inspect the existing dirty worktree and preserve unrelated user changes. Do not use the 02 Workbench or 03 Guided designs as implementation targets.

When finished, show the changed files, explain how each mission and the review flow work, report tests and any limits, and provide screenshots of both missions at 1280×720 if the environment can render Pygame.

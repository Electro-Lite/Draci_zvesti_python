# Current handoff guide — give this to the implementation AI first

This page has precedence over older phase notes where they discuss partial results or placeholders. All artboard values are illustrative except the documented measured DB 13 Evolution examples. Design files only were changed here; no application implementation is included.

For a **single message to one experienced implementation AI**, copy [MASTER_HANDOFF_PROMPT.md](MASTER_HANDOFF_PROMPT.md) verbatim and give this design directory as context. The phased prompts below are useful if you prefer smaller implementation passes.

## Non-negotiable routing

`live pending/running/stopping → shared progress → completed + artifact ready → one-time explicit Open results button → mission-specific finished results`

Opening a completed run later from Runs bypasses the handoff and goes straight to that mission's results. Stopped/failed/cancelled/interrupted/historical incomplete runs get status/logs only. Results and adoption are never shown early. A completed status without a readable result artifact means “Preparing results…”/error, not a false finished page.

## Give these files in this order

1. **First prompt:** [run-progress/HANDOFF_PROMPT.md](run-progress/HANDOFF_PROMPT.md). Also give its [notes](run-progress/IMPLEMENTATION_NOTES.md) and [three artboards](run-progress/README.md). This establishes the shared active screen, honest ETA, state boundary, and explicit completion handoff.
2. **Existing finished Counter/Duel results:** use [Counter 1 prompt](counter-decks/HANDOFF_PROMPT.md) and [Duel 2 prompt](matchup-evaluation/HANDOFF_PROMPT.md) only for whichever finished layouts are not already implemented. Their top routing overrides control; do not reimplement already working screens merely because an older phase prompt asks to. Keep their separate layouts and the 1,000-game evaluation guidance.
3. **Evolution finished results, if still a placeholder:** [five-page Evolution prompt](deck-evolution/feasible-analysis/HANDOFF_PROMPT.md), [design](deck-evolution/feasible-analysis/README.md), and [data audit](deck-evolution/feasible-analysis/DATA_AUDIT.md). Keep the five-page approach. Page 1 is a retrospective coverage page, **not** the active progress page. Deep academic analysis stays in Jupyter/raw SQL.
4. **Adoption prompt:** [deck-adoption/HANDOFF_PROMPT.md](deck-adoption/HANDOFF_PROMPT.md) and [notes](deck-adoption/IMPLEMENTATION_NOTES.md). Add to selected Counter candidate and selected evolved deck in completed results; new name, exact copied composition, fresh user-deck identity, `is_AI=false`, no source mutation.

The implementer can combine phases in one coding session, but should verify each boundary separately. If Counter/Duel/Evolution already exist in the target branch, treat their prompts as design contracts and focus on routing/progress/adoption. Inspect the dirty worktree before edits; never overwrite unrelated changes. Report actual code changes and tests in the implementation conversation.

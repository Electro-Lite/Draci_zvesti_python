# In-progress Training Arena — separate shared design

This screen is for a **live, unfinished run only**. It restores the old dashboard's reassuring loading/ring, nested generation and batch progress, elapsed time, and event trail. The three artboards show [running](01-running-progress.png), [completion handoff](02-complete-handoff.png), and [stopped/failed/interrupted](03-unfinished-state.png). SVGs are editable; example figures are illustrative.

The screen is shared in structure, not in invented metrics. The hierarchy reads: overall run → current mission phase → only the nested levels the trainer actually reports. Counter finding may show counter generation, controller generation, and candidate validation games. Duel evaluation may show learning generation and current checkpoint-game count. Deck evolution may show outer generation and deck pairings, but its nested controller learning remains indeterminate unless telemetry is added. Do not call pairings games.

An ETA is useful only when measured enough to defend it. Use trainer-provided ETA or recent completed units with a range and clear “estimate” label; otherwise show “Estimating…”. Never freeze a stale number, infer completion from 100% progress, or show a fabricated ETA from the wireframe.

After authoritative job completion **and result artifact readiness**, this same live session briefly shows the completion handoff with an explicit “Open Counter/Duel/Evolution results” button. It does not auto-navigate. Selecting a completed run later from Runs opens the mission result directly. If completion was reported but the artifact is not ready, show “Preparing results…” and disable the button until it is safe. Failed, stopped, cancelled, interrupted, or historically incomplete runs do not enter the completed result layouts.

The finished-run Deck Evolution “Run pulse” page is a **retrospective evidence/coverage page**, not this live progress screen. It remains part of the existing five-page result design.

Read [implementation notes](IMPLEMENTATION_NOTES.md) and use the [copyable prompt](HANDOFF_PROMPT.md). Run `python wireframe-design/training-arena-v2/run-progress/render.py` to regenerate SVG/PNG previews.

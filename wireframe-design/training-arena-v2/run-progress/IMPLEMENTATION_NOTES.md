# Progress-screen implementation contract

## State and navigation

| Run state | Arena destination | Result access |
| --- | --- | --- |
| Pending/running/stopping, live UI-owned job | Shared progress screen | No mission-result tabs, analysis, or Adopt deck |
| Completed; artifact still loading/verifying | Completion handoff, “Preparing results…” | Disabled until artifact is valid |
| Completed; artifact ready, currently being watched | Completion handoff | User explicitly clicks “Open [mission] results” |
| Completed, selected later from Runs | Its distinct finished mission layout | Direct entry; do not replay handoff |
| Stopped/failed/cancelled/interrupted/incomplete | Honest terminal status and logs | No finished-run design or adoption |

Use authoritative `TrainingJob.status`/persisted run completion, not a 100% telemetry counter, to cross the completed boundary. Preserve identity, Back to runs, logs, stop confirmation, and safe exit. The Stop action is shown only for a stoppable UI-owned live job. Historical `incomplete` records are not live jobs. Consider immediate navigation to the progress screen after launch, or a clear “View progress” route from Runs; either path must make the common screen easy to reach.

## What each mission can honestly show

- Counter finding: outer counter generations; persistent controller-learning generations; current candidate-test game count when emitted; phase/event text. Candidate names, W/D/L and deck compositions belong to its **finished** result screen only.
- Duel evaluation: the two populations' learning generations/checkpoint phase and game counts if emitted. If current telemetry is only checkpoint-level, show an indeterminate learning substep instead of simulated per-genome counts. Checkpoint outcomes and both deck compositions belong to its **finished** result screen only.
- Deck evolution: outer generation and completed/total deck-pairing queue. Current inner controller training inside a pairing has no exact live counter; label it “running, count unavailable” unless instrumented. Fitness/population/composition analysis belongs to its **finished** five-page design.

`TrainingService.job_telemetry()` currently exposes phase, generation, round_completed/round_total, phase_progress, eta_seconds, elapsed_seconds and checkpoint_generation. Counter and matchup may need additional non-blocking telemetry for every desired nested level. Do not reverse-engineer a precise level from unrelated settings or render loops. For overall percent, derive from known units/phases and disclose assumptions; otherwise use indeterminate progress rather than a misleading weighted 58%. Preserve completed numerator/denominator, phase labels, and timestamps. Keep data reads/aggregation off the Pygame draw loop.

ETA: show elapsed always. Prefer a trainer estimate when current and evidence-backed. Otherwise estimate from several completed comparable work units (e.g. a rolling median/EMA), update when phase changes, show a range or “about”, and replace with “Estimating…” when there are too few samples, work changes shape, the run stalls, or the estimate expires. Do not guarantee finish time or go negative. Progress and ETA must remain consistent with actual configured workload.

At completion, verify the mission-specific summary/result material is available before enabling “Open results”; handle write lag and malformed/empty artifact with a recoverable explanation. Avoid automatic transition so the completion state is visible. Keep a timestamped recent-event trail with bounded memory, but no early candidate/checkpoint analytical table. Verify narrow windows by scrolling instead of shrinking all text. Test all transitions, stale telemetry, missing ETA, stop/failed cases, artifact lag, and resume from Runs.

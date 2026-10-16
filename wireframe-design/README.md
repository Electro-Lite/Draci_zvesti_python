# AI training workbench design

For the **Training Arena**, start with the [current implementation handoff guide](training-arena-v2/HANDOFF_GUIDE.md). It separates a shared [in-progress screen](training-arena-v2/run-progress/README.md) from finished mission-specific results and [deck adoption](training-arena-v2/deck-adoption/README.md). The previous generic Arena studies are preserved in [archive/arena-v1](archive/arena-v1/).

The implemented direction is the full-window **Training workbench** described
in [COCKPIT_SPEC.md](COCKPIT_SPEC.md) and [HANDOFF_PROMPT.md](HANDOFF_PROMPT.md).

The original Concept 01 SVGs are retained as visual references for the dark
panel system, density, responsive summary, and launch review. Their old
“Training cockpit” and two-mission labels are historical and are not the
current product vocabulary. Concepts 02 and 03 remain exploration only.

The current workbench has three mission drafts: counter-deck training,
two-deck matchup evaluation, and general deck evolution. At narrow sizes the
same controls stack into one scrollable column with a pinned launch action.

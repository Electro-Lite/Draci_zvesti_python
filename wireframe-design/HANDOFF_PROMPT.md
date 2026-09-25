# Training workbench handoff

Implement and maintain the full-window **Training workbench** in the Pygame AI
Training menu. Use [COCKPIT_SPEC.md](COCKPIT_SPEC.md) as the behavior contract;
the older SVGs remain useful only for palette, density, and panel proportions.

The workbench has three mission choices in one persistent left rail, without a
numbered wizard or section-step labels:

- Counter-deck training: one user deck remains fixed while counter decks and
  persistent controllers evolve across the whole run.
- Matchup evaluation: two fixed decks coevolve controllers and report Deck A
  win rate over controller generations.
- General deck evolution: the existing seed-based tournament deck builder.

Preserve a separate in-memory draft for each mission. Keep all relevant fields
directly editable, retain presets and the explicit launch review, and keep Runs,
the guide, dashboards, stop behavior, and exit warning available. The setup
must work at 1600×900, 1280×720, and 640×480 with keyboard and mouse access.

Results must use mission-specific language. Counter results show aggregate
selected-deck win rate and Top counter. Matchup results identify Deck A and
Deck B and show win rate across generations. Never describe either mission as
playing against random opponents.

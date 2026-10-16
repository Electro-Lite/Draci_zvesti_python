# Adopt a discovered deck — shared save flow

Entry points exist only in **completed** mission results: the currently selected Counter candidate on [Counter 1](../counter-decks/01-compositions-first.png), and the currently selected generated Deck Evolution deck on its [Population page](../deck-evolution/feasible-analysis/02-population.png) or [generated-deck browser](01-evolution-deck-browser.png). Duel does not need adoption because its participants are already user-selected decks. The Counter “Inspect deck” action is still removed; composition remains directly on the page.

The [browser](01-evolution-deck-browser.png) makes selection explicit for any stored evolved deck, not only the top-ranked example. The [name dialog](02-name-and-confirm.png) asks for the new user-deck name and explains that the source is copied. [Success](03-adoption-success.png) confirms actual persistence, then offers Back to results/Open in editor. There is no “saved” state before the transaction succeeds.

The source run and AI artifact are immutable. Adoption copies the **exact card IDs and copy counts** into a fresh deck identity; it is saved as `is_AI = false` and appears in My decks/user-deck pickers. If a source composition cannot be resolved or validated, explain why and do not silently change cards to make it legal. Handle existing same-name/same-composition user decks explicitly rather than overwriting or claiming a new save. Names in the artboards are examples.

Read the [implementation contract](IMPLEMENTATION_NOTES.md) and [copyable prompt](HANDOFF_PROMPT.md). Regenerate assets with `python wireframe-design/training-arena-v2/deck-adoption/render.py`.

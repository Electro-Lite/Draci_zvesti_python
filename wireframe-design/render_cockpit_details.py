"""Render the selected cockpit's missing mission and launch-review states.

Run: python wireframe-design/render_cockpit_details.py
"""

from render_wireframes import Board, GOLD, GREEN, BLUE, MUTED, TEXT, PANEL, PANEL2, LINE


def rail(b: Board, current: str):
    b.panel(42, 151, 286, 675, "Mission & navigation", "Section shortcuts, not a wizard", BLUE)
    b.pill(60, 223, 250, 47, "Train a deck controller", GOLD if current == "player" else MUTED)
    b.pill(60, 281, 250, 47, "Evolve and study decks", GOLD if current == "builder" else MUTED)
    b.line(60, 352, 310, 352)
    names = [("01", "Mission"), ("02", "Configuration"), ("03", "Evidence"), ("04", "Preflight")]
    for i, (number, name) in enumerate(names):
        y = 390 + 54 * i
        selected = i == 1
        b.rect(59, y-27, 251, 43, PANEL2 if selected else PANEL, 8, GOLD if selected else LINE)
        b.text(76, y, number, 14, GOLD if selected else MUTED, 700)
        b.text(116, y, name, 17, TEXT if selected else MUTED, 600)
    b.pill(60, 605, 250, 40, "Training guide  →", MUTED)
    b.pill(60, 656, 250, 40, "←  Back to menu", MUTED)
    b.pill(60, 743, 250, 47, "Open run library  →", BLUE)


def builder():
    b = Board("Training cockpit / deck builder", "Same shell, mission-specific fields and workload", "01B")
    rail(b, "builder")
    b.panel(348, 151, 802, 420, "Configure deck evolution", "All request values visible; any edit switches preset to Custom")
    for x, label, active in [(368, "Quick check", False), (545, "Balanced", False), (722, "Deep study", False), (899, "Custom", True)]:
        b.pill(x, 223, 165, 40, label, GOLD if active else MUTED)
    b.field(369, 300, 350, "Run label", "replicated-study")
    b.field(742, 300, 384, "Seed set", "4 seeds  ▾", "400009 · 450001 · 500009 · 550007")
    b.field(369, 389, 235, "Outer generations", "1  ▾", "Deck evolution cycles")
    b.field(626, 389, 235, "Inner generations", "50  ▾", "Controller learning")
    b.field(883, 389, 243, "Matches / candidate", "12  ▾", "Must be even")
    b.field(369, 478, 350, "Evaluator workers", "12  ▾")
    b.field(742, 478, 384, "Holdout seed pairs", "20  ▾", "40 paired games per matchup")

    b.panel(348, 587, 802, 239, "Workload & preflight", "Computed as settings change; no fabricated ETA", GREEN)
    b.rect(369, 655, 363, 133, PANEL2, 8, LINE)
    b.text(386, 686, "480 outer matchups", 22, GOLD, 700)
    b.text(386, 718, "plus nested controller training", 15, TEXT)
    b.text(386, 753, "4 seeds × 1 outer × 20 × 12 ÷ 2", 14, MUTED)
    b.rect(746, 655, 380, 133, PANEL2, 8, LINE)
    b.text(763, 685, "Preflight", 18, TEXT, 700)
    b.text(763, 714, "✓  Seeds valid   ✓  Even match count", 14, GREEN)
    b.text(763, 745, "Engine: 20 target decks · 2 outer workers", 13, MUTED)
    b.text(763, 768, "These are fixed by the current trainer", 12, MUTED)

    b.panel(1170, 151, 388, 675, "Run summary", "Always visible before committing", GOLD)
    for y, name, value in [(235,"MISSION","Deck builder experiment"),(298,"PRESET","Custom"),(361,"SEEDS","4 independent runs"),(424,"EVOLUTION","1 outer / 50 inner"),(487,"RIVALS","12 per candidate"),(550,"HOLDOUT","20 seed pairs")]:
        b.text(1194, y, name, 12, MUTED, 700, spacing=1)
        b.text(1194, y+25, value, 18, TEXT, 600)
        b.line(1194, y+40, 1534, y+40)
    b.rect(1194, 640, 340, 70, "#2b352f", 9, GREEN)
    b.text(1212, 670, "READY TO REVIEW", 16, GREEN, 700)
    b.text(1212, 693, "Workload is not a duration estimate", 13, MUTED)
    b.pill(1194, 734, 340, 55, "Review & launch  →", GOLD, "#47351d", 18)
    b.footer("Builder mode replaces deck selectors with seeds and nested controls", "01B  ·  BUILDER")
    b.save("01b-cockpit-deck-builder")


def review():
    b = Board("Training cockpit / launch review", "Focused confirmation before a trainer process starts", "01C")
    b.rect(42, 151, 1516, 675, PANEL, 14, LINE)
    b.text(72, 198, "Setup remains unchanged behind this review", 22, MUTED, 700)
    b.rect(42, 151, 1516, 675, "#0a0e14", 14)
    b.rect(314, 191, 972, 594, PANEL, 16, GOLD, 2)
    b.text(346, 243, "Review training request", 31, TEXT, 700)
    b.text(346, 274, "Deck builder experiment  ·  replicated-study", 17, MUTED)
    b.line(346, 295, 1254, 295)
    b.text(346, 328, "CONFIGURATION", 13, GOLD, 700, spacing=1)
    for y, left, right in [(362,"Seed set","400009, 450001, 500009, 550007"),
                            (399,"Generations","1 outer · 50 inner"),
                            (436,"Matches / candidate","12"),
                            (473,"Evaluator workers","12"),
                            (510,"Holdout seed pairs","20")]:
        b.text(346, y, left, 17, MUTED)
        b.text(1239, y, right, 17, TEXT, 600, "end")
        b.line(346, y+12, 1254, y+12)
    b.rect(346, 548, 908, 85, PANEL2, 8, LINE)
    b.text(365, 580, "480 outer matchups plus nested controller training", 19, GOLD, 700)
    b.text(365, 610, "This workload is not an ETA. Starting creates a training job and opens Runs.", 14, MUTED)
    b.pill(346, 682, 218, 59, "Back to settings", MUTED)
    b.pill(936, 682, 318, 59, "Start training", GOLD, "#47351d", 19)
    b.footer("Validation errors return focus to their fields; cancellation keeps the draft", "01C  ·  REVIEW")
    b.save("01c-cockpit-launch-review")


if __name__ == "__main__":
    builder()
    review()

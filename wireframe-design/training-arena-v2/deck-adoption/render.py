"""Render design-only adoption flow; never touches application data."""

from html import escape
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
W, H = 1600, 900
BG, PANEL, RAISED, LINE = "#0d1219", "#18212b", "#23313f", "#45586a"
TEXT, MUTED, GOLD, GREEN, BLUE = "#eff3f7", "#a8b6c5", "#ecb14b", "#5bc684", "#6da9df"


class Board:
    def __init__(self, title, subtitle, badge):
        self.s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', f'<rect width="{W}" height="{H}" fill="{BG}"/>']
        self.box(0, 0, W, 6, GOLD, 0)
        self.text(42, 37, "DRACI ZVESTI  /  TRAINING ARENA", 15, GOLD, 700)
        self.text(42, 82, title, 34, TEXT, 700)
        self.text(42, 113, subtitle, 16, MUTED)
        self.box(1355, 36, 203, 37, "#382e1e", 8, GOLD)
        self.text(1457, 61, badge, 12, GOLD, 700, "middle")
        self.line(42, 835, 1558, 835)
        self.text(42, 868, "Design-only example · displayed values are illustrative unless explicitly marked observed.", 12, MUTED)

    def box(self, x, y, w, h, fill=PANEL, r=10, stroke=None):
        self.s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"' + (f' stroke="{stroke}"' if stroke else "") + "/>")

    def text(self, x, y, v, size=16, color=TEXT, weight=400, anchor="start"):
        self.s.append(f'<text x="{x}" y="{y}" font-family="DejaVu Sans, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{color}">{escape(str(v))}</text>')

    def line(self, x1, y1, x2, y2):
        self.s.append(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{LINE}"/>')

    def panel(self, x, y, w, h, title, note="", accent=GOLD):
        self.box(x, y, w, h, PANEL, 12, LINE)
        self.box(x, y, 5, h, accent, 2)
        self.text(x + 22, y + 32, title, 21, TEXT, 700)
        if note:
            self.text(x + 22, y + 58, note, 13, MUTED)

    def button(self, x, y, w, label, color=GOLD, fill="#47351d"):
        self.box(x, y, w, 55, fill, 8, color)
        self.text(x + w / 2, y + 35, label, 16, color, 700, "middle")

    def save(self, name):
        self.s.append("</svg>")
        path = ROOT / f"{name}.svg"
        path.write_text("\n".join(self.s) + "\n", encoding="utf-8")
        subprocess.run(["rsvg-convert", "-o", str(ROOT / f"{name}.png"), str(path)], check=True)


def browser():
    a = Board("Choose an evolved deck", "Completed deck-evolution run DB 13 · select the exact generated deck to copy", "COMPLETED RUN")
    a.panel(42, 153, 490, 654, "Generated decks", "Generation: 12 ▾ · filter all · local fitness order", BLUE)
    rows = [("Gen12_ID191", "+25.2", True), ("Gen12_ID198", "+18.4", False), ("Gen12_ID194", "+12.7", False), ("Gen12_ID205", "+8.1", False), ("Gen12_ID173", "+4.6", False), ("Gen12_ID192", "−3.8", False)]
    for i, (name, score, active) in enumerate(rows):
        y = 252 + i * 78
        a.box(66, y, 442, 61, "#3d3526" if active else RAISED, 7, GOLD if active else LINE)
        a.text(85, y + 26, name, 16, TEXT, 700)
        a.text(85, y + 48, "Generated artifact · outer generation 12", 11, MUTED)
        a.text(489, y + 36, score, 16, GREEN, 700, "end")
    a.text(67, 767, "Scroll/filter all stored generations and decks.", 12, MUTED)
    a.panel(552, 153, 1006, 508, "Selected deck composition", "Gen12_ID191 · exact recorded card-copy counts · local fitness is not a win rate", GREEN)
    a.text(580, 244, "Card", 14, MUTED, 700)
    a.text(1512, 244, "Copies", 14, MUTED, 700, "end")
    for i in range(10):
        y = 277 + i * 35
        a.text(581, y, f"{i+1:02d}   Stored card name / ID {i+1}", 14, TEXT)
        a.text(1511, y, "2" if i < 2 else "1", 14, BLUE, 700, "end")
        if i < 9:
            a.line(580, y + 9, 1515, y + 9)
    a.panel(552, 681, 1006, 126, "Copy into my decks", "The generated source remains in this training run; adoption creates a new user deck.", GOLD)
    a.button(1238, 729, 291, "Adopt selected deck  →")
    a.save("01-evolution-deck-browser")


def naming():
    a = Board("Counter results", "Selected candidate · composition and test results remain visible underneath", "COMPLETED RUN")
    a.panel(42, 153, 1516, 652, "Selected counter · 12 cards", "Adopt this counter as my deck", BLUE)
    for i in range(9):
        a.text(75, 277 + i * 48, f"{i+1:02d}   Source card {i+1}", 16, MUTED)
    a.box(0, 0, W, H, "#080b10", 0)
    a.s[-1] = a.s[-1].replace('fill="#080b10"', 'fill="#080b10" opacity="0.74"')
    a.panel(361, 167, 878, 565, "Save a copy to My decks", "Original counter candidate stays unchanged in the completed run.", GOLD)
    a.text(399, 282, "New deck name", 16, TEXT, 700)
    a.box(399, 305, 802, 65, RAISED, 8, BLUE)
    a.text(421, 346, "My Blue Counter", 19, TEXT)
    a.text(399, 405, "Source", 14, MUTED)
    a.text(1200, 405, "Counter run · selected candidate #3", 14, TEXT, 600, "end")
    a.text(399, 443, "Composition", 14, MUTED)
    a.text(1200, 443, "12 cards · exact copy counts preserved", 14, TEXT, 600, "end")
    a.line(399, 469, 1200, 469)
    a.text(399, 511, "Will save as a user deck (is_AI = false) with a fresh ID.", 16, GREEN, 700)
    a.text(399, 542, "If this name/composition already exists, offer to open it or choose another name.", 13, MUTED)
    a.button(399, 631, 240, "Cancel", BLUE, RAISED)
    a.button(777, 631, 424, "Save as my deck  →")
    a.save("02-name-and-confirm")


def success():
    a = Board("Deck added to My decks", "The training artifact was preserved; the new copy is now a normal player deck.", "SAVED")
    a.panel(236, 175, 1128, 573, "My Blue Counter", "User deck · newly assigned deck ID · 12 cards", GREEN)
    a.text(285, 296, "✓", 56, GREEN, 700)
    a.text(371, 285, "Ready to edit and use", 25, TEXT, 700)
    a.text(371, 323, "This deck now appears in user-deck lists and relevant deck pickers.", 16, MUTED)
    a.line(282, 366, 1316, 366)
    a.text(284, 414, "Original source", 15, MUTED)
    a.text(1316, 414, "Counter candidate #3 · unchanged", 15, TEXT, 700, "end")
    a.text(284, 454, "New classification", 15, MUTED)
    a.text(1316, 454, "My deck · not AI-generated", 15, GREEN, 700, "end")
    a.button(282, 600, 395, "Back to results", BLUE, RAISED)
    a.button(810, 600, 505, "Open in deck editor  →")
    a.save("03-adoption-success")


if __name__ == "__main__":
    browser()
    naming()
    success()

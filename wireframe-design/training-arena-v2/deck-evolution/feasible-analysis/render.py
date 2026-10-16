"""Render the evidence-first deck-evolution Arena rethink.

Design-only assets. The numbers shown are read-only observations from local DB 13;
the script does not query or modify the application database.
Requires rsvg-convert.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
W, H = 1600, 900
BG, PANEL, RAISED, LINE = "#0d1219", "#18212b", "#23313f", "#46586a"
TEXT, MUTED = "#eff3f7", "#a8b6c5"
GOLD, GREEN, BLUE, RED = "#ecb14b", "#5bc684", "#6da9df", "#e26467"
PAGES = ("Run pulse", "Population", "Matchups", "Composition", "Research")


class Art:
    def __init__(self, title: str, subtitle: str, active: int, badge: str = "OBSERVED · DB 13"):
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
            f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        ]
        self.box(0, 0, W, 6, GOLD, 0)
        self.txt(42, 37, "DRACI ZVESTI  /  TRAINING ARENA", 15, GOLD, 700, spacing=2)
        self.txt(42, 82, title, 34, TEXT, 700)
        self.txt(43, 113, subtitle, 16, MUTED)
        self.box(1362, 36, 196, 36, "#382e1e", 8, GOLD)
        self.txt(1460, 60, badge, 12, GOLD, 700, "middle")
        self.box(42, 151, 236, 674, PANEL, 13, LINE)
        self.txt(64, 185, "DECK EVOLUTION", 15, GOLD, 700)
        self.txt(64, 211, "One run · five questions", 12, MUTED)
        for i, page in enumerate(PAGES):
            y = 237 + i * 64
            self.box(58, y, 204, 50, "#3d3526" if i == active else RAISED, 8, GOLD if i == active else LINE)
            self.txt(74, y + 31, f"{i + 1:02d}  {page}", 15, TEXT if i == active else MUTED, 700 if i == active else 500)
        self.line(58, 609, 262, 609)
        self.txt(64, 640, "RUN  DB 13", 13, BLUE, 700)
        self.txt(64, 665, "replicated-final", 13, TEXT)
        self.txt(64, 695, "Seed 104729", 13, MUTED)
        self.txt(64, 726, "Outer generations: 12", 12, MUTED)
        self.txt(64, 751, "Inner generations: 20", 12, MUTED)
        self.line(42, 844, 1558, 844)
        self.txt(42, 875, "Measured local DB 13 unless noted. Scores are relative to each generation's opponent pool.", 12, MUTED)
        self.txt(1558, 875, f"EVOLUTION / {active + 1:02d} OF 05", 12, GOLD, 700, "end")

    def box(self, x, y, w, h, fill=PANEL, r=10, stroke=None):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"' +
                          (f' stroke="{stroke}" stroke-width="1"' if stroke else "") + "/>")

    def txt(self, x, y, s, size=16, color=TEXT, weight=400, anchor="start", spacing=0):
        self.parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-family="DejaVu Sans, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" letter-spacing="{spacing}">{escape(str(s))}</text>')

    def line(self, x1, y1, x2, y2, color=LINE, width=1):
        self.parts.append(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="{width}"/>')

    def poly(self, points, color, width=3):
        coords = " ".join(f"{x},{y}" for x, y in points)
        self.parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>')
        for x, y in points:
            self.parts.append(f'<circle cx="{x}" cy="{y}" r="3" fill="{color}"/>')

    def panel(self, x, y, w, h, title, note="", accent=GOLD):
        self.box(x, y, w, h, PANEL, 12, LINE)
        self.box(x, y, 5, h, accent, 2)
        self.txt(x + 22, y + 31, title, 20, TEXT, 700)
        if note:
            self.txt(x + 22, y + 55, note, 13, MUTED)

    def save(self, stem):
        self.parts.append("</svg>")
        svg = ROOT / f"{stem}.svg"
        png = ROOT / f"{stem}.png"
        svg.write_text("\n".join(self.parts) + "\n", encoding="utf-8")
        subprocess.run(["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(png), str(svg)], check=True)


def run_pulse():
    a = Art("Deck evolution / run pulse", "What finished, what is still running, and which data can be trusted.", 0)
    a.panel(296, 151, 1262, 154, "Run DB 13 · replicated-final", "Completed  ·  23 July 2026  ·  63m 47s", GREEN)
    a.txt(322, 248, "12 / 12", 39, GREEN, 700)
    a.txt(530, 229, "OUTER GENERATIONS", 12, MUTED, 700)
    a.txt(530, 254, "Deck populations completed", 17, TEXT, 600)
    a.box(915, 229, 616, 20, RAISED, 8)
    a.box(915, 229, 616, 20, GREEN, 8)
    a.txt(915, 277, "1,458 / 1,458 outer pairings resolved", 15, TEXT, 600)
    a.panel(296, 324, 604, 350, "Generation work", "Pairings are deck-vs-deck evaluations, not individual games", BLUE)
    counts = [120, 120, 120, 120, 120, 126, 126, 120, 126, 120, 120, 120]
    for i, n in enumerate(counts):
        x = 326 + i * 45
        h = round(117 * n / 126)
        a.box(x, 537 - h, 25, h, BLUE if i < 11 else GREEN, 3)
        if i in (0, 5, 11):
            a.txt(x + 12, 560, str(i + 1), 12, MUTED, 700, "middle")
    a.txt(325, 600, "20–21 genomes per generation", 15, TEXT)
    a.txt(325, 631, "The live version shows the current pairing queue and phase.", 13, MUTED)
    a.panel(918, 324, 640, 350, "Evidence readiness", "A trustworthy analysis starts with coverage and provenance", GOLD)
    for i, (k, v, c) in enumerate((
        ("Genome rows", "243 recorded", GREEN),
        ("Outer matchup rows", "1,458 scored", GREEN),
        ("Card compositions", "243 stored deck lists", GREEN),
        ("Fixed benchmark", "Not recorded for this run", RED),
        ("Live inner-loop progress", "Not streamed per pairing", RED),
    )):
        y = 418 + i * 54
        a.txt(945, y, k, 15, MUTED)
        a.txt(1530, y, v, 15, c, 700, "end")
        if i < 4:
            a.line(945, y + 17, 1530, y + 17)
    a.panel(296, 692, 1262, 133, "Read this correctly", "Completion measures executed work; it does not prove the decks improved.", RED)
    a.txt(319, 783, "Next: inspect population spread and composition change without calling relative fitness absolute quality.", 15, TEXT)
    a.save("01-run-pulse")


def population():
    a = Art("Deck evolution / population", "A run can converge without producing stronger decks against a fixed opponent.", 1)
    a.panel(296, 151, 820, 479, "Relative fitness envelope", "Outer generation · measured score range among contemporaries", BLUE)
    low = [-59.8, -49.6, -34.0, -43.3, -48.1, -39.3, -42.0, -57.1, -35.3, -55.2, -37.8, -31.6]
    high = [58.8, 55.4, 38.6, 43.6, 43.7, 30.3, 38.2, 27.2, 37.6, 30.7, 28.8, 25.2]
    chart_x, chart_y, chart_w, chart_h = 352, 278, 705, 245
    for v in (-60, -30, 0, 30, 60):
        y = chart_y + round((65 - v) / 130 * chart_h)
        a.line(chart_x, y, chart_x + chart_w, y, LINE if v else GOLD)
        a.txt(chart_x - 13, y + 5, str(v), 12, MUTED, 500, "end")
    points_hi = [(chart_x + round(i * chart_w / 11), chart_y + round((65 - v) / 130 * chart_h)) for i, v in enumerate(high)]
    points_lo = [(chart_x + round(i * chart_w / 11), chart_y + round((65 - v) / 130 * chart_h)) for i, v in enumerate(low)]
    a.poly(points_hi, GREEN)
    a.poly(points_lo, RED)
    for i in (0, 5, 11):
        a.txt(chart_x + round(i * chart_w / 11), 550, f"Gen {i + 1}", 12, MUTED, 600, "middle")
    a.txt(350, 588, "●  Best local score", 14, GREEN, 700)
    a.txt(570, 588, "●  Worst local score", 14, RED, 700)
    a.panel(1134, 151, 424, 479, "Interpretation guardrail", "Do not call this a quality-improvement curve", RED)
    a.txt(1160, 253, "118.5 → 56.8", 28, GOLD, 700)
    a.txt(1160, 281, "Score spread narrowed, Gen 1 → 12", 13, MUTED)
    a.line(1160, 308, 1532, 308)
    a.txt(1160, 345, "Best score: +58.8 → +25.2", 16, TEXT, 600)
    a.txt(1160, 378, "Mean score: 0 by zero-sum design", 15, MUTED)
    a.txt(1160, 426, "Opponents changed each generation.", 15, TEXT)
    a.txt(1160, 456, "A fixed benchmark was not logged.", 15, TEXT)
    a.txt(1160, 513, "Safe claim: population differentiation", 14, GREEN, 700)
    a.txt(1160, 539, "changed. Absolute strength is unknown.", 14, MUTED)
    a.panel(296, 648, 1262, 177, "Diversity and exemplars", "Exact signatures are a reference, not a full archetype measure", GOLD)
    a.txt(323, 748, "18 / 20", 30, BLUE, 700)
    a.txt(466, 746, "unique deck signatures · Gen 1", 15, MUTED)
    a.txt(866, 748, "16 / 20", 30, BLUE, 700)
    a.txt(1009, 746, "unique deck signatures · Gen 12", 15, MUTED)
    a.txt(323, 790, "Top final deck: Gen12_ID191 · +25.2 versus its own 12 scheduled rivals.", 14, TEXT)
    a.box(1184, 754, 344, 51, "#47351d", 8, GOLD)
    a.txt(1356, 786, "Adopt selected deck  →", 15, GOLD, 700, "middle")
    a.save("02-population")


def matchups():
    a = Art("Deck evolution / local matchups", "Which final-generation opponents favored this deck—and how much evidence is there?", 2)
    a.panel(296, 151, 1262, 113, "Final outer generation · 20 decks · 120 scheduled pairs", "A sparse local network: each deck faced 12 of 19 possible rivals", GOLD)
    a.txt(320, 235, "Selected deck  Gen12_ID191", 20, BLUE, 700)
    a.txt(1531, 235, "Fitness +25.2 vs local slate", 17, TEXT, 600, "end")
    a.panel(296, 282, 778, 422, "Opponent ledger", "Deck 191's score; positive favors row deck, not a win rate", BLUE)
    rows = (("Gen12_ID198", "+69.5", GREEN), ("Gen12_ID194", "+69.3", GREEN),
            ("Gen12_ID205", "+58.8", GREEN), ("Gen12_ID173", "+14.5", GREEN),
            ("Gen12_ID192", "−33.5", RED))
    for i, (rival, score, color) in enumerate(rows):
        y = 391 + i * 53
        a.box(323, y - 26, 725, 46, RAISED, 7, LINE)
        a.txt(343, y + 3, rival, 16, TEXT, 600)
        a.txt(975, y + 3, score, 18, color, 700, "end")
    a.txt(323, 675, "Five shown of 12; actual UI scrolls all opponents and supports selection.", 13, MUTED)
    a.panel(1092, 282, 466, 422, "What the database says", "Matchup score ≠ observed win percentage", RED)
    a.txt(1118, 385, "Result stored: deck-relative fitness", 15, TEXT, 600)
    a.txt(1118, 424, "Planned final holdout: 20 seed pairs", 14, MUTED)
    a.txt(1118, 453, "≈40 games per pair · below 1,000 target", 14, RED, 700)
    a.line(1118, 481, 1532, 481)
    a.txt(1118, 522, "Show as exploratory local evidence.", 15, GOLD, 700)
    a.txt(1118, 557, "Do not turn +69.5 into a win rate.", 14, TEXT)
    a.txt(1118, 593, "For a stable pair comparison, run a", 14, MUTED)
    a.txt(1118, 620, "separate 1,000-game Duel evaluation.", 14, MUTED)
    a.panel(296, 722, 1262, 103, "Research question answered", "Which opponents are promising follow-ups? Not: which deck is universally best.", GREEN)
    a.save("03-local-matchups")


def composition():
    a = Art("Deck evolution / composition", "Which cards became common—and what does that not tell us about play?", 3)
    a.panel(296, 151, 770, 674, "Card adoption · Gen 1 versus Gen 12", "Deck presence, n = 20 decks in each generation; same-run comparison", BLUE)
    a.txt(320, 249, "CARD", 12, MUTED, 700)
    a.txt(736, 249, "GEN 1", 12, MUTED, 700, "end")
    a.txt(1009, 249, "GEN 12", 12, MUTED, 700, "end")
    rows = (("Draci Fanatik", 90, 100), ("Novic", 85, 100),
            ("Paladin", 65, 30), ("Panos", 50, 15), ("Pesak", 85, 80))
    for i, (name, first, last) in enumerate(rows):
        y = 279 + i * 100
        a.box(319, y, 724, 82, RAISED, 7, LINE)
        a.txt(338, y + 31, name, 16, TEXT, 600)
        a.txt(736, y + 31, f"{first}%", 17, BLUE, 700, "end")
        a.txt(1009, y + 31, f"{last}%", 17, GREEN if last >= first else RED, 700, "end")
        a.box(338, y + 50, 665, 10, PANEL, 5)
        a.box(338, y + 50, round(665 * last / 100), 10, GREEN if last >= first else RED, 5)
    a.panel(1084, 151, 474, 360, "Selected card · Draci Fanatik", "Frequency is not causal contribution", GOLD)
    a.txt(1110, 255, "18 / 20 → 20 / 20", 24, GREEN, 700)
    a.txt(1110, 285, "decks containing this card", 13, MUTED)
    a.txt(1110, 341, "Mean copies when present", 15, TEXT, 600)
    a.txt(1110, 373, "1.56 → 3.35", 22, GOLD, 700)
    a.txt(1110, 421, "Near-universal inclusion leaves", 14, MUTED)
    a.txt(1110, 449, "almost no absence comparison group.", 14, MUTED)
    a.panel(1084, 529, 474, 296, "Safe analysis boundary", "Source: stored deck lists, not game-action logs", RED)
    a.txt(1110, 625, "Can report: pick rate, copies, shifts", 15, GREEN, 700)
    a.txt(1110, 663, "Can test: local fitness association", 15, GOLD, 700)
    a.txt(1110, 701, "Cannot claim: drawn/played win rate", 15, RED, 700)
    a.txt(1110, 751, "Go to notebooks for multi-seed replication", 13, MUTED)
    a.txt(1110, 777, "and carefully scoped presence-lift tests.", 13, MUTED)
    a.save("04-composition")


def research_boundary():
    a = Art("Deck evolution / research boundary", "Keep the Arena useful; send expensive or unsupported claims to a reproducible notebook.", 4, "FEASIBILITY DECISION")
    a.panel(296, 151, 1262, 120, "The honest split", "A deep run-scoped deck analysis is feasible; full professor-grade game analysis is not a live Pygame draw task.", GOLD)
    a.txt(320, 239, "Build the first four pages as cached, run-scoped evidence. Treat the notebook as a first-class handoff.", 16, TEXT, 600)
    columns = (
        (296, "Arena · available now", GREEN, (
            "Run progress and integrity",
            "Population score spread",
            "Stored deck composition shifts",
            "Relative local matchup scores",
            "Source, scope and denominators",
        )),
        (722, "Notebook / precompute", GOLD, (
            "Controller learning curves",
            "Held-out W/D/L aggregation",
            "Composition-aware archetypes",
            "Multi-seed replication tests",
            "Uncertainty and sensitivity",
        )),
        (1148, "Not logged for DB 13", RED, (
            "Drawn-card win rate",
            "Played-card win rate",
            "Ability-use causal effects",
            "Turn-level timing effects",
            "Dragon-specific outcome paths",
        )),
    )
    for x, title, accent, items in columns:
        a.panel(x, 289, 410, 390, title, "", accent)
        for i, item in enumerate(items):
            y = 381 + i * 55
            a.box(x + 24, y - 15, 10, 10, accent, 2)
            a.txt(x + 47, y - 4, item, 15, TEXT)
    a.panel(296, 699, 1262, 126, "Go / no-go call", "GO for run-scoped deck-level evidence; NO-GO for making every notebook chart a live Arena tab.", BLUE)
    a.txt(320, 792, "Open the selected run ID in the existing notebooks for heavier controller, holdout and multi-seed work.", 15, TEXT)
    a.save("05-research-boundary")


if __name__ == "__main__":
    run_pulse()
    population()
    matchups()
    composition()
    research_boundary()

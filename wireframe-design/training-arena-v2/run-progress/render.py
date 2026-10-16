"""Render the shared in-progress Training Arena handoff states (design only)."""

from __future__ import annotations

from html import escape
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
W, H = 1600, 900
BG, PANEL, RAISED, LINE = "#0d1219", "#18212b", "#23313f", "#45586a"
TEXT, MUTED = "#eff3f7", "#a8b6c5"
GOLD, GREEN, BLUE, RED = "#ecb14b", "#5bc684", "#6da9df", "#e26467"


class Art:
    def __init__(self, title, subtitle, state):
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
                      f'<rect width="{W}" height="{H}" fill="{BG}"/>']
        self.box(0, 0, W, 6, GOLD, 0)
        self.txt(42, 37, "DRACI ZVESTI  /  TRAINING ARENA", 15, GOLD, 700, spacing=2)
        self.txt(42, 82, title, 35, TEXT, 700)
        self.txt(43, 113, subtitle, 16, MUTED)
        self.box(1364, 36, 194, 37, "#382e1e", 8, GOLD)
        self.txt(1461, 61, state, 13, GOLD, 700, "middle")
        self.line(42, 834, 1558, 834)

    def box(self, x, y, w, h, fill=PANEL, radius=10, stroke=None):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"' +
                          (f' stroke="{stroke}" stroke-width="1"' if stroke else "") + "/>")

    def txt(self, x, y, value, size=16, color=TEXT, weight=400, anchor="start", spacing=0):
        self.parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-family="DejaVu Sans, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" letter-spacing="{spacing}">{escape(str(value))}</text>')

    def line(self, x1, y1, x2, y2, color=LINE):
        self.parts.append(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="1"/>')

    def panel(self, x, y, w, h, title, note="", accent=GOLD):
        self.box(x, y, w, h, PANEL, 13, LINE)
        self.box(x, y, 5, h, accent, 2)
        self.txt(x + 22, y + 32, title, 21, TEXT, 700)
        if note:
            self.txt(x + 22, y + 57, note, 13, MUTED)

    def bar(self, x, y, w, ratio, color, height=18):
        self.box(x, y, w, height, RAISED, height // 2)
        if ratio:
            self.box(x, y, max(2, round(w * min(1, max(0, ratio)))), height, color, height // 2)

    def button(self, x, y, w, h, label, color=GOLD, fill="#47351d"):
        self.box(x, y, w, h, fill, 8, color)
        self.txt(x + w / 2, y + h / 2 + 6, label, 17, color, 700, "middle")

    def footer(self, message):
        self.txt(42, 867, message, 13, MUTED)
        self.txt(1558, 867, "PROGRESS / DESIGN STUDY", 12, GOLD, 700, "end")

    def save(self, stem):
        self.parts.append("</svg>")
        path = ROOT / f"{stem}.svg"
        png = ROOT / f"{stem}.png"
        path.write_text("\n".join(self.parts) + "\n", encoding="utf-8")
        subprocess.run(["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(png), str(path)], check=True)


def running():
    a = Art("Training in progress", "Counter-deck lab · Starter Blue · run counter-lab-42", "RUNNING · EXAMPLE")
    a.panel(42, 151, 1516, 164, "Overall run", "", GREEN)
    a.txt(245, 198, "Counter generation 3 of 5 · phase: testing generated candidates", 13, MUTED)
    a.parts.append('<circle cx="145" cy="245" r="55" fill="none" stroke="#344352" stroke-width="13"/>')
    a.parts.append('<circle cx="145" cy="245" r="55" fill="none" stroke="#5bc684" stroke-width="13" stroke-dasharray="201 346" transform="rotate(-90 145 245)"/>')
    a.txt(145, 251, "58%", 28, GREEN, 700, "middle")
    a.txt(245, 232, "Current phase: validate counter candidates", 23, TEXT, 700)
    a.txt(245, 265, "Results and deck adoption stay locked until the run completes.", 15, MUTED)
    a.bar(1030, 229, 484, .584, GREEN, 20)
    a.txt(1030, 275, "Overall estimate · based on completed work", 13, MUTED)

    a.panel(42, 333, 504, 313, "Three levels of progress", "Show only levels with real telemetry", BLUE)
    for i, (label, amount, ratio, color) in enumerate((
        ("Counter generations", "2 complete · now 3 / 5", .584, GOLD),
        ("Persistent controller training", "40 / 40 generations", 1, BLUE),
        ("Current candidate validation", "18,420 / 20,000 games", .921, GREEN),
    )):
        y = 434 + i * 75
        a.txt(64, y, label, 14, TEXT, 600)
        a.txt(520, y, amount, 13, MUTED, 600, "end")
        a.bar(64, y + 12, 456, ratio, color, 13)

    a.panel(564, 333, 492, 313, "Current phase", "One evolving run, several distinct kinds of work", GOLD)
    for i, (label, mark, color) in enumerate((
        ("Generate candidate decks", "DONE", GREEN),
        ("Train both controller populations", "DONE", GREEN),
        ("Validate candidate decks", "RUNNING", GOLD),
        ("Save generation summary", "WAITING", MUTED),
    )):
        y = 430 + i * 52
        a.box(586, y - 23, 448, 41, RAISED, 7, LINE)
        a.txt(602, y + 3, label, 14, TEXT)
        a.txt(1015, y + 3, mark, 11, color, 700, "end")

    a.panel(1074, 333, 484, 313, "Time and compute", "ETA is conditional, never a promise", BLUE)
    a.txt(1098, 434, "Elapsed", 14, MUTED)
    a.txt(1530, 434, "1h 14m", 18, TEXT, 700, "end")
    a.txt(1098, 483, "Estimated remaining", 14, MUTED)
    a.txt(1530, 483, "about 45–70m", 19, GOLD, 700, "end")
    a.txt(1098, 532, "Workers", 14, MUTED)
    a.txt(1530, 532, "8 active", 18, TEXT, 700, "end")
    a.txt(1098, 588, "Estimate uses recent completed batches;", 13, MUTED)
    a.txt(1098, 612, "show ‘Estimating…’ when evidence is thin.", 13, MUTED)

    a.panel(42, 664, 1516, 149, "Latest run events", "A short, timestamped trail—not early analysis", GREEN)
    a.txt(65, 744, "11:48   Controller generation 40 / 40 completed", 14, TEXT)
    a.txt(65, 777, "12:11   18,420 / 20,000 validation games", 14, TEXT)
    a.button(1117, 721, 190, 55, "Back to runs", BLUE, RAISED)
    a.button(1324, 721, 204, 55, "Stop training", RED, RAISED)
    a.footer("No mission-result tabs while status is running. Stopping still requires confirmation.")
    a.save("01-running-progress")


def complete():
    a = Art("Training complete", "Counter-deck lab · Starter Blue · run counter-lab-42", "READY TO OPEN RESULTS")
    a.panel(42, 151, 1516, 211, "The run finished and its result artifact is ready", "", GREEN)
    a.parts.append('<circle cx="150" cy="267" r="64" fill="none" stroke="#5bc684" stroke-width="14"/>')
    a.txt(150, 277, "100%", 28, GREEN, 700, "middle")
    a.txt(266, 210, "One-time handoff · reopening this run goes straight to Counter results", 13, MUTED)
    a.txt(266, 264, "5 / 5 counter generations complete", 25, TEXT, 700)
    a.txt(266, 302, "Output verified · candidate ranking and compositions available", 16, MUTED)
    a.panel(42, 381, 895, 310, "Finished work", "Progress facts only; head-to-head analysis lives in Counter results", BLUE)
    for i, (label, value) in enumerate((
        ("Counter generations", "5 / 5"),
        ("Controller generations", "40 / 40"),
        ("Validation games", "Recorded in completed summary"),
        ("Elapsed", "2h 03m"),
    )):
        y = 476 + i * 50
        a.txt(66, y, label, 16, MUTED)
        a.txt(910, y, value, 16, TEXT, 700, "end")
    a.panel(955, 381, 603, 310, "What next?", "Results open only on your action", GOLD)
    a.txt(981, 480, "Inspect candidates, outcomes and both", 17, TEXT)
    a.txt(981, 511, "complete deck compositions.", 17, TEXT)
    a.button(981, 558, 551, 65, "Open Counter results  →", GOLD)
    a.button(42, 728, 260, 57, "Back to runs", BLUE, RAISED)
    a.button(318, 728, 260, 57, "View log", MUTED, RAISED)
    a.footer("For finished runs selected from Runs, skip this handoff and open the mission result directly.")
    a.save("02-complete-handoff")


def unfinished():
    a = Art("Training stopped before completion", "Counter-deck lab · Starter Blue · run counter-lab-42", "NOT COMPLETE")
    a.panel(42, 151, 1516, 202, "No completed result is available", "Stopped at counter generation 3 of 5. Partial logs/artifacts are preserved for diagnosis.", RED)
    a.txt(70, 267, "3 / 5", 53, RED, 700)
    a.txt(294, 252, "Final Counter results stay unavailable.", 22, TEXT, 700)
    a.txt(294, 287, "A partial checkpoint is not a finished training run.", 16, MUTED)
    a.panel(42, 373, 1516, 335, "Next action", "Status-specific: stopped, failed or interrupted use the same no-results rule", GOLD)
    a.txt(70, 481, "Review the last trainer messages and decide whether to start a new run.", 19, TEXT)
    a.txt(70, 535, "Do not present partial candidate or matchup metrics in the finished-run design.", 16, MUTED)
    a.button(70, 607, 320, 62, "View log", GOLD)
    a.button(408, 607, 320, 62, "Back to runs", BLUE, RAISED)
    a.footer("An existing historical incomplete database record must not masquerade as a live UI-owned job.")
    a.save("03-unfinished-state")


if __name__ == "__main__":
    running()
    complete()
    unfinished()

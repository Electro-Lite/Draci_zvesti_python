"""Generate standalone SVG/PNG concept boards and an editable draw.io layout map.

Run from the repository root: python wireframe-design/render_wireframes.py
Only files inside wireframe-design are written.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
import subprocess
from xml.etree.ElementTree import Element, SubElement, ElementTree


ROOT = Path(__file__).resolve().parent
W, H = 1600, 900
BG = "#0d1219"
PANEL = "#18212b"
PANEL2 = "#202c38"
LINE = "#45586a"
TEXT = "#eff3f7"
MUTED = "#a8b6c5"
GOLD = "#ecb14b"
GREEN = "#5bc684"
BLUE = "#6da9df"


class Board:
    def __init__(self, title: str, subtitle: str, number: str):
        self.items = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
                      '<rect width="1600" height="900" fill="#0d1219"/>']
        self.rect(0, 0, W, 7, GOLD, 0)
        self.text(42, 38, "DRACI ZVESTI  /  AI TRAINING", 16, GOLD, weight=700, spacing=2)
        self.text(42, 88, title, 38, TEXT, weight=700)
        self.text(43, 119, subtitle, 17, MUTED)
        self.pill(1414, 39, 142, 34, f"CONCEPT {number}", GOLD, "#392d1e", 13)

    def rect(self, x, y, w, h, fill=PANEL, radius=12, stroke=None, sw=1):
        self.items.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"' +
                          (f' stroke="{stroke}" stroke-width="{sw}"' if stroke else "") + '/>')

    def line(self, x1, y1, x2, y2, color=LINE, sw=1):
        self.items.append(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="{sw}"/>')

    def text(self, x, y, value, size=18, color=TEXT, weight=400, anchor="start", spacing=0):
        self.items.append(f'<text x="{x}" y="{y}" fill="{color}" font-family="DejaVu Sans, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" letter-spacing="{spacing}">{escape(str(value))}</text>')

    def pill(self, x, y, w, h, label, color=GOLD, fill=PANEL2, size=15):
        self.rect(x, y, w, h, fill, 9, color)
        self.text(x + w/2, y + h/2 + size*0.35, label, size, color, 700, "middle")

    def panel(self, x, y, w, h, title, note=None, accent=GOLD):
        self.rect(x, y, w, h, PANEL, 14, LINE)
        self.rect(x, y, 5, h, accent, 2)
        self.text(x+23, y+32, title, 20, TEXT, 700)
        if note:
            self.text(x+23, y+56, note, 13, MUTED)

    def field(self, x, y, w, label, value, hint=None, color=BLUE):
        self.text(x, y, label.upper(), 12, MUTED, 700, spacing=1)
        self.rect(x, y+13, w, 39, PANEL2, 7, LINE)
        self.text(x+12, y+40, value, 17, TEXT, 600)
        if hint:
            self.text(x, y+69, hint, 12, color)

    def footer(self, left, right):
        self.line(42, 854, 1558, 854)
        self.text(43, 878, left, 14, MUTED)
        self.text(1557, 878, right, 14, GOLD, 700, "end")

    def save(self, stem):
        self.items.append("</svg>")
        svg = ROOT / f"{stem}.svg"
        png = ROOT / f"{stem}.png"
        svg.write_text("\n".join(self.items) + "\n", encoding="utf-8")
        subprocess.run(["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(png), str(svg)], check=True)


def cockpit():
    b = Board("Training cockpit", "Everything important visible at once · player controller example", "01")
    b.panel(42, 151, 286, 675, "Mission & navigation", "Section shortcuts, not a wizard", BLUE)
    b.pill(60, 223, 250, 47, "Train a deck controller", GOLD)
    b.pill(60, 281, 250, 47, "Evolve and study decks", MUTED)
    b.line(60, 352, 310, 352)
    for yy, num, name, active in [(390,"01","Mission",False),(444,"02","Configuration",True),(498,"03","Evidence",False),(552,"04","Preflight",False)]:
        b.rect(59, yy-27, 251, 43, PANEL2 if active else PANEL, 8, GOLD if active else LINE)
        b.text(76, yy, num, 14, GOLD if active else MUTED, 700)
        b.text(116, yy, name, 17, TEXT if active else MUTED, 600)
    b.pill(60, 605, 250, 40, "Training guide  →", MUTED)
    b.pill(60, 656, 250, 40, "←  Back to menu", MUTED)
    b.pill(60, 743, 250, 47, "Open run library  →", BLUE)

    b.panel(348, 151, 802, 334, "Configure controller", "Preset fills fields; each field remains directly editable")
    for x,label,chosen in [(367,"Quick check",False),(545,"Balanced",True),(723,"Deep study",False),(901,"Custom",False)]:
        b.pill(x, 223, 165, 40, label, GOLD if chosen else MUTED)
    b.field(369, 299, 350, "Run label", "thesis-control-01")
    b.field(742, 299, 384, "Player deck", "Starter Blue_1  ▾")
    b.field(369, 388, 350, "Opponent deck", "Killer Queen_1  ▾")
    b.field(742, 388, 181, "Generations", "40  ▾")
    b.field(945, 388, 181, "Workers", "8  ▾")

    b.panel(348, 501, 802, 325, "Evaluation & validation", "Settings and launch conditions in the same view", GREEN)
    b.field(369, 595, 250, "Games / checkpoint", "100  ▾")
    b.field(641, 595, 216, "Checkpoints", "10 · 25 · 40", "Derived from generations")
    b.field(879, 595, 247, "Deck selection", "2 decks selected", "Both IDs must exist", GREEN)
    b.rect(369, 675, 757, 110, PANEL2, 9, LINE)
    b.text(386, 703, "Preflight", 17, TEXT, 700)
    b.text(386, 731, "✓  Run label valid      ✓  Decks selected      ✓  Worker count valid", 15, GREEN)
    b.text(386, 760, "Estimated 4,500 simulated games · workload only, no time promise", 14, MUTED)

    b.panel(1170, 151, 388, 675, "Run summary", "Always visible before committing", GOLD)
    for yy, name, value in [(235,"MISSION","Specific deck player"),(298,"PRESET","Balanced"),(361,"DECK","Starter Blue_1"),(424,"OPPONENT","Killer Queen_1"),(487,"GENERATIONS","40"),(550,"EVALUATION","100 games/checkpoint")]:
        b.text(1194, yy, name, 12, MUTED, 700, spacing=1)
        b.text(1194, yy+25, value, 18, TEXT, 600)
        b.line(1194, yy+40, 1534, yy+40)
    b.rect(1194, 640, 340, 70, "#2b352f", 9, GREEN)
    b.text(1212, 670, "READY TO REVIEW", 16, GREEN, 700)
    b.text(1212, 693, "Confirm launch in next step", 13, MUTED)
    b.pill(1194, 734, 340, 55, "Review & launch  →", GOLD, "#47351d", 18)
    b.footer("Best for expert repeat use: dense, immediate comparison", "A  ·  COCKPIT")
    b.save("01-training-cockpit")


def workbench():
    b = Board("Experiment workbench", "Independent sections for the nested deck builder experiment", "02")
    b.pill(43, 151, 294, 39, "Deck builder experiment", GOLD)
    b.pill(349, 151, 225, 39, "Specific deck player", MUTED)
    b.text(1547, 178, "RUN LABEL  /  final-deck-discovery", 17, TEXT, 600, "end")

    b.panel(42, 210, 499, 257, "01  Design the study", "What is repeated, and for how long", BLUE)
    b.field(65, 284, 220, "Independent seeds", "4 seed set  ▾", "104729, 130363, 155921, 196613")
    b.field(306, 284, 212, "Outer generations", "1  ▾", "Deck evolution cycles")
    b.field(65, 380, 220, "Inner generations", "50  ▾", "Controller learning per candidate")
    b.field(306, 380, 212, "Matches / candidate", "12  ▾", "Even count required")

    b.panel(560, 210, 499, 257, "02  Evidence quality", "Holdout games determine deck strength", GREEN)
    b.field(583, 284, 214, "Holdout seed pairs", "20  ▾", "40 games per pairing")
    b.field(818, 284, 217, "Evaluator workers", "12  ▾", "Inner parallel matches")
    b.rect(583, 380, 452, 58, PANEL2, 8, LINE)
    b.text(600, 404, "Frozen controllers + matched seeds", 15, TEXT, 700)
    b.text(600, 427, "Both seating orders · paired evaluation", 13, MUTED)

    b.panel(1078, 210, 480, 257, "03  Workload model", "Computed from current scheduling formula", GOLD)
    b.text(1102, 300, "480", 52, GOLD, 700)
    b.text(1237, 296, "outer matchups", 19, TEXT, 600)
    b.text(1237, 322, "plus nested controller training", 14, MUTED)
    b.line(1102, 354, 1534, 354)
    b.text(1102, 388, "4 seeds × 1 outer gen × 20 × 12 ÷ 2", 16, TEXT)
    b.text(1102, 428, "This is workload, not a clock estimate", 14, MUTED)

    b.panel(42, 484, 1017, 342, "04  Review the experiment", "Wide review area for method, validation and implications", GOLD)
    b.rect(65, 558, 299, 223, PANEL2, 9, LINE)
    b.text(84, 591, "Configuration", 18, TEXT, 700)
    for yy, txt in [(627,"•  4 independent seed runs"),(659,"•  1 outer / 50 inner generations"),(691,"•  12 rival decks per candidate"),(723,"•  12 evaluator workers")]:
        b.text(84, yy, txt, 15, MUTED)
    b.rect(379, 558, 310, 223, PANEL2, 9, LINE)
    b.text(397, 591, "Preflight checks", 18, TEXT, 700)
    for yy, txt in [(627,"✓  Seed set is valid"),(659,"✓  Matches count is even"),(691,"✓  Worker count in range"),(723,"✓  20 holdout pairs")]:
        b.text(397, yy, txt, 15, GREEN)
    b.rect(705, 558, 331, 223, PANEL2, 9, LINE)
    b.text(723, 591, "Experimental note", 18, TEXT, 700)
    b.text(723, 626, "One outer generation keeps", 15, MUTED)
    b.text(723, 653, "seed runs independent.", 15, MUTED)
    b.text(723, 698, "Comparison remains available", 15, MUTED)
    b.text(723, 725, "after the run completes.", 15, MUTED)

    b.panel(1078, 484, 480, 342, "05  Launch controls", "Final checks and a deliberate start", GOLD)
    b.text(1102, 567, "PRESET", 12, MUTED, 700, spacing=1)
    b.pill(1102, 582, 136, 37, "Quick check", MUTED)
    b.pill(1248, 582, 136, 37, "Balanced", MUTED)
    b.pill(1394, 582, 140, 37, "Custom", GOLD)
    b.rect(1102, 653, 432, 66, "#2b352f", 9, GREEN)
    b.text(1119, 681, "All fields valid", 17, GREEN, 700)
    b.text(1119, 704, "Review the request before starting", 13, MUTED)
    b.pill(1102, 742, 432, 55, "Review & launch  →", GOLD, "#47351d", 18)
    b.footer("Best for research: separates schedule, evidence and workload", "B  ·  WORKBENCH")
    b.save("02-experiment-workbench")


def guided():
    b = Board("Guided training flow", "Full-screen pages with one decision group at a time", "03")
    steps = [("1","Mission"),("2","Decks"),("3","Learning"),("4","Evaluation"),("5","Launch")]
    for i,(num,name) in enumerate(steps):
        x=42+i*306
        b.rect(x, 151, 286, 58, "#47351d" if i==2 else PANEL, 9, GOLD if i==2 else LINE)
        b.text(x+20, 187, num, 21, GOLD if i==2 else MUTED, 700)
        b.text(x+54, 187, name, 18, TEXT if i==2 else MUTED, 600)
    b.panel(42, 231, 1068, 568, "Step 3  /  Learning schedule", "Control the training depth and resource use", BLUE)
    b.text(67, 333, "How long should the controller learn?", 29, TEXT, 700)
    b.text(67, 369, "Choose a starting point, then adjust the numbers below.", 17, MUTED)
    for x,label,desc,active in [(67,"Quick check","10 generations · 4 workers",False),(405,"Balanced","40 generations · 8 workers",True),(743,"Deep study","65 generations · 12 workers",False)]:
        b.rect(x, 406, 314, 111, "#47351d" if active else PANEL2, 10, GOLD if active else LINE, 2 if active else 1)
        b.text(x+20, 446, label, 21, TEXT, 700)
        b.text(x+20, 483, desc, 14, GOLD if active else MUTED)
    b.field(68, 572, 300, "Controller generations", "40  ▾", "10–10,000 supported")
    b.field(391, 572, 300, "Parallel workers", "8  ▾", "1–128 supported")
    b.rect(714, 573, 369, 91, PANEL2, 8, LINE)
    b.text(731, 601, "Maturity checkpoints", 15, MUTED, 700)
    b.text(731, 638, "10    →    25    →    40", 22, GREEN, 700)
    b.rect(68, 704, 1015, 65, PANEL2, 8, LINE)
    b.text(85, 732, "Why this matters", 16, GOLD, 700)
    b.text(85, 756, "More generations add training games; checkpoints show whether learning continues.", 14, MUTED)

    b.panel(1130, 231, 428, 568, "Live review", "Follows each step so context is never lost", GOLD)
    for yy,name,value in [(315,"MISSION","Deck controller"),(390,"PLAYER DECK","Starter Blue_1"),(465,"OPPONENT","Killer Queen_1"),(540,"SCHEDULE","40 generations / 8 workers")]:
        b.text(1154, yy, name, 12, MUTED, 700, spacing=1)
        b.text(1154, yy+26, value, 18, TEXT, 600)
        b.line(1154, yy+41, 1534, yy+41)
    b.rect(1154, 627, 380, 72, PANEL2, 8, LINE)
    b.text(1171, 655, "Next: evaluation games", 17, TEXT, 700)
    b.text(1171, 682, "Review workload before launch", 14, MUTED)
    b.pill(1154, 725, 380, 55, "Continue  →", GOLD, "#47351d", 18)
    b.footer("Best for first-time users: one stage at a time, with persistent summary", "C  ·  GUIDED")
    b.save("03-guided-training-flow")


def drawio():
    """Editable section map for the three concepts, one page per concept."""
    mx = Element("mxfile", host="app.diagrams.net", type="device")
    pages = [
        ("01 Cockpit", [(20,20,180,470,"Mission / navigation"),(216,20,490,220,"Controller settings"),(216,258,490,232,"Evaluation / validation"),(722,20,248,470,"Persistent run summary")]),
        ("02 Workbench", [(20,20,300,180,"Study design"),(335,20,300,180,"Evidence quality"),(650,20,300,180,"Workload model"),(20,215,615,270,"Experiment review"),(650,215,300,270,"Launch controls")]),
        ("03 Guided", [(20,20,930,55,"Five-stage progress rail"),(20,90,650,395,"Current stage: learning"),(685,90,265,395,"Persistent live review")]),
    ]
    for page_id,(name,blocks) in enumerate(pages):
        diagram=SubElement(mx,"diagram",id=f"concept-{page_id+1}",name=name)
        model=SubElement(diagram,"mxGraphModel",dx="1100",dy="700",grid="1",gridSize="10",page="1",pageWidth="1000",pageHeight="540")
        root=SubElement(model,"root")
        SubElement(root,"mxCell",id="0")
        SubElement(root,"mxCell",id="1",parent="0")
        for i,(x,y,w,h,label) in enumerate(blocks,2):
            cell=SubElement(root,"mxCell",id=str(i),value=label,style="rounded=1;whiteSpace=wrap;html=1;fillColor=#18212B;strokeColor=#ECB14B;fontColor=#EFF3F7;fontSize=18;align=center;",vertex="1",parent="1")
            SubElement(cell,"mxGeometry",x=str(x),y=str(y),width=str(w),height=str(h),attrib={"as":"geometry"})
    ElementTree(mx).write(ROOT/"layout-map.drawio",encoding="utf-8",xml_declaration=True)


if __name__ == "__main__":
    cockpit()
    workbench()
    guided()
    drawio()

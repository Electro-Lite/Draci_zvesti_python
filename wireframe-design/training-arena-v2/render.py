"""Render the mission-specific Training Arena design studies.

Only files beneath training-arena-v2 are written. Requires rsvg-convert.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
import argparse
import subprocess


ROOT = Path(__file__).resolve().parent
W, H = 1600, 900
BG, PANEL, RAISED = "#0d1219", "#18212b", "#202c38"
LINE, TEXT, MUTED = "#45586a", "#eff3f7", "#a8b6c5"
GOLD, GREEN, BLUE, RED = "#ecb14b", "#5bc684", "#6da9df", "#e26467"
MANA = {"BLUE": "#70aee6", "RED": "#e98072", "BLACK": "#b7a1cf"}

STARTER = [("Lucisnik", 2, "BLUE"), ("Paladin", 2, "BLUE"), ("Panos", 2, "BLUE"),
           ("Pesak", 2, "BLUE"), ("Strazny", 2, "BLUE")]
COUNTER = [("Draci Fanatik", 4, "BLACK"), ("Pesak", 2, "BLUE"),
           ("Asketa", 1, "RED"), ("Dummy", 1, "BLACK"),
           ("Innosuv Fanatik", 1, "RED"), ("Lucisnik", 1, "BLUE"),
           ("Novic", 1, "RED"), ("Paladin", 1, "BLUE")]
KILLER = [("Novic", 4, "RED"), ("Zabijak", 4, "BLACK"), ("Asketa", 2, "RED")]


class Art:
    def __init__(self, title, subtitle, code):
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
                      f'<rect width="{W}" height="{H}" fill="{BG}"/>']
        self.box(0, 0, W, 6, GOLD, r=0)
        self.txt(42, 37, "DRACI ZVESTI  /  TRAINING ARENA", 15, GOLD, 700, spacing=2)
        self.txt(42, 83, title, 35, TEXT, 700)
        self.txt(43, 113, subtitle, 16, MUTED)
        self.pill(1364, 37, 194, 35, code, GOLD, "#382e1e", 13)
        self.pill(1385, 86, 173, 31, "EXAMPLE DATA", BLUE, RAISED, 12)

    def box(self, x, y, w, h, fill=PANEL, r=10, stroke=None, sw=1):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"' +
                          (f' stroke="{stroke}" stroke-width="{sw}"' if stroke else "") + '/>')

    def txt(self, x, y, s, size=16, color=TEXT, weight=400, anchor="start", spacing=0):
        self.parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-family="DejaVu Sans, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" letter-spacing="{spacing}">{escape(str(s))}</text>')

    def line(self, x1, y1, x2, y2, color=LINE, sw=1):
        self.parts.append(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="{sw}"/>')

    def pill(self, x, y, w, h, label, color=GOLD, fill=RAISED, size=15):
        self.box(x,y,w,h,fill,8,color)
        self.txt(x+w/2,y+h/2+size*.35,label,size,color,700,"middle")

    def panel(self, x,y,w,h,title,note="",accent=GOLD):
        self.box(x,y,w,h,PANEL,13,LINE)
        self.box(x,y,5,h,accent,2)
        self.txt(x+22,y+31,title,20,TEXT,700)
        if note:self.txt(x+22,y+55,note,13,MUTED)

    def card_row(self,x,y,w,name,count,mana,*,row_h=40,selected=False):
        self.box(x,y,w,row_h,"#283443" if selected else RAISED,7,GOLD if selected else LINE)
        self.box(x+10,y+7,26,row_h-14,MANA[mana],5)
        self.txt(x+23,y+row_h/2+5,name[:1],15,BG,700,"middle")
        self.txt(x+47,y+row_h/2+6,name,16,TEXT,600)
        self.pill(x+w-54,y+5,42,row_h-10,f"×{count}",MANA[mana],PANEL,13)

    def meter(self,x,y,w,ratio,color=GREEN,label=""):
        self.box(x,y,w,14,"#354353",7)
        self.box(x,y,max(3,round(w*ratio)),14,color,7)
        if label:self.txt(x+w,y-7,label,13,color,700,"end")

    def poly(self,points,color=GOLD,sw=3):
        p=" ".join(f"{x},{y}" for x,y in points)
        self.parts.append(f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>')
        for x,y in points:self.parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>')

    def footer(self,left,right):
        self.line(42,844,1558,844)
        self.txt(42,875,left,13,MUTED)
        self.txt(1558,875,right,13,GOLD,700,"end")

    def save(self, mission, stem):
        target=ROOT/mission
        target.mkdir(parents=True,exist_ok=True)
        self.parts.append("</svg>")
        svg=target/f"{stem}.svg"
        png=target/f"{stem}.png"
        svg.write_text("\n".join(self.parts)+"\n",encoding="utf-8")
        subprocess.run(["rsvg-convert","-w",str(W),"-h",str(H),"-o",str(png),str(svg)],check=True)


def counter_composition():
    a=Art("Counter hunt / compositions first","A concrete answer: which counter beat my deck, and what is in both decks?","COUNTER 01")
    a.panel(42,151,422,674,"Your selected deck · Starter Blue","10 cards · five distinct cards · saved deck",BLUE)
    for i,(name,count,mana) in enumerate(STARTER):a.card_row(62,228+i*56,382,name,count,mana)
    a.box(62,542,382,116,RAISED,9,LINE)
    a.txt(80,574,"What changed?",17,TEXT,700)
    a.txt(80,605,"Counter shares 4 card copies",15,MUTED)
    a.txt(80,633,"6 selected-deck cards are absent there",14,MUTED)
    a.line(62,718,444,718)
    a.txt(62,752,"Complete selected composition is shown above.",13,MUTED)
    a.panel(482,151,596,317,"Head-to-head result","Counter G1 #8 against your selected deck",GOLD)
    a.txt(508,252,"80%",57,GOLD,700)
    a.txt(677,233,"COUNTER WIN RATE",13,MUTED,700)
    a.txt(677,264,"Counter G1 #8 wins 800 of 1,000 games",16,TEXT,700)
    a.txt(508,319,"COUNTER 800",14,GREEN,700)
    a.txt(703,319,"DRAWS 100",14,MUTED,700)
    a.txt(847,319,"STARTER BLUE 100",14,RED,700)
    a.box(508,340,544,23,RED,6)
    a.box(508,340,489,23,MUTED,6)
    a.box(508,340,435,23,GREEN,6)
    a.box(508,340,544,23,"none",6,LINE)
    a.txt(725,357,"80%",13,BG,700,"middle")
    a.txt(970,357,"10%",12,BG,700,"middle")
    a.txt(1024,357,"10%",12,BG,700,"middle")
    a.txt(508,389,"Result is for this counter versus this deck, not the whole pool.",13,MUTED)
    a.line(508,396,1052,396)
    a.txt(508,414,"RUN DEPTH",12,GOLD,700)
    a.txt(608,414,"1 counter gen · 10 controller gens · 2 × 15 genomes",13,TEXT,600)
    a.txt(508,435,"20 candidates × 1,000 tests = 20,000 validation games",12,GREEN,700)
    a.txt(508,455,"~2,250 controller-learning · ~22,250 total scheduled games",12,MUTED,600)
    a.panel(482,486,596,339,"Counter candidates","Final generation · choose a candidate to inspect",GREEN)
    for i,(name,rate,games) in enumerate((("Counter G1 #8","80%","1,000"),("Counter G1 #1","80%","1,000"),("Counter G1 #14","70%","1,000"),("Counter G1 #17","70%","1,000"),("Counter G1 #15","65%","1,000"))):
        y=568+i*48
        a.box(505,y-24,550,45,"#303b46" if i==0 else RAISED,7,GOLD if i==0 else LINE)
        a.txt(521,y+5,name,16,TEXT,700 if i==0 else 500)
        a.txt(872,y+5,f"{rate} · {games} games",15,GOLD if i==0 else MUTED,700)
    a.panel(1096,151,462,674,"Selected counter · G1 #8","12 cards · eight distinct cards · generated deck",GOLD)
    for i,(name,count,mana) in enumerate(COUNTER):a.card_row(1116,225+i*53,422,name,count,mana,row_h=39)
    a.line(1116,688,1538,688)
    a.txt(1116,716,"Complete counter composition is shown above.",13,MUTED)
    a.pill(1116,744,422,51,"Adopt this counter as my deck  →",GOLD,"#47351d",15)
    a.footer("Deck compositions match saved records; 1,000-game outcomes are illustrative.","COUNTER / COMPOSITION FIRST")
    a.save("counter-decks","01-compositions-first")


def counter_investigation():
    a=Art("Counter hunt / investigation board","Select a counter, inspect its composition changes, then read its own evidence.","COUNTER 02")
    a.panel(42,151,332,674,"Candidate ladder","Final generation · 20 counters",BLUE)
    for i,(n,s) in enumerate((("G1 #8","80%"),("G1 #1","80%"),("G1 #14","70%"),("G1 #17","70%"),("G1 #15","65%"))):
        y=236+i*74;a.box(64,y-27,288,60,"#3d3526" if i==0 else RAISED,8,GOLD if i==0 else LINE)
        a.txt(80,y+1,n,19,TEXT,700);a.txt(331,y+1,s,21,GOLD,700,"end")
        a.txt(80,y+23,"20 validation games",12,MUTED)
    a.txt(65,710,"Sort: counter win rate  ↓",13,BLUE,700)
    a.pill(64,744,288,49,"Show all 20 counters",BLUE,RAISED,15)
    a.panel(392,151,766,674,"Composition comparison","Starter Blue → Counter G1 #8 · quantities are card copies",GOLD)
    a.txt(418,241,"YOUR DECK",13,BLUE,700)
    a.txt(746,241,"COUNTER",13,GOLD,700)
    a.txt(1093,241,"CHANGE",13,MUTED,700,"end")
    rows=(("Draci Fanatik",0,4,"BLACK"),("Pesak",2,2,"BLUE"),("Lucisnik",2,1,"BLUE"),
          ("Paladin",2,1,"BLUE"),("Panos",2,0,"BLUE"),("Strazny",2,0,"BLUE"),
          ("Asketa",0,1,"RED"),("Dummy",0,1,"BLACK"),("Innosuv Fanatik",0,1,"RED"),("Novic",0,1,"RED"))
    for i,(name,left,right,mana) in enumerate(rows):
        y=272+i*45;a.box(416,y,718,39,RAISED,6,LINE)
        a.box(426,y+8,20,23,MANA[mana],4)
        a.txt(455,y+26,name,15,TEXT,600)
        a.txt(609,y+26,f"×{left}",16,BLUE,700)
        a.txt(783,y+26,f"×{right}",16,GOLD,700)
        delta=right-left;a.txt(1097,y+26,f"{delta:+d}" if delta else "same",14,GREEN if delta>0 else RED if delta<0 else MUTED,700,"end")
    a.txt(418,769,"Both complete decks remain one click away.",14,MUTED)
    a.panel(1176,151,382,404,"Why this counter stands out","For the selected pair only",GREEN)
    a.txt(1199,250,"16 / 20",44,GREEN,700)
    a.txt(1199,281,"counter wins",17,TEXT,700)
    a.txt(1199,327,"2 draws · 2 selected-deck wins",14,MUTED)
    a.line(1199,351,1535,351)
    a.txt(1199,389,"4 shared card copies",16,TEXT)
    a.txt(1199,427,"12 cards versus 10 cards",16,TEXT)
    a.txt(1199,478,"Small sample; compare other counters",13,MUTED)
    a.panel(1176,573,382,252,"Deck inspector","Full card lists and images",BLUE)
    a.txt(1199,651,"Your deck  ·  10 cards",16,TEXT,600)
    a.txt(1199,683,"Counter G1 #8  ·  12 cards",16,TEXT,600)
    a.pill(1199,728,336,50,"Open both full decks  →",BLUE,RAISED,15)
    a.footer("Pick another counter to update composition and that candidate's own W/D/L.","COUNTER / INVESTIGATION")
    a.save("counter-decks","02-investigation-board")


def counter_inspector():
    a=Art("Inspect both decks","Counter training · full card composition for the currently selected pair","COUNTER DETAIL")
    a.panel(42,151,718,674,"Your deck · Starter Blue","Saved player deck · 10 total cards · five unique",BLUE)
    a.panel(778,151,780,674,"Counter G1 #8","Generated counter · 12 total cards · eight unique",GOLD)
    for i,(n,c,m) in enumerate(STARTER):a.card_row(65,235+i*75,670,n,c,m,row_h=55)
    for i,(n,c,m) in enumerate(COUNTER):a.card_row(802,223+i*67,732,n,c,m,row_h=49)
    a.pill(65,728,670,54,"←  Back to counter results",BLUE,RAISED,16)
    a.footer("Example lists are actual card copies from a saved deck and counter-run summary.","INSPECTOR / COUNTER")
    a.save("counter-decks","03-deck-inspector")


def duel_scoreboard():
    a=Art("Deck duel / two-sided scoreboard","Every rate names its deck; both complete compositions sit beside the result.","DUEL 01")
    a.panel(42,151,422,674,"Deck A · Starter Blue","10 cards · selected first",BLUE)
    for i,(n,c,m) in enumerate(STARTER):a.card_row(62,231+i*68,382,n,c,m,row_h=53)
    a.pill(62,744,382,50,"Inspect Deck A  →",BLUE,RAISED,16)
    a.panel(482,151,596,674,"Final seat-balanced checkpoint","Deck A: Starter Blue  /  Deck B: Killer Queen",GOLD)
    a.txt(510,248,"100 games",29,TEXT,700)
    a.txt(510,289,"Deck A win rate",16,BLUE,700)
    a.txt(922,289,"53%",34,BLUE,700,"end")
    a.meter(510,304,542,.53,BLUE)
    a.txt(510,356,"Draw rate",16,MUTED,700)
    a.txt(922,356,"14%",34,MUTED,700,"end")
    a.meter(510,371,542,.14,MUTED)
    a.txt(510,423,"Deck B win rate",16,RED,700)
    a.txt(922,423,"33%",34,RED,700,"end")
    a.meter(510,438,542,.33,RED)
    a.box(510,506,542,101,RAISED,8,LINE)
    a.txt(529,546,"DECK A WINS",13,BLUE,700);a.txt(529,578,"53",27,TEXT,700)
    a.txt(702,546,"DRAWS",13,MUTED,700);a.txt(702,578,"14",27,TEXT,700)
    a.txt(845,546,"DECK B WINS",13,RED,700);a.txt(845,578,"33",27,TEXT,700)
    a.txt(510,657,"53% is Deck A wins / all 100 games.",15,MUTED)
    a.txt(510,686,"Draws are separate; Deck B win rate is 33%.",15,MUTED)
    a.pill(510,744,542,50,"See learning checkpoints  →",GOLD,"#47351d",16)
    a.panel(1096,151,462,674,"Deck B · Killer Queen","10 cards · selected second",RED)
    for i,(n,c,m) in enumerate(KILLER):a.card_row(1116,231+i*86,422,n,c,m,row_h=62)
    a.box(1116,537,422,137,RAISED,9,LINE)
    a.txt(1135,574,"Reading the result",18,TEXT,700)
    a.txt(1135,607,"Blue always means Deck A.",15,BLUE)
    a.txt(1135,638,"Red always means Deck B.",15,RED)
    a.pill(1116,744,422,50,"Inspect Deck B  →",RED,RAISED,16)
    a.footer("Deck lists match saved decks; outcomes are illustrative examples.","DUEL / SCOREBOARD")
    a.save("matchup-evaluation","01-two-sided-scoreboard")


def duel_checkpoints():
    a=Art("Deck duel / checkpoint study","Follow the same two decks as their controllers mature; never hide the perspective.","DUEL 02")
    a.panel(42,151,354,674,"The two fixed decks","One pairing across every checkpoint",BLUE)
    a.box(64,230,310,157,RAISED,8,BLUE)
    a.txt(82,265,"DECK A",13,BLUE,700);a.txt(82,297,"Starter Blue",22,TEXT,700)
    a.txt(82,330,"Lucisnik ×2 · Paladin ×2",14,MUTED)
    a.txt(82,355,"Panos ×2 · Pesak ×2 · Strazny ×2",13,MUTED)
    a.box(64,405,310,151,RAISED,8,RED)
    a.txt(82,440,"DECK B",13,RED,700);a.txt(82,472,"Killer Queen",22,TEXT,700)
    a.txt(82,505,"Novic ×4 · Zabijak ×4",14,MUTED)
    a.txt(82,530,"Asketa ×2",14,MUTED)
    a.line(64,593,374,593)
    a.txt(64,626,"Deck IDs stay fixed while",15,MUTED)
    a.txt(64,653,"controllers change by generation.",15,MUTED)
    a.panel(414,151,770,674,"Seat-balanced checkpoint outcomes","1,000 new games per row · Deck A wins / draws / Deck B wins",GOLD)
    a.txt(440,248,"CHECKPOINT",13,MUTED,700)
    a.txt(1018,248,"DECK A  /  DRAW  /  DECK B",13,MUTED,700,"end")
    for i,(gen,wa,draw,wb) in enumerate(((1,38,12,50),(10,45,13,42),(25,49,14,37),(40,53,14,33))):
        y=280+i*112;a.box(438,y,720,95,RAISED,8,GOLD if gen==40 else LINE)
        a.txt(455,y+29,f"Gen {gen}",18,TEXT,700)
        a.txt(762,y+29,f"A {wa}%",16,BLUE,700)
        a.txt(870,y+29,f"Draw {draw}%",15,MUTED,700)
        a.txt(1014,y+29,f"B {wb}%",16,RED,700)
        a.box(455,y+51,678,20,PANEL,5)
        a.box(455,y+51,round(678*wa/100),20,BLUE,5)
        a.box(455+round(678*wa/100),y+51,round(678*draw/100),20,MUTED,0)
        a.box(455+round(678*(wa+draw)/100),y+51,round(678*wb/100),20,RED,5)
    a.box(438,727,720,80,"#293540",8,LINE)
    for x in (616,793,973):a.line(x,740,x,795,LINE)
    for x,value,label in ((455,"2 × 15","GENOMES EACH GEN"),(634,"40","LEARNING GENERATIONS"),(811,"15","GAMES / GENOME / GEN"),(990,"4 × 1,000","CHECKPOINT TRIALS")):
        a.txt(x,762,value,22,TEXT,700)
        a.txt(x,788,label,10,MUTED,700)
    a.panel(1202,151,356,674,"Final reading","Generation 40 · example",GREEN)
    a.txt(1226,251,"Deck A · 53%",25,BLUE,700)
    a.txt(1226,290,"Deck B · 33%",25,RED,700)
    a.txt(1226,329,"Draws · 14%",22,MUTED,700)
    a.line(1226,353,1534,353)
    a.txt(1226,397,"1,000 new games per checkpoint",15,TEXT)
    a.txt(1226,432,"Both seating orders balanced",15,TEXT)
    a.txt(1226,458,"Final: A 530 · D 140 · B 330",13,MUTED)
    a.txt(1226,487,"Do the controllers change",15,GOLD,700)
    a.txt(1226,516,"the matchup over time?",15,GOLD,700)
    a.txt(1226,563,"A rises 38% → 53%",17,BLUE,700)
    a.txt(1226,616,"4 checks × 1,000 = 4,000 games",14,MUTED)
    a.txt(1226,644,"Separate from learning games.",14,MUTED)
    a.box(1226,665,308,55,RAISED,8,LINE)
    a.txt(1241,689,"~13,000 games scheduled",17,GOLD,700)
    a.txt(1241,709,"9,000 learning + 4,000 evaluation",11,MUTED)
    a.pill(1226,735,308,50,"Open methodology  →",GOLD,RAISED,15)
    a.footer("The scoreboard and checkpoints use Deck A / Deck B labels everywhere.","DUEL / CHECKPOINT STUDY")
    a.save("matchup-evaluation","02-checkpoint-study")


def duel_inspector():
    a=Art("Inspect duel decks","The two fixed compositions remain accessible from scoreboard and checkpoint views.","DUEL DETAIL")
    a.panel(42,151,737,674,"Deck A · Starter Blue","Saved deck · 10 total cards · blue perspective",BLUE)
    a.panel(797,151,761,674,"Deck B · Killer Queen","Saved deck · 10 total cards · red perspective",RED)
    for i,(n,c,m) in enumerate(STARTER):a.card_row(66,233+i*82,688,n,c,m,row_h=61)
    for i,(n,c,m) in enumerate(KILLER):a.card_row(821,233+i*105,712,n,c,m,row_h=74)
    a.box(821,592,712,113,RAISED,9,LINE)
    a.txt(841,628,"Composition note",17,TEXT,700)
    a.txt(841,660,"These lists are identities, not causes of the observed win rate.",14,MUTED)
    a.pill(66,748,688,50,"←  Back to duel evaluation",BLUE,RAISED,16)
    a.footer("Card names and copy counts match the two saved example decks.","INSPECTOR / DUEL")
    a.save("matchup-evaluation","03-deck-inspector")


def builder_research():
    a=Art("Deck evolution / research dashboard","A readable story first, with population, diversity, matchups, and card signals below.","EVOLUTION 01")
    a.box(42,151,1516,57,PANEL,9,LINE)
    a.txt(64,187,"Meta-evolution  ·  DB 84  ·  complete  ·  one run scope",18,TEXT,700)
    a.pill(1133,162,122,35,"Story",GOLD,"#47351d",14)
    a.pill(1267,162,122,35,"Evidence",MUTED,RAISED,14)
    a.pill(1401,162,133,35,"Methods",MUTED,RAISED,14)
    a.panel(42,227,1080,131,"Finding in one sentence",accent=GOLD)
    a.txt(66,301,"A strong deck emerged, but the population became concentrated.",23,TEXT,700)
    a.txt(66,332,"Inspect the spread and diversity before claiming the whole meta improved.",14,MUTED)
    a.panel(1140,227,418,131,"Scope & integrity","10 outer generations · illustrative",BLUE)
    a.txt(1163,306,"20 decks / generation",17,TEXT,700)
    a.txt(1163,334,"Held-out matchup rows: 1,200",13,MUTED)
    a.panel(42,376,714,265,"Population fitness","Best, median and worst must be separate",BLUE)
    for y in (476,517,558):a.line(71,y,721,y,"#314151")
    a.poly(((73,560),(180,530),(287,508),(394,493),(501,467),(608,459),(717,449)),GOLD,3)
    a.poly(((73,584),(180,569),(287,551),(394,548),(501,538),(608,530),(717,525)),BLUE,3)
    a.poly(((73,607),(180,601),(287,593),(394,592),(501,585),(608,579),(717,574)),RED,3)
    a.txt(74,619,"Outer gen 1",12,MUTED);a.txt(719,619,"Gen 10",12,MUTED,anchor="end")
    a.txt(505,433,"Best",13,GOLD,700);a.txt(582,433,"Median",13,BLUE,700);a.txt(681,433,"Worst",13,RED,700)
    a.panel(774,376,368,265,"Diversity","Similarity-aware view",GREEN)
    a.txt(798,465,"5.2",47,GREEN,700)
    a.txt(798,493,"effective archetypes",14,MUTED)
    a.meter(798,531,320,.38,GREEN,"38% viable share")
    a.txt(798,589,"Exact signatures can exaggerate",13,MUTED)
    a.txt(798,612,"diversity when decks differ by one card.",13,MUTED)
    a.panel(1160,376,398,265,"Matchup structure","Who beats whom locally?",GOLD)
    names=("Blue","Red","Green","Black")
    for i,n in enumerate(names):a.txt(1248+i*73,454,n,11,MUTED,700,"middle")
    matrix=((0,1,-1,1),(-1,0,1,-1),(1,-1,0,1),(-1,1,-1,0))
    for i,n in enumerate(names):
        a.txt(1184,485+i*34,n,11,MUTED,700)
        for j,v in enumerate(matrix[i]):
            a.box(1226+j*73,466+i*34,61,27,"#2f664d" if v>0 else "#663b40" if v<0 else RAISED,4)
            a.txt(1257+j*73,485+i*34,"+" if v>0 else "−" if v<0 else "·",14,TEXT,700,"middle")
    a.panel(42,659,894,166,"Card-balance signals","Generation-local presence lift · association only",GOLD)
    a.txt(65,753,"Draci Fanatik",18,TEXT,700);a.txt(403,753,"high inclusion",15,MUTED)
    a.txt(655,753,"+8.4 lift",20,GOLD,700)
    a.txt(65,791,"Compare against same-generation baseline and show sample counts.",14,MUTED)
    a.panel(954,659,604,166,"Read deeper","From beginner explanation to full method",BLUE)
    a.pill(977,741,263,53,"Explain these metrics",BLUE,RAISED,15)
    a.pill(1254,741,280,53,"Open research evidence",GOLD,RAISED,15)
    a.footer("The figures are illustrative; deeper statistics need notebook-style run-scoped aggregation.","EVOLUTION / RESEARCH DASHBOARD")
    a.save("deck-evolution","01-research-dashboard")


def builder_workbench():
    a=Art("Deck evolution / investigation workbench","Question-led analysis for a researcher without losing the beginner explanation.","EVOLUTION 02")
    a.panel(42,151,347,674,"Choose a question","One run scope · DB 84",BLUE)
    questions=("Did decks improve?","Did diversity collapse?","Which cards shifted?","Are matchups polarized?","Did controllers learn?")
    for i,q in enumerate(questions):
        y=237+i*76;a.box(64,y-25,303,59,"#44361f" if i==2 else RAISED,8,GOLD if i==2 else LINE)
        a.txt(82,y+8,q,16,TEXT,700 if i==2 else 500)
    a.box(64,654,303,126,RAISED,9,LINE)
    a.txt(82,689,"Scope",15,GOLD,700)
    a.txt(82,718,"This run · final generation",14,TEXT)
    a.txt(82,749,"Show all seeds / groups  ▾",13,BLUE)
    a.panel(407,151,772,444,"Which cards shifted?","Pick rate versus presence lift by generation group",GOLD)
    for y in (290,370,450,530):a.line(482,y,1142,y,"#314151")
    for x in (482,647,812,977,1142):a.line(x,290,x,530,"#314151")
    a.txt(485,273,"PRESENCE LIFT (fitness points)",12,MUTED,700)
    a.txt(812,567,"PICK RATE  →",13,MUTED,700,"middle")
    dots=((0.91,0.76,"Draci Fanatik",GOLD),(0.54,0.57,"Paladin",BLUE),(0.37,0.34,"Zabijak",RED),(0.23,0.48,"Innosuv Fanatik",GREEN))
    for px,py,name,col in dots:
        x=round(482+660*px);y=round(530-240*py)
        a.parts.append(f'<circle cx="{x}" cy="{y}" r="11" fill="{col}" stroke="{PANEL}" stroke-width="3"/>')
        a.txt(x+15,y-8,name,13,TEXT,700)
    a.panel(1197,151,361,444,"Selected card","Draci Fanatik · example",GREEN)
    a.txt(1221,250,"90%",39,GOLD,700)
    a.txt(1221,277,"final-gen pick rate",14,MUTED)
    a.txt(1221,331,"+8.4",31,GREEN,700)
    a.txt(1221,358,"presence lift vs local baseline",13,MUTED)
    a.line(1221,387,1533,387)
    a.txt(1221,425,"Observed",14,GREEN,700)
    a.txt(1221,452,"Often in higher-scoring decks.",14,TEXT)
    a.txt(1221,494,"Limit",14,GOLD,700)
    a.txt(1221,521,"Not played-card win rate.",14,MUTED)
    a.txt(1221,550,"Near-universal pick needs care.",13,MUTED)
    a.panel(407,613,1151,212,"Evidence ledger","Make the reasoning auditable",BLUE)
    heads=(("DEFINITION","Mean score with card − local baseline"),("SAMPLE","Show decks with card / total decks"),("COMPARISON","Same outer-generation group"),("SOURCE","Genome + deck composition rows"))
    for i,(h,v) in enumerate(heads):
        x=431+i*279;a.box(x,683,263,109,RAISED,7,LINE)
        a.txt(x+15,716,h,12,BLUE,700)
        # Split by intent to keep every value inside its cell.
        parts={0:("Mean with card", "− local baseline"),1:("Decks with card", "/ total decks"),2:("Same outer-gen", "group"),3:("Genome + deck", "composition rows")}[i]
        a.txt(x+15,746,parts[0],14,TEXT)
        a.txt(x+15,769,parts[1],14,TEXT)
    a.footer("This mode exposes method and sample counts before any academic claim.","EVOLUTION / INVESTIGATION")
    a.save("deck-evolution","02-investigation-workbench")


def builder_evidence():
    a=Art("Deck evolution / research evidence","Run-scoped definitions, denominators, comparisons, and limitations for academic review.","EVOLUTION METHODS")
    a.box(42,151,1516,58,PANEL,9,LINE)
    a.txt(64,188,"Scope: DB 84  ·  seed 104729  ·  final outer-generation group",17,TEXT,700)
    a.pill(1263,162,271,36,"Change scope  ▾",BLUE,RAISED,14)
    a.panel(42,228,355,296,"Population shift","Best is not the median",BLUE)
    a.txt(66,317,"Best +22",27,GOLD,700)
    a.txt(66,358,"Median +7",25,BLUE,700)
    a.txt(66,399,"Worst −13",23,RED,700)
    a.line(66,424,373,424)
    a.txt(66,456,"n = 20 final-gen decks",14,MUTED)
    a.txt(66,488,"Spread is evidence of uneven quality.",13,MUTED)
    a.panel(414,228,355,296,"Composition-aware diversity","Not exact signatures alone",GREEN)
    a.txt(438,319,"5.2",43,GREEN,700)
    a.txt(438,349,"effective archetypes",15,TEXT)
    a.txt(438,395,"38% viable share",20,GOLD,700)
    a.txt(438,441,"Similarity kernel discounts decks",14,MUTED)
    a.txt(438,468,"differing by one card replacement.",14,MUTED)
    a.panel(786,228,355,296,"Meta-weighted performance","Against common local opponents",GOLD)
    a.txt(810,310,"Raw average",15,MUTED)
    a.txt(1109,310,"+17",21,TEXT,700,"end")
    a.meter(810,326,299,.74,GOLD)
    a.txt(810,381,"Meta-weighted",15,MUTED)
    a.txt(1109,381,"+11",21,TEXT,700,"end")
    a.meter(810,397,299,.52,BLUE)
    a.txt(810,458,"Common opponents reduce this",14,MUTED)
    a.txt(810,482,"candidate's apparent advantage.",14,MUTED)
    a.panel(1158,228,400,296,"Matchup polarization","Balance is more than one champion",RED)
    a.txt(1182,320,"31%",39,RED,700)
    a.txt(1182,353,"close-matchup share",15,TEXT)
    a.txt(1182,399,"Mean |score|  9.6",19,MUTED,700)
    a.txt(1182,450,"Lower absolute score means",14,MUTED)
    a.txt(1182,477,"more even matchups.",14,MUTED)
    a.panel(42,544,1516,281,"Evidence ledger","For every claim: measurement, denominator, scope, and interpretation limit",BLUE)
    headers=((65,"QUESTION"),(407,"MEASURE"),(755,"SAMPLE / SCOPE"),(1158,"LIMIT"))
    for x,label in headers:a.txt(x,631,label,12,BLUE,700)
    rows=(
        ("Did deck quality rise?","Best / median / worst fitness","20 decks × 10 outer generations","Fitness alone is not user win rate"),
        ("Did the meta narrow?","Effective archetypes; viable share","Final generation, one seed","Archetype grouping choice matters"),
        ("Is a card overused?","Presence lift; pick rate","18 / 20 final decks with card","Presence does not imply card play"),
        ("Are pairings balanced?","Mean |score|; close-matchup rate","Held-out local pairings","Intervals are descriptive here"),
    )
    for i,row in enumerate(rows):
        y=652+i*38;a.box(63,y-21,1472,33,RAISED,5,LINE)
        for (x,_),value in zip(headers,row):a.txt(x,y,value,13,TEXT if x==65 else MUTED,600 if x==65 else 400)
    a.footer("Example numbers are illustrative; metric definitions follow analysis notebooks.","EVOLUTION / RESEARCH EVIDENCE")
    a.save("deck-evolution","03-research-evidence")


def builder_explainer():
    a=Art("Metric explainer / presence lift","A layered explanation: plain English, formula, sample, and research caveat.","EVOLUTION DETAIL")
    a.panel(166,151,1268,674,"Card presence lift","Deck evolution · one run · one outer-generation group",GOLD)
    a.pill(192,227,161,40,"Beginner",GOLD,"#47351d",15)
    a.pill(366,227,161,40,"Research",MUTED,RAISED,15)
    a.box(192,295,570,198,RAISED,9,LINE)
    a.txt(217,334,"In plain language",20,TEXT,700)
    a.txt(217,370,"Do decks containing this card score better",17,TEXT)
    a.txt(217,400,"than the typical deck from the same period?",17,TEXT)
    a.txt(217,448,"It compares deck lists, not cards played in games.",14,GOLD)
    a.box(781,295,626,198,RAISED,9,LINE)
    a.txt(806,334,"Research definition",20,TEXT,700)
    a.txt(806,380,"presence lift = mean(score | card present)",18,BLUE,700)
    a.txt(959,414,"− mean(score | same-gen decks)",18,BLUE,700)
    a.txt(806,459,"Report pick rate, sample sizes, run ID, and interval.",14,MUTED)
    a.box(192,515,590,261,RAISED,9,LINE)
    a.txt(217,553,"Example evidence panel",20,TEXT,700)
    a.txt(217,595,"Card: Draci Fanatik",18,TEXT,700)
    a.txt(217,628,"Pick rate: 90%  ·  Lift: +8.4 fitness points",16,GREEN)
    a.txt(217,660,"With card: 18 decks  ·  Total: 20 decks",15,MUTED)
    a.txt(217,699,"Scope: this run, final outer generation",15,MUTED)
    a.box(801,515,606,261,RAISED,9,LINE)
    a.txt(826,553,"What you can conclude",20,TEXT,700)
    a.txt(826,594,"Association with stronger deck lists in this scope.",15,GREEN)
    a.txt(826,637,"What you cannot conclude",18,GOLD,700)
    a.txt(826,672,"The card caused wins or was drawn / played well.",15,MUTED)
    a.txt(826,707,"Near-universal inclusion leaves a small absence group.",14,MUTED)
    a.pill(192,780,320,39,"←  Back to investigation",BLUE,RAISED,14)
    a.footer("Example values are invented; the formulas and interpretation follow the analysis guide.","EXPLAINER / PRESENCE LIFT")
    a.save("deck-evolution","04-metric-explainer")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("boards",nargs="*",choices=("counter-01","duel-02"),
                        help="Render only selected boards; omit to render all boards")
    selected=set(parser.parse_args().boards)
    if not selected:
        counter_composition();counter_investigation();counter_inspector()
        duel_scoreboard();duel_checkpoints();duel_inspector()
        builder_research();builder_workbench();builder_evidence();builder_explainer()
    else:
        if "counter-01" in selected:counter_composition()
        if "duel-02" in selected:duel_checkpoints()

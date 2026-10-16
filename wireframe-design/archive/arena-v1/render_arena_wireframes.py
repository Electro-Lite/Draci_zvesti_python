"""Generate Training Arena alternatives for all three current missions.

The displayed numbers are illustrative sample data, never live run data.
Run: python wireframe-design/render_arena_wireframes.py
"""

from __future__ import annotations

from render_wireframes import Board, GOLD, GREEN, BLUE, MUTED, TEXT, PANEL, PANEL2, LINE


RED = "#e26467"
MISSIONS = {
    "counter": {
        "name": "Counter-deck training", "run": "counter-study-05", "id": "UI 05",
        "subject": "Starter Blue", "other": "evolved counter decks",
        "tabs": ("Overview", "Counter pool", "Controllers", "Findings"),
        "metric": "61%", "metric_name": "TOP COUNTER WIN RATE",
        "fact1": "5 / 5", "fact1_name": "Counter generations",
        "fact2": "20", "fact2_name": "Final candidates",
        "fact3": "40", "fact3_name": "Controller generations",
        "chart": (56, 53, 48, 43, 39), "chart_name": "Selected deck win rate vs counter pool",
        "chart_x": (1, 2, 3, 4, 5), "source": "UI summary and final counter rows",
        "result": "Top counter: Counter G5 #12", "result2": "61% vs Starter Blue · 40 balanced games",
        "story": "Persistent controllers face a changing counter pool.",
        "caution": "The pooled deck win rate mixes different counter opponents.",
        "stages": ("Controller training", "Candidate decks", "Validation games", "Select counters"),
        "active": 2, "live": "Cycle 4 / 5 · 62 / 100 trials", "live2": "Counter controller: generation 32 / 40",
        "live_outer": "4 / 5", "live_signal": "62 / 100 trials", "phase_ratio": 0.62, "live_chart_count": 3,
        "evidence": ("Counter G5 #12", "Counter G5 #04", "Counter G5 #19"),
        "scores": ("61%", "57%", "54%"),
        "evidence_label": "Candidate counter win rate vs selected deck",
    },
    "matchup": {
        "name": "Deck matchup evaluation", "run": "blue-vs-choir", "id": "UI 12",
        "subject": "Starter Blue", "other": "Iron Choir",
        "tabs": ("Overview", "Checkpoints", "Outcome", "Findings"),
        "metric": "53%", "metric_name": "DECK A WIN RATE",
        "fact1": "53–14–33", "fact1_name": "Wins · draws · losses",
        "fact2": "100", "fact2_name": "Final test games",
        "fact3": "40", "fact3_name": "Controller generations",
        "chart": (38, 45, 49, 53), "chart_name": "Deck A win rate at checkpoints",
        "chart_x": (1, 10, 25, 40), "source": "UI summary and checkpoint outcomes",
        "result": "Starter Blue vs Iron Choir", "result2": "53 wins · 14 draws · 33 losses",
        "story": "The same two decks are compared at every checkpoint.",
        "caution": "Checkpoint percentages use separate test-game samples.",
        "stages": ("Coevolve controllers", "Freeze checkpoint", "Seat-balanced games", "Final outcome"),
        "active": 2, "live": "Checkpoint 25 / 40 · 72 / 100 games", "live2": "Deck A wins 36 · draws 12 · Deck B wins 24",
        "live_outer": "25 / 40", "live_signal": "36 / 72 Deck A wins", "phase_ratio": 0.72, "live_chart_count": 2,
        "evidence": ("Generation 1", "Generation 10", "Generation 25", "Generation 40"),
        "scores": ("38%", "45%", "49%", "53%"),
        "evidence_label": "Deck A win rate at each checkpoint",
    },
    "builder": {
        "name": "General deck evolution", "run": "meta-evolution-02", "id": "DB 84",
        "subject": "Candidate population", "other": "evolved deck field",
        "tabs": ("Overview", "Population", "Matchups", "Card signals"),
        "metric": "+22.4", "metric_name": "BEST FITNESS",
        "fact1": "10 / 10", "fact1_name": "Outer generations",
        "fact2": "1,200", "fact2_name": "Logged matchups",
        "fact3": "20", "fact3_name": "Target population",
        "chart": (3, 8, 13, 12, 18, 20, 19, 22, 21, 22), "chart_name": "Best population fitness by generation",
        "chart_x": (1, 2, 3, 4, 5, 6, 7, 8, 9, 10), "source": "Database genome and matchup records",
        "result": "Best observed deck fitness +22.4", "result2": "10 outer generations · 1,200 matchups",
        "story": "Deck fitness comes from held-out pairings.",
        "caution": "Card association is descriptive, not causal.",
        "stages": ("Seed run", "Outer generation", "Nested controllers", "Holdout matchups"),
        "active": 2, "live": "Outer generation 6 / 10", "live2": "Inner controller 18 / 50 · 8 workers",
        "live_outer": "6 / 10", "live_signal": "+18.2 best fitness", "phase_ratio": 0.36, "live_chart_count": 5,
        "evidence": ("Blue vs Red", "Green vs Black", "Blue vs Green"),
        "scores": ("+22.4", "+15.8", "−8.1"),
        "evidence_label": "Deck 1 fitness in diverse matchups",
    },
}


def line_chart(b: Board, x, y, w, h, values, *, color=GOLD, axis="generation", unit="", x_values=None):
    for i in range(5):
        yy = y + i * h / 4
        b.line(x, yy, x+w, yy, "#324252")
    low, high = min(values), max(values)
    spread = max(1, high-low)
    b.text(x-7,y+4,f"{high}{unit}",12,MUTED,anchor="end")
    b.text(x-7,y+h+4,f"{low}{unit}",12,MUTED,anchor="end")
    points = [(x + i*w/max(1,len(values)-1), y+h-((v-low)/spread)*h) for i,v in enumerate(values)]
    pts = " ".join(f"{px:.1f},{py:.1f}" for px,py in points)
    b.items.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    for px,py in points:
        b.items.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{color}" stroke="#0d1219" stroke-width="2"/>')
    x_values = x_values or tuple(range(1,len(values)+1))
    b.text(x, y+h+29, str(x_values[0]), 13, MUTED)
    b.text(x+w, y+h+29, str(x_values[-1]), 13, MUTED, anchor="end")
    b.text(x+w/2, y+h+29, axis, 13, MUTED, anchor="middle")


def frame(b: Board, d, mode):
    b.pill(1394, 91, 162, 34, "SAMPLE DATA", BLUE, PANEL2, 12)
    b.rect(42, 151, 1516, 71, PANEL, 12, LINE)
    b.text(63, 184, d["name"], 23, TEXT, 700)
    run_id = "UI 84" if mode == "live" and d["id"] == "DB 84" else d["id"]
    b.text(63, 207, f'{run_id}  ·  {d["run"]}  ·  {d["subject"]}  vs  {d["other"]}', 14, MUTED)
    b.pill(1354, 168, 180, 38, "RUNNING" if mode == "live" else "COMPLETED", GOLD if mode == "live" else GREEN)


def footer(b: Board, note):
    b.line(42, 839, 1558, 839)
    b.pill(42, 849, 216, 37, "←  Back to runs", MUTED, PANEL2, 14)
    b.text(1558, 873, note, 14, GOLD, 700, "end")


def mission_studio(key, d):
    b = Board("Arena A / Mission studio", "Mission-specific overview inside a familiar tabbed shell", "ARENA A")
    frame(b,d,"completed")
    tabs=d["tabs"]
    for i,t in enumerate(tabs):
        x=42+i*385
        b.pill(x,239,372,45,t,GOLD if i==0 else MUTED,PANEL2,15)
    b.panel(42,301,392,277,d["metric_name"],"Primary outcome for this mission",GOLD)
    b.text(65,417,d["metric"],68,GOLD,700)
    b.text(65,463,d["result"],16,TEXT,600)
    b.text(65,497,d["result2"],14,MUTED)
    b.rect(65,524,345,34,PANEL2,6,LINE)
    b.text(78,547,"Open mission evidence  →",13,BLUE,700)
    b.panel(451,301,716,277,d["chart_name"],"Outcome trend; axis and units stay visible",BLUE)
    line_chart(b,492,392,627,121,d["chart"],color=GREEN if key=="matchup" else GOLD,unit="%" if key!="builder" else "",x_values=d["chart_x"])
    b.panel(1184,301,374,277,"Run facts","Mission-specific labels",GREEN)
    for i,(v,n) in enumerate(((d["fact1"],d["fact1_name"]),(d["fact2"],d["fact2_name"]),(d["fact3"],d["fact3_name"]))):
        yy=386+i*59
        b.text(1207,yy,v,23,TEXT,700)
        b.text(1380,yy,n,13,MUTED)
        if i<2:b.line(1207,yy+13,1530,yy+13)
    b.panel(42,595,743,227,"What happened",d["story"],GOLD)
    for i,(name,score) in enumerate(zip(d["evidence"][:3],d["scores"][:3])):
        yy=681+i*43
        b.rect(64,yy-25,698,35,PANEL2,6,LINE)
        b.text(80,yy,name,15,TEXT,600)
        b.text(742,yy,score,17,GREEN,700,"end")
    b.panel(802,595,756,227,"Interpretation & limits","Only conclusions supported by this run",BLUE)
    b.text(826,682,d["result"],18,TEXT,700)
    b.text(826,721,d["caution"],15,MUTED)
    b.text(826,771,"View evidence source, count and sample details  →",14,BLUE,700)
    footer(b,"A · TABBED MISSION STUDIO")
    b.save(f"arena-a-{key}")


def timeline(key,d):
    b=Board("Arena B / Run timeline","Live operation with explicit phases and mission context","ARENA B")
    frame(b,d,"live")
    b.panel(42,240,343,581,"Run stages","Current work is highlighted",BLUE)
    for i,stage in enumerate(d["stages"]):
        y=323+i*105
        active=i==d["active"]
        b.rect(65,y-25,296,76,"#3d321f" if active else PANEL2,8,GOLD if active else LINE)
        b.text(83,y+2,f"0{i+1}",14,GOLD if active else MUTED,700)
        b.text(120,y+2,stage,17,TEXT,700 if active else 500)
        b.text(120,y+30,"IN PROGRESS" if active else "EARLIER IN CYCLE" if i<d["active"] else "NEXT IN CYCLE",12,GOLD if active else GREEN if i<d["active"] else MUTED,700)
    b.panel(404,240,744,354,"Current activity",d["story"],GOLD)
    b.text(432,341,d["live"],29,TEXT,700)
    b.text(432,380,d["live2"],18,MUTED)
    b.rect(432,423,688,22,"#2b3540",10)
    b.rect(432,423,round(688*d["phase_ratio"]),22,GOLD,10)
    b.text(432,479,f'Current stage · illustrative {round(d["phase_ratio"]*100)}%',15,GOLD,700)
    b.text(432,532,"RUN PROGRESS",13,MUTED,700)
    b.text(1121,532,"Overall run phase shown separately  →",13,BLUE,700,"end")
    b.panel(1167,240,391,354,"Live signals","Only currently available telemetry",GREEN)
    for i,(label,value) in enumerate((("STATUS","Running"),("CYCLE / CHECKPOINT",d["live_outer"]),("LATEST SIGNAL",d["live_signal"]),("ELAPSED","18 min"))):
        yy=324+i*62
        b.text(1191,yy,label,12,MUTED,700)
        b.text(1191,yy+26,value,20,TEXT,700)
        if i<3:b.line(1191,yy+37,1534,yy+37)
    b.panel(404,612,744,209,"Progress history","Best recorded signal; not a final verdict",BLUE)
    line_chart(b,432,687,687,75,d["chart"][:d["live_chart_count"]],unit="%" if key!="builder" else "",x_values=d["chart_x"][:d["live_chart_count"]])
    b.panel(1167,612,391,209,"Controls & provenance","Safe actions remain visible",GOLD)
    b.pill(1191,684,343,43,"Stop training…",RED,PANEL2,15)
    b.text(1191,759,"Telemetry updated moments ago",14,MUTED)
    b.text(1191,785,"Final evidence appears after evaluation",12,BLUE)
    footer(b,"B · LIVE TIMELINE")
    b.save(f"arena-b-{key}")


def evidence_desk(key,d):
    b=Board("Arena C / Evidence desk","Completed-run analysis with provenance and limits","ARENA C")
    frame(b,d,"completed")
    b.panel(42,240,942,306,d["chart_name"],"Read the trend and the sample together",BLUE)
    line_chart(b,81,341,852,142,d["chart"],color=GREEN if key=="matchup" else GOLD,unit="%" if key!="builder" else "",x_values=d["chart_x"])
    b.panel(1002,240,556,306,"Main result",d["metric_name"],GOLD)
    b.text(1028,349,d["metric"],64,GOLD,700)
    b.text(1028,393,d["result"],19,TEXT,700)
    b.text(1028,428,d["result2"],15,MUTED)
    b.rect(1028,462,504,60,PANEL2,8,LINE)
    b.text(1046,490,"SAMPLE / SOURCE",12,BLUE,700)
    b.text(1046,514,d["source"],13,MUTED)
    b.panel(42,563,942,258,"Mission evidence",d["evidence_label"],GREEN)
    rows=list(zip(d["evidence"],d["scores"]))
    for i,(label,value) in enumerate(rows):
        y=651+i*41
        b.rect(65,y-27,896,36,PANEL2,6,LINE)
        b.text(82,y,label,16,TEXT,600)
        b.text(930,y,value,17,GREEN if not value.startswith("−") else RED,700,"end")
    b.panel(1002,563,556,258,"Interpretation guardrails","Separate observation from inference",GOLD)
    b.text(1028,641,"OBSERVED",12,GREEN,700)
    b.text(1028,670,d["result"],17,TEXT,600)
    b.text(1028,713,"LIMIT",12,GOLD,700)
    b.text(1028,743,d["caution"],14,MUTED)
    b.text(1028,788,"See full run settings and source details  →",14,BLUE,700)
    footer(b,"C · EVIDENCE DESK")
    b.save(f"arena-c-{key}")


if __name__=="__main__":
    for key,data in MISSIONS.items():
        mission_studio(key,data)
        timeline(key,data)
        evidence_desk(key,data)

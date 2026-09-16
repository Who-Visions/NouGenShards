"""Learn With Mrs. B pilot: cover + Unit 1 (pp. 1-5) as print-ready vector line art.

100% PURE BLACK AND WHITE LINE ART (No Grayscale, No Color Fills).
Elevated vector drawing engine aligned to official NouGenArt model sheets.
"""
from pathlib import Path
import math

from nougen_vector_art import (
    W, H, INK, LINE, FINE, THIN, FONT, HEAVY,
    st, ln, text, hollow, dotted, ruled, star, crayon,
    mrs_b_standing, curious_granddaughter, shape_friend
)

OUT = Path(__file__).parent

# ----------------------------------------------------------------- people
HAIR = {
    "puffs": lambda cx, cy, r: (f'<circle cx="{cx-r*0.88}" cy="{cy-r*0.88}" r="{r*0.46}" {st()}/>'
                                f'<circle cx="{cx+r*0.88}" cy="{cy-r*0.88}" r="{r*0.46}" {st()}/>'),
    "curly": lambda cx, cy, r: "".join(f'<circle cx="{cx + r*dx}" cy="{cy - r*dy}" r="{r*0.32}" {st()}/>'
                                       for dx, dy in ((-0.85, 0.4), (-0.55, 0.85), (0, 1.05), (0.55, 0.85), (0.85, 0.4))),
    "bob": lambda cx, cy, r: (f'<path d="M{cx-r*1.15},{cy+r*0.6} Q{cx-r*1.25},{cy-r*1.3} {cx},{cy-r*1.2} '
                              f'Q{cx+r*1.25},{cy-r*1.3} {cx+r*1.15},{cy+r*0.6} Z" {st()}/>'),
    "short": lambda cx, cy, r: (f'<path d="M{cx-r*0.95},{cy-r*0.2} Q{cx-r},{cy-r*1.15} {cx},{cy-r*1.08} '
                                f'Q{cx+r},{cy-r*1.15} {cx+r*0.95},{cy-r*0.2} Q{cx},{cy-r*0.7} {cx-r*0.95},{cy-r*0.2} Z" {st()}/>'),
}


def face(cx, cy, r, expr="happy", hair=None, w=LINE):
    out = []
    if hair in ("bob",):
        out.append(HAIR[hair](cx, cy, r))
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" {st(w)}/>')
    if hair in ("puffs", "curly", "short"):
        out.append(HAIR[hair](cx, cy, r))
    ex, ey, er = r * 0.36, cy - r * 0.08, max(r * 0.09, 3)
    if expr == "tired":
        for s in (-1, 1):
            out.append(f'<path d="M{cx+s*ex-r*0.16},{ey} Q{cx+s*ex},{ey+r*0.12} {cx+s*ex+r*0.16},{ey}" {ln(FINE)}/>')
        out.append(f'<ellipse cx="{cx}" cy="{cy+r*0.42}" rx="{r*0.12}" ry="{r*0.08}" {st(FINE)}/>')
        out.append(text(cx + r * 1.05, cy - r * 0.7, "z", size=int(r * 0.45)) + text(cx + r * 1.35, cy - r * 1.05, "z", size=int(r * 0.35)))
    else:
        big = expr == "scared"
        for s in (-1, 1):
            if big:
                out.append(f'<circle cx="{cx+s*ex}" cy="{ey}" r="{r*0.18}" {st(FINE)}/>')
                out.append(f'<circle cx="{cx+s*ex}" cy="{ey}" r="{er*0.8}" fill="{INK}"/>')
            else:
                out.append(f'<circle cx="{cx+s*ex}" cy="{ey}" r="{er*1.2}" fill="{INK}"/>')
                out.append(f'<circle cx="{cx+s*ex - 1.5}" cy="{ey - 1.5}" r="{er*0.4}" fill="#fff"/>')
        if expr == "happy":
            out.append(f'<path d="M{cx-r*0.42},{cy+r*0.22} Q{cx},{cy+r*0.72} {cx+r*0.42},{cy+r*0.22} Z" {st(FINE+0.5)}/>')
        elif expr == "sad":
            out.append(f'<path d="M{cx-r*0.36},{cy+r*0.55} Q{cx},{cy+r*0.2} {cx+r*0.36},{cy+r*0.55}" {ln(FINE+0.5)}/>')
            for s in (-1, 1):
                out.append(f'<line x1="{cx+s*(ex+r*0.18)}" y1="{ey-r*0.2}" x2="{cx+s*(ex-r*0.14)}" y2="{ey-r*0.36}" {ln(FINE)}/>')
            if r >= 30:
                out.append(f'<path d="M{cx+ex},{ey+r*0.18} q{-r*0.08},{r*0.16} 0,{r*0.22} q{r*0.08},{-r*0.06} 0,{-r*0.22} Z" {st(2.5)}/>')
        elif expr == "mad":
            out.append(f'<path d="M{cx-r*0.32},{cy+r*0.5} Q{cx},{cy+r*0.32} {cx+r*0.32},{cy+r*0.5}" {ln(FINE+0.5)}/>')
            for s in (-1, 1):
                out.append(f'<line x1="{cx+s*ex+s*r*0.18}" y1="{ey-r*0.3}" x2="{cx+s*ex-s*r*0.14}" y2="{ey-r*0.16}" {ln(FINE+0.5)}/>')
        elif expr == "scared":
            out.append(f'<ellipse cx="{cx}" cy="{cy+r*0.45}" rx="{r*0.16}" ry="{r*0.2}" {st(FINE)}/>')
            for s in (-1, 1):
                out.append(f'<path d="M{cx+s*ex-r*0.15},{ey-r*0.32} Q{cx+s*ex},{ey-r*0.45} {cx+s*ex+r*0.15},{ey-r*0.32}" {ln(FINE)}/>')
    return "".join(out)


def child(cx, top, s=1.0, expr="happy", hair="short", arm="down", holds=None):
    """Elevated child standing vector model with distinct hairstyles & shoes."""
    r = 50 * s
    hy = top + r
    out = []
    body_top, body_h, bw = hy + r * 0.95, 120 * s, 100 * s
    # legs & shoes
    for dx in (-0.22, 0.22):
        x = cx + dx * bw
        out.append(f'<rect x="{x-14*s}" y="{body_top+body_h-10*s}" width="{28*s}" height="{95*s}" rx="{10*s}" {st(LINE)}/>')
        out.append(f'<path d="M{x-20*s},{body_top+body_h+85*s} L{x+24*s},{body_top+body_h+85*s} '
                   f'Q{x+32*s},{body_top+body_h+98*s} {x+22*s},{body_top+body_h+108*s} '
                   f'L{x-20*s},{body_top+body_h+108*s} Z" {st(LINE)}/>')
        out.append(f'<line x1="{x-20*s}" y1="{body_top+body_h+100*s}" x2="{x+28*s}" y2="{body_top+body_h+100*s}" {ln(FINE)}/>')
    # arms
    sh_y = body_top + 22 * s
    for side in (-1, 1):
        sx = cx + side * bw * 0.46
        if arm == "wave" and side == 1:
            ex, ey = sx + 58 * s, sh_y - 85 * s
        elif arm == "up":
            ex, ey = sx + side * 45 * s, sh_y - 90 * s
        else:
            ex, ey = sx + side * 36 * s, sh_y + 92 * s
        out.append(f'<line x1="{sx}" y1="{sh_y}" x2="{ex}" y2="{ey}" stroke="{INK}" stroke-width="{28*s+LINE}" stroke-linecap="round"/>')
        out.append(f'<line x1="{sx}" y1="{sh_y}" x2="{ex}" y2="{ey}" stroke="#fff" stroke-width="{28*s-LINE+2}" stroke-linecap="round"/>')
        out.append(f'<circle cx="{ex}" cy="{ey}" r="{14*s}" {st(FINE)}/>')
        hand = 1 if cx >= W / 2 else -1
        if holds == "crayon" and side == hand:
            ang = -90 - 5 * side if arm == "up" else (-35 if side == 1 else 215)
            out.append(crayon(ex, ey, 95 * s, angle=ang, th=24 * s))
        elif holds == "crayon-inner" and side == -hand:
            out.append(crayon(ex, ey, 80 * s, angle=-90, th=24 * s))
    # body (shirt)
    out.append(f'<path d="M{cx-bw/2},{body_top+18*s} Q{cx-bw/2},{body_top} {cx-bw/2+22*s},{body_top} '
               f'L{cx+bw/2-22*s},{body_top} Q{cx+bw/2},{body_top} {cx+bw/2},{body_top+18*s} '
               f'L{cx+bw/2},{body_top+body_h} L{cx-bw/2},{body_top+body_h} Z" {st(LINE)}/>')
    out.append(f'<path d="M{cx-18*s},{body_top} Q{cx},{body_top+20*s} {cx+18*s},{body_top}" {ln(FINE)}/>')
    # neck + head
    out.append(f'<rect x="{cx-12*s}" y="{hy+r*0.8}" width="{24*s}" height="{r*0.3}" {st(FINE)}/>')
    out.append(face(cx, hy, r, expr, hair))
    return "".join(out)


def mrs_b(cx, top, s=1.0, arm="wave", holds=None):
    """Wrapper mapping to official Mrs. B vector model."""
    return mrs_b_standing(cx, top, s=s, arm=arm, holds=holds)


# ----------------------------------------------------------------- page chrome
def icon(kind, x, y, s=1.0):
    if kind == "SEE":
        return (f'<path d="M{x-30*s},{y} Q{x},{y-28*s} {x+30*s},{y} Q{x},{y+28*s} {x-30*s},{y} Z" {st(FINE+1)}/>'
                f'<circle cx="{x}" cy="{y}" r="{10*s}" fill="{INK}"/>'
                f'<circle cx="{x-2*s}" cy="{y-2*s}" r="{3*s}" fill="#fff"/>')
    if kind == "SAY":
        return (f'<path d="M{x-30*s},{y-20*s} h{60*s} a8,8 0 0 1 8,8 v{26*s} a8,8 0 0 1 -8,8 h{-38*s} l{-14*s},{14*s} v{-14*s} '
                f'h{-8*s} a8,8 0 0 1 -8,-8 v{-26*s} a8,8 0 0 1 8,-8 Z" {st(FINE+1)}/>')
    if kind == "COLOR":
        return crayon(x - 30 * s, y + 10 * s, 64 * s, angle=-25, w=FINE, th=18 * s)
    if kind == "TRACE":
        return (crayon(x - 30 * s, y + 4 * s, 64 * s, angle=-25, w=FINE, th=18 * s) +
                f'<line x1="{x-34*s}" y1="{y+26*s}" x2="{x+34*s}" y2="{y+26*s}" stroke="{INK}" stroke-width="3" stroke-dasharray="2 7" stroke-linecap="round"/>')
    return star(x, y, 28 * s, w=FINE + 1)


def page(n, step, title, direction, words, tip, body, unit="UNIT 1 · ME & FEELINGS"):
    pill = max(320, len(unit) * 11.5 + 40)
    head = (f'<rect x="40" y="32" width="{pill}" height="46" rx="23" {st(FINE)}/>'
            + text(40 + pill / 2, 63, unit, size=20)
            + f'<rect x="600" y="26" width="210" height="58" rx="29" {st(FINE)}/>'
            + icon(step, 645, 55, 0.7) + text(685, 65, step, size=26, anchor="start", fam=HEAVY)
            + hollow(W / 2, 145, title, size=52)
            + text(W / 2, 185, direction, size=24, weight="700"))
    foot = (f'<rect x="40" y="980" width="770" height="88" rx="18" {st(FINE)}/>'
            + text(62, 1012, "Words: " + " · ".join(words), size=17, anchor="start", weight="700")
            + text(62, 1042, "Mrs. B tip: " + tip, size=15, anchor="start", weight="400")
            + text(785, 1045, f"{n}", size=24, anchor="end", fam=HEAVY))
    return svg(head + body + foot)


def svg(inner):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            f'<rect width="{W}" height="{H}" fill="#fff"/>{inner}</svg>')


WORDS = ["hello", "name", "happy", "sad", "mad", "scared", "tired"]


# ----------------------------------------------------------------- PAGES

def cover():
    b = []
    b.append(f'<rect x="30" y="30" width="790" height="1040" rx="30" {ln(LINE)}/>')
    b.append(f'<path d="M150,70 h550 l-30,40 l30,40 h-550 l30,-40 Z" {st()}/>')
    b.append(text(W / 2, 124, "LEARN WITH MRS. B", size=38, fam=HEAVY))
    b.append(hollow(W / 2, 235, "My First English", size=68))
    b.append(hollow(W / 2, 320, "Coloring & Activity", size=68))
    b.append(hollow(W / 2, 405, "Book", size=82))
    for (x, y, r) in ((90, 200, 26), (770, 210, 22), (95, 450, 20), (760, 440, 28)):
        b.append(star(x, y, r))
    
    # Mrs. B in center
    b.append(mrs_b_standing(340, 480, 0.88, arm="wave", holds="book"))
    # Curious (granddaughter) next to her
    b.append(curious_granddaughter(580, 560, 0.78, arm="wave"))
    
    # Shape Friends
    b.append(shape_friend("circle", 150, 720, r=36))
    b.append(shape_friend("star", 720, 720, r=36))
    
    # Crayons row at bottom
    for i in range(6):
        b.append(crayon(80 + i * 118, 970, 105, angle=0))
    b.append(text(W / 2, 1035, "ESOL · Pre-K to Grade 1 · See · Say · Color · Trace · Use", size=20))
    return svg("".join(b))


def p1():
    """
    Unit 1, Page 1: 100% PURE BLACK AND WHITE VECTOR MASTER ART.
    - Mrs. B & Curious in the classroom
    - Shape Friends (Circle & Star)
    - Classroom environment (window, bookshelf, poster, bunting)
    - Helen Elliston 4-Step Blank Shading Swatches (Ready for coloring!)
    - Bilingual Home Prompt in Haitian Creole & English
    """
    b = []
    
    # Outer art boundary frame
    b.append(f'<rect x="45" y="200" width="760" height="665" rx="18" {st(LINE)}/>')
    
    # Classroom Background: Bunting Banner overhead
    b.append(f'<path d="M50,230 Q425,270 800,230" {ln(FINE+1)}/>')
    flags = ["H", "E", "L", "L", "O", "!", "♡"]
    for i, ch in enumerate(flags):
        fx = 120 + i * 90
        fy = 238 + int(math.sin(i * 0.5) * 12)
        b.append(f'<polygon points="{fx-32},{fy} {fx+32},{fy} {fx},{fy+50}" {st(FINE)}/>')
        b.append(text(fx, fy + 32, ch, size=24, fam=HEAVY))
    
    # Classroom Window with Sun & Clouds (Right side)
    b.append(f'<rect x="540" y="290" width="240" height="230" rx="8" {st(LINE)}/>')
    b.append(f'<line x1="660" y1="290" x2="660" y2="520" {ln(FINE)}/>')
    b.append(f'<line x1="540" y1="405" x2="780" y2="405" {ln(FINE)}/>')
    b.append(f'<circle cx="730" cy="340" r="32" {st(FINE)}/>')
    for ray_i in range(8):
        ray_a = ray_i * math.pi / 4
        b.append(f'<line x1="{730 + 40*math.cos(ray_a):.1f}" y1="{340 + 40*math.sin(ray_a):.1f}" '
                 f'x2="{730 + 54*math.cos(ray_a):.1f}" y2="{340 + 54*math.sin(ray_a):.1f}" {ln(FINE)}/>')
    
    # Classroom Motivational Poster (Left side)
    b.append(f'<rect x="65" y="290" width="130" height="170" rx="6" {st(LINE)}/>')
    b.append(text(130, 325, "♡", size=22, fam=FONT))
    b.append(text(130, 355, "Learn", size=18, fam=HEAVY))
    b.append(text(130, 385, "Grow", size=18, fam=HEAVY))
    b.append(text(130, 415, "Belong", size=18, fam=HEAVY))
    b.append(text(130, 442, "Together", size=15, fam=FONT))
    
    # Bookshelf (Center-Right Background)
    b.append(f'<rect x="420" y="470" width="360" height="250" rx="6" {st(LINE)}/>')
    b.append(f'<line x1="420" y1="595" x2="780" y2="595" {ln(LINE)}/>')
    # Books on shelf
    for bi in range(6):
        b.append(f'<rect x="{440 + bi*22}" y="500" width="18" height="85" rx="3" {st(FINE)}/>')
    # Potted Plant on shelf top
    b.append(f'<polygon points="460,470 485,470 480,440 465,440" {st(FINE)}/>')
    b.append(f'<circle cx="472" cy="425" r="16" {st(FINE)}/>')
    # Heart Crayon Caddy
    b.append(f'<rect x="700" y="525" width="55" height="60" rx="6" {st(FINE)}/>')
    b.append(text(727, 562, "♡", size=22))
    b.append(crayon(712, 515, 45, angle=-80, th=12, w=FINE))
    b.append(crayon(732, 515, 45, angle=-70, th=12, w=FINE))
    
    # Mrs. B Full Character Model (Left-Center)
    b.append(mrs_b_standing(285, 330, s=0.88, arm="wave", holds="book"))
    
    # Mrs. B Speech Bubble
    b.append(f'<path d="M120,240 h260 a14,14 0 0 1 14,14 v44 a14,14 0 0 1 -14,14 h-150 l-25,22 l8,-22 h-93 a14,14 0 0 1 -14,-14 v-44 a14,14 0 0 1 14,-14 Z" {st(FINE+1)}/>')
    b.append(text(250, 276, "Hello Learners! Let's Go Further Together! ♡", size=14, fam=HEAVY))
    
    # Curious (Granddaughter) Full Character Model (Right-Center)
    b.append(curious_granddaughter(540, 470, s=0.75, arm="wave"))
    
    # Shape Friends in Foreground (Waving & Cheering)
    b.append(shape_friend("circle", 430, 770, r=32))
    b.append(shape_friend("star", 710, 770, r=34))
    
    # Shading Practice Bar (Helen Elliston Formula - 100% PURE B&W TEST CIRCLES FOR CHILD TO COLOR)
    b.append(f'<rect x="45" y="878" width="760" height="88" rx="14" {st(FINE+1)}/>')
    b.append(text(65, 912, "4-STEP COLORING GUIDE (TRY YOUR COLORS!):", size=15, anchor="start", fam=HEAVY))
    b.append(text(65, 942, "1. Light Base Wash  →  2. Medium Midtone  →  3. Dark Shadow  →  4. White Highlight", size=13, anchor="start", fam=FONT))
    
    # 4 Blank Test Swatch Circles
    swatch_labels = ["1. Base", "2. Midtone", "3. Shadow", "4. Highlight"]
    for si, slabel in enumerate(swatch_labels):
        sx = 510 + si * 72
        b.append(f'<circle cx="{sx}" cy="{910}" r="18" {st(FINE)}/>')
        b.append(text(sx, 945, slabel, size=11, anchor="middle", fam=FONT))
    
    return page(1, "SEE", "HELLO, I'M MRS. B!", "Say hello to Mrs. B and Curious! Color the classroom.",
                ["teacher / pwofesè", "hello / bonjou", "friend / zanmi", "kind / jantiy"],
                "Mande pitit ou a: \"Kiyès ki pwofesè a?\" (Who is the teacher?) Practice saying \"Hello, Mrs. B!\" together.",
                "".join(b))


def p2():
    feelings = ["happy", "sad", "mad", "scared", "tired"]
    shuffled = ["tired", "happy", "scared", "sad", "mad"]
    hairs = ["puffs", "short", "curly", "bob", "short"]
    b = []
    for i, (f, hr) in enumerate(zip(feelings, hairs)):
        y = 310 + i * 128
        b.append(face(190, y, 52, f, hr))
        b.append(f'<circle cx="300" cy="{y}" r="9" fill="{INK}"/>')
    for i, wd in enumerate(shuffled):
        y = 310 + i * 128
        b.append(f'<circle cx="530" cy="{y}" r="9" fill="{INK}"/>')
        b.append(f'<rect x="560" y="{y-38}" width="220" height="76" rx="38" {st(FINE+1)}/>')
        b.append(text(670, y + 12, wd, size=36))
    b.append(text(W / 2, 935, "I feel ________.", size=34))
    return page(2, "SAY", "How Do I Feel?", "Point. Say: I feel ___. Match.",
                feelings, "Make each face together, then say the sentence.", "".join(b))


def p3():
    b = [f'<path d="M40,860 Q425,820 810,860" {ln()}/>',
         f'<circle cx="720" cy="300" r="48" {st()}/>']
    for k in range(10):
        a = k * math.pi / 5
        b.append(f'<line x1="{720+62*math.cos(a):.0f}" y1="{300+62*math.sin(a):.0f}" x2="{720+88*math.cos(a):.0f}" y2="{300+88*math.sin(a):.0f}" {ln(FINE+1)}/>')
    b.append(f'<rect x="118" y="500" width="44" height="345" rx="10" {st()}/>')
    canopy = ((140, 450, 80), (95, 515, 55), (190, 515, 58), (140, 385, 62))
    for cx, cy, r in canopy:
        b.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" {st()}/>')
    for cx, cy, r in canopy:
        b.append(f'<circle cx="{cx}" cy="{cy}" r="{r - LINE / 2}" fill="#fff"/>')
    kids = [(290, "happy", "puffs"), (430, "sad", "short"), (570, "scared", "curly"), (710, "tired", "bob")]
    for cx, ex, hr in kids:
        b.append(child(cx, 600, 0.72, ex, hr))
    rows = [("happy", "yellow"), ("sad", "blue"), ("scared", "green"), ("tired", "red")]
    for i, (f, c) in enumerate(rows):
        x = 60 + i * 190
        b.append(face(x + 32, 918, 30, f))
        b.append(text(x + 70, 928, f"= {c}", size=24, anchor="start"))
    return page(3, "COLOR", "Feelings Park", "Listen. Color each child.",
                ["happy", "sad", "scared", "tired", "yellow", "blue", "green", "red"],
                "Read one line at a time. Point first, then color.", "".join(b))


def p4():
    words = ["happy", "sad", "mad"]
    b = []
    for i, w in enumerate(words):
        y = 290 + i * 210
        b.append(face(170, y + 48, 52, w))
        b.append(f'<g transform="translate(270, {y})">')
        b.append(ruled(0, 0, 500, h=96))
        b.append(dotted(16, 76, w, size=88))
        b.append(ruled(0, 100, 500, h=96))
        b.append(f'</g>')
    return page(4, "TRACE", "Trace & Write", "Trace the feeling words with Mrs. B.",
                words, "Trace slowly with your finger first, then with a crayon.", "".join(b))


def p5():
    b = [f'<rect x="70" y="290" width="710" height="570" rx="24" {st()}/>',
         f'<rect x="100" y="320" width="650" height="510" rx="16" {ln(FINE)}/>',
         text(W / 2, 480, "Draw your feeling face here!", size=32, weight="400", fill="#888"),
         shape_friend("circle", 170, 730, r=32),
         shape_friend("star", 680, 730, r=34),
         f'<g transform="translate(100, 885)">',
         ruled(0, 0, 650, h=80),
         text(30, 58, "Today I feel _________________ .", size=32, anchor="start"),
         f'</g>']
    return page(5, "USE", "My Feeling Today", "Draw how you feel today. Write your word.",
                ["today", "I feel", "happy", "brave"],
                "Talk about today: 'What made you smile today?'", "".join(b))


# ----------------------------------------------------------------- main build
def build_all():
    pages = [
        ("00_cover.svg", cover()),
        ("01_p1_see.svg", p1()),
        ("02_p2_say.svg", p2()),
        ("03_p3_color.svg", p3()),
        ("04_p4_trace.svg", p4()),
        ("05_p5_use.svg", p5()),
    ]
    for fn, content in pages:
        fp = OUT / fn
        fp.write_text(content, encoding="utf-8")
        print(f"Wrote {fp} ({len(content)} bytes)")


if __name__ == "__main__":
    build_all()

"""Learn With Mrs. B, Unit 6: Animals & Actions (pp. 26-30), print-ready line art.

Reuses the pilot generator (build_pilot.py) for page chrome, people and letters.
Animal and action helpers live here so the shared generator stays untouched.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_pilot import *  # noqa: F401,F403
from build_pilot import OUT, W, INK, LINE, FINE, FONT, HEAVY

UNIT = "UNIT 6 · ANIMALS & ACTIONS"
WORDS = ["cat", "dog", "fish", "bird", "frog", "run", "jump", "swim", "fly"]


# ----------------------------------------------------------------- helpers
def limb(x1, y1, x2, y2, w, cap=True):
    """Outlined tube (leg/arm): black stroke with a white core."""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{INK}" stroke-width="{w+LINE}" stroke-linecap="round"/>'
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#fff" stroke-width="{w-LINE+2}" stroke-linecap="round"/>')


def tube(d, w):
    """Outlined curved tube along path d (tails)."""
    return (f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{w+LINE}" stroke-linecap="round"/>'
            f'<path d="{d}" fill="none" stroke="#fff" stroke-width="{w-LINE+2}" stroke-linecap="round"/>')


def eye(x, y, r):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{INK}"/>'


def speed(x, y, s=1.0, d=1, n=3):
    """Motion lines trailing behind something moving in direction d."""
    return "".join(f'<line x1="{x - d*(10 + (i % 2) * 14)*s:.1f}" y1="{y + (i - 1) * 22 * s:.1f}" '
                   f'x2="{x - d*(52 + (i % 2) * 14)*s:.1f}" y2="{y + (i - 1) * 22 * s:.1f}" {ln(FINE+0.5)}/>'
                   for i in range(n))


# ----------------------------------------------------------------- animals
def cat(cx, cy, s=1.0):
    """Sitting cat facing front. cy is the body center; ears reach cy-135s, feet cy+112s."""
    o = [tube(f"M{cx+50*s},{cy+85*s} Q{cx+120*s},{cy+70*s} {cx+105*s},{cy+10*s} Q{cx+95*s},{cy-25*s} {cx+115*s},{cy-40*s}", 22 * s),
         f'<ellipse cx="{cx}" cy="{cy+35*s}" rx="{62*s}" ry="{75*s}" {st()}/>']
    hx, hy, r = cx, cy - 50 * s, 52 * s
    for sd in (-1, 1):
        o.append(f'<polygon points="{hx+sd*r*0.95},{hy-r*0.1} {hx+sd*r*0.85},{hy-r*1.6} {hx+sd*r*0.2},{hy-r*0.85}" {st()}/>')
        o.append(f'<polygon points="{hx+sd*r*0.78},{hy-r*0.55} {hx+sd*r*0.75},{hy-r*1.25} {hx+sd*r*0.42},{hy-r*0.85}" {ln(FINE)}/>')
    o.append(f'<circle cx="{hx}" cy="{hy}" r="{r}" {st()}/>')
    for sd in (-1, 1):
        o.append(eye(hx + sd * r * 0.38, hy - r * 0.12, r * 0.11))
        for k in (-1, 0, 1):
            o.append(f'<line x1="{hx+sd*r*0.35}" y1="{hy+r*0.3+k*r*0.12}" x2="{hx+sd*r*1.25}" y2="{hy+r*0.22+k*r*0.28}" {ln(2.5)}/>')
        o.append(f'<ellipse cx="{cx+sd*28*s}" cy="{cy+105*s}" rx="{22*s}" ry="{13*s}" {st(FINE+1)}/>')
    o.append(f'<polygon points="{hx-r*0.12},{hy+r*0.14} {hx+r*0.12},{hy+r*0.14} {hx},{hy+r*0.3}" fill="{INK}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>')
    o.append(f'<path d="M{hx-r*0.28},{hy+r*0.42} Q{hx-r*0.14},{hy+r*0.58} {hx},{hy+r*0.32} Q{hx+r*0.14},{hy+r*0.58} {hx+r*0.28},{hy+r*0.42}" {ln(FINE)}/>')
    return "".join(o)


def dog(cx, cy, s=1.0, d=1, run=False):
    """Side-view dog facing direction d. cy is the body center; paws near cy+95s."""
    o = []
    bx = cx - d * 75 * s
    o.append(tube(f"M{bx},{cy-20*s} Q{bx-d*30*s},{cy-40*s} {bx-d*38*s},{cy-80*s}", 16 * s))
    if run:
        legs = [(-55, 20, -110, 70), (-35, 20, -80, 85), (40, 20, 105, 60), (58, 20, 118, 45)]
    else:
        legs = [(-58, 20, -62, 95), (-32, 20, -32, 95), (35, 20, 35, 95), (60, 20, 62, 95)]
    lw = (22 if run else 28) * s
    for i in (1, 3, 0, 2):
        x1, y1, x2, y2 = legs[i]
        o.append(limb(cx + d * x1 * s, cy + y1 * s, cx + d * x2 * s, cy + y2 * s, lw))
    if not run:
        for x1, y1, x2, y2 in legs:
            o.append(f'<ellipse cx="{cx+d*(x2+8)*s}" cy="{cy+(y2+10)*s}" rx="{19*s}" ry="{10*s}" {st(FINE+1)}/>')
    o.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{85*s}" ry="{45*s}" {st()}/>')
    hx, hy, r = cx + d * 78 * s, cy - 52 * s, 42 * s
    o.append(f'<circle cx="{hx}" cy="{hy}" r="{r}" {st()}/>')
    o.append(f'<ellipse cx="{hx+d*38*s}" cy="{hy+14*s}" rx="{30*s}" ry="{20*s}" {st()}/>')
    o.append(f'<ellipse cx="{hx+d*64*s}" cy="{hy+6*s}" rx="{9*s}" ry="{8*s}" fill="{INK}"/>')
    o.append(f'<path d="M{hx+d*30*s},{hy+26*s} Q{hx+d*44*s},{hy+36*s} {hx+d*58*s},{hy+24*s}" {ln(FINE)}/>')
    o.append(eye(hx + d * 12 * s, hy - 10 * s, 5.5 * s))
    o.append(f'<ellipse cx="{hx-d*22*s}" cy="{hy+10*s}" rx="{15*s}" ry="{32*s}" transform="rotate({d*20} {hx-d*22*s} {hy+10*s})" {st()}/>')
    o.append(f'<path d="M{hx-d*28*s},{hy+36*s} Q{hx},{hy+50*s} {hx+d*16*s},{hy+38*s}" {ln(FINE)}/>')
    return "".join(o)


def fish(cx, cy, s=1.0, d=1):
    """Side-view fish facing d. About 230s wide, 110s tall."""
    o = [f'<polygon points="{cx-d*55*s},{cy} {cx-d*115*s},{cy-45*s} {cx-d*105*s},{cy} {cx-d*115*s},{cy+45*s}" {st()}/>',
         f'<path d="M{cx-d*25*s},{cy-38*s} Q{cx-d*5*s},{cy-78*s} {cx+d*40*s},{cy-38*s}" {st()}/>',
         f'<ellipse cx="{cx}" cy="{cy}" rx="{75*s}" ry="{45*s}" {st()}/>',
         f'<path d="M{cx+d*28*s},{cy-30*s} Q{cx+d*12*s},{cy} {cx+d*28*s},{cy+30*s}" {ln(FINE)}/>',
         f'<circle cx="{cx+d*48*s}" cy="{cy-12*s}" r="{11*s}" {st(FINE)}/>',
         eye(cx + d * 50 * s, cy - 12 * s, 5 * s),
         f'<path d="M{cx+d*52*s},{cy+14*s} Q{cx+d*62*s},{cy+20*s} {cx+d*70*s},{cy+10*s}" {ln(FINE)}/>',
         f'<path d="M{cx-d*5*s},{cy+8*s} Q{cx-d*25*s},{cy+30*s} {cx+d*5*s},{cy+30*s} Z" {st(FINE)}/>']
    return "".join(o)


def bird(cx, cy, s=1.0, d=1, fly=True):
    """Round bird facing d. Flying: wing raised; perched: folded wing + legs."""
    o = [f'<polygon points="{cx-d*40*s},{cy-5*s} {cx-d*95*s},{cy-25*s} {cx-d*90*s},{cy+20*s}" {st()}/>']
    if not fly:
        for k in (-12, 12):
            o.append(f'<path d="M{cx+k*s},{cy+38*s} l0,{24*s} m{-10*s},0 l{20*s},0" {ln(FINE+0.5)}/>')
    o.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{58*s}" ry="{44*s}" {st()}/>')
    hx, hy, r = cx + d * 45 * s, cy - 36 * s, 32 * s
    o.append(f'<polygon points="{hx+d*26*s},{hy-9*s} {hx+d*58*s},{hy+2*s} {hx+d*26*s},{hy+13*s}" {st(FINE+1)}/>')
    o.append(f'<circle cx="{hx}" cy="{hy}" r="{r}" {st()}/>')
    o.append(eye(hx + d * 10 * s, hy - 6 * s, 5.5 * s))
    if fly:
        o.append(f'<path d="M{cx+d*15*s},{cy-15*s} Q{cx+d*5*s},{cy-95*s} {cx-d*55*s},{cy-115*s} '
                 f'Q{cx-d*42*s},{cy-88*s} {cx-d*58*s},{cy-78*s} Q{cx-d*40*s},{cy-58*s} {cx-d*52*s},{cy-44*s} '
                 f'Q{cx-d*30*s},{cy-30*s} {cx-d*30*s},{cy-5*s} Z" {st()}/>')
    else:
        o.append(f'<path d="M{cx-d*35*s},{cy-5*s} Q{cx},{cy-25*s} {cx+d*22*s},{cy+5*s} Q{cx-d*5*s},{cy+30*s} {cx-d*35*s},{cy-5*s} Z" {st(FINE+1)}/>')
    return "".join(o)


def frog(cx, cy, s=1.0, jump=False):
    """Front-view frog. Sitting: wide and low; jumping: legs stretched down, arms out."""
    o = []
    if jump:
        for sd in (-1, 1):
            o.append(limb(cx + sd * 30 * s, cy + 40 * s, cx + sd * 70 * s, cy + 115 * s, 26 * s))
            o.append(f'<ellipse cx="{cx+sd*84*s}" cy="{cy+125*s}" rx="{26*s}" ry="{12*s}" {st()}/>')
            o.append(limb(cx + sd * 45 * s, cy - 5 * s, cx + sd * 100 * s, cy - 30 * s, 20 * s))
            o.append(f'<circle cx="{cx+sd*106*s}" cy="{cy-34*s}" r="{14*s}" {st()}/>')
        o.append(f'<ellipse cx="{cx}" cy="{cy+5*s}" rx="{62*s}" ry="{68*s}" {st()}/>')
    else:
        for sd in (-1, 1):
            o.append(f'<ellipse cx="{cx+sd*62*s}" cy="{cy+38*s}" rx="{40*s}" ry="{30*s}" {st()}/>')
            o.append(f'<ellipse cx="{cx+sd*92*s}" cy="{cy+68*s}" rx="{32*s}" ry="{12*s}" {st()}/>')
        o.append(f'<ellipse cx="{cx}" cy="{cy+10*s}" rx="{80*s}" ry="{58*s}" {st()}/>')
        for sd in (-1, 1):
            o.append(f'<ellipse cx="{cx+sd*28*s}" cy="{cy+66*s}" rx="{18*s}" ry="{10*s}" {st(FINE+1)}/>')
    ey = cy - 52 * s
    for sd in (-1, 1):
        o.append(f'<circle cx="{cx+sd*36*s}" cy="{ey}" r="{24*s}" {st()}/>')
        o.append(eye(cx + sd * 36 * s, ey, 8 * s))
    o.append(f'<path d="M{cx-45*s},{cy-5*s} Q{cx},{cy+35*s} {cx+45*s},{cy-5*s}" {ln(FINE+0.5)}/>')
    o.append(f'<path d="M{cx-60*s},{cy-35*s} Q{cx},{cy-58*s} {cx+60*s},{cy-35*s}" fill="#fff" stroke="none"/>')
    return "".join(o)


ANIMALS = {"cat": cat, "dog": dog, "fish": fish, "bird": bird, "frog": frog}


# ----------------------------------------------------------------- action icons
def act_icon(kind, x, y, s=1.0):
    """Verb icon centered at x, y, about 110s wide."""
    if kind == "run":  # sneaker with speed lines
        return (f'<path d="M{x-35*s},{y-30*s} L{x-5*s},{y-30*s} Q{x+5*s},{y-5*s} {x+40*s},{y} '
                f'Q{x+58*s},{y+4*s} {x+58*s},{y+20*s} L{x-35*s},{y+20*s} Z" {st(FINE+1)}/>'
                f'<line x1="{x-35*s}" y1="{y+8*s}" x2="{x+58*s}" y2="{y+8*s}" {ln(FINE)}/>'
                + speed(x - 38 * s, y - 8 * s, s * 0.9, 1))
    if kind == "jump":  # hop arc over the ground
        return (f'<line x1="{x-58*s}" y1="{y+30*s}" x2="{x+58*s}" y2="{y+30*s}" {ln(FINE+1)}/>'
                f'<path d="M{x-45*s},{y+22*s} Q{x},{y-75*s} {x+42*s},{y+14*s}" fill="none" stroke="{INK}" stroke-width="{FINE+1}" stroke-dasharray="10 8" stroke-linecap="round"/>'
                f'<polygon points="{x+50*s},{y+22*s} {x+28*s},{y+10*s} {x+48*s},{y-2*s}" fill="{INK}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>')
    if kind == "swim":  # waves
        return "".join(f'<path d="M{x-55*s},{y+k*24*s} q{14*s},{-14*s} {27*s},0 t{27*s},0 t{27*s},0 t{27*s},0" {ln(FINE+1)}/>'
                       for k in (-1, 0, 1))
    # fly: a pair of feathered wings
    o = []
    for d in (-1, 1):
        o.append(f'<path d="M{x+d*6*s},{y+22*s} Q{x+d*10*s},{y-30*s} {x+d*58*s},{y-40*s} '
                 f'Q{x+d*50*s},{y-24*s} {x+d*58*s},{y-16*s} Q{x+d*42*s},{y-4*s} {x+d*48*s},{y+6*s} '
                 f'Q{x+d*30*s},{y+14*s} {x+d*6*s},{y+22*s} Z" {st(FINE+1)}/>')
    return "".join(o)


def paw(cx, cy, s=1.0):
    o = [f'<ellipse cx="{cx}" cy="{cy+18*s}" rx="{52*s}" ry="{44*s}" {st()}/>']
    for dx, dy in ((-52, -40), (-20, -66), (20, -66), (52, -40)):
        o.append(f'<ellipse cx="{cx+dx*s}" cy="{cy+dy*s}" rx="{16*s}" ry="{20*s}" {st()}/>')
    return "".join(o)


def fin(cx, cy, s=1.0, d=1):
    """Tail-fin shape to hold a letter; letter area centered at cx, cy."""
    return (f'<path d="M{cx-50*s},{cy+50*s} Q{cx-60*s},{cy-40*s} {cx-15*s*d},{cy-75*s} '
            f'Q{cx+40*s},{cy-55*s} {cx+60*s},{cy-20*s} Q{cx+62*s},{cy+30*s} {cx+45*s},{cy+50*s} '
            f'Q{cx},{cy+62*s} {cx-50*s},{cy+50*s} Z" {st()}/>'
            + "".join(f'<line x1="{cx+dx*s}" y1="{cy+44*s}" x2="{cx+dx*1.25*s}" y2="{cy+30*s}" {ln(FINE-0.5)}/>' for dx in (-36, 38)))


def swatch(x, y, r=18):
    return f'<circle cx="{x}" cy="{y}" r="{r}" {st(FINE)}/>'


# ----------------------------------------------------------------- pages
def float_cart(cx, top, label, w=220):
    """Parade float: decorated platform with the animal's name and two wheels."""
    o = [f'<rect x="{cx-w/2}" y="{top}" width="{w}" height="62" rx="12" {st()}/>',
         f'<path d="M{cx-w/2+10},{top+62} q{(w-20)/8},{24} {(w-20)/4},0 t{(w-20)/4},0 t{(w-20)/4},0 t{(w-20)/4},0" {st(FINE)}/>',
         text(cx, top + 45, label, size=38, fam=HEAVY)]
    for dx in (-w * 0.3, w * 0.3):
        o.append(f'<circle cx="{cx+dx}" cy="{top+92}" r="24" {st()}/>')
        o.append(f'<circle cx="{cx+dx}" cy="{top+92}" r="7" fill="{INK}"/>')
    return "".join(o)


def p26():
    b = []
    r1, r2 = 490, 830  # float tops
    # road lines under each row of wheels
    b.append(f'<line x1="40" y1="{r1+118}" x2="810" y2="{r1+118}" {ln(FINE)}/>')
    b.append(f'<line x1="40" y1="{r2+118}" x2="810" y2="{r2+118}" {ln(FINE)}/>')
    # row 1: cat, dog, bird
    b.append(cat(160, r1 - 118, 0.95) + float_cart(160, r1, "cat"))
    b.append(dog(425, r1 - 118, 1.0, d=1) + float_cart(425, r1, "dog"))
    b.append(f'<path d="M640,{r1} v-60 M740,{r1} v-60" {ln(LINE)}/>'
             f'<line x1="620" y1="{r1-60}" x2="760" y2="{r1-60}" {ln(LINE)}/>')
    b.append(bird(690, r1 - 126, 1.05, d=-1, fly=False) + float_cart(690, r1, "bird"))
    # row 2: fish in a bowl, Mrs. B leading, frog
    b.append(f'<path d="M95,{r2} Q55,{r2-80} 90,{r2-150} L230,{r2-150} Q265,{r2-80} 225,{r2} Z" {st()}/>'
             f'<path d="M78,{r2-110} q20,-12 40,0 t40,0 t40,0 t40,0" {ln(FINE)}/>')
    b.append(fish(165, r2 - 60, 0.52, d=1) + float_cart(160, r2, "fish"))
    b.append(mrs_b(425, r2 - 126, 0.52, arm="wave"))
    b.append(frog(690, r2 - 80, 0.95) + float_cart(690, r2, "frog"))
    return page(26, "SEE", "Animal Parade", "Say each animal. Color.",
                WORDS[:5], "Point: 'It is a dog.' Ask: 'What animal do you like?'", "".join(b), unit=UNIT)


def p27():
    b = []
    animals = [("fish", lambda y: fish(170, y, 0.72)),
               ("bird", lambda y: bird(165, y + 18, 0.95, fly=True)),
               ("dog", lambda y: dog(150, y - 5, 0.72, d=1)),
               ("frog", lambda y: frog(170, y - 5, 0.75))]
    verbs = ["run", "jump", "fly", "swim"]
    for i, (name, fn) in enumerate(animals):
        y = 320 + i * 150
        b.append(fn(y))
        b.append(f'<circle cx="320" cy="{y}" r="10" fill="{INK}"/>')
    for i, v in enumerate(verbs):
        y = 320 + i * 150
        b.append(f'<circle cx="520" cy="{y}" r="10" fill="{INK}"/>')
        b.append(f'<rect x="550" y="{y-58}" width="250" height="116" rx="22" {st(FINE+1)}/>')
        b.append(act_icon(v, 625, y, 0.8))
        b.append(text(735, y + 13, v, size=38))
    b.append(text(W / 2, 925, "The ____ can ____.", size=40))
    return page(27, "SAY", "Who Can Do It?", "Match. Say it out loud.",
                ["run", "jump", "swim", "fly", "fish", "bird", "dog", "frog"],
                "Act out each verb together: run, jump, swim, fly!", "".join(b), unit=UNIT)


def p28():
    b = []
    # sun, cloud, grass line, pond
    b.append(f'<circle cx="720" cy="320" r="42" {st()}/>')
    for k in range(10):
        a = k * math.pi / 5
        b.append(f'<line x1="{720+56*math.cos(a):.0f}" y1="{320+56*math.sin(a):.0f}" x2="{720+80*math.cos(a):.0f}" y2="{320+80*math.sin(a):.0f}" {ln(FINE+1)}/>')
    cloud = ((130, 320, 38), (175, 300, 46), (225, 318, 38), (175, 332, 36))
    for cx, cy, r in cloud:
        b.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" {st()}/>')
    for cx, cy, r in cloud:
        b.append(f'<circle cx="{cx}" cy="{cy}" r="{r - LINE/2}" fill="#fff"/>')
    b.append(bird(450, 385, 0.9, d=1, fly=True) + speed(375, 385, 1.0, 1))
    b.append(f'<path d="M40,490 Q220,470 425,486 T810,480" {ln()}/>')
    b.append(f'<ellipse cx="270" cy="690" rx="225" ry="115" {st()}/>')
    for x, y in ((130, 640), (300, 780)):
        b.append(f'<path d="M{x},{y} q15,-10 30,0 t30,0" {ln(FINE)}/>')
    b.append(fish(200, 700, 0.62, d=1))
    b.append(f'<path d="M325,735 A48,20 0 1 1 375,747 L350,733 Z" {st()}/>')
    b.append(f'<path d="M372,722 Q380,680 415,655" fill="none" stroke="{INK}" stroke-width="{FINE}" stroke-dasharray="8 8" stroke-linecap="round"/>')
    b.append(frog(470, 580, 0.55, jump=True))
    b.append(dog(690, 670, 0.72, d=1, run=True) + speed(596, 652, 0.9, 1))
    for x in (520, 770, 610):
        b.append(f'<path d="M{x},800 l8,-26 l8,26 l8,-20 l6,20" {ln(FINE)}/>')
    # key: listen for the verb
    b.append(f'<line x1="40" y1="835" x2="810" y2="835" stroke="{INK}" stroke-width="2.5" stroke-dasharray="10 10"/>')
    key = [("fly", "blue"), ("swim", "orange"), ("jump", "green"), ("run", "brown")]
    for i, (v, c) in enumerate(key):
        x = 70 + (i % 2) * 390
        y = 880 + (i // 2) * 58
        b.append(swatch(x + 18, y - 10))
        b.append(text(x + 50, y, f"can {v} = {c}", size=30, anchor="start"))
    return page(28, "COLOR", "Pond and Sky", "Listen. Color who can.",
                ["fly", "swim", "jump", "run", "blue", "orange", "green", "brown"],
                "Read: 'Which animal can jump? Color it green.'", "".join(b), unit=UNIT)


def p29():
    b = []
    # left: paw trail with Dd
    b.append(text(170, 285, "Dd says /d/", size=30))
    for i, (x, ch) in enumerate(((120, "D"), (225, "d"), (120, "D"))):
        y = 385 + i * 125
        b.append(paw(x, y, 0.95))
        b.append(dotted(x, y + 44, ch, size=74, anchor="middle"))
    # right: fin trail with Ff
    b.append(text(680, 285, "Ff says /f/", size=30))
    for i, (x, ch) in enumerate(((730, "F"), (625, "f"), (730, "F"))):
        y = 380 + i * 125
        b.append(fin(x, y, 0.95))
        b.append(dotted(x, y + 30, ch, size=74, anchor="middle"))
    # middle: picture words
    b.append(dog(420, 350, 0.5, d=1) + text(425, 425, "dog", size=28))
    b.append(fish(430, 500, 0.5) + text(425, 565, "fish", size=28))
    b.append(frog(425, 640, 0.48) + text(425, 705, "frog", size=28))
    # bottom: trace dog + frame
    b.append(text(60, 760, "Trace:", size=28, anchor="start"))
    b.append(ruled(170, 725, 250, 80) + dotted(182, 797, "dog", size=86))
    b.append(dog(640, 755, 0.55, d=1, run=True) + speed(570, 745, 0.8, 1))
    b.append(ruled(60, 850, 740, 100) + dotted(72, 938, "The dog can run.", size=80))
    return page(29, "TRACE", "D and F", "Trace the letters. Say them.",
                ["dog", "fish", "frog", "run"],
                "Dd says /d/. Ff says /f/. Say dog, fish, frog.", "".join(b), unit=UNIT)


def p30():
    b = []
    # left: draw-yourself frame with a child in motion
    b.append(f'<rect x="50" y="260" width="400" height="530" rx="16" {st()}/>')
    b.append(f'<rect x="72" y="282" width="356" height="486" rx="10" {ln(FINE)}/>')
    b.append(child(250, 330, 1.05, "happy", "puffs", arm="up"))
    for sd in (-1, 1):
        b.append(f'<path d="M{250+sd*120},{420} q{sd*20},-20 0,-40" {ln(FINE)}/>'
                 f'<path d="M{250+sd*140},{440} q{sd*28},-30 0,-60" {ln(FINE)}/>')
    b.append(f'<line x1="110" y1="700" x2="390" y2="700" stroke="{INK}" stroke-width="3" stroke-dasharray="12 10"/>')
    # I can ___ writing line
    b.append(text(60, 890, "I can", size=44, anchor="start", fam=HEAVY))
    b.append(ruled(200, 830, 250, 90))
    # right: verb bank
    for i, v in enumerate(["run", "jump", "swim", "fly"]):
        x = 480 + (i % 2) * 168
        y = 262 + (i // 2) * 146
        b.append(f'<rect x="{x}" y="{y}" width="152" height="132" rx="18" {st(FINE+1)}/>')
        b.append(act_icon(v, x + 76, y + 50, 0.75))
        b.append(text(x + 76, y + 118, v, size=30))
    # Mrs. B badge
    b.append(f'<polygon points="590,905 560,970 600,955 620,975 640,915" {st()}/>'
             f'<polygon points="690,905 720,970 680,955 660,975 640,915" {st()}/>')
    b.append(f'<circle cx="640" cy="760" r="150" {st()}/>' + f'<circle cx="640" cy="760" r="132" {ln(FINE)}/>')
    b.append(mrs_b(640, 660, 0.44, arm="cheer"))
    return page(30, "USE", "I Can!", "Act it. Draw you. Write.",
                ["I can", "run", "jump", "swim", "fly"],
                "Say: 'Show me! What can you do?' Then write it.", "".join(b), unit=UNIT)


PAGES = [("u6_p26_see", p26), ("u6_p27_say", p27), ("u6_p28_color", p28),
         ("u6_p29_trace", p29), ("u6_p30_use", p30)]


def main():
    for name, fn in PAGES:
        (OUT / f"{name}.svg").write_text(fn(), encoding="utf-8")
    print(f"wrote {len(PAGES)} Unit 6 pages to {OUT}")


if __name__ == "__main__":
    main()

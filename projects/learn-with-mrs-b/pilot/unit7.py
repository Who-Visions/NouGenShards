"""Learn With Mrs. B, Unit 7: My Community (pp. 31-35) as print-ready line art.

Reuses the pilot generator (build_pilot.py) for page chrome, people and primitives.
Local helpers: adult community helpers with role cues, helper tools, shape-built
buildings (store, school, park) and a simple map.
"""
from build_pilot import *  # noqa: F401,F403
from build_pilot import OUT, W, INK, LINE, FINE, FONT, HEAVY, st, ln, text, hollow, dotted, ruled, star, face, child, mrs_b, page

UNIT = "UNIT 7 · MY COMMUNITY"
WORDS7 = ["doctor", "firefighter", "police officer", "bus driver", "teacher", "store", "park"]
HELPERS = ["doctor", "firefighter", "police officer", "bus driver", "teacher"]


def page7(n, step, title, direction, words, tip, body):
    s = page(n, step, title, direction, words, tip, body, unit=UNIT)
    # the shared footer uses a fixed 19-unit word line; shrink it only when it would overflow the box
    est = len("Words: " + " · ".join(words)) * 19 * 0.56
    if est > 735:
        size = max(14, int(19 * 735 / est))
        s = s.replace('font-size="19" font-weight="700" text-anchor="start" fill="#111">Words:',
                      f'font-size="{size}" font-weight="700" text-anchor="start" fill="#111">Words:')
    return s


def tube(x1, y1, x2, y2, w):
    """Outlined tube (sleeve, hose): thick ink stroke with a white core."""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{INK}" stroke-width="{w+LINE}" stroke-linecap="round"/>'
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#fff" stroke-width="{w-LINE+2}" stroke-linecap="round"/>')


def pill(cx, y, w, h, label, size=22):
    out = f'<rect x="{cx-w/2}" y="{y}" width="{w}" height="{h}" rx="{h/2}" {st(FINE)}/>'
    lines = label.split("\n")
    if len(lines) == 1:
        out += text(cx, y + h / 2 + size * 0.36, label, size=size)
    else:
        sz = size - 3
        out += text(cx, y + h / 2 - 3, lines[0], size=sz) + text(cx, y + h / 2 + sz - 1, lines[1], size=sz)
    return out


# ----------------------------------------------------------------- hats
def helmet(cx, hy, r):
    """Firefighter helmet sitting on a head of radius r centered at hy."""
    by = hy - r * 0.42
    return (f'<path d="M{cx-r*1.4},{by} Q{cx-r*1.35},{by+r*0.3} {cx-r*0.9},{by+r*0.22} L{cx+r*0.9},{by+r*0.22} '
            f'Q{cx+r*1.35},{by+r*0.3} {cx+r*1.4},{by} Z" {st(FINE+1)}/>'
            f'<path d="M{cx-r*1.0},{by+r*0.05} Q{cx-r*1.05},{hy-r*1.5} {cx},{hy-r*1.5} Q{cx+r*1.05},{hy-r*1.5} {cx+r*1.0},{by+r*0.05} Z" {st()}/>'
            f'<path d="M{cx-r*0.24},{hy-r*1.1} h{r*0.48} v{r*0.42} q0,{r*0.16} {-r*0.24},{r*0.24} q{-r*0.24},{-r*0.08} {-r*0.24},{-r*0.24} Z" {st(FINE)}/>')


def police_cap(cx, hy, r):
    return (f'<path d="M{cx-r*0.92},{hy-r*0.42} Q{cx},{hy-r*0.02} {cx+r*0.92},{hy-r*0.42} Z" {st(FINE+1)}/>'
            f'<path d="M{cx-r*0.95},{hy-r*0.72} L{cx-r*1.25},{hy-r*1.28} Q{cx},{hy-r*1.45} {cx+r*1.25},{hy-r*1.28} L{cx+r*0.95},{hy-r*0.72} Z" {st()}/>'
            f'<rect x="{cx-r*0.95}" y="{hy-r*0.74}" width="{r*1.9}" height="{r*0.34}" {st(FINE+1)}/>'
            + star(cx, hy - r * 0.98, r * 0.24, w=FINE))


def bus_cap(cx, hy, r):
    return (f'<path d="M{cx-r*0.95},{hy-r*0.45} Q{cx},{hy-r*0.08} {cx+r*0.95},{hy-r*0.45} Z" {st(FINE+1)}/>'
            f'<path d="M{cx-r*0.98},{hy-r*0.5} Q{cx-r*1.08},{hy-r*1.35} {cx},{hy-r*1.35} Q{cx+r*1.08},{hy-r*1.35} {cx+r*0.98},{hy-r*0.5} Z" {st()}/>'
            f'<line x1="{cx-r*0.98}" y1="{hy-r*0.72}" x2="{cx+r*0.98}" y2="{hy-r*0.72}" {ln(FINE)}/>'
            f'<circle cx="{cx}" cy="{hy-r*0.97}" r="{r*0.14}" {st(FINE)}/>')


# ----------------------------------------------------------------- adult helpers
def adult(cx, top, s=1.0, role="doctor", hair="short", beard=False):
    """Community helper; `top` is the top of the head (hats sit above it). ~347*s tall."""
    r = 40 * s
    hy = top + r
    bt, bh, bw = hy + r * 0.95, 150 * s, 110 * s
    o = []
    for dx in (-0.22, 0.22):
        x = cx + dx * bw
        o.append(f'<rect x="{x-15*s}" y="{bt+bh-10*s}" width="{30*s}" height="{105*s}" rx="{8*s}" {st()}/>')
        o.append(f'<ellipse cx="{x+(9*s if dx>0 else -9*s)}" cy="{bt+bh+100*s}" rx="{27*s}" ry="{13*s}" {st()}/>')
    sh_y = bt + 24 * s
    arms, hands = [], []
    for side in (-1, 1):
        sx = cx + side * bw * 0.44
        if role == "bus driver":
            ex, ey = cx + side * 34 * s, bt + 72 * s
        else:
            ex, ey = sx + side * 16 * s, sh_y + 100 * s
        arms.append(tube(sx, sh_y, ex, ey, 30 * s))
        hands.append(f'<circle cx="{ex}" cy="{ey}" r="{14*s}" {st()}/>')
    if role != "bus driver":
        o += arms + hands
    bottom = bt + bh + (48 * s if role == "doctor" else 0)
    flare = 8 * s if role == "doctor" else 0
    o.append(f'<path d="M{cx-bw/2},{bt+20*s} Q{cx-bw/2},{bt} {cx-bw/2+22*s},{bt} L{cx+bw/2-22*s},{bt} '
             f'Q{cx+bw/2},{bt} {cx+bw/2},{bt+20*s} L{cx+bw/2+flare},{bottom} L{cx-bw/2-flare},{bottom} Z" {st()}/>')
    if role == "doctor":
        o.append(f'<path d="M{cx-24*s},{bt} L{cx},{bt+72*s} L{cx+24*s},{bt}" {ln(FINE)}/>')
        o.append(f'<line x1="{cx}" y1="{bt+72*s}" x2="{cx}" y2="{bottom}" {ln(FINE)}/>')
        o.append(f'<rect x="{cx-44*s}" y="{bt+92*s}" width="{26*s}" height="{24*s}" {st(FINE)}/>')
        o.append(f'<path d="M{cx-20*s},{bt+3*s} Q{cx-28*s},{bt+56*s} {cx},{bt+60*s} Q{cx+28*s},{bt+56*s} {cx+20*s},{bt+3*s}" {ln(FINE+0.5)}/>')
        o.append(f'<path d="M{cx},{bt+60*s} Q{cx+6*s},{bt+84*s} {cx+24*s},{bt+88*s}" {ln(FINE+0.5)}/>')
        o.append(f'<circle cx="{cx+32*s}" cy="{bt+90*s}" r="{10*s}" {st(FINE)}/>')
    elif role == "firefighter":
        o.append(f'<line x1="{cx}" y1="{bt+6*s}" x2="{cx}" y2="{bt+bh}" {ln(FINE)}/>')
        for yy in (0.52, 0.74):
            o.append(f'<rect x="{cx-bw/2}" y="{bt+bh*yy}" width="{bw}" height="{13*s}" {st(FINE)}/>')
    elif role == "police officer":
        o.append(f'<path d="M{cx-26*s},{bt} L{cx-6*s},{bt+26*s} L{cx},{bt+6*s} L{cx+6*s},{bt+26*s} L{cx+26*s},{bt}" {ln(FINE)}/>')
        o.append(f'<line x1="{cx}" y1="{bt+26*s}" x2="{cx}" y2="{bt+bh-20*s}" {ln(FINE)}/>')
        o.append(star(cx - 28 * s, bt + 52 * s, 17 * s, w=FINE))
        o.append(f'<rect x="{cx+14*s}" y="{bt+42*s}" width="{26*s}" height="{22*s}" {st(FINE)}/>')
        o.append(f'<rect x="{cx-bw/2}" y="{bt+bh-22*s}" width="{bw}" height="{14*s}" {st(FINE)}/>')
    elif role == "bus driver":
        o.append(f'<path d="M{cx-22*s},{bt} L{cx},{bt+22*s} L{cx+22*s},{bt}" {ln(FINE)}/>')
        wy = bt + 78 * s
        o += arms
        o.append(f'<circle cx="{cx}" cy="{wy}" r="{38*s}" {st()}/>')
        o.append(f'<circle cx="{cx}" cy="{wy}" r="{12*s}" {st(FINE)}/>')
        for x2, y2 in ((cx - 36 * s, wy), (cx + 36 * s, wy), (cx, wy + 36 * s)):
            o.append(f'<line x1="{cx}" y1="{wy}" x2="{x2}" y2="{y2}" {ln(FINE)}/>')
        o.append(f'<circle cx="{cx}" cy="{wy}" r="{12*s}" {st(FINE)}/>')
        o += hands
    o.append(f'<rect x="{cx-12*s}" y="{hy+r*0.8}" width="{24*s}" height="{r*0.3}" {st(FINE)}/>')
    o.append(face(cx, hy, r, "happy", hair))
    if beard:
        o.append(f'<path d="M{cx-r*0.92},{hy+r*0.12} Q{cx-r*0.88},{hy+r*1.12} {cx},{hy+r*1.14} Q{cx+r*0.88},{hy+r*1.12} {cx+r*0.92},{hy+r*0.12} '
                 f'Q{cx+r*0.62},{hy+r*0.86} {cx},{hy+r*0.86} Q{cx-r*0.62},{hy+r*0.86} {cx-r*0.92},{hy+r*0.12} Z" {st(FINE)}/>')
    if role == "firefighter":
        o.append(helmet(cx, hy, r))
    elif role == "police officer":
        o.append(police_cap(cx, hy, r))
    elif role == "bus driver":
        o.append(bus_cap(cx, hy, r))
    return "".join(o)


CAST = {  # role -> (hair, beard): mixed gender, varied hair
    "doctor": ("puffs", False),
    "firefighter": ("bob", False),
    "police officer": ("short", False),
    "bus driver": ("curly", True),
}


def helper(role, cx, top, s):
    hair, beard = CAST[role]
    return adult(cx, top, s, role, hair, beard)


# ----------------------------------------------------------------- tools / icons
def stethoscope(cx, cy, s=1.0):
    return (f'<path d="M{cx-24*s},{cy-40*s} Q{cx-30*s},{cy+6*s} {cx},{cy+8*s} Q{cx+30*s},{cy+6*s} {cx+24*s},{cy-40*s}" {ln(LINE*s+1)}/>'
            f'<path d="M{cx},{cy+8*s} Q{cx+6*s},{cy+32*s} {cx+30*s},{cy+30*s}" {ln(LINE*s+1)}/>'
            f'<circle cx="{cx+42*s}" cy="{cy+28*s}" r="{14*s}" {st()}/>'
            f'<circle cx="{cx+42*s}" cy="{cy+28*s}" r="{5*s}" {st(FINE)}/>'
            f'<circle cx="{cx-24*s}" cy="{cy-42*s}" r="{6*s}" {st(FINE)}/>'
            f'<circle cx="{cx+24*s}" cy="{cy-42*s}" r="{6*s}" {st(FINE)}/>')


def hose(cx, cy, s=1.0):
    ccx = cx - 18 * s
    return (f'<circle cx="{ccx}" cy="{cy}" r="{32*s}" fill="none" stroke="{INK}" stroke-width="{16*s+LINE}"/>'
            f'<circle cx="{ccx}" cy="{cy}" r="{32*s}" fill="none" stroke="#fff" stroke-width="{16*s-LINE+2}"/>'
            f'<circle cx="{ccx}" cy="{cy}" r="{12*s}" {st(FINE)}/>'
            + tube(ccx + 30 * s, cy + 14 * s, cx + 36 * s, cy - 14 * s, 16 * s)
            + f'<path d="M{cx+30*s},{cy-24*s} L{cx+58*s},{cy-44*s} L{cx+66*s},{cy-30*s} L{cx+44*s},{cy-6*s} Z" {st()}/>')


def bus(cx, cy, s=1.0):
    o = [f'<rect x="{cx-62*s}" y="{cy-32*s}" width="{124*s}" height="{58*s}" rx="{10*s}" {st()}/>']
    for i in range(3):
        x = cx - 52 * s + i * 28 * s
        o.append(f'<rect x="{x}" y="{cy-22*s}" width="{22*s}" height="{18*s}" rx="{3*s}" {st(FINE)}/>')
    o.append(f'<rect x="{cx+32*s}" y="{cy-22*s}" width="{22*s}" height="{40*s}" rx="{3*s}" {st(FINE)}/>')
    for x in (cx - 34 * s, cx + 14 * s):
        o.append(f'<circle cx="{x}" cy="{cy+26*s}" r="{13*s}" {st()}/>')
        o.append(f'<circle cx="{x}" cy="{cy+26*s}" r="{4*s}" fill="{INK}"/>')
    return "".join(o)


def police_badge(cx, cy, s=1.0):
    return star(cx, cy, 36 * s) + f'<circle cx="{cx}" cy="{cy+2*s}" r="{9*s}" {st(FINE)}/>'


def book(cx, cy, s=1.0):
    o = []
    for side in (-1, 1):
        o.append(f'<path d="M{cx},{cy-24*s} Q{cx+side*30*s},{cy-38*s} {cx+side*58*s},{cy-28*s} L{cx+side*58*s},{cy+30*s} '
                 f'Q{cx+side*30*s},{cy+20*s} {cx},{cy+34*s} Z" {st()}/>')
        for k in range(3):
            y = cy - 12 * s + k * 14 * s
            o.append(f'<line x1="{cx+side*12*s}" y1="{y}" x2="{cx+side*44*s}" y2="{y-4*s}" {ln(FINE-1)}/>')
    return "".join(o)


def helmet_icon(cx, cy, s=1.0):
    r = 34 * s
    return helmet(cx, cy + r * 0.9, r)


def police_cap_icon(cx, cy, s=1.0):
    r = 34 * s
    return police_cap(cx, cy + r * 0.9, r)


# ----------------------------------------------------------------- buildings (220 wide, 240 tall; origin = bottom center)
def store(x, g):
    o = [f'<rect x="{x-80}" y="{g-240}" width="160" height="40" rx="8" {st()}/>', text(x, g - 210, "store", size=28),
         f'<rect x="{x-100}" y="{g-192}" width="200" height="192" {st()}/>',
         f'<rect x="{x-108}" y="{g-192}" width="216" height="30" {st()}/>']
    for i in range(6):
        cx = x - 90 + i * 36
        o.append(f'<path d="M{cx-18},{g-162} a18,16 0 0 0 36,0 Z" {st(FINE+1)}/>')
    o.append(f'<rect x="{x-24}" y="{g-92}" width="48" height="92" {st()}/>')
    o.append(f'<circle cx="{x+14}" cy="{g-46}" r="4" fill="{INK}"/>')
    for wx in (x - 88, x + 40):
        o.append(f'<rect x="{wx}" y="{g-126}" width="48" height="50" {st(FINE+1)}/>')
        o.append(f'<line x1="{wx+24}" y1="{g-126}" x2="{wx+24}" y2="{g-76}" {ln(FINE)}/>')
    o.append(f'<circle cx="{x-64}" cy="{g-94}" r="11" {st(FINE)}/>')
    o.append(f'<circle cx="{x+64}" cy="{g-94}" r="11" {st(FINE)}/>')
    return "".join(o)


def school(x, g):
    o = [f'<polygon points="{x-116},{g-150} {x},{g-242} {x+116},{g-150}" {st()}/>',
         f'<circle cx="{x}" cy="{g-186}" r="20" {st(FINE+1)}/>',
         f'<line x1="{x}" y1="{g-186}" x2="{x}" y2="{g-200}" {ln(FINE)}/>',
         f'<line x1="{x}" y1="{g-186}" x2="{x+10}" y2="{g-180}" {ln(FINE)}/>',
         f'<rect x="{x-100}" y="{g-150}" width="200" height="150" {st()}/>',
         f'<rect x="{x-62}" y="{g-140}" width="124" height="38" rx="6" {st(FINE+1)}/>', text(x, g - 112, "school", size=26),
         f'<rect x="{x-26}" y="{g-84}" width="52" height="84" {st()}/>',
         f'<line x1="{x}" y1="{g-84}" x2="{x}" y2="{g}" {ln(FINE)}/>']
    for wx in (x - 88, x + 44):
        o.append(f'<rect x="{wx}" y="{g-88}" width="44" height="44" {st(FINE+1)}/>')
        o.append(f'<line x1="{wx}" y1="{g-66}" x2="{wx+44}" y2="{g-66}" {ln(FINE)}/>')
    return "".join(o)


def tree(cx, g, trunk_h=110, k=1.0):
    canopy = ((cx, g - trunk_h - 50 * k, 58 * k), (cx - 44 * k, g - trunk_h - 12 * k, 38 * k),
              (cx + 44 * k, g - trunk_h - 12 * k, 38 * k), (cx, g - trunk_h - 96 * k, 36 * k))
    o = [f'<rect x="{cx-15*k}" y="{g-trunk_h}" width="{30*k}" height="{trunk_h}" rx="6" {st()}/>']
    o += [f'<circle cx="{a}" cy="{b}" r="{c}" {st()}/>' for a, b, c in canopy]
    o += [f'<circle cx="{a}" cy="{b}" r="{c-LINE/2}" fill="#fff"/>' for a, b, c in canopy]
    return "".join(o)


def park(x, g):
    o = [tree(x - 40, g, 100, 0.95),
         f'<rect x="{x+68}" y="{g-128}" width="10" height="128" {st(FINE)}/>',
         f'<rect x="{x+30}" y="{g-172}" width="86" height="44" rx="6" {st()}/>', text(x + 73, g - 140, "park", size=26)]
    for fx in (x - 98, x + 100):
        o.append(f'<line x1="{fx}" y1="{g}" x2="{fx}" y2="{g-26}" {ln(FINE)}/>')
        o.append(f'<circle cx="{fx}" cy="{g-34}" r="10" {st(FINE)}/>')
    return "".join(o)


# ----------------------------------------------------------------- pages
def p31():
    g = 492
    b = [store(152, g), school(425, g), park(688, g), f'<line x1="40" y1="{g}" x2="810" y2="{g}" {ln()}/>',
         f'<line x1="40" y1="882" x2="810" y2="882" {ln()}/>']
    xs = [115, 270, 425, 580, 735]
    s, feet = 0.85, 880
    for role, x in zip(HELPERS[:4], xs):
        b.append(helper(role, x, feet - 347 * s, s))
    mb = 0.58
    b.append(mrs_b(xs[4], feet - 485.5 * mb, mb, arm="down"))
    labels = ["doctor", "firefighter", "police\nofficer", "bus driver", "teacher"]
    for x, lab in zip(xs, labels):
        b.append(pill(x, 896, 146, 58, lab, size=22))
    return page7(31, "SEE", "Our Neighborhood", "Color. Say: This is a ___.",
                 WORDS7, "Who helps us in our town?", "".join(b))


def portrait(i, role, x0, y0, w, h):
    cid = f"u7pp{i}"
    cx, cy = x0 + w / 2, y0 + h / 2
    if role == "teacher":
        s = 0.45
        fig = mrs_b(cx, cy - 58 * 1.25 * s + 4, s, arm="down")
    else:
        s = 0.72
        fig = helper(role, cx, cy - 8 - 40 * s * 2 + 40 * s, s)
    return (f'<clipPath id="{cid}"><rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="14"/></clipPath>'
            f'<g clip-path="url(#{cid})">{fig}</g>'
            f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="14" {ln(FINE+1)}/>')


def p32():
    b = []
    tools = [("bus", bus, 0.78), ("book", book, 0.72), ("stethoscope", stethoscope, 0.8),
             ("badge", police_badge, 0.85), ("hose", hose, 0.72)]
    for i, role in enumerate(HELPERS):
        y = 312 + i * 128
        b.append(portrait(i, role, 60, y - 56, 116, 112))
        size = min(26, 205 / (len(role) * 0.58))
        b.append(text(192, y + 9, role, size=round(size), anchor="start"))
        b.append(f'<circle cx="432" cy="{y}" r="9" fill="{INK}"/>')
        name, fn, sc = tools[i]
        b.append(f'<circle cx="572" cy="{y}" r="9" fill="{INK}"/>')
        b.append(f'<rect x="600" y="{y-56}" width="190" height="112" rx="16" {st(FINE+1)}/>')
        b.append(fn(695, y - 14, sc))
        b.append(text(695, y + 46, name, size=20))
    b.append(text(W / 2, 948, "A ________ helps us.", size=34))
    return page7(32, "SAY", "Helpers and Tools", "Match. Say: A ___ helps us.",
                 HELPERS, "How does a firefighter help?", "".join(b))


def p33():
    b = []
    paths = ["M355,822 H230 Q160,822 160,752 V492", "M425,700 V492", "M495,822 H620 Q690,822 690,752 V492"]
    pw = 70
    # butt caps: the park path ends flat on the park's ground line; building paths end under the buildings
    b += [f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{pw+LINE}" stroke-linejoin="round"/>' for d in paths]
    b += [f'<path d="{d}" fill="none" stroke="#fff" stroke-width="{pw-LINE}" stroke-linejoin="round"/>' for d in paths]
    # park drawn so the gap between tree and sign post sits over the path (local x +22)
    b += [store(160, 492), park(403, 492), school(690, 492),
          f'<line x1="285" y1="492" x2="385" y2="492" {ln()}/>', f'<line x1="465" y1="492" x2="535" y2="492" {ln()}/>']
    b.append(tree(292, 772, 70, 0.72))
    b.append(tree(558, 772, 70, 0.72))
    # home (start)
    b.append(f'<rect x="355" y="742" width="140" height="158" {st()}/>')
    b.append(f'<polygon points="335,746 425,660 515,746" {st()}/>')
    b.append(f'<rect x="372" y="832" width="42" height="68" {st()}/>')
    b.append(f'<circle cx="404" cy="868" r="4" fill="{INK}"/>')
    b.append(f'<rect x="430" y="768" width="48" height="46" {st(FINE+1)}/>')
    b.append(f'<line x1="454" y1="768" x2="454" y2="814" {ln(FINE)}/>')
    b.append(text(425, 728, "home", size=22))
    b.append(text(W / 2, 950, "I go to the ________.", size=34))
    return page7(33, "COLOR", "Where Do I Go?", "Color a path. Say it.",
                 ["store", "park", "school"], "Where do you go on Saturday?", "".join(b))


def p34():
    b = []
    icons = [(stethoscope, 0.62, 0), (helmet_icon, 0.9, 4), (police_badge, 0.72, 0), (bus, 0.55, 0), (book, 0.55, 0)]
    labels = ["doctor", "firefighter", "police\nofficer", "bus driver", "teacher"]
    for i, (fn, sc, dy) in enumerate(icons):
        x = 115 + i * 155
        b.append(f'<circle cx="{x}" cy="302" r="52" {st()}/>')
        b.append(f'<circle cx="{x}" cy="302" r="43" {ln(FINE-1)}/>')
        b.append(fn(x - (6 if fn is stethoscope else 0), 302 + dy, sc))
        lines = labels[i].split("\n")
        if len(lines) == 1:
            b.append(text(x, 384, lines[0], size=21))
        else:
            b.append(text(x, 378, lines[0], size=19) + text(x, 399, lines[1], size=19))
    b.append(ruled(60, 432, 730, 110) + dotted(80, 538, "A teacher", size=112))
    b.append(ruled(60, 570, 730, 110) + dotted(80, 676, "helps us.", size=112))
    b.append(text(60, 730, "Now you: pick a helper.", size=26, anchor="start"))
    b.append(ruled(60, 748, 730, 90) + dotted(78, 835, "A", size=92))
    b.append(ruled(60, 866, 730, 90) + dotted(78, 953, "helps us.", size=92))
    return page7(34, "TRACE", "Helper Words", "Trace. Then write your own.",
                 HELPERS, "Read your sentence to me.", "".join(b))


def p35():
    b = []
    # big uniform outline to personalize
    for x in (150, 250):
        b.append(f'<rect x="{x}" y="730" width="80" height="170" rx="12" {st()}/>')
    b.append(f'<ellipse cx="180" cy="908" rx="54" ry="22" {st()}/>')
    b.append(f'<ellipse cx="300" cy="908" rx="54" ry="22" {st()}/>')
    b.append(tube(138, 528, 100, 730, 62) + f'<circle cx="100" cy="738" r="28" {st()}/>')
    b.append(tube(342, 528, 380, 730, 62) + f'<circle cx="380" cy="738" r="28" {st()}/>')
    b.append(f'<path d="M120,540 Q120,490 170,490 L310,490 Q360,490 360,540 L352,748 L128,748 Z" {st()}/>')
    b.append(f'<path d="M204,490 L240,566 L276,490" {ln(FINE+0.5)}/>')
    b.append(f'<line x1="240" y1="566" x2="240" y2="748" {ln(FINE)}/>')
    for i in range(4):
        b.append(f'<circle cx="254" cy="{598+i*38}" r="6" {st(FINE-1)}/>')
    b.append(f'<rect x="282" y="604" width="52" height="46" rx="4" {st(FINE)}/>')
    b.append(f'<rect x="146" y="604" width="70" height="46" rx="8" {st(FINE)}/>')
    b.append(f'<rect x="226" y="458" width="28" height="36" {st(FINE)}/>')
    b.append(f'<ellipse cx="240" cy="368" rx="82" ry="96" {st()}/>')
    b.append(text(240, 362, "Draw", size=24, weight="400", fill="#999"))
    b.append(text(240, 392, "your face", size=24, weight="400", fill="#999"))
    # sentence
    b.append(text(460, 318, "I want to be a", size=34, anchor="start"))
    b.append(ruled(460, 340, 345, 86))
    # helper ideas
    b.append(text(460, 476, "Ideas:", size=24, anchor="start"))
    tiles = [(helmet_icon, 0.95, "firefighter", 6), (police_cap_icon, 0.95, "police officer", 6),
             (stethoscope, 0.72, "doctor", 0), (bus, 0.62, "bus driver", 0)]
    for i, (fn, sc, lab, dy) in enumerate(tiles):
        x0 = 460 + (i % 2) * 176
        y0 = 492 + (i // 2) * 146
        b.append(f'<rect x="{x0}" y="{y0}" width="168" height="136" rx="16" {st(FINE+1)}/>')
        b.append(fn(x0 + 84 - (6 if fn is stethoscope else 0), y0 + 56 + dy, sc))
        b.append(text(x0 + 84, y0 + 122, lab, size=19))
    # Mrs. B badge
    bx, by = 530, 866
    for side in (-1, 1):
        b.append(f'<polygon points="{bx+side*14},{by+40} {bx+side*46},{by+40} {bx+side*40},{by+100} {bx+side*28},{by+84} {bx+side*14},{by+104}" {st(FINE+1)}/>')
    b.append(f'<circle cx="{bx}" cy="{by}" r="62" {st()}/>')
    b.append(f'<circle cx="{bx}" cy="{by}" r="52" {ln(FINE-1)}/>')
    b.append(star(bx, by - 10, 30, w=FINE + 1))
    b.append(text(bx, by + 38, "Mrs. B", size=17))
    b.append(text(612, 858, "Great job,", size=28, anchor="start", fam=HEAVY))
    b.append(text(612, 894, "helper!", size=28, anchor="start", fam=HEAVY))
    return page7(35, "USE", "When I Grow Up", "Draw you. Write your job.",
                 WORDS7[:5], "Who do you want to be? Why?", "".join(b))


PAGES = [("u7_p31_see", p31), ("u7_p32_say", p32), ("u7_p33_color", p33),
         ("u7_p34_trace", p34), ("u7_p35_use", p35)]


def main():
    for name, fn in PAGES:
        (OUT / f"{name}.svg").write_text(fn(), encoding="utf-8")
    print(f"wrote {len(PAGES)} pages to {OUT}")


if __name__ == "__main__":
    main()

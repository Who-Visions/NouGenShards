"""Learn With Mrs. B, Unit 4: Colors & Shapes (pp. 16-20) as print-ready line art.

Reuses the pilot generator (build_pilot.py) for primitives, people and page chrome.
Pages are black line art: color words sit beside outlined swatches, never real fills.
"""
import math

from build_pilot import *  # noqa: F401,F403  (W, H, INK, LINE, FINE, st, ln, text, ...)

UNIT = "UNIT 4 · COLORS & SHAPES"
COLORS = ["red", "blue", "yellow", "green"]
SHAPES = ["circle", "square", "triangle", "star"]
WORDS = COLORS + SHAPES
GRAY = "#9a9a9a"


# ----------------------------------------------------------------- local helpers
def dash(w=5):
    """Gray dotted outline for tracing shapes."""
    return (f'fill="none" stroke="{GRAY}" stroke-width="{w}" stroke-dasharray="1 12" '
            f'stroke-linecap="round" stroke-linejoin="round"')


def star_pts(cx, cy, r, inner=0.45):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * inner
        a = math.pi / 2 + i * math.pi / 5
        pts.append(f"{cx + rr*math.cos(a):.1f},{cy - rr*math.sin(a):.1f}")
    return " ".join(pts)


def tri_pts(cx, cy, s):
    """Equilateral-ish triangle of side s centered on its box."""
    h = s * 0.87
    return f"{cx},{cy-h/2:.1f} {cx+s/2:.1f},{cy+h/2:.1f} {cx-s/2:.1f},{cy+h/2:.1f}"


def shape(kind, cx, cy, size, style=None):
    """Plain outlined shape; size is the bounding width."""
    style = style or st()
    if kind == "circle":
        return f'<circle cx="{cx}" cy="{cy}" r="{size/2}" {style}/>'
    if kind == "square":
        return f'<rect x="{cx-size/2}" y="{cy-size/2}" width="{size}" height="{size}" rx="{size*0.06:.1f}" {style}/>'
    if kind == "triangle":
        return f'<polygon points="{tri_pts(cx, cy, size)}" {style}/>'
    return f'<polygon points="{star_pts(cx, cy, size/2)}" {style}/>'


def swatch(x, y, word, size=28, r=16):
    """Outlined swatch circle with the color word beside it. (x, y) is the swatch center."""
    return (f'<circle cx="{x}" cy="{y}" r="{r}" {st(FINE+0.5)}/>'
            + text(x + r + 12, y + size * 0.36, word, size=size, anchor="start"))


def smile(cx, cy, r):
    """Friendly face features (no head outline) for shape characters."""
    ex, er = r * 0.38, max(r * 0.1, 4)
    return (f'<circle cx="{cx-ex}" cy="{cy-r*0.15}" r="{er}" fill="{INK}"/>'
            f'<circle cx="{cx+ex}" cy="{cy-r*0.15}" r="{er}" fill="{INK}"/>'
            f'<path d="M{cx-r*0.4},{cy+r*0.15} Q{cx},{cy+r*0.6} {cx+r*0.4},{cy+r*0.15}" {ln(FINE+0.5)}/>')


def limbs(cx, top, bottom, half, arm_y):
    """Stick arms and legs with round hands/feet for a shape character."""
    out = []
    for s in (-1, 1):
        hx, hy = cx + s * (half + 20), arm_y - 22
        out.append(f'<line x1="{cx+s*half}" y1="{arm_y}" x2="{hx}" y2="{hy}" {ln(LINE)}/>')
        out.append(f'<circle cx="{hx}" cy="{hy}" r="9" {st(FINE)}/>')
        lx = cx + s * 24
        out.append(f'<line x1="{lx}" y1="{bottom}" x2="{lx}" y2="{bottom+34}" {ln(LINE)}/>')
        out.append(f'<ellipse cx="{lx+s*8}" cy="{bottom+40}" rx="18" ry="9" {st(FINE)}/>')
    return "".join(out)


def shape_friend(kind, cx, cy, size=140):
    """Smiling shape character: limbs behind, shape body, face on top."""
    half = size / 2
    if kind == "triangle":
        h = size * 0.87
        top, bottom = cy - h / 2, cy + h / 2
        arm_y, fx, fy, fr, arm_half = cy + h * 0.1, cx, cy + h * 0.12, size * 0.2, size * 0.33
    elif kind == "star":
        top, bottom = cy - half, cy + half * 0.81
        arm_y, fx, fy, fr, arm_half = cy - half * 0.31, cx, cy + 2, size * 0.17, half
        bottom = cy + half * 0.55
    else:
        top, bottom = cy - half, cy + half
        arm_y, fx, fy, fr, arm_half = cy + 4, cx, cy, size * 0.3, half
    return limbs(cx, top, bottom, arm_half - 4, arm_y) + shape(kind, cx, cy, size) + smile(fx, fy, fr)


def paint_pot(cx, top, word, w=150):
    """Paint pot with an open paint surface and a label band carrying the color word."""
    h = 170
    rim_y = top + 22
    out = [
        # jar body
        f'<path d="M{cx-w/2},{rim_y} L{cx-w/2+8},{top+h-18} Q{cx-w/2+10},{top+h} {cx-w/2+30},{top+h} '
        f'L{cx+w/2-30},{top+h} Q{cx+w/2-10},{top+h} {cx+w/2-8},{top+h-18} L{cx+w/2},{rim_y} Z" {st()}/>',
        # rim + paint surface with a drip
        f'<ellipse cx="{cx}" cy="{rim_y}" rx="{w/2+6}" ry="20" {st()}/>',
        f'<ellipse cx="{cx}" cy="{rim_y}" rx="{w/2-12}" ry="11" {ln(FINE)}/>',
        f'<path d="M{cx+w/2-2},{rim_y+8} q10,22 0,40 q-10,-18 0,-40 Z" {st(FINE)}/>',
        # label band
        f'<rect x="{cx-w/2+14}" y="{top+78}" width="{w-28}" height="52" rx="10" {st(FINE)}/>',
        text(cx, top + 115, word, size=30),
    ]
    return "".join(out)


def bubble(x, y, w, h, tail="left"):
    tx = x + 40 if tail == "left" else x + w - 70
    return (f'<path d="M{x+18},{y} h{w-36} a18,18 0 0 1 18,18 v{h-36} a18,18 0 0 1 -18,18 '
            f'h{-(x+w-18-(tx+30))} l-20,26 v-26 h{-(tx+10-(x+18))} a18,18 0 0 1 -18,-18 v{-(h-36)} '
            f'a18,18 0 0 1 18,-18 Z" {st(FINE+1)}/>')


# ----------------------------------------------------------------- pages
def p16():
    b = []
    for i, c in enumerate(COLORS):
        b.append(paint_pot(140 + i * 190, 265, c))
    b.append(f'<line x1="60" y1="480" x2="790" y2="480" stroke="{INK}" stroke-width="2.5" stroke-dasharray="12 10"/>')
    for i, k in enumerate(SHAPES):
        cx = 140 + i * 190
        b.append(shape_friend(k, cx, 625, 124))
        b.append(text(cx, 790, k, size=32))
    b.append(bubble(170, 830, 510, 80) + text(425, 884, "It is red. It is a circle.", size=32))
    return page(16, "SEE", "Color & Shape Friends", "Color each pot. Color the friends.",
                WORDS, "Ask: 'What color is it?' Answer: 'It is blue.'", "".join(b), unit=UNIT)


def obj(kind, cx, cy):
    """Six simple outline objects for p17."""
    if kind == "ball":
        return (f'<circle cx="{cx}" cy="{cy}" r="44" {st()}/>'
                f'<path d="M{cx-44},{cy} Q{cx},{cy-22} {cx+44},{cy}" {ln(FINE)}/>'
                f'<path d="M{cx},{cy-44} Q{cx-24},{cy} {cx},{cy+44}" {ln(FINE)}/>')
    if kind == "clock":
        return (f'<circle cx="{cx}" cy="{cy}" r="44" {st()}/>'
                + "".join(f'<circle cx="{cx+34*math.cos(a):.1f}" cy="{cy+34*math.sin(a):.1f}" r="3" fill="{INK}"/>'
                          for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2))
                + f'<line x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy-26}" {ln(FINE+1)}/>'
                  f'<line x1="{cx}" y1="{cy}" x2="{cx+18}" y2="{cy+8}" {ln(FINE+1)}/>')
    if kind == "window":
        return (f'<rect x="{cx-44}" y="{cy-44}" width="88" height="88" rx="4" {st()}/>'
                f'<line x1="{cx}" y1="{cy-44}" x2="{cx}" y2="{cy+44}" {ln(FINE+1)}/>'
                f'<line x1="{cx-44}" y1="{cy}" x2="{cx+44}" y2="{cy}" {ln(FINE+1)}/>')
    if kind == "pizza":
        return (f'<path d="M{cx-48},{cy-38} Q{cx},{cy-54} {cx+48},{cy-38} L{cx},{cy+46} Z" {st()}/>'
                f'<path d="M{cx-44},{cy-30} Q{cx},{cy-44} {cx+44},{cy-30}" {ln(FINE)}/>'
                f'<circle cx="{cx-12}" cy="{cy-12}" r="8" {st(FINE)}/><circle cx="{cx+14}" cy="{cy-8}" r="7" {st(FINE)}/>'
                f'<circle cx="{cx}" cy="{cy+14}" r="7" {st(FINE)}/>')
    if kind == "flag":
        return (f'<line x1="{cx-40}" y1="{cy-46}" x2="{cx-40}" y2="{cy+48}" {ln(LINE+1)}/>'
                f'<polygon points="{cx-40},{cy-44} {cx+48},{cy-18} {cx-40},{cy+8}" {st()}/>')
    return f'<polygon points="{star_pts(cx, cy, 48)}" {st()}/>'


def p17():
    # one shape per object, so every match has exactly one right answer
    left = ["ball", "window", "pizza", "star"]
    right = [("blue", "square"), ("green", "star"), ("red", "circle"), ("yellow", "triangle")]
    rows = [325 + i * 170 for i in range(4)]
    b = []
    for k, y in zip(left, rows):
        b.append(f'<g transform="translate(150 {y}) scale(1.4) translate(-150 {-y})">{obj(k, 150, y)}</g>')
        b.append(text(260, y + 10, k, size=30, anchor="start", weight="400"))
        b.append(f'<circle cx="400" cy="{y}" r="10" fill="{INK}"/>')
    for (c, s), y in zip(right, rows):
        b.append(f'<circle cx="465" cy="{y}" r="9" fill="{INK}"/>')
        b.append(f'<rect x="495" y="{y-36}" width="305" height="72" rx="36" {st(FINE+1)}/>')
        b.append(swatch(528, y, f"a {c} {s}", size=28))
    b.append(text(W / 2, 950, "Say: It is a red circle.", size=32))
    return page(17, "SAY", "Describe It", "Point. Say it. Match.",
                WORDS, "Ask: 'Tell me about the ball.' Help: 'It is a red circle.'", "".join(b), unit=UNIT)


def house(x, w, base, roof_h, door, windows, wall_h):
    """House from shapes: square wall, triangle roof, circle windows, square door."""
    top = base - wall_h
    cx = x + w / 2
    out = [f'<polygon points="{x-18},{top} {cx},{top-roof_h} {x+w+18},{top}" {st()}/>',
           f'<rect x="{x}" y="{top}" width="{w}" height="{wall_h}" {st()}/>']
    for wx, wy, wr in windows:
        out.append(f'<circle cx="{wx}" cy="{wy}" r="{wr}" {st()}/>')
    dx, ds = door
    out.append(f'<rect x="{dx-ds/2}" y="{base-ds}" width="{ds}" height="{ds}" {st()}/>')
    out.append(f'<circle cx="{dx+ds/2-14}" cy="{base-ds/2}" r="5" fill="{INK}"/>')
    return "".join(out)


def p18():
    base = 790
    b = [f'<circle cx="110" cy="320" r="50" {st()}/>']
    for k in range(10):
        a = k * math.pi / 5
        b.append(f'<line x1="{110+64*math.cos(a):.0f}" y1="{320+64*math.sin(a):.0f}" '
                 f'x2="{110+86*math.cos(a):.0f}" y2="{320+86*math.sin(a):.0f}" {ln(FINE+1)}/>')
    b.append(f'<path d="M620,310 q0,-34 36,-34 q14,-26 46,-18 q34,-10 44,22 q30,4 26,30 Z" {st(FINE+1)}/>')
    b.append(f'<line x1="40" y1="{base}" x2="810" y2="{base}" {ln()}/>')
    b.append(house(70, 210, base, 110, (175, 90), [(125, 620, 30), (225, 620, 30)], 250))
    b.append(house(320, 210, base, 120, (425, 110), [(370, 510, 32), (480, 510, 32), (425, 600, 26)], 360))
    b.append(house(570, 210, base, 110, (675, 90), [(625, 620, 30), (725, 620, 30)], 250))
    b.append(f'<circle cx="80" cy="835" r="16" {st(FINE+0.5)}/>' +
             text(108, 845, "Color the circle windows yellow.", size=28, anchor="start"))
    b.append(f'<rect x="64" y="864" width="32" height="32" rx="3" {st(FINE+0.5)}/>' +
             text(108, 890, "Color the square door red.", size=28, anchor="start"))
    b.append(text(W / 2, 950, "The door is ________.", size=32))
    b.append(swatch(595, 836, "yellow", size=24, r=13) + swatch(595, 880, "red", size=24, r=13))
    return page(18, "COLOR", "Shape Town", "Listen. Color the town.",
                WORDS, "Read one direction, pause, and let your child say it back.", "".join(b), unit=UNIT)


def moon(cx, cy, r):
    return (f'<path d="M{cx},{cy-r} A{r},{r} 0 1 0 {cx},{cy+r} A{r*0.78},{r*0.78} 0 1 1 {cx},{cy-r} Z" {st(FINE+1)}/>')


def p19():
    b = [f'<rect x="45" y="252" width="760" height="220" rx="24" {st(FINE+0.5)}/>',
         moon(775, 445, 20)]
    for x, y, r in ((85, 290, 10), (235, 440, 8), (420, 285, 9), (610, 440, 8), (780, 285, 9)):
        b.append(f'<polygon points="{star_pts(x, y, r)}" {st(2.5)}/>')
    for i, k in enumerate(SHAPES):
        cx = 150 + i * 183
        b.append(shape(k, cx, 350, 112, dash()))
        b.append(f'<circle cx="{cx if k != "square" else cx-56}" cy="{350-56 if k != "triangle" else 350-48.7}" r="7" fill="{INK}"/>'
                 if k != "circle" else f'<circle cx="{cx}" cy="294" r="7" fill="{INK}"/>')
        b.append(text(cx, 452, k, size=26))
    # left: /s/ picture words
    b.append(text(185, 525, "Ss says /s/", size=30))
    b.append(f'<circle cx="110" cy="605" r="34" {st()}/>')
    for k in range(8):
        a = k * math.pi / 4
        b.append(f'<line x1="{110+44*math.cos(a):.0f}" y1="{605+44*math.sin(a):.0f}" '
                 f'x2="{110+58*math.cos(a):.0f}" y2="{605+58*math.sin(a):.0f}" {ln(FINE+1)}/>')
    b.append(text(190, 615, "sun", size=30, anchor="start"))
    b.append(f'<polygon points="{star_pts(110, 740, 52)}" {st()}/>' + text(190, 750, "star", size=30, anchor="start"))
    b.append(f'<rect x="68" y="833" width="84" height="84" rx="5" {st()}/>' + text(190, 887, "square", size=30, anchor="start"))
    # right: trace rows
    x0, rw = 370, 430
    b.append(text(x0, 506, "Trace:", size=22, anchor="start", weight="400"))
    b.append(ruled(x0, 515, rw, 84) + dotted(x0 + 12, 596, "Ss  Ss  Ss", size=92))
    b.append(text(x0, 633, "Trace:", size=22, anchor="start", weight="400"))
    b.append(ruled(x0, 642, rw, 80) + dotted(x0 + 12, 719, "It is a star.", size=64))
    b.append(text(x0, 759, "Trace, then write:", size=22, anchor="start", weight="400"))
    b.append(swatch(x0 + 200, 752, "red", size=22, r=12))
    b.append(ruled(x0, 768, rw, 84) + dotted(x0 + 12, 849, "red", size=92))
    b.append(ruled(x0 + 190, 870, rw - 190, 84) if False else ruled(x0, 870, rw, 84))
    return page(19, "TRACE", "S is for Square", "Trace. Say /s/.",
                ["square", "star", "sun", "circle", "triangle"],
                "Ss says /s/. Sun, star, square. Say them together.", "".join(b), unit=UNIT)


def robot():
    d = dash(5)
    cx = 250
    out = [
        # antenna + star
        f'<line x1="{cx}" y1="330" x2="{cx}" y2="308" {d}/>',
        f'<polygon points="{star_pts(cx, 290, 20)}" {d}/>',
        # head (square) with circle eyes and triangle nose
        f'<rect x="{cx-80}" y="330" width="160" height="130" rx="8" {d}/>',
        f'<circle cx="{cx-36}" cy="378" r="20" {d}/>', f'<circle cx="{cx+36}" cy="378" r="20" {d}/>',
        f'<polygon points="{tri_pts(cx, 412, 26)}" {d}/>',
        f'<rect x="{cx-30}" y="432" width="60" height="12" rx="4" {d}/>',
        # neck + body (square) with star and circle buttons
        f'<rect x="{cx-20}" y="460" width="40" height="22" {d}/>',
        f'<rect x="{cx-100}" y="482" width="200" height="190" rx="10" {d}/>',
        f'<polygon points="{star_pts(cx, 550, 42)}" {d}/>',
        f'<circle cx="{cx-40}" cy="628" r="14" {d}/>', f'<circle cx="{cx}" cy="628" r="14" {d}/>',
        f'<circle cx="{cx+40}" cy="628" r="14" {d}/>',
        # arms: squares with circle hands
        f'<rect x="{cx-168}" y="500" width="54" height="54" {d}/>', f'<rect x="{cx-168}" y="562" width="54" height="54" {d}/>',
        f'<circle cx="{cx-141}" cy="650" r="26" {d}/>',
        f'<rect x="{cx+114}" y="500" width="54" height="54" {d}/>', f'<rect x="{cx+114}" y="562" width="54" height="54" {d}/>',
        f'<circle cx="{cx+141}" cy="650" r="26" {d}/>',
        # legs: squares, triangle feet
        f'<rect x="{cx-72}" y="672" width="50" height="50" {d}/>', f'<rect x="{cx+22}" y="672" width="50" height="50" {d}/>',
        f'<polygon points="{cx-47},{722} {cx-7},{782} {cx-87},{782}" {d}/>',
        f'<polygon points="{cx+47},{722} {cx+87},{782} {cx+7},{782}" {d}/>',
    ]
    return "".join(out)


def p20():
    b = [f'<rect x="60" y="252" width="390" height="552" rx="20" {ln(FINE)}/>', robot()]
    # Mrs. B with a prompt bubble
    b.append(bubble(480, 256, 320, 76, tail="left") + text(640, 304, "Tell me about it!", size=28))
    b.append(mrs_b(620, 372, 0.62, arm="wave"))
    # color word bank with swatches
    for i, c in enumerate(COLORS):
        b.append(swatch(515 + (i % 2) * 150, 710 + (i // 2) * 52, c, size=26, r=15))
    # writing zone + Mrs. B badge
    b.append(text(60, 900, "The robot is", size=32, anchor="start"))
    b.append(ruled(270, 830, 400, 80))
    b.append(f'<circle cx="740" cy="870" r="60" {st()}/>' + f'<circle cx="740" cy="870" r="49" {ln(FINE)}/>'
             + f'<polygon points="{star_pts(740, 856, 24)}" {st(FINE)}/>' + text(740, 900, "Mrs. B", size=17))
    return page(20, "USE", "Build a Robot", "Trace. Color. Write.",
                WORDS, "Ask: 'Tell me about your robot.' Help: 'The head is blue.'", "".join(b), unit=UNIT)


PAGES = [("u4_p16_see", p16), ("u4_p17_say", p17), ("u4_p18_color", p18),
         ("u4_p19_trace", p19), ("u4_p20_use", p20)]


def main():
    for name, fn in PAGES:
        (OUT / f"{name}.svg").write_text(fn(), encoding="utf-8")
    print(f"wrote {len(PAGES)} pages to {OUT}")


if __name__ == "__main__":
    main()

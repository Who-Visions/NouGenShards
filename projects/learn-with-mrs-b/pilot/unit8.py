"""Learn With Mrs. B, Unit 8 (pp. 36-40): Review, Mini Story & Celebration.

Reuses the pilot generator's primitives and page chrome; adds picture-dictionary
icons, comic panels and a trophy. Writes u8_p36_see.svg ... u8_p40_use.svg.
"""
import math
import re

from build_pilot import *  # noqa: F401,F403  (W, H, INK, LINE, FINE, st, ln, text, ...)

UNIT = "UNIT 8 · REVIEW & CELEBRATION"
MIA = "puffs"  # Mia's hair: the same girl on every story panel


# ----------------------------------------------------------------- small icons
# Each icon is centered on (cx, cy) and fits a box about 110 * s wide.
def ic_face(cx, cy, s=1.0, expr="happy", hair="short"):
    return face(cx, cy + 6 * s, 38 * s, expr, hair)


def ic_mom(cx, cy, s=1.0):
    return (f'<path d="M{cx-48*s},{cy+52*s} Q{cx-46*s},{cy+14*s} {cx},{cy+12*s} '
            f'Q{cx+46*s},{cy+14*s} {cx+48*s},{cy+52*s} Z" {st()}/>'
            + face(cx, cy - 12 * s, 30 * s, "happy", "bob"))


def ic_baby(cx, cy, s=1.0):
    return (f'<ellipse cx="{cx}" cy="{cy+30*s}" rx="{50*s}" ry="{24*s}" {st()}/>'
            + face(cx, cy - 8 * s, 31 * s, "happy")
            + f'<path d="M{cx-4*s},{cy-38*s} q{8*s},{-12*s} {12*s},{-2*s}" {ln(FINE)}/>')


def ic_book(cx, cy, s=1.0):
    return (f'<path d="M{cx},{cy-28*s} Q{cx-28*s},{cy-44*s} {cx-52*s},{cy-34*s} L{cx-52*s},{cy+34*s} '
            f'Q{cx-28*s},{cy+24*s} {cx},{cy+40*s} Z" {st()}/>'
            f'<path d="M{cx},{cy-28*s} Q{cx+28*s},{cy-44*s} {cx+52*s},{cy-34*s} L{cx+52*s},{cy+34*s} '
            f'Q{cx+28*s},{cy+24*s} {cx},{cy+40*s} Z" {st()}/>'
            + "".join(f'<line x1="{cx+d*14*s}" y1="{cy+(k*16-14)*s}" x2="{cx+d*40*s}" y2="{cy+(k*16-18)*s}" {ln(FINE-1)}/>'
                      for d in (-1, 1) for k in range(3)))


def ic_pencil(cx, cy, s=1.0):
    x, y, L, th = cx - 54 * s, cy, 108 * s, 24 * s
    h = th / 2
    return (f'<g transform="rotate(-30 {cx} {cy})">'
            f'<rect x="{x}" y="{y-h}" width="{16*s}" height="{th}" rx="{5*s}" {st()}/>'
            f'<rect x="{x+16*s}" y="{y-h}" width="{62*s}" height="{th}" {st()}/>'
            f'<polygon points="{x+78*s},{y-h} {x+L},{y} {x+78*s},{y+h}" {st()}/>'
            f'<polygon points="{x+L-9*s},{y-4*s} {x+L},{y} {x+L-9*s},{y+4*s}" fill="{INK}"/></g>')


def ic_circle(cx, cy, s=1.0):
    return f'<circle cx="{cx}" cy="{cy}" r="{44*s}" {st()}/>'


def ic_star(cx, cy, s=1.0):
    return star(cx, cy + 4 * s, 50 * s)


def ic_apple(cx, cy, s=1.0, w=LINE):
    return (f'<path d="M{cx},{cy-24*s} C{cx-46*s},{cy-44*s} {cx-54*s},{cy+38*s} {cx},{cy+42*s} '
            f'C{cx+54*s},{cy+38*s} {cx+46*s},{cy-44*s} {cx},{cy-24*s} Z" {st(w)}/>'
            f'<path d="M{cx},{cy-24*s} q{2*s},{-14*s} {8*s},{-22*s}" {ln(max(FINE, w*0.7))}/>'
            f'<ellipse cx="{cx+22*s}" cy="{cy-38*s}" rx="{14*s}" ry="{7*s}" transform="rotate(-25 {cx+22*s} {cy-38*s})" {st(max(FINE, w*0.7))}/>')


def ic_milk(cx, cy, s=1.0):
    return (f'<rect x="{cx-30*s}" y="{cy-18*s}" width="{60*s}" height="{68*s}" {st()}/>'
            f'<polygon points="{cx-30*s},{cy-18*s} {cx-18*s},{cy-44*s} {cx+18*s},{cy-44*s} {cx+30*s},{cy-18*s}" {st()}/>'
            f'<rect x="{cx-14*s}" y="{cy-54*s}" width="{28*s}" height="{10*s}" {st(FINE)}/>'
            + text(cx, cy + 25 * s, "MILK", size=17 * s, fam=HEAVY))


def ic_dog(cx, cy, s=1.0):
    return (f'<ellipse cx="{cx-36*s}" cy="{cy+2*s}" rx="{15*s}" ry="{30*s}" transform="rotate(15 {cx-36*s} {cy})" {st()}/>'
            f'<ellipse cx="{cx+36*s}" cy="{cy+2*s}" rx="{15*s}" ry="{30*s}" transform="rotate(-15 {cx+36*s} {cy})" {st()}/>'
            f'<circle cx="{cx}" cy="{cy}" r="{36*s}" {st()}/>'
            f'<ellipse cx="{cx}" cy="{cy+18*s}" rx="{20*s}" ry="{15*s}" {st(FINE)}/>'
            f'<ellipse cx="{cx}" cy="{cy+10*s}" rx="{8*s}" ry="{6*s}" fill="{INK}"/>'
            f'<circle cx="{cx-13*s}" cy="{cy-10*s}" r="{4.5*s}" fill="{INK}"/>'
            f'<circle cx="{cx+13*s}" cy="{cy-10*s}" r="{4.5*s}" fill="{INK}"/>'
            f'<path d="M{cx-7*s},{cy+24*s} q{7*s},{6*s} {14*s},0" {ln(FINE-1)}/>')


def ic_fish(cx, cy, s=1.0):
    return (f'<polygon points="{cx+26*s},{cy} {cx+56*s},{cy-26*s} {cx+56*s},{cy+26*s}" {st()}/>'
            f'<ellipse cx="{cx-6*s}" cy="{cy}" rx="{40*s}" ry="{26*s}" {st()}/>'
            f'<circle cx="{cx-28*s}" cy="{cy-6*s}" r="{4.5*s}" fill="{INK}"/>'
            f'<path d="M{cx-8*s},{cy-20*s} q{12*s},{20*s} 0,{40*s}" {ln(FINE-1)}/>')


def ic_bus(cx, cy, s=1.0):
    out = [f'<rect x="{cx-55*s}" y="{cy-32*s}" width="{110*s}" height="{58*s}" rx="{10*s}" {st()}/>']
    for i in range(3):
        out.append(f'<rect x="{cx-45*s+i*26*s}" y="{cy-24*s}" width="{20*s}" height="{18*s}" rx="{3*s}" {st(FINE)}/>')
    out.append(f'<rect x="{cx+33*s}" y="{cy-24*s}" width="{15*s}" height="{40*s}" rx="{3*s}" {st(FINE)}/>')
    for dx in (-30, 28):
        out.append(f'<circle cx="{cx+dx*s}" cy="{cy+28*s}" r="{12*s}" {st()}/>')
    return "".join(out)


def tree(cx, base, s=1.0):
    canopy = ((0, -95, 42), (-30, -70, 30), (30, -70, 30))
    out = [f'<rect x="{cx-10*s}" y="{base-60*s}" width="{20*s}" height="{60*s}" rx="{4*s}" {st()}/>']
    out += [f'<circle cx="{cx+dx*s}" cy="{base+dy*s}" r="{r*s}" {st()}/>' for dx, dy, r in canopy]
    out += [f'<circle cx="{cx+dx*s}" cy="{base+dy*s}" r="{r*s-LINE/2}" fill="#fff"/>' for dx, dy, r in canopy]
    return "".join(out)


def ic_park(cx, cy, s=1.0):
    return (f'<line x1="{cx-54*s}" y1="{cy+50*s}" x2="{cx+54*s}" y2="{cy+50*s}" {ln()}/>'
            + tree(cx, cy + 50 * s, 0.74 * s))


def house(x, base, s=1.0):
    """Simple home: x is the left wall, base the ground line."""
    w, h = 150 * s, 110 * s
    return (f'<path d="M{x},{base} v{-h} l{w/2},{-w*0.45} l{w/2},{w*0.45} v{h} Z" {st()}/>'
            f'<rect x="{x+w*0.38}" y="{base-62*s}" width="{w*0.24}" height="{62*s}" rx="{4*s}" {st(FINE)}/>'
            f'<rect x="{x+w*0.1}" y="{base-92*s}" width="{w*0.2}" height="{w*0.2}" {st(FINE)}/>'
            f'<rect x="{x+w*0.7}" y="{base-92*s}" width="{w*0.2}" height="{w*0.2}" {st(FINE)}/>')


def school(x, base, s=1.0):
    w, h = 190 * s, 120 * s
    out = [f'<line x1="{x+w/2}" y1="{base-h-w*0.32}" x2="{x+w/2}" y2="{base-h-w*0.32-50*s}" {ln(FINE)}/>',
           f'<path d="M{x+w/2},{base-h-w*0.32-50*s} l{40*s},{12*s} l{-40*s},{12*s} Z" {st(FINE)}/>',
           f'<path d="M{x},{base} v{-h} l{w/2},{-w*0.32} l{w/2},{w*0.32} v{h} Z" {st()}/>',
           f'<circle cx="{x+w/2}" cy="{base-h-8*s}" r="{14*s}" {st(FINE)}/>',
           f'<rect x="{x+w*0.4}" y="{base-58*s}" width="{w*0.2}" height="{58*s}" rx="{4*s}" {st(FINE)}/>']
    for fx in (0.1, 0.7):
        out.append(f'<rect x="{x+w*fx}" y="{base-95*s}" width="{w*0.2}" height="{30*s}" {st(FINE)}/>')
    return "".join(out)


def big_bus(x, y, w=210, h=110):
    """Side view school bus; (x, y) is the top-left of the body."""
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" {st()}/>']
    n = 3
    ww = (w * 0.66) / n - 8
    for i in range(n):
        out.append(f'<rect x="{x+14+i*(ww+8)}" y="{y+14}" width="{ww}" height="{h*0.32}" rx="5" {st(FINE)}/>')
    out.append(f'<rect x="{x+w*0.76}" y="{y+14}" width="{w*0.16}" height="{h*0.62}" rx="5" {st(FINE)}/>')
    out.append(f'<line x1="{x}" y1="{y+h*0.58}" x2="{x+w*0.74}" y2="{y+h*0.58}" {ln(FINE)}/>')
    for fx in (0.22, 0.78):
        out.append(f'<circle cx="{x+w*fx}" cy="{y+h}" r="{h*0.19}" {st()}/>')
    return "".join(out)


ICONS = {"happy": lambda x, y: ic_face(x, y, 1, "happy", "curly"),
         "sad": lambda x, y: ic_face(x, y, 1, "sad", "short"),
         "mom": ic_mom, "baby": ic_baby, "book": ic_book, "pencil": ic_pencil,
         "circle": ic_circle, "star": ic_star, "apple": ic_apple, "milk": ic_milk,
         "dog": ic_dog, "fish": ic_fish, "bus": ic_bus, "park": ic_park}


def panel(x, y, w, h, caption=None, cap_h=64, cap_size=28):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" {st()}/>']
    if caption:
        out.append(f'<line x1="{x}" y1="{y+h-cap_h}" x2="{x+w}" y2="{y+h-cap_h}" {ln(FINE)}/>')
        out.append(text(x + w / 2, y + h - cap_h / 2 + cap_size * 0.36, caption, size=cap_size))
    return "".join(out)


def trophy(cx, top):
    t = top
    return (f'<path d="M{cx-72},{t+30} C{cx-128},{t+24} {cx-126},{t+118} {cx-50},{t+128}" {ln(LINE+8)}/>'
            f'<path d="M{cx-72},{t+30} C{cx-128},{t+24} {cx-126},{t+118} {cx-50},{t+128}" fill="none" stroke="#fff" stroke-width="{LINE-4}" stroke-linecap="round"/>'
            f'<path d="M{cx+72},{t+30} C{cx+128},{t+24} {cx+126},{t+118} {cx+50},{t+128}" {ln(LINE+8)}/>'
            f'<path d="M{cx+72},{t+30} C{cx+128},{t+24} {cx+126},{t+118} {cx+50},{t+128}" fill="none" stroke="#fff" stroke-width="{LINE-4}" stroke-linecap="round"/>'
            f'<path d="M{cx-82},{t} L{cx+82},{t} Q{cx+80},{t+150} {cx},{t+172} Q{cx-80},{t+150} {cx-82},{t} Z" {st()}/>'
            f'<ellipse cx="{cx}" cy="{t}" rx="82" ry="14" {st()}/>'
            + star(cx, t + 82, 40, w=FINE + 1)
            + f'<rect x="{cx-18}" y="{t+168}" width="36" height="50" {st()}/>'
            f'<rect x="{cx-62}" y="{t+214}" width="124" height="24" rx="6" {st()}/>'
            f'<rect x="{cx-92}" y="{t+236}" width="184" height="62" rx="10" {st()}/>'
            + text(cx, t + 280, "I can!", size=32, fam=HEAVY))


# ----------------------------------------------------------------- pages
REVIEW = ["happy", "sad", "mom", "baby", "book", "pencil", "circle",
          "star", "apple", "milk", "dog", "fish", "bus", "park"]


def p36():
    b = []
    tw, th, gap = 140, 168, 17.5
    rows = [REVIEW[0:5], REVIEW[5:10], REVIEW[10:14]]
    for r, words in enumerate(rows):
        total = len(words) * tw + (len(words) - 1) * gap
        x0 = 40 + (770 - total) / 2
        y = 248 + r * (th + 14)
        for i, wd in enumerate(words):
            x = x0 + i * (tw + gap)
            b.append(f'<rect x="{x}" y="{y}" width="{tw}" height="{th}" rx="16" {st(FINE+0.5)}/>')
            b.append(ICONS[wd](x + tw / 2, y + 66))
            b.append(f'<line x1="{x+16}" y1="{y+th-16}" x2="{x+tw-16}" y2="{y+th-16}" stroke="{INK}" stroke-width="2.5"/>')
            b.append(text(x + tw / 2, y + th - 24, wd, size=26))
    # letter strip: every letter traced in Units 1-6
    ly = 810
    b.append(text(40, ly + 50, "My letters:", size=26, anchor="start"))
    letters = ["Hh", "Mm", "Bb", "Ss", "Aa", "Dd", "Ff"]
    for i, lt in enumerate(letters):
        x = 196 + i * 88
        b.append(f'<rect x="{x}" y="{ly}" width="82" height="72" rx="10" {st(FINE)}/>')
        b.append(dotted(x + 41, ly + 51, lt, size=33, anchor="middle"))
    b.append(text(W / 2, 948, "I know ____________!", size=36))
    return page(36, "SEE", "My Word Book", "Color. Say each word.",
                ["happy", "mom", "book", "star", "apple", "dog", "bus"],
                "Ask: 'Which word is your favorite?'", "".join(b), unit=UNIT)


def p37():
    b = []
    pw, ph = 375, 345
    spots = [(40, 252), (435, 252), (40, 622), (435, 622)]
    caps = ["Hello! My name is Mia.", "I see a bus.", "I feel happy.", "I like apples."]
    for (x, y), c in zip(spots, caps):
        b.append(panel(x, y, pw, ph, c))
    ground = lambda x, y: f'<line x1="{x+16}" y1="{y+262}" x2="{x+pw-16}" y2="{y+262}" {ln(FINE)}/>'
    # 1 home: Mia waves in front of her house
    x, y = spots[0]
    b.append(ground(x, y))
    b.append(house(x + 195, y + 262, 1.05))
    b.append(child(x + 105, y + 50, 0.62, "happy", MIA, arm="wave"))
    b.append(text(x + 30, y + 40, "1", size=30, anchor="start", fam=HEAVY))
    # 2 bus: Mia at the bus stop, bus arriving
    x, y = spots[1]
    b.append(ground(x, y))
    b.append(f'<rect x="{x+26}" y="{y+70}" width="10" height="192" {st(FINE)}/>'
             f'<rect x="{x+10}" y="{y+40}" width="42" height="34" rx="6" {st(FINE)}/>'
             + text(x + 31, y + 64, "BUS", size=14, fam=HEAVY))
    b.append(big_bus(x + 175, y + 128, 180, 110))
    b.append(child(x + 106, y + 50, 0.62, "happy", MIA, arm="down"))
    b.append(text(x + pw - 30, y + 40, "2", size=30, anchor="end", fam=HEAVY))
    # 3 school: Mia arrives at school, happy
    x, y = spots[2]
    b.append(ground(x, y))
    b.append(school(x + 170, y + 262, 1.0))
    b.append(child(x + 95, y + 50, 0.62, "happy", MIA, arm="up"))
    b.append(text(x + 30, y + 40, "3", size=30, anchor="start", fam=HEAVY))
    # 4 lunch: Mia at the table with a bowl of apples
    x, y = spots[3]
    b.append(ground(x, y))
    b.append(child(x + 110, y + 57, 0.62, "happy", MIA, arm="down"))
    b.append(f'<rect x="{x+30}" y="{y+180}" width="{pw-60}" height="26" rx="6" {st()}/>'
             f'<rect x="{x+42}" y="{y+204}" width="18" height="60" {st()}/>'
             f'<rect x="{x+pw-74}" y="{y+204}" width="18" height="60" {st()}/>')
    bx = x + 265
    b.append(ic_apple(bx - 30, y + 140, 0.55) + ic_apple(bx + 30, y + 140, 0.55) + ic_apple(bx, y + 118, 0.55))
    b.append(f'<path d="M{bx-72},{y+150} h144 q-8,30 -72,30 q-64,0 -72,-30 Z" {st()}/>')
    b.append(text(x + pw - 30, y + 40, "4", size=30, anchor="end", fam=HEAVY))
    return page(37, "SAY", "Mia's Big Day", "Listen. Point. Read along.",
                ["hello", "name", "happy", "bus", "apples"],
                "Read it once. Then your child points and 'reads'.", "".join(b), unit=UNIT)


def p38():
    b = []
    pw, ph, gap, y = 240, 330, 25, 252
    for i in range(3):
        x = 40 + i * (pw + gap)
        b.append(panel(x, y, pw, ph))
        b.append(f'<circle cx="{x+36}" cy="{y+36}" r="26" {st(FINE+1)}/>')
        b.append(f'<line x1="{x+14}" y1="{y+ph-44}" x2="{x+pw-14}" y2="{y+ph-44}" {ln(FINE)}/>')
    s = 0.52
    # A (last): lunch with apples
    x = 40
    b.append(child(x + 68, y + 114, s, "happy", MIA))
    b.append(f'<rect x="{x+18}" y="{y+208}" width="{pw-36}" height="22" rx="6" {st()}/>'
             f'<rect x="{x+24}" y="{y+228}" width="15" height="58" {st()}/>'
             f'<rect x="{x+pw-51}" y="{y+228}" width="15" height="58" {st()}/>')
    ax = x + 184
    b.append(ic_apple(ax - 20, y + 178, 0.42) + ic_apple(ax + 20, y + 178, 0.42) + ic_apple(ax, y + 160, 0.42))
    b.append(f'<path d="M{ax-50},{y+186} h100 q-6,22 -50,22 q-44,0 -50,-22 Z" {st()}/>')
    # B (first): home, waving
    x = 40 + pw + gap
    b.append(house(x + 122, y + 286, 0.72))
    b.append(child(x + 66, y + 110, s, "happy", MIA, arm="wave"))
    # C (next): the bus
    x = 40 + 2 * (pw + gap)
    b.append(big_bus(x + 114, y + 196, 112, 70))
    b.append(child(x + 52, y + 110, s, "happy", MIA))
    b.append(text(W / 2, 632, "How does Mia feel at the end?", size=30))
    feels = ["happy", "sad", "tired", "scared"]
    for i, f in enumerate(feels):
        cx = 130 + i * 197
        fc = face(cx, 728, 50, f, MIA)
        if f == "tired":  # move the sleepy z's clear of Mia's puff
            fc = re.sub(r'<text[^>]*>z</text>', '', fc) + text(cx + 78, 736, "z", size=26) + text(cx + 96, 712, "z", size=20)
        b.append(fc)
        b.append(text(cx, 822, f, size=26))
    b.append(text(60, 922, "First Mia", size=36, anchor="start"))
    b.append(ruled(250, 852, 540, 84))
    return page(38, "COLOR", "What Happened?", "Number 1, 2, 3. Color.",
                ["first", "next", "last", "happy", "sad", "tired"],
                "Ask: 'What did Mia do first? Next? Last?'", "".join(b), unit=UNIT)


def p39():
    b = [f'<rect x="275" y="250" width="300" height="300" rx="14" {st()}/>',
         f'<rect x="300" y="275" width="250" height="250" rx="8" {ln(FINE)}/>',
         text(425, 408, "Draw you!", size=30, weight="400", fill="#999"),
         star(150, 330, 34), star(700, 330, 34), star(180, 470, 24), star(670, 470, 24)]
    rows = [(585, "My name is"), (712, "I like"), (839, "I can")]
    for y, starter in rows:
        b.append(ruled(50, y, 750, 96))
        b.append(dotted(60, y + 88, starter, size=70))
    return page(39, "TRACE", "All About Me", "Trace. Write. Draw you.",
                ["My name is", "I like", "I can"],
                "Say: 'Read your story about you!'", "".join(b), unit=UNIT)


def p40():
    b = [f'<line x1="40" y1="648" x2="810" y2="648" {ln()}/>']
    b.append(mrs_b(140, 290, 0.72, arm="cheer"))
    b.append(trophy(410, 330))
    b.append(child(590, 430, 0.62, "happy", "curly", arm="up"))
    b.append(child(726, 430, 0.62, "happy", "bob", arm="wave"))
    items = [("I can read!", 80, 700), ("I can write!", 450, 700),
             ("I can speak!", 80, 790), ("I can listen!", 450, 790)]
    for label, x, y in items:
        b.append(star(x + 36, y + 32, 38))
        b.append(text(x + 90, y + 44, label, size=32, anchor="start"))
    b.append(text(60, 935, "My name is", size=34, anchor="start"))
    b.append(ruled(270, 866, 520, 84))
    return page(40, "USE", "I Can Do It!", "Color a star for each.",
                ["I can", "read", "write", "speak"],
                "Ask: 'Tell me three things you can do in English now.'", "".join(b), unit=UNIT)


PAGES = [("u8_p36_see", p36), ("u8_p37_say", p37), ("u8_p38_color", p38),
         ("u8_p39_trace", p39), ("u8_p40_use", p40)]


def main():
    for name, fn in PAGES:
        (OUT / f"{name}.svg").write_text(fn(), encoding="utf-8")
    print(f"wrote {len(PAGES)} Unit 8 pages to {OUT}")


if __name__ == "__main__":
    main()

"""Learn With Mrs. B, Unit 3: Classroom & School (pp. 11-15) as print-ready line art.

Reuses the pilot generator (build_pilot.py) for page chrome, people and primitives.
Writes u3_p11_see.svg ... u3_p15_use.svg into the pilot folder.
"""
from build_pilot import *  # noqa: F401,F403
from build_pilot import OUT, W, INK, LINE, FINE, FONT, HEAVY

UNIT = "UNIT 3 · CLASSROOM & SCHOOL"
WORDS3 = ["book", "pencil", "crayon", "desk", "backpack", "teacher", "scissors"]


# ----------------------------------------------------------------- school objects
def tag(x, y, word, size=24):
    """Word label in a pill, centered on (x, y)."""
    w = len(word) * size * 0.62 + 26
    return (f'<rect x="{x-w/2:.1f}" y="{y-size*0.75:.1f}" width="{w:.1f}" height="{size*1.5:.1f}" rx="{size*0.75:.1f}" {st(FINE)}/>'
            + text(x, y + size * 0.36, word, size=size))


def pencil(x, y, L=180, angle=0, th=30, w=LINE):
    """Pencil lying along +x from (x, y): eraser, ferrule, body, cone, lead."""
    h = th / 2
    x1, x2 = x + L * 0.12, x + L * 0.2
    x3, tip = x + L * 0.78, x + L
    xa = x3 + (tip - x3) * 0.62
    f = min(w, FINE)
    return (f'<g transform="rotate({angle} {x} {y})">'
            f'<rect x="{x}" y="{y-h}" width="{x1-x+th*0.2}" height="{th}" rx="{th*0.3}" {st(w)}/>'
            f'<rect x="{x3-2}" y="{y-h}" width="2" height="{th}" {st(w)}/>'
            f'<polygon points="{x3},{y-h} {tip},{y} {x3},{y+h}" {st(w)}/>'
            f'<polygon points="{xa},{y-h*0.38} {tip},{y} {xa},{y+h*0.38}" fill="{INK}" stroke="{INK}" stroke-width="{f}" stroke-linejoin="round"/>'
            f'<rect x="{x2}" y="{y-h}" width="{x3-x2}" height="{th}" {st(w)}/>'
            f'<rect x="{x1}" y="{y-h}" width="{x2-x1}" height="{th}" {st(w)}/>'
            f'<line x1="{(x1+x2)/2}" y1="{y-h}" x2="{(x1+x2)/2}" y2="{y+h}" {ln(f)}/>'
            f'<line x1="{x2+6}" y1="{y}" x2="{x3-6}" y2="{y}" {ln(f)}/></g>')


def book(x, y, w=90, h=130, lw=LINE):
    """Closed book, front cover facing out; (x, y) is the top-left corner."""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" {st(lw)}/>'
            f'<line x1="{x+w*0.17}" y1="{y}" x2="{x+w*0.17}" y2="{y+h}" {ln(FINE)}/>'
            f'<rect x="{x+w*0.32}" y="{y+h*0.2}" width="{w*0.54}" height="{h*0.24}" rx="4" {st(FINE)}/>')


def spine(x, bottom, w, h, letter):
    """Book spine on a shelf with a dotted letter to trace."""
    top = bottom - h
    return (f'<rect x="{x}" y="{top}" width="{w}" height="{h}" rx="5" {st()}/>'
            f'<line x1="{x}" y1="{top+24}" x2="{x+w}" y2="{top+24}" {ln(FINE)}/>'
            f'<line x1="{x}" y1="{bottom-24}" x2="{x+w}" y2="{bottom-24}" {ln(FINE)}/>'
            + dotted(x + w / 2, top + h / 2 + 26, letter, size=76, anchor="middle"))


def desk(x, y, w, leg_h):
    return (f'<rect x="{x+22}" y="{y+30}" width="26" height="{leg_h}" rx="6" {st()}/>'
            f'<rect x="{x+w-48}" y="{y+30}" width="26" height="{leg_h}" rx="6" {st()}/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="34" rx="8" {st()}/>')


def backpack(cx, top, w=150, h=170):
    """Closed backpack, front view; `top` is the top of the body (handle sits above)."""
    x0, x1, b = cx - w / 2, cx + w / 2, top + h
    r = w * 0.28
    return (f'<path d="M{cx-w*0.16},{top+4} Q{cx-w*0.16},{top-w*0.2} {cx},{top-w*0.2} Q{cx+w*0.16},{top-w*0.2} {cx+w*0.16},{top+4}" {ln()}/>'
            f'<path d="M{x0},{b-12} L{x0},{top+r} Q{x0},{top} {x0+r},{top} L{x1-r},{top} Q{x1},{top} {x1},{top+r} L{x1},{b-12} '
            f'Q{x1},{b} {x1-12},{b} L{x0+12},{b} Q{x0},{b} {x0},{b-12} Z" {st()}/>'
            f'<path d="M{x0+4},{top+r*0.7} Q{cx},{top-8} {x1-4},{top+r*0.7} L{x1-4},{top+h*0.36} Q{cx},{top+h*0.48} {x0+4},{top+h*0.36} Z" {st(FINE+0.5)}/>'
            f'<rect x="{cx-w*0.08}" y="{top+h*0.36}" width="{w*0.16}" height="{h*0.13}" rx="3" {st(FINE)}/>'
            f'<rect x="{x0+w*0.16}" y="{top+h*0.58}" width="{w*0.68}" height="{h*0.3}" rx="{w*0.08}" {st(FINE+0.5)}/>'
            f'<line x1="{x0+w*0.24}" y1="{top+h*0.66}" x2="{x1-w*0.24}" y2="{top+h*0.66}" {ln(FINE)}/>')


def scissors(cx, cy, s=1.0, angle=0):
    """Scissors with blades pointing along the rotated +x axis; s scales, stroke stays constant."""
    w, f = LINE / s, FINE / s
    ring = ''.join(
        f'<g transform="rotate({ra} {-58} {sy*30})"><ellipse cx="-58" cy="{sy*30}" rx="32" ry="22" {st(w)}/>'
        f'<ellipse cx="-58" cy="{sy*30}" rx="17" ry="9" {st(f)}/></g>'
        for sy, ra in ((1, -20),))
    ring2 = (f'<g transform="rotate(20 -58 -30)"><ellipse cx="-58" cy="-30" rx="32" ry="22" {st(w)}/>'
             f'<ellipse cx="-58" cy="-30" rx="17" ry="9" {st(f)}/></g>')
    return (f'<g transform="translate({cx} {cy}) rotate({angle}) scale({s})">'
            f'<path d="M-34,22 L110,14 Q60,-8 -30,-6 Z" {st(w)}/>' + ring
            + f'<path d="M-34,-22 L110,-14 Q60,8 -30,6 Z" {st(w)}/>' + ring2
            + f'<circle cx="0" cy="0" r="6" fill="{INK}"/></g>')


def whiteboard(x, y, w, h):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" {st()}/>'
            f'<rect x="{x+16}" y="{y+16}" width="{w-32}" height="{h-32}" rx="4" {ln(FINE)}/>'
            f'<rect x="{x+w*0.15}" y="{y+h}" width="{w*0.7}" height="14" rx="4" {st(FINE)}/>'
            f'<rect x="{x+w*0.62}" y="{y+h-10}" width="56" height="12" rx="5" {st(FINE)}/>')


def bus(cx, top, s=1.0):
    x0, wd, ht = cx - 105 * s, 210 * s, 100 * s
    out = [f'<rect x="{x0}" y="{top}" width="{wd}" height="{ht}" rx="{16*s}" {st()}/>']
    for i in range(3):
        out.append(f'<rect x="{x0+14*s+i*46*s}" y="{top+14*s}" width="{36*s}" height="{32*s}" rx="{5*s}" {st(FINE)}/>')
    out.append(f'<rect x="{x0+156*s}" y="{top+14*s}" width="{38*s}" height="{70*s}" rx="{5*s}" {st(FINE)}/>')
    out.append(f'<line x1="{x0}" y1="{top+62*s}" x2="{x0+150*s}" y2="{top+62*s}" {ln(FINE)}/>')
    for wx in (x0 + 45 * s, x0 + 165 * s):
        out.append(f'<circle cx="{wx}" cy="{top+ht}" r="{22*s}" {st()}/><circle cx="{wx}" cy="{top+ht}" r="{7*s}" fill="{INK}"/>')
    return "".join(out)


def paper(x, y, w, h):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" {st(FINE+1)}/>'


# ----------------------------------------------------------------- pages
def p11():
    b = [whiteboard(60, 262, 400, 146),
         text(260, 350, "I see a book.", size=42),
         mrs_b(640, 292, 0.85, arm="wave", holds="book"),
         tag(640, 734, "teacher"),
         desk(70, 610, 440, 250),
         book(96, 478, 92, 132), tag(142, 448, "book"),
         pencil(215, 590, 160, 0, 32), tag(295, 548, "pencil"),
         crayon(392, 590, 112, 0, th=30), tag(450, 548, "crayon"),
         tag(290, 760, "desk"),
         backpack(570, 780, 150, 145), tag(570, 953, "backpack"),
         scissors(742, 848, 0.72, -62), tag(735, 953, "scissors")]
    return page(11, "SEE", "Mrs. B's Classroom", "Color. Say: I see a ___.",
                WORDS3, "Point and ask: What do you see? I see a book.", "".join(b), unit=UNIT)


def p12():
    b = [f'<rect x="556" y="262" width="244" height="136" rx="18" {st(FINE+1)}/>',
         text(678, 302, "I found:", size=28)]
    for i in range(5):
        b.append(f'<circle cx="{596+i*41}" cy="{352}" r="16" {st(FINE)}/>')
    # wall shelf with a book and a crayon
    b.append(f'<path d="M100,440 v28 h28" {ln(FINE+1)}/><path d="M470,440 v28 h-28" {ln(FINE+1)}/>')
    b.append(f'<rect x="70" y="420" width="430" height="22" rx="5" {st()}/>')
    b.append(book(110, 276, 100, 144))
    b.append(crayon(270, 400, 170, 0, th=34))
    # desk with a pencil and scissors
    b.append(desk(70, 640, 440, 260))
    b.append(pencil(100, 618, 200, 0, 36))
    b.append(scissors(410, 600, 0.72, 0))
    # chair with the backpack
    b.append(f'<rect x="756" y="440" width="30" height="224" rx="8" {st()}/>')
    b.append(f'<rect x="596" y="690" width="24" height="210" rx="6" {st()}/>'
             f'<rect x="752" y="690" width="24" height="210" rx="6" {st()}/>')
    b.append(f'<rect x="576" y="660" width="216" height="32" rx="8" {st()}/>')
    b.append(backpack(668, 478, 150, 182))
    b.append(f'<line x1="44" y1="902" x2="806" y2="902" {ln(FINE)}/>')
    b.append(text(W / 2, 954, "I see a ________.", size=34))
    return page(12, "SAY", "I Spy at School", "Find and circle 5 things.",
                ["book", "pencil", "crayon", "scissors", "backpack"],
                "Take turns: 'I spy a pencil!' Then say: I see a pencil.", "".join(b), unit=UNIT)


def task_write(x, y):
    out = [paper(x, y, 150, 165)]
    for k in range(3):
        out.append(f'<line x1="{x+16}" y1="{y+52+k*42}" x2="{x+134}" y2="{y+52+k*42}" stroke="{INK}" stroke-width="2.5"/>')
    out.append(text(x + 62, y + 90, "abc", size=34))
    return "".join(out)


def task_cut(x, y):
    return (paper(x, y, 150, 165)
            + f'<circle cx="{x+75}" cy="{y+82}" r="48" fill="none" stroke="{INK}" stroke-width="3.5" stroke-dasharray="10 8"/>'
            + f'<line x1="{x}" y1="{y+82}" x2="{x+27}" y2="{y+82}" stroke="{INK}" stroke-width="3.5" stroke-dasharray="10 8"/>')


def task_color(x, y):
    cx, cy = x + 75, y + 85
    heart = (f'<path d="M{cx},{cy+48} C{cx-70},{cy} {cx-50},{cy-52} {cx},{cy-24} '
             f'C{cx+50},{cy-52} {cx+70},{cy} {cx},{cy+48} Z" {st()}/>')
    scrib = "".join(f'<line x1="{cx-40+k*10}" y1="{cy-24+abs(k-1)*4}" x2="{cx-52+k*12}" y2="{cy+14+k*3}" {ln(2.5)}/>' for k in range(4))
    return paper(x, y, 150, 165) + heart + scrib


def p13():
    rows = [("write", task_write, [("pencil", 0), ("scissors", 1), ("backpack", 2)]),
            ("cut", task_cut, [("book", 0), ("scissors", 1), ("crayon", 2)]),
            ("color", task_color, [("backpack", 0), ("book", 1), ("crayon", 2)])]
    xs = [360, 530, 700]
    b = []
    for i, (verb, pic, choices) in enumerate(rows):
        y0 = 258 + i * 236
        b.append(f'<rect x="50" y="{y0}" width="750" height="220" rx="20" {st(FINE)}/>')
        b.append(pic(78, y0 + 14))
        b.append(text(153, y0 + 208, f"to {verb}", size=24, weight="400"))
        b.append(text(530, y0 + 48, f"To {verb}, I need a ____.", size=30))
        cy = y0 + 138
        for name, slot in choices:
            x = xs[slot]
            if name == "pencil":
                b.append(pencil(x - 75, cy, 150, -20, 32))
            elif name == "scissors":
                b.append(scissors(x + 8, cy, 0.62, -35))
            elif name == "backpack":
                b.append(backpack(x, cy - 44, 104, 110))
            elif name == "book":
                b.append(book(x - 42, cy - 62, 84, 118))
            elif name == "crayon":
                b.append(crayon(x - 56, cy + 18, 118, angle=-25, th=42))
        # dividers between the choices
        for dx in (445, 615):
            b.append(f'<line x1="{dx}" y1="{y0+74}" x2="{dx}" y2="{y0+200}" stroke="#bbb" stroke-width="2" stroke-dasharray="6 8"/>')
    return page(13, "COLOR", "What Do I Need?", "Color the one you need.",
                ["pencil", "scissors", "crayon", "book", "backpack"],
                "Ask: To cut, what do you need? Say: I need scissors.", "".join(b), unit=UNIT)


def p14():
    b = [f'<rect x="64" y="256" width="722" height="276" rx="12" {st()}/>',
         f'<line x1="64" y1="504" x2="786" y2="504" {ln()}/>']
    heights = [200, 176, 214, 188, 206, 172, 196, 210]
    x = 92
    for i, hgt in enumerate(heights):
        b.append(spine(x, 504, 74, hgt, "B" if i % 2 == 0 else "b"))
        x += 84
    pics = [(170, "book"), (425, "backpack"), (670, "bus")]
    b.append(book(122, 566, 96, 124))
    b.append(backpack(425, 580, 116, 110))
    b.append(bus(670, 580, 0.95))
    for px, wd in pics:
        b.append(text(px, 752, wd, size=34))
    b.append(text(70, 812, "Trace:", size=26, anchor="start"))
    b.append(ruled(70, 830, 710, 100) + dotted(90, 926, "I see a book.", size=98))
    b.append(text(780, 812, "Bb says /b/", size=26, anchor="end"))
    return page(14, "TRACE", "B is for Book", "Trace Bb. Say /b/.",
                ["book", "backpack", "bus"], "Bb says /b/. Book, bag, bus. What else says /b/?", "".join(b), unit=UNIT)


def p15():
    b = []
    # flap folded open behind the bag
    b.append(f'<path d="M104,404 Q96,276 275,272 Q454,276 446,404 Z" {st()}/>')
    b.append(f'<rect x="251" y="262" width="48" height="66" rx="8" {st(FINE+1)}/>')
    b.append(f'<rect x="263" y="300" width="24" height="16" rx="3" {st(FINE)}/>')
    # shoulder straps peeking out at the sides
    for sx in (-1, 1):
        x = 275 + sx * 195
        b.append(f'<path d="M{x},{470} Q{x+sx*40},{600} {x+sx*6},{800}" {ln(LINE*4)}/><path d="M{x},{470} Q{x+sx*40},{600} {x+sx*6},{800}" fill="none" stroke="#fff" stroke-width="{LINE*4-2*LINE}"/>')
    # body with open top
    b.append(f'<path d="M80,410 L80,842 Q80,902 140,902 L410,902 Q470,902 470,842 L470,410 Z" {st()}/>')
    b.append(f'<ellipse cx="275" cy="410" rx="195" ry="44" {st()}/>')
    b.append(f'<path d="M110,414 Q275,368 440,414" {ln(FINE)}/>')
    b.append(f'<rect x="118" y="490" width="314" height="370" rx="26" fill="none" stroke="#999" stroke-width="3" stroke-dasharray="12 10"/>')
    b.append(text(275, 685, "Draw 3 things", size=30, weight="400", fill="#999"))
    # counting row
    b.append(text(520, 300, "I packed:", size=30, anchor="start"))
    for i in range(3):
        b.append(f'<circle cx="{556+i*84}" cy="354" r="30" {st(FINE+1)}/>' + text(556 + i * 84, 366, str(i + 1), size=34, fill="#999"))
    b.append(text(520, 466, "I need a", size=32, anchor="start"))
    b.append(ruled(520, 486, 280, 80))
    b.append(text(520, 636, "I see a", size=32, anchor="start"))
    b.append(ruled(520, 656, 280, 80))
    b.append(f'<circle cx="660" cy="830" r="56" {st()}/>' + star(660, 826, 32, w=FINE + 1))
    b.append(text(660, 930, "You did it!", size=28, fam=HEAVY))
    return page(15, "USE", "Pack My Backpack", "Draw 3 things. Write.",
                WORDS3, "Ask: What will you pack? Why? Count the things together.", "".join(b), unit=UNIT)


PAGES = [("u3_p11_see", p11), ("u3_p12_say", p12), ("u3_p13_color", p13),
         ("u3_p14_trace", p14), ("u3_p15_use", p15)]


def main():
    for name, fn in PAGES:
        (OUT / f"{name}.svg").write_text(fn(), encoding="utf-8")
    print(f"wrote {len(PAGES)} Unit 3 pages to {OUT}")


if __name__ == "__main__":
    main()

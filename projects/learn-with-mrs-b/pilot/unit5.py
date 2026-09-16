"""Learn With Mrs. B, Unit 5: Food & Everyday Needs (pp. 21-25).

Reuses the pilot generator (build_pilot.py) without editing it.
Run: python unit5.py  -> writes u5_p21_see.svg ... u5_p25_use.svg next to this file.
"""
from build_pilot import *  # noqa: F401,F403  (W, H, LINE, FINE, st, ln, text, hollow, dotted, ruled, star, face, page, OUT ...)

UNIT = "UNIT 5 · FOOD & EVERYDAY NEEDS"
FOODS = ["apple", "banana", "rice", "bread", "milk", "water"]


# ----------------------------------------------------------------- food helpers
def apple(cx, cy, r, w=LINE):
    """Apple centered on (cx, cy); spans about cy-1.15r (stem) to cy+0.95r."""
    d = (f'M{cx},{cy-0.7*r} C{cx-0.3*r},{cy-r} {cx-r},{cy-0.9*r} {cx-r},{cy-0.15*r} '
         f'C{cx-r},{cy+0.6*r} {cx-0.45*r},{cy+r} {cx-0.2*r},{cy+0.95*r} Q{cx},{cy+0.88*r} {cx+0.2*r},{cy+0.95*r} '
         f'C{cx+0.45*r},{cy+r} {cx+r},{cy+0.6*r} {cx+r},{cy-0.15*r} C{cx+r},{cy-0.9*r} {cx+0.3*r},{cy-r} {cx},{cy-0.7*r} Z')
    return (f'<line x1="{cx}" y1="{cy-0.7*r}" x2="{cx+0.08*r}" y2="{cy-1.12*r}" {ln(min(w, FINE+1))}/>'
            f'<ellipse cx="{cx+0.34*r}" cy="{cy-0.98*r}" rx="{0.28*r}" ry="{0.12*r}" '
            f'transform="rotate(-25 {cx+0.34*r} {cy-0.98*r})" {st(min(w, FINE))}/>'
            f'<path d="{d}" {st(w)}/>')


def banana(cx, cy, s=1.0, spots=False):
    """Curved banana (spots=True draws a plantain). Spans about x +-80s, y -45s..+30s."""
    p = lambda x, y: f"{cx+x*s:.1f},{cy+y*s:.1f}"
    out = [f'<rect x="{cx-86*s}" y="{cy-50*s}" width="{16*s}" height="{14*s}" rx="{3*s}" '
           f'transform="rotate(-35 {cx-78*s} {cy-43*s})" {st(FINE)}/>',
           f'<path d="M{p(-74,-36)} Q{p(-30,52)} {p(72,-2)} L{p(78,-10)} Q{p(-22,6)} {p(-64,-42)} Z" {st()}/>',
           f'<path d="M{p(-66,-38)} Q{p(-24,26)} {p(70,-6)}" {ln(2.5)}/>']
    if spots:
        for x, y in ((-30, 8), (0, 14), (30, 8)):
            out.append(f'<ellipse cx="{cx+x*s}" cy="{cy+y*s}" rx="{5*s}" ry="{3.5*s}" fill="{INK}"/>')
    return "".join(out)


def rice_bowl(cx, cy, s=1.0):
    """Bowl of rice; spans about y -70s..+92s, x +-85s."""
    out = [f'<path d="M{cx-78*s},{cy} Q{cx-72*s},{cy-40*s} {cx-35*s},{cy-45*s} Q{cx},{cy-72*s} {cx+35*s},{cy-45*s} '
           f'Q{cx+72*s},{cy-40*s} {cx+78*s},{cy} Z" {st()}/>']
    for x, y, a in ((-40, -22, 20), (-10, -40, -15), (22, -24, 30), (48, -14, -20), (0, -12, 60)):
        out.append(f'<ellipse cx="{cx+x*s}" cy="{cy+y*s}" rx="{7*s}" ry="{3.5*s}" transform="rotate({a} {cx+x*s} {cy+y*s})" {st(2)}/>')
    out.append(f'<rect x="{cx-32*s}" y="{cy+70*s}" width="{64*s}" height="{18*s}" rx="{5*s}" {st()}/>')
    out.append(f'<path d="M{cx-85*s},{cy} Q{cx-80*s},{cy+78*s} {cx},{cy+78*s} Q{cx+80*s},{cy+78*s} {cx+85*s},{cy} Z" {st()}/>')
    out.append(f'<path d="M{cx-60*s},{cy+28*s} Q{cx},{cy+40*s} {cx+60*s},{cy+28*s}" {ln(FINE)}/>')
    return "".join(out)


def bread(cx, cy, s=1.0):
    """Loaf of bread; spans y -55s..+45s, x +-85s."""
    out = [f'<path d="M{cx-85*s},{cy+45*s} L{cx-85*s},{cy-5*s} Q{cx-85*s},{cy-55*s} {cx},{cy-55*s} '
           f'Q{cx+85*s},{cy-55*s} {cx+85*s},{cy-5*s} L{cx+85*s},{cy+45*s} Z" {st()}/>']
    for dx in (-40, 0, 40):
        out.append(f'<line x1="{cx+(dx-14)*s}" y1="{cy-8*s}" x2="{cx+(dx+14)*s}" y2="{cy-36*s}" {ln(FINE)}/>')
    return "".join(out)


def milk(cx, cy, s=1.0, label=True):
    """Milk carton; spans y -97s..+80s, x +-45s."""
    out = [f'<rect x="{cx-30*s}" y="{cy-97*s}" width="{60*s}" height="{14*s}" rx="{3*s}" {st(FINE)}/>',
           f'<path d="M{cx-45*s},{cy-40*s} L{cx-30*s},{cy-84*s} L{cx+30*s},{cy-84*s} L{cx+45*s},{cy-40*s} Z" {st()}/>',
           f'<rect x="{cx-45*s}" y="{cy-40*s}" width="{90*s}" height="{120*s}" rx="{4*s}" {st()}/>']
    if label:
        out.append(f'<rect x="{cx-32*s}" y="{cy-5*s}" width="{64*s}" height="{44*s}" rx="{8*s}" {st(FINE)}/>')
        out.append(text(cx, cy + 25 * s, "MILK", size=20 * s, fam=HEAVY))
    return "".join(out)


def water(cx, cy, s=1.0):
    """Water bottle with a drop on the label; spans y -100s..+100s, x +-40s."""
    return (f'<rect x="{cx-17*s}" y="{cy-100*s}" width="{34*s}" height="{24*s}" rx="{5*s}" {st()}/>'
            f'<path d="M{cx-14*s},{cy-76*s} L{cx-14*s},{cy-66*s} Q{cx-40*s},{cy-58*s} {cx-40*s},{cy-35*s} '
            f'L{cx-40*s},{cy+84*s} Q{cx-40*s},{cy+100*s} {cx-24*s},{cy+100*s} L{cx+24*s},{cy+100*s} '
            f'Q{cx+40*s},{cy+100*s} {cx+40*s},{cy+84*s} L{cx+40*s},{cy-35*s} Q{cx+40*s},{cy-58*s} {cx+14*s},{cy-66*s} '
            f'L{cx+14*s},{cy-76*s} Z" {st()}/>'
            f'<rect x="{cx-40*s}" y="{cy-5*s}" width="{80*s}" height="{55*s}" {st(FINE)}/>'
            f'<path d="M{cx},{cy+2*s} Q{cx+16*s},{cy+26*s} {cx},{cy+42*s} Q{cx-16*s},{cy+26*s} {cx},{cy+2*s} Z" {st(FINE)}/>')


def plate(cx, cy, r):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" {st()}/><circle cx="{cx}" cy="{cy}" r="{r*0.8}" {ln(FINE)}/>'


def ant(cx, cy, s=1.0):
    out = []
    for dx in (-18, 0, 18):
        x = cx + dx * s
        out.append(f'<path d="M{x},{cy} l{-10*s},{26*s} M{x},{cy} l{10*s},{26*s}" {ln(FINE)}/>')
    out.append(f'<path d="M{cx+38*s},{cy-14*s} q{8*s},{-26*s} {26*s},{-30*s} M{cx+44*s},{cy-10*s} q{18*s},{-18*s} {36*s},{-16*s}" {ln(FINE)}/>')
    out.append(f'<ellipse cx="{cx-40*s}" cy="{cy}" rx="{26*s}" ry="{20*s}" {st()}/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{13*s}" {st()}/>')
    out.append(f'<circle cx="{cx+34*s}" cy="{cy-4*s}" r="{17*s}" {st()}/>')
    out.append(f'<circle cx="{cx+40*s}" cy="{cy-8*s}" r="{3.5*s}" fill="{INK}"/>')
    return "".join(out)


def market_stall(x0, x1, top, shelves, base):
    """Awning with stripes and scallops, two posts, shelf planks at `shelves` (y), counter front to `base`."""
    aw_b = top + 55
    out = []
    n = 10
    sw = (x1 - x0) / n
    for i in range(n):  # scallops under the awning
        out.append(f'<path d="M{x0+i*sw},{aw_b} A{sw/2},{sw/2.6} 0 0 0 {x0+(i+1)*sw},{aw_b}" {st()}/>')
    out.append(f'<rect x="{x0}" y="{top}" width="{x1-x0}" height="{aw_b-top}" rx="8" {st()}/>')
    for i in range(1, n):
        out.append(f'<line x1="{x0+i*sw}" y1="{top}" x2="{x0+i*sw}" y2="{aw_b}" {ln(FINE)}/>')
    px0, px1 = x0 + 15, x1 - 39
    for px in (px0, px1):
        out.append(f'<rect x="{px}" y="{aw_b+sw/2.6}" width="24" height="{shelves[-1]-aw_b-sw/2.6}" {st()}/>')
    for y in shelves:
        out.append(f'<rect x="{px0}" y="{y}" width="{px1+24-px0}" height="44" rx="6" {st()}/>')
    y = shelves[-1] + 44
    out.append(f'<rect x="{px0}" y="{y}" width="{px1+24-px0}" height="{base-y}" rx="6" {st()}/>')
    return "".join(out)


def bubble(x, y, w, h, s, tail="left"):
    """Rounded speech bubble with a small tail; text centered."""
    tx = x if tail == "left" else x + w
    sgn = -1 if tail == "left" else 1
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2}" {st(FINE+1)}/>'
            f'<path d="M{tx-sgn*4},{y+h*0.35} L{tx+sgn*22},{y+h*0.55} L{tx-sgn*4},{y+h*0.7}" {st(FINE+1)}/>'
            f'<line x1="{tx-sgn*6}" y1="{y+h*0.38}" x2="{tx-sgn*6}" y2="{y+h*0.67}" stroke="#fff" stroke-width="7"/>'
            + text(x + w / 2, y + h / 2 + 11, s, size=30))


def upage(n, step, title, direction, words, tip, body, tsize=62):
    """page() with an adjustable title size (page() fixes 62, too wide for long titles)."""
    if tsize == 62:
        return page(n, step, title, direction, words, tip, body, unit=UNIT)
    return page(n, step, "", direction, words, tip, hollow(W / 2, 170, title, size=tsize) + body, unit=UNIT)


# ----------------------------------------------------------------- pages
def p21():
    s1, s2, base = 505, 740, 870
    b = [market_stall(45, 805, 250, (s1, s2), base)]
    # top shelf: apple, banana, plantain, bread
    b.append(apple(175, s1 - 52, 55))
    b.append(banana(338, s1 - 32, 0.95))
    b.append(banana(505, s1 - 34, 0.95, spots=True))
    b.append(bread(675, s1 - 42, 0.85))
    b.append(hollow(W / 2, s2 + 44 + 68, "MARKET", size=62))
    # bottom shelf: rice, milk, water
    b.append(rice_bowl(215, s2 - 92, 1.0))
    b.append(milk(425, s2 - 72, 0.9))
    b.append(water(635, s2 - 85, 0.85))
    for x, wd in ((175, "apple"), (340, "banana"), (510, "plantain"), (675, "bread")):
        b.append(text(x, s1 + 32, wd, size=26))
    for x, wd in ((215, "rice"), (425, "milk"), (635, "water")):
        b.append(text(x, s2 + 32, wd, size=26))
    # model frame, two children
    b.append(face(95, 928, 36, "happy", "puffs"))
    b.append(bubble(155, 898, 250, 62, "I like apples.", "left"))
    b.append(face(755, 928, 36, "happy", "short"))
    b.append(bubble(445, 898, 250, 62, "I like rice.", "right"))
    return upage(21, "SEE", "Market Day", "Say each food. Color it.",
                 FOODS, "Which food do you eat at home?", "".join(b))


def p22():
    foods = [("apple", lambda x, y: apple(x, y + 5, 60)), ("banana", lambda x, y: banana(x, y + 8, 1.3)),
             ("rice", lambda x, y: rice_bowl(x, y - 8, 0.85)), ("bread", lambda x, y: bread(x, y + 5, 1.0)),
             ("milk", lambda x, y: milk(x, y + 8, 0.8)), ("water", lambda x, y: water(x, y + 2, 0.75))]
    b = []
    for i, (wd, fn) in enumerate(foods):
        cx = 170 + (i % 3) * 255
        top = 255 + (i // 3) * 315
        b.append(f'<rect x="{cx-120}" y="{top}" width="240" height="300" rx="18" {ln(FINE)}/>')
        b.append(fn(cx, top + 95))
        b.append(text(cx, top + 207, wd, size=30))
        b.append(face(cx - 52, top + 252, 32, "happy"))
        b.append(face(cx + 52, top + 252, 32, "sad"))
    b.append(text(W / 2, 930, "I like ___.     I don't like ___.", size=32))
    return upage(22, "SAY", "I Like, I Don't Like", "Circle a face. Say it.",
                 FOODS + ["like"], "Do you like bananas? Say: I like bananas.", "".join(b), tsize=52)


def p23():
    rows = [("apple", 2, (4, 2, 1)), ("banana", 4, (3, 4, 5)), ("bread", 1, (1, 5, 2)),
            ("apple", 5, (3, 5, 4)), ("banana", 3, (2, 1, 3))]
    b = []
    for i, (kind, n, opts) in enumerate(rows):
        top = 255 + i * 128
        cy = top + 59
        b.append(f'<rect x="45" y="{top}" width="760" height="118" rx="18" {ln(FINE)}/>')
        gap = 84 if kind == "apple" else 100
        x0 = 262 - (n - 1) * gap / 2
        for k in range(n):
            x = x0 + k * gap
            if kind == "apple":
                b.append(apple(x, cy + 6, 36))
            elif kind == "banana":
                b.append(banana(x, cy + 6, 0.58))
            else:
                b.append(bread(x, cy + 6, 0.8))
        b.append(f'<line x1="485" y1="{top+14}" x2="485" y2="{top+104}" {ln(2.5)}/>')
        for j, o in enumerate(opts):
            x = 565 + j * 88
            b.append(f'<circle cx="{x}" cy="{cy}" r="40" {ln(FINE)}/>')
            b.append(hollow(x, cy + 23, str(o), size=64))
    b.append(text(W / 2, 942, "I have 3 apples.", size=32))
    return upage(23, "COLOR", "Count and Color", "Count. Color the number.",
                 ["one", "two", "three", "four", "five", "apples", "bananas"],
                 "Count with me. How many?", "".join(b))


def p24():
    b = [f'<path d="M50,792 Q250,775 460,792" {ln()}/>',
         f'<rect x="226" y="560" width="48" height="228" rx="10" {st()}/>']
    canopy = ((250, 455, 140), (140, 525, 80), (360, 525, 80), (250, 370, 92))
    for cx, cy, r in canopy:
        b.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" {st()}/>')
    for cx, cy, r in canopy:
        b.append(f'<circle cx="{cx}" cy="{cy}" r="{r - LINE / 2}" fill="#fff"/>')
    for i, (x, y) in enumerate(((250, 360), (160, 455), (340, 455), (200, 560), (300, 560))):
        b.append(apple(x, y, 42))
        b.append(dotted(x, y + 18, "A" if i % 2 == 0 else "a", size=50, anchor="middle"))
    b.append(text(645, 292, "Aa says /a/", size=30))
    b.append(ruled(500, 310, 290, 90) + dotted(512, 398, "Aa", size=100))
    b.append(ruled(500, 440, 290, 90) + dotted(512, 528, "apple", size=84))
    b.append(ant(575, 650, 1.0) + text(575, 740, "ant", size=28))
    b.append(water(725, 630, 0.72) + text(725, 740, "water", size=28))
    b.append(text(60, 890, "Trace:", size=30, anchor="start"))
    b.append(ruled(200, 815, 590, 95) + dotted(210, 908, "I need water.", size=74))
    return upage(24, "TRACE", "A is for Apple", "Trace Aa. Trace the words.",
                 ["apple", "ant", "water", "I need water."],
                 "When you are thirsty, say: I need water.", "".join(b))


def p25():
    b = [plate(300, 500, 210),
         text(300, 508, "Draw your food", size=26, weight="400", fill="#999"),
         # fork
         f'<rect x="56" y="470" width="16" height="190" rx="8" {st(FINE+1)}/>',
         f'<path d="M50,370 v70 q0,30 14,30 q14,0 14,-30 v-70" {st(FINE+1)}/>',
         f'<line x1="59" y1="372" x2="59" y2="425" {ln(FINE)}/><line x1="69" y1="372" x2="69" y2="425" {ln(FINE)}/>',
         # spoon
         f'<rect x="540" y="430" width="16" height="230" rx="8" {st(FINE+1)}/>',
         f'<ellipse cx="548" cy="390" rx="22" ry="34" {st(FINE+1)}/>',
         # cup
         f'<path d="M615,330 L745,330 L728,560 L632,560 Z" {st()}/>',
         f'<path d="M621,380 L739,380" {ln(FINE)}/>',
         # Mrs. B badge
         f'<circle cx="680" cy="650" r="54" {st()}/>' + star(680, 646, 32, w=FINE + 1),
         text(680, 738, "You did it!", size=24, fam=HEAVY),
         text(60, 823, "I have", size=34, anchor="start"), ruled(190, 765, 600, 80),
         text(60, 928, "I like", size=34, anchor="start"), ruled(190, 870, 600, 80)]
    return upage(25, "USE", "My Healthy Plate", "Draw your meal. Write.",
                 FOODS + ["one-five"], "What is on your plate? How many?", "".join(b), tsize=58)


PAGES = [("u5_p21_see", p21), ("u5_p22_say", p22), ("u5_p23_color", p23),
         ("u5_p24_trace", p24), ("u5_p25_use", p25)]


def main():
    for name, fn in PAGES:
        (OUT / f"{name}.svg").write_text(fn(), encoding="utf-8")
    print(f"wrote {len(PAGES)} Unit 5 pages to {OUT}")


if __name__ == "__main__":
    main()

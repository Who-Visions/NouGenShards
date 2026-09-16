"""Learn With Mrs. B, Unit 2: My Family (pp. 6-10) as print-ready line art.

Reuses the pilot primitives from build_pilot.py (not edited here). Writes one SVG per page.
"""
import math
from build_pilot import *  # noqa: F401,F403
from build_pilot import OUT, W, INK, LINE, FINE, HEAVY

UNIT = "UNIT 2 · MY FAMILY"
FAMILY = ["mom", "dad", "sister", "brother", "baby", "grandma", "grandpa"]
_clip_n = [0]


def _cid():
    _clip_n[0] += 1
    return f"u2c{_clip_n[0]}"


# ----------------------------------------------------------------- family heads
def glasses(cx, cy, r):
    ey = cy - r * 0.08
    return (f'<circle cx="{cx-r*0.36}" cy="{ey}" r="{r*0.22}" {ln(FINE)}/>'
            f'<circle cx="{cx+r*0.36}" cy="{ey}" r="{r*0.22}" {ln(FINE)}/>'
            f'<line x1="{cx-r*0.14}" y1="{ey}" x2="{cx+r*0.14}" y2="{ey}" {ln(FINE)}/>')


def head(cx, cy, r, who, expr="happy"):
    """Head for one family member; each person has a distinct hair/feature silhouette."""
    pre, post, hair = [], [], None
    if who == "mom":
        pre.append(f'<path d="M{cx-r*1.12},{cy+r*1.25} Q{cx-r*1.3},{cy-r*1.3} {cx},{cy-r*1.2} '
                   f'Q{cx+r*1.3},{cy-r*1.3} {cx+r*1.12},{cy+r*1.25} Q{cx},{cy+r*1.05} {cx-r*1.12},{cy+r*1.25} Z" {st()}/>')
        hair = "short"
    elif who == "dad":
        hair = "short"
        # chin beard sitting below the smile
        post.append(f'<path d="M{cx-r*0.86},{cy+r*0.3} Q{cx-r*0.8},{cy+r*1.18} {cx},{cy+r*1.18} Q{cx+r*0.8},{cy+r*1.18} {cx+r*0.86},{cy+r*0.3} '
                    f'Q{cx},{cy+r*1.0} {cx-r*0.86},{cy+r*0.3} Z" {st(FINE+1)}/>')
    elif who == "grandma":
        pre.append(f'<circle cx="{cx}" cy="{cy-r*1.28}" r="{r*0.38}" {st()}/>')
        hair = "bob"
        post.append(glasses(cx, cy, r))
    elif who == "grandpa":
        for s in (-1, 1):
            pre.append(f'<ellipse cx="{cx+s*r*0.93}" cy="{cy-r*0.12}" rx="{r*0.26}" ry="{r*0.42}" {st()}/>')
        post.append(f'<path d="M{cx-r*0.42},{cy+r*0.34} Q{cx-r*0.22},{cy+r*0.1} {cx},{cy+r*0.22} '
                    f'Q{cx+r*0.22},{cy+r*0.1} {cx+r*0.42},{cy+r*0.34} Q{cx},{cy+r*0.3} {cx-r*0.42},{cy+r*0.34} Z" {st(FINE)}/>')
        post.append(glasses(cx, cy, r))
    elif who == "sister":
        hair = "puffs"
    elif who == "brother":
        hair = "curly"
    elif who == "baby":
        post.append(f'<path d="M{cx-r*0.08},{cy-r*0.97} C{cx-r*0.12},{cy-r*1.45} {cx+r*0.42},{cy-r*1.38} {cx+r*0.22},{cy-r*1.12}" {ln(FINE)}/>')
    else:  # "me"
        hair = "short"
    return "".join(pre) + face(cx, cy, r, expr, hair) + "".join(post)


def bust(cx, cy, r, who, bottom):
    """Head and shoulders down to `bottom` (clipped by the frame that holds it)."""
    sw = r * (1.25 if who == "baby" else 1.6)
    ys = cy + r * 0.98
    out = [f'<path d="M{cx-sw},{bottom+20} L{cx-sw},{ys+r*0.45} Q{cx-sw},{ys} {cx-sw+r*0.5},{ys} '
           f'L{cx+sw-r*0.5},{ys} Q{cx+sw},{ys} {cx+sw},{ys+r*0.45} L{cx+sw},{bottom+20} Z" {st()}/>',
           f'<path d="M{cx-r*0.35},{ys} Q{cx},{ys+r*0.4} {cx+r*0.35},{ys}" {ln(FINE)}/>',
           f'<rect x="{cx-r*0.22}" y="{cy+r*0.8}" width="{r*0.44}" height="{r*0.26}" {st(FINE)}/>',
           head(cx, cy, r, who)]
    return "".join(out)


def portrait(cx, cy, w, h, who, shape="rect", r=46, head_dy=None):
    """Picture frame (thick frame + thin mat) with a family member's bust clipped inside."""
    cid, inset = _cid(), 16
    if shape == "oval":
        outer = f'<ellipse cx="{cx}" cy="{cy}" rx="{w/2}" ry="{h/2}" {st()}/>'
        inner_shape = f'<ellipse cx="{cx}" cy="{cy}" rx="{w/2-inset}" ry="{h/2-inset}"'
    else:
        outer = f'<rect x="{cx-w/2}" y="{cy-h/2}" width="{w}" height="{h}" rx="10" {st()}/>'
        inner_shape = f'<rect x="{cx-w/2+inset}" y="{cy-h/2+inset}" width="{w-2*inset}" height="{h-2*inset}" rx="4"'
    clip = f'<clipPath id="{cid}">{inner_shape}/></clipPath>'
    inner = f'<g clip-path="url(#{cid})">{bust(cx, cy + (-h * 0.1 if head_dy is None else head_dy), r, who, cy + h / 2)}</g>'
    return outer + clip + inner + inner_shape + f' {ln(FINE)}/>'


# ----------------------------------------------------------------- full figures
def hat(cx, cy, r):
    """Brimmed hat sitting on a head centered at (cx, cy) with radius r."""
    return (f'<path d="M{cx-r*0.86},{cy-r*0.72} L{cx-r*0.76},{cy-r*1.62} Q{cx},{cy-r*1.85} {cx+r*0.76},{cy-r*1.62} '
            f'L{cx+r*0.86},{cy-r*0.72} Z" {st()}/>'
            f'<line x1="{cx-r*0.84}" y1="{cy-r*0.98}" x2="{cx+r*0.84}" y2="{cy-r*0.98}" {ln(FINE)}/>'
            f'<ellipse cx="{cx}" cy="{cy-r*0.7}" rx="{r*1.5}" ry="{r*0.26}" {st()}/>')


def adult(cx, top, s, who, outfit="pants", with_hat=False):
    """Standing adult; about 387*s tall from the top of the head to the soles."""
    r = 50 * s
    hy = top + r
    body_top, body_h, bw = hy + r * 0.95, 150 * s, 120 * s
    leg_bottom = body_top + body_h + 125 * s
    out = []
    leg_top = body_top + body_h + (55 * s if outfit == "dress" else -10 * s)
    for dx in (-0.22, 0.22):
        x = cx + dx * bw
        out.append(f'<rect x="{x-15*s}" y="{leg_top}" width="{30*s}" height="{leg_bottom-leg_top}" rx="{8*s}" {st()}/>')
        out.append(f'<ellipse cx="{x+(9*s if dx > 0 else -9*s)}" cy="{leg_bottom}" rx="{28*s}" ry="{14*s}" {st()}/>')
    sh_y = body_top + 24 * s
    for side in (-1, 1):
        sx = cx + side * bw * 0.44
        ex, ey = sx + side * 34 * s, sh_y + 110 * s
        out.append(f'<line x1="{sx}" y1="{sh_y}" x2="{ex}" y2="{ey}" stroke="{INK}" stroke-width="{34*s+LINE}" stroke-linecap="round"/>')
        out.append(f'<line x1="{sx}" y1="{sh_y}" x2="{ex}" y2="{ey}" stroke="#fff" stroke-width="{34*s-LINE+2}" stroke-linecap="round"/>')
        out.append(f'<circle cx="{ex}" cy="{ey}" r="{16*s}" {st()}/>')
    out.append(f'<path d="M{cx-bw/2},{body_top+22*s} Q{cx-bw/2},{body_top} {cx-bw/2+26*s},{body_top} '
               f'L{cx+bw/2-26*s},{body_top} Q{cx+bw/2},{body_top} {cx+bw/2},{body_top+22*s} '
               f'L{cx+bw/2},{body_top+body_h} L{cx-bw/2},{body_top+body_h} Z" {st()}/>')
    if outfit == "dress":
        out.append(f'<path d="M{cx-bw*0.5},{body_top+body_h*0.55} L{cx-bw*0.72},{body_top+body_h+60*s} '
                   f'L{cx+bw*0.72},{body_top+body_h+60*s} L{cx+bw*0.5},{body_top+body_h*0.55} Z" {st()}/>')
    out.append(f'<path d="M{cx-20*s},{body_top} Q{cx},{body_top+22*s} {cx+20*s},{body_top}" {ln(FINE)}/>')
    out.append(f'<rect x="{cx-13*s}" y="{hy+r*0.8}" width="{26*s}" height="{r*0.3}" {st(FINE)}/>')
    out.append(head(cx, hy, r, who))
    if with_hat:
        out.append(hat(cx, hy, r))
    return "".join(out)


def milk(cx, bottom, s=1.0):
    w, h = 70 * s, 95 * s
    x, y = cx - w / 2, bottom - h
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" {st()}/>'
            f'<path d="M{x},{y} L{x+w*0.18},{y-30*s} L{x+w*0.82},{y-30*s} L{x+w},{y} Z" {st()}/>'
            f'<rect x="{x+w*0.35}" y="{y-44*s}" width="{w*0.3}" height="{14*s}" {st(FINE)}/>'
            f'<ellipse cx="{cx}" cy="{y+h*0.5}" rx="{w*0.3}" ry="{h*0.2}" {ln(FINE)}/>')


def heart(cx, cy, r, w=LINE):
    return (f'<path d="M{cx},{cy+r*0.9} C{cx-r*1.6},{cy-r*0.1} {cx-r*0.9},{cy-r*1.35} {cx},{cy-r*0.45} '
            f'C{cx+r*0.9},{cy-r*1.35} {cx+r*1.6},{cy-r*0.1} {cx},{cy+r*0.9} Z" {st(w)}/>')


# ----------------------------------------------------------------- pages
def p6():
    b = []
    cols = (160, 425, 690)
    rows = (350, 590, 830)
    layout = [("grandma", "oval"), ("grandpa", "rect"), ("mom", "oval"),
              ("dad", "rect"), ("sister", "oval"), ("brother", "rect")]
    for i, (who, shape) in enumerate(layout):
        cx, cy = cols[i % 3], rows[i // 3]
        if who == "grandma":  # smaller, lower head so the bun clears the oval's narrow top
            b.append(portrait(cx, cy, 214, 184, who, shape, r=38, head_dy=2))
        else:
            b.append(portrait(cx, cy, 214, 184, who, shape))
        b.append(text(cx, cy + 128, who, size=32))
    b.append(portrait(160, 830, 214, 184, "baby", "rect", r=44))
    b.append(text(160, 958, "baby", size=32))
    # model sentence bubble pointing at the baby's frame
    b.append(f'<path d="M330,760 h440 a22,22 0 0 1 22,22 v96 a22,22 0 0 1 -22,22 h-440 a22,22 0 0 1 -22,-22 '
             f'v-30 l-30,-18 l30,-18 v-30 a22,22 0 0 1 22,-22 Z" {st(FINE+1)}/>')
    b.append(text(550, 845, "This is my baby.", size=42))
    return page(6, "SEE", "Family Photo Wall", "Look. Say. Color each one.",
                FAMILY, "Ask: Who is this? Say: This is my grandma.", "".join(b), unit=UNIT)


def p7():
    people = ["mom", "dad", "sister", "brother", "baby", "grandpa"]
    shuffled = ["baby", "grandpa", "mom", "brother", "dad", "sister"]
    b = []
    for i, who in enumerate(people):
        y = 300 + i * 106
        cid = _cid()
        b.append(f'<circle cx="185" cy="{y}" r="50" {st()}/>'
                 f'<clipPath id="{cid}"><circle cx="185" cy="{y}" r="{50-LINE/2}"/></clipPath>'
                 f'<g clip-path="url(#{cid})">{bust(185, y - 6, 27, who, y + 60)}</g>'
                 f'<circle cx="185" cy="{y}" r="50" {ln()}/>')
        b.append(f'<circle cx="290" cy="{y}" r="9" fill="{INK}"/>')
    for i, wd in enumerate(shuffled):
        y = 300 + i * 106
        b.append(f'<circle cx="540" cy="{y}" r="9" fill="{INK}"/>')
        b.append(f'<rect x="570" y="{y-36}" width="220" height="72" rx="36" {st(FINE+1)}/>')
        b.append(text(680, y + 12, wd, size=34))
    b.append(text(W / 2, 938, "This is my ________.", size=34))
    return page(7, "SAY", "Who Is It?", "Point. Say it. Match.",
                FAMILY, "Point to the baby. Say: This is my baby.", "".join(b), unit=UNIT)


def _shirt(cx, cy, s):
    return (f'<path d="M{cx-14*s},{cy-18*s} L{cx-30*s},{cy-10*s} L{cx-38*s},{cy+4*s} L{cx-24*s},{cy+10*s} '
            f'L{cx-22*s},{cy+26*s} L{cx+22*s},{cy+26*s} L{cx+24*s},{cy+10*s} L{cx+38*s},{cy+4*s} '
            f'L{cx+30*s},{cy-10*s} L{cx+14*s},{cy-18*s} Q{cx},{cy-8*s} {cx-14*s},{cy-18*s} Z" {st(FINE)}/>')


def p8():
    b = []
    # sky
    b.append(f'<circle cx="640" cy="330" r="42" {st()}/>')
    for k in range(10):
        a = k * math.pi / 5
        b.append(f'<line x1="{640+56*math.cos(a):.0f}" y1="{330+56*math.sin(a):.0f}" '
                 f'x2="{640+80*math.cos(a):.0f}" y2="{330+80*math.sin(a):.0f}" {ln(FINE+1)}/>')
    b.append(f'<path d="M250,360 a34,34 0 0 1 20,-58 a44,44 0 0 1 80,-6 a32,32 0 0 1 44,40 a26,26 0 0 1 -6,24 Z" {st()}/>')
    # ground and picnic blanket
    b.append(f'<path d="M40,760 Q425,735 810,760" {ln()}/>')
    bl = [(275, 770), (590, 770), (640, 880), (225, 880)]
    b.append(f'<polygon points="{" ".join(f"{x},{y}" for x, y in bl)}" {st()}/>')
    for t in (1 / 3, 2 / 3):
        x0, x1 = 275 + (590 - 275) * t, 225 + (640 - 225) * t
        b.append(f'<line x1="{x0}" y1="770" x2="{x1}" y2="880" {ln(FINE)}/>')
    b.append(f'<line x1="{250}" y1="825" x2="{615}" y2="825" {ln(FINE)}/>')
    # family
    b.append(adult(132, 478, 1.0, "grandpa", "pants", with_hat=True))
    b.append(adult(718, 478, 1.0, "mom", "dress"))
    b.append(child(330, 545, 0.72, "happy", "puffs"))
    # basket on the blanket
    b.append(f'<path d="M520,772 a42,42 0 0 1 84,0" {ln(FINE+1)}/>'
             f'<path d="M506,772 h112 l-12,52 h-88 Z" {st()}/>'
             f'<line x1="512" y1="798" x2="612" y2="798" {ln(FINE)}/>')
    # baby on its own blanket
    b.append(f'<rect x="395" y="822" width="190" height="72" rx="14" transform="rotate(-4 490 858)" {st()}/>')
    b.append(f'<ellipse cx="505" cy="856" rx="62" ry="24" {st()}/>'
             f'<path d="M480,834 Q490,856 480,878" {ln(FINE)}/>')
    b.append(head(435, 852, 27, "baby"))
    # color key
    key = [("hat", "green"), ("blanket", "yellow"), ("dress", "red"), ("shirt", "blue")]
    for i, (thing, color) in enumerate(key):
        x = 62 + i * 192
        cy = 935
        if thing == "hat":
            b.append(hat(x + 30, cy + 10, 20))
        elif thing == "blanket":
            b.append(f'<rect x="{x+4}" y="{cy-14}" width="52" height="30" rx="6" {st(FINE)}/>')
        elif thing == "dress":
            b.append(f'<path d="M{x+20},{cy-20} h20 l4,12 l12,26 h-52 l12,-26 Z" {st(FINE)}/>')
        else:
            b.append(_shirt(x + 30, cy - 2, 0.78))
        b.append(text(x + 68, cy + 10, f"= {color}", size=24, anchor="start"))
    return page(8, "COLOR", "Family Picnic", "Listen. Color the clothes.",
                ["grandpa", "baby", "mom", "sister", "green", "yellow", "red", "blue"],
                "Read one at a time: Color grandpa's hat green.", "".join(b), unit=UNIT)


def p9():
    b = []
    # refrigerator
    b.append(f'<rect x="60" y="262" width="330" height="690" rx="26" {st()}/>')
    b.append(f'<line x1="60" y1="470" x2="390" y2="470" {ln()}/>')
    b.append(f'<rect x="352" y="300" width="18" height="130" rx="9" {st(FINE)}/>')
    b.append(f'<rect x="352" y="500" width="18" height="170" rx="9" {st(FINE)}/>')
    b.append(f'<rect x="90" y="952" width="40" height="18" rx="4" {st(FINE)}/>'
             f'<rect x="320" y="952" width="40" height="18" rx="4" {st(FINE)}/>')
    magnets = [(145, 366, "M"), (275, 366, "m"), (145, 568, "m"), (275, 568, "M"), (145, 698, "M"), (275, 698, "m")]
    for x, y, ch in magnets:
        b.append(f'<rect x="{x-52}" y="{y-52}" width="104" height="104" rx="18" {st()}/>')
        b.append(dotted(x, y + 33, ch, size=96, anchor="middle"))
    # a drawing held by a round magnet: I love my mom
    b.append(f'<rect x="110" y="785" width="215" height="140" rx="4" transform="rotate(-3 217 855)" {st(FINE+1)}/>')
    b.append(heart(217, 858, 44))
    b.append(f'<circle cx="217" cy="790" r="14" {st(FINE)}/>')
    # right column: sound, words, frame
    b.append(text(625, 302, "Mm says /m/", size=30))
    b.append(ruled(450, 322, 350, 90) + dotted(462, 408, "Mm", size=100))
    b.append(ruled(450, 442, 350, 90) + dotted(462, 528, "mom", size=100))
    b.append(head(505, 612, 36, "mom") + text(505, 700, "mom", size=26))
    b.append(head(625, 612, 36, "me") + text(625, 700, "me", size=26))
    b.append(milk(745, 660, 0.85) + text(745, 700, "milk", size=26))
    b.append(text(625, 752, "Trace:", size=28))
    b.append(ruled(450, 770, 350, 70) + dotted(458, 838, "I love my", size=58))
    b.append(ruled(450, 868, 350, 70) + dotted(458, 936, "mom.", size=58))
    return page(9, "TRACE", "M is for Mom", "Trace the magnets. Say /m/.",
                ["mom", "me", "milk", "love"], "Mm says /m/. Mom, me, milk. What else starts with /m/?",
                "".join(b), unit=UNIT)


def p10():
    b = []
    b.append(f'<rect x="590" y="282" width="56" height="90" {st()}/>')
    b.append(f'<rect x="580" y="270" width="76" height="22" rx="4" {st()}/>')
    b.append(f'<polygon points="75,392 425,262 775,392" {st()}/>')
    b.append(f'<rect x="110" y="392" width="630" height="308" {st()}/>')
    for row in range(2):
        for col in range(3):
            x, y = 140 + col * 200, 412 + row * 146
            b.append(f'<rect x="{x}" y="{y}" width="170" height="126" rx="6" {st()}/>')
    b.append(f'<circle cx="425" cy="335" r="30" {st(FINE+1)}/>')
    b.append(heart(425, 338, 16, w=FINE))
    b.append(text(50, 802, "This is my", size=34, anchor="start"))
    b.append(ruled(250, 727, 555, 75))
    b.append(text(50, 894, "I love my", size=34, anchor="start"))
    b.append(ruled(250, 819, 555, 75))
    for i, wd in enumerate(FAMILY):
        x = 40 + i * 111.4
        b.append(f'<rect x="{x}" y="{915}" width="102" height="52" rx="14" {st(FINE)}/>')
        b.append(text(x + 51, 949, wd, size=21))
    return page(10, "USE", "My Family", "Draw your family. Write.",
                FAMILY, "Tell me about your family. Home words are welcome, then say it in English.",
                "".join(b), unit=UNIT)


PAGES = [("u2_p06_see", p6), ("u2_p07_say", p7), ("u2_p08_color", p8), ("u2_p09_trace", p9), ("u2_p10_use", p10)]


def main():
    for name, fn in PAGES:
        (OUT / f"{name}.svg").write_text(fn(), encoding="utf-8")
    print(f"wrote {len(PAGES)} Unit 2 pages to {OUT}")


if __name__ == "__main__":
    main()

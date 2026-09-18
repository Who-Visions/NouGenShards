"""
nougen_vector_art.py - Master High-Precision Vector SVG Drawing Engine
for "Learn With Mrs. B: ESOL Coloring & Activity Masterclass".

100% PURE BLACK AND WHITE LINE ART (No Grayscale, No Color Fills).
Standards:
- Coco Wyo Bold & Easy (4.5pt main silhouettes, 2.5pt interior details)
- Anti-overwhelm open fills (fill="#fff" stroke="#111")
- Official NouGenArt Model Sheets:
  * Mrs. B (High textured afro-puff bun, hoop earrings, open cardigan, B badge, book, wide trousers, Chucks)
  * Curious (Granddaughter with twin space buns, Hello Kitty pinafore / pink tee, charm Crocs)
  * Brave (Grandson with rescue cap, badge vest, sneakers)
  * Creative (Space shirt) & Kind (Hijab)
  * Shape Friends (Circle, Square, Triangle, Star with expressive faces & limbs)
  * Cultural Food Icons (Plantain, Rice, Apple, Milk, Bread)
  * Classroom Props (Books, Crayons, Desks, Backpacks)
  * Miniature Pony & Farm Animals
"""

import math

W, H = 850, 1100
INK = "#111"
LINE = 5.0        # Bold outer contours (Coco Wyo standard)
FINE = 2.8        # Inner secondary details
THIN = 1.8        # Subtle texture lines
FONT = "'Arial Rounded MT Bold','Nunito','Arial',sans-serif"
HEAVY = "'Arial Black','Arial',sans-serif"

def st(w=LINE, f="#fff"):
    """Standard stroke & fill (pure black and white)."""
    return f'fill="{f}" stroke="{INK}" stroke-width="{w}" stroke-linejoin="round" stroke-linecap="round"'

def ln(w=FINE):
    """Open line stroke without fill."""
    return f'fill="none" stroke="{INK}" stroke-width="{w}" stroke-linejoin="round" stroke-linecap="round"'

def text(x, y, s, size=28, anchor="middle", weight="700", fam=FONT, fill=INK):
    s = str(s).replace("&", "&amp;")
    return (f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" fill="{fill}">{s}</text>')

def hollow(x, y, s, size=76, anchor="middle"):
    """Open coloring outline text."""
    s = str(s).replace("&", "&amp;")
    return (f'<text x="{x}" y="{y}" font-family="{HEAVY}" font-size="{size}" text-anchor="{anchor}" '
            f'fill="#fff" stroke="{INK}" stroke-width="4.5" stroke-linejoin="round">{s}</text>')

def dotted(x, y, s, size=88, anchor="start"):
    """Dotted/dashed trace letters."""
    s = str(s).replace("&", "&amp;")
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="700" text-anchor="{anchor}" '
            f'fill="none" stroke="{INK}" stroke-width="2.5" stroke-dasharray="4 6">{s}</text>')

def ruled(x, y, w, h=96):
    """K-1 handwriting practice guidelines."""
    return (f'<line x1="{x}" y1="{y}" x2="{x+w}" y2="{y}" stroke="{INK}" stroke-width="2.5"/>'
            f'<line x1="{x}" y1="{y+h/2}" x2="{x+w}" y2="{y+h/2}" stroke="{INK}" stroke-width="2" stroke-dasharray="10 8"/>'
            f'<line x1="{x}" y1="{y+h}" x2="{x+w}" y2="{y+h}" stroke="{INK}" stroke-width="3.5"/>')

def star(cx, cy, r, w=LINE):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.46
        a = math.pi / 2 + i * math.pi / 5
        pts.append(f"{cx + rr*math.cos(a):.1f},{cy - rr*math.sin(a):.1f}")
    return f'<polygon points="{" ".join(pts)}" {st(w)}/>'

def crayon(x, y, length=150, angle=0, w=LINE, th=28):
    t = f'transform="rotate({angle} {x} {y})"'
    body, h, band = length * 0.72, th / 2, length * 0.12
    return (f'<g {t}><rect x="{x}" y="{y-h}" width="{body}" height="{th}" rx="{th*0.2}" {st(w)}/>'
            f'<line x1="{x+band}" y1="{y-h}" x2="{x+band}" y2="{y+h}" {ln(FINE)}/>'
            f'<line x1="{x+body-band}" y1="{y-h}" x2="{x+body-band}" y2="{y+h}" {ln(FINE)}/>'
            f'<polygon points="{x+body},{y-h*0.86} {x+length},{y} {x+body},{y+h*0.86}" {st(w)}/></g>')

# ----------------------------------------------------------------- CHARACTERS

def mrs_b_standing(cx, top, s=1.0, arm="wave", holds=None, expr="happy"):
    """
    Official NouGenArt Mrs. B Character Vector Model.
    - High coiled afro-puff bun with texture loops
    - Gold hoop earrings & friendly eyes with lashes
    - Open cardigan with deep patch pockets over black crewneck
    - Teacher lanyard with rectangular badge ('B' + heart)
    - Held notebook ('Kind English Brighter Futures')
    - Wide-leg trousers & classic low-top canvas sneakers (Chucks)
    """
    r = 54 * s
    hy = top + r * 1.35
    out = []
    
    # 1. Hair: High Coiled Afro-Puff Bun
    bun_y = hy - r * 1.15
    bun_r = r * 0.85
    # Hair base outline
    out.append(f'<ellipse cx="{cx}" cy="{bun_y}" rx="{bun_r*1.15}" ry="{bun_r}" {st(LINE)}/>')
    # Textured curly ring loops along the perimeter
    for angle_deg in range(0, 360, 40):
        rad = math.radians(angle_deg)
        lx = cx + (bun_r * 1.05) * math.cos(rad)
        ly = bun_y + (bun_r * 0.9) * math.sin(rad)
        out.append(f'<circle cx="{lx}" cy="{ly}" r="{r*0.24}" {st(FINE)}/>')
    for dx, dy in ((-0.35, -0.2), (0.35, -0.2), (0, 0.25), (-0.4, 0.3), (0.4, 0.3)):
        out.append(f'<circle cx="{cx + r*dx}" cy="{bun_y + r*dy}" r="{r*0.22}" {st(FINE)}/>')
    # Hairband / scrunchie
    out.append(f'<ellipse cx="{cx}" cy="{hy - r*0.75}" rx="{r*0.65}" ry="{r*0.18}" {st(FINE+0.5)}/>')
    
    # 2. Lower Body: Wide-Leg Trousers & Chucks Sneakers
    body_top = hy + r * 0.95
    waist_y = body_top + 130 * s
    crotch_y = waist_y + 60 * s
    pant_bot_y = waist_y + 240 * s
    pw = 68 * s
    
    # Left Leg & Right Leg Trousers
    for side in (-1, 1):
        px = cx + side * (pw * 0.52)
        # Pant leg outline
        out.append(f'<path d="M{cx + side*8*s},{crotch_y} L{px - side*pw*0.48},{pant_bot_y} '
                   f'L{px + side*pw*0.48},{pant_bot_y} L{cx + side*pw*0.95},{waist_y} Z" {st(LINE)}/>')
        # Pant cuff
        out.append(f'<line x1="{px - side*pw*0.48}" y1="{pant_bot_y}" x2="{px + side*pw*0.48}" y2="{pant_bot_y}" {ln(FINE)}/>')
        # Sneaker (Chuck Taylor Low-Top Style)
        sx = px
        sy = pant_bot_y
        out.append(f'<path d="M{sx - 28*s},{sy} L{sx + 32*s},{sy} Q{sx + 40*s},{sy + 20*s} {sx + 30*s},{sy + 36*s} '
                   f'L{sx - 28*s},{sy + 36*s} Q{sx - 34*s},{sy + 18*s} {sx - 28*s},{sy} Z" {st(LINE)}/>')
        # Rubber toe bumper
        out.append(f'<path d="M{sx + 14*s},{sy + 10*s} Q{sx + 32*s},{sy + 18*s} {sx + 24*s},{sy + 36*s}" {ln(FINE)}/>')
        # Sole bottom line
        out.append(f'<line x1="{sx - 32*s}" y1="{sy + 30*s}" x2="{sx + 36*s}" y2="{sy + 30*s}" {ln(FINE)}/>')
        # Laces
        out.append(f'<line x1="{sx - 10*s}" y1="{sy + 8*s}" x2="{sx + 6*s}" y2="{sy + 16*s}" {ln(THIN)}/>')
        out.append(f'<line x1="{sx - 10*s}" y1="{sy + 16*s}" x2="{sx + 6*s}" y2="{sy + 8*s}" {ln(THIN)}/>')
    
    # Belt & Waistband
    out.append(f'<rect x="{cx - pw*0.9}" y="{waist_y - 12*s}" width="{pw*1.8}" height="{14*s}" rx="{4*s}" {st(FINE)}/>')
    out.append(f'<rect x="{cx - 10*s}" y="{waist_y - 14*s}" width="{20*s}" height="{18*s}" rx="{3*s}" {st(FINE+1)}/>')
    
    # 3. Torso: Crewneck Shirt & Open Cardigan
    bw = 140 * s
    cardigan_bot = waist_y + 40 * s
    
    # Cardigan Back/Outer Outline
    out.append(f'<path d="M{cx - bw/2},{body_top + 22*s} Q{cx - bw/2},{body_top} {cx - bw/2 + 28*s},{body_top} '
               f'L{cx + bw/2 - 28*s},{body_top} Q{cx + bw/2},{body_top} {cx + bw/2},{body_top + 22*s} '
               f'L{cx + bw*0.52},{cardigan_bot} L{cx - bw*0.52},{cardigan_bot} Z" {st(LINE)}/>')
    
    # Cardigan Open Front Lapels (showing inner top)
    lapel_w = 26 * s
    out.append(f'<path d="M{cx - lapel_w},{body_top} L{cx - lapel_w*0.8},{cardigan_bot} L{cx - bw*0.52},{cardigan_bot} '
               f'L{cx - bw/2},{body_top + 22*s} Z" {st(FINE)}/>')
    out.append(f'<path d="M{cx + lapel_w},{body_top} L{cx + lapel_w*0.8},{cardigan_bot} L{cx + bw*0.52},{cardigan_bot} '
               f'L{cx + bw/2},{body_top + 22*s} Z" {st(FINE)}/>')
    
    # Cardigan Deep Patch Pockets
    out.append(f'<rect x="{cx - bw*0.46}" y="{waist_y - 10*s}" width="{36*s}" height="{44*s}" rx="{6*s}" {st(FINE)}/>')
    out.append(f'<rect x="{cx + bw*0.46 - 36*s}" y="{waist_y - 10*s}" width="{36*s}" height="{44*s}" rx="{6*s}" {st(FINE)}/>')
    
    # Teacher Lanyard & "B ♡" Badge
    lanyard_y = body_top + 2*s
    badge_y = body_top + 82*s
    out.append(f'<path d="M{cx - 16*s},{lanyard_y} L{cx},{badge_y} L{cx + 16*s},{lanyard_y}" {ln(FINE+0.5)}/>')
    # Metal clip
    out.append(f'<rect x="{cx - 5*s}" y="{badge_y}" width="{10*s}" height="{8*s}" rx="{2*s}" {st(FINE)}/>')
    # Rectangular ID Badge
    out.append(f'<rect x="{cx - 18*s}" y="{badge_y + 8*s}" width="{36*s}" height="{48*s}" rx="{5*s}" {st(LINE)}/>')
    out.append(f'<circle cx="{cx}" cy="{badge_y + 14*s}" r="{3*s}" fill="{INK}"/>')
    out.append(text(cx, badge_y + 36*s, "B", size=int(22*s), fam=HEAVY))
    out.append(text(cx, badge_y + 48*s, "♡", size=int(12*s), fam=FONT))
    
    # 4. Arms & Held Book
    sh_y = body_top + 26 * s
    lh_pos = (cx - bw * 0.44, sh_y + 115 * s)
    rh_pos = (cx + bw * 0.44 + 40 * s, sh_y - 80 * s)
    
    # Right Arm: Welcoming Wave
    if arm == "wave":
        out.append(f'<path d="M{cx + bw*0.44},{sh_y} Q{cx + bw*0.62},{sh_y - 20*s} {rh_pos[0]},{rh_pos[1]}" '
                   f'stroke="{INK}" stroke-width="{32*s+LINE}" stroke-linecap="round" fill="none"/>')
        out.append(f'<path d="M{cx + bw*0.44},{sh_y} Q{cx + bw*0.62},{sh_y - 20*s} {rh_pos[0]},{rh_pos[1]}" '
                   f'stroke="#fff" stroke-width="{32*s-LINE+2}" stroke-linecap="round" fill="none"/>')
        # Open Waving Hand with 5 fingers
        hx, hy_hand = rh_pos
        out.append(f'<circle cx="{hx}" cy="{hy_hand}" r="{16*s}" {st(FINE)}/>')
        for fi, f_ang in enumerate((-40, -15, 10, 35, 60)):
            frad = math.radians(f_ang)
            fx = hx + 22 * s * math.sin(frad)
            fy = hy_hand - 22 * s * math.cos(frad)
            out.append(f'<line x1="{hx}" y1="{hy_hand}" x2="{fx}" y2="{fy}" stroke="{INK}" stroke-width="{7*s}" stroke-linecap="round"/>')
            out.append(f'<line x1="{hx}" y1="{hy_hand}" x2="{fx}" y2="{fy}" stroke="#fff" stroke-width="{7*s-3}" stroke-linecap="round"/>')
    
    # Left Arm: Holding Hardbound Book against hip
    out.append(f'<path d="M{cx - bw*0.44},{sh_y} Q{cx - bw*0.58},{sh_y + 50*s} {lh_pos[0]},{lh_pos[1]}" '
               f'stroke="{INK}" stroke-width="{32*s+LINE}" stroke-linecap="round" fill="none"/>')
    out.append(f'<path d="M{cx - bw*0.44},{sh_y} Q{cx - bw*0.58},{sh_y + 50*s} {lh_pos[0]},{lh_pos[1]}" '
               f'stroke="#fff" stroke-width="{32*s-LINE+2}" stroke-linecap="round" fill="none"/>')
    
    # Book: "Kind English Brighter Futures ♡"
    bx, by = lh_pos[0] - 10 * s, lh_pos[1] - 40 * s
    bwk, bhk = 72 * s, 98 * s
    out.append(f'<g transform="rotate(-8 {bx} {by})">')
    out.append(f'<rect x="{bx - bwk/2}" y="{by}" width="{bwk}" height="{bhk}" rx="{6*s}" {st(LINE)}/>')
    out.append(f'<rect x="{bx - bwk/2 + 8*s}" y="{by + 8*s}" width="{bwk - 16*s}" height="{bhk - 16*s}" rx="{4*s}" {ln(FINE)}/>')
    out.append(text(bx, by + 30*s, "Kind", size=int(14*s), fam=HEAVY))
    out.append(text(bx, by + 46*s, "English", size=int(12*s), fam=HEAVY))
    out.append(text(bx, by + 62*s, "Brighter", size=int(11*s), fam=HEAVY))
    out.append(text(bx, by + 76*s, "Futures ♡", size=int(10*s), fam=FONT))
    out.append(f'</g>')
    # Left hand gripping book
    out.append(f'<ellipse cx="{lh_pos[0]}" cy="{lh_pos[1] + 10*s}" rx="{14*s}" ry="{12*s}" {st(FINE+1)}/>')
    
    # 5. Neck & Face
    out.append(f'<rect x="{cx - 15*s}" y="{hy + r*0.75}" width="{30*s}" height="{r*0.38}" {st(FINE)}/>')
    # Head circle
    out.append(f'<circle cx="{cx}" cy="{hy}" r="{r}" {st(LINE)}/>')
    
    # Gold Hoop Earrings
    for side in (-1, 1):
        out.append(f'<circle cx="{cx + side*r*1.04}" cy="{hy + r*0.35}" r="{r*0.22}" {st(FINE+1)}/>')
        out.append(f'<circle cx="{cx + side*r*1.04}" cy="{hy + r*0.35}" r="{r*0.14}" fill="#fff" stroke="{INK}" stroke-width="{FINE}"/>')
    
    # Eyes & Eyebrows with Lashes
    for side in (-1, 1):
        ex = cx + side * r * 0.38
        ey = hy - r * 0.06
        # Eyebrow arch
        out.append(f'<path d="M{ex - side*r*0.22},{ey - r*0.28} Q{ex},{ey - r*0.42} {ex + side*r*0.22},{ey - r*0.25}" {ln(FINE+1)}/>')
        # Eye outline
        out.append(f'<ellipse cx="{ex}" cy="{ey}" rx="{r*0.22}" ry="{r*0.16}" {st(FINE+1)}/>')
        # Iris & Pupil
        out.append(f'<circle cx="{ex + side*2*s}" cy="{ey}" r="{r*0.11}" fill="{INK}"/>')
        # Specular light highlight
        out.append(f'<circle cx="{ex + side*2*s - 2*s}" cy="{ey - 2*s}" r="{r*0.04}" fill="#fff"/>')
        # Eyelashes
        out.append(f'<line x1="{ex + side*r*0.18}" y1="{ey - r*0.12}" x2="{ex + side*r*0.28}" y2="{ey - r*0.22}" {ln(FINE)}/>')
    
    # Cute Button Nose
    out.append(f'<path d="M{cx - 5*s},{hy + r*0.18} Q{cx},{hy + r*0.24} {cx + 5*s},{hy + r*0.18}" {ln(FINE)}/>')
    
    # Warm Encouraging Smile
    out.append(f'<path d="M{cx - r*0.42},{hy + r*0.38} Q{cx},{hy + r*0.82} {cx + r*0.42},{hy + r*0.38} Z" {st(FINE+1)}/>')
    # Teeth line
    out.append(f'<line x1="{cx - r*0.34}" y1="{hy + r*0.44}" x2="{cx + r*0.34}" y2="{hy + r*0.44}" {ln(FINE)}/>')
    
    return "".join(out)


def curious_granddaughter(cx, top, s=0.95, arm="wave", holds=None, outfit="pinafore"):
    """
    Official NouGenArt Mrs. B's Granddaughter ('Curious') Vector Model.
    - Twin high coiled afro puff buns ('Space Buns') with pearl earrings
    - Hello Kitty scalloped pinafore dress or pink tee & shorts
    - Light blue/lavender Crocs with charms (Jibbitz)
    - Pink heart backpack
    """
    r = 44 * s
    hy = top + r * 1.3
    out = []
    
    # 1. Hair: High Twin Afro-Puff Buns (Space Buns)
    for side in (-1, 1):
        bx = cx + side * r * 1.15
        by = hy - r * 0.95
        br = r * 0.65
        out.append(f'<circle cx="{bx}" cy="{by}" r="{br}" {st(LINE)}/>')
        for adeg in range(0, 360, 45):
            rad = math.radians(adeg)
            out.append(f'<circle cx="{bx + br*math.cos(rad)}" cy="{by + br*math.sin(rad)}" r="{r*0.2}" {st(FINE)}/>')
        # Hair scrunchie band
        out.append(f'<ellipse cx="{cx + side*r*0.75}" cy="{hy - r*0.55}" rx="{r*0.25}" ry="{r*0.12}" {st(FINE)}/>')
    
    # 2. Lower Body & Crocs
    body_top = hy + r * 0.95
    dress_bot = body_top + 140 * s
    feet_y = dress_bot + 100 * s
    
    # Legs
    for side in (-1, 1):
        lx = cx + side * 24 * s
        out.append(f'<rect x="{lx - 12*s}" y="{dress_bot - 10*s}" width="{24*s}" height="{90*s}" rx="{8*s}" {st(LINE)}/>')
        # Cute Crocs Shoe (with holes & charms)
        cx_shoe = lx + side * 4 * s
        cy_shoe = feet_y
        out.append(f'<path d="M{cx_shoe - 24*s},{cy_shoe} Q{cx_shoe - 28*s},{cy_shoe - 14*s} {cx_shoe + 8*s},{cy_shoe - 14*s} '
                   f'Q{cx_shoe + 30*s},{cy_shoe - 10*s} {cx_shoe + 28*s},{cy_shoe + 18*s} L{cx_shoe - 24*s},{cy_shoe + 18*s} Z" {st(LINE)}/>')
        # Croc strap
        out.append(f'<path d="M{cx_shoe - 18*s},{cy_shoe - 2*s} Q{cx_shoe - 6*s},{cy_shoe - 12*s} {cx_shoe + 10*s},{cy_shoe - 2*s}" {ln(FINE)}/>')
        # Ventilation holes
        for hx, hy_h in ((-6, 2), (6, 0), (16, 4), (2, 8)):
            out.append(f'<circle cx="{cx_shoe + hx*s}" cy="{cy_shoe + hy_h*s}" r="{2.5*s}" {st(THIN)}/>')
        # Jibbitz charm (heart/star)
        out.append(f'<circle cx="{cx_shoe + 10*s}" cy="{cy_shoe + 2*s}" r="{5*s}" {st(FINE+0.5)}/>')
    
    # 3. Torso: Hello Kitty Pinafore Dress & Striped Undershirt
    bw = 96 * s
    # Striped Undershirt Shoulders
    out.append(f'<rect x="{cx - bw/2}" y="{body_top}" width="{bw}" height="{50*s}" rx="{10*s}" {st(LINE)}/>')
    for si in range(1, 4):
        out.append(f'<line x1="{cx - bw/2}" y1="{body_top + si*12*s}" x2="{cx + bw/2}" y2="{body_top + si*12*s}" {ln(FINE)}/>')
    
    # Pinafore Dress (A-line with scalloped hem)
    out.append(f'<path d="M{cx - bw*0.38},{body_top + 30*s} L{cx - bw*0.62},{dress_bot} '
               f'L{cx + bw*0.62},{dress_bot} L{cx + bw*0.38},{body_top + 30*s} Z" {st(LINE)}/>')
    
    # Hello Kitty Face Emblem on bib
    hk_cx, hk_cy = cx, body_top + 60 * s
    out.append(f'<ellipse cx="{hk_cx}" cy="{hk_cy}" rx="{24*s}" ry="{18*s}" {st(FINE+1)}/>')
    # HK Ears
    out.append(f'<polygon points="{hk_cx - 20*s},{hk_cy - 12*s} {hk_cx - 24*s},{hk_cy - 24*s} {hk_cx - 10*s},{hk_cy - 16*s}" {st(FINE)}/>')
    out.append(f'<polygon points="{hk_cx + 20*s},{hk_cy - 12*s} {hk_cx + 24*s},{hk_cy - 24*s} {hk_cx + 10*s},{hk_cy - 16*s}" {st(FINE)}/>')
    # HK Bow
    out.append(f'<circle cx="{hk_cx + 18*s}" cy="{hk_cy - 16*s}" r="{5*s}" {st(FINE+1)}/>')
    # Scalloped Apple Border at Hem
    scallop_w = bw * 1.24 / 6
    for sci in range(6):
        sc_x = cx - bw*0.62 + sci * scallop_w + scallop_w/2
        out.append(f'<path d="M{sc_x - scallop_w/2},{dress_bot} Q{sc_x},{dress_bot + 10*s} {sc_x + scallop_w/2},{dress_bot}" {ln(FINE)}/>')
        # Little apple icon
        out.append(f'<circle cx="{sc_x}" cy="{dress_bot - 8*s}" r="{4*s}" {st(THIN)}/>')
    
    # 4. Arms & Backpack
    # Pink Backpack Straps
    out.append(f'<path d="M{cx - bw*0.35},{body_top + 10*s} Q{cx - bw*0.48},{body_top + 45*s} {cx - bw*0.38},{body_top + 80*s}" {ln(FINE+1)}/>')
    out.append(f'<path d="M{cx + bw*0.35},{body_top + 10*s} Q{cx + bw*0.48},{body_top + 45*s} {cx + bw*0.38},{body_top + 80*s}" {ln(FINE+1)}/>')
    
    # Waving Right Arm
    out.append(f'<line x1="{cx + bw*0.44}" y1="{body_top + 20*s}" x2="{cx + bw*0.8}" y2="{body_top - 50*s}" '
               f'stroke="{INK}" stroke-width="{24*s+LINE}" stroke-linecap="round"/>')
    out.append(f'<line x1="{cx + bw*0.44}" y1="{body_top + 20*s}" x2="{cx + bw*0.8}" y2="{body_top - 50*s}" '
               f'stroke="#fff" stroke-width="{24*s-LINE+2}" stroke-linecap="round"/>')
    out.append(f'<circle cx="{cx + bw*0.8}" cy="{body_top - 50*s}" r="{14*s}" {st(FINE)}/>')
    
    # Left Arm: Down by side
    out.append(f'<line x1="{cx - bw*0.44}" y1="{body_top + 20*s}" x2="{cx - bw*0.65}" y2="{body_top + 70*s}" '
               f'stroke="{INK}" stroke-width="{24*s+LINE}" stroke-linecap="round"/>')
    out.append(f'<line x1="{cx - bw*0.44}" y1="{body_top + 20*s}" x2="{cx - bw*0.65}" y2="{body_top + 70*s}" '
               f'stroke="#fff" stroke-width="{24*s-LINE+2}" stroke-linecap="round"/>')
    out.append(f'<circle cx="{cx - bw*0.65}" cy="{body_top + 70*s}" r="{14*s}" {st(FINE)}/>')
    
    # 5. Neck & Face
    out.append(f'<rect x="{cx - 10*s}" y="{hy + r*0.75}" width="{20*s}" height="{r*0.3}" {st(FINE)}/>')
    out.append(f'<circle cx="{cx}" cy="{hy}" r="{r}" {st(LINE)}/>')
    
    # Pearl Stud Earrings
    for side in (-1, 1):
        out.append(f'<circle cx="{cx + side*r*0.98}" cy="{hy + r*0.25}" r="{r*0.1}" {st(FINE+0.5)}/>')
    
    # Big Cute Eyes & Smile
    for side in (-1, 1):
        ex = cx + side * r * 0.36
        ey = hy - r * 0.05
        out.append(f'<path d="M{ex - side*r*0.18},{ey - r*0.25} Q{ex},{ey - r*0.36} {ex + side*r*0.18},{ey - r*0.22}" {ln(FINE)}/>')
        out.append(f'<circle cx="{ex}" cy="{ey}" r="{r*0.22}" {st(FINE+1)}/>')
        out.append(f'<circle cx="{ex + side*2*s}" cy="{ey}" r="{r*0.14}" fill="{INK}"/>')
        out.append(f'<circle cx="{ex + side*2*s - 2*s}" cy="{ey - 2*s}" r="{r*0.05}" fill="#fff"/>')
    
    # Sweet Open Child Smile
    out.append(f'<path d="M{cx - r*0.36},{hy + r*0.35} Q{cx},{hy + r*0.8} {cx + r*0.36},{hy + r*0.35} Z" {st(FINE+1)}/>')
    
    return "".join(out)


def shape_friend(kind, cx, cy, r=40, expr="happy"):
    """Animated Shape Friends (Circle, Square, Triangle, Star) with cute faces & limbs."""
    out = []
    # Body
    if kind == "circle":
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" {st(LINE)}/>')
    elif kind == "square":
        out.append(f'<rect x="{cx - r}" y="{cy - r}" width="{r*2}" height="{r*2}" rx="{12}" {st(LINE)}/>')
    elif kind == "triangle":
        pts = f"{cx},{cy - r*1.1} {cx - r*1.1},{cy + r*0.9} {cx + r*1.1},{cy + r*0.9}"
        out.append(f'<polygon points="{pts}" {st(LINE)}/>')
    elif kind == "star":
        out.append(star(cx, cy, r*1.2, w=LINE))
    
    # Face (Eyes + Big Happy Open Smile)
    ex, ey = r * 0.35, cy - r * 0.1
    for side in (-1, 1):
        out.append(f'<circle cx="{cx + side*ex}" cy="{ey}" r="{r*0.15}" fill="{INK}"/>')
        out.append(f'<circle cx="{cx + side*ex - 1.5}" cy="{ey - 1.5}" r="{r*0.05}" fill="#fff"/>')
    out.append(f'<path d="M{cx - r*0.32},{cy + r*0.18} Q{cx},{cy + r*0.58} {cx + r*0.32},{cy + r*0.18} Z" {st(FINE+0.5)}/>')
    
    # Limbs (Waving arms + little feet)
    out.append(f'<line x1="{cx - r*0.9}" y1="{cy}" x2="{cx - r*1.4}" y2="{cy - r*0.4}" {ln(FINE+1)}/>')
    out.append(f'<circle cx="{cx - r*1.4}" cy="{cy - r*0.4}" r="{r*0.12}" {st(FINE)}/>')
    out.append(f'<line x1="{cx + r*0.9}" y1="{cy}" x2="{cx + r*1.4}" y2="{cy - r*0.4}" {ln(FINE+1)}/>')
    out.append(f'<circle cx="{cx + r*1.4}" cy="{cy - r*0.4}" r="{r*0.12}" {st(FINE)}/>')
    
    # Feet
    out.append(f'<rect x="{cx - r*0.5}" y="{cy + r*0.9}" width="{r*0.3}" height="{r*0.4}" rx="{4}" {st(FINE)}/>')
    out.append(f'<rect x="{cx + r*0.2}" y="{cy + r*0.9}" width="{r*0.3}" height="{r*0.4}" rx="{4}" {st(FINE)}/>')
    
    return "".join(out)

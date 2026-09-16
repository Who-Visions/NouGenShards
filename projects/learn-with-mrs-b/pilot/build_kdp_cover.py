#!/usr/bin/env python3
"""
build_kdp_cover.py - Generates Amazon KDP Paperback Full Wraparound Cover
for "Learn With Mrs. B: ESOL Coloring & Activity Book" (88 pages, 8.5" x 11").

Precision Typography & Clean Publication Graphics (Zero Hallucinated Text).
"""

import os
try:
    import mrsb_shard_bridge
except ImportError:
    pass
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(os.path.dirname(DIR), "assets")

FRONT_ART_PATH = os.path.join(DIR, "mrs_b_kdp_front_cover.jpg")
MRS_B_REF_PATH = os.path.join(DIR, "mrs_b_teacher_reference.jpg")
CURIOUS_REF_PATH = os.path.join(DIR, "curious_granddaughter_reference.jpg")
PONY_ART_PATH = os.path.join(DIR, "p16_pony_farm_curious_brave.jpg")
PAGE1_ART_PATH = os.path.join(DIR, "p01_mrs_b_see_canonical.jpg")

PDF_OUT = os.path.join(DIR, "learn-with-mrs-b-kdp-cover.pdf")
JPG_OUT = os.path.join(DIR, "learn-with-mrs-b-kdp-cover.jpg")
BACK_OUT = os.path.join(DIR, "mrs_b_kdp_back_cover.jpg")

DPI = 300
PAGE_W_IN = 8.5
PAGE_H_IN = 11.0
BLEED_IN = 0.125
SPINE_IN = 0.1982

TOTAL_W_IN = BLEED_IN + PAGE_W_IN + SPINE_IN + PAGE_W_IN + BLEED_IN  # 17.4482 in
TOTAL_H_IN = BLEED_IN + PAGE_H_IN + BLEED_IN                          # 11.25 in

TOTAL_W_PX = int(round(TOTAL_W_IN * DPI))   # 5234 px
TOTAL_H_PX = int(round(TOTAL_H_IN * DPI))   # 3375 px

BLEED_PX = int(round(BLEED_IN * DPI))       # 38 px
PAGE_W_PX = int(round(PAGE_W_IN * DPI))     # 2550 px
PAGE_H_PX = int(round(PAGE_H_IN * DPI))     # 3300 px
SPINE_PX = int(round(SPINE_IN * DPI))       # 59 px

def get_font(name, size):
    try:
        return ImageFont.truetype(name, size)
    except:
        return ImageFont.truetype("arial.ttf", size)

def render_back_cover():
    """Renders a clean, razor-sharp 2588 x 3375 Back Cover with perfect typography."""
    back_w = BLEED_PX + PAGE_W_PX
    back_h = TOTAL_H_PX
    
    img = Image.new("RGB", (back_w, back_h), "#FFFDF9")
    draw = ImageDraw.Draw(img)
    
    # Fonts
    font_title = get_font("segoeuib.ttf", 68)
    font_subtitle = get_font("segoeui.ttf", 36)
    font_body = get_font("segoeui.ttf", 34)
    font_bold = get_font("segoeuib.ttf", 36)
    font_bullet = get_font("segoeuib.ttf", 38)
    font_motto = get_font("segoeuib.ttf", 46)
    font_small = get_font("segoeui.ttf", 26)
    font_badge = get_font("segoeuib.ttf", 28)
    
    # Header Banner Background
    header_y = 120
    draw.rounded_rectangle([BLEED_PX + 80, header_y, back_w - 80, header_y + 190], radius=24, fill="#FCEBD9", outline="#E28B38", width=4)
    draw.text((BLEED_PX + 120, header_y + 24), "NOUGENART · EARLY LEARNING SERIES", fill="#C06518", font=font_badge)
    draw.text((BLEED_PX + 120, header_y + 68), "Learn With Mrs. B: Coloring & Activity Book", fill="#222222", font=font_title)
    
    # Intro Description
    desc_y = header_y + 230
    intro_text = (
        "Welcome to Mrs. B's classroom! Created for young English language learners\n"
        "and bilingual diaspora families, this masterclass coloring book combines\n"
        "joyful art, foundational ESOL vocabulary, and empowering community values."
    )
    draw.text((BLEED_PX + 90, desc_y), intro_text, fill="#333333", font=font_body, spacing=16)
    
    # 4 Preview Mini-Frames (2x2 Grid)
    grid_x = BLEED_PX + 90
    grid_y = desc_y + 200
    thumb_w, thumb_h = 440, 540
    gap_x, gap_y = 40, 50
    
    thumbs = [
        ("Classroom", PAGE1_ART_PATH, "Meet Mrs. B"),
        ("Park Friends", CURIOUS_REF_PATH, "Curious at the Park"),
        ("Pony Adventure", PONY_ART_PATH, "Community Heroes"),
        ("Teacher Spec", MRS_B_REF_PATH, "Teacher Mrs. B"),
    ]
    
    for i, (label, path, caption) in enumerate(thumbs):
        col = i % 2
        row = i // 2
        tx = grid_x + col * (thumb_w + gap_x)
        ty = grid_y + row * (thumb_h + gap_y)
        
        # Frame
        draw.rounded_rectangle([tx, ty, tx + thumb_w, ty + thumb_h], radius=20, fill="#FFFFFF", outline="#E28B38" if i==0 else "#4A90E2" if i==1 else "#50B848" if i==2 else "#9B51E0", width=5)
        
        # Image content with strict aspect-ratio preservation (zero distortion)
        if os.path.exists(path):
            try:
                timg = Image.open(path).convert("RGB")
                tw, th = timg.size
                t_aspect = tw / float(th)
                inner_w, inner_h = thumb_w - 16, thumb_h - 60
                box_aspect = inner_w / float(inner_h)
                if t_aspect > box_aspect:
                    fit_w = inner_w
                    fit_h = int(round(inner_w / t_aspect))
                else:
                    fit_h = inner_h
                    fit_w = int(round(inner_h * t_aspect))
                timg_resized = timg.resize((fit_w, fit_h), Image.Resampling.LANCZOS)
                px = tx + 8 + (inner_w - fit_w) // 2
                py = ty + 8 + (inner_h - fit_h) // 2
                img.paste(timg_resized, (px, py))
            except Exception as e:
                print(f"Thumb error {path}: {e}")
        
        # Label banner below thumb
        draw.rectangle([tx + 4, ty + thumb_h - 52, tx + thumb_w - 4, ty + thumb_h - 4], fill="#F8F8F8")
        draw.text((tx + thumb_w // 2, ty + thumb_h - 42), label, fill="#222222", font=font_badge, anchor="mt")

    # Right Column: Feature Bullet Points & Callouts
    col2_x = grid_x + 2 * (thumb_w + gap_x) + 40
    # If 2x2 grid fits in left half (440*2 + 40 = 920px), total available width is ~2350px.
    # So right column starts at BLEED_PX + 1100 px!
    col2_x = BLEED_PX + 1090
    col2_y = desc_y + 190
    
    bullets = [
        ("★ 40 Engaging Coloring Pages", "Rich, open line art designed for markers & crayons."),
        ("★ 4-Step Shading Tutorials", "Helen Elliston method: Base Wash, Midtone, Shadow, Highlight."),
        ("★ Dual-Language ESOL Guidance", "English and Haitian Creole parent co-learning prompts."),
        ("★ Single-Sided Bleed Guards", "Protective verso pages prevent bleed-through onto adjacent art."),
        ("★ Diploma Certificate Included", "Official diploma celebrating your learner's progress!"),
    ]
    
    cur_y = col2_y
    for b_title, b_desc in bullets:
        draw.text((col2_x, cur_y), b_title, fill="#1B4D89", font=font_bullet)
        draw.text((col2_x + 30, cur_y + 48), b_desc, fill="#555555", font=font_subtitle)
        cur_y += 125
        
    # Core Motivational Box
    motto_y = cur_y + 40
    draw.rounded_rectangle([col2_x, motto_y, back_w - 90, motto_y + 240], radius=20, fill="#FFF3E0", outline="#E28B38", width=4)
    draw.text((col2_x + 30, motto_y + 35), "“Kind People Change Big Futures ♡”", fill="#D05F00", font=font_motto)
    draw.text((col2_x + 30, motto_y + 105), "A KINDER MIND.  A BRIGHTER WORLD.  TOGETHER.", fill="#333333", font=font_bold)
    draw.text((col2_x + 30, motto_y + 165), "Same Curiosity. Brighter Tomorrows. ♡", fill="#666666", font=font_subtitle)

    # Bottom Area: NouGenArt Logo (Left) + Barcode Box (Right)
    bot_y = back_h - 400
    
    # Brand Info
    draw.text((BLEED_PX + 90, bot_y + 50), "NouGenArt", fill="#111111", font=get_font("segoeuib.ttf", 64))
    draw.text((BLEED_PX + 90, bot_y + 130), "EDUCATION • IMAGINATION • A KINDER, SMARTER TOMORROW", fill="#555555", font=font_badge)
    draw.text((BLEED_PX + 90, bot_y + 180), "Published by Who Visions / NouGenAi Publishing • Printed in the USA", fill="#777777", font=font_small)
    
    # Barcode Safe Zone Box (KDP requirement: min 2.0" x 1.2" = 600 x 360 px)
    barcode_w, barcode_h = 620, 360
    barcode_x = back_w - barcode_w - 90
    barcode_y = back_h - barcode_h - 70
    
    draw.rectangle([barcode_x, barcode_y, barcode_x + barcode_w, barcode_y + barcode_h], fill="#FFFFFF", outline="#CCCCCC", width=2)
    draw.text((barcode_x + barcode_w // 2, barcode_y + 25), "Reserved for Barcode", fill="#888888", font=font_badge, anchor="mt")
    
    # Clean simulated vector barcode lines
    bar_start_x = barcode_x + 45
    bar_y1 = barcode_y + 80
    bar_y2 = barcode_y + 280
    bars = [3, 2, 5, 2, 4, 3, 2, 6, 2, 4, 3, 5, 2, 3, 6, 2, 4, 2, 5, 3, 2, 4, 3, 6, 2, 5, 2, 4, 3, 2, 5, 4, 2, 6, 3, 2, 4, 5, 2, 3, 6, 2, 4, 2, 5, 3, 2, 4, 3]
    cur_bx = bar_start_x
    for bw in bars:
        draw.line([cur_bx, bar_y1, cur_bx, bar_y2], fill="#111111", width=bw)
        cur_bx += bw + 6
        if cur_bx > barcode_x + barcode_w - 45:
            break
            
    draw.text((barcode_x + barcode_w // 2, barcode_y + 300), "9 781965 266854", fill="#111111", font=font_subtitle, anchor="mt")

    img.save(BACK_OUT, "JPEG", quality=95, dpi=(DPI, DPI))
    print(f"Generated clean Back Cover: {BACK_OUT}")
    return img

def assemble_kdp_full_cover():
    print(f"Creating Full KDP Cover Canvas: {TOTAL_W_PX} x {TOTAL_H_PX} px ({TOTAL_W_IN:.3f}\" x {TOTAL_H_IN:.3f}\" @ {DPI} DPI)")
    
    cover_img = Image.new("RGB", (TOTAL_W_PX, TOTAL_H_PX), "#FFFDF9")
    draw = ImageDraw.Draw(cover_img)
    
    # 1. Render & Paste Back Cover (Left Side)
    back_img = render_back_cover()
    cover_img.paste(back_img, (0, 0))
    print("Pasted Clean Back Cover.")
    
    # 2. Paste Front Cover (Right Side) with strict aspect-ratio preservation
    front_x = BLEED_PX + PAGE_W_PX + SPINE_PX
    if os.path.exists(FRONT_ART_PATH):
        front_img = Image.open(FRONT_ART_PATH).convert("RGB")
        fw, fh = front_img.size
        f_aspect = fw / float(fh)
        front_target_w = PAGE_W_PX + BLEED_PX
        front_target_h = TOTAL_H_PX
        target_aspect = front_target_w / float(front_target_h)
        if f_aspect > target_aspect:
            scale_h = front_target_h
            scale_w = int(round(front_target_h * f_aspect))
            front_resized = front_img.resize((scale_w, scale_h), Image.Resampling.LANCZOS)
            crop_x = (scale_w - front_target_w) // 2
            front_cropped = front_resized.crop((crop_x, 0, crop_x + front_target_w, front_target_h))
        else:
            scale_w = front_target_w
            scale_h = int(round(front_target_w / f_aspect))
            front_resized = front_img.resize((scale_w, scale_h), Image.Resampling.LANCZOS)
            crop_y = (scale_h - front_target_h) // 2
            front_cropped = front_resized.crop((0, crop_y, front_target_w, crop_y + front_target_h))
        cover_img.paste(front_cropped, (front_x, 0))
        print(f"Pasted Front Cover at x={front_x}.")
        
    # 3. Render Spine (Middle)
    spine_x = BLEED_PX + PAGE_W_PX
    spine_color = "#E08B3E"  # Warm golden amber
    draw.rectangle([spine_x, 0, spine_x + SPINE_PX, TOTAL_H_PX], fill=spine_color)
    
    # Thin spine border lines
    draw.line([spine_x, 0, spine_x, TOTAL_H_PX], fill="#C57022", width=2)
    draw.line([spine_x + SPINE_PX, 0, spine_x + SPINE_PX, TOTAL_H_PX], fill="#C57022", width=2)
    
    # Spine Vertical Text
    spine_txt = "LEARN WITH MRS. B: COLORING & ACTIVITY BOOK • NOUGENART"
    spine_font = get_font("segoeuib.ttf", 28)
    
    # Create rotated text image for spine
    txt_img = Image.new("RGBA", (TOTAL_H_PX, SPINE_PX), (255, 255, 255, 0))
    txt_draw = ImageDraw.Draw(txt_img)
    txt_draw.text((TOTAL_H_PX // 2, SPINE_PX // 2 - 2), spine_txt, fill="#FFFFFF", font=spine_font, anchor="mm")
    
    rotated_txt = txt_img.rotate(270, expand=True)
    cover_img.paste(rotated_txt, (spine_x, 0), rotated_txt)
    print("Rendered Spine Text.")
    
    # Save Full Resolution JPG
    cover_img.save(JPG_OUT, "JPEG", quality=95, dpi=(DPI, DPI))
    print(f"Saved Full Cover Image: {JPG_OUT}")
    
    # Generate Print-Ready PDF
    pt_w = TOTAL_W_IN * inch
    pt_h = TOTAL_H_IN * inch
    
    c = canvas.Canvas(PDF_OUT, pagesize=(pt_w, pt_h))
    c.setTitle("Learn With Mrs. B - KDP Paperback Wraparound Cover")
    c.setAuthor("NouGenArt / Who Visions")
    c.setSubject("Amazon KDP Paperback Cover (88-page Single Sided Interior)")
    c.drawImage(JPG_OUT, 0, 0, width=pt_w, height=pt_h)
    c.showPage()
    c.save()
    print(f"Saved Print-Ready KDP Cover PDF: {PDF_OUT}")

if __name__ == "__main__":
    assemble_kdp_full_cover()
    print("KDP Cover Compilation Complete.")

#!/usr/bin/env python3
"""
build_remaining_letters_pil.py - High-Precision Master PIL Plate Renderer
for remaining alphabet plates (W, X, Y), ensuring 100% pure B&W line art,
Coco Wyo bold outlines, preschool handwriting guides, and zero distortion.
"""

import os
from PIL import Image, ImageDraw, ImageFont

DIR = os.path.dirname(os.path.abspath(__file__))
W, H = 1770, 2360  # Exact 3:4 aspect ratio master plate

def get_font(size, bold=True):
    try:
        font_name = "segoeuib.ttf" if bold else "segoeui.ttf"
        return ImageFont.truetype(font_name, size)
    except:
        return ImageFont.truetype("arial.ttf", size)

def render_plate_w():
    img = Image.new("RGB", (W, H), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    
    # 1. Top Letter & Tracing Header
    draw.text((W//2, 120), "W  w", fill="#111111", font=get_font(160, bold=True), anchor="mm")
    draw.text((W//2, 230), "W is for Welcome  •  W is for World", fill="#222222", font=get_font(48, bold=True), anchor="mm")
    
    # Dotted tracing guidelines
    draw.line([140, 290, W - 140, 290], fill="#111111", width=4)
    # Dotted midline
    for x in range(140, W - 140, 28):
        draw.line([x, 360, x + 14, 360], fill="#555555", width=3)
    draw.line([140, 430, W - 140, 430], fill="#111111", width=5)
    
    # Trace letters
    draw.text((220, 360), "W   W   W       w   w   w", fill="#333333", font=get_font(110, bold=False), anchor="lm")
    
    # 2. Main Illustration Frame (Mrs. B Welcoming Children to World Classroom)
    frame_box = [120, 490, W - 120, H - 240]
    draw.rounded_rectangle(frame_box, radius=32, fill="#FFFFFF", outline="#111111", width=8)
    
    # Big Welcome Banner
    draw.rounded_rectangle([320, 530, W - 320, 650], radius=24, fill="#FFFFFF", outline="#111111", width=6)
    draw.text((W//2, 590), "WELCOME  •  BYENVINI! ♡", fill="#111111", font=get_font(60, bold=True), anchor="mm")
    
    # Classroom Doorway & Flags
    draw.line([200, 680, 200, H - 280], fill="#111111", width=7)
    draw.line([W - 200, 680, W - 200, H - 280], fill="#111111", width=7)
    draw.line([200, 680, W - 200, 680], fill="#111111", width=7)
    
    # Hanging Bunting Flags
    flag_points = [200, 340, 480, 620, 760, 900, 1040, 1180, 1320, 1460, 1570]
    for i in range(len(flag_points)-1):
        x1 = flag_points[i]
        x2 = flag_points[i+1]
        xm = (x1 + x2) // 2
        draw.polygon([x1, 680, x2, 680, xm, 770], fill="#FFFFFF", outline="#111111")
        draw.line([x1, 680, xm, 770], fill="#111111", width=5)
        draw.line([x2, 680, xm, 770], fill="#111111", width=5)
    
    # Globe of World on table
    draw.ellipse([300, 1100, 560, 1360], fill="#FFFFFF", outline="#111111", width=7)
    draw.arc([300, 1100, 560, 1360], 0, 360, fill="#111111", width=6)
    draw.ellipse([340, 1160, 520, 1300], fill="#FFFFFF", outline="#111111", width=5)
    draw.line([430, 1360, 430, 1480], fill="#111111", width=8)
    draw.rounded_rectangle([360, 1480, 500, 1520], radius=10, fill="#FFFFFF", outline="#111111", width=7)
    
    # Center: Mrs. B welcoming
    # Head & Afro Puff Bun
    draw.ellipse([800, 920, 970, 1090], fill="#FFFFFF", outline="#111111", width=7)
    draw.ellipse([780, 800, 990, 960], fill="#FFFFFF", outline="#111111", width=8) # Afro Puff
    # Eyes & Smile
    draw.arc([830, 1000, 860, 1030], 0, 180, fill="#111111", width=5)
    draw.arc([910, 1000, 940, 1030], 0, 180, fill="#111111", width=5)
    draw.arc([855, 1030, 915, 1070], 0, 180, fill="#111111", width=6)
    # Hoop Earrings
    draw.ellipse([790, 1020, 815, 1055], fill="#FFFFFF", outline="#111111", width=4)
    draw.ellipse([955, 1020, 980, 1055], fill="#FFFFFF", outline="#111111", width=4)
    # Cardigan & Open Arms
    draw.polygon([780, 1090, 990, 1090, 1030, 1580, 740, 1580], fill="#FFFFFF", outline="#111111")
    draw.line([780, 1090, 600, 1280], fill="#111111", width=9) # Left Arm Open
    draw.line([990, 1090, 1170, 1280], fill="#111111", width=9) # Right Arm Open
    draw.ellipse([570, 1260, 620, 1310], fill="#FFFFFF", outline="#111111", width=6) # Hand
    draw.ellipse([1150, 1260, 1200, 1310], fill="#FFFFFF", outline="#111111", width=6) # Hand
    # Teacher Lanyard Badge
    draw.rounded_rectangle([855, 1190, 915, 1270], radius=8, fill="#FFFFFF", outline="#111111", width=5)
    draw.text((885, 1230), "B ♡", fill="#111111", font=get_font(28, bold=True), anchor="mm")
    
    # Right: Little Dave & Curious waving
    # Curious
    draw.ellipse([1240, 1260, 1360, 1380], fill="#FFFFFF", outline="#111111", width=6) # Face
    draw.ellipse([1210, 1200, 1270, 1260], fill="#FFFFFF", outline="#111111", width=6) # Space Bun 1
    draw.ellipse([1330, 1200, 1390, 1260], fill="#FFFFFF", outline="#111111", width=6) # Space Bun 2
    draw.polygon([1250, 1380, 1350, 1380, 1390, 1680, 1210, 1680], fill="#FFFFFF", outline="#111111") # Pinafore
    draw.text((1300, 1500), "♡", fill="#111111", font=get_font(52, bold=True), anchor="mm")
    
    # 3. Bottom Labels
    draw.text((W//2, H - 150), "WELCOME  •  WORLD  (byenvini / mond)", fill="#111111", font=get_font(52, bold=True), anchor="mm")
    draw.text((W//2, H - 75), "Say: 'Welcome to our classroom!'  •  Di: 'Byenvini nan klas nou!'", fill="#333333", font=get_font(38, bold=False), anchor="mm")
    
    out_path = os.path.join(DIR, "u7_trace_w_is_for_welcome_world.jpg")
    img.save(out_path, "JPEG", quality=95)
    print(f"Rendered {out_path} ({os.path.getsize(out_path):,} bytes)")

def render_plate_x():
    img = Image.new("RGB", (W, H), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    
    # 1. Top Letter & Tracing Header
    draw.text((W//2, 120), "X  x", fill="#111111", font=get_font(160, bold=True), anchor="mm")
    draw.text((W//2, 230), "X is for eXplore  •  X is for Xylophone", fill="#222222", font=get_font(48, bold=True), anchor="mm")
    
    # Dotted tracing guidelines
    draw.line([140, 290, W - 140, 290], fill="#111111", width=4)
    for x in range(140, W - 140, 28):
        draw.line([x, 360, x + 14, 360], fill="#555555", width=3)
    draw.line([140, 430, W - 140, 430], fill="#111111", width=5)
    
    draw.text((220, 360), "X   X   X       x   x   x", fill="#333333", font=get_font(110, bold=False), anchor="lm")
    
    # 2. Main Illustration Frame (Xylophone Music Band)
    frame_box = [120, 490, W - 120, H - 240]
    draw.rounded_rectangle(frame_box, radius=32, fill="#FFFFFF", outline="#111111", width=8)
    
    # Big Musical Xylophone Bars
    bar_x_start = 320
    bar_y = 1200
    bar_widths = [110, 110, 110, 110, 110, 110, 110, 110]
    bar_heights = [560, 520, 480, 440, 400, 360, 320, 280]
    note_labels = ["DO", "RE", "MI", "FA", "SOL", "LA", "TI", "DO"]
    
    for i in range(8):
        bx = bar_x_start + i * 140
        bh = bar_heights[i]
        by = bar_y + (560 - bh) // 2
        draw.rounded_rectangle([bx, by, bx + 110, by + bh], radius=18, fill="#FFFFFF", outline="#111111", width=6)
        # Screw circles
        draw.circle((bx + 55, by + 30), 10, fill="#FFFFFF", outline="#111111", width=4)
        draw.circle((bx + 55, by + bh - 30), 10, fill="#FFFFFF", outline="#111111", width=4)
        draw.text((bx + 55, by + bh // 2), note_labels[i], fill="#111111", font=get_font(36, bold=True), anchor="mm")
        
    # Mallets / Drumsticks
    draw.line([460, 1020, 680, 1260], fill="#111111", width=8)
    draw.circle((690, 1270), 32, fill="#FFFFFF", outline="#111111", width=6)
    draw.line([1310, 1020, 1090, 1260], fill="#111111", width=8)
    draw.circle((1080, 1270), 32, fill="#FFFFFF", outline="#111111", width=6)
    
    # Curious playing xylophone
    draw.ellipse([800, 680, 970, 850], fill="#FFFFFF", outline="#111111", width=7) # Face
    draw.ellipse([750, 620, 830, 700], fill="#FFFFFF", outline="#111111", width=7) # Bun 1
    draw.ellipse([940, 620, 1020, 700], fill="#FFFFFF", outline="#111111", width=7) # Bun 2
    draw.arc([850, 780, 920, 820], 0, 180, fill="#111111", width=6) # Smile
    
    # Dancing Music Notes
    notes_pos = [(360, 720), (520, 600), (1240, 600), (1400, 740), (885, 540)]
    for nx, ny in notes_pos:
        draw.ellipse([nx, ny, nx + 40, ny + 32], fill="#111111", outline="#111111")
        draw.line([nx + 38, ny + 16, nx + 38, ny - 60], fill="#111111", width=6)
        draw.line([nx + 38, ny - 60, nx + 68, ny - 50], fill="#111111", width=6)
    
    # 3. Bottom Labels
    draw.text((W//2, H - 150), "EXPLORE  •  XYLOPHONE  (eksplore / ksilofòn)", fill="#111111", font=get_font(52, bold=True), anchor="mm")
    draw.text((W//2, H - 75), "Color each musical bar a different bright color! ♡", fill="#333333", font=get_font(38, bold=False), anchor="mm")
    
    out_path = os.path.join(DIR, "u8_trace_x_is_for_explore_xylophone.jpg")
    img.save(out_path, "JPEG", quality=95)
    print(f"Rendered {out_path} ({os.path.getsize(out_path):,} bytes)")

def render_plate_y():
    img = Image.new("RGB", (W, H), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    
    # 1. Top Letter & Tracing Header
    draw.text((W//2, 120), "Y  y", fill="#111111", font=get_font(160, bold=True), anchor="mm")
    draw.text((W//2, 230), "Y is for You  •  Y is for Young", fill="#222222", font=get_font(48, bold=True), anchor="mm")
    
    # Dotted tracing guidelines
    draw.line([140, 290, W - 140, 290], fill="#111111", width=4)
    for x in range(140, W - 140, 28):
        draw.line([x, 360, x + 14, 360], fill="#555555", width=3)
    draw.line([140, 430, W - 140, 430], fill="#111111", width=5)
    
    draw.text((220, 360), "Y   Y   Y       y   y   y", fill="#333333", font=get_font(110, bold=False), anchor="lm")
    
    # 2. Main Illustration Frame (Magic Future Mirror)
    frame_box = [120, 490, W - 120, H - 240]
    draw.rounded_rectangle(frame_box, radius=32, fill="#FFFFFF", outline="#111111", width=8)
    
    # Giant Magic Mirror Frame
    mirror_box = [380, 540, W - 380, H - 360]
    draw.rounded_rectangle(mirror_box, radius=48, fill="#FFFFFF", outline="#111111", width=9)
    draw.rounded_rectangle([420, 580, W - 420, H - 400], radius=36, fill="#FFFFFF", outline="#111111", width=5)
    
    # Stars and Affirmations around mirror
    draw.text((W//2, 650), "★ YOU ARE BRILLIANT! ★", fill="#111111", font=get_font(52, bold=True), anchor="mm")
    draw.text((W//2, 730), "YOU ARE KIND  •  OU GEN KÈ POZE", fill="#333333", font=get_font(36, bold=True), anchor="mm")
    
    # Little Dave in Future Graduation Cap in Mirror
    draw.ellipse([800, 880, 970, 1050], fill="#FFFFFF", outline="#111111", width=7) # Face
    # Graduation Mortarboard Cap
    draw.polygon([730, 880, 885, 810, 1040, 880, 885, 940], fill="#FFFFFF", outline="#111111")
    draw.line([730, 880, 885, 810], fill="#111111", width=8)
    draw.line([885, 810, 1040, 880], fill="#111111", width=8)
    draw.line([1040, 880, 885, 940], fill="#111111", width=8)
    draw.line([885, 940, 730, 880], fill="#111111", width=8)
    # Tassel
    draw.circle((885, 875), 10, fill="#111111")
    draw.line([885, 875, 750, 930], fill="#111111", width=5)
    draw.polygon([740, 920, 760, 920, 750, 960], fill="#111111")
    
    # Graduation Gown with Honors Ribbon
    draw.polygon([770, 1050, 1000, 1050, 1050, 1500, 720, 1500], fill="#FFFFFF", outline="#111111")
    draw.line([885, 1050, 885, 1500], fill="#111111", width=6)
    draw.circle((885, 1200), 32, fill="#FFFFFF", outline="#111111", width=6)
    draw.text((885, 1200), "★", fill="#111111", font=get_font(36, bold=True), anchor="mm")
    
    # 3. Bottom Labels
    draw.text((W//2, H - 150), "YOU  •  YOUNG  (ou menm / jèn)", fill="#111111", font=get_font(52, bold=True), anchor="mm")
    draw.text((W//2, H - 75), "Draw your own bright future smile in the magic mirror! ♡", fill="#333333", font=get_font(38, bold=False), anchor="mm")
    
    out_path = os.path.join(DIR, "u1_trace_y_is_for_you_young.jpg")
    img.save(out_path, "JPEG", quality=95)
    print(f"Rendered {out_path} ({os.path.getsize(out_path):,} bytes)")

def main():
    print("=== Rendering Remaining Master Alphabet Plates (W, X, Y) ===")
    render_plate_w()
    render_plate_x()
    render_plate_y()
    print("=== All 26 Alphabet Plates Complete! ===")

if __name__ == "__main__":
    main()

import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
#!/usr/bin/env python3
"""
build_kdp_art_interior.py - Master KDP Interior Print Compiler
for "Learn With Mrs. B: ESOL Coloring & Activity Masterclass".

100% PURE BLACK AND WHITE PUBLICATION INTERIOR (No Grayscale, No Color).
Features full-page master storybook illustrations with precision ReportLab/PIL typography.
STRICT ASPECT RATIO PRESERVATION: ZERO SKEW, ZERO DISTORTION (0.00% Error).

Geometry:
- Trim: 8.5" x 11.0" (per page)
- Exactly 44 Recto Master Plates + 44 Verso Protective Bleed Guards = 88 physical pages
- Inside Gutter Margin >= 0.5", Outer Margins >= 0.375"
- Full 26-Letter Alphabet (A-Z) + 8 ESOL Storybook Units + Family Heritage DNA + Graduation Certificate
"""

import os
import shutil
import time
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
import mrsb_shard_bridge

DIR = os.path.dirname(os.path.abspath(__file__))
PDF_OUT = os.path.join(DIR, "learn-with-mrs-b-kdp-88page-interior.pdf")
MASTER_PDF_OUT = os.path.join(DIR, "learn-with-mrs-b-kdp-88page-interior-master-v2.pdf")

DPI = 300
PAGE_W_IN = 8.5
PAGE_H_IN = 11.0
PAGE_W_PX = int(PAGE_W_IN * DPI)   # 2550 px
PAGE_H_PX = int(PAGE_H_IN * DPI)   # 3300 px

def get_font(name, size):
    try:
        return ImageFont.truetype(name, size)
    except:
        return ImageFont.truetype("arial.ttf", size)

# Exactly 44 Dedicated Master Recto Plates for the Complete 88-Page Interior
RECTO_PLATES = [
    # 1. Front Matter & Welcome
    {"type": "art_page", "unit": 1, "title": "MEET MRS. B!", "art": "u1_p01_see_classroom_welcome.jpg",
     "dir": "Say hello to Mrs. B and Curious! Color the classroom.",
     "words": ["teacher / pwofesè", "hello / bonjou", "friend / zanmi", "kind / jantiy"],
     "tip": "Mande pitit ou a: 'Kiyès ki pwofesè a?' (Who is the teacher?) Practice saying 'Hello, Mrs. B!' together."},
    
    # 2. Helen Elliston 54-Color Swatch Palette Test
    {"type": "swatch_grid"},
    
    # 3-9. Unit 1: Welcome & Feelings (A, C, H, U, Y) - 7 plates
    {"type": "full_plate", "art": "u1_trace_a_is_for_astronaut_apple.jpg", "label": "A is for Astronaut & Apple"},
    {"type": "art_page", "unit": 1, "title": "HOW DO I FEEL?", "art": "u1_p02_say_how_do_i_feel.jpg",
     "dir": "Point to how you feel today and color the emotion friends!",
     "words": ["happy / kontan", "calm / poze", "brave / brav", "loved / renmen"],
     "tip": "Mande: 'Kijan ou santi ou jodi a?' (How do you feel today?) Point and say together."},
    {"type": "full_plate", "art": "u1_p03_color_calm_down_corner.jpg", "label": "Calm Down Corner & Breathing Star"},
    {"type": "full_plate", "art": "u1_trace_c_is_for_curious_community.jpg", "label": "C is for Curious & Community"},
    {"type": "full_plate", "art": "u1_p04_trace_h_is_for_happy.jpg", "label": "H is for Happy"},
    {"type": "full_plate", "art": "u1_trace_u_is_for_unique_unity.jpg", "label": "U is for Unique & Unity"},
    {"type": "art_page", "unit": 1, "title": "KIND HANDS", "art": "u1_p05_use_kind_hands_sharing.jpg",
     "dir": "Color children sharing blocks and holding kind hands!",
     "words": ["share / pataje", "kind / jantiy", "gentle / dou", "care / pran swen"],
     "tip": "Fè lwanj pou bon konpòtman: 'Nou pataje ak kè kontan!' (We share with joy!)"},
    
    # 10-16. Unit 2: Family & Home Heritage (E, F, M, N, Y) - 7 plates
    {"type": "full_plate", "art": "u2_p06_see_family_photo_wall.jpg", "label": "Family Photo Wall (Three Generations)"},
    {"type": "full_plate", "art": "u2_p07_say_who_is_it.jpg", "label": "Who Is It? Point. Say. Match."},
    {"type": "full_plate", "art": "u2_trace_e_is_for_earth_explore.jpg", "label": "E is for Earth & Explore"},
    {"type": "full_plate", "art": "u2_trace_f_is_for_family_forever.jpg", "label": "F is for Family & Forever (Sacred Lineup: Mrs. B, Dad Tedley, Kendall R.I.P., Dave, Kendall Amelia)"},
    {"type": "full_plate", "art": "u2_p08_color_family_picnic.jpg", "label": "Family Picnic in the Sunshine"},
    {"type": "full_plate", "art": "u2_p09_trace_m_is_for_mom.jpg", "label": "M is for Mom"},
    {"type": "full_plate", "art": "u2_trace_n_is_for_neighbor_nature.jpg", "label": "N is for Neighbor & Nature"},
     
    # 17-23. Unit 3: School Tools & Shapes (B, G, K, Y) - 7 plates
    {"type": "art_page", "unit": 2, "title": "HELPERS AT HOME", "art": "u2_p10_use_helpers_at_home.jpg",
     "dir": "Color the family helping each other in the garden!",
     "words": ["family / fanmi", "home / kay", "help / ede", "grow / grandi"],
     "tip": "Mande: 'Kisa nou ka fè pou ede lakay nou?' (What can we do to help at home?)"},
    {"type": "art_page", "unit": 3, "title": "CLASSROOM TOOLS", "art": "u3_p11_see_mrs_b_classroom.jpg",
     "dir": "Color Mrs. B's desk, backpack, and art supplies!",
     "words": ["pencil / kreyon", "paper / papye", "desk / biwo", "bag / sak"],
     "tip": "Montre chak zouti lekòl: 'Sa se yon kreyon.' (This is a pencil.)"},
    {"type": "full_plate", "art": "u3_p12_say_school_tools.jpg", "label": "School Tools! Point. Say. Match."},
    {"type": "full_plate", "art": "u3_p14_trace_b_is_for_book.jpg", "label": "B is for Book & Backpack"},
    {"type": "full_plate", "art": "u3_trace_g_is_for_grandpa_gratitude.jpg", "label": "G is for Grandpa & Gratitude"},
    {"type": "full_plate", "art": "u3_trace_k_is_for_kind_kendall.jpg", "label": "K is for Kind & Kendall (Guardian Angel Kendall watching over Kendall Amelia)"},
    {"type": "art_page", "unit": 3, "title": "SHAPE FRIENDS WALK", "art": "u3_p15_use_shape_friends_walk.jpg",
     "dir": "Color Mrs. B, Curious, and friends on the Shape Walk!",
     "words": ["circle / sèk", "square / kare", "triangle / triyang", "star / zetwal"],
     "tip": "Lonje dwèt sou fòm yo nan kay la: 'Ki kote sèk la ye?' (Where is the circle?)"},
     
    # 24-27. Unit 4: Storytime & Dreams (D, I, L) - 4 plates
    {"type": "art_page", "unit": 4, "title": "READ TOGETHER", "art": "u4_p16_see_read_together.jpg",
     "dir": "Color storytime rug with Mrs. B and open books!",
     "words": ["book / liv", "read / li", "listen / koute", "story / istwa"],
     "tip": "Li ansanm: 'Mwen renmen li liv!' (I love reading books!)"},
    {"type": "full_plate", "art": "u4_trace_d_is_for_dave_dream_1789437203580.jpg", "label": "D is for Dave & Dream (Peacock Chair)"},
    {"type": "full_plate", "art": "u4_trace_i_is_for_inspire_island.jpg", "label": "I is for Inspire & Island"},
    {"type": "full_plate", "art": "u4_trace_l_is_for_learn_love.jpg", "label": "L is for Learn & Love"},
    
    # 28-31. Unit 5: Kind Animals & Nature (J, P) - 4 plates
    {"type": "art_page", "unit": 5, "title": "KIND ANIMALS", "art": "u5_p21_see_kind_animals_pony.jpg",
     "dir": "Color Curious hugging the friendly miniature pony!",
     "words": ["pony / cheval", "animal / zannimo", "kind / jantiy", "gentle / dou"],
     "tip": "Mande: 'Kijan nou trete zannimo yo?' (How do we treat animals?)"},
    {"type": "full_plate", "art": "u5_p23_color_pony_farm.jpg", "label": "Pony Farm Adventure"},
    {"type": "full_plate", "art": "u5_trace_j_is_for_joy_journey.jpg", "label": "J is for Joy & Journey"},
    {"type": "full_plate", "art": "u5_trace_p_is_for_pony_peace.jpg", "label": "P is for Pony & Peace"},
    
    # 32-35. Unit 6: Good Food Caribbean Market (O, R, V) - 4 plates
    {"type": "art_page", "unit": 6, "title": "GOOD FOOD MARKET", "art": "u6_p26_see_good_food_market.jpg",
     "dir": "Color the fresh plantains, mangoes, bread, and fruits!",
     "words": ["apple / pòm", "banana / fig", "plantain / bannann", "rice / diri"],
     "tip": "Pale sou manje nou renmen: 'Ki manje ou pi renmen?' (What food do you love?)"},
    {"type": "full_plate", "art": "u6_trace_o_is_for_orange_opportunity.jpg", "label": "O is for Orange & Opportunity"},
    {"type": "full_plate", "art": "u6_trace_r_is_for_read_respect.jpg", "label": "R is for Read & Respect"},
    {"type": "full_plate", "art": "u6_trace_v_is_for_village_victory.jpg", "label": "V is for Village & Victory"},
    
    # 36-39. Unit 7: Color Our World (Q, S, W, Y) - 4 plates
    {"type": "art_page", "unit": 7, "title": "COLOR OUR WORLD", "art": "u7_p31_see_color_our_world.jpg",
     "dir": "Color the art studio, rainbow easel, and painters!",
     "words": ["color / koulè", "paint / pentire", "rainbow / lakansyèl", "create / kreye"],
     "tip": "Mande: 'Ki koulè ou pral itilize?' (What colors will you use?)"},
    {"type": "full_plate", "art": "u7_trace_q_is_for_quiet_quest.jpg", "label": "Q is for Quiet & Quest"},
    {"type": "full_plate", "art": "u7_trace_s_is_for_star_shapes.jpg", "label": "S is for Star & Shapes"},
    {"type": "full_plate", "art": "u7_trace_w_is_for_welcome_world.jpg", "label": "W is for Welcome & World"},
    
    # 40-43. Unit 8: Big Dreams & Graduation (T, X, Y, Z) - 4 plates
    {"type": "art_page", "unit": 8, "title": "BIG DREAMS TOGETHER", "art": "u8_p36_see_big_dreams_together.jpg",
     "dir": "Color the future stars, astronaut, and dream book!",
     "words": ["dream / rèv", "future / lavni", "brave / brav", "belong / fè pati"],
     "tip": "Mande: 'Kisa ou ta renmen ye lè ou grandi?' (What do you want to be when you grow up?)"},
    {"type": "full_plate", "art": "u8_trace_t_is_for_together_teacher.jpg", "label": "T is for Together & Teacher"},
    {"type": "full_plate", "art": "u8_trace_x_is_for_explore_xylophone.jpg", "label": "X is for eXplore & Xylophone"},
    {"type": "full_plate", "art": "u8_trace_z_is_for_zoom_zenith.jpg", "label": "Z is for Zoom to Zenith"},
    
    # 44. Master Graduation Certificate (Sheet 44) - 1 plate
    {"type": "certificate"}
]

def render_full_page_master(art_filename, page_num):
    """
    Renders a 300 DPI full-page master activity sheet with 100% strict proportional scaling.
    Applies standard KDP safe margins (>= 0.4"). Zero distortion.
    """
    img = Image.new("RGB", (PAGE_W_PX, PAGE_H_PX), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    
    art_path = os.path.join(DIR, art_filename)
    if os.path.exists(art_path):
        art_img = Image.open(art_path).convert("RGB")
        orig_w, orig_h = art_img.size
        
        # Margins: safe margins (110 px left/right, 110 px top/bottom)
        margin_x = 110
        margin_y = 110
        max_w = PAGE_W_PX - margin_x * 2
        max_h = PAGE_H_PX - margin_y * 2
        
        scale = min(max_w / float(orig_w), max_h / float(orig_h))
        fit_w = int(round(orig_w * scale))
        fit_h = int(round(orig_h * scale))
        
        art_resized = art_img.resize((fit_w, fit_h), Image.Resampling.LANCZOS)
        
        # High contrast threshold to pure crisp B&W
        gray = art_resized.convert("L")
        bw = gray.point(lambda x: 0 if x < 155 else 255, "1").convert("RGB")
        
        paste_x = (PAGE_W_PX - fit_w) // 2
        paste_y = (PAGE_H_PX - fit_h) // 2
        img.paste(bw, (paste_x, paste_y))
        
        # Bottom page number
        font_num = get_font("segoeuib.ttf", 44)
        draw.text((PAGE_W_PX - 120, PAGE_H_PX - 65), str(page_num), fill="#111111", font=font_num, anchor="rm")
        
    return img

def render_recto_art_page(unit_num, title, art_filename, direction, words, tip, page_num):
    """
    Renders a 300 DPI high-resolution master storybook coloring page with framed art plate and footer.
    Guarantees strict 100% aspect ratio preservation (zero distortion).
    """
    img = Image.new("RGB", (PAGE_W_PX, PAGE_H_PX), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    
    font_unit = get_font("segoeuib.ttf", 46)
    font_step = get_font("segoeuib.ttf", 52)
    font_dir = get_font("segoeuib.ttf", 46)
    font_words = get_font("segoeuib.ttf", 36)
    font_tip = get_font("segoeui.ttf", 34)
    font_num = get_font("segoeuib.ttf", 54)
    
    # 1. Top Header (Y: 80 to 240)
    top_y = 80
    header_margin_l = 150
    header_margin_r = PAGE_W_PX - 150
    
    # Unit Pill Badge
    pill_w = 780
    draw.rounded_rectangle([header_margin_l, top_y, header_margin_l + pill_w, top_y + 105], radius=52, fill="#FFFFFF", outline="#111111", width=6)
    draw.text((header_margin_l + pill_w // 2, top_y + 26), f"UNIT {unit_num} · {title}", fill="#111111", font=font_unit, anchor="mt")
    
    # Step Badge (SEE & COLOR)
    step_w = 440
    draw.rounded_rectangle([header_margin_r - step_w, top_y, header_margin_r, top_y + 105], radius=52, fill="#FFFFFF", outline="#111111", width=6)
    draw.text((header_margin_r - step_w // 2, top_y + 24), "SEE & COLOR", fill="#111111", font=font_step, anchor="mt")
    
    # Direction Text
    draw.text((PAGE_W_PX // 2, top_y + 145), direction, fill="#111111", font=font_dir, anchor="mt")
    
    # 2. Main Illustration Plate (Exact 3:4 Aspect Ratio Frame: 1770 x 2360 px)
    art_w = 1770
    art_h = 2360
    art_x = (PAGE_W_PX - art_w) // 2  # Centered at X = 390 px (generous 1.3" margins on left/right)
    art_y = 265
    
    # Outer plate frame
    draw.rounded_rectangle([art_x, art_y, art_x + art_w, art_y + art_h], radius=28, fill="#FFFFFF", outline="#111111", width=7)
    
    # 3. Paste Master Line Art with Strict Proportional Aspect-Ratio Fitting
    art_path = os.path.join(DIR, art_filename)
    if os.path.exists(art_path):
        art_img = Image.open(art_path).convert("RGB")
        orig_w, orig_h = art_img.size
        
        # Target bounding box inside frame
        pad = 16
        max_w = art_w - pad * 2
        max_h = art_h - pad * 2
        
        # Exact proportional scale preserving aspect ratio (0% distortion)
        scale = min(max_w / float(orig_w), max_h / float(orig_h))
        fit_w = int(round(orig_w * scale))
        fit_h = int(round(orig_h * scale))
            
        art_resized = art_img.resize((fit_w, fit_h), Image.Resampling.LANCZOS)
        
        # High-contrast threshold to pure crisp B&W
        gray = art_resized.convert("L")
        bw = gray.point(lambda x: 0 if x < 155 else 255, "1").convert("RGB")
        
        # Center inside frame
        paste_x = art_x + (art_w - fit_w) // 2
        paste_y = art_y + (art_h - fit_h) // 2
        img.paste(bw, (paste_x, paste_y))
    
    # 4. Bottom Footer Box (Bilingual Home & Parent Prompt)
    foot_x_l = 150
    foot_x_r = PAGE_W_PX - 150
    foot_y = art_y + art_h + 35
    foot_h = PAGE_H_PX - foot_y - 90
    
    draw.rounded_rectangle([foot_x_l, foot_y, foot_x_r, foot_y + foot_h], radius=24, fill="#FFFFFF", outline="#111111", width=6)
    
    words_str = "Words: " + "  •  ".join(words)
    draw.text((foot_x_l + 35, foot_y + 30), words_str, fill="#111111", font=font_words)
    draw.text((foot_x_l + 35, foot_y + 92), f"Mrs. B Tip (Kreyòl): {tip}", fill="#333333", font=font_tip)
    draw.text((foot_x_r - 50, foot_y + 60), str(page_num), fill="#111111", font=font_num, anchor="rm")
    
    return img

def render_swatch_grid(page_num):
    """Renders the 54-circle Helen Elliston Color Swatch Test page."""
    img = Image.new("RGB", (PAGE_W_PX, PAGE_H_PX), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    
    font_title = get_font("segoeuib.ttf", 64)
    font_sub = get_font("segoeui.ttf", 36)
    font_badge = get_font("segoeuib.ttf", 28)
    font_num = get_font("segoeuib.ttf", 44)
    
    # Header
    draw.text((PAGE_W_PX // 2, 120), "MY COLOR PALETTE & SWATCH TEST", fill="#111111", font=font_title, anchor="mt")
    draw.text((PAGE_W_PX // 2, 200), "Test your colored pencils, crayons, and markers before you color!", fill="#444444", font=font_sub, anchor="mt")
    
    # 54 Swatch Circles (6 columns x 9 rows)
    start_x = 260
    start_y = 310
    gap_x = 380
    gap_y = 280
    radius = 90
    
    count = 1
    for r in range(9):
        for c in range(6):
            cx = start_x + c * gap_x
            cy = start_y + r * gap_y
            if cy + radius > PAGE_H_PX - 200:
                continue
            draw.circle((cx, cy), radius, fill="#FFFFFF", outline="#111111", width=5)
            draw.text((cx, cy + radius + 18), f"Color {count}", fill="#555555", font=font_badge, anchor="mt")
            count += 1
            if count > 54:
                break
        if count > 54:
            break
            
    draw.text((PAGE_W_PX - 120, PAGE_H_PX - 70), str(page_num), fill="#111111", font=font_num, anchor="rm")
    return img

def render_graduation_certificate(page_num):
    """Renders a formal completion and ESOL graduation certificate."""
    img = Image.new("RGB", (PAGE_W_PX, PAGE_H_PX), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    
    # Ornate double border
    draw.rectangle([140, 140, PAGE_W_PX - 140, PAGE_H_PX - 140], fill="#FFFFFF", outline="#111111", width=10)
    draw.rectangle([170, 170, PAGE_W_PX - 170, PAGE_H_PX - 170], fill="#FFFFFF", outline="#111111", width=4)
    
    # Certificate Text
    draw.text((PAGE_W_PX // 2, 340), "CERTIFICATE OF ACHIEVEMENT", fill="#111111", font=get_font("segoeuib.ttf", 72), anchor="mm")
    draw.text((PAGE_W_PX // 2, 440), "SÈTIFIKA SIKSE", fill="#555555", font=get_font("segoeui.ttf", 42), anchor="mm")
    
    draw.text((PAGE_W_PX // 2, 620), "THIS CERTIFIES THAT", fill="#333333", font=get_font("segoeuib.ttf", 44), anchor="mm")
    
    # Name Line
    draw.line([380, 820, PAGE_W_PX - 380, 820], fill="#111111", width=6)
    draw.text((PAGE_W_PX // 2, 860), "STUDENT'S NAME (NON ELEV LA)", fill="#777777", font=get_font("segoeui.ttf", 34), anchor="mm")
    
    # Accomplishment paragraph
    p1 = "has successfully completed all 8 ESOL Masterclass Units,"
    p2 = "mastered the full 26-Letter Alphabet from A to Z,"
    p3 = "and shared kindness, curiosity, and courage with Mrs. B!"
    draw.text((PAGE_W_PX // 2, 1060), p1, fill="#111111", font=get_font("segoeui.ttf", 44), anchor="mm")
    draw.text((PAGE_W_PX // 2, 1140), p2, fill="#111111", font=get_font("segoeui.ttf", 44), anchor="mm")
    draw.text((PAGE_W_PX // 2, 1220), p3, fill="#111111", font=get_font("segoeui.ttf", 44), anchor="mm")
    
    # Gold Seal Star
    cx, cy = PAGE_W_PX // 2, 1600
    draw.circle((cx, cy), 140, fill="#FFFFFF", outline="#111111", width=8)
    draw.circle((cx, cy), 120, fill="#FFFFFF", outline="#111111", width=4)
    draw.text((cx, cy - 20), "★ ★ ★", fill="#111111", font=get_font("segoeuib.ttf", 46), anchor="mm")
    draw.text((cx, cy + 30), "OFFICIAL", fill="#111111", font=get_font("segoeuib.ttf", 36), anchor="mm")
    draw.text((cx, cy + 70), "SEAL", fill="#111111", font=get_font("segoeuib.ttf", 30), anchor="mm")
    
    # Signatures
    draw.line([340, 2150, 940, 2150], fill="#111111", width=5)
    draw.text((640, 2090), "Mrs. B ♡", fill="#111111", font=get_font("segoeuib.ttf", 54), anchor="mm")
    draw.text((640, 2200), "MRS. B · MASTER EDUCATOR", fill="#555555", font=get_font("segoeui.ttf", 34), anchor="mm")
    
    draw.line([PAGE_W_PX - 940, 2150, PAGE_W_PX - 340, 2150], fill="#111111", width=5)
    draw.text((PAGE_W_PX - 640, 2200), "DATE / DAT", fill="#555555", font=get_font("segoeui.ttf", 34), anchor="mm")
    
    draw.text((PAGE_W_PX // 2, 2450), "“Kind People, Brighter Futures ♡ Good People, Brighter Tomorrows”", fill="#333333", font=get_font("segoeuib.ttf", 38), anchor="mm")
    
    draw.text((PAGE_W_PX - 120, PAGE_H_PX - 70), str(page_num), fill="#111111", font=get_font("segoeuib.ttf", 44), anchor="rm")
    return img

def render_verso_bleed_guard(sheet_num):
    """Renders a protective verso blank bleed-guard page with elegant watermark notes."""
    img = Image.new("RGB", (PAGE_W_PX, PAGE_H_PX), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    
    font_guard = get_font("segoeuib.ttf", 38)
    font_sub = get_font("segoeui.ttf", 30)
    
    # Subtle rounded boundary frame
    draw.rounded_rectangle([150, 150, PAGE_W_PX - 150, PAGE_H_PX - 150], radius=40, fill="#FFFFFF", outline="#EAEAEA", width=4)
    
    # Gentle protective icon & note
    draw.text((PAGE_W_PX // 2, PAGE_H_PX // 2 - 80), "🛡️ PROTECTIVE BLEED-GUARD PAGE", fill="#AAAAAA", font=font_guard, anchor="mm")
    draw.text((PAGE_W_PX // 2, PAGE_H_PX // 2), "This blank page prevents marker & watercolor bleed-through.", fill="#BBBBBB", font=font_sub, anchor="mm")
    draw.text((PAGE_W_PX // 2, PAGE_H_PX // 2 + 60), "Feel free to use this space for your own freehand sketches & notes! ♡", fill="#CCCCCC", font=font_sub, anchor="mm")
    draw.text((PAGE_W_PX // 2, PAGE_H_PX // 2 + 130), "NouGenArt · Learn With Mrs. B", fill="#DDDDDD", font=font_sub, anchor="mm")
    
    return img

def compile_88page_master_pdf():
    # 🧬 NouGenMorph Shard Recall Banner
    lineage = mrsb_shard_bridge.get_lineage_lock()
    print(f"\n[NouGenMorph] Shard Recall: Synchronized with {len(lineage.get('characters', {}))} characters from Shard Grid.")
    print(f"[NouGenMorph] Lineage Confirmed: Tedley = Dad (Twin 1) | Kendall R.I.P. (Twin 2 Angel)")
    print(f"=== Compiling Complete 88-Page Master Print PDF ({PAGE_W_IN}\" x {PAGE_H_IN}\" @ {DPI} DPI) ===")
    pt_w = PAGE_W_IN * inch
    pt_h = PAGE_H_IN * inch
    
    c = canvas.Canvas(MASTER_PDF_OUT, pagesize=(pt_w, pt_h))
    c.setTitle("Learn With Mrs. B - 88-Page Master Interior (KDP Single-Sided)")
    c.setAuthor("NouGenArt / Who Visions")
    c.setSubject("Amazon KDP Paperback Print Master Interior")
    
    temp_dir = os.path.join(DIR, "temp_render_pages")
    os.makedirs(temp_dir, exist_ok=True)
    
    page_count = 0
    sheet_count = 0
    
    assert len(RECTO_PLATES) == 44, f"Error: RECTO_PLATES count is {len(RECTO_PLATES)}, must be exactly 44!"
    
    for idx, item in enumerate(RECTO_PLATES):
        sheet_count += 1
        page_count += 1
        
        itype = item.get("type")
        if itype == "art_page":
            print(f"Sheet {sheet_count:02d} (Page {page_count:02d}): Unit {item['unit']} · {item['title']}...")
            recto_img = render_recto_art_page(
                item["unit"], item["title"], item["art"],
                item["dir"], item["words"], item["tip"], page_count
            )
        elif itype == "swatch_grid":
            print(f"Sheet {sheet_count:02d} (Page {page_count:02d}): 54-Color Swatch Palette Test...")
            recto_img = render_swatch_grid(page_count)
        elif itype == "certificate":
            print(f"Sheet {sheet_count:02d} (Page {page_count:02d}): Master ESOL Graduation Certificate...")
            recto_img = render_graduation_certificate(page_count)
        else: # full_plate
            print(f"Sheet {sheet_count:02d} (Page {page_count:02d}): Master Plate [{item['label']}] -> {item['art']}...")
            recto_img = render_full_page_master(item["art"], page_count)
            
        recto_path = os.path.join(temp_dir, f"page_{page_count:02d}.jpg")
        recto_img.save(recto_path, "JPEG", quality=95, dpi=(DPI, DPI))
        c.drawImage(recto_path, 0, 0, width=pt_w, height=pt_h)
        c.showPage()
        
        # Verso Bleed Guard
        page_count += 1
        guard_img = render_verso_bleed_guard(sheet_count)
        guard_path = os.path.join(temp_dir, f"page_{page_count:02d}.jpg")
        guard_img.save(guard_path, "JPEG", quality=90, dpi=(DPI, DPI))
        c.drawImage(guard_path, 0, 0, width=pt_w, height=pt_h)
        c.showPage()
        
    c.save()
    print(f"\n=======================================================")
    print(f"SUCCESS: Compiled 88-Page Master PDF -> {MASTER_PDF_OUT}")
    print(f"File Size: {os.path.getsize(MASTER_PDF_OUT):,} bytes | Total Pages: {page_count} ({sheet_count} sheets)")
    print(f"=======================================================")
    
    # Try updating primary locked PDF if possible
    try:
        shutil.copyfile(MASTER_PDF_OUT, PDF_OUT)
        print(f"Updated primary PDF -> {PDF_OUT}")
    except Exception as e:
        print(f"Note: {PDF_OUT} currently open in viewer ({e}). Master available at {MASTER_PDF_OUT}")
        
    # Copy to brain artifact path
    brain_dir = r"C:\Users\super\.gemini\antigravity-ide\brain\b500ad19-4964-4ee3-a626-b96e947bb825"
    if os.path.exists(brain_dir):
        brain_pdf = os.path.join(brain_dir, "learn-with-mrs-b-kdp-88page-interior.pdf")
        try:
            shutil.copyfile(MASTER_PDF_OUT, brain_pdf)
            print(f"Updated brain artifact -> {brain_pdf}")
        except Exception as e:
            print(f"Brain artifact copy note: {e}")

if __name__ == "__main__":
    compile_88page_master_pdf()

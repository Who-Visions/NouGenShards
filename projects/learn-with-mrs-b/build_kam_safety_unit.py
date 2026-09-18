"""
Build Kam the Police Helper: Community & Police Safety Unit (KDP Print-Ready PDF).
NouGenArt Publishing & Education
"""

import os
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

ASSETS_DIR = r"~\Outpost\NouGen\projects\learn-with-mrs-b\assets"
OUTPUT_PDF = r"~\Outpost\NouGen\projects\learn-with-mrs-b\kam_police_safety_unit_booklet.pdf"

PAGE_WIDTH, PAGE_HEIGHT = letter # 8.5 x 11 inches (612 x 792 pt)

def draw_header_footer(c, title_text, subtitle_text, page_num):
    # Header
    c.setStrokeColorRGB(0.1, 0.1, 0.1)
    c.setLineWidth(1.5)
    c.line(0.5 * inch, PAGE_HEIGHT - 0.75 * inch, PAGE_WIDTH - 0.5 * inch, PAGE_HEIGHT - 0.75 * inch)
    
    c.setFont("Helvetica-Bold", 14)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(0.5 * inch, PAGE_HEIGHT - 0.65 * inch, title_text)
    
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawRightString(PAGE_WIDTH - 0.5 * inch, PAGE_HEIGHT - 0.65 * inch, subtitle_text)
    
    # Footer
    c.setStrokeColorRGB(0.1, 0.1, 0.1)
    c.setLineWidth(1.5)
    c.line(0.5 * inch, 0.65 * inch, PAGE_WIDTH - 0.5 * inch, 0.65 * inch)
    
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(0.5 * inch, 0.45 * inch, "NouGenArt • Community Helpers  |  Learn With Mrs. B")
    
    c.setFont("Helvetica", 9)
    c.drawRightString(PAGE_WIDTH - 0.5 * inch, 0.45 * inch, f"Page {page_num}")

def draw_image_page(c, image_path, title, subtitle, page_num):
    c.saveState()
    draw_header_footer(c, title, subtitle, page_num)
    
    avail_x = 0.5 * inch
    avail_y = 0.85 * inch
    avail_w = PAGE_WIDTH - 1.0 * inch
    avail_h = PAGE_HEIGHT - 1.7 * inch
    
    if os.path.exists(image_path):
        with Image.open(image_path) as img:
            iw, ih = img.size
            aspect = iw / ih
            
            target_w = avail_w
            target_h = target_w / aspect
            
            if target_h > avail_h:
                target_h = avail_h
                target_w = target_h * aspect
            
            x_pos = avail_x + (avail_w - target_w) / 2.0
            y_pos = avail_y + (avail_h - target_h) / 2.0
            
            c.drawImage(image_path, x_pos, y_pos, width=target_w, height=target_h, preserveAspectRatio=True)
            
            c.setStrokeColorRGB(0.15, 0.15, 0.15)
            c.setLineWidth(1.5)
            c.rect(x_pos, y_pos, target_w, target_h)
            
    c.restoreState()
    c.showPage()

def draw_cover_page(c):
    c.saveState()
    c.setStrokeColorRGB(0.1, 0.1, 0.1)
    c.setLineWidth(4)
    c.rect(0.4 * inch, 0.4 * inch, PAGE_WIDTH - 0.8 * inch, PAGE_HEIGHT - 0.8 * inch)
    c.setLineWidth(1)
    c.rect(0.48 * inch, 0.48 * inch, PAGE_WIDTH - 0.96 * inch, PAGE_HEIGHT - 0.96 * inch)
    
    c.setFont("Helvetica-Bold", 24)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawCentredString(PAGE_WIDTH / 2.0, PAGE_HEIGHT - 1.15 * inch, "OFFICER KAM'S SAFETY UNIT")
    
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0.15, 0.35, 0.75)
    c.drawCentredString(PAGE_WIDTH / 2.0, PAGE_HEIGHT - 1.45 * inch, "COMMUNITY HELPERS & POLICE SAFETY ACTIVITY BOOK")
    
    c.setFont("Helvetica-Oblique", 10)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawCentredString(PAGE_WIDTH / 2.0, PAGE_HEIGHT - 1.7 * inch, "Kinder Minds  •  Safer Communities  •  Brighter Tomorrows")
    
    cover_img = os.path.join(ASSETS_DIR, "kam_police_helper_coloring_master.jpg")
    if os.path.exists(cover_img):
        img_w = 4.4 * inch
        img_h = 5.5 * inch
        c.drawImage(cover_img, (PAGE_WIDTH - img_w) / 2.0, 2.35 * inch, width=img_w, height=img_h)
        c.setStrokeColorRGB(0.2, 0.2, 0.2)
        c.setLineWidth(1.5)
        c.rect((PAGE_WIDTH - img_w) / 2.0, 2.35 * inch, img_w, img_h)
    
    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    c.setLineWidth(1.5)
    c.roundRect(0.8 * inch, 0.95 * inch, PAGE_WIDTH - 1.6 * inch, 1.15 * inch, 6)
    
    c.setFont("Helvetica-Bold", 10)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(1.0 * inch, 1.7 * inch, "JUNIOR SAFETY OFFICER NAME:")
    c.line(3.5 * inch, 1.7 * inch, PAGE_WIDTH - 1.0 * inch, 1.7 * inch)
    
    c.drawString(1.0 * inch, 1.3 * inch, "CLASSROOM / TEACHER:")
    c.line(3.0 * inch, 1.3 * inch, PAGE_WIDTH - 1.0 * inch, 1.3 * inch)
    
    c.setFont("Helvetica-Bold", 8)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawCentredString(PAGE_WIDTH / 2.0, 0.65 * inch, "NouGenArt Publishing  •  Learn With Mrs. B Series  •  Grades K-3")
    
    c.restoreState()
    c.showPage()

def draw_tracing_page(c, page_num):
    c.saveState()
    draw_header_footer(c, "Safety Words Tracing & Handwriting Practice", "Trace the bold letters. Say each safety word aloud.", page_num)
    
    words = [
        ("POLICE", "An officer who protects and helps our community."),
        ("SAFETY", "Making good choices to stay protected from harm."),
        ("CROSSWALK", "The safe white stripes where we cross the street."),
        ("CALL 9-1-1", "The emergency number to call when someone needs help fast."),
        ("STOP & LOOK", "Always look left, right, and left again before walking."),
        ("BE A HELPER", "Kind words and helping hands make a strong community.")
    ]
    
    start_y = PAGE_HEIGHT - 1.4 * inch
    box_height = 1.15 * inch
    spacing = 1.3 * inch
    
    for i, (word, meaning) in enumerate(words):
        y = start_y - (i * spacing)
        if y < 1.0 * inch:
            break
            
        c.setStrokeColorRGB(0.2, 0.2, 0.2)
        c.setLineWidth(1.5)
        c.roundRect(0.6 * inch, y, PAGE_WIDTH - 1.2 * inch, box_height, 6)
        
        c.setStrokeColorRGB(0.7, 0.7, 0.7)
        c.setLineWidth(1)
        c.line(0.8 * inch, y + 0.9 * inch, PAGE_WIDTH - 0.8 * inch, y + 0.9 * inch)
        c.setDash(4, 3)
        c.line(0.8 * inch, y + 0.55 * inch, PAGE_WIDTH - 0.8 * inch, y + 0.55 * inch)
        c.setDash()
        c.setStrokeColorRGB(0.3, 0.3, 0.3)
        c.line(0.8 * inch, y + 0.2 * inch, PAGE_WIDTH - 0.8 * inch, y + 0.2 * inch)
        
        c.setFont("Helvetica-Bold", 24)
        c.setFillColorRGB(0.6, 0.6, 0.6)
        c.drawString(1.0 * inch, y + 0.3 * inch, word)
        
        c.setFont("Helvetica-Oblique", 9)
        c.setFillColorRGB(0.2, 0.2, 0.2)
        c.drawRightString(PAGE_WIDTH - 0.8 * inch, y + 0.95 * inch, meaning)
        
        c.setStrokeColorRGB(0.3, 0.3, 0.3)
        c.setLineWidth(1)
        c.rect(PAGE_WIDTH - 1.2 * inch, y + 0.28 * inch, 0.3 * inch, 0.3 * inch)
        c.setFont("Helvetica", 8)
        c.drawCentredString(PAGE_WIDTH - 1.05 * inch, y + 0.15 * inch, "Done!")

    c.restoreState()
    c.showPage()

def draw_certificate_page(c, page_num):
    c.saveState()
    draw_header_footer(c, "Official Junior Safety Officer Certificate", "Awarded for mastering community and police safety rules!", page_num)
    
    c.setStrokeColorRGB(0.1, 0.2, 0.5)
    c.setLineWidth(4)
    c.rect(0.6 * inch, 1.0 * inch, PAGE_WIDTH - 1.2 * inch, PAGE_HEIGHT - 2.0 * inch)
    c.setLineWidth(1)
    c.rect(0.68 * inch, 1.08 * inch, PAGE_WIDTH - 1.36 * inch, PAGE_HEIGHT - 2.16 * inch)
    
    c.setFont("Helvetica-Bold", 22)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawCentredString(PAGE_WIDTH / 2.0, PAGE_HEIGHT - 1.7 * inch, "CERTIFICATE OF ACHIEVEMENT")
    
    c.setFont("Helvetica-Bold", 13)
    c.setFillColorRGB(0.2, 0.4, 0.8)
    c.drawCentredString(PAGE_WIDTH / 2.0, PAGE_HEIGHT - 2.05 * inch, "THIS OFFICIALLY CERTIFIES THAT")
    
    c.setStrokeColorRGB(0.1, 0.1, 0.1)
    c.setLineWidth(2)
    c.line(1.5 * inch, PAGE_HEIGHT - 2.8 * inch, PAGE_WIDTH - 1.5 * inch, PAGE_HEIGHT - 2.8 * inch)
    c.setFont("Helvetica-Oblique", 11)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawCentredString(PAGE_WIDTH / 2.0, PAGE_HEIGHT - 3.0 * inch, "(Student's Full Name)")
    
    c.setFont("Helvetica", 11)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawCentredString(PAGE_WIDTH / 2.0, PAGE_HEIGHT - 3.5 * inch, "has successfully completed the NouGenArt Community Safety Course and pledged to:")
    
    pledges = [
        "1. Stop, Look, and Listen at every crosswalk before crossing.",
        "2. Memorize their home address and how to call 9-1-1 in an emergency.",
        "3. Always treat classmates, neighbors, and community helpers with kindness.",
        "4. Be a brave, helpful leader and wear helmets and seatbelts every time."
    ]
    
    for i, p in enumerate(pledges):
        c.setFont("Helvetica-Bold", 10)
        c.setFillColorRGB(0.15, 0.15, 0.15)
        c.drawString(1.1 * inch, PAGE_HEIGHT - (3.9 + i * 0.38) * inch, f"[✓]  {p}")
        
    sig_y = 2.1 * inch
    c.setLineWidth(1.5)
    c.line(1.2 * inch, sig_y, 3.4 * inch, sig_y)
    c.line(PAGE_WIDTH - 3.4 * inch, sig_y, PAGE_WIDTH - 1.2 * inch, sig_y)
    
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawCentredString(2.3 * inch, sig_y - 0.2 * inch, "Officer Kam (Police Helper)")
    c.drawCentredString(PAGE_WIDTH - 2.3 * inch, sig_y - 0.2 * inch, "Mrs. B (Lead Educator)")
    
    c.setFont("Helvetica-Bold", 11)
    c.setFillColorRGB(0.2, 0.4, 0.8)
    c.drawCentredString(PAGE_WIDTH / 2.0, 1.35 * inch, "★ OFFICIAL JUNIOR SAFETY BADGE EARNED ★")
    
    c.restoreState()
    c.showPage()

def build_pdf():
    c = canvas.Canvas(OUTPUT_PDF, pagesize=letter)
    
    # Page 1: Cover
    draw_cover_page(c)
    
    # Page 2: Officer Kam at Police Station Full Coloring Plate
    station_img = os.path.join(ASSETS_DIR, "kam_police_helper_coloring_master.jpg")
    draw_image_page(c, station_img, "Lesson 1: Meet Officer Kam & The Police Station", "Color Officer Kam on duty protecting our neighborhood!", 1)
    
    # Page 3: Kam's Safety Rules Master Activity Blackboard Plate
    safety_plate_img = os.path.join(ASSETS_DIR, "kam_community_safety_master_plate.jpg")
    draw_image_page(c, safety_plate_img, "Lesson 2: Kam's Safety Rules & 9-1-1 Emergency Icons", "Learn the 8 safety rules and count the helper cheerleaders!", 2)
    
    # Page 4: Full Color & Line Art Dual Reference Model Sheet
    model_sheet_img = os.path.join(ASSETS_DIR, "kam_police_helper_color_and_lineart_sheet.jpg")
    draw_image_page(c, model_sheet_img, "Lesson 3: Official Model Sheet & Character Colors", "Study the uniform colors and color your own Officer Kam!", 3)
    
    # Page 5: Handwriting & Safety Words Tracing
    draw_tracing_page(c, 4)
    
    # Page 6: Certificate of Completion & Junior Officer Pledge
    draw_certificate_page(c, 5)
    
    c.save()
    print(f"Generated: {OUTPUT_PDF} ({os.path.getsize(OUTPUT_PDF):,} bytes)")

if __name__ == "__main__":
    build_pdf()

"""Assemble the Complete 88-Page Single-Sided Amazon KDP Print Interior:
Alternates Recto Illustrations with Verso Bleed-Guard pages.

Output Files:
- HTML: projects/learn-with-mrs-b/pilot/kdp_88page_interior.html
- PDF:  projects/learn-with-mrs-b/pilot/learn-with-mrs-b-kdp-88page-interior.pdf
"""
import os
import shutil
import subprocess
from pathlib import Path

OUT = Path(r"~\Outpost\NouGen\projects\learn-with-mrs-b\pilot")

def get_browser():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("chrome"),
        shutil.which("msedge")
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None

def main():
    content_sequence = [
        "01_p1_see", "02_p2_say", "03_p3_color", "04_p4_trace", "05_p5_use",
        "u2_p06_see", "u2_p07_say", "u2_p08_color", "u2_p09_trace", "u2_p10_use",
        "u3_p11_see", "u3_p12_say", "u3_p13_color", "u3_p14_trace", "u3_p15_use",
        "u4_p16_see", "u4_p17_say", "u4_p18_color", "u4_p19_trace", "u4_p20_use",
        "u5_p21_see", "u5_p22_say", "u5_p23_color", "u5_p24_trace", "u5_p25_use",
        "u6_p26_see", "u6_p27_say", "u6_p28_color", "u6_p29_trace", "u6_p30_use",
        "u7_p31_see", "u7_p32_say", "u7_p33_color", "u7_p34_trace", "u7_p35_use",
        "u8_p36_see", "u8_p37_say", "u8_p38_color", "u8_p39_trace", "u8_p40_use"
    ]
    
    # 88-Page Explicit Pagination Plan
    full_88_page_plan = []
    
    # Sheet 1 (Pages 1-2): Title / Dedication
    full_88_page_plan.append(("00_cover", "Page 1 - Interior Title Page"))
    full_88_page_plan.append(("00_dedication", "Page 2 - Dedication & Belongs To"))
    
    # Sheet 2 (Pages 3-4): Swatch Grid / Bleed Guard
    full_88_page_plan.append(("00_swatch_grid", "Page 3 - 54-Circle Color Test Page"))
    full_88_page_plan.append(("00_blank_bleed_guard", "Page 4 - Protective Bleed Guard"))
    
    # Sheets 3 to 42 (Pages 5-84): 40 Unit Canvases + Alternating Bleed Guards
    for idx, name in enumerate(content_sequence, start=1):
        p_recto = 4 + (idx * 2 - 1)
        p_verso = p_recto + 1
        full_88_page_plan.append((name, f"Page {p_recto} - {name}"))
        full_88_page_plan.append(("00_blank_bleed_guard", f"Page {p_verso} - Protective Bleed Guard"))
        
    # Sheet 43 (Pages 85-86): Certificate of Completion
    full_88_page_plan.append(("41_certificate", "Page 85 - Official Certificate of Completion"))
    full_88_page_plan.append(("00_blank_bleed_guard", "Page 86 - Protective Bleed Guard"))
    
    # Sheet 44 (Pages 87-88): Back Matter Guide
    full_88_page_plan.append(("42_backmatter_guide", "Page 87 - Parent Guide & 50-Word Index"))
    full_88_page_plan.append(("00_blank_bleed_guard", "Page 88 - Final Protective Backing"))
    
    print(f"=== Assembling Full 88-Page Single-Sided KDP Interior ===")
    print(f"Total Sheets: {len(full_88_page_plan)//2} | Total Pages: {len(full_88_page_plan)}")
    
    svgs = []
    for svg_name, label in full_88_page_plan:
        svg_file = OUT / f"{svg_name}.svg"
        if svg_file.exists():
            svg_content = svg_file.read_text(encoding="utf-8")
            svgs.append(svg_content)
        else:
            print(f"ERROR: Missing SVG {svg_file}")
            return
            
    html = ("<!doctype html><html><head><meta charset='utf-8'><title>Learn With Mrs. B - 88-Page KDP Single-Sided Interior</title>"
            "<style>@page{size:8.5in 11in;margin:0}html,body{margin:0;padding:0;background:#ffffff}"
            ".pg{width:8.5in;height:11in;page-break-after:always;overflow:hidden;box-sizing:border-box}"
            ".pg svg{width:100%;height:100%}</style></head><body>"
            + "".join(f"<div class='pg'>{s}</div>" for s in svgs) + "</body></html>")
            
    master_html_path = OUT / "kdp_88page_interior.html"
    master_html_path.write_text(html, encoding="utf-8")
    print(f"Wrote {master_html_path} ({len(svgs)} pages)")
    
    pdf_path = OUT / "learn-with-mrs-b-kdp-88page-interior.pdf"
    exe = get_browser()
    if exe:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="mrsb_kdp88_") as prof:
            cmd = [
                exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--user-data-dir={prof}", f"--print-to-pdf={pdf_path}",
                master_html_path.resolve().as_uri()
            ]
            print("Rendering 88-page print PDF via headless browser...")
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=240)
        print(f"SUCCESS: Compiled Master 88-Page PDF -> {pdf_path} ({pdf_path.stat().st_size:,} bytes)")
    else:
        print("ERROR: No headless Chrome/Edge found.")

if __name__ == "__main__":
    main()

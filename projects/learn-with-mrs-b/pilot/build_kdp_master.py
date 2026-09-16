"""Assemble the Master KDP-Ready Learn With Mrs. B Book:
Cover + Dedication + 54-Circle Swatch Grid + 40 Unit Pages (Units 1-8) + Certificate of Completion.

Compiles kdp_master.html and learn-with-mrs-b-kdp-master.pdf.
"""
import os
import shutil
import subprocess
from pathlib import Path

OUT = Path(r"c:\Users\super\Outpost\NouGen\projects\learn-with-mrs-b\pilot")

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

def build_kdp_master():
    # Sequence of SVGs
    sequence = [
        "00_cover",
        "00_dedication",
        "00_swatch_grid",
        "01_p1_see", "02_p2_say", "03_p3_color", "04_p4_trace", "05_p5_use",
        "u2_p06_see", "u2_p07_say", "u2_p08_color", "u2_p09_trace", "u2_p10_use",
        "u3_p11_see", "u3_p12_say", "u3_p13_color", "u3_p14_trace", "u3_p15_use",
        "u4_p16_see", "u4_p17_say", "u4_p18_color", "u4_p19_trace", "u4_p20_use",
        "u5_p21_see", "u5_p22_say", "u5_p23_color", "u5_p24_trace", "u5_p25_use",
        "u6_p26_see", "u6_p27_say", "u6_p28_color", "u6_p29_trace", "u6_p30_use",
        "u7_p31_see", "u7_p32_say", "u7_p33_color", "u7_p34_trace", "u7_p35_use",
        "u8_p36_see", "u8_p37_say", "u8_p38_color", "u8_p39_trace", "u8_p40_use",
        "41_certificate"
    ]
    
    svgs = []
    for name in sequence:
        svg_file = OUT / f"{name}.svg"
        if svg_file.exists():
            svg_content = svg_file.read_text(encoding="utf-8")
            svgs.append(svg_content)
        else:
            print(f"Warning: SVG not found: {svg_file}")
            
    html = ("<!doctype html><html><head><meta charset='utf-8'><title>Learn With Mrs. B - Master KDP Edition</title>"
            "<style>@page{size:8.5in 11in;margin:0}html,body{margin:0;padding:0;background:#ffffff}"
            ".pg{width:8.5in;height:11in;page-break-after:always;overflow:hidden;box-sizing:border-box}"
            ".pg svg{width:100%;height:100%}</style></head><body>"
            + "".join(f"<div class='pg'>{s}</div>" for s in svgs) + "</body></html>")
            
    master_html_path = OUT / "kdp_master.html"
    master_html_path.write_text(html, encoding="utf-8")
    print(f"Wrote {master_html_path} ({len(svgs)} pages)")
    
    pdf_path = OUT / "learn-with-mrs-b-kdp-master.pdf"
    exe = get_browser()
    if exe:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="mrsb_kdp_") as prof:
            cmd = [
                exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--user-data-dir={prof}", f"--print-to-pdf={pdf_path}",
                master_html_path.resolve().as_uri()
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        print(f"Compiled Master PDF: {pdf_path} ({pdf_path.stat().st_size:,} bytes)" if pdf_path.exists() else "PDF compilation failed")
    else:
        print("No headless Chrome/Edge browser found for PDF compilation.")

if __name__ == "__main__":
    build_kdp_master()

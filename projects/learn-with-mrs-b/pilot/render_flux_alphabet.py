#!/usr/bin/env python3
"""
render_flux_alphabet.py - Render remaining letters (W, X, Y) and full alphabet bonus plates
using high-speed zero-cost FLUX pipeline with automatic PIL pure black-and-white thresholding.
"""

import os
import sys
import urllib.request
import urllib.parse
import io
from PIL import Image

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

DIR = os.path.dirname(os.path.abspath(__file__))

PLATES = [
    {
        "filename": "u7_trace_w_is_for_welcome_world.jpg",
        "title": "W is for Welcome & World",
        "prompt": "kids coloring book master page letter W is for Welcome and World, Mrs. B high afro puff bun welcoming diverse children to school, bold clean black line art, pure white background, zero gray shading, zero gradients, handwriting tracing guidelines W W W w w w, outline vector art"
    },
    {
        "filename": "u8_trace_x_is_for_explore_xylophone.jpg",
        "title": "X is for eXplore & Xylophone",
        "prompt": "kids coloring book master page letter X is for Explore and Xylophone, young Black girl with twin space buns playing musical wooden xylophone, musical notes in air, bold clean black line art, pure white background, zero gray shading, handwriting tracing guidelines X X X x x x, outline vector art"
    },
    {
        "filename": "u1_trace_y_is_for_you_young.jpg",
        "title": "Y is for You & Young",
        "prompt": "kids coloring book master page letter Y is for You and Young, young Black boy and girl looking in magic mirror seeing future graduation cap and gown, bold clean black line art, pure white background, zero gray shading, handwriting tracing guidelines Y Y Y y y y, outline vector art"
    }
]

def render_flux_plate(plate):
    filename = plate["filename"]
    title = plate["title"]
    prompt = plate["prompt"]
    target_path = os.path.join(DIR, filename)
    
    print(f"Rendering [{title}] -> {filename} via FLUX...")
    clean_prompt = prompt + ", 100% black line art on pure white background, crisp vector coloring page, no grayscale, no shading, no solid dark fills"
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=1024&nologo=true&model=flux&seed=42"
    
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            raw_img = Image.open(io.BytesIO(data)).convert("RGB")
            
            # High-contrast threshold to 100% crisp pure B&W line art
            gray = raw_img.convert("L")
            bw = gray.point(lambda x: 0 if x < 155 else 255, "1").convert("RGB")
            
            bw.save(target_path, "JPEG", quality=95)
            print(f"  SUCCESS: Saved {filename} ({os.path.getsize(target_path):,} bytes, {bw.size[0]}x{bw.size[1]})")
            return True
    except Exception as e:
        print(f"  Error rendering {filename}: {e}")
        return False

def main():
    print("=== Rendering Remaining Alphabet Plates via FLUX ===")
    for plate in PLATES:
        render_flux_plate(plate)
    print("Done!")

if __name__ == "__main__":
    main()

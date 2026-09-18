#!/usr/bin/env python3
"""
render_alphabet_batch3.py - Render remaining letters T, U, V, W, X, Y
"""

import os
import sys
import json
import base64
import urllib.request
from PIL import Image
import io

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

DIR = os.path.dirname(os.path.abspath(__file__))

KEYS = [
    ("kushboygroup", os.environ.get("OPENROUTER_API_KEY", "")),
    ("whovisionsteam", os.environ.get("OPENROUTER_API_KEY", "")),
    ("aiwithdav3", os.environ.get("OPENROUTER_API_KEY", "")),
    ("davemeralus", os.environ.get("OPENROUTER_API_KEY", "")),
    ("nougenai", os.environ.get("OPENROUTER_API_KEY", "")),
    ("superdavewho", os.environ.get("OPENROUTER_API_KEY", "")),
    ("whovisions", os.environ.get("OPENROUTER_API_KEY", "")),
    ("whovisionsllc", os.environ.get("OPENROUTER_API_KEY", "")),
]

MODELS = [
    "google/gemini-2.5-flash-image",
    "google/gemini-3.1-flash-lite-image",
    "google/gemini-3.1-flash-image"
]

REMAINING_PAGES = [
    {
        "filename": "u8_trace_t_is_for_together_teacher.jpg",
        "title": "T is for Together & Teacher",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter T. 100% pure black and white line art on a pure white background. Zero gray shading.

Top section:
Large outline uppercase 'T' and lowercase 't' for coloring.
Dotted tracing lines: 'T T T' and 't t t'.

Middle section - Storybook Illustration:
Mrs. B (beloved educator with high bun and lanyard badge) standing in the center of a circle of diverse happy students (including Little Dave, Curious, and friends) holding hands around a giant classroom parachute or friendship circle.
Colorful confetti and heart ribbons flutter in the air.
A big classroom banner in the background reads: 'WE ARE BETTER TOGETHER ♡ NOU PI FÒ ANSANM'.

Bottom section:
Bold outline word labels: 'TOGETHER' and 'TEACHER'.
Bilingual subtitle: 'ansanm / pwofesè'.
Prompt box: 'Write a thank-you note to your teacher!'

Master coloring book line art."""
    },
    {
        "filename": "u1_trace_u_is_for_unique_unity.jpg",
        "title": "U is for Unique & Unity",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter U. 100% pure black and white line art on a pure white background.

Top section:
Large outline uppercase 'U' and lowercase 'u' for coloring.
Dotted tracing lines: 'U U U' and 'u u u'.

Middle section - Storybook Illustration:
Curious and Little Dave holding up a giant colorful rainbow umbrella together during a gentle warm sunshower.
Under the umbrella, animal friends (a bunny, a puppy, and a kitten) shelter peacefully together.
A brilliant double rainbow arches across the sky with smiling clouds.

Bottom section:
Bold outline word labels: 'UNIQUE' and 'UNITY'.
Bilingual subtitle: 'inik / inite'.
Banner: 'Each of us is special, and together we shine!'

Crisp black and white line art."""
    },
    {
        "filename": "u6_trace_v_is_for_village_victory.jpg",
        "title": "V is for Village & Victory",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter V. 100% pure black and white line art on a pure white background.

Top section:
Large outline uppercase 'V' and lowercase 'v' for coloring.
Dotted tracing lines: 'V V V' and 'v v v'.

Middle section - Storybook Illustration:
A festive school sports day and community celebration.
Little Dave crossing the finish line with arms raised in victory, breaking a celebration ribbon.
Curious, Mrs. B, and the whole family cheering and waving victory flags from the bleachers.
Medals, ribbons, and a shiny trophy stand on a podium.

Bottom section:
Bold outline word labels: 'VILLAGE' and 'VICTORY'.
Bilingual subtitle: 'vilaj / viktwa'.
Banner: 'It takes a whole village to raise a champion!'

Clean outline coloring master plate."""
    },
    {
        "filename": "u7_trace_w_is_for_welcome_world.jpg",
        "title": "W is for Welcome & World",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter W. 100% pure black and white line art on a pure white background.

Top section:
Large outline uppercase 'W' and lowercase 'w' for coloring.
Dotted tracing lines: 'W W W' and 'w w w'.

Middle section - Storybook Illustration:
Mrs. B standing at the open classroom doorway with open arms welcoming children from all cultures into the school.
Little Dave holds a welcome sign in English and Haitian Creole: 'WELCOME / BYENVINI!'.
Flags of different nations and hand-painted welcome banners hang across the hallway.

Bottom section:
Bold outline word labels: 'WELCOME' and 'WORLD'.
Bilingual subtitle: 'byenvini / mond'.
Prompt: 'How do you say welcome in your family?'

Crisp children's coloring book line art."""
    },
    {
        "filename": "u8_trace_x_is_for_explore_xylophone.jpg",
        "title": "X is for eXplore & Xylophone",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter X. 100% pure black and white line art on a pure white background.

Top section:
Large outline uppercase 'X' and lowercase 'x' for coloring.
Dotted tracing lines: 'X X X' and 'x x x'.

Middle section - Storybook Illustration:
A joyful classroom music band!
Curious playing a colorful wooden xylophone with mallets, smiling with musical rhythm.
Little Dave plays the saxophone or tambourine.
Musical notes (treble clefs, quarter notes, eighth notes) dance through the air like magical bubbles around Mrs. B as she conducts with a baton.

Bottom section:
Bold outline word labels: 'XYLOPHONE' and 'EXPLORE'.
Bilingual subtitle: 'ksilofòn / eksplore'.
Activity: 'Color each bar of the xylophone a different color!'

Master coloring book line art."""
    },
    {
        "filename": "u1_trace_y_is_for_you_young.jpg",
        "title": "Y is for You & Young",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter Y. 100% pure black and white line art on a pure white background.

Top section:
Large outline uppercase 'Y' and lowercase 'y' for coloring.
Dotted tracing lines: 'Y Y Y' and 'y y y'.

Middle section - Storybook Illustration:
A full-length magic mirror frame decorated with stars and affirmations ('YOU ARE SMART ♡ YOU ARE LOVED ♡ YOU ARE CAPABLE').
Little Dave and Curious stand in front of the mirror, seeing their bright future reflections wearing cap & gown graduation crowns.
Mrs. B places a gentle encouraging hand on their shoulders.

Bottom section:
Bold outline word labels: 'YOU' and 'YOUNG'.
Bilingual subtitle: 'ou menm / jèn'.
Activity box: 'Draw a picture of YOU in the magic mirror!'

High-contrast clean coloring book master plate."""
    }
]

def generate_page(page_info):
    filename = page_info["filename"]
    title = page_info["title"]
    prompt = page_info["prompt"]
    target_path = os.path.join(DIR, filename)
    
    if os.path.exists(target_path) and os.path.getsize(target_path) > 50000:
        print(f"Already exists: {filename}")
        return True
        
    print(f"\nStarting generation for: {title} -> {filename}")
    
    for key_name, api_key in KEYS:
        for model in MODELS:
            try:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://nougen.ai",
                    "X-Title": "NouGen Masterclass Book"
                }
                
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
                
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers
                )
                
                with urllib.request.urlopen(req, timeout=90) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    choice = res.get("choices", [{}])[0]
                    message = choice.get("message", {})
                    
                    img_data = None
                    images = message.get("images", [])
                    if images and len(images) > 0:
                        img_url = images[0].get("image_url", {}).get("url", "")
                        if "base64," in img_url:
                            b64_str = img_url.split("base64,")[1]
                            img_data = base64.b64decode(b64_str)
                    
                    if not img_data:
                        content = message.get("content", "")
                        if "data:image" in content and "base64," in content:
                            b64_part = content.split("base64,")[1].split('"')[0].split(")")[0].strip()
                            img_data = base64.b64decode(b64_part)
                    
                    if img_data:
                        raw_img = Image.open(io.BytesIO(img_data)).convert("RGB")
                        gray = raw_img.convert("L")
                        bw = gray.point(lambda x: 0 if x < 160 else 255, "1").convert("RGB")
                        bw.save(target_path, "JPEG", quality=95)
                        print(f"  SUCCESS via [{key_name} - {model}]: {filename} ({os.path.getsize(target_path):,} bytes)")
                        return True
            except Exception as e:
                continue
                
    print(f"  FAILED to render {filename} after all keys.")
    return False

def main():
    print(f"=== Rendering Remaining 6 Plates (T, U, V, W, X, Y) ===")
    successes = 0
    for page in REMAINING_PAGES:
        if generate_page(page):
            successes += 1
    print(f"\nFinal Alphabet Complete: {successes}/{len(REMAINING_PAGES)} rendered.")

if __name__ == "__main__":
    main()

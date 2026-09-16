#!/usr/bin/env python3
"""
render_alphabet_plates.py - Autonomous Master Coloring & Activity Renderer
Uses fleet OpenRouter image endpoints to generate 100% pure black & white
coloring and alphabet handwriting activity plates.

Saves directly to JPEG/PNG in projects/learn-with-mrs-b/pilot/ with exact
proportional aspect ratio and pure line-art contrast.
"""

import os
import sys
import json
import base64
import urllib.request
from PIL import Image, ImageOps
import io

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

DIR = os.path.dirname(os.path.abspath(__file__))

OPENROUTER_KEYS = [
    os.environ.get("OPENROUTER_API_KEY", ""),
    os.environ.get("OPENROUTER_API_KEY", ""),
    os.environ.get("OPENROUTER_API_KEY", ""),
    os.environ.get("OPENROUTER_API_KEY", ""),
    os.environ.get("OPENROUTER_API_KEY", "")
]

MODELS = [
    "google/gemini-2.5-flash-image",
    "google/gemini-3.1-flash-image",
    "google/gemini-3-pro-image"
]

PAGES_TO_RENDER = [
    {
        "filename": "u1_trace_a_is_for_astronaut_apple.jpg",
        "title": "A is for Astronaut & Apple",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter A. 100% pure black and white line art on a clean pure white background. Zero gray shading, zero gradients, zero colors. Bold clean vector-style coloring outlines.

Top section:
Prominent large uppercase 'A' and lowercase 'a' in bold outline fonts for children to color in.
Underneath the big letters, horizontal handwriting tracing guide lines showing dotted uppercase 'A A A' and dotted lowercase 'a a a' with directional stroke numbers and arrows for preschool handwriting practice.

Middle section - Full Storybook Coloring Illustration:
Kid Dave (young Black boy with a neat clean fade haircut, confident friendly smile) dressed in a playful astronaut suit holding space blueprint roll and looking up at the stars and planets.
Next to him is young niece Kendall Amelia ('Curious', young Black girl with iconic twin puffy space buns with colorful bead bands, cute heart dress) reaching joyfully towards a large cartoon apple hanging from an apple tree branch.
In the background: cartoon planets, smiling stars, a gentle crescent moon, and an apple basket.

Bottom section:
Bold clear outline word labels: 'ASTRONAUT' and 'APPLE'.
Bilingual English and Haitian Creole subtitle: 'astwonòt / pòm'.
A small decorative dotted box with 'Draw your own Apple or Rocket!' activity prompt.

Crisp high-contrast children's coloring book master plate, ready for Amazon KDP print."""
    },
    {
        "filename": "u1_trace_c_is_for_curious_community.jpg",
        "title": "C is for Curious & Community",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter C. 100% pure black and white line art on a clean pure white background. Zero gray shading, zero gradients, zero color fills. Bold clean vector-style coloring outlines.

Top section:
Large bold outline uppercase 'C' and lowercase 'c' for coloring.
Dotted handwriting tracing lines: 'C C C' and 'c c c' with handwriting guide lines and starting dots.

Middle section - Storybook Coloring Illustration:
Young niece Kendall Amelia Meralus ('Curious' - young Black girl with twin puffy space buns with bead bands, heart pinafore dress, and Crocs) holding a magnifying glass and exploring a vibrant community flower and vegetable garden.
Next to her, Little Dave is watering large sunflowers with a watering can.
In the background: friendly neighborhood houses, fluttering butterflies, blooming carrots, and smiling sun.

Bottom section:
Bold outline word labels: 'CURIOUS' and 'COMMUNITY'.
Bilingual subtitle: 'kirye / kominote'.
Dotted activity box: 'Find and color 3 hidden caterpillars in the garden!'

Crisp high-contrast coloring book page, clean outline vector style."""
    },
    {
        "filename": "u2_trace_f_is_for_family_forever.jpg",
        "title": "F is for Family & Forever (The Sacred Meralus Lineup)",
        "prompt": """A sacred, beautiful professional children's coloring and alphabet activity page for the letter F. 100% pure black and white line art on a pure white background. Zero gray shading, zero solid black blocks. Bold clean coloring outlines.

Top section:
Large bold outline uppercase 'F' and lowercase 'f' for coloring.
Dotted handwriting guide lines: 'F F F' and 'f f f' with tracing dots and arrows.

Middle section - Full Family Storybook Illustration:
A heartwarming family portrait lineup standing together on a grassy lawn with flowers:
From left to right:
1. Mrs. B (beloved Haitian-American matriarch & teacher with high afro puff bun, hoop earrings, and welcoming open smile).
2. Tedley (Twin 1 in graduation cap & gown holding his diploma ribbon).
3. Dad (techdadteddy with neat styled locs updo and kind beard).
4. Kendall Meralus (Twin 2 — beloved brother who passed away April 12, 2020, depicted as a handsome smiling young angel with beautiful feathered angel wings, a gentle glowing halo, and a heart ribbon badge).
5. Dave Meralus (Dav3 - smiling proudly in his tailored blazer).
In front of them: Little Dave (in his smart suit with blueprints) and young Kendall Amelia ('Curious' in her twin space buns and heart dress) holding hands and waving with joy.
Above them: a rainbow arch made of hearts and sparkling stars.

Bottom section:
Bold outline word labels: 'FAMILY' and 'FOREVER'.
Bilingual subtitle: 'fanmi / pou tout tan'.
Dotted banner: 'We are strong when we love each other!'

Pure high-contrast black line art coloring book master plate."""
    },
    {
        "filename": "u3_trace_g_is_for_grandpa_gratitude.jpg",
        "title": "G is for Grandpa & Gratitude",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter G. 100% pure black and white line art on a pure white background. Zero gray shading, zero fills. Bold clean outlines.

Top section:
Large outline uppercase 'G' and lowercase 'g' for coloring.
Dotted tracing guidelines: 'G G G' and 'g g g' with handwriting stroke guides.

Middle section - Storybook Illustration:
Beloved Grandpa (kind older Black gentleman with smooth bald crown, warm mustache, and wireframe glasses) sitting comfortably in a wooden rocking chair on a porch, holding open a big illustrated storybook.
Sitting on a cozy braided rug at his feet: Little Dave and niece Curious, listening attentively with big smiles and holding cups of warm cocoa.
In the background: potted ferns, porch railing, and singing birds on a tree branch.

Bottom section:
Bold outline word labels: 'GRANDPA' and 'GRATITUDE'.
Bilingual subtitle: 'granpè / rekonesans'.
Prompt box: 'What makes you feel grateful today?'

Crisp children's coloring book line art ready for printing."""
    },
    {
        "filename": "u3_trace_k_is_for_kind_kendall.jpg",
        "title": "K is for Kind & Kendall",
        "prompt": """A touching, beautiful children's coloring and alphabet handwriting activity page for the letter K. 100% pure black and white line art on a pure white background. Zero grayscale, zero fills. Bold clean outlines.

Top section:
Large outline uppercase 'K' and lowercase 'k' for children to color.
Dotted tracing lines: 'K K K' and 'k k k' with preschool stroke arrows.

Middle section - Sacred Storybook Illustration:
Niece Kendall Amelia Meralus ('Curious', twin space buns with bead bands, heart dress) standing under a peaceful starlit sky, gently holding a warm glowing lantern that shines with heart-shaped light beams.
In the soft starlight above, the gentle smiling silhouette of her uncle Kendall Meralus (angel wings, gentle smile) watching over her with eternal protection and love.
Next to Curious, a playful puppy with a heart collar sits beside a blooming garden of hibiscus flowers.

Bottom section:
Bold outline word labels: 'KIND' and 'KENDALL'.
Bilingual subtitle: 'jantiy / renmen'.
Dotted banner: 'Kindness shines like the brightest star!'

High-contrast clean coloring book master plate."""
    },
    {
        "filename": "u4_trace_l_is_for_learn_love.jpg",
        "title": "L is for Learn & Love",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter L. 100% pure black and white line art on a pure white background. Zero grayscale shading, zero color fills. Bold clean outlines.

Top section:
Large outline uppercase 'L' and lowercase 'l' for coloring.
Dotted tracing lines: 'L L L' and 'l l l' with stroke direction guides.

Middle section - Storybook Illustration:
Mrs. B (high afro puff bun, hoop earrings, cozy cardigan with 'B' heart badge) standing at a large classroom chalkboard pointing to the alphabet letters A, B, C, D and writing 'BONJOU / HELLO ♡'.
At little wooden classroom desks: Little Dave (with his notebook and pencil) and niece Curious raise their hands eagerly to answer.
Alphabet building blocks and heart bubbles float cheerfully around the classroom.

Bottom section:
Bold outline word labels: 'LEARN' and 'LOVE'.
Bilingual subtitle: 'aprann / renmen'.
Activity box: 'Circle all the hearts you can find in the classroom!'

Crisp children's coloring book master plate."""
    },
    {
        "filename": "u5_trace_p_is_for_pony_peace.jpg",
        "title": "P is for Pony & Peace",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter P. 100% pure black and white line art on a pure white background. Zero gray shading. Bold vector coloring outlines.

Top section:
Large outline uppercase 'P' and lowercase 'p' for coloring.
Dotted tracing lines: 'P P P' and 'p p p' with handwriting guide lines.

Middle section - Storybook Illustration:
A cute, gentle miniature pony with a braided mane and flower garland standing peacefully in a sunny farm pasture.
Niece Curious ('Kendall Amelia', space buns with beads) is gently brushing the pony's mane with a soft brush.
Little Dave stands beside the wooden fence holding a juicy red apple for the pony to nibble on.
In the background: a friendly red barn outline, wooden fences, rolling hills, and sunflowers.

Bottom section:
Bold outline word labels: 'PONY' and 'PEACE'.
Bilingual subtitle: 'cheval / lapè'.
Activity box: 'Count the flowers in the pony's mane!'

Crisp coloring book line art, Amazon KDP print ready."""
    },
    {
        "filename": "u6_trace_r_is_for_read_respect.jpg",
        "title": "R is for Read & Respect",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter R. 100% pure black and white line art on a pure white background. Zero gray shading. Bold clean outlines.

Top section:
Large outline uppercase 'R' and lowercase 'r' for coloring.
Dotted tracing lines: 'R R R' and 'r r r' with preschool handwriting guides.

Middle section - Storybook Illustration:
Kid Dave (young Dave in his sharp tailored pinstripe suit, collared shirt, and clean fade haircut) sitting proudly in a high-back wicker peacock chair, holding open his favorite book titled 'GOOD PEOPLE BRIGHTER TOMORROWS ♡'.
Next to him, Mrs. B sits on a stool holding her teacher binder titled 'Kind People Brighter Futures ♡'.
Surrounding them are tall library bookshelves filled with books, a desk globe, and a glowing study lamp.

Bottom section:
Bold outline word labels: 'READ' and 'RESPECT'.
Bilingual subtitle: 'li / respè'.
Banner: 'Reading opens the door to all your dreams!'

High-contrast clean coloring book master plate."""
    },
    {
        "filename": "u7_trace_s_is_for_star_shapes.jpg",
        "title": "S is for Star & Shapes",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter S. 100% pure black and white line art on a pure white background. Zero grayscale. Bold clean vector outlines.

Top section:
Large outline uppercase 'S' and lowercase 's' for coloring.
Dotted tracing lines: 'S S S' and 's s s' with handwriting arrows.

Middle section - Storybook Illustration:
Niece Curious and Little Dave outdoors on a picnic blanket on a starry night, holding a bunch of playful geometric shape balloons: a smiling Star, a Circle, a Square, a Triangle, and a Heart.
In the night sky above: giant constellation outlines connecting stars into shapes (a big smiling teddy bear constellation and a spaceship constellation).

Bottom section:
Bold outline word labels: 'STAR' and 'SHAPES'.
Bilingual subtitle: 'zetwal / fòm'.
Matching activity box: 'Match the shape word to each balloon!'

Crisp children's coloring book line art."""
    },
    {
        "filename": "u8_trace_z_is_for_zoom_zenith.jpg",
        "title": "Z is for Zoom & Zenith",
        "prompt": """A complete professional children's coloring and alphabet handwriting activity page for the letter Z. 100% pure black and white line art on a pure white background. Zero gray shading. Bold clean outlines.

Top section:
Large outline uppercase 'Z' and lowercase 'z' for coloring.
Dotted tracing lines: 'Z Z Z' and 'z z z' with directional arrows.

Middle section - Storybook Illustration:
Little Dave and niece Curious inside a creative cardboard rocket ship they built together, decorated with foil stars, buttons, and dials, pretending to blast off to the moon.
All 26 letters of the alphabet (A through Z) float joyfully around their rocket like sparkling cosmic dust.
Mrs. B stands nearby smiling and cheering through a cardboard megaphone: 'To the top! Reach your Zenith!'

Bottom section:
Bold outline word labels: 'ZOOM' and 'ZENITH'.
Bilingual subtitle: 'vole / zénit'.
Celebration banner: 'Congratulations! You mastered the entire alphabet!'

Master coloring and graduation activity page."""
    }
]

def generate_page(page_info):
    filename = page_info["filename"]
    title = page_info["title"]
    prompt = page_info["prompt"]
    target_path = os.path.join(DIR, filename)
    
    print(f"\n🎨 Starting generation for: {title} -> {filename}")
    
    for key_idx, api_key in enumerate(OPENROUTER_KEYS):
        for model in MODELS:
            try:
                print(f"  Attempting with Key #{key_idx+1} on model [{model}]...")
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
                    
                    # Extract image data (either in images list or markdown/base64)
                    img_data = None
                    images = message.get("images", [])
                    if images and len(images) > 0:
                        img_url = images[0].get("image_url", {}).get("url", "")
                        if "base64," in img_url:
                            b64_str = img_url.split("base64,")[1]
                            img_data = base64.b64decode(b64_str)
                    
                    # If not in images array, check text content for base64 or markdown url
                    if not img_data:
                        content = message.get("content", "")
                        if "data:image" in content and "base64," in content:
                            b64_part = content.split("base64,")[1].split('"')[0].split(")")[0].strip()
                            img_data = base64.b64decode(b64_part)
                    
                    if img_data:
                        # Process image: ensure 100% crisp pure B&W line art
                        raw_img = Image.open(io.BytesIO(img_data)).convert("RGB")
                        
                        # High contrast threshold to pure black & white line art
                        gray = raw_img.convert("L")
                        bw = gray.point(lambda x: 0 if x < 160 else 255, "1").convert("RGB")
                        
                        bw.save(target_path, "JPEG", quality=95)
                        print(f"  ✅ SUCCESS: Rendered & saved {filename} ({os.path.getsize(target_path):,} bytes, {bw.size[0]}x{bw.size[1]})")
                        return True
                    else:
                        print(f"  Warning: No image in response from {model}, message content: {str(message)[:100]}")
            except Exception as e:
                print(f"  Error on {model}: {e}")
                continue
                
    print(f"  ❌ FAILED to render {filename} after all retries.")
    return False

def main():
    print(f"=== NouGen Masterclass Book: Batch Plate Renderer ===")
    print(f"Total plates to cook: {len(PAGES_TO_RENDER)}")
    
    successes = 0
    for page in PAGES_TO_RENDER:
        if generate_page(page):
            successes += 1
            
    print(f"\n==========================================")
    print(f"Batch generation complete: {successes}/{len(PAGES_TO_RENDER)} plates rendered successfully.")
    print(f"==========================================")

if __name__ == "__main__":
    main()

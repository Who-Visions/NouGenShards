# Higgsfield AI Prompt Engine Architecture & Model Integration

## 1. Overview
Higgsfield AI is a multi-engine cinematic AI video and image production platform hosting:
- **Video Models**: Kling 3.0 / 3.0 Omni / Motion Control, Sora 2 (UI-only tier), Google Veo 3.1 / 3.1 Lite, Wan 2.7 / 2.6 / 2.5, Seedance 2.5 / 2.0 / Pro, Minimax Hailuo 2.3 / 02, FLUX 3 Video, Higgsfield DoP (Lite / Standard / Turbo).
- **Image Models**: Soul 2.0 / Cinema Preview / Cast (Soul ID character consistency), Nano Banana Pro / 2, Kling Image 3.0 / Omni, Seedream 4.0, GPT Image 2.0, Flux 2 / Kontext.
- **Engines & Tooling**: 100+ named Motion Presets, Cinema Studio 2.5 / 3.0 / 3.5, Vibe Motion, Soul Cast AI actors, dual-channel stereo audio, Photodump presets.

---

## 2. Mandatory Prompt Architecture: MCSLA

Every single-shot video prompt MUST follow the 5-layer **MCSLA** structure:

```
[MODEL] Kling 3.0 | 16:9 | 8s
[CAMERA] Atmosphere push-in, low-angle 24mm anamorphic lens, steady tracking
[SUBJECT] Detective David Chen, weathered trench coat, rain droplets glistening on collar
[LOOK] Cyberpunk neo-noir, high contrast 35mm film grain, tungsten street reflections, cyan rim light
[ACTION] Pulls silver lighter from pocket, thumb clicks wheel once, flame illuminates jawline as gaze snaps to alley entrance
```

### The 5 Layers
1. **Model Header**: Model identifier, aspect ratio enum (e.g. `16:9`, `9:16`, `21:9`), duration (seconds).
2. **Camera**: Named camera preset or optical specification (lens mm, angle, movement velocity, rig).
3. **Subject**: Key character/object with precise visual anchors, clothing, physical textures.
4. **Look**: Lighting palette, film stock, color grading, atmosphere, volumetric cues.
5. **Action**: Chronological verb-driven physical motion and micro-expressions.

---

## 3. Seedance Block-Scaffold Production Prompts
For long-form, complex narrative shots, Seedance replaces single-shot MCSLA with structured section blocks:

```markdown
# SHOT BRIEF: Rain Alley Confrontation

## 1. SCENE INTENT & PACE
- Tempo: Slow build tension
- Mood: Ominous, clinical

## 2. SPATIAL BLOCKING & ENVIRONMENT
- Location: Damp wet alleyway between brick high-rises
- Depth: Fore-ground fire escape, mid-ground subject, back-ground neon haze

## 3. CHARACTER CONTINUITY (SOUL ID)
- Subject: [Soul-ID: Chen-04], sharp jawline, stubble, damp wool collar

## 4. CHOREOGRAPHED ACTION (TIME-CODED)
- 00:00 - 00:03: Subject steps out of shadow, left boot splashes in puddle
- 00:03 - 00:06: Camera tracks sideways; subject turns head 45 degrees left
- 00:06 - 00:08: Subject halts, hand enters frame holding encrypted glass drive

## 5. OPTICAL & LIGHTING MANIFEST
- Camera: Arri Alexa 65 look, 35mm Master Prime, subtle handheld breathing
- Lighting: Backlit rain from high sodium vapor streetlamp, soft cool fill from neon billboard
```

---

## 4. Hard Constraints & Negative Phrasing
- Positive-phrasing constraint rule: Modern models (Kling 3.0, Veo 3.1) interpret positive phrasing significantly better than traditional negative lists ("clear stable limbs, anatomically correct five-fingered hands, sharp focus" vs "no bad anatomy, no extra fingers").
- Aspect ratio rule: Strict enum adherence (Seedance supports native 21:9; Kling requires standard 16:9/9:16/1:1).

---

## 5. Fleet Skill Location & Sub-skills
- Installed path: `C:\Users\super\.gemini\config\skills\higgsfield-ai-prompt-skill\`
- Active junction: `C:\Users\super\.gemini\config\skills\higgsfield\`
- Sub-skill modules: 33 specialized modules for acting, camera, motion, seedance, cinema studio, soul character locking, and marketing factory.

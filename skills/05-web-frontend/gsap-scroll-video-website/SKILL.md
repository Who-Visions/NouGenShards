---
name: gsap-scroll-video-website
description: "Build scroll-driven animated websites with video background synchronized to scroll position using Vite + GSAP ScrollTrigger + SplitText + Lenis. Creates cinematic one-page experiences where a background video plays as the user scrolls, with text reveal animations, gradient effects, and section-by-section narrative storytelling."
risk: low
source: "nougentube:5ryZ6Tsco9c (AI Foundations - Opus 5.5 Website Build)"
date_added: "2026-09-28"
---

# gsap-scroll-video-website

## 1. Stack
- **Vite**: Build tool for fast local development and optimized production builds.
- **GSAP**: Core animation library.
- **GSAP ScrollTrigger**: Plugin for triggering animations based on scroll position.
- **GSAP SplitText**: Plugin for splitting text into words/characters for staggered reveals.
- **Lenis**: Smooth scrolling library.
- **Optional PHP Backend**: For simple lead capture forms.

## 2. Architecture
- **Lenis** provides smooth scroll behavior across all devices.
- **GSAP ScrollTrigger** pins the video and controls playback position based on scroll depth.
- **SplitText** splits headings into individual characters/words for staggered reveal animations.
- Video `currentTime` is mapped to scroll progress (0-1) × `video.duration`.
- Each section acts as a scroll-triggered scene with its own dedicated animations, timed with the video background.

## 3. Scaffolding
Run the following commands to bootstrap your project:
```bash
npm create vite@latest project-name -- --template vanilla
cd project-name
npm install gsap lenis
```
*Note: GSAP ScrollTrigger and SplitText are included in the gsap package. You just need to register them as plugins in your code.*

## 4. Core Pattern: Video Scroll Sync
The key code pattern to sync your video playback with scroll progress:
```javascript
import Lenis from 'lenis'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'

gsap.registerPlugin(ScrollTrigger, SplitText)

// Smooth scrolling
const lenis = new Lenis()
lenis.on('scroll', ScrollTrigger.update)
gsap.ticker.add((time) => lenis.raf(time * 1000))
gsap.ticker.lagSmoothing(0)

// Video scroll sync
const video = document.querySelector('.hero-video')
ScrollTrigger.create({
  trigger: '.video-container',
  start: 'top top',
  end: 'bottom bottom',
  pin: '.video-wrapper',
  scrub: true,
  onUpdate: (self) => {
    if (video.duration) {
      video.currentTime = self.progress * video.duration
    }
  }
})
```

## 5. Text Reveal Patterns
Use SplitText for dynamic word/char animations on scroll:
```javascript
// Word-by-word reveal on scroll
const split = new SplitText('.reveal-text', { type: 'words' })
gsap.from(split.words, {
  scrollTrigger: {
    trigger: '.reveal-text',
    start: 'top 80%',
    end: 'top 20%',
    scrub: true
  },
  opacity: 0,
  y: 30,
  stagger: 0.05
})
```

## 6. Gradient Effects
Temperature/mood gradient for thematic sections:
```javascript
// Hot-to-cool gradient transition (e.g., asphalt = orange → white)
ScrollTrigger.create({
  trigger: '.hot-section',
  start: 'top center',
  end: 'bottom center',
  onUpdate: (self) => {
    const progress = self.progress
    const color = gsap.utils.interpolate('#FF6B00', '#FFFFFF', progress)
    document.querySelector('.hot-text').style.color = color
  }
})
```

## 7. Section-by-Section Narrative
HTML structure pattern for scroll storytelling:
```html
<div class="scroll-narrative">
  <div class="video-container" style="height: 500vh">
    <div class="video-wrapper">
      <video class="hero-video" muted playsinline preload="auto">
        <source src="/video.mp4" type="video/mp4">
      </video>
    </div>
    <section class="scene" data-scene="1">
      <h2 class="reveal-text">Every crack is an open door for water.</h2>
    </section>
    <section class="scene" data-scene="2">
      <h2 class="reveal-text">We don't pave over problems. We remove them.</h2>
    </section>
    <!-- More scenes... -->
  </div>
</div>
```

## 8. Performance Notes
- Preload video with `preload="auto"`
- Use `muted playsinline` for autoplay compatibility on mobile
- Keep video under 20MB for smooth scrubbing
- Use `will-change: transform` sparingly on animated elements
- Lenis `lagSmoothing(0)` prevents GSAP ticker stutter

## 9. Lead Capture Integration
For an optional PHP backend:
- Simple form POST to PHP endpoint
- SQLite or MySQL for lead storage
- Form validation client-side with progressive enhancement

## 10. Deployment Checklist
- Run `npm run build` to generate the `dist/` folder
- Upload `dist/` to any static host (Hostinger, Vercel, Netlify, Cloud Run)
- For PHP backend: ensure PHP 8+ on host
- Set correct MIME types for video files

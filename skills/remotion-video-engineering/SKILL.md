---
name: remotion-video-engineering
description: Programmatic video engineering, frame-perfect React animation, motion kinematics, dynamic audio sync, and headless rendering pipeline for Remotion. Used by NouGen agents for automated visual synthesis, video composition, and media pipelines.
version: 4.0.523
---

# 🎬 Remotion Video Engineering (NouGen Shang Tsung Edition)

`remotion-video-engineering` is the native NouGen evolution of programmatic React video engineering. It provides domain-specific video engineering patterns, frame-accurate motion physics, audio synchronization, and headless CLI rendering across the Observatory swarm.

---

## 🏛️ 1. Core Principles of Video-as-Code

1. **Frame-Driven State (`useCurrentFrame()`)**:
   - In Remotion, time is quantized into discrete integers: `frame = useCurrentFrame()`.
   - Never use CSS `@keyframes`, transitions, or `setInterval` for animations. Every property must be a pure, deterministic function of `frame` and `fps`.
2. **Spring Physics & Motion Kinematics**:
   - Use `spring({ frame, fps, config: { damping: 200, mass: 1, stiffness: 100 } })` for organic deceleration.
   - Use `interpolate(frame, inputRange, outputRange, options)` with `Easing.bezier()` or `Easing.spring()`.
   - Prefer modern CSS transform shorthands (`scale`, `translate`, `rotate`) over composite `transform` strings.
   - For scale interpolations, always specify `output: 'perceptual-scale'`.
3. **Timeline Sequencing & Composition Architecture**:
   - Nest scenes using `<Sequence from={startFrame} durationInFrames={length}>` or `<Series>`.
   - Encapsulate parameters in Zod schemas (`z.object({...})`) to allow automated parameter injection by NouGen agents.
4. **Zero-Cost CLI & Headless Rendering**:
   - Preview compositions interactively via Remotion Studio: `npx remotion preview`.
   - Headless CLI rendering to MP4/WebM: `npx remotion render <entry> <comp-id> out/<name>.mp4`.
   - Transparent video rendering using ProRes 4444 or VP9 with alpha channel.

---

## ⚡ 2. Canonical Motion & Animation Patterns

### Frame Interpolation with Clamp and Easing
```tsx
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

export const TitleCard = ({ title }: { title: string }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const translateY = interpolate(frame, [0, fps * 0.75], [40, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.spring({ damping: 15, mass: 0.8 }),
  });

  return (
    <div
      style={{
        opacity,
        translate: `0px ${translateY}px`,
        fontSize: "72px",
        fontWeight: "bold",
        fontFamily: "Inter, sans-serif",
        color: "#ffffff",
      }}
    >
      {title}
    </div>
  );
};
```

### Staggered Sequences & Transitions
```tsx
import { Sequence, useVideoConfig } from "remotion";
import { TitleCard } from "./TitleCard";
import { FeatureGrid } from "./FeatureGrid";

export const ExplainerVideo = () => {
  const { fps } = useVideoConfig();

  return (
    <div style={{ flex: 1, backgroundColor: "#000000" }}>
      {/* Intro sequence: 0s to 3s */}
      <Sequence from={0} durationInFrames={fps * 3}>
        <TitleCard title="Autonomous Fleet Intelligence" />
      </Sequence>

      {/* Main feature showcase: 2.5s to 8s (overlapping transition) */}
      <Sequence from={Math.round(fps * 2.5)} durationInFrames={fps * 5.5}>
        <FeatureGrid />
      </Sequence>
    </div>
  );
};
```

---

## 🔊 3. Audio & Subtitle Synchronization

- **Audio Trimming & Volume Curves**:
  ```tsx
  import { Audio, staticFile, interpolate, useCurrentFrame } from "remotion";

  export const BackgroundTrack = () => {
    const frame = useCurrentFrame();
    const volume = interpolate(frame, [0, 30, 270, 300], [0, 0.8, 0.8, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });

    return <Audio src={staticFile("audio/ambient-beat.mp3")} volume={volume} />;
  };
  ```
- **Frame-Accurate Transcript Alignment**:
  - Calculate word display intervals using: `wordStartFrame = Math.round(word.startSeconds * fps)`.

---

## 🛠️ 4. Headless Automated Pipeline

NouGen agents orchestrate video generation via CLI subcommands:

1. **Bootstrap Project**:
   ```bash
   npx create-video@latest --yes --blank --no-tailwind <target-dir>
   ```
2. **Preview Studio**:
   ```bash
   npx remotion preview
   ```
3. **Headless MP4 Render**:
   ```bash
   npx remotion render src/index.ts MainComposition out/video.mp4 --concurrency=8 --gl=angle
   ```
4. **Still Frame Extraction**:
   ```bash
   npx remotion still src/index.ts MainComposition out/thumbnail.png --frame=45
   ```

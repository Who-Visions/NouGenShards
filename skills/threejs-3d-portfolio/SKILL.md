---
name: threejs-3d-portfolio
description: Expert engineering patterns for interactive 3D WebGL developer portfolios using React Three Fiber (@react-three/fiber), Drei (@react-three/drei), Three.js, Framer Motion, and TailwindCSS based on Adrian Hajdin's project_3D_developer_portfolio. Use when building, scaffolding, optimizing, or debugging 3D canvases, GLTF/GLB models, orbit controls, stars/particles backgrounds, 3D floating tech spheres/icosahedrons, and responsive Canvas camera viewports.
version: 1.0.0
---

# 🌐 ThreeJS 3D Developer Portfolio Engineering

`threejs-3d-portfolio` provides production architecture, component templates, and optimization rules distilled from Adrian Hajdin's `@react-three/fiber` & Three.js 3D Developer Portfolio.

---

## 🏗️ 1. Core Architecture & Tech Stack

- **Renderer**: `@react-three/fiber` (R3F declarative WebGL layer on Three.js).
- **Abstractions & Helpers**: `@react-three/drei` (`useGLTF`, `OrbitControls`, `Preload`, `Float`, `Decal`, `Points`, `PointMaterial`).
- **Motion & View Transitions**: `framer-motion` (choreographed section fades, stagger containers, slide-ins).
- **Styling**: `tailwindcss` with dark mode glassmorphism (`backdrop-blur-md`, subtle borders, neon accents).
- **Mathematics & Vectors**: `maath` (spherical distribution random points).

---

## ⚡ 2. Production Canvas Patterns

### 2.1 Responsive 3D Canvas Shell with CanvasLoader Fallback
Always isolate `<Canvas>` inside a responsive parent container with bounded height, explicit `dpr`, shadows, and fallback loader:

```jsx
import React, { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Preload } from "@react-three/drei";
import CanvasLoader from "./Loader";

export function ModelCanvas({ children, cameraPosition = [20, 3, 5], fov = 25 }) {
  return (
    <Canvas
      frameloop="demand"
      shadows
      dpr={[1, 2]}
      camera={{ position: cameraPosition, fov }}
      gl={{ preserveDrawingBuffer: true }}
    >
      <Suspense fallback={<CanvasLoader />}>
        <OrbitControls
          enableZoom={false}
          maxPolarAngle={Math.PI / 2}
          minPolarAngle={Math.PI / 2}
        />
        {children}
      </Suspense>
      <Preload all />
    </Canvas>
  );
}
```

### 2.2 Low-Overhead HTML Loader in 3D Space
Uses Drei's `<Html>` wrapper to render progress percentage directly inside the WebGL viewport without canvas tearing:

```jsx
import { Html, useProgress } from "@react-three/drei";

export default function CanvasLoader() {
  const { progress } = useProgress();
  return (
    <Html as="div" center style={{ display: "flex", justifyContent: "center", alignItems: "center", flexDirection: "column" }}>
      <span className="canvas-loader" />
      <p style={{ fontSize: 14, color: "#F1F1F1", fontWeight: 800, marginTop: 40 }}>
        {progress.toFixed(2)}%
      </p>
    </Html>
  );
}
```

---

## 🪐 3. Key 3D Components

### 3.1 Interactive 3D Tech Ball (Decal Projection)
Renders floating, rotatable polyhedrons with technology logos projected as decals:

```jsx
import React from "react";
import { Decal, Float, OrbitControls, useTexture } from "@react-three/drei";

export function Ball({ imgUrl }) {
  const [decal] = useTexture([imgUrl]);

  return (
    <Float speed={1.75} rotationIntensity={1} floatIntensity={2}>
      <ambientLight intensity={0.25} />
      <directionalLight position={[0, 0, 0.05]} />
      <mesh castShadow receiveShadow scale={2.75}>
        <icosahedronGeometry args={[1, 1]} />
        <meshStandardMaterial
          color="#fff8eb"
          polygonOffset
          polygonOffsetFactor={-5}
          flatShading
        />
        <Decal
          position={[0, 0, 1]}
          rotation={[2 * Math.PI, 0, 6.25]}
          scale={1}
          map={decal}
          flatShading
        />
      </mesh>
    </Float>
  );
}
```

### 3.2 Immersive Starfield Canvas
Uses random spherical point distribution and rotational delta ticks:

```jsx
import { useState, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Points, PointMaterial } from "@react-three/drei";
import * as random from "maath/random/dist/maath-random.esm";

export function Stars(props) {
  const ref = useRef();
  const [sphere] = useState(() => random.inSphere(new Float32Array(5000), { radius: 1.2 }));

  useFrame((state, delta) => {
    if (ref.current) {
      ref.current.rotation.x -= delta / 10;
      ref.current.rotation.y -= delta / 15;
    }
  });

  return (
    <group rotation={[0, 0, Math.PI / 4]}>
      <Points ref={ref} positions={sphere} stride={3} frustumCulled {...props}>
        <PointMaterial
          transparent
          color="#f272c8"
          size={0.002}
          sizeAttenuation={true}
          depthWrite={false}
        />
      </Points>
    </group>
  );
}
```

---

## 📱 4. Mobile & GPU Optimization Rules

1. **`frameloop="demand"`**: Never run `frameloop="always"` unless animating real-time physics or camera sweeps. Use `demand` to pause WebGL render cycles when idle, saving 90% GPU/battery.
2. **Dynamic DPR**: Clamp device pixel ratio to `dpr={[1, 2]}` to prevent 3x/4x mobile screens from dropping below 30 FPS.
3. **Media Query Listeners**: Adjust camera position, mesh scale, and rotation dynamically based on viewport width (`isMobile ? 0.7 : 0.75`).
4. **GLTF Preload**: Always register `useGLTF.preload('/path/to/model.gltf')` outside the component lifecycle to prevent hitching on mount.

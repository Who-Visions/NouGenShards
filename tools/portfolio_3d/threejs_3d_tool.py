#!/usr/bin/env python3
"""
threejs_3d_tool.py — Scaffolding and verification CLI tool for Three.js & R3F 3D Portfolios.
Distilled from adrianhajdin/project_3D_developer_portfolio canon.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

CANON_DIR = Path("/Users/kushboygroup/The Observatory/NouGen/nougenshards/canon/3d-developer-portfolio/adrianhajdin__project_3D_developer_portfolio")

COMPONENT_TEMPLATES = {
    "ComputersCanvas": """import React, { Suspense, useEffect, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Preload, useGLTF } from "@react-three/drei";
import CanvasLoader from "./Loader";

export const Computers = ({ isMobile, modelPath = "./desktop_pc/scene.gltf" }) => {
  const computer = useGLTF(modelPath);

  return (
    <mesh>
      <hemisphereLight intensity={0.15} groundColor="black" />
      <spotLight
        position={[-20, 50, 10]}
        angle={0.12}
        penumbra={1}
        intensity={1}
        castShadow
        shadow-mapSize={1024}
      />
      <pointLight intensity={1} />
      <primitive
        object={computer.scene}
        scale={isMobile ? 0.7 : 0.75}
        position={isMobile ? [0, -3, -2.2] : [0, -3.25, -1.5]}
        rotation={[-0.01, -0.2, -0.1]}
      />
    </mesh>
  );
};

export const ComputersCanvas = ({ modelPath }) => {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(max-width: 500px)");
    setIsMobile(mediaQuery.matches);
    const handler = (e) => setIsMobile(e.matches);
    mediaQuery.addEventListener("change", handler);
    return () => mediaQuery.removeEventListener("change", handler);
  }, []);

  return (
    <Canvas
      frameloop="demand"
      shadows
      dpr={[1, 2]}
      camera={{ position: [20, 3, 5], fov: 25 }}
      gl={{ preserveDrawingBuffer: true }}
    >
      <Suspense fallback={<CanvasLoader />}>
        <OrbitControls
          enableZoom={false}
          maxPolarAngle={Math.PI / 2}
          minPolarAngle={Math.PI / 2}
        />
        <Computers isMobile={isMobile} modelPath={modelPath} />
      </Suspense>
      <Preload all />
    </Canvas>
  );
};

export default ComputersCanvas;
""",
    "BallCanvas": """import React, { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { Decal, Float, OrbitControls, Preload, useTexture } from "@react-three/drei";
import CanvasLoader from "./Loader";

export const Ball = ({ imgUrl }) => {
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
};

export const BallCanvas = ({ icon }) => {
  return (
    <Canvas
      frameloop="demand"
      dpr={[1, 2]}
      gl={{ preserveDrawingBuffer: true }}
    >
      <Suspense fallback={<CanvasLoader />}>
        <OrbitControls enableZoom={false} />
        <Ball imgUrl={icon} />
      </Suspense>
      <Preload all />
    </Canvas>
  );
};

export default BallCanvas;
""",
    "StarsCanvas": """import { useState, useRef, Suspense } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Points, PointMaterial, Preload } from "@react-three/drei";
import * as random from "maath/random/dist/maath-random.esm";

export const Stars = (props) => {
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
};

export const StarsCanvas = () => {
  return (
    <div className="w-full h-auto absolute inset-0 z-[-1]">
      <Canvas camera={{ position: [0, 0, 1] }}>
        <Suspense fallback={null}>
          <Stars />
        </Suspense>
        <Preload all />
      </Canvas>
    </div>
  );
};

export default StarsCanvas;
""",
    "EarthCanvas": """import React, { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Preload, useGLTF } from "@react-three/drei";
import CanvasLoader from "./Loader";

export const Earth = ({ modelPath = "./planet/scene.gltf" }) => {
  const earth = useGLTF(modelPath);

  return (
    <primitive object={earth.scene} scale={2.5} position-y={0} rotation-y={0} />
  );
};

export const EarthCanvas = ({ modelPath }) => {
  return (
    <Canvas
      shadows
      frameloop="demand"
      dpr={[1, 2]}
      gl={{ preserveDrawingBuffer: true }}
      camera={{
        fov: 45,
        near: 0.1,
        far: 200,
        position: [-4, 3, 6],
      }}
    >
      <Suspense fallback={<CanvasLoader />}>
        <OrbitControls
          autoRotate
          enableZoom={false}
          maxPolarAngle={Math.PI / 2}
          minPolarAngle={Math.PI / 2}
        />
        <Earth modelPath={modelPath} />
        <Preload all />
      </Suspense>
    </Canvas>
  );
};

export default EarthCanvas;
"""
}

def inspect_canon():
    """Print summary of sharded 3D developer portfolio files."""
    if not CANON_DIR.exists():
        print(f"Error: Canon directory not found at {CANON_DIR}", file=sys.stderr)
        return 1

    files = list(CANON_DIR.rglob("*"))
    source_files = [f for f in files if f.is_file() and f.suffix in (".js", ".jsx", ".md", ".json")]
    
    print("=" * 60)
    print("🌌 3D Developer Portfolio Canon Summary")
    print(f"Repo: adrianhajdin/project_3D_developer_portfolio")
    print(f"Location: {CANON_DIR}")
    print(f"Total Source Blobs: {len(source_files)}")
    print("=" * 60)
    for sf in sorted(source_files):
        rel = sf.relative_to(CANON_DIR)
        print(f"  • {rel} ({sf.stat().st_size:,} bytes)")
    print("=" * 60)
    return 0

def scaffold(component: str, out_path: str):
    """Scaffold a canonical 3D component into the target path."""
    if component not in COMPONENT_TEMPLATES:
        print(f"Unknown component: {component}. Available: {list(COMPONENT_TEMPLATES.keys())}", file=sys.stderr)
        return 1
    
    dest = Path(out_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(COMPONENT_TEMPLATES[component], encoding="utf-8")
    print(f"✨ Scaffolded {component} -> {dest}")
    return 0

def main():
    parser = argparse.ArgumentParser(description="Three.js 3D Developer Portfolio CLI Tool")
    subparsers = parser.add_subparsers(dest="subcommand")

    # inspect
    subparsers.add_parser("inspect", help="Inspect sharded canon components and files")

    # scaffold
    scaffold_p = subparsers.add_parser("scaffold", help="Scaffold a canonical 3D canvas component")
    scaffold_p.add_argument("component", choices=list(COMPONENT_TEMPLATES.keys()))
    scaffold_p.add_argument("--out", "-o", required=True, help="Destination file path")

    args = parser.parse_args()

    if args.subcommand == "inspect":
        return inspect_canon()
    elif args.subcommand == "scaffold":
        return scaffold(args.component, args.out)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())

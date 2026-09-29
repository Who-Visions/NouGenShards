#!/bin/bash
# Usage: ./scaffold.sh <project-name>
PROJECT=${1:-scroll-video-site}
npm create vite@latest $PROJECT -- --template vanilla
cd $PROJECT
npm install gsap lenis
mkdir -p public/video src/styles
echo "Project scaffolded. Add your video to public/video/ and start with npm run dev"

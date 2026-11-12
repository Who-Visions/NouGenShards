#!/usr/bin/env bash
# Build nougen-supervisor.exe. Go is needed; if this machine has none, set BUILD_HOST to an
# ssh target that has Go on Windows (and BUILD_DIR to a scratch folder there) to build remotely.
# Usage: ./build.sh <version>      e.g. ./build.sh 1.2.0-20261111
set -euo pipefail
V="${1:?version required}"
cd "$(dirname "$0")"
LD="-H=windowsgui -s -w -X main.version=$V"
if [ -z "${BUILD_HOST:-}" ]; then
  gofmt -l . && go vet . && go test -count=1 . && GOOS=windows go build -trimpath -ldflags "$LD" -o nougen-supervisor.exe .
else
  R="${BUILD_DIR:?set BUILD_DIR (remote scratch folder, forward slashes)}"
  scp -q -o BatchMode=yes main.go main_test.go go.mod "$BUILD_HOST:$R/"
  ssh -o BatchMode=yes "$BUILD_HOST" "cd /d ${R//\//\\} && go vet . && go test -count=1 . && go build -trimpath -ldflags \"$LD\" -o nougen-supervisor.exe ."
  scp -q -o BatchMode=yes "$BUILD_HOST:$R/nougen-supervisor.exe" .
fi
ls -la nougen-supervisor.exe

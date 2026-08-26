#!/usr/bin/env bash
# Сборка .aar у оператора. В среде агента нет Android SDK / gomobile.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
unset GOOS GOARCH || true
go install golang.org/x/mobile/cmd/gomobile@latest
gomobile init
mkdir -p ../app/android/app/libs
gomobile bind -target=android -androidapi 24 -o ../app/android/app/libs/mobilelib.aar ./cmd/mobilelib
echo "wrote app/android/app/libs/mobilelib.aar"

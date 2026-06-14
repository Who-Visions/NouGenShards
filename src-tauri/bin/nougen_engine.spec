# -*- mode: python ; coding: utf-8 -*-
# Builds the NouGenShards engine sidecar bundled with the Tauri app.
# Output name matches Tauri's externalBin convention: nougen_engine-<triple>.
# Build via build-sidecar.ps1 (which sets distpath so the .exe lands in bin/).
import os

from PyInstaller.utils.hooks import collect_submodules

# SPECPATH is injected by PyInstaller; resolve the repo `src` from it.
SRC = os.path.abspath(os.path.join(SPECPATH, "..", "..", "src"))

# Pull in the whole engine package plus its optional submodules so the frozen
# binary can serve search / status / stats without the dev tree present.
hidden = collect_submodules("nougen_shards")

a = Analysis(
    ["sidecar_bootstrap.py"],
    pathex=[SRC],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="nougen_engine-x86_64-pc-windows-msvc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

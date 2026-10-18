# -*- mode: python ; coding: utf-8 -*-
# Builds the NouGenShards engine sidecar bundled with the Tauri app.
# Output name matches Tauri's externalBin convention: nougen_engine-<triple>.
# Build via build-sidecar.ps1 (which sets distpath so the .exe lands in bin/).
import os

# SPECPATH is injected by PyInstaller; resolve the repo `src` from it.
SRC = os.path.abspath(os.path.join(SPECPATH, "..", "..", "src"))

# Python's analysis follows the bootstrap's static imports. These chat modules
# are imported by command dispatch or tool execution and must be frozen too.
# Avoid collecting every unrelated engine submodule into the desktop sidecar.
hidden = [
    "nougen_shards.chat_service",
    "nougen_shards.chat_widget_ir",
    "nougen_shards.credential_patterns",
    "nougen_shards.brain_scan.redaction",
    "nougen_shards.dynamic_api",
    "nougen_shards.dashboard_live",
    "nougen_shards.cli",
]

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

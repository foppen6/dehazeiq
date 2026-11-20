# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-recept för DeHazeIQ. Körs från projektroten:
#   pyinstaller --noconfirm packaging/dehazeiq.spec
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PKG = os.path.join(ROOT, "packaging")
IS_MAC = sys.platform == "darwin"

with open(os.path.join(ROOT, "dehazeiq", "__init__.py"), encoding="utf-8") as fh:
    VERSION = re.search(r'__version__ = "([^"]+)"', fh.read()).group(1)

# Gränssnittet (HTML/CSS/JS/logga)
datas = [(os.path.join(ROOT, "dehazeiq", "web"), os.path.join("dehazeiq", "web"))]

# Inbakad FFmpeg (hämtas av byggsystemet till packaging/ffmpeg)
binaries = []
ff_root = os.path.join(PKG, "ffmpeg")
for dirpath, _, files in os.walk(ff_root):
    for f in files:
        if f.startswith("."):
            continue
        rel = os.path.relpath(dirpath, PKG)
        binaries.append((os.path.join(dirpath, f), rel))
if not binaries:
    raise SystemExit("packaging/ffmpeg saknas – hämta FFmpeg först")

# Inbyggd AI-modell (CLIP ONNX + textinbäddningar), hämtas av byggsystemet till packaging/models
models = os.path.join(PKG, "models")
if not os.path.exists(os.path.join(models, "clip_vision.onnx")):
    raise SystemExit("packaging/models saknas – hämta AI-modellen först")
datas.append((models, "models"))

a = Analysis(
    [os.path.join(PKG, "run_dehazeiq.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=["dehazeiq.app", "dehazeiq.launcher"],
    excludes=["torch", "open_clip", "tkinter", "matplotlib", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DeHazeIQ",
    console=False,
    icon=os.path.join(PKG, "icon.icns" if IS_MAC else "icon.ico"),
    codesign_identity=None,
)

coll = COLLECT(exe, a.binaries, a.datas, name="DeHazeIQ")

if IS_MAC:
    app = BUNDLE(
        coll,
        name="DeHazeIQ.app",
        icon=os.path.join(PKG, "icon.icns"),
        bundle_identifier="se.dehazeiq.app",
        version=VERSION,
        info_plist={
            "CFBundleName": "DeHazeIQ",
            "CFBundleDisplayName": "DeHazeIQ",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "NSAppleEventsUsageDescription": "DeHazeIQ öppnar Finder för att välja mappar och visa exporterade filer.",
        },
    )

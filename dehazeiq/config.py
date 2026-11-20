"""Gemensamma inställningar: stilar, format och sökvägar."""

import os
from pathlib import Path

HOME = Path(os.environ.get("DEHAZEIQ_HOME", Path.home() / "DeHazeIQ")).expanduser()
PROJECTS_DIR = HOME / "projects"

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mts", ".m2ts", ".avi", ".mkv", ".insv"}
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".wav", ".aif", ".aiff", ".flac", ".ogg"}

# Bildformat: namn -> (bredd, höjd) i 1080p-läge
FORMATS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}

# Upplösning: skalfaktor mot 1080p-basen
RESOLUTIONS = {
    "preview": 0.5,
    "720p": 2 / 3,
    "1080p": 1.0,
    "4k": 2.0,
}

OUTPUT_FPS = 30

# Stilar. Varje stil är en uppsättning vikter som styr generatorn och renderingen.
#   avg_shot / min_shot / max_shot – klipplängder i sekunder
#   beat_sync   – 0..1, hur ofta klipp läggs på musikens taktslag
#   motion_pref – -1..1, negativ = föredrar lugna tagningar, positiv = rörelse
#   variety     – hur hårt upprepning av liknande motiv straffas
#   temperature – slump i urvalet (högre = mer variation mellan genereringar)
#   color       – färgprofil (se COLOR_PROFILES)
#   orig_audio  – volym för originalljud under musiken (0 = av)
#   fade        – toning in/ut i början och slutet (sekunder)
STYLES = {
    "cinematic": {
        "label": "Cinematisk",
        "avg_shot": 3.4, "min_shot": 2.2, "max_shot": 6.0,
        "beat_sync": 0.5, "motion_pref": -0.25, "variety": 0.6,
        "temperature": 0.22, "color": "cinematic", "orig_audio": 0.06,
        "fade": 0.8,
    },
    "action": {
        "label": "Action",
        "avg_shot": 1.6, "min_shot": 0.8, "max_shot": 3.0,
        "beat_sync": 0.9, "motion_pref": 0.6, "variety": 0.5,
        "temperature": 0.28, "color": "punchy", "orig_audio": 0.0,
        "fade": 0.3,
    },
    "calm": {
        "label": "Lugn natur",
        "avg_shot": 4.4, "min_shot": 3.0, "max_shot": 8.0,
        "beat_sync": 0.2, "motion_pref": -0.6, "variety": 0.7,
        "temperature": 0.22, "color": "natural", "orig_audio": 0.12,
        "fade": 1.2,
    },
    "playful": {
        "label": "Lekfull",
        "avg_shot": 2.2, "min_shot": 1.0, "max_shot": 3.6,
        "beat_sync": 0.85, "motion_pref": 0.2, "variety": 0.5,
        "temperature": 0.3, "color": "playful", "orig_audio": 0.1,
        "fade": 0.3,
    },
}

COLOR_PROFILES = {
    "cinematic": "eq=contrast=1.06:saturation=1.08:gamma=0.98",
    "punchy": "eq=contrast=1.12:saturation=1.18",
    "natural": "eq=contrast=1.03:saturation=1.05",
    "playful": "eq=contrast=1.08:saturation=1.25:brightness=0.01,colorbalance=rm=0.03:bm=-0.02",
}

PROXY_SHORT_SIDE = 540

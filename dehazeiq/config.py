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
    "documentary": {
        "label": "Dokumentär",
        "avg_shot": 5.5, "min_shot": 3.5, "max_shot": 8.5,
        "beat_sync": 0.2, "motion_pref": -0.3, "variety": 0.6,
        "temperature": 0.2, "color": "natural", "orig_audio": 0.85,
        "fade": 1.0, "speech_pref": 0.15,
    },
    "widescreen": {
        "label": "Filmisk bredbild",
        "avg_shot": 4.2, "min_shot": 2.6, "max_shot": 7.0,
        "beat_sync": 0.5, "motion_pref": 0.0, "variety": 0.55,
        "temperature": 0.22, "color": "muted", "orig_audio": 0.25,
        "fade": 1.4, "look_fx": {"letterbox": 1},
    },
    "vintage": {
        "label": "Vintage Super 8",
        "avg_shot": 2.8, "min_shot": 1.6, "max_shot": 4.5,
        "beat_sync": 0.6, "motion_pref": 0.1, "variety": 0.5,
        "temperature": 0.3, "color": "vintage", "orig_audio": 0.15,
        "fade": 0.8, "look_fx": {"grain": 0.8, "weave": 1, "glow": 1},
    },
    "musicvideo": {
        "label": "Musikvideo",
        "avg_shot": 1.1, "min_shot": 0.5, "max_shot": 2.2,
        "beat_sync": 1.0, "motion_pref": 0.7, "variety": 0.45,
        "temperature": 0.3, "color": "punchy", "orig_audio": 0.0,
        "fade": 0.2, "look_fx": {}, "beat_flash": 4,
    },
    "ambient": {
        "label": "Ambient",
        "avg_shot": 9.0, "min_shot": 6.0, "max_shot": 14.0,
        "beat_sync": 0.0, "motion_pref": -0.5, "variety": 0.6,
        "temperature": 0.15, "color": "natural", "orig_audio": 1.0,
        "fade": 2.0, "look_fx": {}, "no_music": True, "no_text": True,
    },
    "vlog": {
        "label": "Vlogg",
        "avg_shot": 2.4, "min_shot": 1.4, "max_shot": 4.0,
        "beat_sync": 0.7, "motion_pref": 0.2, "variety": 0.6,
        "temperature": 0.3, "color": "natural", "orig_audio": 0.35,
        "fade": 0.5, "look_fx": {}, "speech_pref": 0.35,
    },
    "minimal": {
        "label": "Minimal",
        "avg_shot": 3.2, "min_shot": 2.0, "max_shot": 5.5,
        "beat_sync": 0.7, "motion_pref": 0.0, "variety": 0.55,
        "temperature": 0.2, "color": "natural", "orig_audio": 0.2,
        "fade": 0.6, "look_fx": {}, "no_effects": True,
    },
    # Reklamfilmer: egna texter (krok, säljpunkter, uppmaning, adress, logga) läggs in i efterhand
    "promo_energy": {
        "label": "Reklam · energi",
        "avg_shot": 1.3, "min_shot": 0.7, "max_shot": 2.4,
        "beat_sync": 1.0, "motion_pref": 0.6, "variety": 0.5,
        "temperature": 0.25, "color": "punchy", "orig_audio": 0.0,
        "fade": 0.2, "look_fx": {}, "promo": "energy", "no_auto_text": True,
    },
    "promo_premium": {
        "label": "Reklam · premium",
        "avg_shot": 3.2, "min_shot": 2.2, "max_shot": 5.0,
        "beat_sync": 0.6, "motion_pref": -0.3, "variety": 0.6,
        "temperature": 0.2, "color": "muted", "orig_audio": 0.0,
        "fade": 0.9, "look_fx": {"letterbox": 1}, "promo": "premium", "no_auto_text": True,
    },
    "promo_info": {
        "label": "Reklam · information",
        "avg_shot": 2.8, "min_shot": 1.8, "max_shot": 4.2,
        "beat_sync": 0.6, "motion_pref": 0.0, "variety": 0.6,
        "temperature": 0.2, "color": "natural", "orig_audio": 0.0,
        "fade": 0.5, "look_fx": {}, "promo": "info", "no_auto_text": True,
    },
    "promo_experience": {
        "label": "Reklam · upplevelse",
        "avg_shot": 2.4, "min_shot": 1.4, "max_shot": 4.0,
        "beat_sync": 0.8, "motion_pref": 0.2, "variety": 0.55,
        "temperature": 0.28, "color": "cinematic", "orig_audio": 0.0,
        "fade": 0.6, "look_fx": {}, "promo": "experience", "no_auto_text": True,
    },
    # Trailer: lugn start, textskyltar, allt kortare klipp mot ett klimax och titeln på slutet
    "trailer": {
        "label": "Trailer",
        "avg_shot": 2.0, "min_shot": 0.6, "max_shot": 4.8,
        "beat_sync": 0.8, "motion_pref": 0.3, "variety": 0.55,
        "temperature": 0.25, "color": "cinematic", "orig_audio": 0.0,
        "fade": 0.6, "look_fx": {"letterbox": 1}, "promo": "trailer", "ramp": True, "no_auto_text": True,
    },
    # Musikvideor: klippen följer musikens takt och energi, starkaste klippen på refrängen/dropen
    "mv_ballad": {
        "label": "Musikvideo · ballad",
        "avg_shot": 3.6, "min_shot": 2.0, "max_shot": 6.5,
        "beat_sync": 1.0, "motion_pref": -0.4, "variety": 0.6,
        "temperature": 0.22, "color": "cinematic", "orig_audio": 0.0,
        "fade": 1.2, "look_fx": {"glow": 1}, "music_video": "ballad", "bar_sync": True, "no_auto_text": True,
    },
    "mv_glitch": {
        "label": "Musikvideo · glitch",
        "avg_shot": 0.9, "min_shot": 0.4, "max_shot": 1.8,
        "beat_sync": 1.0, "motion_pref": 0.8, "variety": 0.4,
        "temperature": 0.35, "color": "punchy", "orig_audio": 0.0,
        "fade": 0.1, "look_fx": {"rgbshift": 1}, "beat_flash": 2, "music_video": "glitch", "no_auto_text": True,
    },
    "mv_lyrics": {
        "label": "Musikvideo · med sångtext",
        "avg_shot": 2.0, "min_shot": 1.0, "max_shot": 3.5,
        "beat_sync": 1.0, "motion_pref": 0.3, "variety": 0.5,
        "temperature": 0.28, "color": "cinematic", "orig_audio": 0.0,
        "fade": 0.6, "look_fx": {}, "music_video": "lyrics", "bar_sync": True, "no_auto_text": True,
    },
    # Sociala medier (Instagram, TikTok, Shorts)
    "hookreel": {
        "label": "Hook-reel",
        "avg_shot": 1.4, "min_shot": 0.7, "max_shot": 2.6,
        "beat_sync": 0.95, "motion_pref": 0.5, "variety": 0.5,
        "temperature": 0.3, "color": "punchy", "orig_audio": 0.05,
        "fade": 0.15, "look_fx": {}, "social": "social", "no_auto_text": True,
    },
    "pov": {
        "label": "POV",
        "avg_shot": 2.6, "min_shot": 1.4, "max_shot": 4.2,
        "beat_sync": 0.7, "motion_pref": 0.1, "variety": 0.6,
        "temperature": 0.28, "color": "natural", "orig_audio": 0.2,
        "fade": 0.3, "look_fx": {}, "social": "pov", "no_auto_text": True, "speech_pref": 0.2,
    },
    "beforeafter": {
        "label": "Före/efter",
        "avg_shot": 2.6, "min_shot": 1.6, "max_shot": 3.6,
        "beat_sync": 0.8, "motion_pref": -0.1, "variety": 0.7,
        "temperature": 0.28, "color": "punchy", "orig_audio": 0.0,
        "fade": 0.2, "look_fx": {}, "social": "beforeafter", "no_auto_text": True,
    },
    "top5": {
        "label": "Topp 5",
        "avg_shot": 3.0, "min_shot": 2.0, "max_shot": 4.5,
        "beat_sync": 0.8, "motion_pref": 0.1, "variety": 0.9,
        "temperature": 0.28, "color": "punchy", "orig_audio": 0.0,
        "fade": 0.2, "look_fx": {}, "social": "top5", "no_auto_text": True,
    },
    "loopreel": {
        "label": "Loop",
        "avg_shot": 2.0, "min_shot": 1.0, "max_shot": 3.2,
        "beat_sync": 0.9, "motion_pref": 0.2, "variety": 0.6,
        "temperature": 0.28, "color": "cinematic", "orig_audio": 0.0,
        "fade": 0.0, "look_fx": {}, "social": "loop", "no_auto_text": True,
    },
    "photodump": {
        "label": "Fotodump",
        "avg_shot": 0.55, "min_shot": 0.35, "max_shot": 0.9,
        "beat_sync": 1.0, "motion_pref": 0.0, "variety": 0.9,
        "temperature": 0.28, "color": "playful", "orig_audio": 0.0,
        "fade": 0.1, "look_fx": {}, "social": "dump", "no_auto_text": True,
    },
    "cinereel": {
        "label": "Cinematic reel",
        "avg_shot": 3.0, "min_shot": 2.0, "max_shot": 5.0,
        "beat_sync": 0.6, "motion_pref": -0.3, "variety": 0.6,
        "temperature": 0.22, "color": "cinematic", "orig_audio": 0.05,
        "fade": 0.8, "look_fx": {"letterbox": 1}, "social": "cine",
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
    "muted": "eq=contrast=1.1:saturation=0.85:gamma=0.97,colorbalance=bs=0.03:rh=0.03",
    "vintage": "colorbalance=rs=0.07:gs=0.02:bs=-0.07:rm=0.05:bm=-0.05:rh=0.03:bh=-0.03,eq=saturation=0.8:contrast=1.06:gamma=1.03",
}

PROXY_SHORT_SIDE = 540


# Var filmen ska visas: format och standardlängd (sekunder)
PLATFORMS = {
    "reels": {"label": "Instagram Reels", "format": "9:16", "length": 30},
    "tiktok": {"label": "TikTok", "format": "9:16", "length": 30},
    "shorts": {"label": "YouTube Shorts", "format": "9:16", "length": 45},
    "youtube": {"label": "YouTube", "format": "16:9", "length": 180},
    "feed": {"label": "Instagram-flöde", "format": "4:5", "length": 30},
    "facebook": {"label": "Facebook", "format": "4:5", "length": 45},
    "square": {"label": "Kvadrat", "format": "1:1", "length": 30},
}

# Vilka sorters filmer AI:n ska göra av materialet (väljs vid import eller senare)
FILM_TYPES = {
    "auto": {"label": "Låt AI välja", "platform": "reels", "count": 3},
    "dive": {"label": "Dykfilm", "platform": "youtube", "count": 3},
    "trip": {"label": "Resefilm", "platform": "youtube", "count": 3},
    "reels": {"label": "Reels och shorts", "platform": "reels", "count": 6},
    "social": {"label": "Sociala medier-trender", "platform": "reels", "count": 4, "length": 15},
    "animal": {"label": "Djurporträtt", "platform": "feed", "count": 3},
    "promo": {"label": "Reklamfilm", "platform": "reels", "count": 4, "length": 30},
    "musicvideo": {"label": "Musikvideo", "platform": "reels", "count": 4},
    "trailer": {"label": "Trailer", "platform": "youtube", "count": 3, "length": 45},
    "prompt": {"label": "Egen beskrivning", "platform": "reels", "count": 3},
}

SOCIAL_STYLES = ["hookreel", "pov", "beforeafter", "top5", "loopreel", "photodump", "cinereel"]
LENGTH_PRESETS = [7, 15, 30, 60, 90]
PROMO_STYLES = ["promo_energy", "promo_premium", "promo_info", "promo_experience"]
MV_STYLES = ["musicvideo", "mv_ballad", "mv_glitch", "mv_lyrics"]

# Färgutseenden för redigeringen. Värden: exponering, kontrast, mättnad, temperatur, nyans (−1..1),
# samt svartvitt och sepia (0..1). Styrkan skalar dem.
LOOKS = {
    # Färgutseenden. Värdena nedan läggs på reglagen; render.LOOK_RECIPES ger själva karaktären
    # (färgbalans, kanalblandning, kurvor) så att varje utseende syns tydligt.
    "none": {"label": "Stilens färg"},
    "original": {"label": "Original"},
    "natural": {"label": "Naturlig", "contrast": 0.06},
    "underwater": {"label": "Undervatten", "contrast": 0.08},
    "warm": {"label": "Varm"},
    "cold": {"label": "Kall"},
    "vivid": {"label": "Livlig", "contrast": 0.12},
    "film": {"label": "Film", "contrast": 0.1},
    "bw": {"label": "Svartvitt", "bw": 1.0, "contrast": 0.2},
    "bw_soft": {"label": "Svartvitt mjuk", "bw": 1.0, "contrast": -0.12, "exposure": 0.06},
    "sepia": {"label": "Sepia", "bw": 1.0, "sepia": 0.9},
}
GRADE_KEYS = ("exposure", "contrast", "saturation", "temperature", "tint", "sharpen", "vignette")

"""Export av tidslinje till OpenTimelineIO (.otio) för DaVinci Resolve m.fl.

Skrivs som ren JSON enligt OTIO-schemat så att inget extra paket behövs.
Resolve: Arkiv › Importera › Tidslinje… och välj .otio-filen.
"""

import json
from pathlib import Path

from .config import OUTPUT_FPS


def _rt(value, rate):
    return {"OTIO_SCHEMA": "RationalTime.1", "rate": float(rate), "value": float(round(value))}


def _tr(start, dur, rate):
    return {"OTIO_SCHEMA": "TimeRange.1",
            "start_time": _rt(start * rate, rate), "duration": _rt(dur * rate, rate)}


def _url(path):
    # as_uri() ger korrekta URL:er på både macOS (file:///Users/…) och Windows (file:///C:/…)
    return Path(path).resolve().as_uri()


def _clip(name, path, start, dur, rate, avail=None, metadata=None):
    ref = {"OTIO_SCHEMA": "ExternalReference.1", "name": "", "metadata": {},
           "available_range": _tr(0, avail, rate) if avail else None,
           "available_image_bounds": None, "target_url": _url(path)}
    return {"OTIO_SCHEMA": "Clip.2", "name": name, "metadata": metadata or {},
            "source_range": _tr(start, dur, rate), "effects": [], "markers": [],
            "enabled": True, "color": None,
            "media_references": {"DEFAULT_MEDIA": ref},
            "active_media_reference_key": "DEFAULT_MEDIA"}


def _track(name, kind, children):
    return {"OTIO_SCHEMA": "Track.1", "name": name, "metadata": {}, "source_range": None,
            "effects": [], "markers": [], "enabled": True, "color": None,
            "children": children, "kind": kind}


def to_otio(project, proposal) -> dict:
    clips = project.data["clips"]
    video = []
    for s in proposal["shots"]:
        c = clips[s["clip_id"]]
        rate = round(c.get("fps") or OUTPUT_FPS, 3)
        video.append(_clip(c["name"], c["path"], s["src_start"], s["duration"], rate,
                           avail=c.get("duration"),
                           metadata={"dehazeiq": {"crop_cx": s.get("cx"), "tags": s.get("tags")}}))
    tracks = [_track("V1", "Video", video)]
    if proposal.get("music"):
        total = sum(s["duration"] for s in proposal["shots"])
        name = Path(proposal["music"]).name
        tracks.append(_track("A1", "Audio", [_clip(name, proposal["music"], 0.0, total, OUTPUT_FPS)]))
    return {
        "OTIO_SCHEMA": "Timeline.1",
        "name": f"{project.data['name']} – {proposal['style_label']}",
        "metadata": {"dehazeiq": {"format": proposal["format"], "seed": proposal["seed"]}},
        "global_start_time": None,
        "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "metadata": {},
                   "source_range": None, "effects": [], "markers": [], "enabled": True,
                   "color": None, "children": tracks},
    }


def write_otio(project, proposal, path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(to_otio(project, proposal), ensure_ascii=False, indent=2), "utf-8")
    return path

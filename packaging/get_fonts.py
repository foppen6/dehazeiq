"""Hämtar de fria typsnitten (SIL Open Font License / Apache) som texteffekterna använder
från Google Fonts arkiv på GitHub till packaging/fonts. Körs av byggsystemet."""

import sys
import urllib.request
from pathlib import Path

FONTS = {
    "Anton-Regular.ttf": "anton",
    "BebasNeue-Regular.ttf": "bebasneue",
    "ArchivoBlack-Regular.ttf": "archivoblack",
    "PermanentMarker-Regular.ttf": "permanentmarker",
    "Pacifico-Regular.ttf": "pacifico",
    "Bangers-Regular.ttf": "bangers",
    "DMSerifDisplay-Regular.ttf": "dmserifdisplay",
}
BASE = "https://raw.githubusercontent.com/google/fonts/main"
out = Path(__file__).resolve().parent / "fonts"
out.mkdir(exist_ok=True)
missing = 0
for name, fam in FONTS.items():
    dst = out / name
    if dst.exists():
        continue
    for lic in ("ofl", "apache", "ufl"):
        try:
            with urllib.request.urlopen(f"{BASE}/{lic}/{fam}/{name}", timeout=60) as r:
                data = r.read()
            if data[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
                dst.write_bytes(data)
                print("Hämtade", name, f"({lic}, {len(data) // 1024} kB)")
                for lf in ("OFL.txt", "LICENSE.txt"):
                    try:
                        with urllib.request.urlopen(f"{BASE}/{lic}/{fam}/{lf}", timeout=60) as r:
                            (out / f"{Path(name).stem}-{lf}").write_bytes(r.read())
                        break
                    except Exception:  # noqa: BLE001
                        pass
                break
        except Exception:  # noqa: BLE001
            continue
    else:
        missing += 1
        print("Saknas:", name)
print("Typsnitt:", len(FONTS) - missing, "av", len(FONTS))
sys.exit(1 if missing > 2 else 0)

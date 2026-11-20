"""Startpunkt för den installerade appen (Mac .app och Windows .exe).

Startar servern i bakgrunden och öppnar DeHazeIQ i ett eget programfönster
(pywebview). Går fönstret inte att öppna används webbläsaren i stället.
"""

import argparse
import os
import sys
import threading
import time
import traceback
import webbrowser


def _redirect_output():
    """En fönsterapp har ingen terminal – skriv utskrifter till en loggfil."""
    from .config import HOME
    HOME.mkdir(parents=True, exist_ok=True)
    log = open(HOME / "dehazeiq.log", "a", encoding="utf-8", buffering=1)
    log.write(f"\n===== Start {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    sys.stdout = log
    sys.stderr = log


def selftest() -> int:
    """Kontrollerar att allt som behövs finns i den byggda appen. Körs av byggsystemet."""
    if sys.stdout is None or sys.stderr is None:  # fönsterapp på Windows saknar terminal
        log = open("dehazeiq-selftest.log", "w", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    ok = True
    try:
        from . import media
        print("ffmpeg:", media.ffmpeg())
        print("ffprobe:", media.ffprobe())
        media.run([media.ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                   "-i", "testsrc2=s=320x240:d=0.5", "-c:v", "libx264", "-f", "null", "-"])
        media.run([media.ffprobe(), "-version"])
        print("Videokodning:", media.encoder_label())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        ok = False
    try:
        import cv2
        import numpy
        print("OpenCV", cv2.__version__, "NumPy", numpy.__version__)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        ok = False
    try:
        from . import app  # noqa: F401
        from .app import WEB
        assert (WEB / "index.html").exists() and (WEB / "logo.png").exists(), "webbfiler saknas"
        print("Webbfiler:", WEB)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        ok = False
    try:
        import numpy as np

        from . import ai
        m = ai.get()
        assert m is not None, "AI-modellen saknas eller går inte att ladda"
        img = (np.random.rand(240, 427, 3) * 255).astype("uint8")
        e = m.embed([img])
        print("AI-modell:", m.folder, "inbäddning", e.shape, "intresse", round(float(m.interest(e)[0]), 3))
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        ok = False
    try:
        import webview  # noqa: F401
        print("pywebview: finns")
    except Exception as e:  # noqa: BLE001
        print("pywebview saknas (webbläsaren används):", e)
    print("SJÄLVTEST", "OK" if ok else "MISSLYCKADES")
    return 0 if ok else 1


def _show_error(message: str):
    """Visa ett felmeddelande även utan terminal."""
    print(message)
    try:
        import webview
        webview.create_window("DeHazeIQ", html=f"<body style='background:#0B0F14;color:#E8EEF4;"
                              f"font-family:system-ui;padding:32px'><h2>DeHazeIQ kunde inte starta</h2>"
                              f"<p>{message}</p></body>", width=560, height=280)
        webview.start()
    except Exception:  # noqa: BLE001
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="DeHazeIQ")
    ap.add_argument("--port", type=int, default=int(os.environ.get("DEHAZEIQ_PORT", 8765)))
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--browser", action="store_true", help="använd webbläsaren i stället för eget fönster")
    ap.add_argument("--selftest", action="store_true")
    # macOS kan skicka med -psn_… när appen startas från Finder
    args, _ = ap.parse_known_args(argv)

    if args.selftest:
        return selftest()
    if getattr(sys, "frozen", False):
        _redirect_output()

    from . import app, media
    try:
        server, url = app.start_server(args.port, args.lan)
    except media.MediaError as e:
        _show_error(str(e))
        return 1
    if server is not None:
        threading.Thread(target=server.serve_forever, daemon=True).start()

    if not args.browser:
        try:
            import webview
            webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
            webview.create_window("DeHazeIQ", url, width=1440, height=900, min_size=(1000, 680),
                                  background_color="#0B0F14", text_select=True)
            webview.start()
            return 0  # fönstret stängt = avsluta appen
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            print("Eget fönster gick inte att öppna – använder webbläsaren.")

    webbrowser.open(url)
    if server is None:
        return 0
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())

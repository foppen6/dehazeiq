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
        import subprocess as _sp
        print("Underprocesser utan fönster:", bool(getattr(_sp.Popen, "_dehazeiq_patched", False)) or "ej Windows")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        ok = False
    if sys.platform.startswith("win"):
        try:
            n, control = _windows_console_check()
            print("Konsolfönster vid FFmpeg-anrop:", n, "| detektorn ser ett avsiktligt fönster:", control)
            if n:
                ok = False
        except Exception:  # noqa: BLE001
            traceback.print_exc()
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
        b = ai.get_bio()
        assert b is not None, "artmodellen (BioCLIP) saknas"
        print("Artmodell:", len(b.species), "arter, topp:", b.top(b.embed([img]), 1)[0][0][0])
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        ok = False
    try:
        from . import vlm
        srv = vlm.server_binary()
        print("Djupanalys: llama-server", srv or "saknas", "| minne", round(vlm.ram_gb()), "GB",
              "| modellval", (vlm.choose_model() or {}).get("name"))
        if srv and sys.platform == "darwin":
            import subprocess as _s
            r = _s.run([str(srv), "--version"], capture_output=True, text=True, timeout=60)
            print("llama-server --version:", (r.stdout + r.stderr).strip().splitlines()[-1:])
            assert r.returncode == 0, "llama-server startar inte i appen"
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


def _windows_console_check():
    """Startar FFmpeg på samma sätt som appen gör och räknar synliga konsolfönster som dyker upp."""
    import ctypes
    import subprocess
    from ctypes import wintypes

    from . import media
    user32 = ctypes.windll.user32
    classes = ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS")
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def snapshot():
        res = set()

        def cb(hwnd, _lp):
            if user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, buf, 256)
                if buf.value in classes:
                    res.add(hwnd)
            return True

        user32.EnumWindows(proto(cb), 0)
        return res

    def watch(fn):
        before = snapshot()
        seen = set()
        stop = threading.Event()

        def loop():
            while not stop.is_set():
                seen.update(snapshot() - before)
                time.sleep(0.03)

        th = threading.Thread(target=loop, daemon=True)
        th.start()
        try:
            fn()
            time.sleep(0.3)
        finally:
            stop.set()
            th.join()
        return len(seen)

    def ours():
        for _ in range(4):
            media.run([media.ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                       "-i", "testsrc2=s=320x240:d=0.4", "-f", "null", "-"])
        subprocess.run([media.ffprobe(), "-version"], capture_output=True)  # utan egna flaggor

    def control():  # ett avsiktligt synligt konsolfönster – visar att detektorn fungerar
        p = subprocess.Popen(["cmd", "/c", "ping -n 2 127.0.0.1 >nul"], creationflags=0x00000010)
        p.wait()

    return watch(ours), watch(control) > 0


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
    from . import media  # noqa: F401  – installerar "inga konsolfönster" på Windows direkt

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

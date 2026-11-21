"""Lokal webbserver för DeHazeIQ. Startas med: python -m dehazeiq

Servern lyssnar bara på 127.0.0.1. Gränssnittet öppnas i webbläsaren.
"""

import json
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import cv2

from . import TAGLINE, __version__, ai, effects, media, pipeline, tagging, vlm
from .config import FORMATS, HOME, PROJECTS_DIR, STYLES
from .project import JOBS, Project, auto_name, save_default_settings

WEB = Path(__file__).parent / "web"
MEDIA_DIRS = {"proxies", "renders"}


class ApiError(Exception):
    def __init__(self, message, status=HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


def _project(pid) -> Project:
    if not re.fullmatch(r"[a-z0-9-]+", pid or ""):
        raise ApiError("Ogiltigt projekt", HTTPStatus.NOT_FOUND)
    try:
        return Project(pid)
    except FileNotFoundError:
        raise ApiError("Projektet finns inte", HTTPStatus.NOT_FOUND)


def _project_view(p: Project) -> dict:
    d = dict(p.data)
    d["clips"] = p.clips()
    d.pop("order", None)
    d["job"] = JOBS.status(p.id)
    return d


# ---------- filväljare (macOS, Windows, Linux) ----------

def _osascript(script: str):
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if proc.returncode != 0:
        return []  # användaren avbröt
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


_PS_HEAD = ("$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$owner=New-Object System.Windows.Forms.Form -Property @{TopMost=$true};")
_PS_FILTERS = {
    "files": "Video|*.mp4;*.mov;*.m4v;*.mts;*.m2ts;*.avi;*.mkv;*.insv|Alla filer|*.*",
    "music": "Ljud|*.mp3;*.m4a;*.aac;*.wav;*.aif;*.aiff;*.flac;*.ogg|Alla filer|*.*",
}


def _powershell(kind: str):
    if kind == "folder":
        body = ("$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
                "$d.Description='Välj mapp med filmklipp';$d.ShowNewFolderButton=$false;"
                "if($d.ShowDialog($owner) -eq 'OK'){$d.SelectedPath}")
    else:
        multi = "$true" if kind == "files" else "$false"
        title = "Välj filmklipp" if kind == "files" else "Välj musik"
        body = ("$d=New-Object System.Windows.Forms.OpenFileDialog;"
                f"$d.Multiselect={multi};$d.Title='{title}';$d.Filter='{_PS_FILTERS[kind]}';"
                "if($d.ShowDialog($owner) -eq 'OK'){$d.FileNames -join \"`n\"}")
    proc = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", _PS_HEAD + body],
                          capture_output=True, creationflags=0x08000000)  # inget konsolfönster
    out = proc.stdout.decode("utf-8", "replace")
    return [line.strip() for line in out.splitlines() if line.strip()]


def _zenity(kind: str):
    import shutil as _sh
    if not _sh.which("zenity"):
        raise ApiError("Ingen filväljare hittades. Klistra in sökvägen i stället.")
    cmd = ["zenity", "--file-selection"]
    if kind == "folder":
        cmd.append("--directory")
    elif kind == "files":
        cmd += ["--multiple", "--separator=\n"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def choose(kind: str):
    if kind not in ("folder", "files", "music"):
        raise ApiError("Okänd dialog")
    if sys.platform == "darwin":
        if kind == "folder":
            return _osascript('POSIX path of (choose folder with prompt "Välj mapp med filmklipp")')
        if kind == "files":
            return _osascript(
                'set fs to choose file with prompt "Välj filmklipp" with multiple selections allowed\n'
                'set out to ""\n'
                'repeat with f in fs\n set out to out & POSIX path of f & linefeed\nend repeat\n'
                'return out')
        return _osascript('POSIX path of (choose file with prompt "Välj musik" '
                          'of type {"public.audio"})')
    if sys.platform.startswith("win"):
        return _powershell(kind)
    return _zenity(kind)


def reveal(path: Path):
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    elif sys.platform.startswith("win"):
        subprocess.Popen(["explorer", f"/select,{path}"])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])


# ---------- mobil via wifi (följeslagarläge) ----------

LAN = {"server": None, "port": None}
_KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def lan_key() -> str:
    f = HOME / "lan_key.txt"
    try:
        k = f.read_text("utf-8").strip()
        if re.fullmatch(r"[A-Z0-9]{6}", k):
            return k
    except OSError:
        pass
    k = "".join(secrets.choice(_KEY_ALPHABET) for _ in range(6))
    HOME.mkdir(parents=True, exist_ok=True)
    f.write_text(k, "utf-8")
    return k


def lan_addresses(port):
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # skickar inget, väljer bara rätt nätverkskort
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    ips = sorted(ip for ip in ips if not ip.startswith("127."))
    return [f"http://{ip}:{port}/" for ip in ips]


def lan_status():
    if not LAN["server"]:
        return {"enabled": False}
    return {"enabled": True, "port": LAN["port"], "urls": lan_addresses(LAN["port"]), "key": lan_key()}


def start_lan(port):
    if LAN["server"]:
        return lan_status()
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    except OSError as e:
        raise ApiError(f"Kunde inte öppna port {port} för wifi: {e}")
    srv.lan = True
    LAN.update(server=srv, port=port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    lan_key()
    return lan_status()


def stop_lan():
    srv = LAN["server"]
    if srv:
        LAN.update(server=None, port=None)
        threading.Thread(target=srv.shutdown, daemon=True).start()
    return lan_status()


_LOGIN_PAGE = """<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>DeHazeIQ</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#0B0F14;color:#E8EEF4;font-family:-apple-system,system-ui,sans-serif}
form{display:flex;flex-direction:column;gap:14px;width:min(320px,90vw);text-align:center}
img{width:96px;height:96px;border-radius:22px;align-self:center}
input{height:52px;border-radius:12px;border:1px solid #2A3644;background:#121820;color:#E8EEF4;
font-size:24px;letter-spacing:.3em;text-align:center;text-transform:uppercase}
button{height:50px;border-radius:12px;border:none;background:#2EC4D6;color:#04222A;font-size:16px;font-weight:600}
p{margin:0;color:#8A9AAB}</style></head><body><form method="get" action="/">
<img src="/static/logo.png" alt="DeHazeIQ"><h1 style="margin:0;font-size:22px">DeHazeIQ</h1>
<p>Ange koden som visas på datorn under "Mobil".</p>
<label for="k" style="position:absolute;left:-9999px">Kod</label>
<input id="k" name="key" autocomplete="off" maxlength="6" autofocus>
<button type="submit">Anslut</button>%ERR%</form></body></html>"""


# ---------- bildrutor ----------

_frame_lock = threading.Lock()


def frame_jpeg(p: Project, cid: str, t: float, width: int) -> bytes:
    width = max(80, min(int(width), 640))
    key = f"{cid}_{int(round(t * 10))}_{width}.jpg"
    cache = p.cache / "frames"
    cache.mkdir(exist_ok=True)
    f = cache / key
    if f.exists():
        return f.read_bytes()
    proxy = p.proxy_path(cid)
    if not proxy.exists():
        raise ApiError("Ingen proxy ännu", HTTPStatus.NOT_FOUND)
    with _frame_lock:
        cap = cv2.VideoCapture(str(proxy))
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
        ok, img = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, img = cap.read()
        cap.release()
    if not ok or img is None:
        raise ApiError("Kunde inte läsa bildruta", HTTPStatus.NOT_FOUND)
    h, w = img.shape[:2]
    img = cv2.resize(img, (width, max(2, int(h * width / w))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 82])
    data = buf.tobytes()
    f.write_bytes(data)
    return data


# ---------- HTTP ----------

def _vlm_download():
    try:
        vlm.download()
    except Exception as e:  # noqa: BLE001
        print("Nedladdning av djupanalysmodellen misslyckades:", e)


class Handler(BaseHTTPRequestHandler):
    server_version = f"DeHazeIQ/{__version__}"

    def log_message(self, fmt, *args):  # tystare logg
        if os.environ.get("DEHAZEIQ_DEBUG"):
            super().log_message(fmt, *args)

    # ----- svar -----
    def _send(self, status, body: bytes, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, status=HTTPStatus.OK):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_000_000:
            raise ApiError("För stor förfrågan")
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            raise ApiError("Ogiltig JSON")

    def _file(self, path: Path):
        if not path.is_file():
            return self._json({"error": "Hittades inte"}, HTTPStatus.NOT_FOUND)
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        status = HTTPStatus.OK
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                elif m.group(2):  # suffix: sista N byte
                    start = max(0, size - int(m.group(2)))
                if start > end or start >= size:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if path.suffix in (".mp4", ".otio"):
            self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{_quote(path.name)}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as fh:
            fh.seek(start)
            left = length
            while left > 0:
                chunk = fh.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    # ----- åtkomst -----
    @property
    def is_remote(self) -> bool:
        return bool(getattr(self.server, "lan", False))

    def _cookie_key(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "dhq_key":
                return v
        return None

    def _authorized(self) -> bool:
        """Lokala anrop är alltid tillåtna. Via wifi krävs koden (cookie)."""
        if not self.is_remote:
            return True
        key = lan_key()
        if secrets.compare_digest(self._cookie_key() or "", key):
            return True
        if self.command in ("GET", "HEAD"):
            q = parse_qs(urlparse(self.path).query)
            given = ((q.get("key") or [""])[0]).strip().upper()
            if given and secrets.compare_digest(given, key):
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", f"dhq_key={key}; Path=/; Max-Age=31536000; "
                                               "HttpOnly; SameSite=Strict")
                self.end_headers()
                return False
            path = urlparse(self.path).path
            if path in ("/", "") or not path.startswith(("/api", "/media")):
                if path.startswith("/static/logo.png"):
                    self._file(WEB / "logo.png")
                    return False
                err = '<p style="color:#E8806B">Fel kod, försök igen.</p>' if given else ""
                self._send(HTTPStatus.UNAUTHORIZED, _LOGIN_PAGE.replace("%ERR%", err).encode("utf-8"),
                           "text/html; charset=utf-8")
                return False
        self._json({"error": "Ange koden från datorn"}, HTTPStatus.UNAUTHORIZED)
        return False

    # ----- routning -----
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._authorized():
            return
        try:
            self._route_get()
        except ApiError as e:
            self._json({"error": str(e)}, e.status)
        except Exception as e:  # noqa: BLE001
            self._json({"error": f"Internt fel: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):
        # Skydd mot att andra webbsidor anropar den lokala servern
        if self.headers.get("X-DeHazeIQ") != "1":
            return self._json({"error": "Saknar X-DeHazeIQ-header"}, HTTPStatus.FORBIDDEN)
        if not self._authorized():
            return
        try:
            self._route_post()
        except ApiError as e:
            self._json({"error": str(e)}, e.status)
        except Exception as e:  # noqa: BLE001
            self._json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _route_get(self):
        url = urlparse(self.path)
        parts = [unquote(x) for x in url.path.split("/") if x]
        q = parse_qs(url.query)
        if not parts:
            return self._file(WEB / "index.html")
        if parts[0] == "static" and len(parts) == 2 and re.fullmatch(r"[\w.-]+", parts[1]):
            return self._file(WEB / parts[1])
        if parts[0] == "media" and len(parts) == 4 and parts[2] in MEDIA_DIRS:
            p = _project(parts[1])
            base = (p.dir / parts[2]).resolve()
            f = (base / parts[3]).resolve()
            if base not in f.parents:
                raise ApiError("Ogiltig sökväg", HTTPStatus.FORBIDDEN)
            return self._file(f)
        if parts[0] != "api":
            raise ApiError("Hittades inte", HTTPStatus.NOT_FOUND)
        api = parts[1:]
        if api == ["lan"]:
            if self.is_remote:
                raise ApiError("Bara från datorn", HTTPStatus.FORBIDDEN)
            return self._json(lan_status())
        if api == ["info"]:
            return self._json({
                "version": __version__, "tagline": TAGLINE, "platform": sys.platform,
                "remote": self.is_remote, "encoder": media.encoder_label(),
                "hw_encoder": bool(media.hw_encoder()), "clip_ai": tagging.AVAILABLE or ai.available(),
                "projects_dir": str(PROJECTS_DIR),
                "analysis_version": pipeline.target_version(),
                "styles": {k: {"label": v["label"], "avg_shot": v["avg_shot"]} for k, v in STYLES.items()},
                "formats": list(FORMATS),
            })
        if api == ["projects"]:
            return self._json(Project.list_all())
        if api == ["vlm"]:
            return self._json(vlm.status())
        if len(api) >= 2 and api[0] == "p":
            p = _project(api[1])
            if len(api) == 2:
                return self._json(_project_view(p))
            if api[2:] == ["status"]:
                return self._json(JOBS.status(p.id))
            if api[2:] == ["themes"]:
                return self._json(pipeline.themes(p.id))
            if api[2:] == ["frame"]:
                cid = (q.get("clip") or [""])[0]
                if cid not in p.data["clips"]:
                    raise ApiError("Okänt klipp", HTTPStatus.NOT_FOUND)
                t = float((q.get("t") or ["0"])[0])
                w = int((q.get("w") or ["320"])[0])
                data = frame_jpeg(p, cid, t, w)
                return self._send(HTTPStatus.OK, data, "image/jpeg",
                                  {"Cache-Control": "max-age=86400"})
        raise ApiError("Hittades inte", HTTPStatus.NOT_FOUND)

    def _route_post(self):
        parts = [unquote(x) for x in urlparse(self.path).path.split("/") if x]
        body = self._body()
        if parts[:1] != ["api"]:
            raise ApiError("Hittades inte", HTTPStatus.NOT_FOUND)
        api = parts[1:]
        if api == ["projects"]:
            name = (body.get("name") or "").strip() or "Nytt projekt"
            p = Project.create(name[:80])
            return self._json(_project_view(p), HTTPStatus.CREATED)
        if api == ["import"]:
            # Ett klick: skapa projekt efter mappnamnet och kör hela flödet automatiskt
            if self.is_remote:
                raise ApiError("Det här görs på datorn.", HTTPStatus.FORBIDDEN)
            paths = [str(x) for x in body.get("paths") or [] if str(x).strip()]
            if not paths:
                raise ApiError("Ange en mapp eller filer")
            p = Project.create(auto_name(paths))
            JOBS.start(p.id, "auto", pipeline.auto, p.id, paths)
            return self._json(_project_view(p), HTTPStatus.CREATED)
        if api == ["choose"]:
            if self.is_remote:
                raise ApiError("Välj filer på datorn – dialogen öppnas där.", HTTPStatus.FORBIDDEN)
            return self._json({"paths": choose(body.get("kind", "folder"))})
        if api == ["lan"]:
            if self.is_remote:
                raise ApiError("Bara från datorn", HTTPStatus.FORBIDDEN)
            if body.get("enable"):
                return self._json(start_lan(self.server.server_address[1] + 1))
            return self._json(stop_lan())
        if api == ["vlm", "download"]:
            if self.is_remote:
                raise ApiError("Det här görs på datorn.", HTTPStatus.FORBIDDEN)
            st = vlm.status()
            if not st["supported"]:
                raise ApiError("Djupanalys stöds inte på den här datorn")
            if st["download"].get("state") != "running":
                threading.Thread(target=_vlm_download, daemon=True).start()
            return self._json({"ok": True})
        if len(api) < 3 or api[0] != "p":
            raise ApiError("Hittades inte", HTTPStatus.NOT_FOUND)
        p = _project(api[1])
        action = api[2:]
        busy_msg = "Vänta tills det pågående jobbet är klart."

        if self.is_remote and (action in (["import"], ["music"]) or action[-1:] == ["reveal"]):
            raise ApiError("Det här görs på datorn.", HTTPStatus.FORBIDDEN)
        if action == ["import"]:
            paths = [str(x) for x in body.get("paths") or [] if str(x).strip()]
            if not paths:
                raise ApiError("Ange en mapp eller filer")
            if JOBS.busy(p.id):
                raise ApiError(busy_msg, HTTPStatus.CONFLICT)
            JOBS.start(p.id, "auto", pipeline.auto, p.id, paths)
            return self._json({"ok": True})
        if action == ["auto"]:
            if JOBS.busy(p.id):
                raise ApiError(busy_msg, HTTPStatus.CONFLICT)
            JOBS.start(p.id, "auto", pipeline.auto, p.id, None)
            return self._json({"ok": True})
        if action == ["diagnostics"]:
            out = pipeline.diagnostics(p.id)
            if not self.is_remote:
                reveal(out)
            return self._json({"file": out.name})
        if action == ["rename"]:
            name = (body.get("name") or "").strip()
            if not name:
                raise ApiError("Ange ett namn")
            p.rename(name)
            return self._json({"name": p.data["name"]})
        if action == ["delete"]:
            if self.is_remote:
                raise ApiError("Projekt tas bort på datorn.", HTTPStatus.FORBIDDEN)
            if JOBS.busy(p.id):
                raise ApiError(busy_msg, HTTPStatus.CONFLICT)
            p.delete()
            return self._json({"deleted": p.id})
        if action == ["analyze"]:
            if JOBS.busy(p.id):
                raise ApiError(busy_msg, HTTPStatus.CONFLICT)
            JOBS.start(p.id, "analyze", pipeline.analyze_all, p.id, bool(body.get("redo")))
            return self._json({"ok": True})
        if action == ["deep"]:
            if JOBS.busy(p.id):
                raise ApiError(busy_msg, HTTPStatus.CONFLICT)
            if not vlm.ready():
                raise ApiError("Ladda ner modellen för djupanalys först")
            JOBS.start(p.id, "deep", pipeline.deep_analyze, p.id, bool(body.get("redo")))
            return self._json({"ok": True})
        if action == ["music"]:
            info = pipeline.set_music(p.id, body.get("path"))
            return self._json({"music": info})
        if action == ["settings"]:
            p.reload()
            s = p.data.setdefault("settings", {})
            for k in ("format", "length", "style"):
                if k in body:
                    s[k] = body[k]
            if isinstance(body.get("effects"), dict):
                eff = effects.enabled(s)
                eff.update({k: bool(v) for k, v in body["effects"].items() if k in effects.EFFECTS})
                if eff != effects.enabled(s):
                    # förhandsvisningarna gjordes med andra effekter: gör om dem vid nästa uppspelning
                    for prop in p.data.get("proposals", []):
                        (prop.get("renders") or {}).pop("preview", None)
                s["effects"] = eff
            p.save()
            save_default_settings(s)
            return self._json({"settings": s})
        if len(action) == 2 and action[0] == "clip":
            cid = action[1]
            if cid not in p.data["clips"]:
                raise ApiError("Okänt klipp", HTTPStatus.NOT_FOUND)
            fields = {k: bool(body[k]) for k in ("favorite", "excluded") if k in body}
            p.update_clip(cid, **fields)
            return self._json(p.data["clips"][cid])
        if action == ["generate"]:
            style = body.get("style", "auto")
            if style != "auto" and style not in STYLES:
                raise ApiError("Okänd stil")
            fmt = body.get("format", "9:16")
            try:
                length = float(body.get("length", 30))
            except (TypeError, ValueError):
                raise ApiError("Ogiltig längd")
            length = max(5.0, min(length, 600.0))
            favs = [c["id"] for c in p.clips() if c.get("favorite") and c.get("analysis")]
            theme = body.get("theme") or None
            try:
                props = pipeline.generate(p.id, style, fmt, length, favs, theme)
            except RuntimeError as e:
                raise ApiError(str(e))
            return self._json({"proposals": props})
        if len(action) == 3 and action[0] == "proposal":
            prop_id, verb = action[1], action[2]
            if not p.proposal(prop_id):
                raise ApiError("Förslaget finns inte", HTTPStatus.NOT_FOUND)
            if verb == "regenerate":
                try:
                    return self._json({"proposal": pipeline.regenerate_one(p.id, prop_id)})
                except RuntimeError as e:
                    raise ApiError(str(e))
            if verb == "render":
                res = body.get("resolution", "preview")
                if res not in ("preview", "720p", "1080p", "4k"):
                    raise ApiError("Okänd upplösning")
                if JOBS.busy(p.id):
                    raise ApiError(busy_msg, HTTPStatus.CONFLICT)
                JOBS.start(p.id, f"render:{res}:{prop_id}", pipeline.render_proposal, p.id, prop_id, res)
                return self._json({"ok": True})
            if verb == "reveal":
                name = body.get("file", "")
                f = (p.renders / name).resolve()
                if p.renders.resolve() not in f.parents or not f.exists():
                    raise ApiError("Filen finns inte", HTTPStatus.NOT_FOUND)
                reveal(f)
                return self._json({"ok": True})
        raise ApiError("Hittades inte", HTTPStatus.NOT_FOUND)


def _quote(s):
    from urllib.parse import quote
    return quote(s)


def start_server(port: int, lan: bool = False):
    """Starta den lokala servern. Returnerar (server, url); server är None om porten är upptagen
    (då körs DeHazeIQ troligen redan och url pekar på den)."""
    media.ffmpeg()
    media.ffprobe()
    media.lower_priority()
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{port}/"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        return None, url
    print(f"DeHazeIQ {__version__} – {TAGLINE}")
    print(f"Körs på {url}")
    print(f"Projekt sparas i {PROJECTS_DIR}")
    print("FFmpeg:", media.ffmpeg())
    print("Videokodning:", media.encoder_label())
    print("AI-bildförståelse:", "på" if ai.available() else "av (modellen saknas)")
    if lan:
        st = start_lan(port + 1)
        print("Mobil via wifi:", ", ".join(st["urls"]) or f"port {st['port']}", "· kod:", st["key"])
    return server, url


def main(argv=None):
    """Terminalläge: python -m dehazeiq [--lan] [--port N] [--no-browser] [--window]"""
    import argparse
    ap = argparse.ArgumentParser(description=f"DeHazeIQ – {TAGLINE}")
    ap.add_argument("--port", type=int, default=int(os.environ.get("DEHAZEIQ_PORT", 8765)))
    ap.add_argument("--lan", action="store_true", help="öppna även för mobil/surfplatta på samma wifi")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--window", action="store_true", help="öppna i eget fönster (kräver pywebview)")
    args = ap.parse_args(argv)
    if args.window:
        from . import launcher
        return launcher.main(["--port", str(args.port)] + (["--lan"] if args.lan else []))
    try:
        server, url = start_server(args.port, args.lan)
    except media.MediaError as e:
        print(f"\n{e}\n")
        sys.exit(1)
    if server is None:
        print(f"Port {args.port} är upptagen – körs DeHazeIQ redan? Öppnar webbläsaren.")
        webbrowser.open(url)
        return
    print("Avsluta med Ctrl+C.")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAvslutar.")

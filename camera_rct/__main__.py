"""Loopback-only HTTP UI; no third-party Python dependencies."""

import argparse
import fcntl
import json
import secrets
import signal
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .recorder import Recorder, load_config


ROOT = Path(__file__).resolve().parent.parent
WEB = Path(__file__).resolve().parent / "web"


def make_handler(recorder, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Recording events are printed separately, without request noise.

        def respond(self, code, body, content_type="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            port = self.server.server_address[1]
            return self.headers.get("Host") in ("localhost:{}".format(port), "127.0.0.1:{}".format(port))

        def do_GET(self):
            if not self.valid_host():
                self.respond(403, {"error": "Invalid host"})
                return
            if self.path == "/api/status":
                self.respond(200, recorder.status())
            elif self.path == "/api/token":
                self.respond(200, {"token": token})
            else:
                assets = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                          "/style.css": ("style.css", "text/css; charset=utf-8")}
                if self.path not in assets:
                    self.respond(404, {"error": "Not found"})
                    return
                filename, content_type = assets[self.path]
                self.respond(200, (WEB / filename).read_bytes(), content_type)

        def do_POST(self):
            if not self.valid_host() or self.headers.get("X-App-Token") != token:
                self.respond(403, {"error": "Invalid request token; reload the page"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("Invalid request length")
                data = json.loads(self.rfile.read(length))
                if self.path == "/api/selection":
                    recorder.save_selection(data)
                elif self.path == "/api/start":
                    recorder.start()
                elif self.path == "/api/stop":
                    recorder.stop()
                else:
                    self.respond(404, {"error": "Not found"})
                    return
                self.respond(200, recorder.status())
            except (ValueError, UnicodeError) as exc:
                self.respond(400, {"error": str(exc)})
            except OSError:
                self.respond(500, {"error": "文件写入失败，请检查磁盘和权限 / Check disk and permissions"})

    return Handler


def main():
    parser = argparse.ArgumentParser(description="RTSP camera recorder / RTSP 摄像头录制")
    parser.add_argument("--config", type=Path, default=ROOT / "config/cameras.json")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    recorder = server = None
    try:
        (ROOT / "data").mkdir(exist_ok=True)
        # Keep the file descriptor open: two app instances must not own one state file.
        with (ROOT / "data/app.lock").open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                parser.error("程序已运行 / Another recorder instance is running")
            config = load_config(args.config, ROOT)
            recorder = Recorder(ROOT, config)
            server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(recorder, secrets.token_urlsafe(32)))
            def shutdown(signum, frame):
                recorder.stop()
                threading.Thread(target=server.shutdown, daemon=True).start()
            signal.signal(signal.SIGINT, shutdown)
            signal.signal(signal.SIGTERM, shutdown)
            url = "http://localhost:{}".format(args.port)
            print("打开 / Open: " + url, flush=True)
            print("录像目录 / Recordings: " + str(config["output_dir"]), flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            try:
                server.serve_forever(poll_interval=0.2)
            finally:
                recorder.close()
                server.server_close()
    except (OSError, ValueError) as exc:
        # JSON errors and file paths are useful; config contents (URLs) are not printed.
        parser.exit(1, "启动失败 / Startup failed: {}\n请检查 config/cameras.json 和 data/state.json。\n".format(exc))


if __name__ == "__main__":
    main()

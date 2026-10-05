"""Independent FFmpeg workers with startup and frame-progress watchdogs."""

import json
import math
import os
import re
import selectors
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .storage import SelectionStore, write_json


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_config(path, root):
    with Path(path).open(encoding="utf-8") as stream:
        config = json.load(stream)
    if not isinstance(config, dict):
        raise ValueError("Configuration must be an object")
    cameras = config.get("cameras")
    if not isinstance(cameras, list) or not cameras:
        raise ValueError("Configure at least one camera")
    names = set()
    for camera in cameras:
        if not isinstance(camera, dict):
            raise ValueError("Each camera must be an object")
        name, url = camera.get("name", ""), camera.get("url", "")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", name) or name in names:
            raise ValueError("Camera names must be unique: letters, digits, _ and - only")
        if not isinstance(url, str) or urlsplit(url).scheme not in ("rtsp", "rtsps") or not urlsplit(url).hostname:
            raise ValueError("Camera URL must be RTSP/RTSPS (" + name + ")")
        names.add(name)
    for key, default in (("startup_timeout_seconds", 30), ("stall_timeout_seconds", 15)):
        value = config.get(key, default)
        if type(value) not in (float, int) or not math.isfinite(value) or value < 1:
            raise ValueError(key + " must be a finite number >= 1")
        config[key] = value
    output = config.get("output_dir", "recordings")
    if not isinstance(output, str) or not output.strip():
        raise ValueError("output_dir must be a nonempty path")
    config["output_dir"] = (Path(root) / Path(output).expanduser()).resolve()
    return config


def ffmpeg_command(binary, camera, output):
    # A separate watchdog avoids the timeout/stimeout option differences in
    # the FFmpeg versions shipped by Ubuntu 20.04 and newer distributions.
    return [binary, "-hide_banner", "-nostdin", "-loglevel", "error", "-n",
            "-rtsp_transport", "tcp", "-i", camera["url"],
            "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
            "-progress", "pipe:1", "-nostats", str(output)]


def finish_process(process):
    if process.poll() is None:
        try:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        except ProcessLookupError:
            process.wait()


class Recorder:
    def __init__(self, root, config, binary=None):
        self.root = Path(root)
        self.config = config
        self.binary = binary or shutil.which("ffmpeg")
        if not self.binary:
            raise ValueError("未找到 FFmpeg，请安装 / Install ffmpeg first")
        self.lock = threading.RLock()
        self.store = SelectionStore(self.root / "data/state.json")
        self.log_path = self.root / "logs/events.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.active = False
        self.stopping = False
        self.session = None
        self.session_dir = None
        self.cameras = {}
        self.threads = []
        self.stop_event = threading.Event()
        self.log_error = None

    def status(self):
        with self.lock:
            return {"selection": dict(self.store.value), "active": self.active,
                    "stopping": self.stopping, "session": self.session,
                    "cameras": [dict(value) for value in self.cameras.values()],
                    "log_error": self.log_error}

    def save_selection(self, value):
        with self.lock:
            if self.active:
                raise ValueError("录制期间不能修改选项 / Recording is active")
            self.store.save(value)

    def event(self, event, camera=None, reason=None):
        with self.lock:
            entry = {"time": timestamp(), "session": self.session, "event": event,
                     "camera": camera, "reason": reason}
            line = json.dumps(entry, ensure_ascii=False)
            print(line, flush=True)
            # Never include RTSP URLs or credentials in persistent logs.
            for path in (self.log_path, self.session_dir / "events.jsonl"):
                try:
                    with path.open("a", encoding="utf-8") as stream:
                        stream.write(line + "\n")
                except OSError:
                    self.log_error = "日志写入失败，请检查磁盘 / Cannot write event log; check disk"

    def start(self):
        with self.lock:
            if self.active:
                raise ValueError("已经在录制 / Recording is already active")
            selection = dict(self.store.value)
            session = "{number:04d}_{group}_{visit}_".format(**selection)
            session += datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            directory = self.config["output_dir"] / session
            directory.mkdir(parents=True, exist_ok=False)
            write_json(directory / "session.json", {
                "session": session, "started_at": timestamp(), "selection": selection,
                "cameras": [camera["name"] for camera in self.config["cameras"]]})
            self.session, self.session_dir = session, directory
            self.stop_event = threading.Event()
            self.active, self.stopping, self.log_error = True, False, None
            self.cameras = {camera["name"]: {"name": camera["name"], "state": "connecting",
                            "reason": None} for camera in self.config["cameras"]}
            self.threads = []
            self.event("session_started")
            for camera in self.config["cameras"]:
                thread = threading.Thread(target=self._record, args=(camera,), daemon=True)
                self.threads.append(thread)
                try:
                    thread.start()
                except RuntimeError:
                    self.threads.remove(thread)
                    self._finished(camera["name"], "failed", "worker_start_failed")

    def stop(self):
        with self.lock:
            if self.active:
                self.stopping = True
                self.stop_event.set()

    def close(self):
        self.stop()
        for thread in self.threads:
            thread.join()

    def _finished(self, name, state, reason):
        with self.lock:
            self.cameras[name].update(state=state, reason=reason)
            self.event("camera_failed" if state == "failed" else "camera_stopped", name, reason)
            if all(value["state"] in ("failed", "stopped") for value in self.cameras.values()):
                self.active, self.stopping = False, False
                self.event("session_finished", reason="user_stop" if self.stop_event.is_set() else "all_cameras_failed")

    def _record(self, camera):
        name = camera["name"]
        process = None
        selector = selectors.DefaultSelector()
        state, reason = "failed", "worker_error"
        try:
            # 每个摄像头独立运行一个 FFmpeg 进程，避免单路故障影响其他摄像头。
            process = subprocess.Popen(ffmpeg_command(self.binary, camera, self.session_dir / (name + ".mkv")),
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, start_new_session=True)
            selector.register(process.stdout, selectors.EVENT_READ)
            started = last_progress = time.monotonic()
            last_frame = 0
            pending = b""
            while True:
                if self.stop_event.is_set():
                    # 主线程请求停止时，记录正常停止原因并跳出循环。
                    state, reason = "stopped", "user_stop"
                    break
                for key, _ in selector.select(timeout=0.2):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        if line.startswith(b"frame="):
                            try:
                                frame = int(line.split(b"=", 1)[1])
                            except ValueError:
                                continue
                            if frame > last_frame:
                                # 只有帧数继续增长才算有进展，并在首帧到达时标记为录制中。
                                last_frame, last_progress = frame, time.monotonic()
                                with self.lock:
                                    if self.cameras[name]["state"] == "connecting":
                                        self.cameras[name]["state"] = "recording"
                                        self.event("camera_recording", name)
                code = process.poll()
                if code is not None:
                    # FFmpeg 自行退出通常表示流结束或进程异常退出。
                    reason = "stream_ended_exit_{}".format(code)
                    break
                now = time.monotonic()
                if last_frame == 0 and now - started > self.config["startup_timeout_seconds"]:
                    # 启动超时表示尚未收到任何视频帧。
                    reason = "startup_timeout"
                    break
                if last_frame > 0 and now - last_progress > self.config["stall_timeout_seconds"]:
                    # 已经有过视频帧但长时间没有新帧，判定为流卡住。
                    reason = "frame_timeout"
                    break
        except OSError:
            # 进程创建、管道读取或 selector 操作失败时交给统一收尾逻辑处理。
            reason = "process_or_io_error"
        finally:
            if process is not None:
                # 无论退出原因是什么，都确保 FFmpeg 和输出管道被回收。
                finish_process(process)
                if process.stdout:
                    process.stdout.close()
            selector.close()
            self._finished(name, state, reason)

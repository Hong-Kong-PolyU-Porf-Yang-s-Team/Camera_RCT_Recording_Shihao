# RTSP Camera Recorder

[中文（默认）](../README.md) | English

A compact, large-text recording interface for Ubuntu 20.04 desktop and Ubuntu 20.04 under Windows WSL2. One Python application serves the frontend and runs independent FFmpeg workers. Uses Python 3.10 and FFmpeg; no pip packages or Node.js. The UI is approximately 490px wide; resize the browser window for a small control panel.

## Features

- **0001–9999** ID, changed one step using `−` / `+`, without wrapping.
- Dropdowns for **I (Intervention) / C (Control)** and **1 / 2**.
- Selections immediately persisted to `data/state.json` and restored on restart. IDs do not increment automatically; press `+` for the next participant.
- Independent RTSP recording: failed cameras do not stop healthy ones, even if only one remains. The session ends automatically when all fail, or manually using Stop.
- Videos default to **`~/Desktop/data/`**, with all videos directly in one folder. Duplicate recordings cancel the entire start operation with an error.
- Logs identify the camera, session, reason and timestamp, using the system timezone with a UTC offset.

There was no legacy recorder in the repository, so naming and MKV are new defaults. The interface displays recording status, without live video preview. Independent connections do not provide frame-level synchronization.

## Runtime and dependencies

Use **Python 3.10**. The application and tests use only the Python standard library: **no third-party Python packages are required**. The repository's `requirements.txt` documents this and contains no pip dependencies.

| Dependency | Purpose and installation |
| --- | --- |
| Python 3.10 standard library | `http.server` serves the UI; `subprocess`, `threading` and `selectors` manage recording workers; `json` and `pathlib` persist configuration; `fcntl` provides the Linux process lock; `unittest` runs tests. Included with Python; no pip installation needed |
| FFmpeg / ffprobe | System command-line tools for RTSP recording and video verification. Install the Ubuntu `ffmpeg` package; these are not Python packages |
| Browser | Opens the local interface; WSL2 can use a Windows browser |

### Dependency checklist for a fresh WSL Ubuntu installation

- **Python runtime:** Python 3.10, including its standard library.
- **Ubuntu system packages:** `ffmpeg`, which provides both the `ffmpeg` and `ffprobe` commands. apt automatically installs its required system dependencies.
- **Python packages installed through pip:** None. OpenCV, Flask, NumPy and Python FFmpeg wrappers are unnecessary; no `pip install` command is needed.
- **Interface environment:** Use your existing Windows browser. No Linux graphical desktop, Node.js or npm is required.

First check the Ubuntu and Python versions in your fresh installation:

```bash
cat /etc/os-release
python3 --version
python3.10 --version
```

Ubuntu 20.04 ships with Python 3.8 by default; `sudo apt install python3` alone does not provide Python 3.10. If `python3.10` is not found, install or configure Python 3.10 separately before continuing. The FFmpeg installation command below does not install Python 3.10.

Install the required system package inside the Ubuntu terminal:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

Verify the installation:

```bash
python3.10 --version
ffmpeg -version
ffprobe -version
```

## Setup and launch

After preparing the dependencies above, run the following from the repository directory. Subsequent commands explicitly use `python3.10` to avoid selecting a different system `python3` version:

```bash
cp config/cameras.example.json config/cameras.json
```

Edit `config/cameras.json`. Replace all three placeholder URLs (`192.168.1.101`, `.102`, `.103`), including credentials and the manufacturer's stream path. `/stream1` is only an example. URL-encode special characters in credentials. Camera names must be unique and contain only letters, digits, underscores or hyphens, up to 48 characters.

```bash
python3.10 -m camera_rct
```

Open **http://localhost:8765**, select ID/group/visit and click **Start**. Click **Stop** and wait for **Session finished** before exiting. Terminal `Ctrl+C` or SIGTERM also stops workers and attempts to finalize video files.

On WSL2, use this command and open the URL in a **Windows browser**, without requiring a Linux graphical environment:

```bash
python3.10 -m camera_rct --no-browser
```

Use `--port 8766` for another port or `--config /path/to/cameras.json` for another configuration. The service listens only on `127.0.0.1`. If WSL2 localhost access fails, check Windows/WSL localhost forwarding. Cameras must be reachable from WSL2; VPNs, firewalls and subnets can affect access.

**Output path:** In WSL2, `~` means the Ubuntu user's home, not the Windows desktop. To store on Windows, set `output_dir` to `/mnt/c/Users/YOUR_WINDOWS_USER/Desktop/data`, adjusting for OneDrive if applicable. On Ubuntu desktop, keep `~/Desktop/data`. Missing directories are created automatically. Relative paths resolve against the project root.

## Files and failures

```text
~/Desktop/data/
├── 20261006_0001_I_1_1.mkv
├── 20261006_0001_I_1_2.mkv
└── 20261006_0001_I_1_3.mkv
```

Names follow `YYYYMMDD_ID_C-or-I_1-or-2_cameraNumber.mkv`. IDs have four digits; camera numbers start at 1 in configuration order. Any existing recording with the same date, ID, group and visit blocks the entire start operation. The page lists all matching filenames; delete them before retrying. Files are never automatically renamed or overwritten.

A camera failing at startup may produce no video or an incomplete file. Events are stored only in the project's `logs/events.jsonl` and printed in the terminal. No per-session metadata or event files are created. Example:

```json
{"time":"2026-10-05T14:30:15+08:00","session":"20261005_0001_I_1","event":"camera_failed","camera":"camera2","reason":"frame_timeout"}
```

Each camera uses an independent FFmpeg process over RTSP/TCP. Its first video stream and optional audio are copied without re-encoding into MKV. Codecs must be supported by FFmpeg/MKV. See the official [RTSP documentation](https://ffmpeg.org/ffmpeg-protocols.html#rtsp) and [stream copy documentation](https://ffmpeg.org/ffmpeg.html#Streamcopy).

| Reason | Meaning |
| --- | --- |
| `startup_timeout` | No initial video progress within 30 seconds; configurable via `startup_timeout_seconds` |
| `frame_timeout` | No new video frames for 15 seconds after starting; configurable via `stall_timeout_seconds` |
| `stream_ended_exit_N` | FFmpeg exited with code N; unexpectedly ended streams count as failures |
| `process_or_io_error` / `worker_start_failed` | Process/file operation failure / worker thread startup failure |
| `user_stop` | Normal operator stop, not a camera failure |

Failed cameras do not reconnect automatically within a session. Repair the connection, stop the current session and start a new one. After a timeout, a worker allows up to approximately five more seconds for finalization before killing an unresponsive process. Forced termination, power loss or full disks may leave incomplete video; check storage regularly. Log write failures appear in the UI while terminal events continue. Raw FFmpeg error text is discarded to prevent credential leakage, so an exit code alone cannot distinguish network, authentication and codec problems.

Closing the browser **does not stop recording**; reopen the page to control it. Selections are locked while active. A process lock prevents two instances sharing the same project state. Corrupt state JSON causes a startup error instead of silently resetting IDs; back up and repair or remove `data/state.json`.

## Layout and migration

```text
camera_rct/
  __main__.py           HTTP service and entry point
  recorder.py           Independent workers, watchdogs and logs
  storage.py            JSON validation and atomic persistence
  web/                  HTML, CSS and JavaScript frontend
config/
  cameras.example.json  Three placeholder cameras; copy to cameras.json
markdown/README_EN.md   English documentation
tests/test_recorder.py  Automated tests
data/                  Generated cache and process lock
logs/                  Generated aggregate events
```

Real configuration (including passwords), cache and logs are ignored by Git. Default recordings are outside the repository. To migrate, copy the project, real configuration and `data/state.json`, install Python 3.10 and FFmpeg, then verify camera addresses and output paths. Copy existing recordings separately.

## Tests

```bash
python3.10 -m unittest discover -s tests -v
```

Tests cover persistence and limits, one/two/all camera failures, startup/frame timeouts, manual stop, flat filenames, duplicate rejection, restored IDs after restart and HTTP mutation checks. Real FFmpeg-generated video verifies readable MKV output (skipped without FFmpeg/ffprobe). Simulations do not replace hardware acceptance testing: connect all three cameras, disconnect them one by one, verify remaining recordings continue, then inspect logs and play back the files.

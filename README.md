# RTSP 摄像头录制

中文（默认） | [English](markdown/README_EN.md)

适用于 Ubuntu 20.04 桌面和 Windows 下 Ubuntu 20.04 WSL2。Python 一体化程序同时提供浏览器界面与 RTSP 录制后台，无需 Node.js 或第三方 Python 包。界面约 490px 宽、大字号、大按钮，可缩小浏览器窗口使用。

## 功能

- 编号 **0001–9999**，点击 `−` / `+` 每次调整 1，边界不循环。
- 下拉选择 **I（Intervention，干预）/ C（Control，对照）** 和 **1 / 2**。
- 选项即时保存至项目内 `data/state.json`，重启后恢复。结束录制不会自动增加编号；下一位请点 `+`。
- 每路摄像头独立录制。一台故障，其余继续；只剩一台也继续；全部故障才自动结束本次录制。支持手动停止。
- 默认录像存到 **`~/Desktop/data/`**，所有录像直接放在同一目录，不创建批次子目录；重复录制会报错并取消整次启动。
- 日志记录故障时间、摄像头名称、录制批次和原因；时间使用系统本地时区，包含 UTC 偏移。

仓库最初没有旧录制代码，因此文件命名和 MKV 格式是新默认值。界面显示录制状态，不提供实时视频预览。独立连接不保证三路画面帧级同步。

## 运行环境与依赖

使用 **Python 3.10**。当前代码和测试只使用 Python 标准库，**无需安装第三方 Python 包**。仓库的 `requirements.txt` 记录这一点，没有需要通过 pip 安装的依赖。

| 依赖 | 用途与安装方式 |
| --- | --- |
| Python 3.10 标准库 | `http.server` 提供界面服务；`subprocess`、`threading`、`selectors` 管理录像进程；`json`、`pathlib` 保存配置；`fcntl` 提供 Linux 进程锁；`unittest` 运行测试。随 Python 提供，无需 pip 安装 |
| FFmpeg / ffprobe | 系统命令行工具，用于 RTSP 录制和视频验证；通过 Ubuntu 的 `ffmpeg` 软件包安装，不是 Python 包 |
| 浏览器 | 打开本地操作界面；WSL2 可使用 Windows 浏览器 |

### 全新 WSL Ubuntu 的依赖清单

- **Python 运行环境：** Python 3.10（包含标准库）。
- **Ubuntu 系统软件包：** `ffmpeg`，同时提供 `ffmpeg` 和 `ffprobe` 命令；apt 会自动安装它所需的系统依赖。
- **通过 pip 安装的 Python 包：** 无。无需安装 OpenCV、Flask、NumPy 或 Python FFmpeg 包，也无需运行 `pip install`。
- **界面环境：** 使用现有 Windows 浏览器即可，无需安装 Linux 图形桌面、Node.js 或 npm。

先检查新安装的 Ubuntu 和 Python 版本：

```bash
cat /etc/os-release
python3 --version
python3.10 --version
```

Ubuntu 20.04 默认提供 Python 3.8，单独执行 `sudo apt install python3` 不会得到 Python 3.10。若 `python3.10` 提示找不到命令，需要先单独安装或配置 Python 3.10；下面安装 FFmpeg 的命令不会安装 Python 3.10。

在 Ubuntu 终端安装所需系统软件包：

```bash
sudo apt update
sudo apt install -y ffmpeg
```

安装完成后检查：

```bash
python3.10 --version
ffmpeg -version
ffprobe -version
```

## 安装与启动

完成上述依赖准备后，在项目目录执行。后续命令显式使用 `python3.10`，避免使用到系统中其他版本的 `python3`：

```bash
cp config/cameras.example.json config/cameras.json
```

编辑 `config/cameras.json`：示例中的三个 IP 为 `192.168.1.101`、`.102`、`.103`，请替换完整 RTSP 地址，包括用户名、密码和厂商指定的流路径。`/stream1` 只是示例。密码中的 `@`、`:` 等特殊字符需要 URL 编码。摄像头名称必须唯一，只能使用字母、数字、下划线、短横线，最多 48 字符。

```bash
python3.10 -m camera_rct
```

打开 **http://localhost:8765**，选择编号、组别、次数，点击“开始录制”。结束时点“停止录制”，等到显示“本次录制已结束”再退出。终端 `Ctrl+C` 或 SIGTERM 也会停止各路并尽量完成视频封装。

WSL2 中运行下面命令，然后在 **Windows 浏览器**打开上述地址，无需 WSL 图形环境：

```bash
python3.10 -m camera_rct --no-browser
```

端口冲突时用 `--port 8766`，自定义配置用 `--config /path/to/cameras.json`。程序仅监听 `127.0.0.1`。若 WSL2 无法通过 localhost 访问，请检查 Windows/WSL 的 localhost 转发。摄像头需要能从 WSL2 访问；VPN、防火墙或不同网段可能影响连接。

**存储路径：** WSL2 的 `~` 是 Ubuntu 用户家目录，因此默认不是 Windows 桌面。若要存 Windows 桌面，将配置的 `output_dir` 改为 `/mnt/c/Users/你的Windows用户名/Desktop/data`（使用 OneDrive 时按实际路径调整）。Ubuntu 桌面保留默认 `~/Desktop/data` 即可。目录不存在时自动创建，相对路径按项目根目录解析。

## 文件与故障处理

```text
~/Desktop/data/
├── 20261006_0001_I_1_1.mkv
├── 20261006_0001_I_1_2.mkv
└── 20261006_0001_I_1_3.mkv
```

文件名格式为 `年月日_ID_C或I_1或2_摄像头编号.mkv`，ID 保留四位，摄像头编号按配置列表顺序从 1 开始。开始前检查同一日期、ID、组别和次数的所有已有录像；即使只有一个文件，也会取消整次录制，并在页面逐行列出需要删除的旧文件。删除这些文件后才可重录，不自动改名或覆盖。

连接失败的摄像头可能没有视频文件或只有不完整文件。事件统一保存到项目内 `logs/events.jsonl`，终端也打印相同内容，不再生成批次 `session.json` 或单独的事件文件。例如：

```json
{"time":"2026-10-05T14:30:15+08:00","session":"20261005_0001_I_1","event":"camera_failed","camera":"camera2","reason":"frame_timeout"}
```

每路独立运行 FFmpeg，通过 RTSP/TCP 连接，复制第一条视频流和可选音频，不重编码，封装为 MKV。摄像头编码需被 FFmpeg/MKV 支持。参考官方 [RTSP 文档](https://ffmpeg.org/ffmpeg-protocols.html#rtsp) 和 [流复制说明](https://ffmpeg.org/ffmpeg.html#Streamcopy)。

| 原因 | 含义 |
| --- | --- |
| `startup_timeout` | 默认 30 秒没有开始输出视频帧；可用 `startup_timeout_seconds` 调整 |
| `frame_timeout` | 开始录制后默认 15 秒没有新帧；可用 `stall_timeout_seconds` 调整 |
| `stream_ended_exit_N` | FFmpeg 退出，N 为退出码；提前结束的流也视为故障 |
| `process_or_io_error` / `worker_start_failed` | 进程或文件操作失败 / 工作线程启动失败 |
| `user_stop` | 操作员正常停止，不算摄像头故障 |

故障摄像头不会在同次录制中自动重连；修复后停止当前批次，再开始新批次。超时后最多另等约 5 秒让进程完成封装，仍不退出则强制结束对应进程。强制终止、断电、磁盘写满可能造成视频尾部缺失，请定期检查空间。日志写入失败会在界面提示，终端仍打印事件。为避免泄露 RTSP 密码，不保存 FFmpeg 原始错误文本；退出码本身无法区分网络、认证和格式问题。

关闭网页**不会停止录制**，重新打开即可继续控制。录制期间锁定选项。同一项目禁止同时运行两份程序。缓存损坏时会报错而不会默默重置编号，请先备份再修复或删除 `data/state.json`。

## 目录与迁移

```text
camera_rct/
  __main__.py           HTTP 服务及启动入口
  recorder.py           独立录制、超时及日志
  storage.py            JSON 校验与原子保存
  web/                  HTML、CSS、JavaScript 前端
config/
  cameras.example.json  三路地址模板，复制为 cameras.json
markdown/README_EN.md   英文说明
tests/test_recorder.py  自动测试
data/                  自动生成：缓存和进程锁
logs/                  自动生成：汇总日志
```

真实配置（包含密码）、缓存、日志已被 Git 忽略；默认录像在仓库外。迁移时复制项目、真实配置和 `data/state.json`，安装 Python 3.10 和 FFmpeg，并核对摄像头地址及输出路径。已有录像需另行复制。

## 测试

```bash
python3.10 -m unittest discover -s tests -v
```

测试覆盖缓存及编号边界、一/两/全部摄像头故障、启动与断流超时、手动停止、平铺命名、重复录制拒绝启动、重启恢复编号和 HTTP 操作校验。真实 FFmpeg 生成测试画面并验证 MKV 可读性（未安装 FFmpeg/ffprobe 则跳过）。模拟测试不能替代实机验收：接入三路摄像头后逐台断开，确认剩余录像持续写入，最后检查日志与视频回放。

"use strict";
const element = (id) => document.getElementById(id);
let token, status, busy = false;
const states = {connecting: "连接中 / Connecting", recording: "录制中 / Recording",
  failed: "故障 / Failed", stopped: "已停止 / Stopped"};
const reasons = {startup_timeout: "连接超时 / Connection timeout", frame_timeout: "断流超时 / No new frames",
  process_or_io_error: "进程或文件错误 / Process or file error", worker_error: "录制错误 / Recording error",
  worker_start_failed: "启动失败 / Worker failed to start"};

async function request(path, body) {
  const options = body === undefined ? {} : {method: "POST",
    headers: {"Content-Type": "application/json", "X-App-Token": token}, body: JSON.stringify(body)};
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "请求失败 / Request failed");
  return result;
}
function render() {
  if (!status) return;
  element("number").textContent = String(status.selection.number).padStart(4, "0");
  element("group").value = status.selection.group;
  element("visit").value = status.selection.visit;
  element("selection").disabled = status.active || busy;
  element("minus").disabled = status.selection.number <= 1;
  element("plus").disabled = status.selection.number >= 9999;
  element("start").disabled = status.active || busy;
  element("stop").disabled = !status.active || status.stopping || busy;
  element("summary").textContent = status.stopping ? "正在停止 / Stopping…" : status.active ?
    "正在录制 / Recording" : status.session ? "本次录制已结束 / Session finished" : "准备就绪 / Ready";
  element("session").textContent = status.session || "";
  element("cameras").replaceChildren(...status.cameras.map((camera) => {
    const item = document.createElement("li");
    item.dataset.state = camera.state;
    item.textContent = `${camera.name}: ${states[camera.state]}`;
    if (camera.reason && camera.reason !== "user_stop") {
      item.append(document.createElement("br"));
      const detail = document.createElement("small");
      detail.textContent = reasons[camera.reason] || "视频流已结束 / Stream ended";
      item.append(detail);
    }
    return item;
  }));
  if (status.log_error) element("error").textContent = status.log_error;
}
async function change(path, body) {
  if (busy) return;
  busy = true; render();
  element("error").textContent = "";
  try { status = await request(path, body); }
  catch (error) { element("error").textContent = error.message; }
  finally { busy = false; render(); }
}
function select(patch) { change("/api/selection", {...status.selection, ...patch}); }
element("minus").onclick = () => select({number: status.selection.number - 1});
element("plus").onclick = () => select({number: status.selection.number + 1});
element("group").onchange = (event) => select({group: event.target.value});
element("visit").onchange = (event) => select({visit: Number(event.target.value)});
element("start").onclick = () => change("/api/start", {});
element("stop").onclick = () => change("/api/stop", {});
async function poll() {
  if (!busy) {
    // Serialize polling with button requests so stale responses cannot undo a selection.
    busy = true;
    try {
      token = (await request("/api/token")).token;
      status = await request("/api/status");
      element("error").textContent = "";
      busy = false; render();
    } catch (error) {
      busy = false;
      element("error").textContent = "连接中断，请检查终端 / Connection lost; check terminal";
      element("selection").disabled = element("start").disabled = element("stop").disabled = true;
    }
  }
  setTimeout(poll, 1000);
}
poll();

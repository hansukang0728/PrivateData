// 윈도우 셸에 넘기는 동작들 — 기본 앱으로 열기, 탐색기에서 표시, 속성 대화상자.
import { execFile, spawn } from "node:child_process";
import path from "node:path";

const isWin = process.platform === "win32";

export function openDefault(target) {
  if (!isWin) { spawn("xdg-open", [target], { detached: true, stdio: "ignore" }).unref(); return; }
  spawn("cmd.exe", ["/c", "start", "", target], { detached: true, stdio: "ignore", windowsHide: true }).unref();
}

export function reveal(target) {
  if (!isWin) { spawn("xdg-open", [path.dirname(target)], { detached: true, stdio: "ignore" }).unref(); return; }
  spawn("explorer.exe", ["/select,", target], { detached: true, stdio: "ignore" }).unref();
}

// 속성 대화상자는 COM(Shell.Application)을 거쳐야 뜬다.
export function properties(target) {
  if (!isWin) return;
  const dir = path.dirname(target).replace(/'/g, "''");
  const leaf = path.basename(target).replace(/'/g, "''");
  const ps = `$s = New-Object -ComObject Shell.Application; $f = $s.Namespace('${dir}'); ` +
             `$i = $f.ParseName('${leaf}'); if ($i) { $i.InvokeVerb('Properties') }`;
  execFile("powershell.exe", ["-NoProfile", "-NonInteractive", "-STA", "-Command", ps], { windowsHide: true }, () => {});
}

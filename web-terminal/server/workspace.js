// 작업셋 자동 저장 — 그룹 구성과 폴더·이름·배치만. 실행 중이던 명령은 저장하지 않는다.
import fs from "node:fs";
import path from "node:path";
import { dataDir } from "./pty.js";

const FILE = () => path.join(dataDir(), "workspace.json");

export function load() {
  try { return JSON.parse(fs.readFileSync(FILE(), "utf8")); }
  catch { return null; }
}

export function save(state) {
  try {
    fs.writeFileSync(FILE(), JSON.stringify(state, null, 2), "utf8");
    return true;
  } catch (e) {
    console.error("[PoshDeck] 작업셋 저장 실패:", e.message);
    return false;
  }
}

export function configPath() { return path.join(dataDir(), "config.json"); }

export function config() {
  const defaults = { roots: [], defaultShell: "pwsh", port: 7788 };
  try { return { ...defaults, ...JSON.parse(fs.readFileSync(configPath(), "utf8")) }; }
  catch { return defaults; }
}

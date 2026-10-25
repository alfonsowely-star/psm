/**
 * runs/ 目录管理：生成 runId、保存输入与配置、列历史、读报告。
 */
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

export function genRunId() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

export async function saveRun({ runsDir, runId, inputText, format, config }) {
  const dir = path.join(runsDir, runId);
  await mkdir(dir, { recursive: true });
  const ext = format === "jsonl" ? "jsonl" : "csv";
  await writeFile(path.join(dir, `input.${ext}`), inputText, "utf-8");
  await writeFile(path.join(dir, "config.json"), JSON.stringify(config, null, 2), "utf-8");
  return dir;
}

export async function listRuns(runsDir) {
  try {
    const entries = await readdir(runsDir, { withFileTypes: true });
    const runs = [];
    for (const e of entries) {
      if (!e.isDirectory()) continue;
      try {
        const manifest = JSON.parse(await readFile(path.join(runsDir, e.name, "manifest.json"), "utf-8"));
        runs.push({ runId: e.name, ...manifest });
      } catch { /* 无 manifest 则跳过 */ }
    }
    return runs.sort((a, b) => b.runId.localeCompare(a.runId));
  } catch {
    return [];
  }
}

export async function loadReport(runsDir, runId) {
  const dir = path.join(runsDir, runId);
  const reportData = JSON.parse(await readFile(path.join(dir, "report.json"), "utf-8"));
  const html = await readFile(path.join(dir, "report.html"), "utf-8");
  return { reportData, html };
}

export default { genRunId, saveRun, listRuns, loadReport };

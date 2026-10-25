/**
 * HTTP 服务：静态前端 + JSON API + 调 Python 分析引擎。原生 http，零依赖。
 */
import http from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFile } from "node:child_process";

import { parseTable } from "./data.mjs";
import { genRunId, saveRun, listRuns, loadReport } from "./store.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WEB_DIR = path.join(__dirname, "..", "web");
const RUNS_DIR = path.join(__dirname, "..", "runs");
const PY_DIR = path.join(__dirname, "..", "python");
const PYTHON = process.env.PYTHON || "python";

const PORT = Number(process.env.PORT) || 5175;

const state = {
  data: null,       // { text, format, columns, rowCount }
  config: null,     // { treatCol, treatValue, outcomeCol, covCols, userCol, timeCol, binary, B, N_perm }
  lastRunId: null,
};

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => {
      data += c;
      if (data.length > 50e6) { reject(new Error("请求体过大")); req.destroy(); }
    });
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

function send(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { "Content-Type": "application/json; charset=utf-8" });
  res.end(body);
}

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml" };

async function serveStatic(res, pathname) {
  let file = pathname === "/" ? "index.html" : pathname.slice(1);
  const fp = path.join(WEB_DIR, file);
  if (!fp.startsWith(WEB_DIR)) { res.writeHead(403); res.end(); return; }
  try {
    const data = await readFile(fp);
    res.writeHead(200, { "Content-Type": MIME[path.extname(fp)] ?? "text/plain; charset=utf-8" });
    res.end(data);
  } catch {
    res.writeHead(404); res.end("not found");
  }
}

function runPython(args) {
  return new Promise((resolve, reject) => {
    execFile(PYTHON, ["-B", ...args], {
      cwd: PY_DIR,
      maxBuffer: 30 * 1024 * 1024,
      env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" },
    }, (err, stdout, stderr) => {
      if (err) reject(new Error(String(stderr || err.message || "python 运行失败").trim().slice(-2000)));
      else resolve(stdout);
    });
  });
}

function validateConfig(config, columns) {
  const names = new Set(columns.map((c) => c.name));
  const errs = [];
  if (!config.treat_col || !names.has(config.treat_col)) errs.push("处理方列（谁新谁老）未指定或不存在");
  if (!Array.isArray(config.cov_cols) || config.cov_cols.length === 0) errs.push("维度（协变量）不能为空");
  else config.cov_cols.forEach((c) => { if (!names.has(c)) errs.push(`维度「${c}」不存在`); });
  if (config.treat_value == null || config.treat_value === "") errs.push("新 agent 取值未指定");
  if (config.outcome_col && !names.has(config.outcome_col)) errs.push(`结局列「${config.outcome_col}」不存在`);
  return errs;
}

async function handleRun(body) {
  if (!state.data) throw new Error("请先导入数据");
  if (!state.config) throw new Error("请先完成列映射");

  const errs = validateConfig(state.config, state.data.columns);
  if (errs.length) { const e = new Error(errs.join("；")); e.status = 400; throw e; }

  const runId = genRunId();
  const dir = await saveRun({
    runsDir: RUNS_DIR,
    runId,
    inputText: state.data.text,
    format: state.data.format,
    config: state.config,
  });
  const ext = state.data.format === "jsonl" ? "jsonl" : "csv";
  await runPython([
    "analyze.py",
    "--data", path.join(dir, `input.${ext}`),
    "--config", path.join(dir, "config.json"),
    "--outdir", dir,
  ]);
  state.lastRunId = runId;
  const manifest = JSON.parse(await readFile(path.join(dir, "manifest.json"), "utf-8"));
  return { runId, manifest };
}

async function handle(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const p = url.pathname;
  try {
    if (req.method === "GET" && p === "/api/state") {
      return send(res, 200, {
        hasData: Boolean(state.data),
        columns: state.data?.columns ?? [],
        rowCount: state.data?.rowCount ?? 0,
        config: state.config,
        lastRunId: state.lastRunId,
      });
    }
    if (req.method === "GET" && p === "/api/runs") {
      return send(res, 200, { runs: await listRuns(RUNS_DIR) });
    }
    if (req.method === "GET" && p.startsWith("/api/report/")) {
      const runId = decodeURIComponent(p.slice("/api/report/".length));
      try {
        const { reportData } = await loadReport(RUNS_DIR, runId);
        return send(res, 200, { reportData });
      } catch {
        return send(res, 404, { error: "找不到该运行" });
      }
    }
    if (req.method === "GET" && p.startsWith("/api/view/")) {
      const runId = decodeURIComponent(p.slice("/api/view/".length));
      try {
        const { html } = await loadReport(RUNS_DIR, runId);
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        return res.end(html);
      } catch {
        res.writeHead(404, { "Content-Type": "text/html; charset=utf-8" });
        return res.end('<!doctype html><body style="font:14px system-ui,sans-serif;padding:24px;color:#555">报告还没生成好，或该运行不存在。请回到结果页重新运行，或点「历史运行」里其它记录。</body>');
      }
    }
    if (req.method === "GET" && p.startsWith("/api/cohort/")) {
      const runId = decodeURIComponent(p.slice("/api/cohort/".length));
      try {
        const data = await readFile(path.join(RUNS_DIR, runId, "matched_cohort.csv"));
        res.writeHead(200, { "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": `attachment; filename="matched_cohort_${runId}.csv"` });
        return res.end(data);
      } catch {
        return send(res, 404, { error: "找不到该运行的队列" });
      }
    }

    if (req.method === "POST" && p === "/api/data") {
      const body = JSON.parse(await readBody(req) || "{}");
      const parsed = parseTable(body.text ?? "");
      if (!parsed.format) return send(res, 400, { error: parsed.errors.join("；") });
      state.data = { text: body.text ?? "", format: parsed.format, columns: parsed.columns, rowCount: parsed.rows.length };
      return send(res, 200, { ok: true, format: parsed.format, rowCount: parsed.rows.length, columns: parsed.columns, errors: parsed.errors });
    }
    if (req.method === "POST" && p === "/api/config") {
      if (!state.data) return send(res, 400, { error: "请先导入数据" });
      const body = JSON.parse(await readBody(req) || "{}");
      state.config = {
        id_col: body.id_col || null,
        treat_col: body.treat_col,
        treat_value: body.treat_value,
        cov_cols: body.cov_cols ?? [],
        outcome_col: body.outcome_col || null,
        user_col: body.user_col || null,
        binary: body.binary !== false,
        B: Math.min(1000, Math.max(0, Number(body.B) || 200)),
        N_perm: Math.min(1000, Math.max(0, Number(body.N_perm) || 200)),
      };
      const errs = validateConfig(state.config, state.data.columns);
      return send(res, 200, { ok: true, config: state.config, errors: errs });
    }
    if (req.method === "POST" && p === "/api/run") {
      const body = JSON.parse(await readBody(req) || "{}");
      const result = await handleRun(body);
      return send(res, 200, result);
    }
    if (req.method === "POST" && p === "/api/selfcheck") {
      const output = await runPython(["selfcheck.py"]);
      return send(res, 200, { output });
    }
    if (req.method === "POST" && p === "/api/reset") {
      state.data = null;
      state.config = null;
      state.lastRunId = null;
      return send(res, 200, { ok: true });
    }

    if (req.method === "GET") return serveStatic(res, p);
    return send(res, 404, { error: "未知接口" });
  } catch (err) {
    const code = err?.status ?? 500;
    return send(res, code, { error: String(err?.message ?? err) });
  }
}

const server = http.createServer(handle);
server.listen(PORT, "127.0.0.1", () => {
  console.log(`Agent 效果对比工具已启动：http://localhost:${PORT}`);
});

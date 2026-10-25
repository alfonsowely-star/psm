const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmt(v) {
  return (v == null || (typeof v === "number" && isNaN(v))) ? "—" : Number(v).toFixed(4);
}

let columns = [];
let currentRunId = null;
let lastConfig = null;

function showStep(n) {
  ["s2", "s3", "s4"].forEach((id, i) => {
    document.getElementById(id).classList.toggle("hidden", i + 1 !== n);
  });
  $$(".step").forEach((el, i) => {
    el.classList.toggle("active", i + 1 === n);
    el.classList.toggle("done", i + 1 < n);
  });
}

// 步骤可点击返回（带守卫：没数据不能进映射，没结果不能进结果页）
$$(".step").forEach((el) => el.addEventListener("click", () => {
  const n = Number(el.dataset.goto);
  if (n === 2 && !columns.length) return;
  if (n === 3 && !currentRunId) return;
  if (n === 2) populateMapping();
  showStep(n);
}));

// 结果页返回修改映射
$("#btn-back-edit").addEventListener("click", () => { populateMapping(); showStep(2); });

// ① 导入数据（自动解析）
async function parseData() {
  const text = $("#data-text").value;
  if (!text.trim()) { $("#parse-result").textContent = "请先粘贴或选择数据"; return; }
  const res = await fetch("/api/data", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  const j = await res.json();
  if (!res.ok) { $("#parse-result").textContent = "解析失败：" + (j.error || "未知错误"); return; }
  columns = j.columns || [];
  $("#parse-result").textContent = `已解析 ${j.rowCount} 行 · ${columns.length} 列（${j.format}）` + (j.errors?.length ? ` · ${j.errors.length} 条坏行已跳过` : "");
  const rows = columns.map((c) => `<tr><td>${esc(c.name)}</td><td>${esc(c.type)}</td><td class="num">${c.uniqueCount}</td><td>${esc((c.sampleValues || []).join(", "))}</td></tr>`).join("");
  $("#columns-view").innerHTML = `<table class="data"><tr><th>列名</th><th>类型</th><th>去重数</th><th>示例值</th></tr>${rows}</table>`;
  $("#btn-s2").classList.remove("hidden");
}

$("#file-input").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (f) {
    $("#data-text").value = await f.text();
    parseData();
  }
});

let parseTimer = null;
$("#data-text").addEventListener("input", () => {
  clearTimeout(parseTimer);
  parseTimer = setTimeout(parseData, 400);
});

$("#btn-parse").addEventListener("click", parseData);

$("#btn-s2").addEventListener("click", () => { populateMapping(); showStep(2); });

// ② 映射列
function toggleEffectFields() {
  $("#effect-fields").classList.toggle("hidden", !$("#c-effect").checked);
}

function populateMapping() {
  const opts = ['<option value=""></option>'].concat(columns.map((c) => `<option value="${esc(c.name)}">${esc(c.name)}</option>`)).join("");
  $("#c-id").innerHTML = opts;
  $("#c-treat").innerHTML = opts;
  $("#c-outcome").innerHTML = opts;
  $("#c-user").innerHTML = opts;
  $("#cov-checks").innerHTML = columns.map((c) => `<label class="check"><input type="checkbox" value="${esc(c.name)}"> ${esc(c.name)} <span class="hint">(${esc(c.type)})</span></label>`).join("");
  // 恢复上次的映射选择
  if (lastConfig) {
    $("#c-id").value = lastConfig.id_col || "";
    $("#c-treat").value = lastConfig.treat_col || "";
    $("#c-treatval").value = lastConfig.treat_value ?? "";
    $("#c-outcome").value = lastConfig.outcome_col || "";
    $("#c-user").value = lastConfig.user_col || "";
    $("#c-effect").checked = Boolean(lastConfig.outcome_col);
    if (lastConfig.binary !== undefined) $("#c-binary").value = lastConfig.binary ? "1" : "0";
    $$("#cov-checks input").forEach((cb) => { cb.checked = (lastConfig.cov_cols || []).includes(cb.value); });
  }
  toggleEffectFields();
}
$("#c-effect").addEventListener("change", toggleEffectFields);

$("#btn-run").addEventListener("click", async () => {
  const config = {
    id_col: $("#c-id").value || null,
    treat_col: $("#c-treat").value,
    treat_value: $("#c-treatval").value.trim(),
    cov_cols: [...$$("#cov-checks input:checked")].map((i) => i.value),
  };
  if ($("#c-effect").checked) {
    config.outcome_col = $("#c-outcome").value || null;
    config.user_col = $("#c-user").value || null;
    config.binary = $("#c-binary").value === "1";
  }
  lastConfig = config;
  const cRes = await fetch("/api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config) });
  const cj = await cRes.json();
  if (cj.errors?.length) { $("#run-status").textContent = "配置有误：" + cj.errors.join("；"); return; }
  $("#run-status").textContent = "配对中…";
  const rRes = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const rj = await rRes.json();
  if (!rRes.ok) { $("#run-status").textContent = "运行失败：" + (rj.error || "未知错误"); return; }
  $("#run-status").textContent = "完成 ✓";
  currentRunId = rj.runId;
  renderSummary(rj.manifest);
  $("#report-frame").src = "/api/view/" + rj.runId;
  showStep(3);
  loadRuns();
});

function renderSummary(m) {
  const b = m.balance || {};
  const badge = b.balanced ? '<span class="badge badge-success">两组可比 ✓</span>' : '<span class="badge badge-error">不可比 ✗</span>';
  if (m.effect) {
    $("#report-summary").innerHTML = `<div class="form-grid">
      <div><div class="hint">结局差异（新 − 老）</div><strong>${fmt(m.effect.att)}</strong></div>
      <div><div class="hint">新 agent 队结局均值</div>${fmt(m.effect.mean_treated)}</div>
      <div><div class="hint">老 agent 队结局均值</div>${fmt(m.effect.mean_control)}</div>
      <div><div class="hint">两组是否可比</div>${badge}（差异度 ${fmt(b.max_smd_after)}）</div>
    </div>`;
  } else {
    const dl = currentRunId ? `<a class="btn btn-ghost" href="/api/cohort/${currentRunId}">下载配对结果 CSV</a>` : "";
    $("#report-summary").innerHTML = `<div class="form-grid">
      <div><div class="hint">配对结果</div>新 agent ${m.n_treated} 条 ↔ 老 agent ${m.n_control} 条，配成 <strong>${m.n_matched}</strong> 对</div>
      <div><div class="hint">两组是否可比</div>${badge}（差异度 ${fmt(b.max_smd_after)}）</div>
    </div>${dl}`;
  }
}

// 新手引导
$("#btn-guide").addEventListener("click", () => {
  $("#guide-box").classList.toggle("hidden");
});

// 重新开始
function resetAll() {
  currentRunId = null;
  lastConfig = null;
  columns = [];
  $("#data-text").value = "";
  $("#parse-result").textContent = "";
  $("#columns-view").innerHTML = "";
  $("#btn-s2").classList.add("hidden");
  $("#run-status").textContent = "";
  $("#report-summary").innerHTML = "";
  $("#report-frame").src = "";
  ["c-id", "c-treat", "c-outcome", "c-user"].forEach((id) => { $("#" + id).innerHTML = ""; });
  $("#cov-checks").innerHTML = "";
  $("#c-treatval").value = "";
  $("#c-effect").checked = false;
  $("#effect-fields").classList.add("hidden");
  $("#c-binary").value = "1";
  showStep(1);
}
$("#btn-restart").addEventListener("click", async () => {
  await fetch("/api/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  resetAll();
});

// 引擎自检
$("#btn-selfcheck").addEventListener("click", async () => {
  const box = $("#selfcheck-box");
  box.classList.remove("hidden");
  $("#selfcheck-out").textContent = "自检中（约 10 秒）…";
  const res = await fetch("/api/selfcheck", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const j = await res.json();
  $("#selfcheck-out").textContent = j.output || j.error || "自检失败";
  box.scrollIntoView();
});

// 历史运行
async function loadRuns() {
  const res = await fetch("/api/runs");
  const j = await res.json();
  $("#runs-list").innerHTML = (j.runs || []).map((r) =>
    `<li><a href="#" data-run="${esc(r.runId)}">${esc(r.runId)}</a> <span class="hint">${r.effect ? '效果分析' : `配成 ${r.n_matched} 对`} · ${r.balance?.balanced ? "两组可比✓" : "不可比✗"}</span></li>`
  ).join("");
  $$("#runs-list a").forEach((a) => a.addEventListener("click", async (e) => {
    e.preventDefault();
    const runId = a.dataset.run;
    currentRunId = runId;
    $("#report-frame").src = "/api/view/" + runId;
    showStep(3);
    const res = await fetch("/api/report/" + runId);
    const j = await res.json();
    if (j.reportData) {
      const b = j.reportData.balance_summary || {};
      const badge = b.balanced ? '<span class="badge badge-success">两组可比 ✓</span>' : '<span class="badge badge-error">不可比 ✗</span>';
      if (j.reportData.effect) {
        $("#report-summary").innerHTML = `<div class="form-grid">
          <div><div class="hint">结局差异（新 − 老）</div><strong>${fmt(j.reportData.effect.att)}</strong></div>
          <div><div class="hint">新 agent 队结局均值</div>${fmt(j.reportData.effect.mean_treated)}</div>
          <div><div class="hint">老 agent 队结局均值</div>${fmt(j.reportData.effect.mean_control)}</div>
          <div><div class="hint">两组是否可比</div>${badge}（差异度 ${fmt(b.max_smd_after)}）</div>
        </div>`;
      } else {
        $("#report-summary").innerHTML = `<div class="form-grid">
          <div><div class="hint">配对结果</div>配成 <strong>${j.reportData.n_matched}</strong> 对</div>
          <div><div class="hint">两组是否可比</div>${badge}（差异度 ${fmt(b.max_smd_after)}）</div>
        </div><a class="btn btn-ghost" href="/api/cohort/${runId}">下载配对结果 CSV</a>`;
      }
    }
  }));
}

showStep(1);
loadRuns();

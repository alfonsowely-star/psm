/**
 * 数据解析与列类型推断（CSV / JSONL）。坏行跳过并记账，不整批失败。
 */

export function parseJsonl(text) {
  const rows = [];
  const errors = [];
  const lines = String(text ?? "").split(/\r?\n/);
  lines.forEach((line, i) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    try {
      const obj = JSON.parse(trimmed);
      if (obj && typeof obj === "object" && !Array.isArray(obj)) rows.push(obj);
      else errors.push(`第 ${i + 1} 行不是对象`);
    } catch (e) {
      errors.push(`第 ${i + 1} 行 JSON 解析失败：${e.message}`);
    }
  });
  return { rows, errors };
}

function parseCsvLine(line) {
  const out = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inQuotes) {
      if (c === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++; }
        else inQuotes = false;
      } else cur += c;
    } else {
      if (c === '"') inQuotes = true;
      else if (c === ",") { out.push(cur); cur = ""; }
      else cur += c;
    }
  }
  out.push(cur);
  return out;
}

export function parseCsv(text) {
  const rows = [];
  const errors = [];
  const lines = String(text ?? "").split(/\r?\n/);
  let headerLine = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim()) { headerLine = i; break; }
  }
  if (headerLine < 0) return { rows, errors: ["数据为空"] };
  const header = parseCsvLine(lines[headerLine]);
  if (header.length === 0) return { rows, errors: ["表头为空"] };
  for (let i = headerLine + 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    const cells = parseCsvLine(line);
    if (cells.length !== header.length) {
      errors.push(`第 ${i + 1} 行列数 ${cells.length} 与表头 ${header.length} 不一致，已跳过`);
      continue;
    }
    const obj = {};
    header.forEach((h, j) => { obj[h] = cells[j]; });
    rows.push(obj);
  }
  return { rows, errors };
}

function inferType(values) {
  const nonNull = values.filter((v) => v !== "" && v !== null && v !== undefined);
  if (nonNull.length === 0) return "empty";
  const allNumeric = nonNull.every((v) => !Number.isNaN(Number(v)));
  if (allNumeric) return new Set(nonNull).size <= 2 ? "binary" : "numeric";
  if (nonNull.every((v) => !Number.isNaN(Date.parse(v)))) return "time";
  return "categorical";
}

export function inferColumns(rows) {
  if (!rows.length) return [];
  const names = Object.keys(rows[0]);
  return names.map((name) => {
    const values = rows.map((r) => r[name]);
    const nonNull = values.filter((v) => v !== "" && v !== null && v !== undefined);
    const unique = [...new Set(nonNull)];
    return {
      name,
      type: inferType(values),
      sampleValues: unique.slice(0, 5),
      nullCount: values.length - nonNull.length,
      uniqueCount: unique.length,
    };
  });
}

export function parseTable(text) {
  const trimmed = String(text ?? "").trimStart();
  if (!trimmed) return { format: null, rows: [], columns: [], errors: ["数据为空"] };
  if (trimmed.startsWith("{")) {
    const { rows, errors } = parseJsonl(text);
    return { format: "jsonl", rows, columns: inferColumns(rows), errors };
  }
  const { rows, errors } = parseCsv(text);
  return { format: "csv", rows, columns: inferColumns(rows), errors };
}

export default { parseTable, inferColumns, parseCsv, parseJsonl };

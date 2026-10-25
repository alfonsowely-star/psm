import { test } from "node:test";
import assert from "node:assert";
import { parseCsv, parseJsonl, parseTable, inferColumns } from "../src/data.mjs";

test("parseCsv 解析基础 CSV", () => {
  const { rows, errors } = parseCsv("a,b\n1,2\n3,4");
  assert.equal(rows.length, 2);
  assert.deepEqual(rows[0], { a: "1", b: "2" });
  assert.equal(errors.length, 0);
});

test("parseCsv 处理引号内的逗号", () => {
  const { rows } = parseCsv('id,txt\n1,"a,b"\n2,"c"');
  assert.deepEqual(rows[0], { id: "1", txt: "a,b" });
});

test("parseCsv 列数不一致跳过并记账", () => {
  const { rows, errors } = parseCsv("a,b\n1,2\n3\n4,5");
  assert.equal(rows.length, 2);
  assert.equal(errors.length, 1);
});

test("parseJsonl 解析 JSONL", () => {
  const { rows } = parseJsonl('{"id":"1","x":2}\n{"id":"2","x":3}');
  assert.equal(rows.length, 2);
  assert.deepEqual(rows[1], { id: "2", x: 3 });
});

test("inferColumns 推断类型", () => {
  const rows = [
    { a: "1", b: "x", c: "3.5" },
    { a: "0", b: "y", c: "4.2" },
    { a: "1", b: "x", c: "5" },
  ];
  const cols = inferColumns(rows);
  const byName = Object.fromEntries(cols.map((c) => [c.name, c]));
  assert.equal(byName.a.type, "binary");
  assert.equal(byName.b.type, "categorical");
  assert.equal(byName.c.type, "numeric");
});

test("parseTable 探测 CSV 与 JSONL", () => {
  assert.equal(parseTable("a,b\n1,2").format, "csv");
  assert.equal(parseTable('{"a":1}').format, "jsonl");
});

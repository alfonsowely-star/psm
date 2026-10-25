---
name: agent-psm
description: Agent 配平工具。在非随机分流（定向灰度）下，把「新 agent 处理的进线」和「老 agent 处理的进线」按维度配成可比的两队，输出谁配谁 + 两组是否可比。用户要比较新老 agent、或要找「可比的两拨人」时使用。
---

# Agent 配平（PSM）

本地工具：输入实例 id + 处理方（新/老）+ 维度，输出「配平后的两队」（谁配谁）+ 两组在维度上是否可比。

## 原理

新 agent 不是随机上线的，先上新的人和老 agent 那批人本就不一样。工具用 Mahalanobis 距离匹配，给每条「新 agent 进线」配一个「其他维度最像」的老 agent 进线，配完后两队可比。

## 启动

```bash
cd D:\CCing\agent-psm
npm start
```

打开 http://localhost:5175 。三步：①导入数据 → ②映射列 → ③结果。

## 数据格式（一行 = 一条进线）

| 列 | 必需 | 说明 |
|---|---|---|
| session_id / user_id | 建议 | 实例 id（配对标识） |
| agent | **必需** | 灰度分组：被分到新 agent=1 / 老 agent=0（填「是否被分到灰度组」，不要填「实际谁处理」） |
| member_level 等 | 维度 | 进线时就确定的特征 |

三条铁律：① agent（处理方）唯一不可缺；② 「新 agent」填「是否被分到灰度组」（可以触发），不要填「实际谁处理」（触发过）——按实际处理算会因转人工产生幸存者偏差；③ 维度只能放「进线时就已知」的特征。

## 取数 SQL 模板

```sql
SELECT
  session_id,
  IF(routed_agent = 'new_agent', 1, 0) AS agent,   -- 处理方：新=1 / 老=0
  member_level,
  prev_same_intent_effective AS prev_effective,
  intent_type
FROM your_service_table
WHERE ts >= '2026-10-01' AND ts < '2026-10-21'
```

导出 CSV 丢进工具即可。

## 两条使用路径

### 路径 A：UI（浏览器）
`npm start` 后按三步走。

### 路径 B：headless（命令行）
```bash
cd D:\CCing\agent-psm\python
python -B analyze.py --data ../examples/sample.csv --config ../examples/config.json --outdir ../runs/demo
```
产出 `report.html` / `matched_cohort.csv` / `report.json` / `manifest.json`。

## 结果怎么读

- **两组是否可比**：配平后最大差异度 < 0.1 即可比，是结果可信度的根基。
- **各维度的分布对比**：配平前/后直方图，配平后应基本重合。
- **配对关系**：完整配对在 matched_cohort.csv。

## 引擎自检

```bash
cd D:\CCing\agent-psm\python
python -B selfcheck.py
```

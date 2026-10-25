# Agent 配平工具（PSM）

在非随机分流（定向灰度）下，把「新 agent 处理的进线」和「老 agent 处理的进线」按维度配成**可比的两队**，输出谁配谁 + 两组在维度上是否可比。

- **UI**：Node 零框架（原生 http + 单页前端），端口 5175。
- **引擎**：Python（numpy / pandas / scipy / scikit-learn）。

## 原理

新 agent 定向灰度上线，先上新的人和老 agent 那批人本就不一样。工具用 **Mahalanobis 距离匹配**，给每条「新 agent 进线」配一个「其他维度最像」的老 agent 进线，配完后两队可比——再拿这两队比任何结果才公平。

## 快速开始

依赖：Node ≥22、Python 3（numpy / pandas / scipy / scikit-learn）。

```bash
pip install numpy pandas scipy scikit-learn
npm start
# 浏览器打开 http://localhost:5175
```

三步：①导入数据 → ②映射列（实例 / 处理方 / 维度）→ ③看结果。

## 数据格式

一行 = 一条进线。必需列：处理方 `agent`；建议列：实例 id（session_id / user_id）；维度（协变量）。示例见 `examples/sample.csv`。详见 [docs/GUIDE.md](docs/GUIDE.md)。

## 目录结构

```
agent-psm/
├── package.json          # 零依赖 Node
├── src/                  # server.mjs / data.mjs / store.mjs
├── web/                  # index.html / style.css / app.js
├── python/
│   ├── psm.py            # 匹配引擎（Mahalanobis 匹配 + 配平检查）
│   ├── analyze.py        # CLI + 报告渲染
│   ├── selfcheck.py      # 快速引擎自检
│   ├── test_psm.py       # 效应估计的黄金自检（保留备用）
│   └── make_example.py   # 生成示例数据
├── examples/             # sample.csv + config.json
├── docs/GUIDE.md         # 新手引导
├── skill/SKILL.md        # Claude skill
├── DESIGN.md             # UI 设计规范
└── tests/                # Node 测试
```

## 报告输出

每次运行写入 `runs/<runId>/`：

- `report.html` —— 配平后的两队 + 各维度分布对比 + 可比性判定。
- `matched_cohort.jsonl/.csv` —— 完整配对关系（谁配谁）。
- `report.json` / `manifest.json`。

## 测试

```bash
npm test                        # Node 侧（数据解析 / 列类型推断）
cd python && python -B selfcheck.py   # 匹配引擎自检
```

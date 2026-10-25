# Agent-PSM 统计实现合理性审查报告

- **审查对象**：`agent-psm`（客服对话 Agent 效果对比工具，PSM 因果配平）
- **审查范围**：`python/psm.py`、`python/analyze.py`、`python/selfcheck.py`、`python/test_psm.py`、`python/make_example.py`、`src/server.mjs`、`src/data.mjs`、`src/store.mjs`、`PRD.md`、`README.md`
- **审查视角**：数据科学 / 因果推断方法正确性
- **运行环境**：Anaconda Python 3.8.3 + numpy 1.18.5 / pandas 1.0.5 / scipy 1.5.0 / sklearn 0.23.1
- **审查日期**：2026-10-25
- **结论一句话**：方法论框架专业、点估计公式在理想设定下正确（黄金自检通过），但存在 **2 个会直接改变结果的硬伤**、**1 个核心功能未接线的工程缺口**，以及若干健壮性问题。**当前版本不建议直接用于真实数据下结论。**

---

## 一、总体评价

该工具的目标是在「新 Agent 定向灰度、流量非随机」的观测数据上，用 PSM/IPTW/匹配等方法估计新 Agent 相对老 Agent 的因果效应 ATT，并给出配平诊断、证伪、敏感性与功效分析。

- **方法论选型专业且正确**：倾向得分 + 配平诊断（SMD/VR/ESS/overlap）+ 三法对拍（稳定 IPTW / 双重稳健 AIPW / Mahalanobis 匹配）+ user 层 cluster bootstrap + 置换检验 + E-value + MDE，覆盖了一份严谨观察性因果分析应有的主要环节。
- **大部分公式实现正确**，自带的模拟数据黄金自检（`test_psm.py`）能还原已知真效应、并正确暴露朴素对比的混杂偏差。
- **但关键实现存在已实测确认的错误**，且最有价值的「效应估计」主流程未接入产品，用户当前通过 Web/CLI 实际只能拿到「配平 + 谁配谁」，拿不到「新 Agent 到底好多少、这个数可不可信」。

---

## 二、做对的部分（可信赖）

| 环节 | 位置 | 评价 |
|---|---|---|
| ATT 权重 | `att_weights` | treated=1、control=e/(1−e)，是标准 **ATT** 权重（非 ATE）；仅对 control 侧做 99% 分位截断，方向正确 |
| 稳定 IPTW | `att_ipw` | Hájek 加权均值，ATT = 加权 treated 均值 − 加权 control 均值，正确 |
| 双重稳健 AIPW | `att_dr` | 影响函数 ψ = (Y−m0)·[T−(1−T)w]，经手工推导核对无误；结局模型在 control 组拟合 m0(X)，符合 ATT 口径 |
| 倾向模型 | `fit_propensity` | 逻辑回归 + AUC + 十分位校准，正确 |
| 配平口径 | `balance_table` | 在**加权后样本**上评估配平（符合 PRD 红线 1）；**不使用 t 检验 p 值判配平**（符合红线 2） |
| 有效样本量 | `ess` | ESS = (Σw)²/Σw²，正确 |
| E-value | `evalue` | 风险比 → RR+√(RR(RR−1))，VanderWeele & Ding 公式正确，含保护效应方向处理 |
| MDE | `mde_binary` | 两比例检验 z 系数（z_{0.975}+z_{0.8}）公式正确，以 ESS 折算样本量 |
| 置换检验 | `permutation_test` | 在 user 层打乱标签、且每次重拟合倾向模型（随机化推断的正确做法） |
| 朴素对照 | `naive_difference` | 同时展示未配平均值差，直观暴露混杂偏差，是好的设计 |

**黄金自检结果**（`test_psm.py`，n=6000）：

| 指标 | 数值 |
|---|---|
| 真实 ATT（风险差） | −0.0089 |
| 朴素差 naive | **+0.1036**（被混杂带偏，方向反转） |
| IPTW | −0.0146 |
| DR | −0.0158 |
| 匹配 | −0.0009 |
| IPW 95% CI | [−0.0289, +0.0005]（含 0） |
| 配平 max\|SMD\| | 0.753 → 0.011 |
| ESS / 置换 p / MDE | 3953 / 0.195 / 0.0392 |

点估计在「模型正确设定」下能还原真值并纠正混杂，Monte Carlo（15 seeds）IPW 平均偏差 +0.0012，通过。

---

## 三、必须修复的硬伤（P0，已实测确认）

### P0-1 Mahalanobis 匹配的白化变换用错三角因子

**位置**：`python/psm.py:325-335`（`match_pairs`）

```python
S = np.cov(Xc, rowvar=False) + np.eye(Xc.shape[1]) * 1e-6
L = np.linalg.cholesky(np.linalg.inv(S))   # L 为下三角，L·Lᵀ = S⁻¹
Zc = Xc @ L.T      # ❗ 错误
Zt = X[treated_idx] @ L.T
```

行向量 x 变换为 z = x·A 时，要求 ‖zᵢ−zⱼ‖² = Δx·A·Aᵀ·Δxᵀ = Δx·S⁻¹·Δxᵀ，即需 A·Aᵀ = S⁻¹，故应取 **A = L**（即 `Z = X @ L`）；代码取 A = Lᵀ，此时 A·Aᵀ = Lᵀ·L ≠ L·Lᵀ = S⁻¹，距离不是马氏距离。

**实测证据**（相关系数 0.9、尺度不同的二维连续协变量，400 对照 / 60 处理）：

| 方法 | 与 scipy 标准马氏最近邻一致率 |
|---|---|
| 代码现状（`X @ L.T`） | **41.7%**（即 58.3% 的 treated 配错对象） |
| 修正为（`X @ L`） | **100%** |

**影响**：`matching` 效应估计与导出的「谁配谁」配对队列，在真实连续 / 强相关协变量下不可信。示例数据因是会员等级、0/1 这类弱相关离散变量（`L` 近似对角），自检未能暴露。

**修法**：

```python
Zc = Xc @ L
Zt = X[treated_idx] @ L
```

更稳妥的做法是先对连续变量标准化 / rank 变换，再计算协方差，并对 one-hot 与连续混合导致的病态矩阵给出更充分的正则。

### P0-2 cluster bootstrap 未按抽中次数复制用户

**位置**：`python/psm.py:378-381`（`cluster_bootstrap`）

```python
sampled = rng.choice(groups, size=len(groups), replace=True)
mask = np.isin(g, sampled)   # ❗ 只标记“是否被抽中”，丢失重复次数
d = df[mask]
```

标准 cluster bootstrap 中，某用户被抽中 k 次，其数据应在 bootstrap 样本中出现 k 次；`np.isin` 只返回布尔标记，重复抽中不复制。

**实测证据**（5 个用户、总行数 10，3000 次重采样）：

| 做法 | 重采样后平均总行数 |
|---|---|
| 标准 cluster bootstrap | 10.07（应 ≈ 原始 10） |
| 代码 `np.isin` 做法 | **6.78（约 68%，等价于随机砍掉约 1/3 用户且无重复）** |

**影响**：IPW / DR / 匹配三法的 cluster-robust 95% CI 都不是正确的用户层 bootstrap，FR-8 名不副实。示例数据每用户仅 1–3 条会话、用户数多，集群效应弱，CI 碰巧覆盖真值，故未被测试发现。

**修法**：按抽中顺序拼接用户行（抽几次拼几次），或等价地用计数权重：

```python
parts = [df[g == gu] for gu in sampled]
d = pd.concat(parts, ignore_index=True)
```

---

## 四、会崩溃 / 误导 / 未接线（P1）

### P1-1 协变量缺失直接崩溃，且缺失率被硬编码为 0

- **位置**：`run_analysis` 调 `encode_covariates`（`psm.py:477`）；`balance_table` 中 `"missing": 0`（`psm.py:169`）。
- **实测**：协变量注入 80/2000 缺失后，`run_analysis` 直接抛 `ValueError: Input contains NaN, infinity or a value too large for dtype('float64')`；分类变量缺失则被 `pd.get_dummies` 静默吞为全 0。
- **违背**：PRD FR-1/FR-11 要求的缺失率报告与坏数据优雅处理。
- **修法**：连续变量中位数插补、分类变量众数插补或 `get_dummies(..., dummy_na=True)`，剔除样本需记账并在报告中列缺失率。

### P1-2 效应估计主流程未接入产品（最大工程缺口）

- `python/analyze.py:225` 只调用 `psm.run_matching()`（纯配平）；`src/server.mjs:166-171` 的 `/api/config` 仅保存 `id_col / treat_col / treat_value / cov_cols`，**不接收 `outcome_col / user_col / binary / B / N_perm`**。
- 结果：Web/CLI 输出的 `report.html` 只有「配平 + 配对关系 + 分布对比」，**完全没有** IPW/DR/匹配三法效应、CI、三法对拍告警、置换检验、E-value、MDE、权重诊断 ESS、overlap 诊断。
- `psm.py` 中约一半代码（`run_analysis` 及其调用的完整推断链）仅在 `test_psm.py` 中被运行，属于**已实现但未接线的「死代码」**。PRD 最核心的 FR-6 / FR-7 / FR-8 / FR-9 / FR-12 对用户不可用。
- **修法**：为 `analyze.py` 增加 `run_analysis` 分支（根据是否提供 outcome 列自动选择）；扩展 config 字段；在报告中补「效应卡片 + 三法对拍 + CI + 置换零分布 + E-value + MDE + overlap/ESS」。

### P1-3 同一用户跨 treated/control 时置换检验静默错误

- **位置**：`psm.py:408` `treat_by_group[gi] = t0[g == gi][0]`，只取该用户第一行的分组。
- **实测**：用户 uA 三行会话标签为 [1,0,0]、uB 为 [0,1]，代码将 uA 整体记为 treated、uB 整体记为 control，其余行归属被忽略。
- 真实客服中同一用户多次进线、被不同 Agent 接很常见。
- **修法**：先校验每个 user 分组是否唯一（SUTVA），不唯一则改为按 session 置换并在报告中显式告警降级。

---

## 五、方法与稳健性问题（P2，建议改进）

1. **匹配退化却发「完美配平证书」**：示例协变量仅 member_level(1–5)×prev_effective(0/1) 共 10 个格子，3407 个 treated 只匹配到 **10 个不同 control**（有放回反复使用），报告却显示 SMD=0、「两组可比」。有效对照样本极少、方差被严重低估，证书具有误导性。建议：报告匹配频次与对照组有效样本数、提供无放回匹配 / 卡尺（caliper）选项、对 distinct 对照过少强告警。
2. **匹配距离未处理量纲**：`match_pairs` 直接用 one-hot 与连续变量的原始尺度求协方差；对照组缺某类别时矩阵奇异，fallback 到单位阵会退化为未标准化欧氏距离（`psm.py:324-329`）。建议先标准化。
3. **加权 SMD 分母用加权方差**（`psm.py:136-143`），与 Austin 推荐的「未加权 pooled SD」惯例不一致，0.1 阈值的判定口径会产生偏移。
4. **倾向 / 结局模型未标准化连续变量**：L2 罚对量纲敏感（不影响 AUC/预测概率，但影响系数与 OR 的可解释性、极端量纲下收敛）。
5. **DR 使用截断权重**：99% 截断后严格双重稳健性被破坏（属 bias-variance 实用折中），应在报告中注明。
6. **置换检验的解释边界**：观测数据下 treatment 非随机分配，置换 p 值没有严格的随机化推断解释，只能作为「方法没坏」的 sanity check（PRD 已诚实说明，但报告需明确标注，避免被当正式 p 值）。
7. **敏感性 / 功效不完整**：E-value 仅给点估计，未给 CI 对应的 E-value；MDE 仅实现二值结局，连续结局缺失。
8. **类型推断简化**：会员等级等有序变量被当作连续变量；引擎未做时间类型与时间混杂检测（FR-10 未实现）。

---

## 六、自检为什么没抓到这些问题

`test_psm.py` 虽通过，但验证力有限：

1. **模拟设定过于理想化**：倾向模型与结局模型使用的是同一批已纳入协变量、且函数形式与引擎完全一致（logistic），无未观测混杂、无缺失、按 user 一致分组。这只能验证「零设定错误」下的代码正确性，恰好绕开上述全部缺陷。
2. **断言阈值过宽**：效应真值仅 −0.009，三法点估计从 −0.0009 到 −0.0158、最大分歧（约 0.015）已超过效应本身，仍因容差 0.02–0.03 判通过；CI 仅做单次「真值是否落在区间内」断言，几乎必然通过，无法识别 bootstrap 偏差。
3. **真正的黄金自检被边缘化**：`npm test` 只跑 Node 侧解析测试；界面「引擎自检」按钮调用的 `selfcheck.py` 只验证最容易达标的配平 SMD；能还原效应的 `test_psm.py` 被标为「保留备用」，未纳入常规校验。

建议强化自检：加入强相关连续协变量、协变量缺失、同一用户跨分组、协方差矩阵退化等场景，并对 CI 做 Monte Carlo 覆盖率断言（而非单次覆盖），对三法对拍设置相对分歧阈值。

---

## 七、PRD 功能缺口（已规划未实现）

| PRD 项 | 状态 |
|---|---|
| FR-0 目标试验声明 | 未实现（前端流程中无） |
| FR-5 ATO 权重 / overlap 交互截断 | 仅做 99% 权重截断，未提供 ATO |
| FR-6 三法对拍 + 不一致告警 | 引擎已实现，**未接入报告** |
| FR-7 负对照结局 | 未实现（置换检验已实现） |
| FR-8 cluster-robust 推断 | 已实现但**算法有误**（见 P0-2） |
| FR-9 MDE / 功效 | 二值结局已实现，未接入报告 |
| FR-10 时间混杂检测 | 未实现 |
| FR-11 结局缺失率 | 结局缺失有处理；协变量缺失会崩溃 |
| FR-12 完整 HTML 报告 | 仅渲染配平部分，效应/证伪/敏感性缺失 |
| FR-14 引擎自检 | 仅配平自检，效应黄金自检未挂接 |

---

## 八、修复优先级建议

| 优先级 | 事项 | 工作量 |
|---|---|---|
| **P0** | 修正马氏白化 `X@L.T` → `X@L` | 极小（1 行） |
| **P0** | 修正 cluster bootstrap，按用户计数复制 | 小（数行） |
| **P1** | 协变量缺失插补 / 剔除 + 缺失率报告 | 中 |
| **P1** | 把 `run_analysis` 接进 `analyze.py` 与前端，报告输出效应与证据链 | 中大（核心价值） |
| **P1** | 置换检验前校验 SUTVA，跨组用户按 session 处理并告警 | 小 |
| **P2** | 匹配量纲标准化、卡尺 / 无放回选项、对照有效样本告警 | 中 |
| **P2** | 加权 SMD 分母改用未加权 pooled SD；模型标准化；报告标注截断与置换检验边界 | 中 |
| **P2** | 强化黄金自检（强相关 / 缺失 / 跨组 / CI 覆盖率断言）并挂接为常规测试 | 中 |

> 注：本次审查仅做只读分析与在系统临时目录中的数值验证（验证脚本已删除），未改动项目任何现有文件。

---

## 附录：关键实测复现要点

- **马氏距离**：构造协方差 `[[4,3.6],[3.6,4]]`（ρ=0.9）的对照样本，以 scipy `cdist(metric='mahalanobis', VI=inv(S))` 为基准，比较 `X@L.T` 与 `X@L` 选出的最近邻。
- **cluster bootstrap**：5 用户、行分布 [3,1,2,1,3]，3000 次有放回重采样，比较 `np.isin` 保留行数与按计数拼接的期望行数。
- **缺失值**：用 `test_psm.simulate` 生成数据后对协变量随机注入 NaN，调用 `run_analysis` 观察异常。
- **黄金自检**：`python -B test_psm.py`（在 `python/` 目录）。

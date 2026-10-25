# -*- coding: utf-8 -*-
"""
make_testset.py —— 生成“客服新 Agent 定向灰度”测试数据集（含已知真效应，供 PSM 工具测试）。

设计要点：
  1. 定向灰度（非随机）：高等级、高频、历史有效、投诉意图的会话更易进新 Agent —— 制造强混杂。
  2. 真实因果效应已知且可检出：新 Agent 使“转人工率”下降约 4~6 个百分点（风险差 ATT）。
  3. 连续 + 强相关协变量：monthly_orders / history_complaints / wait_minutes，
     用于检验 Mahalanobis 匹配在连续变量下的表现（内置示例只有离散变量，测不出问题）。
  4. 用户聚类：同一用户多条进线，且带用户级随机效应（组内相关），检验 cluster bootstrap。
  5. 满意度 satisfied 约 30% 非响应（结局缺失），ts 为进线时间戳。

输出：examples/testset_agent.csv ；并打印真实 ATT、处理比例、重叠情况。
仅依赖 numpy / pandas。
"""
import os
import json
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(HERE, "testset_agent.csv")
OUT_CFG = os.path.join(HERE, "testset_config_full.json")

SEED = 20261025
N_USERS = 3600
TAU_LOGIT = -0.32          # 新 Agent 在 logit 尺度的真效应（负=降低转人工）

rng = np.random.default_rng(SEED)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def z(x):
    x = np.asarray(x, dtype=float)
    return (x - x.mean()) / (x.std() + 1e-9)


# ---------- 1) 用户层画像 ----------
member = rng.integers(1, 6, N_USERS)                       # 会员等级 1-5
log_orders = 0.42 * member + rng.normal(0, 0.55, N_USERS)  # 月订单数 与等级强相关
monthly_orders = np.round(np.exp(log_orders + 0.3), 1)
latent = rng.gamma(shape=1.3, scale=1.0, size=N_USERS)     # 潜在“高投诉体质”
history_complaints = rng.poisson(0.28 * latent + 0.04 * member)
u_effect = rng.normal(0, 0.55, N_USERS)                    # 用户级随机效应（影响转人工）

# 每用户 1-4 条进线
counts = rng.integers(1, 5, N_USERS)
user_idx = np.repeat(np.arange(N_USERS), counts)

# ---------- 2) 会话层 ----------
n = len(user_idx)
u_member = member[user_idx]
u_orders = monthly_orders[user_idx]
u_hist = history_complaints[user_idx]
u_eff = u_effect[user_idx]

intent = rng.choice(["complaint", "consult", "billing", "refund"], n,
                    p=[0.30, 0.35, 0.20, 0.15])
complaint = (intent == "complaint").astype(float)
refund = (intent == "refund").astype(float)

# 排队时长（进线时已确定，连续）：投诉/退款、高投诉体质排队更久
wait_log = (0.85 + 0.60 * complaint + 0.35 * refund
            + 0.22 * np.log1p(u_hist) + rng.normal(0, 0.38, n))
wait_minutes = np.clip(np.round(np.exp(wait_log), 1), 0.5, 30.0)

# 上一次进线是否有效（0/1）：高等级更有效
prev_eff_logit = -0.5 + 0.38 * u_member + rng.normal(0, 0.5, n)
prev_effective = rng.binomial(1, sigmoid(prev_eff_logit))

# ---------- 3) 定向灰度（处理分配，强混杂） ----------
logit_t = (
    -1.35
    + 0.55 * u_member
    + 0.30 * z(u_orders)
    + 0.45 * prev_effective
    + 0.60 * complaint
    + 0.06 * z(u_hist)
)
e_true = sigmoid(logit_t)
agent = rng.binomial(1, e_true)

# ---------- 4) 结局：转人工（二值），含真效应 ----------
logit0 = (
    -1.55
    + 0.25 * u_member
    + 0.30 * z(u_hist)
    + 1.05 * complaint
    + 0.55 * refund
    + 0.55 * z(wait_minutes)
    - 0.12 * z(u_orders)
    + u_eff
)
p0 = sigmoid(logit0)
p1 = sigmoid(logit0 + TAU_LOGIT)
transferred = rng.binomial(1, np.where(agent == 1, p1, p0))

# ---------- 5) 满意度（第二结局，约 30% 非响应） ----------
sat_logit = (0.15 - 0.55 * complaint - 0.20 * refund
             + 0.12 * u_member - 0.18 * z(wait_minutes)
             + 0.40 * agent)                              # 新 Agent 提升满意度
satisfied = rng.binomial(1, sigmoid(sat_logit)).astype(float)
miss = rng.random(n) < 0.30
satisfied[miss] = np.nan

# ---------- 6) 时间戳与 id ----------
base = pd.Timestamp("2026-09-01 08:00:00")
ts = base + pd.to_timedelta(rng.integers(0, 50 * 24 * 3600, n), unit="s")
session_id = np.array([f"s_{i:07d}" for i in range(n)])
user_id = np.array([f"u_{i:05d}" for i in user_idx])

df = pd.DataFrame({
    "session_id": session_id,
    "user_id": user_id,
    "ts": ts.strftime("%Y-%m-%dT%H:%M:%S"),
    "agent": agent,
    "member_level": u_member.astype(int),
    "monthly_orders": u_orders,
    "history_complaints": u_hist.astype(int),
    "intent": intent,
    "wait_minutes": wait_minutes,
    "prev_effective": prev_effective.astype(int),
    "transferred": transferred.astype(int),
    "satisfied": satisfied,
})

# ---------- 真实效应（基准答案） ----------
att_true_realized = float(np.mean((p1 - p0)[agent == 1]))      # 实际 treated 人群的真实风险差
base_rate_t = float(np.mean(p0[agent == 1]))                  # treated 若用老 Agent 的反事实转人工率
n_treated = int(agent.sum())
n_control = int(n - n_treated)
e_t, e_c = e_true[agent == 1], e_true[agent == 0]
oos = int(((agent == 1) & ((e_true < e_c.min()) | (e_true > e_c.max()))).sum())

df.to_csv(OUT_CSV, index=False, encoding="utf-8")

# 经典 PSM 效果分析配置（供 psm.run_matching_with_effect / CLI）
cfg = {
    "id_col": "session_id",
    "user_col": "user_id",
    "treat_col": "agent",
    "treat_value": 1,
    "outcome_col": "transferred",
    "cov_cols": ["member_level", "monthly_orders", "history_complaints",
                 "intent", "wait_minutes", "prev_effective"],
    "binary": True,
}
with open(OUT_CFG, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)

print("已生成:", OUT_CSV)
print("总行数 n =", n, " 用户数 =", N_USERS)
print("新 Agent(treated) =", n_treated, " 老 Agent(control) =", n_control,
      " 处理比例 = %.1f%%" % (100 * n_treated / n))
print("treated 反事实基准转人工率(全用老Agent) = %.4f" % base_rate_t)
print("真实 ATT 风险差(新-老, 仅 treated 人群) = %.4f  (约 %.1f 个百分点)"
      % (att_true_realized, 100 * att_true_realized))
print("朴素对比(未配平, 直接均值差) = %.4f  <- 预期被混杂明显高估"
      % float(df.loc[df.agent == 1, "transferred"].mean()
              - df.loc[df.agent == 0, "transferred"].mean()))
print("倾向得分范围: treated [%.3f, %.3f] / control [%.3f, %.3f]；treated 落在支撑域外 = %d"
      % (e_t.min(), e_t.max(), e_c.min(), e_c.max(), oos))
print("协变量相关系数(member~orders)=%.2f, (complaint~wait)=%.2f"
      % (np.corrcoef(u_member, u_orders)[0, 1],
         np.corrcoef(complaint, wait_minutes)[0, 1]))
print("satisfied 缺失率 = %.1f%%" % (100 * df.satisfied.isna().mean()))
print("已生成配置:", OUT_CFG)

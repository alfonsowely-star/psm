"""
模拟数据自检：合成含强混杂 + 已知真效应 tau 的数据，
验证经典 PSM（卡尺匹配配平后算效果）能纠正混杂方向、配平达标。

运行：python test_psm.py
"""

import numpy as np
import pandas as pd
import psm


def simulate(n=6000, seed=42):
    """模拟定向灰度。返回 (df, att_true)，att_true 为真实风险差 ATT。"""
    rng = np.random.default_rng(seed)
    n_users = n // 2
    user_ids = np.repeat(np.arange(n_users), rng.integers(1, 4, n_users))
    if len(user_ids) < n:
        user_ids = np.concatenate([user_ids, rng.integers(0, n_users, n - len(user_ids))])
    user_ids = user_ids[:n]
    member = rng.integers(1, 6, n)               # 会员等级 1-5
    prev_eff = rng.binomial(1, 0.5, n)           # 上一同进线是否触发有效方案
    intent = rng.choice(["complaint", "consult", "billing"], n, p=[0.4, 0.35, 0.25])
    complaint = (intent == "complaint").astype(float)
    # 倾向：定向灰度（强混杂）
    logit_t = -2.0 + 0.6 * member + 0.8 * prev_eff + 0.3 * complaint
    e_true = 1.0 / (1.0 + np.exp(-logit_t))
    t = rng.binomial(1, e_true)
    # 结局：logit 尺度真效应 tau_logit = -0.05；风险差 ATT 需据此另算
    tau_logit = -0.05
    logit0 = -1.0 + 0.5 * member + 0.6 * prev_eff + 0.2 * complaint
    p0 = 1.0 / (1.0 + np.exp(-logit0))
    p1 = 1.0 / (1.0 + np.exp(-(logit0 + tau_logit)))
    y = rng.binomial(1, np.where(t == 1, p1, p0))
    # 真实 ATT（风险差）= E[p1 - p0 | T=1] = Σ(p1-p0)·e_true / Σ e_true
    att_true = float(np.sum((p1 - p0) * e_true) / np.sum(e_true))
    df = pd.DataFrame({
        "user_id": user_ids,
        "member_level": member,
        "prev_effective": prev_eff,
        "intent": intent,
        "agent": t,
        "transferred": y,
    })
    return df, att_true


CONFIG = {
    "treat_col": "agent",
    "treat_value": 1,
    "outcome_col": "transferred",
    "cov_cols": ["member_level", "prev_effective", "intent"],
    "user_col": "user_id",
    "binary": True,
}


def test_single_recovery():
    df, tau = simulate(6000, 42)
    r = psm.run_matching_with_effect(df, dict(CONFIG))
    att = r["effect"]["att"]

    t = psm.encode_treatment(df[CONFIG["treat_col"]], CONFIG["treat_value"])
    y = df[CONFIG["outcome_col"]].astype(float).values
    naive = float(y[t == 1].mean() - y[t == 0].mean())

    print("\n=== 单次恢复（n=6000, seed=42）===")
    print(f"真效应 ATT（风险差）= {tau:.4f}")
    print(f"naive  = {naive:+.4f}   （应被混杂带偏、方向反转）")
    print(f"匹配   = {att:+.4f}")

    assert not np.isnan(att), "匹配效应不应为 NaN"
    assert att < 0, f"匹配效应方向应与真效应一致（负）: {att}"
    assert naive > 0, f"朴素差异应被混杂带偏为正：naive={naive}"

    bsum = r["balance_summary"]
    before_max = max(abs(x["smd_before"]) for x in r["balance"])
    assert before_max > 0.1, "配平前应有明显不平衡"
    assert bsum["max_smd_after"] < 0.1, f"配平后仍有协变量 |SMD|>=0.1: {bsum['imbalanced_covariates']}"

    print(f"配平：max|SMD| {before_max:.3f} → {bsum['max_smd_after']:.3f}，达标={bsum['balanced']}")
    print(f"配对 {r['n_matched']} 对（用到老 agent {r['n_matched_control_distinct']} 条）")
    print("单次恢复通过")
    return r


def test_balance_stability():
    """多 seed 下匹配稳定地实现配平（匹配的核心职责）。

    注：离散/弱相关协变量下匹配效应方向在小样本（n=3000）不稳定（审查 P2-1），
    故这里只断言「配平达标 + 效应有限」，效应方向在 test_single_recovery 用大样本校验。
    """
    n_unbalanced = 0
    n_nan = 0
    n_pos = 0
    for seed in range(15):
        df, tau = simulate(3000, seed)
        r = psm.run_matching_with_effect(df, dict(CONFIG))
        if not r["balance_summary"]["balanced"]:
            n_unbalanced += 1
        if np.isnan(r["effect"]["att"]):
            n_nan += 1
        if not r["effect"]["att"] < 0:
            n_pos += 1
    print("\n=== 稳定性（15 seeds, n=3000）===")
    print(f"配平未达标 {n_unbalanced}/15（应 0），效应 NaN {n_nan}/15（应 0），方向为正 {n_pos}/15（信息性，离散协变量下可漂移）")
    assert n_unbalanced == 0, f"存在 {n_unbalanced} 个 seed 配平未达标"
    assert n_nan == 0, f"存在 {n_nan} 个 seed 效应为 NaN"
    print("稳定性通过")


if __name__ == "__main__":
    test_single_recovery()
    test_balance_stability()
    print("\n全部通过")

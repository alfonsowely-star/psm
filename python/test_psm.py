"""
模拟数据黄金自检：合成含强混杂 + 已知真效应 tau 的数据，
验证 IPTW / DR / 匹配能还原 tau、朴素差异被带偏、配平达标。

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
    "B": 200,
    "N_perm": 200,
}


def test_single_recovery():
    df, tau = simulate(6000, 42)
    r = psm.run_analysis(df, dict(CONFIG))
    ipw = r["estimates"]["ipw"]["att"]
    dr = r["estimates"]["dr"]["att"]
    match = r["estimates"]["matching"]["att"]
    naive = r["estimates"]["naive"]

    print("\n=== 单次恢复（n=6000, seed=42）===")
    print(f"真效应 ATT（风险差）= {tau:.4f}")
    print(f"naive  = {naive:+.4f}   （应被混杂带偏、明显高于真值）")
    print(f"IPW    = {ipw:+.4f}")
    print(f"DR     = {dr:+.4f}")
    print(f"匹配   = {match:+.4f}")

    assert abs(ipw - tau) < 0.02, f"IPW 偏离真值: {ipw}"
    assert abs(dr - tau) < 0.02, f"DR 偏离真值: {dr}"
    assert abs(match - tau) < 0.03, f"匹配偏离真值: {match}"
    assert naive - tau > 0.02, f"朴素差异应被混杂带偏：naive={naive}, tau={tau}"

    ci = r["ci"]["ipw"]
    assert ci["lo"] <= tau <= ci["hi"], f"IPW CI 未覆盖真值: {ci}"
    bsum = r["balance_summary"]
    before_max = max(abs(x["smd_before"]) for x in r["balance"])
    assert before_max > 0.1, "配平前应有明显不平衡"
    assert bsum["max_smd_after"] < 0.1, f"配平后仍有协变量 |SMD|>=0.1: {bsum['imbalanced_covariates']}"

    print(f"IPW CI = [{ci['lo']:+.4f}, {ci['hi']:+.4f}]")
    print(f"配平：max|SMD| {before_max:.3f} → {bsum['max_smd_after']:.3f}，达标={bsum['balanced']}")
    print(f"ESS={r['weight_diagnostics']['ess']:.0f}/{r['n']}  "
          f"E-value={r['evalue']['e_value']:.2f}  MDE={r['mde']:.4f}  置换p={r['permutation']['p_value']:.3f}")
    print("单次恢复通过")
    return r


def test_monte_carlo():
    ipws, taus = [], []
    for seed in range(15):
        df, tau = simulate(3000, seed)
        r = psm.run_analysis(df, dict(CONFIG, B=0, N_perm=0))
        ipws.append(r["estimates"]["ipw"]["att"])
        taus.append(tau)
    ipws = np.array(ipws)
    taus = np.array(taus)
    bias = float(np.mean(ipws - taus))
    print("\n=== Monte Carlo（15 seeds, n=3000）===")
    print(f"IPW 平均偏差 = {bias:+.4f}（应 < 0.015），估计 std = {ipws.std():.4f}")
    assert abs(bias) < 0.015, f"IPW 存在系统性偏差: {bias}"
    print("Monte Carlo 通过")


if __name__ == "__main__":
    test_single_recovery()
    test_monte_carlo()
    print("\n全部通过")

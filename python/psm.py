"""
PSM 因果配平核心库（纯函数，可测试）。

覆盖：倾向得分、配平诊断、ATT 估计（稳定 IPTW / 双重稳健 AIPW / 最近邻匹配）、
user 层 cluster bootstrap、置换检验、E-value、MDE。

仅依赖 numpy / pandas / scipy / scikit-learn。
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.metrics import roc_auc_score
from scipy import stats
from scipy.spatial import cKDTree

SMD_THRESHOLD = 0.1
EPS = 1e-8


# ---------- 数据预处理 ----------

def infer_type(series):
    """推断列类型：'binary' | 'numeric' | 'categorical'。数值才可能 binary，字符串一律 categorical。"""
    s = series.dropna()
    if len(s) == 0:
        return "categorical"
    if pd.to_numeric(s, errors="coerce").notna().all():
        return "binary" if s.nunique() <= 2 else "numeric"
    return "categorical"


def encode_treatment(series, treat_value):
    """把处理方列编码为 0/1（等于 treat_value 的为 1）。数值列数值比较，否则字符串比较兜底。"""
    s = series
    if pd.api.types.is_numeric_dtype(s):
        try:
            tv = pd.to_numeric(str(treat_value))
            return (s == tv).astype(float).values
        except (ValueError, TypeError):
            pass
    return (s.astype(str) == str(treat_value)).astype(float).values


def encode_covariates(df, cov_cols):
    """返回 (X ndarray, feature_names)。分类 one-hot(drop first)，其余转数值。"""
    parts = []
    names = []
    for c in cov_cols:
        typ = infer_type(df[c])
        if typ == "categorical":
            dummies = pd.get_dummies(df[c], prefix=str(c), drop_first=True)
            for col in dummies.columns:
                parts.append(dummies[col].astype(float).values)
                names.append(col)
        else:
            parts.append(df[c].astype(float).values)
            names.append(str(c))
    if not parts:
        return np.zeros((len(df), 1)), ["(无协变量)"]
    return np.column_stack(parts), names


# ---------- 倾向得分 ----------

def fit_propensity(X, t):
    """拟合 P(T=1|X)，返回 (model, e, auc)。"""
    if t.sum() == 0 or t.sum() == len(t):
        raise ValueError("treatment 列只有单一取值，无法做对比")
    model = LogisticRegression(penalty="l2", C=1.0, max_iter=3000, solver="lbfgs")
    model.fit(X, t)
    e = model.predict_proba(X)[:, 1]
    auc = float(roc_auc_score(t, e)) if len(np.unique(t)) == 2 else float("nan")
    return model, e, auc


def propensity_coefs(model, feature_names):
    """系数 + 优势比 OR，供可审计输出。"""
    out = []
    for name, b in zip(feature_names, model.coef_[0]):
        out.append({"feature": name, "coef": float(b), "or": float(np.exp(b))})
    return out


def calibration_bins(e, t, n_bins=10):
    """倾向得分十分位校准：每 bin 平均预测 vs 实际处理比例。"""
    try:
        bins = pd.qcut(e, q=n_bins, duplicates="drop")
    except Exception:
        return []
    df = pd.DataFrame({"e": e, "t": t, "bin": bins})
    out = []
    for b, grp in df.groupby("bin", observed=True):
        out.append({
            "bin": str(b),
            "n": int(len(grp)),
            "pred": float(grp["e"].mean()),
            "obs": float(grp["t"].mean()),
        })
    return out


# ---------- 权重 ----------

def att_weights(e, t, clip_q=0.99):
    """ATT 权重：treated=1，control=e/(1-e)，control 侧极端值截断。"""
    w = np.where(t == 1, 1.0, e / np.maximum(1.0 - e, EPS))
    ctrl = t == 0
    if ctrl.any():
        q = float(np.quantile(w[ctrl], clip_q))
        w = np.where(ctrl & (w > q), q, w)
    return w


def ess(w):
    """有效样本量 = (Σw)^2 / Σw^2。"""
    s2 = float(np.sum(w ** 2))
    return float(np.sum(w) ** 2 / s2) if s2 > 0 else 0.0


# ---------- 配平诊断 ----------

def _wmean(x, w):
    s = float(np.sum(w))
    return float(np.sum(x * w) / s) if s > 0 else float(np.mean(x))


def _wvar(x, w):
    s = float(np.sum(w))
    if s <= 0:
        return float(np.var(x))
    m = float(np.sum(x * w) / s)
    return float(np.sum(w * (x - m) ** 2) / s)


def smd(x_t, x_c, w_t=None, w_c=None):
    """标准化均值差（可选加权）。"""
    m_t = _wmean(x_t, w_t) if w_t is not None else float(np.mean(x_t))
    m_c = _wmean(x_c, w_c) if w_c is not None else float(np.mean(x_c))
    v_t = _wvar(x_t, w_t) if w_t is not None else float(np.var(x_t))
    v_c = _wvar(x_c, w_c) if w_c is not None else float(np.var(x_c))
    denom = float(np.sqrt((v_t + v_c) / 2.0))
    return float((m_t - m_c) / denom) if denom > 1e-12 else 0.0


def balance_table(X, feature_names, t, e, clip_q=0.99):
    """在编码后的特征上：SMD 前 / SMD 后（ATT 权重）、VR 后、偏倚降低率。"""
    w = att_weights(e, t, clip_q)
    rows = []
    for j, name in enumerate(feature_names):
        x = X[:, j]
        xt, xc = x[t == 1], x[t == 0]
        wt, wc = w[t == 1], w[t == 0]
        before = smd(xt, xc)
        after = smd(xt, xc, wt, wc)
        v_t = _wvar(xt, wt)
        v_c = _wvar(xc, wc)
        vr = float(v_t / v_c) if v_c > 1e-12 else float("nan")
        bias_red = float(1.0 - abs(after) / abs(before)) if abs(before) > 1e-12 else float("nan")
        rows.append({
            "covariate": str(name),
            "type": "binary" if len(np.unique(x)) <= 2 else "numeric",
            "mean_treated": _wmean(xt, wt),
            "mean_control": _wmean(xc, wc),
            "smd_before": before,
            "smd_after": after,
            "variance_ratio": vr,
            "bias_reduction": bias_red,
            "missing": 0,
        })
    return rows


def balance_summary(bal_rows, threshold=SMD_THRESHOLD):
    smds = [r["smd_after"] for r in bal_rows if r["smd_after"] is not None]
    bad = [r["covariate"] for r in bal_rows if r["smd_after"] is not None and abs(r["smd_after"]) > threshold]
    reds = [r["bias_reduction"] for r in bal_rows if r["bias_reduction"] is not None and not np.isnan(r["bias_reduction"])]
    return {
        "max_smd_after": float(max(smds)) if smds else float("nan"),
        "n_imbalanced": len(bad),
        "imbalanced_covariates": bad,
        "balanced": len(bad) == 0,
        "mean_bias_reduction": float(np.mean(reds)) if reds else float("nan"),
    }


def run_matching(df, config):
    """纯匹配：把「新 agent」实例配到最相似的老 agent 实例。输出配对 + 配平检查（不需要结局）。"""
    id_col = config.get("id_col")
    treat_col = config["treat_col"]
    treat_value = config["treat_value"]
    cov_cols = config["cov_cols"]

    t = encode_treatment(df[treat_col], treat_value)
    X, feature_names = encode_covariates(df, cov_cols)
    mt, mc = match_pairs(X, t)

    if id_col and id_col in df.columns:
        ids = df[id_col].astype(str).tolist()
    else:
        ids = [str(i) for i in range(len(df))]

    bal_rows = []
    for j, name in enumerate(feature_names):
        x = X[:, j]
        before = smd(x[t == 1], x[t == 0])
        after = smd(x[mt], x[mc]) if len(mt) else float("nan")
        bias_red = float(1.0 - abs(after) / abs(before)) if abs(before) > 1e-12 and not np.isnan(after) else float("nan")
        bal_rows.append({
            "covariate": str(name),
            "smd_before": before,
            "smd_after": after,
            "bias_reduction": bias_red,
        })
    bal_sum = balance_summary(bal_rows)

    pairs = [{"treated_id": ids[i], "control_id": ids[c]} for i, c in zip(mt, mc)]

    return {
        "n": int(len(df)),
        "n_treated": int(t.sum()),
        "n_control": int((1 - t).sum()),
        "n_matched": int(len(mt)),
        "n_matched_control_distinct": int(len(set(ids[c] for c in mc))),
        "balance": bal_rows,
        "balance_summary": bal_sum,
        "pairs": pairs,
        "ids": ids,
        "t": t.astype(int).tolist(),
        "mt": mt.astype(int).tolist(),
        "mc": mc.astype(int).tolist(),
        "matched_control_ids": [ids[c] for c in mc],
    }


def weight_diagnostics(w, t):
    ctrl = w[t == 0]
    return {
        "max_weight": float(np.max(w)),
        "mean_weight": float(np.mean(w)),
        "p99_weight": float(np.quantile(w, 0.99)),
        "control_max_weight": float(np.max(ctrl)) if len(ctrl) else float("nan"),
        "ess": ess(w),
        "ess_ratio": float(ess(w) / len(w)),
    }


def overlap_report(e, t):
    e_t = e[t == 1]
    e_c = e[t == 0]
    lo, hi = float(e_c.min()), float(e_c.max())
    out_of_support = int(((t == 1) & ((e < lo) | (e > hi))).sum())
    return {
        "treated_propensity_min": float(e_t.min()),
        "treated_propensity_max": float(e_t.max()),
        "control_propensity_min": lo,
        "control_propensity_max": hi,
        "treated_out_of_support": out_of_support,
        "overlap_range": [float(max(lo, e_t.min())), float(min(hi, e_t.max()))],
    }


def stratification(e, t, y, n_strata=5):
    """倾向五分位分层：每层内 treated/control 结局均值。"""
    try:
        bins = pd.qcut(e, q=n_strata, duplicates="drop")
    except Exception:
        return []
    df = pd.DataFrame({"e": e, "t": t, "y": y, "bin": bins})
    out = []
    for b, grp in df.groupby("bin", observed=True):
        gt = grp[grp["t"] == 1]["y"]
        gc = grp[grp["t"] == 0]["y"]
        out.append({
            "stratum": str(b),
            "n_treated": int(len(gt)),
            "n_control": int(len(gc)),
            "mean_treated": float(gt.mean()) if len(gt) else float("nan"),
            "mean_control": float(gc.mean()) if len(gc) else float("nan"),
        })
    return out


# ---------- 估计量 ----------

def att_ipw(y, t, e, clip_q=0.99):
    """稳定 IPTW（Hájek）：ATT = E[Y|T=1] - Σ_{T=0} w Y / Σ_{T=0} w。"""
    w = att_weights(e, t, clip_q)
    m1 = _wmean(y[t == 1], w[t == 1])
    m0 = _wmean(y[t == 0], w[t == 0])
    return float(m1 - m0), float(m1), float(m0)


def fit_outcome_model(X, y, t, binary):
    """在 control 组上拟合 m0(X)=E[Y|X,T=0]，返回对全体 X 的预测。"""
    Xc, yc = X[t == 0], y[t == 0]
    if len(np.unique(yc)) <= 1:
        return np.full(len(y), float(yc.mean()))
    if binary:
        m = LogisticRegression(penalty="l2", C=1.0, max_iter=3000, solver="lbfgs").fit(Xc, yc)
        return m.predict_proba(X)[:, 1]
    m = LinearRegression().fit(Xc, yc)
    return m.predict(X)


def att_dr(y, t, e, m0, clip_q=0.99):
    """双重稳健 ATT：1/n1 Σ (Y_i - m0_i) (T_i - (1-T_i) e_i/(1-e_i))。"""
    w = att_weights(e, t, clip_q)
    n1 = int(t.sum())
    if n1 == 0:
        return float("nan"), float("nan"), float("nan")
    psi = (y - m0) * (t - (1.0 - t) * w)
    att = float(psi.sum() / n1)
    m1 = float(y[t == 1].mean())
    return att, m1, m1 - att


def match_pairs(X, t):
    """Mahalanobis 距离 1:1 最近邻匹配（with replacement）。返回 (mt, mc) 索引。"""
    treated_idx = np.where(t == 1)[0]
    control_idx = np.where(t == 0)[0]
    if len(treated_idx) == 0 or len(control_idx) == 0:
        return np.array([], dtype=int), np.array([], dtype=int)
    Xc = X[control_idx]
    S = np.cov(Xc, rowvar=False) + np.eye(Xc.shape[1]) * 1e-6
    try:
        L = np.linalg.cholesky(np.linalg.inv(S))
    except np.linalg.LinAlgError:
        L = np.eye(Xc.shape[1])
    Zc = Xc @ L.T
    Zt = X[treated_idx] @ L.T
    tree = cKDTree(Zc)
    _, j = tree.query(Zt, k=1)
    j = np.atleast_1d(j)
    return treated_idx, control_idx[j]


def att_matching(X, y, t, m0=None):
    """Mahalanobis 配对 + Abadie-Imbens 偏差校正。"""
    mt, mc = match_pairs(X, t)
    if len(mt) == 0:
        return float("nan"), 0, 0
    att = float(y[mt].mean() - y[mc].mean())
    if m0 is not None:
        att = att - float((m0[mt] - m0[mc]).mean())  # Abadie-Imbens 偏差校正
    return att, int(len(mt)), int(len(mc))


def naive_difference(y, t):
    """未配平的朴素均值差（用于展示混杂偏差）。"""
    return float(y[t == 1].mean() - y[t == 0].mean())


# ---------- 推断 ----------

def _fit_all(X, t, y, binary, clip_q=0.99):
    """拟合倾向 + 结局模型，返回三个 ATT 估计。"""
    _, e, _ = fit_propensity(X, t)
    m0 = fit_outcome_model(X, y, t, binary)
    a_ipw, _, _ = att_ipw(y, t, e, clip_q)
    a_dr, _, _ = att_dr(y, t, e, m0, clip_q)
    a_match, _, _ = att_matching(X, y, t, m0)
    return {"ipw": a_ipw, "dr": a_dr, "matching": a_match}


def _group_key(df, user_col):
    if user_col and user_col in df.columns:
        return df[user_col].astype(str).values
    return np.arange(len(df)).astype(str)


def cluster_bootstrap(df, cov_cols, treat_col, treat_value, outcome_col, binary, user_col, B=200, seed=0, clip_q=0.99):
    """user 层 cluster bootstrap：重采样用户，重拟合全套，输出三个估计量的 95% CI。"""
    rng = np.random.default_rng(seed)
    g = _group_key(df, user_col)
    groups = np.unique(g)
    ests = {"ipw": [], "dr": [], "matching": []}
    for _ in range(B):
        sampled = rng.choice(groups, size=len(groups), replace=True)
        mask = np.isin(g, sampled)
        d = df[mask]
        t = encode_treatment(d[treat_col], treat_value)
        if t.sum() == 0 or t.sum() == len(t):
            continue
        X, _ = encode_covariates(d, cov_cols)
        y = d[outcome_col].astype(float).values
        r = _fit_all(X, t, y, binary, clip_q)
        for k in ests:
            ests[k].append(r[k])
    ci = {}
    for k, v in ests.items():
        v = [x for x in v if not np.isnan(x)]
        if len(v) >= 10:
            ci[k] = {"lo": float(np.percentile(v, 2.5)), "hi": float(np.percentile(v, 97.5)), "n": len(v)}
        else:
            ci[k] = None
    return ci


def permutation_test(df, cov_cols, treat_col, treat_value, outcome_col, binary, user_col, N=200, seed=1, clip_q=0.99):
    """treatment 标签在 user 层随机打乱，重估 ATT 得零分布，检验 sharp null。"""
    rng = np.random.default_rng(seed)
    g = _group_key(df, user_col)
    groups = np.unique(g)
    t0 = encode_treatment(df[treat_col], treat_value)
    treat_by_group = {}
    for gi in groups:
        treat_by_group[gi] = t0[g == gi][0]
    X, _ = encode_covariates(df, cov_cols)
    y = df[outcome_col].astype(float).values
    real = _fit_all(X, t0, y, binary, clip_q)["ipw"]
    null = []
    for _ in range(N):
        perm = rng.permutation(groups)
        perm_map = dict(zip(groups, perm))
        t = np.array([treat_by_group[perm_map[gi]] for gi in g]).astype(float)
        if t.sum() == 0 or t.sum() == len(t):
            continue
        null.append(_fit_all(X, t, y, binary, clip_q)["ipw"])
    null = np.array([x for x in null if not np.isnan(x)])
    p = float((np.abs(null) >= abs(real)).mean()) if len(null) else float("nan")
    return {
        "observed_att": float(real),
        "null_mean": float(null.mean()) if len(null) else float("nan"),
        "null_sd": float(null.std()) if len(null) else float("nan"),
        "p_value": p,
        "n_perm": int(len(null)),
    }


# ---------- 敏感性 / 功效 ----------

def evalue(att, m1, m0):
    """二值结局：风险差 → 风险比 → E-value（VanderWeele & Ding 2017）。"""
    m1 = float(np.clip(m1, EPS, 1 - EPS))
    m0 = float(np.clip(m0, EPS, 1 - EPS))
    if att >= 0:
        rr = m1 / m0
    else:
        rr = m0 / m1
    rr = max(rr, 1.0)
    e = rr + np.sqrt(rr * (rr - 1.0))
    return {"risk_difference": float(att), "risk_ratio": float(rr if att >= 0 else 1.0 / rr), "e_value": float(e)}


def mde_binary(m1, m0, ess_t, ess_c, alpha=0.05, power=0.8):
    """二值结局最小可检出效应（风险差，α=0.05 双尾，power=0.8）。"""
    z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    p_t = float(np.clip(m1, EPS, 1 - EPS))
    p_c = float(np.clip(m0, EPS, 1 - EPS))
    return float(z * np.sqrt(p_t * (1 - p_t) / ess_t + p_c * (1 - p_c) / ess_c))


# ---------- 主流程 ----------

def run_analysis(df, config):
    """
    config 键：treat_col, treat_value, outcome_col, cov_cols,
              user_col(可选), binary(默认 True), clip_q(默认 .99),
              B(默认 200), N_perm(默认 200)。
    """
    treat_col = config["treat_col"]
    treat_value = config["treat_value"]
    outcome_col = config["outcome_col"]
    cov_cols = config["cov_cols"]
    user_col = config.get("user_col")
    binary = config.get("binary", True)
    clip_q = config.get("clip_q", 0.99)
    B = config.get("B", 200)
    N_perm = config.get("N_perm", 200)

    missing_outcome = int(df[outcome_col].isna().sum())
    d = df[df[outcome_col].notna()].reset_index(drop=True)
    t = encode_treatment(d[treat_col], treat_value)
    y = d[outcome_col].astype(float).values

    X, feature_names = encode_covariates(d, cov_cols)
    model, e, auc = fit_propensity(X, t)

    coefs = propensity_coefs(model, feature_names)
    calib = calibration_bins(e, t)
    m0 = fit_outcome_model(X, y, t, binary)

    w = att_weights(e, t, clip_q)
    bal_rows = balance_table(X, feature_names, t, e, clip_q)
    bal_sum = balance_summary(bal_rows)
    wd = weight_diagnostics(w, t)
    ov = overlap_report(e, t)
    strat = stratification(e, t, y)

    a_ipw, m1_ipw, m0_ipw = att_ipw(y, t, e, clip_q)
    a_dr, m1_dr, m0_dr = att_dr(y, t, e, m0, clip_q)
    a_match, nm_t, nm_c = att_matching(X, y, t, m0)
    a_naive = naive_difference(y, t)

    ci = cluster_bootstrap(d, cov_cols, treat_col, treat_value, outcome_col, binary, user_col, B=B, seed=0, clip_q=clip_q)
    perm = permutation_test(d, cov_cols, treat_col, treat_value, outcome_col, binary, user_col, N=N_perm, seed=1, clip_q=clip_q)

    ess_t = ess(w[t == 1])
    ess_c = ess(w[t == 0])
    mde = mde_binary(m1_ipw, m0_ipw, ess_t, ess_c) if binary else None
    ev = evalue(a_ipw, m1_ipw, m0_ipw) if binary else None

    n = int(len(d))
    n_treated = int(t.sum())
    n_control = int(n - n_treated)

    return {
        "n": n,
        "n_treated": n_treated,
        "n_control": n_control,
        "auc": auc,
        "propensity_coefs": coefs,
        "calibration": calib,
        "balance": bal_rows,
        "balance_summary": bal_sum,
        "weight_diagnostics": wd,
        "overlap": ov,
        "stratification": strat,
        "estimates": {
            "naive": a_naive,
            "ipw": {"att": a_ipw, "mean_treated": m1_ipw, "mean_control": m0_ipw},
            "dr": {"att": a_dr, "mean_treated": m1_dr, "mean_control": m0_dr},
            "matching": {"att": a_match, "n_matched_treated": nm_t, "n_matched_control": nm_c},
        },
        "ci": ci,
        "permutation": perm,
        "evalue": ev,
        "mde": mde,
        "ess_treated": ess_t,
        "ess_control": ess_c,
        "missing_outcome": missing_outcome,
    }

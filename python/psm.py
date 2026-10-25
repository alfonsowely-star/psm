"""
PSM 因果配平核心库（纯函数，可测试）。

覆盖：协变量编码、Mahalanobis 卡尺匹配、配平诊断、经典 PSM 效果估计
（卡尺匹配配平后，在配平两队上算结局差异 + Abadie-Imbens 偏差校正）。

仅依赖 numpy / pandas / scikit-learn / scipy。
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, LinearRegression
from scipy.spatial import cKDTree

SMD_THRESHOLD = 0.1


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


# ---------- 匹配 ----------

def run_matching(df, config):
    """纯匹配：把「新 agent」实例配到最相似的老 agent 实例。输出配对 + 配平检查（不需要结局）。"""
    id_col = config.get("id_col")
    treat_col = config["treat_col"]
    treat_value = config["treat_value"]
    cov_cols = config["cov_cols"]

    t = encode_treatment(df[treat_col], treat_value)
    if t.sum() == 0 or t.sum() == len(t):
        raise ValueError("处理方列只有单一取值（全 0 或全 1），无法对比：请检查 treat_value 是否与数据中的实际取值一致")
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


def run_matching_with_effect(df, config):
    """经典 PSM：卡尺匹配配平，然后在配平后的两队上算结局差异（效果）。

    与 run_matching 用同一套匹配口径，配平结果与「仅配平」完全一致。
    """
    outcome_col = config["outcome_col"]
    d = df[df[outcome_col].notna()].reset_index(drop=True)
    missing_outcome = int(len(df) - len(d))

    id_col = config.get("id_col")
    treat_col = config["treat_col"]
    treat_value = config["treat_value"]
    cov_cols = config["cov_cols"]
    binary = config.get("binary", True)

    t = encode_treatment(d[treat_col], treat_value)
    if t.sum() == 0 or t.sum() == len(t):
        raise ValueError("处理方列只有单一取值（全 0 或全 1），无法对比：请检查 treat_value 是否与数据中的实际取值一致")
    X, feature_names = encode_covariates(d, cov_cols)
    mt, mc = match_pairs(X, t)

    y = d[outcome_col].astype(float).values
    m0 = fit_outcome_model(X, y, t, binary)

    # 效果 = 配平后两队结局差异 + Abadie-Imbens 偏差校正
    att = float(y[mt].mean() - y[mc].mean()) if len(mt) else float("nan")
    att -= float((m0[mt] - m0[mc]).mean())

    if id_col and id_col in d.columns:
        ids = d[id_col].astype(str).tolist()
    else:
        ids = [str(i) for i in range(len(d))]

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
        "n": int(len(d)),
        "n_treated": int(t.sum()),
        "n_control": int((1 - t).sum()),
        "n_matched": int(len(mt)),
        "n_matched_control_distinct": int(len(set(ids[c] for c in mc))),
        "missing_outcome": missing_outcome,
        "balance": bal_rows,
        "balance_summary": bal_sum,
        "pairs": pairs,
        "ids": ids,
        "t": t.astype(int).tolist(),
        "mt": mt.astype(int).tolist(),
        "mc": mc.astype(int).tolist(),
        "effect": {
            "att": att,
            "mean_treated": float(y[mt].mean()) if len(mt) else float("nan"),
            "mean_control": float(y[mc].mean()) if len(mc) else float("nan"),
        },
    }


# ---------- 估计量 ----------

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


def match_pairs(X, t, caliper=None):
    """Mahalanobis 距离 1:1 最近邻匹配（无放回，贪心，可选卡尺）。

    卡尺：只配「匹配距离 ≤ caliper」的对，配不上的 treated 丢弃（不硬配）。
    默认 caliper = 最近邻距离的中位数。
    """
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
    Zc = Xc @ L
    Zt = X[treated_idx] @ L
    tree = cKDTree(Zc)

    n_t = len(treated_idx)
    n_c = len(control_idx)
    K = min(n_c, 300)
    dd, jj = tree.query(Zt, k=K)
    dd = np.atleast_2d(dd)
    jj = np.atleast_2d(jj)

    if caliper is None:
        caliper = float(np.median(dd[:, 0]))

    order = np.argsort(dd[:, 0])  # 近的先配
    used = np.zeros(n_c, dtype=bool)
    mt, mc = [], []
    for i in order:
        for a in range(K):
            if dd[i, a] > caliper:
                break  # 更远的都不满足卡尺，放弃该 treated
            c = jj[i, a]
            if not used[c]:
                used[c] = True
                mt.append(treated_idx[i])
                mc.append(control_idx[c])
                break
    return np.array(mt, dtype=int), np.array(mc, dtype=int)

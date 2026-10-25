"""
analyze.py —— CLI 入口（纯匹配模式）。

用法：
  python analyze.py --data <csv|jsonl> --config <json> --outdir <dir>

输入：实例 id + 处理方（新/老）+ 维度（协变量）。
输出：配平后的两队（谁配谁）+ 两组在维度上是否可比。
"""

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

import psm


def load_data(path):
    if path.endswith((".jsonl", ".ndjson")):
        return pd.read_json(path, lines=True, encoding="utf-8-sig")
    if path.endswith(".json"):
        return pd.read_json(path, encoding="utf-8-sig")
    return pd.read_csv(path, encoding="utf-8-sig")


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _fmt(v, digits=4):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:+.{digits}f}"


def _jsonable(obj):
    """递归把 float NaN/±Inf 转成 null，避免写出 JS JSON.parse 不认的非法 JSON。"""
    if isinstance(obj, float):
        return None if np.isnan(obj) or np.isinf(obj) else obj
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def _love_plot(bal):
    if not bal:
        return ""
    maxabs = max([abs(r["smd_before"]) for r in bal] + [abs(r["smd_after"]) for r in bal] + [0.2])
    n = len(bal)
    row_h = 30
    pad_left = 180
    w = 640
    h = 50 + n * row_h
    cx = pad_left + w * 0.5
    scale = (w * 0.5 - 12) / maxabs
    parts = [f'<svg viewBox="0 0 {pad_left + w} {h}" width="100%" xmlns="http://www.w3.org/2000/svg">']
    for s in (-1, 1):
        x = cx + s * 0.1 * scale
        parts.append(f'<line x1="{x:.1f}" y1="26" x2="{x:.1f}" y2="{h - 8}" stroke="#c0392b" stroke-dasharray="4 3"/>')
    parts.append(f'<line x1="{cx:.1f}" y1="26" x2="{cx:.1f}" y2="{h - 8}" stroke="#9aa7b3"/>')
    parts.append(f'<text x="{cx - 0.1 * scale:.1f}" y="18" font-size="11" fill="#c0392b">差异度 0.1</text>')
    for i, r in enumerate(bal):
        y = 46 + i * row_h
        parts.append(f'<text x="{pad_left - 8}" y="{y + 12}" text-anchor="end" font-size="12">{_esc(r["covariate"][:22])}</text>')
        xb = cx + r["smd_before"] * scale
        xa = cx + r["smd_after"] * scale
        parts.append(f'<line x1="{xb:.1f}" y1="{y}" x2="{xa:.1f}" y2="{y + 14}" stroke="#c5ced8"/>')
        parts.append(f'<circle cx="{xb:.1f}" cy="{y}" r="4.5" fill="#e67e22"/>')
        parts.append(f'<circle cx="{xa:.1f}" cy="{y + 14}" r="4.5" fill="#157f3d"/>')
    parts.append('</svg>')
    return "".join(parts)


def _balance_rows_html(bal):
    rows = []
    for r in bal:
        br = r["bias_reduction"]
        bias_cell = "—" if br is None or (isinstance(br, float) and np.isnan(br)) else f"{br*100:.0f}%"
        rows.append(
            f"<tr><td>{_esc(r['covariate'])}</td><td>{_fmt(r['smd_before'])}</td>"
            f"<td>{_fmt(r['smd_after'])}</td><td>{bias_cell}</td></tr>"
        )
    return "".join(rows)


def render_effect_report(r, config, df):
    bsum = r["balance_summary"]
    eff = r["effect"]
    cert_color = "#157f3d" if bsum["balanced"] else "#c0392b"
    cert_text = "✓ 两组可比" if bsum["balanced"] else f"✗ 不可比：{', '.join(bsum['imbalanced_covariates'])}"
    mbr = bsum["mean_bias_reduction"]
    mean_br_str = "—" if mbr is None or (isinstance(mbr, float) and np.isnan(mbr)) else f"{mbr*100:.0f}%"
    t = np.array(r["t"]).astype(float)
    mt = np.array(r["mt"]).astype(int)
    mc = np.array(r["mc"]).astype(int)
    dist_plots = "".join(_dist_plot(df, c, t, mt, mc) for c in config["cov_cols"])

    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent 效果对比报告</title>
<style>
body{{font:15px/1.7 system-ui,sans-serif;color:#15283b;background:#f4f7fb;max-width:1180px;margin:36px auto;padding:0 24px}}
h1{{font-size:26px;margin:0 0 4px}} h2{{margin-top:40px;border-top:1px solid #c9d4df;padding-top:22px;font-size:19px}}
.meta{{color:#5a6b7d;font-size:13px;margin-bottom:20px}}
.cards{{display:flex;flex-wrap:wrap;gap:14px;margin:18px 0}}
.card{{background:#fff;border:1px solid #dbe3ec;border-radius:10px;padding:14px 18px;min-width:150px}}
.card .v{{font-size:26px;font-weight:700;color:#1163ad}} .card .k{{font-size:12px;color:#5a6b7d}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px;margin:12px 0}}
td,th{{border:1px solid #dbe3ec;padding:8px 12px;text-align:left}}
th{{background:#e5eef8;font-weight:700}}
.cert{{border:1px solid {cert_color};background:#fff;border-radius:10px;padding:14px 18px;font-size:16px;font-weight:700;color:{cert_color};margin:18px 0}}
svg{{background:#fff;border:1px solid #dbe3ec;border-radius:10px;margin:12px 0}}
</style><body>

<h1>Agent 效果对比报告</h1>
<div class="meta">新 agent（{_esc(config['treat_col'])} = {_esc(config['treat_value'])}）vs 老 agent ·
结局「{_esc(config['outcome_col'])}」 · 样本 {r['n']} 条（新 {r['n_treated']} / 老 {r['n_control']}）· 配成 {r['n_matched']} 对</div>

<h2>新 agent 的真实效果</h2>
<div class="cards">
<div class="card"><div class="v">{_fmt(eff['att'])}</div><div class="k">结局差异（新 − 老）</div></div>
<div class="card"><div class="v">{_fmt(eff['mean_treated'])}</div><div class="k">新 agent 队结局均值</div></div>
<div class="card"><div class="v">{_fmt(eff['mean_control'])}</div><div class="k">老 agent 队结局均值</div></div>
</div>
<p style="font-size:13px;color:#5a6b7d">效果在「卡尺匹配配平后的两队」上计算（新 agent 队 − 老 agent 队），已做偏差校正。</p>

<h2>两组是否可比</h2>
<div class="cert">{cert_text}</div>
<div class="cards">
<div class="card"><div class="v">{_fmt(bsum['max_smd_after'])}</div><div class="k">配平后最大差异度（&lt;0.1 即可比）</div></div>
<div class="card"><div class="v">{mean_br_str}</div><div class="k">平均差异降低</div></div>
</div>
<p style="font-size:13px;color:#5a6b7d">橙=配平前，绿=配平后；点越靠近 0 说明两队越像。红色虚线为差异度 0.1。</p>
{_love_plot(r['balance'])}

<h2>各组维度对比</h2>
<table><tr><th>维度</th><th>差异度 前</th><th>差异度 后</th><th>差异降低</th></tr>{_balance_rows_html(r['balance'])}</table>

<h2>各维度的分布对比</h2>
<p style="font-size:13px;color:#5a6b7d">配平前两组分布有差异，配平后应基本重合。</p>
{dist_plots}

</body></html>"""


def _dist_plot(df, cov, t, mt, mc):
    """一个维度的配平前后分布对比（新=红，老=蓝）。"""
    vals = df[cov]
    n = len(df)
    na_mask = np.zeros(n, dtype=bool)
    na_mask[mt] = True
    oa_mask = np.zeros(n, dtype=bool)
    oa_mask[mc] = True

    numeric = pd.api.types.is_numeric_dtype(vals) and vals.nunique() > 20
    if numeric:
        v = vals.astype(float).values
        lo, hi = float(np.nanmin(v)), float(np.nanmax(v))
        edges = np.linspace(lo, hi, 16)
        g = np.digitize(v, edges[1:-1])
        cats = [f"{edges[i]:.2f}" for i in range(15)]
    else:
        s = vals.astype(str).values
        cats = sorted(set(x for x in vals.dropna().astype(str).unique()))
        cidx = {c: i for i, c in enumerate(cats)}
        g = np.array([cidx.get(x, -1) for x in s])

    def cnt(mask):
        return [int(((g == i) & mask).sum()) for i in range(len(cats))]

    return _render_dist_svg(str(cov), cats, cnt(t == 1), cnt(t == 0), cnt(na_mask), cnt(oa_mask))


def _render_dist_svg(name, cats, nb, ob, na, oa):
    ncat = len(cats)
    panel_w = 300
    bar_h = 120
    pad_b = 46
    h = 200
    w = panel_w * 2 + 30
    maxc = max(max(nb), max(ob), max(na), max(oa), 1)
    group_w = panel_w / ncat
    bar_w = max(3.0, group_w * 0.34)
    show_label = ncat <= 12

    def panel(x0, new_c, old_c, label):
        parts = [f'<text x="{x0 + panel_w/2:.0f}" y="18" text-anchor="middle" font-size="12" fill="#5a6b7d">{label}</text>']
        for i in range(ncat):
            cx = x0 + i * group_w
            hn = new_c[i] / maxc * bar_h
            ho = old_c[i] / maxc * bar_h
            parts.append(f'<rect x="{cx + group_w*0.15:.1f}" y="{pad_b + bar_h - hn:.1f}" width="{bar_w:.1f}" height="{hn:.1f}" fill="#e74c3c" opacity="0.7"/>')
            parts.append(f'<rect x="{cx + group_w*0.55:.1f}" y="{pad_b + bar_h - ho:.1f}" width="{bar_w:.1f}" height="{ho:.1f}" fill="#4d88ff" opacity="0.7"/>')
            if show_label:
                parts.append(f'<text x="{cx + group_w*0.5:.1f}" y="{h - 24}" text-anchor="middle" font-size="9" fill="#8a8f98">{_esc(cats[i][:8])}</text>')
        parts.append(f'<line x1="{x0}" y1="{pad_b + bar_h}" x2="{x0 + panel_w}" y2="{pad_b + bar_h}" stroke="#9aa7b3"/>')
        return "".join(parts)

    svg = [f'<svg viewBox="0 0 {w} {h}" width="100%" xmlns="http://www.w3.org/2000/svg">']
    svg.append(panel(5, nb, ob, "配平前"))
    svg.append(panel(panel_w + 20, na, oa, "配平后"))
    svg.append(f'<text x="10" y="{h-8}" font-size="11" fill="#e74c3c">■ 新 agent</text>')
    svg.append(f'<text x="100" y="{h-8}" font-size="11" fill="#4d88ff">■ 老 agent</text>')
    svg.append('</svg>')
    return f'<div style="margin:14px 0"><div style="font-size:13px;font-weight:600;margin-bottom:2px">{_esc(name)}</div>' + "".join(svg) + "</div>"


def render_report(r, config, df):
    bsum = r["balance_summary"]
    cert_color = "#157f3d" if bsum["balanced"] else "#c0392b"
    cert_text = "✓ 两组在维度上可比" if bsum["balanced"] else f"✗ 某些维度仍不可比：{', '.join(bsum['imbalanced_covariates'])}"
    t = np.array(r["t"]).astype(float)
    mt = np.array(r["mt"]).astype(int)
    mc = np.array(r["mc"]).astype(int)
    dist_plots = "".join(_dist_plot(df, c, t, mt, mc) for c in config["cov_cols"])

    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>配平后的两队</title>
<style>
body{{font:15px/1.7 system-ui,sans-serif;color:#15283b;background:#f4f7fb;max-width:1180px;margin:36px auto;padding:0 24px}}
h1{{font-size:26px;margin:0 0 4px}} h2{{margin-top:40px;border-top:1px solid #c9d4df;padding-top:22px;font-size:19px}}
.meta{{color:#5a6b7d;font-size:13px;margin-bottom:20px}}
.cards{{display:flex;flex-wrap:wrap;gap:14px;margin:18px 0}}
.card{{background:#fff;border:1px solid #dbe3ec;border-radius:10px;padding:14px 18px;min-width:150px}}
.card .v{{font-size:26px;font-weight:700;color:#1163ad}} .card .k{{font-size:12px;color:#5a6b7d}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px;margin:12px 0}}
td,th{{border:1px solid #dbe3ec;padding:8px 12px;text-align:left}}
th{{background:#e5eef8;font-weight:700}}
.cert{{border:1px solid {cert_color};background:#fff;border-radius:10px;padding:14px 18px;font-size:16px;font-weight:700;color:{cert_color};margin:18px 0}}
svg{{background:#fff;border:1px solid #dbe3ec;border-radius:10px;margin:12px 0}}
.scroll{{overflow:auto;max-height:520px}}
</style><body>

<h1>配平后的两队</h1>
<div class="meta">新 agent（{_esc(config['treat_col'])} = {_esc(config['treat_value'])}）{r['n_treated']} 条 ↔ 老 agent {r['n_control']} 条 · 按维度「{_esc(', '.join(config['cov_cols']))}」配成 {r['n_matched']} 对（用到老 agent {r['n_matched_control_distinct']} 条）</div>

<h2>两组在维度上是否可比</h2>
<div class="cert">{cert_text}</div>
<div class="cards">
<div class="card"><div class="v">{_fmt(bsum['max_smd_after'])}</div><div class="k">配平后最大差异度（&lt;0.1 即可比）</div></div>
<div class="card"><div class="v">{('—' if bsum['mean_bias_reduction'] is None or (isinstance(bsum['mean_bias_reduction'], float) and np.isnan(bsum['mean_bias_reduction'])) else f"{bsum['mean_bias_reduction']*100:.0f}%")}</div><div class="k">平均差异降低</div></div>
</div>
<p style="font-size:13px;color:#5a6b7d">橙=配平前，绿=配平后；点越靠近 0 说明两队越像。红色虚线为差异度 0.1。</p>
{_love_plot(r['balance'])}

<h2>各组维度对比</h2>
<table><tr><th>维度</th><th>差异度 前</th><th>差异度 后</th><th>差异降低</th></tr>{_balance_rows_html(r['balance'])}</table>

<h2>各维度的分布对比</h2>
<p style="font-size:13px;color:#5a6b7d">配平前两组分布有差异，配平后应基本重合——这是配平可信度最直观的证据。</p>
{dist_plots}

</body></html>"""


def build_cohort(df, config):
    """构建配对队列（谁配谁），用 Mahalanobis 卡尺匹配。"""
    id_col = config.get("id_col")
    t = psm.encode_treatment(df[config["treat_col"]], config["treat_value"])
    X, _ = psm.encode_covariates(df, config["cov_cols"])
    mt, mc = psm.match_pairs(X, t)
    if id_col and id_col in df.columns:
        ids = df[id_col].astype(str).tolist()
    else:
        ids = [str(i) for i in range(len(df))]
    matched = dict((ids[i], ids[c]) for i, c in zip(mt, mc))
    out = df.copy()
    out["row_id"] = ids
    out["_treatment"] = t.astype(int)
    out["matched_control_id"] = [matched.get(x) for x in ids]
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args(argv)

    with open(args.config, "r", encoding="utf-8-sig") as f:
        config = json.load(f)
    df = load_data(args.data)

    os.makedirs(args.outdir, exist_ok=True)

    if config.get("outcome_col"):
        # 经典 PSM：卡尺匹配配平 + 在配平后的两队上算效果
        r = psm.run_matching_with_effect(df, config)
        d = df[df[config["outcome_col"]].notna()].reset_index(drop=True)
        cohort = build_cohort(d, config)
        with open(os.path.join(args.outdir, "report.json"), "w", encoding="utf-8") as f:
            json.dump(_jsonable(r), f, ensure_ascii=False, indent=2, default=float)
        with open(os.path.join(args.outdir, "report.html"), "w", encoding="utf-8") as f:
            f.write(render_effect_report(r, config, d))
        cohort.to_json(os.path.join(args.outdir, "matched_cohort.jsonl"), orient="records", lines=True, force_ascii=False)
        cohort.to_csv(os.path.join(args.outdir, "matched_cohort.csv"), index=False)
        manifest = {
            "config": config,
            "n": r["n"],
            "n_treated": r["n_treated"],
            "n_control": r["n_control"],
            "n_matched": r["n_matched"],
            "n_matched_control_distinct": r["n_matched_control_distinct"],
            "missing_outcome": r["missing_outcome"],
            "balance": r["balance_summary"],
            "effect": r["effect"],
        }
    else:
        # 仅配平 + 配对
        r = psm.run_matching(df, config)
        cohort = build_cohort(df, config)
        with open(os.path.join(args.outdir, "report.json"), "w", encoding="utf-8") as f:
            json.dump(_jsonable(r), f, ensure_ascii=False, indent=2, default=float)
        with open(os.path.join(args.outdir, "report.html"), "w", encoding="utf-8") as f:
            f.write(render_report(r, config, df))
        cohort.to_json(os.path.join(args.outdir, "matched_cohort.jsonl"), orient="records", lines=True, force_ascii=False)
        cohort.to_csv(os.path.join(args.outdir, "matched_cohort.csv"), index=False)
        manifest = {
            "config": config,
            "n": r["n"],
            "n_treated": r["n_treated"],
            "n_control": r["n_control"],
            "n_matched": r["n_matched"],
            "n_matched_control_distinct": r["n_matched_control_distinct"],
            "balance": r["balance_summary"],
        }

    with open(os.path.join(args.outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(_jsonable(manifest), f, ensure_ascii=False, indent=2, default=float)

    print(json.dumps(_jsonable(manifest), ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main(sys.argv[1:])

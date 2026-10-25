# -*- coding: utf-8 -*-
"""
run_full.py —— 完整因果效应分析 CLI（psm.run_analysis 的临时入口）。

背景：analyze.py 目前只调用 run_matching（仅配平 + 配对），未接 run_analysis
（效应估计 / 三法对拍 / cluster bootstrap CI / 置换检验 / E-value / MDE）。
在产品补齐该接线前，本脚本提供最小命令行入口，用于跑出完整“效应 + 可信度”结果。

用法（在仓库根目录）：
  python examples/run_full.py --data examples/testset_agent.csv \
      --config examples/testset_config_full.json --outdir runs/testset_benchmark

仅依赖 numpy / pandas / scikit-learn / scipy。
"""
import argparse
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
import psm  # noqa: E402


def load(path):
    if path.endswith((".jsonl", ".ndjson")):
        return pd.read_json(path, lines=True)
    if path.endswith(".json"):
        return pd.read_json(path)
    return pd.read_csv(path)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args(argv)

    df = load(args.data)
    cfg = json.load(open(args.config, encoding="utf-8"))
    r = psm.run_analysis(df, cfg)

    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        with open(os.path.join(args.outdir, "effect_report.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2, default=float)
        print("已写出 effect_report.json ->", args.outdir, "\n")

    e = r["estimates"]
    print("n=%d treated=%d control=%d  倾向AUC=%.3f" % (r["n"], r["n_treated"], r["n_control"], r["auc"]))
    print("NAIVE  = %+.4f" % e["naive"])
    print("IPW    = %+.4f" % e["ipw"]["att"])
    print("DR     = %+.4f" % e["dr"]["att"])
    print("MATCH  = %+.4f" % e["matching"]["att"])
    for k in ["ipw", "dr", "matching"]:
        ci = r["ci"].get(k)
        print("CI[%-9s] = %s" % (k, "None" if ci is None else
              "[%+.4f, %+.4f]" % (ci["lo"], ci["hi"])))
    bs = r["balance_summary"]
    print("配平: balanced=%s max|SMD|后=%.3f 平均偏倚降低=%.1f%%" % (
        bs["balanced"], bs["max_smd_after"], 100 * bs["mean_bias_reduction"]))
    print("ESS=%.0f(%.1f%%)  支撑域外treated=%d  置换p=%.4f  E-value=%.3f  MDE=%.4f" % (
        r["weight_diagnostics"]["ess"], 100 * r["weight_diagnostics"]["ess_ratio"],
        r["overlap"]["treated_out_of_support"],
        r["permutation"]["p_value"],
        r["evalue"]["e_value"] if r["evalue"] else float("nan"),
        r["mde"] if r["mde"] is not None else float("nan")))
    print("结局缺失行数 =", r["missing_outcome"])


if __name__ == "__main__":
    main(sys.argv[1:])

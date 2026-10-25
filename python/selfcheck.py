"""快速引擎自检：纯匹配 + 配平检查，几秒出结果。"""
import psm
from test_psm import simulate


def main():
    df, _ = simulate(4000, 1)
    df.insert(0, "session_id", [f"s_{i:06d}" for i in range(len(df))])
    config = {"id_col": "session_id", "treat_col": "agent", "treat_value": 1, "cov_cols": ["member_level", "prev_effective", "intent"]}
    r = psm.run_matching(df, config)
    ok = r["balance_summary"]["balanced"]
    print("引擎自检:", "通过" if ok else "失败")
    print(f"配对 {r['n_matched']} 对 · 配平后最大差异度={r['balance_summary']['max_smd_after']:.3f}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

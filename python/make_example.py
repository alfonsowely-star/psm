"""生成示例数据 + 配置，供 analyze.py 冒烟测试与用户上手。"""
import os
import json

from test_psm import simulate

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(HERE, "..", "examples")
os.makedirs(EXAMPLES, exist_ok=True)

csv_path = os.path.join(EXAMPLES, "sample.csv")
cfg_path = os.path.join(EXAMPLES, "config.json")

df, att_true = simulate(6000, 7)
df.insert(0, "session_id", [f"s_{i:06d}" for i in range(len(df))])
df.to_csv(csv_path, index=False)

config = {
    "id_col": "session_id",
    "treat_col": "agent",
    "treat_value": 1,
    "cov_cols": ["member_level", "prev_effective", "intent"],
}
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print("OK", csv_path)
print("OK", cfg_path)

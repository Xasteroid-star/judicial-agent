"""追加新用例到已有 LangSmith Dataset。

用法:
    python scripts/append_examples.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from langsmith import Client

DATASET_NAME = "Judicial Evidence Golden Cases v2"

client = Client()

cases_path = ROOT / "eval" / "golden_cases.json"
all_cases = json.loads(cases_path.read_text("utf-8"))

# 查已有 example 数
existing = list(client.list_examples(dataset_name=DATASET_NAME))
existing_count = len(existing)
print(f"已有 {existing_count} 条用例")

# 只上传新增的
new_cases = all_cases[existing_count:]
if not new_cases:
    print("没有新用例，golden_cases.json 和 Dataset 已同步。")
    sys.exit(0)

examples = []
for c in new_cases:
    exp = c["expected"]
    examples.append({
        "inputs": {
            "query": c["query"],
            "case_context": c["case_context"],
            "case_name": c["case_name"],
        },
        "outputs": {
            "evidence_chain_complete": str(exp["evidence_chain_complete"]),
            "confidence_min": str(exp.get("confidence_min", "")),
            "confidence_max": str(exp.get("confidence_max", "")),
            "expected_citations": "|".join(exp.get("expected_citations", [])),
            "expected_legal_basis": "|".join(exp.get("expected_legal_basis", [])),
            "should_contain": "|".join(exp.get("should_contain", [])),
            "should_not_contain": "|".join(exp.get("should_not_contain", [])),
        },
        "metadata": {
            "case_id": c["case_id"],
            "case_name": c["case_name"],
        },
    })

dataset = client.read_dataset(dataset_name=DATASET_NAME)
client.create_examples(dataset_id=dataset.id, examples=examples)
print(f"✅ 追加 {len(examples)} 条: {[c['case_name'] for c in new_cases]}")
print(f"🔗 当前共 {existing_count + len(examples)} 条: https://smith.langchain.com/datasets/{dataset.id}")

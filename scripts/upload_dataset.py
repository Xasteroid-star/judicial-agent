"""上传黄金评测集到 LangSmith Dataset。

用法:
    python scripts/upload_dataset.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# 必须最先：把 .env 中的 LANGCHAIN_API_KEY 等注入 os.environ
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from langsmith import Client

client = Client()

cases_path = ROOT / "eval" / "golden_cases.json"
cases = json.loads(cases_path.read_text("utf-8"))

# 创建 dataset（v2：inputs 中带 case_name）
dataset = client.create_dataset(
    dataset_name="Judicial Evidence Golden Cases v2",
    description=(
        "司法证据链 Agent 的 5 条黄金评测集（v2，含 case_name），覆盖："
        "完整证据、证据严重不足、非法证据排除、电子数据为主、仅有口供"
    ),
)

examples = []
for c in cases:
    exp = c["expected"]

    inputs = {
        "query": c["query"],
        "case_context": c["case_context"],
        "case_name": c["case_name"],
    }

    outputs = {
        "evidence_chain_complete": str(exp["evidence_chain_complete"]),
        "confidence_min": str(exp.get("confidence_min", "")),
        "confidence_max": str(exp.get("confidence_max", "")),
        "expected_citations": "|".join(exp.get("expected_citations", [])),
        "expected_legal_basis": "|".join(exp.get("expected_legal_basis", [])),
        "should_contain": "|".join(exp.get("should_contain", [])),
        "should_not_contain": "|".join(exp.get("should_not_contain", [])),
    }

    examples.append({
        "inputs": inputs,
        "outputs": outputs,
        "metadata": {
            "case_id": c["case_id"],
            "case_name": c["case_name"],
        },
    })

client.create_examples(dataset_id=dataset.id, examples=examples)
print(f"✅ 已上传 {len(examples)} 条用例")
print(f"🔗 Dataset: https://smith.langchain.com/datasets/{dataset.id}")

"""从 CAIL 样本数据批量导入评测用例到 LangSmith。

用法:
    python scripts/import_cail_cases.py              # 导入全部 100 条
    python scripts/import_cail_cases.py --limit 30    # 只导入 30 条
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from langsmith import Client

# ── CAIL decision_type → 证据链预期 ──
# P=有罪(证据充分), N=无罪(证据不足/不构成), U=未知
DECISION_MAP = {
    "P": {"complete": True, "conf_min": 0.70, "conf_max": 0.98},
    "N": {"complete": False, "conf_min": 0.00, "conf_max": 0.50},
    "U": {"complete": False, "conf_min": 0.00, "conf_max": 0.70},
}


def load_cail_samples(data_dir: Path) -> list[dict]:
    """加载所有 CAIL 样本文件。"""
    cases = []
    for fname in ["train.jsonl", "test.jsonl", "validation.jsonl"]:
        fpath = data_dir / fname
        if not fpath.exists():
            continue
        for line in fpath.read_text("utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return cases


def build_example(c: dict) -> dict | None:
    """将一条 CAIL 记录转为 LangSmith example。"""
    fact = c.get("fact", "").strip()
    charge = c.get("charge", "未知罪名")
    article = c.get("article", "")
    decision = c.get("decision_type", "U")
    evidence_list = c.get("evidence_list", [])
    case_name = c.get("case_name", "")

    if not fact or len(fact) < 20:
        return None  # 跳过空的

    # 证据名称列表
    ev_names = [e.get("name", "") for e in evidence_list if e.get("name")]
    ev_types = list({e.get("type", "") for e in evidence_list if e.get("type")})

    # 预期结果
    dm = DECISION_MAP.get(decision, DECISION_MAP["U"])
    is_complete = dm["complete"]

    # should_contain: 罪名、法条关键词
    should_contain = []
    if charge and len(charge) < 50:
        should_contain.append(charge[:20])
    if article:
        should_contain.append(f"第{article}条")

    # should_not_contain
    should_not = []
    if is_complete:
        should_not = ["证据不足", "无法认定", "不能认定"]
    else:
        should_not = ["证据确实充分", "足以认定"]

    return {
        "inputs": {
            "query": f"该案证据链是否完整？能否认定{charge}？",
            "case_context": fact[:800],  # 截断过长文本
            "case_name": case_name[:40] or f"CAIL-{c.get('case_id', '?')[:8]}",
        },
        "outputs": {
            "evidence_chain_complete": str(is_complete),
            "confidence_min": str(dm["conf_min"]),
            "confidence_max": str(dm["conf_max"]),
            "expected_citations": "|".join(ev_names[:5]) if ev_names else "",
            "expected_legal_basis": f"刑法第{article}条" if article else "",
            "should_contain": "|".join(should_contain[:5]),
            "should_not_contain": "|".join(should_not),
        },
        "metadata": {
            "case_id": c.get("case_id", ""),
            "case_name": case_name[:40],
            "charge": charge,
            "decision": decision,
            "source": c.get("source", "cail"),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="限制导入条数（0=全部）")
    parser.add_argument("--dataset", default="CAIL 100 Cases v1",
                        help="Dataset 名称")
    args = parser.parse_args()

    data_dir = ROOT / "data" / "samples"
    all_cases = load_cail_samples(data_dir)
    print(f"📂 从 CAIL 加载 {len(all_cases)} 条样本")

    examples = []
    skipped = 0
    for c in all_cases:
        ex = build_example(c)
        if ex:
            examples.append(ex)
        else:
            skipped += 1
        if args.limit and len(examples) >= args.limit:
            break

    if skipped:
        print(f"⏭ 跳过 {skipped} 条（空内容）")

    client = Client()
    dataset = client.create_dataset(
        dataset_name=args.dataset,
        description=f"从 CAIL 样本数据集导入的 {len(examples)} 条刑事案件，"
                    f"自动标注证据链预期（基于判决结果）",
    )

    # 分批上传（每批 20 条）
    batch_size = 20
    for i in range(0, len(examples), batch_size):
        batch = examples[i:i + batch_size]
        client.create_examples(dataset_id=dataset.id, examples=batch)
        print(f"  📤 已上传 {min(i + batch_size, len(examples))}/{len(examples)}")

    print(f"\n✅ 完成: {len(examples)} 条")
    print(f"🔗 https://smith.langchain.com/datasets/{dataset.id}")
    print(f"\n运行评测:")
    print(f"  python eval/langsmith_eval.py --dataset '{args.dataset}' --experiment deepseek-v4-cail100")


if __name__ == "__main__":
    main()

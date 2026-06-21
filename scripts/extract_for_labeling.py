"""从 CAIL 数据中提取证据信息较丰富的案例，生成待标注的 golden cases。

用法:
    python scripts/extract_for_labeling.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

data_dir = ROOT / "data" / "samples"
all_cases = []
for fname in ["train.jsonl", "test.jsonl", "validation.jsonl"]:
    fpath = data_dir / fname
    if fpath.exists():
        for line in fpath.read_text("utf-8").strip().split("\n"):
            if line.strip():
                try:
                    all_cases.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

# 筛选有证据列表且描述较完整的案例
rich = []
for c in all_cases:
    fact = c.get("fact", "")
    ev_list = c.get("evidence_list", [])
    charge = c.get("charge", "")
    decision = c.get("decision_type", "")

    # 要求：fact>=60字，evidence_list>=1条，有明确证据名称
    if len(fact) < 60:
        continue
    if not ev_list:
        continue
    has_named = any(e.get("name", "") and len(e.get("name", "")) > 3 for e in ev_list)
    if not has_named:
        continue

    rich.append(c)

print(f"从 {len(all_cases)} 条中筛选出 {len(rich)} 条证据信息较丰富的案例")

# 挑 10 条不同类型
seen_charges = set()
picked = []
for c in rich:
    charge = c.get("charge", "")
    if charge not in seen_charges or len(picked) < 10:
        if charge not in seen_charges:
            seen_charges.add(charge)
        picked.append(c)
    if len(picked) >= 10:
        break

print(f"选取 {len(picked)} 条（覆盖 {len(seen_charges)} 种罪名）\n")

# 生成 golden cases 格式（expected 留空待标注）
golden = []
for i, c in enumerate(picked):
    fact = c.get("fact", "")
    ev_list = c.get("evidence_list", [])
    charge = c.get("charge", "未知")
    decision = c.get("decision_type", "U")
    case_name = c.get("case_name", "")

    # 提取证据信息
    ev_types = []
    ev_names = []
    for ev in ev_list:
        t = ev.get("type", "")
        n = ev.get("name", "")
        d = ev.get("description", "")
        if t and t not in ev_types:
            ev_types.append(t)
        if n:
            ev_names.append(f"{n}: {d[:60]}" if d else n)

    print(f"{'='*60}")
    print(f"案例 {i+1}: {case_name}")
    print(f"罪名: {charge} | 判决: {decision}")
    print(f"案情: {fact[:300]}")
    print(f"证据类型: {', '.join(ev_types)}")
    print(f"证据详情:")
    for ev in ev_list:
        print(f"  - [{ev.get('type','?')}] {ev.get('name','?')}: {ev.get('description','')[:100]}")
    print()

    golden.append({
        "case_id": f"cail-labeled-{i+1:03d}",
        "case_name": f"{case_name}（{charge}）",
        "query": f"该案证据链是否完整？能否认定{charge}？",
        "case_context": f"{fact}\n\n证据材料：{'；'.join(ev_names[:5])}",
        "expected": {
            "evidence_chain_complete": "TODO: true/false",
            "confidence_min": "TODO",
            "confidence_max": "TODO",
            "expected_citations": "TODO: 证据1|证据2|...",
            "expected_legal_basis": "TODO: 刑法第X条",
            "should_contain": "TODO",
            "should_not_contain": "TODO"
        }
    })

# 写入文件
out_path = ROOT / "eval" / "golden_cases_to_label.json"
out_path.write_text(
    json.dumps(golden, ensure_ascii=False, indent=2),
    encoding="utf-8"
)
print(f"\n已写入: {out_path}")
print("请编辑此文件，将 TODO 替换为正确的预期值，然后:")
print(f"  python scripts/append_examples.py  # 上传到 LangSmith")

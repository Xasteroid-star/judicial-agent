"""案例自动标注脚本 — LLM 提取核心争议 + 关联法条。

用法:
    python scripts/label_cases.py                     # 标注全部案例
    python scripts/label_cases.py --case-id golden-001 # 标一条
    python scripts/label_cases.py --dry-run            # 预览不写入
    python scripts/label_cases.py --review             # 查看待复核列表
    python scripts/label_cases.py --confirm CASE_ID    # 确认一条
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


async def label_all(dry_run: bool = False):
    """从 SQLite 中读取所有未标注案例，逐条标注。"""
    import sqlite3
    from judicial_evidence_agent.core.case_annotator import CaseAnnotator

    db_path = Path(__file__).resolve().parent.parent / "data" / "judicial_evidence.db"
    conn = sqlite3.connect(str(db_path))
    # 只标未标注的（不在 annotated_cases 里的）
    rows = conn.execute("""
        SELECT c.case_id, c.case_name, c.description
        FROM cases c
        WHERE NOT EXISTS (
            SELECT 1 FROM annotated_cases a WHERE a.case_id = c.case_id
        )
    """).fetchall()
    conn.close()

    if not rows:
        print("没有待标注的案例。")
        return

    print(f"待标注案例: {len(rows)} 条\n")
    annotator = CaseAnnotator(db_path=str(db_path))

    for i, (case_id, case_name, description) in enumerate(rows, 1):
        if not description:
            continue
        print(f"[{i}/{len(rows)}] {case_name[:40]}...")

        if dry_run:
            # 规则降级标注预览
            result = CaseAnnotator._rule_based_annotate(description)
            print(f"  争议点: {result.get('core_disputes', [])}")
            print(f"  罪名: {result.get('charges', [])}")
            print(f"  证据类型: {result.get('evidence_types', [])}")
        else:
            try:
                case = await annotator.annotate(case_id, case_name, description)
                annotator.save(case)
                print(f"  争议点: {case.core_disputes}")
                print(f"  罪名: {case.charges}")
                print(f"  状态: {case.review_status}")
            except Exception as e:
                print(f"  失败: {e}")


def show_reviews():
    """查看待复核列表。"""
    from judicial_evidence_agent.core.case_annotator import CaseAnnotator

    db_path = Path(__file__).resolve().parent.parent / "data" / "judicial_evidence.db"
    annotator = CaseAnnotator(db_path=str(db_path))
    pending = annotator.get_pending_reviews()

    if not pending:
        print("没有待复核的标注。")
        return

    print(f"待复核: {len(pending)} 条\n")
    for r in pending:
        print(f"  [{r['case_id']}] {r['case_name']}")
        print(f"    争议点: {r['core_disputes']}")
        print(f"    罪名: {r['charges']}")
        print(f"    摘要: {r['case_summary']}")
        print()


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--case-id", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--review", action="store_true", help="查看待复核列表")
    p.add_argument("--confirm", default="", help="确认一条标注")
    p.add_argument("--reject", default="", help="驳回一条标注")
    p.add_argument("--reason", default="", help="驳回理由")
    args = p.parse_args()

    db_path = Path(__file__).resolve().parent.parent / "data" / "judicial_evidence.db"

    if args.review:
        show_reviews()
        return

    if args.confirm:
        from judicial_evidence_agent.core.case_annotator import CaseAnnotator
        annotator = CaseAnnotator(db_path=str(db_path))
        annotator.confirm(args.confirm)
        print(f"已确认: {args.confirm}")
        return

    if args.reject:
        from judicial_evidence_agent.core.case_annotator import CaseAnnotator
        annotator = CaseAnnotator(db_path=str(db_path))
        annotator.reject(args.reject, args.reason)
        print(f"已驳回: {args.reject}")
        return

    asyncio.run(label_all(args.dry_run))


if __name__ == "__main__":
    main()

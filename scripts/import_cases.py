"""将下载的数据集导入 PostgreSQL。

用法:
    python scripts/import_cases.py                    # 导入全部
    python scripts/import_cases.py --dataset cail2018 # 仅 CAIL
    python scripts/import_cases.py --dataset pdp_bench # 仅 PDP
    python scripts/import_cases.py --dry-run           # 预览不写入
"""

import argparse
import json
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def parse_args():
    p = argparse.ArgumentParser(description="导入法律案例数据集到 PostgreSQL")
    p.add_argument("--dataset", choices=["cail2018", "pdp_bench", "all"], default="all")
    p.add_argument("--dry-run", action="store_true", help="预览不写入")
    p.add_argument("--limit", type=int, default=0, help="限制导入条数（0=全部）")
    p.add_argument("--db-url", default="postgresql+asyncpg://postgres:postgres@localhost:5432/judicial_evidence")
    return p.parse_args()


def load_jsonl(path: Path, limit: int = 0) -> list[dict]:
    """加载 JSONL 文件。"""
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            rows.append(json.loads(line))
    return rows


def import_cail2018(data_dir: Path, dry_run: bool, limit: int):
    """导入 CAIL 2018 数据。

    每条记录结构:
        fact: 事实描述
        meta: {
            relevant_articles: [法条编号],
            accusation: [罪名],
            criminals: [被告人],
            term_of_imprisonment: {imprisonment, death_penalty, life_imprisonment}
        }
    """
    train_path = data_dir / "cail2018" / "train.jsonl"
    if not train_path.exists():
        print(f"文件不存在: {train_path}")
        print("请先运行: python scripts/download_cail2018.py")
        return

    cases = load_jsonl(train_path, limit)
    print(f"CAIL 2018: 加载 {len(cases)} 条")

    if dry_run:
        sample = cases[0]
        print(f"  示例: {sample.get('fact', '')[:200]}...")
        print(f"  标签: 罪名={sample.get('meta', {}).get('accusation')}")
        return

    # TODO: 写入 PostgreSQL（需要 async engine）
    print(f"  准备写入 {len(cases)} 条案件到 cases 表...")
    print("  (数据库写入在 connect_db 阶段实现)")


def import_pdp_bench(data_dir: Path, dry_run: bool, limit: int):
    """导入 PDP-Bench 数据。

    每条记录结构:
        fact: 案件事实
        evidence_list: 结构化证据列表
        decision_type: 4分类（IENP/SNP/DNP/P）
        charge: 罪名
    """
    train_path = data_dir / "pdp_bench" / "train.jsonl"
    if not train_path.exists():
        print(f"文件不存在: {train_path}")
        print("请先运行: python scripts/download_pdp_bench.py")
        return

    cases = load_jsonl(train_path, limit)
    print(f"PDP-Bench: 加载 {len(cases)} 条")

    if dry_run:
        sample = cases[0]
        print(f"  事实: {sample.get('fact', '')[:200]}...")
        print(f"  证据列表: {sample.get('evidence_list', [])[:3]}")
        print(f"  决定类型: {sample.get('decision_type')}")
        return

    print(f"  准备写入 {len(cases)} 条案件到 cases 表...")
    print("  (数据库写入在 connect_db 阶段实现)")


def main():
    args = parse_args()
    data_dir = Path(__file__).resolve().parent.parent / "data"

    if args.dataset in ("cail2018", "all"):
        import_cail2018(data_dir, args.dry_run, args.limit)
    if args.dataset in ("pdp_bench", "all"):
        import_pdp_bench(data_dir, args.dry_run, args.limit)


if __name__ == "__main__":
    main()

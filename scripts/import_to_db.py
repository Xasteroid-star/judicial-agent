"""将切分后的样本数据导入数据库。

支持 PostgreSQL（生产）和 SQLite（本地开发无 PG 时自动回退）。

用法:
    python scripts/import_to_db.py                    # 自动检测
    python scripts/import_to_db.py --db sqlite        # 强制 SQLite
    python scripts/import_to_db.py --db postgres      # 强制 PostgreSQL
    python scripts/import_to_db.py --dry-run          # 预览不写入
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"
DB_DIR = Path(__file__).resolve().parent.parent / "data"


def ensure_tables(conn, db_type: str):
    """创建数据库表（SQLite 兼容 schema）。"""
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY,
            case_name TEXT NOT NULL,
            case_number TEXT NOT NULL,
            case_type TEXT DEFAULT '刑事',
            description TEXT DEFAULT '',
            source TEXT DEFAULT '',
            source_id TEXT DEFAULT '',
            charge TEXT DEFAULT '',
            article TEXT DEFAULT '',
            decision_type TEXT DEFAULT '',
            decision_label TEXT DEFAULT '',
            term_months INTEGER DEFAULT 0,
            created_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS materials (
            material_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'document',
            source_org TEXT DEFAULT '',
            collector TEXT DEFAULT '',
            confidentiality_level TEXT DEFAULT 'medium',
            file_hash TEXT DEFAULT '',
            file_path TEXT DEFAULT '',
            version INTEGER DEFAULT 1,
            processing_status TEXT DEFAULT 'completed',
            received_at TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            FOREIGN KEY (case_id) REFERENCES cases(case_id)
        );

        CREATE TABLE IF NOT EXISTS evidence_chunks (
            chunk_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            material_id TEXT NOT NULL,
            modality TEXT DEFAULT 'text',
            content_text TEXT DEFAULT '',
            extracted_elements TEXT DEFAULT '{}',
            source_pointer TEXT DEFAULT '{}',
            confidence REAL DEFAULT 1.0,
            model_version TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            FOREIGN KEY (case_id) REFERENCES cases(case_id),
            FOREIGN KEY (material_id) REFERENCES materials(material_id)
        );
    """)
    conn.commit()


def import_cases(conn, db_type: str, dry_run: bool = False):
    """导入所有样本数据。"""
    from judicial_evidence_agent.core.corpus.chunk import case_to_chunks

    cur = conn.cursor()
    stats = {"cases": 0, "materials": 0, "chunks": 0}

    for fname in ["train.jsonl", "validation.jsonl", "test.jsonl"]:
        path = DATA_DIR / fname
        if not path.exists():
            print(f"  跳过: {fname} (不存在)")
            continue

        with open(path, encoding="utf-8") as f:
            cases = [json.loads(line) for line in f]

        for case in cases:
            case_id = case["case_id"]

            # 1. 写入 case
            cur.execute(
                """INSERT OR REPLACE INTO cases
                   (case_id, case_name, case_number, case_type, description,
                    source, source_id, charge, article, decision_type, decision_label,
                    term_months, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    case_id,
                    case.get("case_name", ""),
                    case.get("case_number", ""),
                    case.get("case_type", "刑事"),
                    case.get("description", "") or case.get("fact", ""),
                    case.get("source", ""),
                    case.get("source_id", ""),
                    case.get("charge", ""),
                    case.get("article", ""),
                    case.get("decision_type", ""),
                    case.get("decision_label", ""),
                    case.get("term_months", 0),
                    case.get("created_at", ""),
                ),
            )
            stats["cases"] += 1

            # 2. 创建 material（整个案卷材料一份）
            import hashlib
            material_id = hashlib.md5(
                (case_id + "material").encode()
            ).hexdigest()[:32]

            cur.execute(
                """INSERT OR REPLACE INTO materials
                   (material_id, case_id, name, type, processing_status, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    material_id,
                    case_id,
                    f"{case.get('case_name', '')} - 案卷材料",
                    "document",
                    "completed",
                    case.get("created_at", ""),
                ),
            )
            stats["materials"] += 1

            # 3. 切分并写入 evidence_chunks
            chunks = case_to_chunks(case)
            for ch in chunks:
                cur.execute(
                    """INSERT OR REPLACE INTO evidence_chunks
                       (chunk_id, case_id, material_id, modality, content_text,
                        extracted_elements, source_pointer, confidence, model_version, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ch["chunk_id"],
                        case_id,
                        material_id,
                        ch.get("modality", "text"),
                        ch.get("content_text", ""),
                        json.dumps(ch.get("extracted_elements", {}), ensure_ascii=False),
                        json.dumps(ch.get("source_pointer", {}), ensure_ascii=False),
                        ch.get("confidence", 1.0),
                        ch.get("model_version", ""),
                        case.get("created_at", ""),
                    ),
                )
                stats["chunks"] += 1

        if dry_run:
            print(f"  [DRY RUN] {fname}: {len(cases)} 条")
        else:
            conn.commit()
            print(f"  {fname}: {len(cases)} 案件, {stats['chunks']} chunks")

    return stats


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--db", choices=["sqlite", "postgres"], default="sqlite")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--db-url", default="")
    args = p.parse_args()

    if args.db == "postgres":
        try:
            import psycopg2
            url = args.db_url or "postgresql://postgres:postgres@localhost:5432/judicial_evidence"
            conn = psycopg2.connect(url)
            print(f"PostgreSQL 连接成功: {url}")
        except Exception as e:
            print(f"PostgreSQL 连接失败 ({e})，回退到 SQLite")
            args.db = "sqlite"

    if args.db == "sqlite":
        import sqlite3
        db_path = DB_DIR / "judicial_evidence.db"
        conn = sqlite3.connect(str(db_path))
        print(f"SQLite: {db_path}")

    ensure_tables(conn, args.db)

    if args.dry_run:
        print("[DRY RUN 模式] 不写入数据\n")

    stats = import_cases(conn, args.db, args.dry_run)

    if not args.dry_run:
        print(f"\n导入完成: {stats['cases']} 案件, "
              f"{stats['materials']} 材料, {stats['chunks']} chunks")

    conn.close()


if __name__ == "__main__":
    main()

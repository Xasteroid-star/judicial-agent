"""中文向量索引 — 用 numpy + json 替代 Chroma，避免 segfault。

用法:
    python scripts/build_vector_index.py              # 首次建索引
    python scripts/build_vector_index.py --search "故意伤害"  # 测试
"""

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

INDEX_DIR = ROOT / "data" / "bge_index"
INDEX_DIR.mkdir(parents=True, exist_ok=True)


def _get_content(c: dict) -> str:
    """兼容 content 和 content_text 两种字段名。"""
    return (c.get("content") or c.get("content_text") or "")[:2000]


def load_case_chunks(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT chunk_id, case_id, content_text, extracted_elements FROM evidence_chunks WHERE content_text != ''"
    ).fetchall()
    conn.close()
    chunks = []
    for r in rows:
        try:
            elems = json.loads(r[3]) if r[3] else {}
        except Exception:
            elems = {}
        chunks.append({
            "chunk_id": r[0], "case_id": r[1],
            "content": r[2] or "", "source_type": "case",
            "evidence_type": elems.get("evidence_type", ""),
        })
    return chunks


def load_law_chunks() -> list[dict]:
    import yaml
    from judicial_evidence_agent.core.corpus.chunk import split_law_as_chunks

    all_chunks = []
    for meta_path in sorted((ROOT / "corpus").glob("*.meta.yaml")):
        law_id = meta_path.stem.replace(".meta", "")
        md_path = ROOT / "corpus" / f"{law_id}.md"
        if not md_path.exists():
            continue
        with open(meta_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f)
        text = md_path.read_text(encoding="utf-8")
        chunks = split_law_as_chunks(text, law_id, metadata=meta)
        for c in chunks:
            c["source_type"] = "statute"
            c["effective_date"] = meta.get("effective_date", "")
            c["law_name"] = meta.get("law_name", "")
            c["case_id"] = ""
        all_chunks.extend(chunks)
    return all_chunks


def build_index():
    """加载 chunk，用 HuggingFaceEmbeddings（参考 SuperMew），存入 numpy + json。"""
    from sentence_transformers import SentenceTransformer

    print("Loading chunks...")
    case_chunks = load_case_chunks(ROOT / "data" / "judicial_evidence.db")
    law_chunks = load_law_chunks()
    all_chunks = case_chunks + law_chunks
    print(f"Case: {len(case_chunks)}, Law: {len(law_chunks)}, Total: {len(all_chunks)}")

    print("Loading BGE model...")
    model = SentenceTransformer("BAAI/bge-small-zh-v1.5", device="cpu")

    print("Encoding...")
    documents = [_get_content(c) for c in all_chunks]
    embeddings = model.encode(documents, show_progress_bar=True, batch_size=32, normalize_embeddings=True)
    embeddings = np.array(embeddings, dtype=np.float32)
    print(f"Embeddings shape: {embeddings.shape}")

    # 保存向量
    np.save(str(INDEX_DIR / "embeddings.npy"), embeddings)
    print(f"Saved embeddings.npy: {embeddings.shape}")

    # 保存元数据
    metadata = []
    for c in all_chunks:
        metadata.append({
            "chunk_id": c["chunk_id"], "case_id": c.get("case_id", ""),
            "content": _get_content(c), "source_type": c.get("source_type", "case"),
            "evidence_type": c.get("evidence_type", ""),
            "effective_date": c.get("effective_date", ""),
            "law_name": c.get("law_name", ""),
        })
    (INDEX_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Saved metadata.json: {len(metadata)} entries")
    print(f"\nIndex built at: {INDEX_DIR}")


def search(query: str, top_k: int = 10) -> list[dict]:
    """检索：加载索引，计算余弦相似度，返回 top_k 结果。"""
    from sentence_transformers import SentenceTransformer

    embeddings = np.load(str(INDEX_DIR / "embeddings.npy"))
    metadata = json.loads((INDEX_DIR / "metadata.json").read_text("utf-8"))

    model = SentenceTransformer("BAAI/bge-small-zh-v1.5", device="cpu")
    q_emb = model.encode([query], show_progress_bar=False, normalize_embeddings=True)[0]

    # 余弦相似度（向量已归一化，直接点积）
    similarities = np.dot(embeddings, q_emb)
    top_indices = np.argsort(similarities)[::-1][:top_k * 2]

    hits = []
    for idx in top_indices:
        meta = metadata[idx]
        hits.append({
            **meta,
            "distance": round(float(1.0 - similarities[idx]), 4),
        })

    # 排序：法条优先（日期倒序），案件证据优先（相似度）
    statutes = sorted(
        [h for h in hits if h["effective_date"]],
        key=lambda h: h["effective_date"], reverse=True,
    )
    cases = sorted(
        [h for h in hits if not h["effective_date"]],
        key=lambda h: h["distance"],
    )
    return (statutes + cases)[:top_k]


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--search", type=str, default="", help="测试检索")
    p.add_argument("--top-k", type=int, default=5)
    args = p.parse_args()

    if args.search:
        print(f"\n查询: {args.search}")
        hits = search(args.search, args.top_k)
        for i, h in enumerate(hits, 1):
            badge = "法条" if h["effective_date"] else "案件"
            date = h.get("effective_date", "")[:10]
            print(f"  #{i} [{badge}|{date}] dist={h['distance']:.4f} {h['content'][:100]}")
    else:
        build_index()
        # 默认测试
        print("\n测试检索:")
        for q in ["故意伤害", "口供 补强", "电子数据 完整性", "非法证据排除"]:
            print(f"\n  查询: {q}")
            hits = search(q, 3)
            for i, h in enumerate(hits, 1):
                badge = "法条" if h["effective_date"] else "案件"
                print(f"    [{badge}] dist={h['distance']:.4f} {h['content'][:100]}")

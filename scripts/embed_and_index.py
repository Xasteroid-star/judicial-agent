"""Embedding + 向量索引 — 将切分好的 chunk 向量化后写入向量库。

用法:
    python scripts/embed_and_index.py                  # 首次建索引
    python scripts/embed_and_index.py --reindex        # 重建索引
    python scripts/embed_and_index.py --search "转账金额4800元"  # 测试检索

Embedding 模型: sentence-transformers (BAAI/bge-small-zh-v1.5)
向量库: Chroma (本地持久化)
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "judicial_evidence.db"
CHROMA_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma_index"


def load_chunks_from_db(db_path: Path) -> list[dict]:
    """从 SQLite 加载所有案件 evidence_chunks。"""
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("""
        SELECT chunk_id, case_id, material_id, modality,
               content_text, extracted_elements, source_pointer, confidence
        FROM evidence_chunks
        WHERE content_text != ''
    """)
    rows = cur.fetchall()
    conn.close()

    chunks = []
    for r in rows:
        chunks.append({
            "chunk_id": r[0],
            "case_id": r[1],
            "material_id": r[2],
            "modality": r[3],
            "content_text": r[4],
            "extracted_elements": json.loads(r[5]) if r[5] else {},
            "source_pointer": json.loads(r[6]) if r[6] else {},
            "confidence": r[7],
            "source_type": "case",
        })
    return chunks


def load_law_chunks() -> list[dict]:
    """加载法条 corpus 并切分为 chunks（带时效信息）。"""
    import yaml
    from judicial_evidence_agent.core.corpus.chunk import split_law_as_chunks

    corpus_dir = Path(__file__).resolve().parent.parent / "corpus"
    all_chunks = []
    for meta_path in sorted(corpus_dir.glob("*.meta.yaml")):
        law_id = meta_path.stem.replace(".meta", "")
        md_path = corpus_dir / f"{law_id}.md"
        if not md_path.exists():
            continue
        with open(meta_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f)
        text = md_path.read_text(encoding="utf-8")
        chunks = split_law_as_chunks(text, law_id, metadata=meta)
        # 打上来源标记
        for c in chunks:
            c["source_type"] = "statute"
            c["effective_date"] = meta.get("effective_date", "")
            c["law_name"] = meta.get("law_name", "")
        all_chunks.extend(chunks)
    return all_chunks


def build_index(chunks: list[dict], chroma_dir: Path, reindex: bool = False):
    """将 chunks 手动向量化并写入 Chroma（避免 Chroma EF 的 segfault）。"""
    import chromadb
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("BAAI/bge-small-zh-v1.5", device="cpu")
    print("Embedding: BAAI/bge-small-zh-v1.5 (中文，手动嵌入)")

    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection_name = "judicial_evidence_chunks_v2"

    if reindex:
        try:
            client.delete_collection(collection_name)
            print(f"删除旧索引: {collection_name}")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"description": "司法证据链 chunk 向量索引（BGE 中文）"},
    )

    batch_size = 32
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]

        ids = [c["chunk_id"] for c in batch]
        documents = [c["content_text"][:2000] for c in batch]
        metadatas = [
            {
                "case_id": c.get("case_id", ""),
                "material_id": c.get("material_id", ""),
                "modality": c.get("modality", "text"),
                "confidence": c.get("confidence", 1.0),
                "source_type": c.get("source_type", "case"),
                "evidence_type": c.get("extracted_elements", {}).get("evidence_type", ""),
                "effective_date": c.get("effective_date", ""),
                "law_name": c.get("law_name", ""),
            }
            for c in batch
        ]

        # 手动嵌入
        embeddings = model.encode(documents, show_progress_bar=False).tolist()

        try:
            collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
        except Exception as e:
            print(f"  batch {i // batch_size} 写入失败: {e}")

        if (i // batch_size) % 10 == 0:
            print(f"  {min(i + batch_size, len(chunks))}/{len(chunks)} 条已索引...")

    print(f"\n索引完成: {collection.count()} 条向量")
    return collection


def search(collection, query: str, top_k: int = 10) -> list[dict]:
    """检索并按时间降序排列（新法优先）。"""
    results = collection.query(
        query_texts=[query],
        n_results=top_k * 2,  # 多取一些用于排序
    )
    hits = []
    for i, (doc_id, doc, meta, dist) in enumerate(zip(
        results["ids"][0],
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    )):
        hits.append({
            "chunk_id": doc_id,
            "content": doc[:150] + "..." if len(doc) > 150 else doc,
            "case_id": meta.get("case_id", "")[:8],
            "source_type": meta.get("source_type", ""),
            "evidence_type": meta.get("evidence_type", ""),
            "effective_date": meta.get("effective_date", ""),
            "law_name": meta.get("law_name", ""),
            "distance": round(dist, 4),
        })

    # 法条：最新在前，其次按距离。案件证据：排在法条后，按距离。
    statutes = [h for h in hits if h["effective_date"]]
    cases = [h for h in hits if not h["effective_date"]]
    statutes.sort(key=lambda h: h["effective_date"], reverse=True)  # 新→旧
    cases.sort(key=lambda h: h["distance"])  # 近→远
    return (statutes + cases)[:top_k]


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--reindex", action="store_true", help="重建全部索引")
    p.add_argument("--search", type=str, default="", help="测试检索")
    p.add_argument("--top-k", type=int, default=5)
    args = p.parse_args()

    print("加载 chunks...")
    case_chunks = load_chunks_from_db(DB_PATH)
    law_chunks = load_law_chunks()
    chunks = case_chunks + law_chunks
    print(f"案件: {len(case_chunks)} chunks, 法条: {len(law_chunks)} chunks, 总计: {len(chunks)}\n")

    collection = build_index(chunks, CHROMA_DIR, reindex=args.reindex)

    if args.search:
        print(f"\n检索: '{args.search}'")
        hits = search(collection, args.search, args.top_k)
        for i, h in enumerate(hits, 1):
            badge = "法条" if h.get("effective_date") else "案件"
            date_str = h.get("effective_date", "")[:10]
            print(f"  #{i} [{badge}] {h['content'][:80]}")
            print(f"      距离={h['distance']} 日期={date_str}")
    else:
        # 默认跑一条测试
        print("\n测试检索: '非法证据排除'")
        hits = search(collection, "非法证据排除", 5)
        for i, h in enumerate(hits, 1):
            badge = "法条" if h.get("effective_date") else "案件"
            date_str = h.get("effective_date", "")[:10] if h.get("effective_date") else "-"
            print(f"  #{i} [{badge}|{date_str}] {h['content'][:80]}")

    print(f"\nChroma 索引位置: {CHROMA_DIR}")


if __name__ == "__main__":
    main()

"""Download PDP-Bench dataset from HuggingFace.

PDP-Bench — 检察院起诉/不起诉决定预测
- 规模: 4,630 份真实检察院决定书
- 内容: 结构化证据列表 + 嫌疑人信息 + 程序信息 + 190个罪名
- 核心价值: 证据充分性评估（4分类：存疑不起诉/法定不起诉/酌定不起诉/起诉）
- 来源: Julian2002/PDP-Bench
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "pdp_bench"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def download_pdp_bench():
    """从 HuggingFace 下载 PDP-Bench。"""
    try:
        from datasets import load_dataset
    except ImportError:
        print("请先安装: pip install datasets")
        return

    print("下载 PDP-Bench...")
    try:
        ds = load_dataset("Julian2002/PDP-Bench")
        for split in ds.keys():
            out = DATA_DIR / f"{split}.jsonl"
            subset = ds[split]
            with open(out, "w", encoding="utf-8") as f:
                for item in subset:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            print(f"  {split}: {out} ({len(subset)} 条)")
    except Exception as e:
        print(f"下载失败: {e}")
        print("手动下载: https://huggingface.co/datasets/Julian2002/PDP-Bench")

    print(f"\n完成。数据在 {DATA_DIR}")


if __name__ == "__main__":
    download_pdp_bench()

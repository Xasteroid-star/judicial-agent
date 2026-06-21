"""Download CAIL 2018 dataset from HuggingFace.

CAIL 2018 — 中国法律智能技术评测基准数据集
- 规模: 268万刑事裁判文书
- 内容: 事实描述 + 罪名 + 法条 + 刑期
- 来源: 最高人民法院
"""

import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "cail2018"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def download_cail2018():
    """从 HuggingFace 下载 CAIL 2018。

    如果网络受限，也可手动从 https://github.com/china-ai-law-challenge/CAIL2018
    下载并放到 data/cail2018/ 目录。
    """
    try:
        from datasets import load_dataset
    except ImportError:
        print("请先安装 datasets: pip install datasets")
        return

    print("下载 CAIL 2018...")
    for split in ["train", "test", "validation"]:
        print(f"  Loading {split}...")
        try:
            ds = load_dataset("cail2018", split=f"cail2018_{split}")
            out = DATA_DIR / f"{split}.jsonl"
            with open(out, "w", encoding="utf-8") as f:
                for item in ds:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            print(f"  -> {out} ({ds.num_rows} 条)")
        except Exception as e:
            print(f"  {split} 失败: {e}")

    print(f"\n完成。数据在 {DATA_DIR}")


if __name__ == "__main__":
    download_cail2018()

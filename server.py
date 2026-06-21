"""直接启动服务器 — 绕过 pip install 缓存，始终用最新源码。"""
import sys
from pathlib import Path

# 强制从 src/ 导入
sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "judicial_evidence_agent.api.main:app",
        host="127.0.0.1",
        port=9090,
        reload=True,
    )

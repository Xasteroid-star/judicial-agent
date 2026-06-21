"""
司法多模态证据链 Agent — core 包。

所有证据链核心逻辑在此定义，独立于 FastAPI 和前端。
API 层是薄壳，eval harness 和未来的 agent 都直接 import 此包。
"""

__version__ = "0.1.0"

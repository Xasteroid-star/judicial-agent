"""文档文本净化器 — 来自 SuperMew indexing/document_loader.py。

企业级标准：规范化 + 剔除不可见字符 + 编码收敛。
确保入库文本不含乱码、零宽字符、孤立代理项。
"""

import re
import unicodedata

# 非打印 C0/C1 控制字符（保留 \t \n \r）
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# 零宽字符和不可见格式化控制符
_INVISIBLE_CHAR_RE = re.compile(r"[​-‍﻿‏‪-‮]")


def sanitize_text(text: str) -> str:
    """企业级标准文本净化器。

    1. 规范化 (Normalization)：统一转换为标准 NFC 格式
    2. 剔除不合法及不可见字节：NUL、零宽字符、BOM、强排标记
    3. 清洗非打印字符及乱码：C0/C1 控制符号、PUA 私有区
    4. 编码收敛：安全剥离孤立 UTF-16 代理项
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = _INVISIBLE_CHAR_RE.sub("", text)
    text = _CONTROL_CHAR_RE.sub("", text)
    text = re.sub(r"[-]", "", text)

    # 彻底擦除孤立代理项
    try:
        cleaned = text.encode("utf-8", "ignore").decode("utf-8", "ignore")
    except Exception:
        chars = []
        for char in text:
            if 0xD800 <= ord(char) <= 0xDFFF:
                continue
            chars.append(char)
        cleaned = "".join(chars)

    return cleaned

"""修复 golden_cases.json 中字符串内部未转义的双引号。"""
import json, sys
from pathlib import Path

fpath = Path(__file__).resolve().parent.parent / "eval" / "golden_cases.json"
text = fpath.read_text("utf-8")

# 策略：逐字符扫描，在 JSON 字符串值内部遇到 " 时替换为 【】对
result = []
in_string = False
escape_next = False
open_quote_pos = -1
quote_stack = []  # 用于跟踪嵌套

i = 0
while i < len(text):
    ch = text[i]

    if escape_next:
        result.append(ch)
        escape_next = False
        i += 1
        continue

    if ch == '\\':
        result.append(ch)
        escape_next = True
        i += 1
        continue

    if ch == '"':
        if not in_string:
            in_string = True
            open_quote_pos = i
            quote_stack.append(('"', i))
            result.append(ch)
        else:
            # 检查后续字符判断这是否是字符串结束
            j = i + 1
            while j < len(text) and text[j] in ' \t\n\r':
                j += 1
            if j < len(text) and text[j] in ',:]}':
                # 这是 JSON 字符串结束引号
                in_string = False
                quote_stack.pop()
                result.append(ch)
            else:
                # 字符串内部的引号 → 替换
                result.append('【')
        i += 1
        continue

    result.append(ch)
    i += 1

fixed = ''.join(result)

# 把不配对的 【 改为 】
# Simple approach: in case_context strings, 【 is always followed by text then another 【 or end
# Actually the above logic already handles this correctly - just the closing quotes are also replaced
# But we need to match pairs. Let me do a second pass: alternate between 【 and 】
parts = fixed.split('【')
final = parts[0]
for k, part in enumerate(parts[1:], 1):
    final += ('「' if k % 2 == 1 else '」') + part

try:
    data = json.loads(final)
    print(f"✅ 修复成功: {len(data)} 条用例")
    fpath.write_text(final, "utf-8")
except json.JSONDecodeError as e:
    print(f"❌ 仍有错误 at line {e.lineno}, col {e.colno}")
    print(f"   {final[e.pos-30:e.pos+30]}")

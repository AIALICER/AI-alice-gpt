"""
messages.py のインデント整形。
"""

from __future__ import annotations

import ast
import re
import textwrap


def fix_messages_indentation(code: str) -> str:
    """
    Gemini 生成などで括弧内の文字列だけ深くインデントされる問題を修正する。
    """
    code = code.replace("\r\n", "\n")
    lines = code.splitlines()
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if re.match(r"^[A-Z][A-Z0-9_]*\s*=\s*\(\s*$", line):
            result.append(line)
            i += 1
            inner: list[str] = []
            while i < len(lines) and lines[i].strip() != ")":
                inner.append(lines[i])
                i += 1
            if inner:
                indents = [len(ln) - len(ln.lstrip()) for ln in inner if ln.strip()]
                base = min(indents) if indents else 0
                for ln in inner:
                    if not ln.strip():
                        result.append(ln)
                        continue
                    depth = len(ln) - len(ln.lstrip())
                    result.append(" " * (4 + max(0, depth - base)) + ln.lstrip())
            if i < len(lines):
                result.append(lines[i])
                i += 1
            continue

        result.append(line)
        i += 1

    fixed = "\n".join(result)
    if not fixed.endswith("\n"):
        fixed += "\n"
    return fixed


def normalize_messages_source(code: str) -> str:
    """構文チェック付きで messages.py ソースを正規化する。"""
    code = fix_messages_indentation(code)
    # 先頭の docstring ブロックのみ整える（モジュール全体の dedent は壊れやすい）
    code = textwrap.dedent(code)
    if not code.endswith("\n"):
        code += "\n"
    ast.parse(code)
    return code

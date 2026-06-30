"""验证码 JS 压缩混淆器。

用法：``python scripts/obfuscate_captcha.py``

策略（以压缩为主，混淆为辅）：

1. **去注释**：移除所有 ``//`` 和 ``/* */`` 注释
2. **压缩空白**：运算符两侧空白压缩，多余空行移除
3. **字符串 hex 转义**：把字符串中的非字母数字字符转为 ``\\xNN``，
   防止直接 grep ``captcha_id`` / ``X-Captcha-Sign`` 等关键字
4. **单行输出**：全部内容压缩到一行

注意：不做变量名替换。没有真正的 JS 解析器，正则替换变量名容易破坏作用域。

输出：``app/static/js/captcha.min.js``
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "app" / "static" / "js" / "captcha.js"
DST = ROOT / "app" / "static" / "js" / "captcha.min.js"


def tokenize(js: str) -> list[tuple[str, str]]:
    """把 JS 源码分词为 ``[(type, value)]``。

    type ∈ ``code`` | ``string`` | ``comment_line`` | ``comment_block``
    确保字符串 / 注释不会被误处理。
    """
    tokens: list[tuple[str, str]] = []
    i = 0
    n = len(js)
    buf: list[str] = []

    def flush_buf():
        if buf:
            tokens.append(("code", "".join(buf)))
            buf.clear()

    while i < n:
        c = js[i]
        if c == "/" and i + 1 < n and js[i + 1] == "/":
            flush_buf()
            end = js.find("\n", i)
            if end == -1:
                tokens.append(("comment_line", js[i:]))
                break
            tokens.append(("comment_line", js[i:end]))
            i = end
            continue
        if c == "/" and i + 1 < n and js[i + 1] == "*":
            flush_buf()
            end = js.find("*/", i + 2)
            if end == -1:
                tokens.append(("comment_block", js[i:]))
                break
            tokens.append(("comment_block", js[i:end + 2]))
            i = end + 2
            continue
        if c in ("'", '"', "`"):
            flush_buf()
            quote = c
            j = i + 1
            while j < n:
                if js[j] == "\\":
                    j += 2
                    continue
                if js[j] == quote:
                    break
                j += 1
            if j < n:
                tokens.append(("string", js[i:j + 1]))
                i = j + 1
                continue
        buf.append(c)
        i += 1
    flush_buf()
    return tokens


def encode_string(s: str) -> str:
    """把字符串内容编码为转义形式，防止 grep 关键字。

    规则：
    - ASCII 字母数字（a-z A-Z 0-9）保留原样
    - ASCII 标点 / 控制字符 → ``\\xNN``（JS 支持 Latin-1 范围）
    - 非 ASCII 字符（如中文）→ ``\\uXXXX``（JS 支持 BMP 范围）
    - 已有转义序列（如 ``\\n``、``\\x``、``\\u``）保留原样
    """
    quote = s[0]
    content = s[1:-1]
    encoded: list[str] = []
    j = 0
    while j < len(content):
        ch = content[j]
        # 反斜杠转义序列原样保留
        if ch == "\\" and j + 1 < len(content):
            encoded.append(content[j:j + 2])
            j += 2
            continue
        # ASCII 字母数字保留
        if ch.isascii() and ch.isalnum():
            encoded.append(ch)
        elif ch.isascii():
            # ASCII 标点 / 控制字符 → \xNN
            encoded.append(f"\\x{ord(ch):02x}")
        else:
            # 非 ASCII（中文等）→ \uXXXX
            encoded.append(f"\\u{ord(ch):04x}")
        j += 1
    return f"{quote}{''.join(encoded)}{quote}"


def compress_code(code: str) -> str:
    """压缩 code 片段的空白。"""
    code = code.replace("\t", " ")
    while "  " in code:
        code = code.replace("  ", " ")
    lines = [line.strip() for line in code.split("\n")]
    result: list[str] = []
    for line in lines:
        if line == "" and result and result[-1] == "":
            continue
        result.append(line)
    # 安全去除运算符两侧空格
    safe_chars = "{}();,:=<>+-*%!&|^~?"
    out = " ".join(result)
    for ch in safe_chars:
        out = out.replace(f" {ch} ", ch)
        out = out.replace(f" {ch}", ch)
        out = out.replace(f"{ch} ", ch)
    return out


def obfuscate(js: str) -> str:
    """完整压缩 + 混淆流程，输出单行。"""
    tokens = tokenize(js)
    parts: list[str] = []
    for ttype, value in tokens:
        if ttype == "string":
            parts.append(encode_string(value))
        elif ttype in ("comment_line", "comment_block"):
            continue  # 丢弃注释
        else:  # code
            parts.append(compress_code(value))

    # 用空格连接（不用换行）
    obfuscated = " ".join(p for p in parts if p)
    while "  " in obfuscated:
        obfuscated = obfuscated.replace("  ", " ")
    obfuscated = obfuscated.strip()

    # IIFE 包裹（单行）
    return f"(function(){{{obfuscated}}})();\n"


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: 源文件不存在: {SRC}", file=sys.stderr)
        return 1

    src = SRC.read_text(encoding="utf-8")
    obfuscated = obfuscate(src)

    src_size = len(src.encode("utf-8"))
    dst_size = len(obfuscated.encode("utf-8"))
    ratio = (1 - dst_size / src_size) * 100 if src_size > 0 else 0

    DST.write_text(obfuscated, encoding="utf-8")
    print(f"OK: {SRC.name} -> {DST.name}")
    print(f"  原始: {src_size:,} bytes")
    print(f"  压缩: {dst_size:,} bytes")
    print(f"  变化: {ratio:+.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())

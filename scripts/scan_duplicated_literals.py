#!/usr/bin/env python3
"""扫描充当标识符的重复字符串字面量。

用途：在代码库中找出被多处硬编码的路径、键名、类型名等。这类字面量
一旦出现多份，就失去了单一真源，修改时容易漏改其中一处。

用法：
    python scan_duplicated_literals.py --root kernel --root app/src --min-files 2

输出：默认写入 stdout，可用 --out 指定文件。输出为 ASCII，避免终端编码问题。
"""

import argparse
import os
import re
import sys
from collections import defaultdict

EXCLUDE_DIR_NAMES = {
    "node_modules", "dist", "build", "stage", ".git", "coverage",
    "__pycache__", "vendor", "testdata", "screenshots",
}
EXCLUDE_FILE_SUFFIXES = (
    "_test.go", ".test.ts", ".test.tsx", ".spec.ts", ".d.ts",
    ".min.js", "_generated.go", ".gen.go",
)

# Go 双引号字符串、Go 反引号原始字符串
GO_QUOTED = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
GO_RAW = re.compile(r"`([^`\n]*)`")
# TS/JS 单引号、双引号、模板字符串（仅单行）
TS_QUOTED = re.compile(r"""(?:"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)')""")
TS_TEMPLATE = re.compile(r"`([^`\n]*)`")

# 判定「像标识符」的依据：含路径分隔符、下划线、或点号
IDENT_LIKE = re.compile(r"[/_.]")
# 全大写下划线常量
UPPER_CONST = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")

HAS_SPACE = re.compile(r"\s")
HAS_PERCENT = re.compile(r"%")
HAS_CJK = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")

URL_PREFIXES = ("http://", "https://", "file://", "ws://", "wss://")
# 常见噪声：语言/库的固定字符串，重复属正常
NOISE_EXACT = {
    "application/json", "text/html", "text/plain", "utf-8", "UTF-8",
    "Content-Type", "User-Agent", "authorization", "Authorization",
    "content-type", "user-agent", "application/x-www-form-urlencoded",
    "GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH",
}


def iter_source_files(roots):
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dir_path, dir_names, file_names in os.walk(root):
            dir_names[:] = [
                d for d in dir_names
                if d not in EXCLUDE_DIR_NAMES and not d.startswith(".")
            ]
            for file_name in file_names:
                if not (file_name.endswith(".go") or file_name.endswith((".ts", ".tsx"))):
                    continue
                if file_name.endswith(EXCLUDE_FILE_SUFFIXES):
                    continue
                yield os.path.join(dir_path, file_name)


def is_identifier_like(value):
    if len(value) < 4:
        return False
    if value in NOISE_EXACT:
        return False
    if HAS_SPACE.search(value) or HAS_PERCENT.search(value) or HAS_CJK.search(value):
        return False
    if value.startswith(URL_PREFIXES):
        return False
    if not IDENT_LIKE.search(value) and not UPPER_CONST.match(value):
        return False
    # 纯转义/纯符号序列无意义
    if not re.search(r"[A-Za-z0-9]", value):
        return False
    return True


# 纯扩展名，如 ".json"、".png"
BARE_EXTENSION = re.compile(r"^\.[a-z0-9]{1,8}$")
# CSS 选择器（以点开头且带连字符/双下划线），如 ".b3-list-item--focus"
CSS_SELECTOR = re.compile(r"^\.[A-Za-z][A-Za-z0-9_-]*[-_][A-Za-z0-9_-]*$")


def classify(value):
    """返回 (优先级, 是否应报告)。P1 为路径类，P2 为文件名类，P3 为标识符类。"""
    # HTML/Markdown 片段与模板表达式不构成标识符
    if value.startswith("<") or "${" in value:
        return None
    if BARE_EXTENSION.match(value) or CSS_SELECTOR.match(value):
        return None

    has_slash = "/" in value
    has_dot = "." in value
    if not has_slash and not has_dot:
        # 无路径分隔符也无扩展名：可能是 CSS 类名，也可能是键名常量
        if "__" in value or "-" in value:
            return None
        return "P3"
    if has_slash:
        return "P1"
    # 仅含点的情形：隐藏目录名（如 .siyuan）是有效信号，其余按文件名类处理
    return "P2"


# 导入语句中的字符串是模块路径，不构成「应被提取的标识符」，需整块排除。
GO_IMPORT_START = re.compile(r"^\s*import\s*\(")
GO_IMPORT_SINGLE = re.compile(r"^\s*import\s+[\"`]")
TS_IMPORT_LINE = re.compile(r"^\s*(import\b|export\b.*\bfrom\b)")
TS_REQUIRE_LINE = re.compile(r"\brequire\s*\(")


def strip_imports(path, text):
    lines = text.split("\n")
    kept = []
    in_go_import_block = False
    for line in lines:
        if path.endswith(".go"):
            if in_go_import_block:
                if line.strip() == ")":
                    in_go_import_block = False
                kept.append("")
                continue
            if GO_IMPORT_START.match(line):
                in_go_import_block = True
                kept.append("")
                continue
            if GO_IMPORT_SINGLE.match(line):
                kept.append("")
                continue
        else:
            if TS_IMPORT_LINE.match(line) or TS_REQUIRE_LINE.search(line):
                kept.append("")
                continue
        kept.append(line)
    return "\n".join(kept)


def extract_literals(path, text):
    if path.endswith(".go"):
        patterns = (GO_QUOTED, GO_RAW)
    else:
        patterns = (TS_QUOTED, TS_TEMPLATE)
    values = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            for group in match.groups():
                if group is not None:
                    values.append(group)
                    break
    return values


def scan(roots, min_files, min_count):
    occurrences = defaultdict(lambda: {"count": 0, "files": defaultdict(int)})
    scanned = 0
    for path in iter_source_files(roots):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        scanned += 1
        for value in extract_literals(path, strip_imports(path, text)):
            if not is_identifier_like(value):
                continue
            if classify(value) is None:
                continue
            entry = occurrences[value]
            entry["count"] += 1
            entry["files"][path.replace("\\", "/")] += 1

    findings = []
    for value, entry in occurrences.items():
        file_count = len(entry["files"])
        if file_count < min_files or entry["count"] < min_count:
            continue
        priority = classify(value)
        if priority is None:
            continue
        findings.append((priority, value, entry["count"], file_count, entry["files"]))
    findings.sort(key=lambda item: (item[0], -item[3], -item[2], item[1]))
    return findings, scanned


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", dest="roots", default=[],
                        help="扫描根目录，可重复指定")
    parser.add_argument("--min-files", type=int, default=2,
                        help="至少出现在多少个不同文件中（默认 2）")
    parser.add_argument("--min-count", type=int, default=2,
                        help="最少总出现次数（默认 2）")
    parser.add_argument("--top", type=int, default=0,
                        help="仅输出前 N 条，0 表示全部")
    parser.add_argument("--out", default="",
                        help="输出到文件而不是 stdout")
    args = parser.parse_args()

    roots = args.roots or ["kernel", "app/src"]
    findings, scanned = scan(roots, args.min_files, args.min_count)
    if args.top > 0:
        findings = findings[:args.top]

    lines = []
    lines.append("# Duplicated identifier-like string literals")
    lines.append("")
    lines.append("roots: %s" % ", ".join(roots))
    lines.append("files scanned: %d" % scanned)
    lines.append("findings: %d" % len(findings))
    lines.append("")
    lines.append("P1 = path-like (contains /), P2 = filename-like (contains . only),")
    lines.append("P3 = identifier-like (no / or .). CSS class names are excluded.")
    lines.append("")

    labels = {
        "P1": "P1 path-like literals",
        "P2": "P2 filename-like literals",
        "P3": "P3 identifier-like literals",
    }
    for priority in ("P1", "P2", "P3"):
        subset = [item for item in findings if item[0] == priority]
        lines.append("## %s (%d)" % (labels[priority], len(subset)))
        lines.append("")
        if not subset:
            lines.append("(none)")
            lines.append("")
            continue
        lines.append("%-52s %6s %6s" % ("literal", "count", "files"))
        lines.append("-" * 66)
        for _, value, count, file_count, files in subset:
            shown = value if len(value) <= 50 else value[:47] + "..."
            lines.append("%-52s %6d %6d" % (shown, count, file_count))
            ordered = sorted(files.items(), key=lambda item: (-item[1], item[0]))
            for path, hits in ordered[:8]:
                lines.append("      %s (x%d)" % (path, hits))
            if len(ordered) > 8:
                lines.append("      ... and %d more files" % (len(ordered) - 8))
        lines.append("")

    output = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(output)
        print("written: %s" % args.out)
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()

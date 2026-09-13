#!/usr/bin/env python3
"""扫描插入 HTML 时未转义的动态插值。

判据来源：真实缺陷修复提交 dfa2c589f2（"Preserve names in search updates and
history dialogs"）与 f811001983（"Escape dynamic names in confirmation dialogs"）。
这两次修复的共同形态是把 ${x} 改为 ${escapeHtml(x)}，说明项目约定是：凡把
动态值插入 HTML 字符串，都必须经 escapeHtml 或 sanitizeKernelHTML 处理。

用法：
    python scan_unescaped_html.py --root app/src --out result.txt

输出为 ASCII，避免终端编码问题。

`--root` 不存在时以退出码 2 报错，不输出「0 个文件 / 0 条候选」——零候选与没扫到
文件在输出上无法区分，会让调用方把「没扫」当成「没问题」。默认值 `app/src` 是
SiYuan 的布局，用于其他仓库时必须显式传 `--root`。
"""

import argparse
import os
import re
import sys

EXCLUDE_DIR_NAMES = {
    "node_modules", "dist", "build", "stage", ".git", "coverage", "__pycache__",
}
EXCLUDE_FILE_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".d.ts")

# 向 DOM 写入 HTML 的调用点
SINK_CALL = re.compile(
    r"\.(innerHTML|outerHTML)\s*=|"
    r"insertAdjacentHTML\s*\(|"
    r"\.html\s*\(|"
    r"\$\([^)]*\)\.html\s*\(",
)

# 模板字符串中的插值
INTERPOLATION = re.compile(r"\$\{([^{}]+)\}")

# 已知安全的包装函数（项目约定）。新增前先读实现确认它确实转义。
SAFE_WRAPPERS = (
    "escapeHtml", "sanitizeKernelHTML", "escapeAttr", "encodeURIComponent",
    "encodeURI", "CSS.escape",
    # `escapeAriaLabel`（app/src/util/escape.ts）专用于属性语境，会替换引号与 `<`。
    "escapeAriaLabel",
    # `updateHotkeyTip`（protyle/util/compatibility.ts）把 `⌘X` 这类固定串包成 kbd 标记，
    # 输出完全由常量拼接，不接受外部数据。
    "updateHotkeyTip",
)
# 每条规则是 (正则, 是否锚定在开头, 说明)。
# 拆成规则表而不是一个巨大的 alternation：锚定语义不同（match 与 search）的正则
# 混在一起时，只要其中一条能匹配空串，整条规则就会把所有表达式都判为安全。
SAFE_EXPR_RULES = (
    (re.compile(r"^[\'\"`]"), True, "字符串字面量"),
    (re.compile(r"^\d"), True, "纯数字开头"),
    (re.compile(r"^\+\+"), True, "自增（数值）"),
    (re.compile(r"^(true|false|null|undefined)$"), True, "字面量"),
    (re.compile(r"^-\d"), True, "负数"),
    (re.compile(r"^window\.siyuan\.languages\."), True, "受控的 i18n 文案"),
    (re.compile(r"^Constants\.[A-Za-z0-9_.]+$"), True, "仓库常量表"),
    (re.compile(r"^[A-Z][A-Z0-9_]{3,}$"), True, "裸的大写下划线常量"),
    (re.compile(r"^!\s*[\w.\[\]\"']+$"), True, "布尔取反"),
    (re.compile(r"\.length$"), False, "取长度"),
    (re.compile(r"\.toString\(\)$"), False, "数字转字符串"),
    # 尾部的数值字段（可带一步算术）：`a.b.clientWidth + 16` 这类几何量不是注入面。
    # SAFE_VAR_NAME 只能锚定开头，所以尾随形态必须单独成规则。
    (re.compile(r"\.(clientWidth|clientHeight|offsetWidth|offsetHeight|scrollWidth|scrollHeight|"
                r"scrollTop|scrollLeft|length|count|size|width|height|top|left)(\s*[-+*/]\s*\d+)?$"),
     False, "数值字段（含一步算术）"),
    # 三元且两侧分支都是字面量：分支里不可能含动态数据
    (re.compile(r"\?\s*[\"'][^\"'\n]*[\"']\s*:\s*[\"'][^\"'\n]*[\"']"), False, "三元分支均为字面量"),
)
# 数值型变量名：插入到 style/data-* 中不构成 HTML 注入
SAFE_VAR_NAME = re.compile(
    r"^(?:\+\+|--)?(?:index|i|j|n|k|count|num|size|length|width|height|"
    r"zIndex|top|left|right|bottom|opacity|delay|duration|offset|total|page|"
    r"pageSize|matchedAssetCount|refCount|rootRefCount|max|min|level|depth|retry|attempts|"
    r"clientWidth|clientHeight|offsetWidth|offsetHeight|scrollTop|scrollLeft|"
    r"defaultValue|spellcheck)\b",
    re.IGNORECASE,
)
# 数值型变量名：插入到 style/data-* 中不构成 HTML 注入
SAFE_VAR_NAME = re.compile(
    r"^(?:\+\+|--)?(?:index|i|j|n|k|count|num|size|length|width|height|"
    r"zIndex|top|left|right|bottom|opacity|delay|duration|offset|total|page|"
    r"pageSize|matchedAssetCount|refCount|rootRefCount|max|min|level|depth|retry|attempts|"
    r"clientWidth|clientHeight|offsetWidth|offsetHeight|scrollTop|scrollLeft|"
    r"defaultValue|spellcheck)\b",
    re.IGNORECASE,
)
# 处于 style="..." 或 data-*="..." 属性内部
SAFE_ATTR_VALUE = re.compile(r"(?:style|data-[a-z-]+)\s*=\s*[\"'`][^\"'`]*$")
# 行内注释或已标注安全的标记
SAFE_MARKER = re.compile(r"(escapeHtml|sanitize|nolint|noinspection|safe)\b", re.IGNORECASE)


def iter_files(root):
    for dir_path, dir_names, file_names in os.walk(root):
        dir_names[:] = [
            d for d in dir_names
            if d not in EXCLUDE_DIR_NAMES and not d.startswith(".")
        ]
        for file_name in file_names:
            if not file_name.endswith((".ts", ".tsx")):
                continue
            if file_name.endswith(EXCLUDE_FILE_SUFFIXES):
                continue
            yield os.path.join(dir_path, file_name)


def split_expr(expr):
    """粗粒度切分顶层逗号/点号，避免把 foo.bar 误判为函数调用。"""
    return expr.strip()


def looks_unsafe(expr, line):
    expr = split_expr(expr)
    if not expr:
        return False
    # 前导 `(` 会让所有锚定规则失效，先剥掉再判（`(getIcon())` 与 `getIcon()` 同类）
    bare = expr.lstrip("(").strip()
    for pattern, anchored, _ in SAFE_EXPR_RULES:
        if pattern.match(bare) if anchored else pattern.search(expr):
            return False
    if SAFE_VAR_NAME.match(bare):
        return False
    for wrapper in SAFE_WRAPPERS:
        if wrapper in expr:
            return False
    if SAFE_MARKER.search(expr):
        return False
    return True


def in_safe_attribute(joined, offset):
    """判断插值是否处于 style="..." / data-*="..." 属性值内。"""
    head = joined[max(0, offset - 120):offset]
    return bool(SAFE_ATTR_VALUE.search(head))


def scan_file(path):
    findings = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return findings

    # 收集每个 HTML 写入语句的行号范围（含模板字符串续行）
    i = 0
    while i < len(lines):
        line = lines[i]
        if not SINK_CALL.search(line):
            i += 1
            continue
        # 向后收集直到括号/反引号闭合，最多 20 行
        block = []
        depth = 0
        quote = None
        j = i
        while j < len(lines) and j - i < 20:
            text = lines[j]
            block.append(text)
            for index, ch in enumerate(text):
                if quote:
                    if ch == quote and text[index - 1:index] != "\\":
                        quote = None
                    continue
                if ch in "`\"'":
                    quote = ch
                elif ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    depth -= 1
            if depth <= 0 and j > i:
                break
            j += 1

        joined = "\n".join(block)
        for match in INTERPOLATION.finditer(joined):
            expr = match.group(1)
            if not looks_unsafe(expr, joined):
                continue
            if in_safe_attribute(joined, match.start()):
                continue
            findings.append((i + 1, expr.strip(), block[0].strip()[:110]))
        i = max(i + 1, j + 1)
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="app/src", help="扫描根目录")
    parser.add_argument("--out", default="", help="输出文件")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        sys.stderr.write(
            "error: no such directory: %s\n"
            "hint: pass --root explicitly; the built-in default app/src is the\n"
            "      SiYuan layout and will not exist in another repository\n"
            % args.root
        )
        return 2

    total = 0
    all_findings = []
    for path in iter_files(args.root):
        total += 1
        findings = scan_file(path)
        if findings:
            all_findings.append((path.replace("\\", "/"), findings))

    lines = []
    lines.append("# Unescaped dynamic interpolation into HTML")
    lines.append("")
    lines.append("root: %s" % args.root)
    lines.append("files scanned: %d" % total)
    lines.append("files with findings: %d" % len(all_findings))
    lines.append("total candidate sites: %d" % sum(len(f) for _, f in all_findings))
    lines.append("")
    lines.append("Reference: commits dfa2c589f2 and f811001983 fixed this exact class")
    lines.append("by wrapping interpolation in escapeHtml(...). Verify each site by hand;")
    lines.append("this script's SAFE_* filters are coarse heuristics, not proof of safety.")
    lines.append("Prioritize sites whose expression derives from user data, document names,")
    lines.append("tag names, or any value originating from the kernel API.")
    lines.append("")
    for path, findings in sorted(all_findings, key=lambda item: -len(item[1])):
        lines.append("%s (%d)" % (path, len(findings)))
        for line_no, expr, snippet in findings[:12]:
            lines.append("    L%-6d %s" % (line_no, expr[:70]))
            lines.append("            %s" % snippet)
        if len(findings) > 12:
            lines.append("    ... and %d more" % (len(findings) - 12))
        lines.append("")

    output = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(output)
        print("written: %s" % args.out)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

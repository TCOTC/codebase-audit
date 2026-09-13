#!/usr/bin/env python3
"""提取前端 DOM 契约（`data-type` 及其子类型）的闭合集合。

用途：前端的 `data-type` 字面量**没有单一真源**——实测 SiYuan 的 `app/src` 下约
2000 处，散落在 38+ 个文件里，多为裸字符串。权威源是 **Lute 输出的 NodeType**
（`lute.min.js` 与内核侧的类型名）。本脚本把这个闭合集合机械提取出来，供与权威源
逐项 diff，找「漏项」与「拼写漂移」——这正是判据 D3 与模式 P14 要求的动作，
而在此之前该动作只能靠人肉 grep。

用法：
    python scan_dom_type_literals.py --root app/src --out <工作区外临时路径>

可选：
    --kind node|subtype|all   只提取 Node* 族 / 只提取子类型 / 全部（默认 all）
    --min-files N             清单里只列出「出现在 >= N 个文件」的值（默认 1，即全列）

输出为纯 ASCII，避免终端编码问题。扫描根不存在时以退出码 2 报错，不输出
「0 个文件 / 0 条发现」——零发现与没扫到在输出上无法区分，会把「没扫」当成「没问题」。

**产出是候选不是结论**：`Node*` 命名约定本身是权威源的一部分，脚本只能指出
「有这些值、其中这些可疑」；某项是否真为漏项，必须回到 Lute 的 NodeType 判定。
"""

import argparse
import os
import re
import sys
from collections import defaultdict

EXCLUDE_DIR_NAMES = {
    "node_modules", "dist", "build", "stage", ".git", "coverage",
    "__pycache__", "vendor", "testdata", "screenshots", "types",
}
EXCLUDE_FILE_SUFFIXES = (
    ".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".d.ts", ".min.js",
)

# `data-type="X"` / `data-type='X'`（HTML 片段与 querySelector 选择器）
HTML_ATTR = re.compile(r"""data-type\s*=\s*["']([^"']+)["']""")
# setAttribute("data-type", "X")
SET_ATTR = re.compile(
    r"""setAttribute\(\s*["']data-type["']\s*,\s*["']([^"']+)["']""")
# hasClosestByAttribute(<任意参数>, "data-type", "X")
HELPER_ATTR = re.compile(
    r"""hasClosestByAttribute\([^)]*?["']data-type["']\s*,\s*["']([^"']+)["']""", re.S)
# getAttribute("data-type") === "X" / dataset.type === "X" / .includes("X")
CTX_COMPARE = re.compile(
    r"""(?:getAttribute\(\s*["']data-type["']\s*\)|dataset\.type)"""
    r"""\s*(?:===|!==|==|!=|\.includes\()\s*["']([^"']+)["']""")
# 任意位置的 Node* 字面量（兼容未走上面分支的取值写法）
ANY_NODE = re.compile(r"""["'](Node[A-Z][A-Za-z]*)["']""")

# 契约值只允许标识符形态——含 `[`、`^`、`(` 等的命中是正则误取（如选择器片段）
VALUE_SHAPE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

# 无前缀族的合法单项契约值
ALLOWED_EXACT = {
    "av", "img", "audio", "video", "iframe", "widget", "kbd", "tag",
    "text", "backlink", "bookmark", "template",
}
# 带连字符的前缀族（要求后面跟 `-`，避免 `textContent` 这类误收）
ALLOWED_PREFIXES = (
    "inline-", "av-", "img-", "search-", "block-", "file-", "virtual-",
    "code-", "html-", "sandbox-", "pdf-", "audio-", "video-", "widget-",
)
# 其他合法但无前缀族的值（需逐个确认；列在此处以减少噪声，不构成「不是漏项」的结论）
ALLOWED_OTHER = {
    "available-fonts", "backlink", "export-", "oc-", "custom-",
}


def iter_source_files(roots):
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dir_path, dir_names, file_names in os.walk(root):
            dir_names[:] = [d for d in dir_names
                            if d not in EXCLUDE_DIR_NAMES and not d.startswith(".")]
            for file_name in file_names:
                if not file_name.endswith((".ts", ".tsx", ".js")):
                    continue
                if file_name.endswith(EXCLUDE_FILE_SUFFIXES):
                    continue
                yield os.path.join(dir_path, file_name)


def strip_comments_and_strings_kept(text):
    """保留字符串字面量，只去行注释与块注释（避免注释里的示例被当成用法）。"""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"(?m)^\s*//.*$", " ", text)
    text = re.sub(r"(?m)\s//\s.*$", " ", text)
    return text


def looks_like_contract(value, kind):
    """判定一个候选值是否可能是 DOM 契约值。宽松放行，宁可留噪声也不漏。"""
    if not value or not VALUE_SHAPE.match(value):
        return False
    if value.startswith("Node"):
        return kind != "subtype"
    if kind == "node":
        return False
    if value in ALLOWED_EXACT or value.startswith(ALLOWED_PREFIXES):
        return True
    return value in ALLOWED_OTHER


def edit_distance_at_most_one(a, b):
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    i = j = 0
    skipped = False
    while i < len(short) and j < len(long_):
        if short[i] == long_[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = True
            j += 1
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", action="append", default=None,
                        help="源码根目录，可重复。默认 app/src")
    parser.add_argument("--out", default=None, help="输出文件；缺省写 stdout")
    parser.add_argument("--kind", choices=["node", "subtype", "all"], default="all")
    parser.add_argument("--min-files", type=int, default=1,
                        help="清单里只列出出现在 >= N 个文件的值（默认 1）")
    args = parser.parse_args()

    roots = args.root or ["app/src"]
    absent = [r for r in roots if not os.path.isdir(r)]
    if absent:
        # 首行用 ASCII 标记：stderr 可能在任何控制台编码下被读，
        # 且三个扫描脚本共用同一个可 grep 的契约（既有脚本用的是 no such directory）。
        sys.stderr.write(
            "no such directory: %s\n"
            "零发现与没扫到文件在输出上无法区分，故以退出码 2 报错而不是输出 0 条。\n"
            % ", ".join(absent))
        return 2

    counts = defaultdict(int)          # 值 -> 出现次数
    files_of = defaultdict(set)        # 值 -> 文件集合
    total = 0
    file_count = 0

    for path in iter_source_files(roots):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = strip_comments_and_strings_kept(fh.read())
        except OSError:
            continue
        file_count += 1
        here = set()
        for pattern in (HTML_ATTR, SET_ATTR, HELPER_ATTR, CTX_COMPARE, ANY_NODE):
            for match in pattern.finditer(text):
                value = match.group(1)
                if not looks_like_contract(value, args.kind):
                    continue
                here.add(value)
        for value in here:
            counts[value] += 1
            files_of[value].add(path)
        total += len(here)

    if not counts:
        sys.stderr.write("no contract values: 在 %s 下未提取到任何 data-type 契约值。\n"
                         "请确认 --root 指向前端源码目录。\n" % ", ".join(roots))
        return 2

    singles = sorted(v for v in counts if counts[v] == 1)
    pairs = []
    values = sorted(counts)
    for i, a in enumerate(values):
        for b in values[i + 1:]:
            if a.lower() == b.lower() or edit_distance_at_most_one(a, b):
                pairs.append((a, b))

    out = []
    out.append("DOM 契约闭合集合（data-type / 子类型）")
    out.append("=" * 64)
    out.append("扫描根            : %s" % ", ".join(roots))
    out.append("扫描文件数        : %d" % file_count)
    out.append("不同契约值        : %d" % len(counts))
    out.append("提取到的引用总数  : %d（同一文件内同一值只计一次）" % total)
    out.append("")
    out.append("注意：本输出是【候选】。权威源是 Lute 输出的 NodeType，是否漏项")
    out.append("必须与它逐项 diff 后才能判定；拼写漂移也需回读调用点确认可达性。")
    out.append("")

    out.append("-" * 64)
    out.append("疑似拼写漂移（仅大小写不同，或编辑距离 1）")
    out.append("-" * 64)
    if pairs:
        for a, b in pairs:
            out.append("  %-34s vs %-34s  %d/%d" % (a, b, counts[a], counts[b]))
    else:
        out.append("  （无）")
    out.append("")

    out.append("-" * 64)
    out.append("仅出现一次的值（%d 个）—— 需确认是有意的一次性用法还是漏改" % len(singles))
    out.append("-" * 64)
    if singles:
        for value in singles:
            sample = sorted(files_of[value])[0]
            out.append("  %-40s %s" % (value, sample))
    else:
        out.append("  （无）")
    out.append("")

    out.append("-" * 64)
    out.append("完整清单（值 / 文件数；--min-files %d）" % args.min_files)
    out.append("-" * 64)
    listed = [v for v in values if len(files_of[v]) >= args.min_files]
    for value in sorted(listed, key=lambda v: (-len(files_of[v]), v)):
        out.append("  %-40s %3d 文件" % (value, len(files_of[value])))
    out.append("")
    out.append("共 %d 个值；清单列出 %d 个。" % (len(values), len(listed)))

    text = "\n".join(out) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print("已写入 %s" % args.out)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

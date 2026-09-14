#!/usr/bin/env python3
"""扫描设计令牌（CSS 自定义属性）的契约缺口候选。

来源：`github/awesome-copilot` 的 `penpot-uiux-design`（MIT）把
「Design Tokens（spacing / typography / color scale）」列为设计系统的第一层，
并把「与设计系统一致」写进 Design Review Checklist。
但该 skill 依赖 Penpot MCP 从设计文件里**读取**令牌；本仓库没有设计文件，
只有样式源码——因此这里把「令牌一致性」改写成**源码层可判定**的形式：
**被引用的令牌是否有权威定义，或是否有明确的兜底**。

## 为什么必须做三条件合取（这是本脚本的全部价值）

第一版只做「被 `var()` 引用 + 在 SCSS 里找不到定义」，实测 SiYuan 得到 34 条
「无 fallback 的疑似缺失」。**逐条回读后 17/17 全部是假阳性**——它们都由 JS
在运行时写入：

    htmlTarget.style.setProperty("--drag-indent", `${indent}px`);   // listDragTarget.ts:52
    ["--b3-table-frame-left", ...].forEach(n => action.style.removeProperty(n));
    protyle.element.style.setProperty("--b3-width-protyle-wysiwyg", w + "px");

即 **CSS 自定义属性在本仓库是 JS→CSS 的运行时通道**；只查样式表必然产出噪声。
所以判据必须是三条件**合取**：

| 条件 | 含义 |
|---|---|
| ① 引用时没有 fallback | `var(--x)` 而非 `var(--x, #fff)`——后者说明作者已声明兜底 |
| ② 在所有样式根里没有 `--x:` 定义 | 含主题目录（主题是令牌的合法来源） |
| ③ 在源码根里没有任何写入 | `setProperty` / `removeProperty` / 对象键 / 内联 `style` / `cssText` / 模板串 |

只有三条同时成立才是候选：既没有兜底、也没有静态定义、也没有任何人写它。

`removeProperty` 也算写入：**清理调用本身就是该变量存在的证据**
（`tableControl.ts:1277` 清的就是它自己 `setProperty` 过的帧位置）。

## 用法

    python scan_css_token_contract.py --styles app/src/assets/scss --styles app/appearance \\
                                      --source app/src

`--source` 缺失时脚本**仍然运行但会在结论里显式警告**：此时条件 ③ 无法判定，
结果不可用于立论。样式根不存在时以退出码 2 报错——零发现与没扫到在输出上
无法区分，静默输出「0 个」会让使用者以为没有问题。

输出为 ASCII 表头 + UTF-8 正文。仅依赖标准库。
"""

import argparse
import io
import os
import re
import sys

EXCLUDE_DIR_NAMES = {
    "node_modules", "dist", "build", "stage", ".git", "coverage",
    "__pycache__", "vendor", "types",
}
SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".html", ".htm")
STYLE_SUFFIXES = (".scss", ".css", ".sass")
# 生成的产物不参与判定：它们从源码派生，会把缺口抹平。
EXCLUDE_FILE_MARKERS = (".min.", ".d.ts", "bundle")
# 测试文件必须排除：实测 9 个候选里有 7 个只出现在 *.test.ts 中
# （`--b3-font-color14`、`--b3-inline-builtin-error-color` 等是断言里写死的
# 期望串，不是产品代码的引用）。其余扫描器同样排除测试文件。
EXCLUDE_FILE_SUFFIXES = (".test.ts", ".test.tsx", ".test.js", ".spec.ts",
                         ".spec.tsx", ".spec.js")

# --- 条件 ①：引用侧 -----------------------------------------------------------
# `var(--x)` 与 `var(--x, ...)` 靠**逗号**区分，而不是按行截断——
# `var()` 可以跨行书写（实测存在）。第二捕获组为 `,` 即有 fallback。
VAR_REF = re.compile(r"var\(\s*(--[A-Za-z_][\w-]*)\s*(,|\))")

# --- 条件 ②：定义侧 -----------------------------------------------------------
VAR_DEF = re.compile(r"(--[A-Za-z_][\w-]*)\s*:")

# --- 条件 ③：源码写入侧 -------------------------------------------------------
# 判定用的是**宽规则**：令牌名只要在源码根里出现过，就说明 JS 认得它，
# 不能断言它「无人定义」。这一点是被一次漏检逼出来的——
# 只按 `setProperty("--x")` 这类形态匹配时，`--b3-font-family-editor`
# 被报成候选，实际它与 `--b3-font-size-editor` 写在**同一个注入的 CSS 模板串**
# 里（`util/assets.ts:404` 起），而「模板串内 CSS」这条规则带了 backtick 锚点，
# 同串里的第二个变量名落到了锚点之外，抓不到。
# 因此：**形态匹配只用于输出说明，排除判定用宽规则。**
WRITE_PATTERNS = [
    (re.compile(r"""\.(?:set|remove)Property\(\s*["'`](--[A-Za-z_][\w-]*)"""),
     "setProperty/removeProperty"),
    (re.compile(r"""["'`](--[A-Za-z_][\w-]*)["'`]\s*:"""),
     "样式对象键"),
    (re.compile(r"""style\s*=\s*["'`][^"'`]{0,200}?(--[A-Za-z_][\w-]*)\s*:"""),
     "内联 style"),
    (re.compile(r"""cssText[^;]{0,300}?(--[A-Za-z_][\w-]*)\s*:"""),
     "cssText"),
    (re.compile(r"""`[^`]{0,400}?(--[A-Za-z_][\w-]*)\s*:"""),
     "模板串内 CSS"),
]

# 宽规则：源码里任何位置出现 `--x`（字符串、模板串、注释、变量名皆可）。
ANY_MENTION = re.compile(r"(--[A-Za-z_][\w-]*)")


def iter_files(roots, suffixes):
    """产出 (绝对路径, 所属根)。保留根是为了输出相对路径，并跨根去重。"""
    for root in roots:
        for dir_path, dir_names, file_names in os.walk(root):
            dir_names[:] = [d for d in dir_names
                            if d not in EXCLUDE_DIR_NAMES and not d.startswith(".")]
            for name in file_names:
                if not name.endswith(suffixes):
                    continue
                if name.endswith(EXCLUDE_FILE_SUFFIXES):
                    continue
                if any(m in name for m in EXCLUDE_FILE_MARKERS):
                    continue
                yield os.path.join(dir_path, name), root


def collect(roots, suffixes, patterns):
    """按给定正则收集命中。返回 (名称 -> [(相对路径, 行号, 形态)], 文件数)。"""
    found = {}
    scanned = 0
    seen = set()
    if not roots:
        return found, 0
    for path, root in iter_files(roots, suffixes):
        if path in seen:
            continue
        seen.add(path)
        scanned += 1
        try:
            text = io.open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        rel = os.path.relpath(path, root).replace("\\", "/")
        for rx, label in patterns:
            for m in rx.finditer(text):
                sites = found.setdefault(m.group(1), [])
                if len(sites) < 8:
                    sites.append((rel, text.count("\n", 0, m.start()) + 1, label))
    return found, scanned


def collect_var_refs(roots, suffixes):
    """按是否带 fallback 分桶。返回 (无 fallback, 有 fallback, 文件数)。"""
    no_fb, with_fb = {}, {}
    scanned = 0
    seen = set()
    if not roots:
        return no_fb, with_fb, 0
    for path, root in iter_files(roots, suffixes):
        if path in seen:
            continue
        seen.add(path)
        scanned += 1
        try:
            text = io.open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        rel = os.path.relpath(path, root).replace("\\", "/")
        for m in VAR_REF.finditer(text):
            name, tail = m.group(1), m.group(2)
            bucket = with_fb if tail == "," else no_fb
            sites = bucket.setdefault(name, [])
            if len(sites) < 8:
                sites.append((rel, text.count("\n", 0, m.start()) + 1, "var()"))
    return no_fb, with_fb, scanned


def main():
    parser = argparse.ArgumentParser(
        description="扫描设计令牌（CSS 自定义属性）的契约缺口候选")
    parser.add_argument("--styles", action="append", required=True, metavar="DIR",
                        help="样式根（可重复）：SCSS/CSS 与主题目录")
    parser.add_argument("--source", action="append", default=[], metavar="DIR",
                        help="源码根（可重复）：用于判定条件 ③；"
                             "缺失时结果不可用于立论")
    args = parser.parse_args()

    for label, dirs in (("--styles", args.styles), ("--source", args.source)):
        missing = [d for d in dirs if not os.path.isdir(d)]
        if missing:
            sys.stderr.write("no such directory (%s): %s\n"
                             % (label, ", ".join(missing)))
            return 2

    style_no_fb, style_with_fb, style_files = collect_var_refs(
        args.styles, STYLE_SUFFIXES)
    src_no_fb, src_with_fb, source_files = collect_var_refs(
        args.source, SOURCE_SUFFIXES)
    definitions, _ = collect(args.styles, STYLE_SUFFIXES, [(VAR_DEF, "定义")])
    writes, _ = collect(args.source, SOURCE_SUFFIXES, WRITE_PATTERNS)
    # 排除判定用的宽规则：源码里提到过即算有运行时通道。
    mentioned, _ = collect(args.source, SOURCE_SUFFIXES,
                           [(ANY_MENTION, "源码提及")])

    no_fb = dict(style_no_fb)
    for name, sites in src_no_fb.items():
        no_fb.setdefault(name, []).extend(sites)
    with_fb = set(style_with_fb) | set(src_with_fb)

    # 只有样式表里的「定义」才算定义；源码里的 `--x:` 命中已被条件 ③ 覆盖。
    defined_in_css = sorted(n for n in no_fb if n in definitions)
    written_by_js = sorted(n for n in no_fb
                           if n not in definitions and n in writes)
    mentioned_in_src = sorted(n for n in no_fb
                              if n not in definitions and n in mentioned)
    has_fallback = sorted(n for n in no_fb if n in with_fb)
    candidates = sorted(n for n in no_fb
                        if n not in definitions and n not in mentioned
                        and n not in with_fb)

    print("=" * 78)
    print("设计令牌契约扫描（CSS 自定义属性）")
    print("=" * 78)
    print()
    print("扫描范围")
    print("  样式文件 : %d 个（%s）" % (style_files, "、".join(args.styles)))
    print("  源码文件 : %d 个（%s）"
          % (source_files, "、".join(args.source) or "未提供"))
    print("  引用到的令牌 : %d 个" % len(no_fb))
    print("  样式里定义的令牌 : %d 个" % len(definitions))
    print("  源码里写入的令牌 : %d 个" % len(writes))

    print()
    print("条件 ① 引用侧")
    print("  有 fallback（作者已声明兜底，排除）：%d 个" % len(with_fb))
    print("  无 fallback（%d 个）进入后续判定" % len(no_fb))

    print()
    print("条件 ② / ③ 降噪明细（这两条是承重的，不是可选优化）")
    print("  无 fallback 但样式里有定义（条件 ② 排除）：%d 个" % len(defined_in_css))
    print("  无定义但源码里有写入（条件 ③ 排除）：%d 个" % len(written_by_js))
    print("  同一令牌另有带 fallback 的引用（排除）：%d 个" % len(has_fallback))
    print("  **三条件同时成立的候选**：%d 个" % len(candidates))

    if written_by_js:
        print()
        print("  由源码写入而排除的令牌（本仓库里最容易被误报的一批）")
        for n in written_by_js[:15]:
            rel, line, label = writes[n][0]
            print("    %-36s %s 写入 %s:%d" % (n, label, rel, line))
        if len(written_by_js) > 15:
            print("    ...另有 %d 个" % (len(written_by_js) - 15))
    extra = [n for n in mentioned_in_src if n not in writes]
    if extra:
        print()
        print("  另有 %d 个只在源码里被提及（非已知写入形态，但仍属 JS 通道）："
              % len(extra))
        for n in extra[:8]:
            rel, line, _la = mentioned[n][0]
            print("    %-36s 出现于 %s:%d" % (n, rel, line))

    if candidates:
        print()
        print("候选明细（仍须人工确认：可能是第三方打包样式或外部运行期注入）")
        for n in candidates:
            print("  %s" % n)
            for rel, line, _label in no_fb[n][:3]:
                print("      被引用 %s:%d" % (rel, line))

    print()
    print("结论")
    if not args.source:
        print("  警告：未提供 --source，条件 ③（源码写入）未判定——")
        print("        本结果不可用于立论。实测关闭该条件会把运行时注入的")
        print("        令牌全部报成缺失（SiYuan 仓库实测 17/17 假阳性）。")
    print("  三条件同时成立的候选：%d 个" % len(candidates))
    return 0


if __name__ == "__main__":
    sys.exit(main())

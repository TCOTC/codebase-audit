#!/usr/bin/env python3
"""扫描「表单控件有键盘焦点但看不到焦点位置」的候选。

来源：`github/awesome-copilot` 的 `penpot-uiux-design`（MIT）把组件检查清单里的
**状态覆盖**（default / hover / active / disabled / loading）列为核心项；
`a11y.instructions.md`（MIT）把「移除焦点指示器而未给替代」列为键盘类反模式。
本脚本把两者落到 SiYuan 的目录结构上——**只判定可机械判定的部分**。

## 本仓库的机制（决定了这个检查必须怎么做）

`app/src/assets/scss/util/_reset.scss` 对 `button, input, select, textarea`
一律设了 `outline: none`。因此**焦点可见性完全依赖每个组件自己定义
`:focus` / `:focus-visible`**，没定义的就是「焦点不可见」。全仓不存在任何
全局兜底（解析后「无祖先」的焦点规则为 0 条）。

## 三个必须避开的陷阱（都是实测踩出来的，写错就得出相反结论）

| 陷阱 | 错误做法 | 后果 | 正确做法 |
|---|---|---|---|
| **SCSS 嵌套语义** | 只把 `&` 替换成父选择器 | 不含 `&` 的子选择器是**后代**关系，祖先被丢掉 → `.protyle-preview__action button:focus` 被误读成全局 `button:focus`，于是局部规则被当成全局兜底，真缺口被判成「已被覆盖」 | 含 `&` 则替换，不含 `&` 则 `父 + " " + 子` |
| **焦点指示的形态** | 只看 `outline` / `box-shadow` / `border` / `background` | 漏掉 `transform` —— `.b3-slider` 的焦点指示是 `::-webkit-slider-thumb { transform: scale(1.5) }`（滑块放大），会被误报为缺口 | 把 `transform` / `filter` / `opacity` / `color` 一并计入可见变化 |
| **判定单位** | 按**单个类**查是否有焦点规则 | 元素常带多个类，焦点样式可能来自兄弟类 —— `.block__icon.block__icon--show.b3-tooltips.b3-tooltips__n` 的焦点样式来自 `.b3-tooltips:focus-within`，按 `block__icon` 查会漏掉而误报 | 按**元素上的完整类集合**判定：任一成员有焦点规则即算覆盖 |
| **全局兜底的匹配** | 只要存在某个原生标签的焦点规则就算兜底 | `.b3-switch` 是 `<input>`，而全局规则是 `button:focus`，**根本不匹配** | 兜底必须**按该元素的真实标签**匹配，且选择器无祖先 |

## 产出是候选不是结论

本脚本只回答「该表单控件有没有一条会生效的焦点样式」。它**不能**判断：
- 该元素是否真的在 Tab 顺序里（可能被 JS 设了 `tabindex="-1"`）
- 该控件是否被隐藏（`fn__none` / 视觉隐藏的文件输入）
- 键盘是否用方向键而非 Tab 导航（菜单用方向键 + `--current` 修饰类，
  此时 `:focus` 样式确实不是必需的）

因此**必须回读使用点并在真实渲染环境用 Tab 走一遍**再报告。

用法：
    python scan_focus_coverage.py --root app/src --styles app/src/assets/scss \\
                                  --styles app/appearance

`--root` 不存在时以退出码 2 报错——零发现与没扫到在输出上无法区分。
输出为 ASCII 表头 + UTF-8 正文。仅依赖标准库。
"""

import argparse
import io
import os
import re
import sys
from collections import Counter, defaultdict

EXCLUDE_DIR_NAMES = {
    "node_modules", "dist", "build", "stage", ".git", "coverage",
    "__pycache__", "vendor", "types",
}
SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")
STYLE_SUFFIXES = (".scss", ".css", ".sass")
EXCLUDE_FILE_SUFFIXES = (".test.ts", ".test.tsx", ".test.js", ".spec.ts",
                         ".spec.tsx", ".spec.js")
EXCLUDE_FILE_MARKERS = (".min.", ".d.ts")

# 会被 `outline: none` 影响、且原生可聚焦的标签
FORM_TAGS = ("input", "button", "select", "textarea")

FORM_TAG_RX = re.compile(r"<(input|button|select|textarea)\b([^>]{0,700})>", re.I)
CLASS_ATTR_RX = re.compile(r"""class\s*=\s*["']([^"']*)["']""")
# 只接受合法类名：模板插值（`${...}`）、表达式片段（`.?`、`.===`）一律排除，
# 否则会把 `b3-menu__item${!groupByRendered` 这种片段当成类名。
VALID_CLASS_RX = re.compile(r"^[A-Za-z_][\w-]*$")
CLASS_TOKEN_RX = re.compile(r"\.([A-Za-z_][\w-]*)")

# 「焦点时有可见变化」——注意 transform：`.b3-slider` 的指示就是滑块放大。
#
# **负向先行断言必须把 `\s*` 包在里面**：写成 `\s*:\s*(?!none)` 时，
# `\s*` 可以匹配空串，于是 `transform: none` 的 `(?!none)` 在「冒号后一格空格」
# 处成功（看到的是 " none" 而非 "none"）→ `none` 被当成可见变化。
# 实测后果：所有「把变化去掉」的声明反而被判成「有可见变化」，缺口全部消失。
# 正确写法是 `(?!\s*none\b)`——让 `\s*` 参与匹配后再否定。
VISIBLE_RX = re.compile(
    r"(outline(?!-offset)\s*:\s*(?!\s*none\b|\s*0\b)|"
    r"box-shadow\s*:\s*(?!\s*none\b)|"
    r"border[a-z-]*\s*:\s*(?!\s*none\b|\s*0\b)|"
    r"background[a-z-]*\s*:\s*(?!\s*none\b|\s*transparent\b)|"
    r"color\s*:|"
    r"transform\s*:\s*(?!\s*none\b)|"
    r"filter\s*:\s*(?!\s*none\b)|"
    r"opacity\s*:)")
# `:focus-within` 也算：元素自身被聚焦时会命中
FOCUS_RX = re.compile(r":focus(-visible|-within)?")


def iter_files(roots, suffixes):
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


def strip_comments(text):
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def resolve(parents, sel):
    """SCSS 嵌套语义：含 `&` 则替换，不含 `&` 则作为**后代**拼接。

    **这是本脚本最容易写错的一处**：只做 `&` 替换会让不含 `&` 的子选择器
    丢掉全部祖先，把局部规则提升成全局规则（后果见模块 docstring 的陷阱表）。
    """
    parts = [p.strip() for p in sel.split(",") if p.strip()]
    if not parents:
        return [p.replace("&", "") for p in parts] or [""]
    out = []
    for p in parts:
        if "&" in p:
            for par in parents:
                out.append(p.replace("&", par))
        else:
            for par in parents:
                out.append(par + " " + p)
    return out


def parse_style_rules(roots):
    """返回 [(完整选择器, 声明)] —— 处理 SCSS 嵌套与 `&`。"""
    rules = []
    for path, root in iter_files(roots, STYLE_SUFFIXES):
        text = strip_comments(io.open(path, encoding="utf-8",
                                      errors="replace").read())
        stack, buf = [], ""
        for ch in text:
            if ch == "{":
                sel = buf.strip()
                parents = stack[-1] if stack else []
                stack.append(resolve(parents, sel) if sel else parents)
                buf = ""
            elif ch == "}":
                if stack:
                    stack.pop()
                buf = ""
            elif ch == ";":
                raw = buf.strip()
                if raw and stack:
                    for s in stack[-1]:
                        rules.append((s, raw))
                buf = ""
            else:
                buf += ch
    return rules


def collect_usages(roots):
    """返回 [(类集合 frozenset, 标签, 相对路径)]。"""
    uses = []
    for path, root in iter_files(roots, SOURCE_SUFFIXES):
        text = io.open(path, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(path, root).replace("\\", "/")
        for m in FORM_TAG_RX.finditer(text):
            tag, attrs = m.group(1).lower(), m.group(2)
            cm = CLASS_ATTR_RX.search(attrs)
            if not cm:
                continue
            cls = frozenset(c for c in cm.group(1).split()
                            if VALID_CLASS_RX.match(c) and not c.startswith("fn__"))
            if cls:
                uses.append((cls, tag, rel))
    return uses


def index_focus_rules(rules):
    """把「提供可见变化的焦点规则」索引成 类名 → 规则、标签 → 规则。

    索引以**类名**与**裸标签**为键；判定时再按「元素上的完整类集合」查询。
    """
    by_class = defaultdict(list)
    by_tag = defaultdict(list)
    for sel, decl in rules:
        if not FOCUS_RX.search(sel) or not VISIBLE_RX.search(decl):
            continue
        for c in CLASS_TOKEN_RX.findall(sel):
            by_class[c].append(sel)
        s = sel.strip()
        for tag in FORM_TAGS:
            if re.match(r"^" + tag + r"($|[:.\[])", s):
                by_tag[tag].append(sel)
    return by_class, by_tag


def verdict(classes, tag, by_class, by_tag):
    """判定该元素是否有会生效的焦点样式。返回 (是否有, 依据)。

    **按元素上的完整类集合判定**：任一成员命中即可——因为焦点样式常来自
    兄弟类（`.block__icon.b3-tooltips` 的样式来自 `.b3-tooltips:focus-within`），
    按单个类查会误报。

    兜底**按真实标签匹配**：`button:focus` 不得算作 `<input>` 的兜底。

    提到模块级是为了**可被自检直接调用**——判定逻辑写在 main() 里时，
    自检只能测一份副本，而那等于没测。
    """
    for c in sorted(classes):
        if c in by_class:
            return True, "类 `.%s`" % c
    if tag in by_tag:
        return True, "裸标签 `%s`" % tag
    return False, ""


def main():
    parser = argparse.ArgumentParser(
        description="扫描「表单控件有焦点但看不到焦点位置」的候选")
    parser.add_argument("--root", action="append", required=True, metavar="DIR",
                        help="源码根（可重复）")
    parser.add_argument("--styles", action="append", required=True, metavar="DIR",
                        help="样式根（可重复）：SCSS 与主题目录")
    parser.add_argument("--max-list", type=int, default=25,
                        help="每个清单最多列出多少条")
    args = parser.parse_args()

    for label, dirs in (("--root", args.root), ("--styles", args.styles)):
        missing = [d for d in dirs if not os.path.isdir(d)]
        if missing:
            sys.stderr.write("no such directory (%s): %s\n"
                             % (label, ", ".join(missing)))
            return 2

    rules = parse_style_rules(args.styles)
    usages = collect_usages(args.root)
    focus_by_class, tag_focus = index_focus_rules(rules)
    print("=" * 84)
    print("焦点可见性扫描（表单控件）")
    print("=" * 84)
    print()
    print("扫描范围")
    print("  源码文件 : %d 个（%s）"
          % (len(list(iter_files(args.root, SOURCE_SUFFIXES))),
             "、".join(args.root)))
    print("  样式文件 : %d 个（%s）"
          % (len(list(iter_files(args.styles, STYLE_SUFFIXES))),
             "、".join(args.styles)))
    print("  解析出的样式规则 : %d 条" % len(rules))
    print("  含可见焦点变化的类 : %d 个" % len(focus_by_class))
    print("  表单控件使用点 : %d 个" % len(usages))

    covered = Counter()
    gaps = defaultdict(lambda: {"uses": 0, "tags": Counter()})
    for cls, tag, _rel in usages:
        ok, why = verdict(cls, tag, focus_by_class, tag_focus)
        if ok:
            covered[why] += 1
        else:
            g = gaps[cls]
            g["uses"] += 1
            g["tags"][tag] += 1

    n_gap = sum(g["uses"] for g in gaps.values())
    print()
    print("判定结果")
    print("  有焦点指示 : %d" % (len(usages) - n_gap))
    print("  无焦点指示 : %d（%.0f%%）" % (n_gap, 100.0 * n_gap / max(1, len(usages))))
    print("  涉及 %d 种「类集合」组合" % len(gaps))

    print()
    print("  **本仓库的机制**：`util/_reset.scss` 对 button/input/select/textarea")
    print("  一律 `outline: none`，焦点可见性完全依赖组件自己定义 :focus。")
    print("  因此「无焦点指示」不等于缺陷——必须回读使用点并走一遍 Tab。")

    print()
    print("-" * 84)
    print("无焦点指示的形态（按使用点数）")
    print("-" * 84)
    ranked = sorted(gaps.items(), key=lambda kv: -kv[1]["uses"])
    for cls, g in ranked[:args.max_list]:
        tags = ",".join("%s×%d" % (t, n) for t, n in g["tags"].most_common(3))
        print("  %4d 处  %-9s %s"
              % (g["uses"], tags, " ".join("." + c for c in sorted(cls))[:74]))
    if len(ranked) > args.max_list:
        print("  ...另有 %d 种组合" % (len(ranked) - args.max_list))

    print()
    print("-" * 84)
    print("对照：有焦点指示的来源分布（前 %d 个）" % min(8, len(covered)))
    print("-" * 84)
    for why, n in covered.most_common(8):
        print("  %4d 处  %s" % (n, why))

    print()
    print("=" * 84)
    print("下一步（不可省）")
    print("=" * 84)
    print("  1. 逐条回读使用点：该控件是否真的在 Tab 顺序里（`tabindex=\"-1\"` 会排除）")
    print("  2. 确认它没有被隐藏（`fn__none` / 视觉隐藏的文件输入）")
    print("  3. 确认键盘导航方式：若靠方向键 + `--current` 修饰类，`:focus` 不是必需的")
    print("  4. 在真实渲染环境用 Tab 走一遍，比对聚焦前后的计算样式")
    print("     （`getComputedStyle` 前后无差异 = 看不到焦点位置）")
    print("  5. vendored 第三方代码（如 `src/asset/pdf/**`）不要按自研标准要求")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""扫描「表单控件有键盘焦点但看不到焦点位置」的候选。

来源：`github/awesome-copilot` 的 `penpot-uiux-design`（MIT）把组件检查清单里的
**状态覆盖**（default / hover / active / disabled / loading）列为核心项；
`a11y.instructions.md`（MIT）把「移除焦点指示器而未给替代」列为键盘类反模式。
本脚本把两者落到 SiYuan 的目录结构上——**只判定可机械判定的部分**。

## 本仓库的机制（决定了这个检查必须怎么做）

`app/src/assets/scss/util/_reset.scss` 对 `button, input, select, textarea`
一律设了 `outline: none`，因此焦点可见性主要依赖各组件自己的 `:focus` /
`:focus-visible`。**fa729c7c49（#19493）之后又加了一条全局兜底**：

```
:is(button, input, select, textarea)
  :where(:not(.b3-button, .b3-switch, .b3-slider,
              .b3-text-field:not(.b3-text-field--text),
              .b3-select:not(.b3-select--noborder)))
  :focus-visible { outline: 2px solid var(--b3-theme-primary);
                   outline-offset: -2px; }
```

它同时踩中下面表格里的两个陷阱，而**两个方向的错法后果相反**：

- 不认识 `:is()`：兜底被忽略 → `.b3-menu__item`(63)、`.keyboard__action`(38)、
  `.b3-menu__separator`(35)、`.keyboard__slash-item`(21)、`.color__square`(11)、
  `.b3-list-item`(7) 等**已被兜底覆盖**的按钮被报成缺口（实测多报 326 条）；
- 不算特异性：兜底会盖住更高特异性的 `outline: none`，真缺口被报成已覆盖。
  实测两处：`.protyle-preview__action button:focus` (0,2,1) 与
  `.protyle-toolbar__item:focus` (0,2,0)，都高于兜底的 (0,1,1)（#19499 第 2 点）。

## 五个必须避开的陷阱（都是实测踩出来的，写错就得出相反结论）

| 陷阱 | 错误做法 | 后果 | 正确做法 |
|---|---|---|---|
| **SCSS 嵌套语义** | 只把 `&` 替换成父选择器 | 不含 `&` 的子选择器是**后代**关系，祖先被丢掉 → `.protyle-preview__action button:focus` 被误读成全局 `button:focus`，于是局部规则被当成全局兜底，真缺口被判成「已被覆盖」 | 含 `&` 则替换，不含 `&` 则 `父 + " " + 子` |
| **焦点指示的形态** | 只看 `outline` / `box-shadow` / `border` / `background` | 漏掉 `transform` —— `.b3-slider` 的焦点指示是 `::-webkit-slider-thumb { transform: scale(1.5) }`（滑块放大），会被误报为缺口 | 把 `transform` / `filter` / `opacity` / `color` 一并计入可见变化 |
| **判定单位** | 按**单个类**查是否有焦点规则 | 元素常带多个类，焦点样式可能来自兄弟类 —— `.block__icon.block__icon--show.b3-tooltips.b3-tooltips__n` 的焦点样式来自 `.b3-tooltips:focus-within`，按 `block__icon` 查会漏掉而误报 | 按**元素上的完整类集合**判定：任一成员有焦点规则即算覆盖 |
| **全局兜底的匹配** | 只要存在某个原生标签的焦点规则就算兜底 | `.b3-switch` 是 `<input>`，而全局规则是 `button:focus`，**根本不匹配** | 兜底必须**按该元素的真实标签**匹配，且选择器无祖先 |
| **`:is()` / `:where()` 的展开** | 只按「选择器是否以标签名开头」判兜底 | 上游兜底以 `:is(` 开头，永远匹配不上 → 已被覆盖的 326 处被报成缺口 | 先按**顶层**逗号把 `:is(a, b)` / `:where(a, b)` 展开成多条选择器再判定；`:not()` 保留为**谓词**——它的嵌套（`:not(.b3-text-field:not(.b3-text-field--text))`）必须按元素**真实类集合**确定性求值，展开会得出相反结论 |
| **特异性** | 「存在可见焦点声明」就算覆盖 | `:focus { outline: none }` 只要特异性高过兜底就把它反杀，控件仍然没有焦点指示 | 用规范权重（`:where()` 记 0、`:is()`/`:not()` 取参数**最大值**）比较「抑制者」与「提供者」；**提供者的特异性必须严格大于抑制者**才算覆盖 |
| **使用点的枚举面** | 只扫 `<tag ... class="...">` | ① `el.className =` / `classList.add` 赋的类名完全看不到（实测 352 个，339 个不出现在任何 HTML 标签里）；② **不带 `class` 属性**的表单标签（实测 48 处）从不进入任何清单 | 三类分开枚举、分开输出：可回推标签的（`createElement` 绑定）走同一判定，回推不出的按「标签未知」单列，不带 class 的单列并标明「类集合与祖先未知」 |

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

输出三节，**不要混用**：

1. **确定无焦点指示**：所有可能生效的规则都算过特异性后仍然看不到焦点位置。
   这才是「候选缺陷」，仍需回读使用点与真实渲染。
2. **含祖先的抑制规则**：祖先未知（如 `.protyle-preview__action button:focus`），
   无法确定它作用在哪些元素上，**不能计入缺口数**，只列出规则与命中的类名。
3. **运行时赋值 / 不带 class 的表单标签**：标签可能已知（`createElement` 回推），
   也可能未知；未确定的只能人工回读，**不等于缺口**。

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
# vendored 第三方代码：不按自研标准要求（PDF 阅读器是上游 pdf.js 的产物）
VENDORED_PREFIXES = ("asset/pdf/",)

# 会被 `outline: none` 影响、且原生可聚焦的标签
FORM_TAGS = ("input", "button", "select", "textarea")

FORM_TAG_RX = re.compile(r"<(input|button|select|textarea)\b([^>]{0,700})>", re.I)
CLASS_ATTR_RX = re.compile(r"""class\s*=\s*["']([^"']*)["']""")
# 只接受合法类名：模板插值（`${...}`）、表达式片段（`.?`、`.===`）一律排除，
# 否则会把 `b3-menu__item${!groupByRendered` 这种片段当成类名。
VALID_CLASS_RX = re.compile(r"^[A-Za-z_][\w-]*$")
CLASS_TOKEN_RX = re.compile(r"\.([A-Za-z_][\w-]*)")

# ---- 运行时赋类名（使用点枚举的第三类；旧版完全看不到） ----
# `this.element.className = "a b"` / `el.classList.add("a", "b")`。
# 只取引号字面量：模板插值（`` `x ${y}` ``）会拆成片段，片段未必是类名。
ASSIGN_TARGET_RX = re.compile(
    r"([A-Za-z_$][\w$.\[\]'\"]*)\.(?:className|classList)")
CLASSNAME_TAIL_RX = re.compile(r"^\s*=\s*([\"'`])([^\"'`]*)\1")
CLASSLIST_TAIL_RX = re.compile(r"^\s*\.\s*(?:add|toggle)\s*\(([^)]*)\)")
# `const el = document.createElement("button")` —— 唯一能把类名回推成标签的形态
CREATE_ELEMENT_RX = re.compile(
    r"([A-Za-z_$][\w$.\[\]'\"]*)\s*=\s*document\.createElement\(\s*[\"'`]([^\"'`]+)[\"'`]")
STRING_LITERAL_RX = re.compile(r"[\"'`]([^\"'`]*)[\"'`]")

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

# 「抑制」：把轮廓显式去掉。特异性高过提供者时，控件就真的看不到焦点位置。
SUPPRESS_RX = re.compile(r"outline\s*:\s*(?:none|0(?:px)?)\b")
# 「提供」之 outline 分支：有非 none/0 的轮廓值
OUTLINE_VISIBLE_RX = re.compile(
    r"outline\s*:\s*(?!\s*(?:none|0(?:px)?)\b)"
    r"|outline-color\s*:|outline-width\s*:\s*(?!\s*0(?:px)?\b)")
# 「提供」之非 outline 分支：轮廓以外的可见变化（box-shadow / 边框 / 背景 /
# 文字色 / transform / filter / opacity）。单独成组是为了**分属性**处置——
# `outline: none` 只压得住 outline，压不住 box-shadow（`.b3-button` 就靠这个）。
OTHER_VISIBLE_RX = re.compile(
    r"(box-shadow\s*:\s*(?!\s*none\b)|"
    r"border[a-z-]*\s*:\s*(?!\s*none\b|\s*0\b)|"
    r"background[a-z-]*\s*:\s*(?!\s*none\b|\s*transparent\b)|"
    r"color\s*:|"
    r"transform\s*:\s*(?!\s*none\b)|"
    r"filter\s*:\s*(?!\s*none\b)|"
    r"opacity\s*:)")


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

    逗号必须按**顶层**切分：`:is(button, input)` / `:where(:not(.a, .b))` 的
    逗号在括号内，用 `str.split(",")` 会把选择器切成碎片，
    于是上游兜底永远解析不出来（实测：修复前缺口数一度从 326 升到 435）。
    """
    parts = split_selector_list(sel)
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
                if sel.startswith("@"):
                    # at-rule（`@media` / `@supports` / `@keyframes`）：前置部分不是
                    # 选择器，不能当作祖先拼进去（会得到 `X @supports (...) Y` 这种
                    # 永远匹配不上的选择器）。保持父级上下文不变。
                    stack.append(parents)
                else:
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


def split_selector_list(sel):
    """按**顶层**逗号切分选择器：括号内的逗号不切。

    `:is(a, b)` 与 `:not(.a, .b)` 的逗号都在括号内，用 `str.split(",")`
    会把它们切碎。`resolve()` 里的逗号切分是 SCSS 的分组语义，不能改；
    展开 `:is()` 时必须用本函数。
    """
    parts, depth, buf = [], 0, ""
    for ch in sel:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf.strip())
    return [p for p in parts if p]


def matching_paren(text, open_idx):
    """返回与 `text[open_idx] == "("` 配对的闭括号下标；找不到返回 -1。"""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


IS_WHERE_OPEN_RX = re.compile(r":(is|where)\(")
NOT_OPEN_RX = re.compile(r":not\(")


def collapse_is_where(sel, depth=0):
    """把 `:is(a, b)` / `:where(a, b)` 展开成多条选择器。

    上游兜底的选择器是 `:is(button, input, select, textarea):where(:not(...))`，
    不展开就永远匹配不上——这是「多报」的根源。

    **`:not()` 内部不展开**：`:not(:is(a, b))` 等价于「既不是 a 也不是 b」，
    拆成 `:not(a)` 与 `:not(b)` 两条却是「不是 a 或不是 b」，语义相反。
    扫描时遇到 `:not(` 就整段跳过，交给 `match_compound()` 确定性求值。
    """
    if depth > 8:
        return [sel]
    idx, i, n = None, 0, len(sel)
    while i < n:
        m = IS_WHERE_OPEN_RX.search(sel, i)
        if not m:
            break
        # `:not(` 恰好占 5 个字符，紧接其后的 `:is(` / `:where(` 才算「在里面」
        nm = NOT_OPEN_RX.match(sel, max(0, m.start() - 5))
        if nm and nm.end() == m.start():
            close = matching_paren(sel, nm.end() - 1)
            if close < 0:
                break
            i = close + 1
            continue
        idx = m.start()
        break
    if idx is None:
        return [sel]
    open_idx = sel.index("(", idx)
    close_idx = matching_paren(sel, open_idx)
    if close_idx < 0:
        return [sel]
    inner = sel[open_idx + 1:close_idx]
    prefix, suffix = sel[:idx], sel[close_idx + 1:]
    out = []
    for alt in split_selector_list(inner):
        for rest in collapse_is_where(prefix + alt + suffix, depth + 1):
            out.append(rest)
    return out or [sel]


def has_combinator(sel):
    """选择器是否含**顶层**组合子（后代 / `>` / `+` / `~`）。

    括号内的空格不算：`:not(.a .b)` 是谓词，不是后代关系。
    含组合子意味着「祖先未知」，本脚本无法确定它落在哪些元素上——
    计入缺口会误报（把局部规则当成作用于全部同类元素）。
    """
    depth = 0
    for ch in sel:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif depth == 0 and ch in " \t\n>+~":
            return True
    return False


COMPOUND_CLASS_RX = re.compile(r"\.([A-Za-z_][\w-]*)")
COMPOUND_PSEUDO_RX = re.compile(r"::?([A-Za-z-]+)")
COMPOUND_TAG_RX = re.compile(r"([A-Za-z][\w-]*)")
PSEUDO_ELEMENTS = {
    "before", "after", "first-line", "first-letter", "selection",
    "placeholder", "marker", "backdrop", "file-selector-button",
}


def parse_compound(compound):
    """把一个 compound（无组合子的选择器）拆成 (标签, 类集合, 伪类列表)。

    伪类写作 `(名字, 参数)`，无参数时参数为 None。
    返回 None 表示无法解析——调用方按「无法判定」处理，**不得**当成不匹配。
    """
    tag, classes, pseudos = None, set(), []
    i, n = 0, len(compound)
    while i < n:
        ch = compound[i]
        if ch == ".":
            m = COMPOUND_CLASS_RX.match(compound, i)
            if not m:
                return None
            classes.add(m.group(1))
            i = m.end()
        elif ch == ":":
            m = COMPOUND_PSEUDO_RX.match(compound, i)
            if not m:
                return None
            name = ":" + m.group(1).lower()
            i = m.end()
            if i < n and compound[i] == "(":
                end = matching_paren(compound, i)
                if end < 0:
                    return None
                pseudos.append((name, compound[i + 1:end]))
                i = end + 1
            else:
                pseudos.append((name, None))
        elif ch == "[":
            end = compound.find("]", i)
            if end < 0:
                return None
            i = end + 1
        elif ch == "*":
            i += 1
        else:
            m = COMPOUND_TAG_RX.match(compound, i)
            if not m:
                return None
            tag = m.group(1).lower()
            i = m.end()
    return tag, classes, pseudos


def match_compound(compound, tag, classes):
    """判断一个**无组合子**的选择器是否匹配 (标签, 类集合)。

    三态：`True` 匹配 / `False` 确定不匹配 / `None` 无法判定。
    调用方对 `None` 按**宽松**处理（宁多报勿漏报）——本脚本产出的是候选清单。

    `:not()` 按元素**真实类集合**确定性求值是承重的：本仓库的兜底靠
    `:not(.b3-text-field:not(.b3-text-field--text))` 让 `--text` 变体吃轮廓，
    嵌套 `:not` 必须逐层求解；把外层拍平会得出相反结论。
    """
    parsed = parse_compound(compound.strip())
    if parsed is None:
        return None
    ctag, cclasses, pseudos = parsed
    if ctag and ctag != tag:
        return False
    if not cclasses.issubset(classes):
        return False
    for name, inner in pseudos:
        if inner is None:
            continue
        alts = split_selector_list(inner)
        if name == ":not":
            if any(match_compound(a, tag, classes) is True for a in alts):
                return False
            continue
        if name in (":is", ":where"):
            vals = [match_compound(a, tag, classes) for a in alts]
            if all(v is False for v in vals):
                return False
            continue
        # 其余带参伪类（:nth-child / :lang / …）宽松视为可成立
        continue
    return True


def specificity(sel):
    """按选择器规范计算 (id, class, type) 权重，用于比较「谁盖过谁」。

    两个承重细节：
    - **`:where()` 记 0、`:is()`/`:not()` 取参数最大值**。上游兜底靠
      `:where(:not(...))` 把排除项压到 0，总权重才是 (0,1,1)；把 `:not()` 里的
      类算进去会变成 (0,3,1)，反而压过组件自身的 `.foo:focus`。
    - **必须在展开 `:is()` 之前算**：展开后 `:is(button, input)` 的结构就丢了。
    """
    a = b = c = 0
    i, n = 0, len(sel)
    while i < n:
        ch = sel[i]
        if ch == "[":
            end = sel.find("]", i)
            i = n if end < 0 else end + 1
            b += 1
            continue
        if ch == "#":
            m = re.match(r"#([A-Za-z_][\w-]*)", sel[i:])
            if m:
                a += 1
                i += m.end()
            else:
                i += 1
            continue
        if ch == ".":
            m = re.match(r"\.([A-Za-z_][\w-]*)", sel[i:])
            if m:
                b += 1
                i += m.end()
            else:
                i += 1
            continue
        if ch == ":":
            m = re.match(r"::?([A-Za-z-]+)", sel[i:])
            if not m:
                i += 1
                continue
            name = m.group(1).lower()
            i += m.end()
            inner = None
            if i < n and sel[i] == "(":
                end = matching_paren(sel, i)
                if end < 0:
                    continue
                inner = sel[i + 1:end]
                i = end + 1
            if name == "where":
                continue
            if name in ("is", "not", "has", "matches", "any"):
                best = (0, 0, 0)
                for alt in (split_selector_list(inner) if inner else []):
                    s = specificity(alt)
                    if s > best:
                        best = s
                a += best[0]
                b += best[1]
                c += best[2]
                continue
            if name in PSEUDO_ELEMENTS:
                c += 1
            else:
                b += 1
            continue
        if ch == "*":
            i += 1
            continue
        if ch in " \t\n>+~,":
            i += 1
            continue
        m = COMPOUND_TAG_RX.match(sel, i)
        if m:
            c += 1
            i = m.end()
        else:
            i += 1
    return (a, b, c)


def classify_decl(decl):
    """把单条声明归类成 (抑制轮廓, 提供轮廓, 提供其它可见变化)。"""
    return (bool(SUPPRESS_RX.search(decl)),
            bool(OUTLINE_VISIBLE_RX.search(decl)),
            bool(OTHER_VISIBLE_RX.search(decl)))


def collect_focus_rules(rules):
    """把样式规则编译成焦点规则记录，分「无祖先」与「祖先未知」两批。

    每条记录带：展开后的选择器、**原始选择器的特异性**、三类声明标记、
    以及它涉及的类名（用于按类索引）。
    """
    plain, ancestral = [], []
    for sel, decl in rules:
        if not FOCUS_RX.search(sel):
            continue
        suppress, outline_prov, other_prov = classify_decl(decl)
        if not (suppress or outline_prov or other_prov):
            continue
        spec = specificity(sel)
        for expanded in collapse_is_where(sel):
            rec = {
                "sel": expanded.strip(),
                "spec": spec,
                "suppress": suppress,
                "outline": outline_prov,
                "other": other_prov,
                "classes": frozenset(CLASS_TOKEN_RX.findall(expanded)),
            }
            (ancestral if has_combinator(expanded) else plain).append(rec)
    return plain, ancestral


def collect_usages(roots):
    """返回 HTML 字符串里的表单控件使用点。

    每项：(类集合, 标签, 相对路径, 行号, 形态)。
    形态 `html` = 带 class 属性；`classless` = **没有** class 属性。
    旧版只收 `html`，于是不带 class 的控件（实测 48 处）从不进入任何清单——
    它们的样式可能来自祖先选择器（`.protyle-preview__action button:focus`）。
    """
    uses = []
    for path, root in iter_files(roots, SOURCE_SUFFIXES):
        text = io.open(path, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(path, root).replace("\\", "/")
        for m in FORM_TAG_RX.finditer(text):
            tag, attrs = m.group(1).lower(), m.group(2)
            line = text.count("\n", 0, m.start()) + 1
            cm = CLASS_ATTR_RX.search(attrs)
            if not cm:
                uses.append((frozenset(), tag, rel, line, "classless"))
                continue
            cls = frozenset(c for c in cm.group(1).split()
                            if VALID_CLASS_RX.match(c) and not c.startswith("fn__"))
            if cls:
                uses.append((cls, tag, rel, line, "html"))
    return uses


def collect_runtime_classes(roots):
    """扫运行时赋类名（`.className =` / `classList.add|toggle`）。

    返回 `(可判定的使用点, 标签未知的类名 → {文件:行})`。
    能判定是因为形如 `const el = document.createElement("button")`
    后接 `el.className = "…"` 时，**标签可以回推**——这条路径以前完全看不到，
    且 #19499 第 2 点的两处缺陷正落在其中。

    回推不出来的不能静默丢弃：它们是「有这么多类名枚举不到」的上界，
    必须单独输出并写明不能当成缺口。
    """
    known, unknown = [], defaultdict(set)
    for path, root in iter_files(roots, SOURCE_SUFFIXES):
        text = io.open(path, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(path, root).replace("\\", "/")
        created = {m.group(1): m.group(2).lower()
                   for m in CREATE_ELEMENT_RX.finditer(text)}
        if not created:
            continue
        for m in ASSIGN_TARGET_RX.finditer(text):
            tag = created.get(m.group(1))
            rest = text[m.end():m.end() + 400]
            names = set()
            cm = CLASSNAME_TAIL_RX.match(rest)
            if cm:
                names.update(cm.group(2).split())
            lm = CLASSLIST_TAIL_RX.match(rest)
            if lm:
                names.update(s.group(1)
                             for s in STRING_LITERAL_RX.finditer(lm.group(1)))
            names = {x for x in names if VALID_CLASS_RX.match(x)}
            if not names:
                continue
            line = text.count("\n", 0, m.start()) + 1
            if tag in FORM_TAGS:
                known.append((frozenset(names), tag, rel, line, "runtime"))
            else:
                for x in names:
                    unknown[x].add("%s:%d" % (rel, line))
    return known, unknown


def _max_spec(cur, new):
    """特异性取大者（None 表示还没有）。"""
    if cur is None or new > cur:
        return new
    return cur


def index_focus_rules(rules):
    """把「无祖先的焦点规则」索引成 类名 → 记录、标签 → 记录。

    索引以**类名**与**裸标签**为键；判定时再按「元素上的完整类集合」查询。
    含祖先的规则**不进索引**（祖先未知，计入缺口会误报），
    由 main() 单独列成「含祖先的抑制规则」一节。
    """
    plain, _ancestral = collect_focus_rules(rules)
    by_class = defaultdict(list)
    by_tag = defaultdict(list)
    for rec in plain:
        for c in rec["classes"]:
            by_class[c].append(rec)
        m = COMPOUND_TAG_RX.match(rec["sel"])
        if m and m.group(1).lower() in FORM_TAGS:
            by_tag[m.group(1).lower()].append(rec)
    return by_class, by_tag


def verdict(classes, tag, by_class, by_tag):
    """判定该元素是否有会生效的焦点样式。返回 (是否有, 依据)。

    **按元素上的完整类集合判定**：任一成员命中即可——因为焦点样式常来自
    兄弟类（`.block__icon.b3-tooltips` 的样式来自 `.b3-tooltips:focus-within`），
    按单个类查会误报。

    兜底**按真实标签匹配**：`button:focus` 不得算作 `<input>` 的兜底。

    **算特异性**：`outline: none` 只要特异性高过提供者就把它反杀，控件仍然
    看不到焦点位置（#19499 第 2 点）。**分属性比较**——抑制只压得住 outline，
    压不住 box-shadow（`.b3-button` 就靠 box-shadow）。

    提到模块级是为了**可被自检直接调用**——判定逻辑写在 main() 里时，
    自检只能测一份副本，而那等于没测。
    """
    cands = []
    for c in sorted(classes):
        cands.extend(by_class.get(c, ()))
    cands.extend(by_tag.get(tag, ()))
    if not cands:
        return False, ""
    suppress = other = outline = None
    why = ""
    for rec in cands:
        if match_compound(rec["sel"], tag, classes) is False:
            continue
        if rec["suppress"]:
            suppress = _max_spec(suppress, rec["spec"])
        if rec["other"]:
            other = _max_spec(other, rec["spec"])
            why = why or rec["sel"]
        if rec["outline"]:
            outline = _max_spec(outline, rec["spec"])
            why = why or rec["sel"]
    if other is not None and (suppress is None or other >= suppress):
        return True, "规则 `%s`" % why
    if outline is not None and (suppress is None or outline > suppress):
        return True, "规则 `%s`" % why
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
    runtime_known, runtime_unknown = collect_runtime_classes(args.root)
    usages.extend(runtime_known)
    _plain, ancestral = collect_focus_rules(rules)
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
    forms = Counter(u[4] for u in usages)
    print("    其中：HTML 带 class %d / 运行时回推 %d / **无 class** %d"
          % (forms["html"], forms["runtime"], forms["classless"]))

    covered = Counter()
    gaps = defaultdict(lambda: {"uses": 0, "tags": Counter()})
    for cls, tag, _rel, _line, _form in usages:
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
    print("  无焦点指示 : %d（%.0f%%）"
          % (n_gap, 100.0 * n_gap / max(1, len(usages))))
    print("  涉及 %d 种「类集合」组合" % len(gaps))
    print()
    print("  **本仓库的机制**：`util/_reset.scss` 对 button/input/select/textarea")
    print("  一律 `outline: none`；fa729c7c49 之后又有一条 `:is(...):where(:not(...))`")
    print("  全局兜底，因此本脚本必须展开 `:is()` / `:where()` 并比较特异性后")
    print("  才能说「无焦点指示」。即便如此，它也不等于缺陷——")
    print("  必须回读使用点并走一遍 Tab。")

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

    # 第二节：含祖先的抑制规则。祖先未知，**不能计入缺口数**，只列出来。
    print()
    print("-" * 84)
    print("含祖先的抑制规则（`outline: none`，但选择器带祖先）")
    print("-" * 84)
    seen = set()
    sup_anc = []
    for rec in ancestral:
        if not rec["suppress"] or rec["sel"] in seen:
            continue
        seen.add(rec["sel"])
        sup_anc.append(rec)
    if not sup_anc:
        print("  （无）")
    for rec in sup_anc[:args.max_list]:
        print("  特异性 %-9s %s" % (str(rec["spec"]), rec["sel"][:70]))
    if len(sup_anc) > args.max_list:
        print("  ...另有 %d 条" % (len(sup_anc) - args.max_list))
    print("  祖先未知 → **不知道它作用在哪些元素上**，不能当成缺口；")
    print("  但若其特异性高于全局兜底，命中的控件就没有焦点指示。")
    print("  实例：#19499 第 2 点（`.protyle-toolbar__item:focus` 无祖先，已被计入")
    print("  上面的缺口；`.protyle-preview__action button:focus` 有祖先，落在本节）。")

    # 第三节：运行时赋类名中回推不出标签的。不能静默丢弃。
    print()
    print("-" * 84)
    print("运行时赋类名：标签未知的类名（不可判定）")
    print("-" * 84)
    no_rule = {x: v for x, v in runtime_unknown.items()
               if x not in focus_by_class}
    print("  运行时赋类名且**回推不出标签**的类名 : %d 个" % len(runtime_unknown))
    print("    其中样式里**完全没有**焦点规则的 : %d 个" % len(no_rule))
    print("  **这是上界，不是缺口数**：`div` 上也常赋同类名，")
    print("  静态无法确定元素标签，因此只能人工回读。")
    for x in sorted(no_rule)[:args.max_list]:
        print("  %-46s %s"
              % (x, ", ".join(sorted(no_rule[x])[:2])[:34]))
    if len(no_rule) > args.max_list:
        print("  ...另有 %d 个" % (len(no_rule) - args.max_list))

    # 第四节：没有 class 的表单标签。类集合与祖先都未知。
    print()
    print("-" * 84)
    print("不带 class 属性的表单标签（类集合与祖先未知）")
    print("-" * 84)
    classless = [u for u in usages if u[4] == "classless"]
    vendored = [u for u in classless if u[2].startswith(VENDORED_PREFIXES)]
    classless = [u for u in classless if not u[2].startswith(VENDORED_PREFIXES)]
    print("  自研代码 %d 处（vendored 的 PDF 阅读器另 %d 处，不按自研标准要求）"
          % (len(classless), len(vendored)))
    print("  它们会被全局兜底覆盖（无排除类），但若祖先里有更高")
    print("  特异性的 `outline: none`（见上节），实际就没有焦点指示。")
    for cls, tag, rel, line, _form in classless[:args.max_list]:
        print("  %-9s %s:%d" % ("<" + tag + ">", rel, line))
    if len(classless) > args.max_list:
        print("  ...另有 %d 处" % (len(classless) - args.max_list))

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

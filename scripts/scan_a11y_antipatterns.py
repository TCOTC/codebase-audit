#!/usr/bin/env python3
"""扫描可机械检出的无障碍（a11y）行为反模式候选。

来源：`github/awesome-copilot` 的 `a11y.instructions.md`（MIT）与
`accessibility-runtime-tester.agent.md`（MIT）中的反模式清单，
**按本 skill 的边界裁剪**后落到 SiYuan 的目录结构上。

上游方法论的两条硬约束已内化：① 不得把推测的辅助技术行为当作事实报告，
必须有运行期证据；② 「Lighthouse 通过」不是无障碍的证明，
也不得因静态语义正确就停止（反之亦然）。

## 本脚本只覆盖三类，且都是「行为」而非「外观」

判据 I 的边界是：只管行为（状态、可达性、约束、反馈），不管外观。
因此这里**不含**对比度、配色、字号、动效等视觉项——那些属于 a11y 工具
（axe / Lighthouse）与设计审查，不是本 skill 的范围。

| 编号 | 反模式 | 为何可机械检出 |
|---|---|---|
| K2 | 正整数 `tabindex` | 破坏 DOM 顺序，是纯语法特征 |
| K5 | `outline: none` 且同选择器无 `:focus` 替代 | SCSS 可按选择器分块解析 |
| A6 | 纯图标按钮没有可访问名 | `<button>` 内只有 `svg`/`use` 且无 `aria-label`/文本 |

其余反模式（A2 `aria-hidden` 包裹可聚焦元素、A3 `role` 缺必需属性、
K3 焦点陷阱无 Esc、K6 仅 hover 无 focus、K7 关闭后焦点不回位）
**需要跨行/跨文件的语义判断**，脚本只给出提示位点，判定必须人工完成——
详见 `references/patterns.md` 的 P40 与 `SKILL.md` 判据 I3。

用法：
    python scan_a11y_antipatterns.py --root app/src
    python scan_a11y_antipatterns.py --root app/src --styles app/src/assets/scss

输出为 ASCII 表头 + UTF-8 正文。扫描根不存在时以退出码 2 报错——
零发现与没扫到在输出上无法区分，静默输出「0 个」会让使用者以为没有问题。
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
EXCLUDE_FILE_SUFFIXES = (".test.ts", ".test.tsx", ".test.js", ".spec.ts",
                         ".d.ts", ".min.js", ".min.css")

# --- K2：正整数 tabindex ------------------------------------------------------
POSITIVE_TABINDEX = re.compile(
    r"""tabindex\s*=\s*["']?[1-9]\d*|tabIndex\s*=\s*\{\s*[1-9]\d*|"""
    r"""\.tabIndex\s*=\s*[1-9]\d*""")

# --- K5：outline: none（需按选择器判定是否有 :focus 替代）--------------------
OUTLINE_NONE = re.compile(r"""outline\s*:\s*(?:none|0|0px)\s*(?:;|$)""")
FOCUS_RULE = re.compile(r""":focus(?:-visible|-within)?\b""")

# 判定「该选择器的类名是否落在可聚焦元素上」。
# **不加这道核对就几乎全是假阳性**：实测 `.av` / `.emojis` / `.b3-form` 都是容器，
# 容器本就不会出现焦点轮廓，对它 `outline: none` 是无害的。
# a11y 原文档也明确警告「不要把推测的辅助技术行为当成事实来报」。
FOCUSABLE_TAGS = ("<button", "<a ", "<input", "<select", "<textarea",
                  "[tabindex", "contenteditable", 'role="button"',
                  'role="tab"', 'role="checkbox"', 'role="menuitem"')
CLASS_TOKEN = re.compile(r"\.([A-Za-z_][\w-]*)")


def rel_path(path, roots):
    """输出以扫描根为基准的相对路径。

    **必须传 `start`**：`os.path.relpath(path)` 不传第二个参数时以 **cwd** 为基准，
    而 `--root` 可以是任意路径；两者不同盘时（Windows：`d:\\...` 与 `c:\\...`）
    直接抛 `ValueError: path is on mount 'd:', start on mount 'C:'`，
    **整个脚本崩溃、一条结论都输不出**。

    实测这个缺陷长期存在而未被发现：自检只在「cwd 与仓库同盘」时跑过，
    一旦在 skill 目录（C:）下扫描 D: 上的仓库就全崩。
    教训：**测试结果依赖 cwd 的通过是假通过**——工具的输出路径应以扫描根为基准，
    而不是以「碰巧在哪运行」为基准。
    """
    for root in roots or ():
        try:
            return os.path.relpath(path, root).replace("\\", "/")
        except ValueError:
            continue
    return path.replace("\\", "/")


def class_lands_on_focusable(roots, class_name):
    """返回一个命中说明，或 None。检测窗口是含该类名的那一行及其后 2 行。"""
    needle = class_name
    for path in iter_files(roots, (".ts", ".tsx", ".js")):
        text = io.open(path, encoding="utf-8", errors="replace").read()
        if needle not in text:
            continue
        lines = text.split("\n")
        for no, line in enumerate(lines, 1):
            if needle not in line:
                continue
            window = " ".join(lines[no - 1:no + 2])
            if any(sig in window for sig in FOCUSABLE_TAGS):
                # 仅当类名与可聚焦标签在同一窗口内，才认为它作用于可聚焦元素
                if ("." + class_name) in window or ("\"" + class_name) in window \
                        or ("'" + class_name) in window or (" " + class_name) in window:
                    return "%s:%d" % (rel_path(path, roots), no)
    return None

# --- A6：纯图标按钮无可访问名 -------------------------------------------------
BUTTON_OPEN = re.compile(r"""<button\b[^>]*>""", re.I)
NAME_SIGNALS = re.compile(
    r"""aria-label\s*=|aria-labelledby\s*=|title\s*=|data-tip\s*=""", re.I)
ICON_ONLY = re.compile(r"""^\s*<(?:svg|use|img|i|span\s+class=["'][^"']*icon)\b""", re.I)
VISIBLE_TEXT = re.compile(r""">\s*[^\s<][^<]*""")
# 按钮自身的结束标签——必须先按它裁切，否则会把 JS 字符串的收尾当成按钮内文字。
BUTTON_CLOSE = re.compile(r"</button>", re.I)

# --- 提示位点（需人工判定，不计入结论）--------------------------------------
HINT_SIGNALS = (
    (re.compile(r"""aria-hidden\s*[=:]\s*["']?true"""),
     "A2 需确认被隐藏的元素内不含可聚焦内容"),
    (re.compile(r"""role\s*=\s*["'](?:tab|checkbox|combobox|slider|switch|menuitem)["']"""),
     "A3 需确认带必需 aria-* 属性（tab→aria-selected 等）"),
    (re.compile(r"""addEventListener\(\s*["']mouseenter["']"""),
     "K6 需确认配对的 focus 处理"),
    (re.compile(r"""addEventListener\(\s*["']mouseover["']"""),
     "K6 需确认配对的 focus 处理"),
    (re.compile(r"""classList\.(?:add|remove)\(\s*["'][^"']*(?:dialog|modal|popover|menu)[^"']*["']"""),
     "K3/K7 需确认真实渲染下的焦点陷阱与关闭后焦点回位"),
)


def iter_files(roots, exts):
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dir_path, dir_names, file_names in os.walk(root):
            dir_names[:] = [d for d in dir_names
                            if d not in EXCLUDE_DIR_NAMES and not d.startswith(".")]
            for name in file_names:
                if not name.endswith(exts):
                    continue
                if name.endswith(EXCLUDE_FILE_SUFFIXES):
                    continue
                yield os.path.join(dir_path, name)


def iter_scss_blocks(text):
    """把 SCSS 粗解析成 (选择器, 起始行, 块体)。不做完整 SCSS 语法分析。"""
    lines = text.split("\n")
    depth = 0
    sel_parts = []
    start = 1
    body = []
    for no, line in enumerate(lines, 1):
        code = re.sub(r"/\*.*?\*/", "", line)
        if depth == 0:
            stripped = code.strip()
            if not stripped or stripped.startswith("//"):
                continue
            if "{" in code:
                sel_parts.append(code.split("{")[0].strip())
                depth = code.count("{") - code.count("}")
                start = no
                body = [code.split("{", 1)[1]]
                if depth == 0:
                    yield " ".join(sel_parts).strip(), start, "\n".join(body)
                    sel_parts = []
                continue
            sel_parts.append(stripped)
        else:
            depth += code.count("{") - code.count("}")
            body.append(code)
            if depth <= 0:
                yield " ".join(sel_parts).strip(), start, "\n".join(body)
                sel_parts = []
                body = []
                depth = 0


def scan_styles(styles_roots):
    """K5：返回 [(相对路径, 行号, 选择器, 有同选择器 :focus 替代, 文件内是否有 :focus)]。"""
    findings = []
    for path in iter_files(styles_roots, (".scss", ".css")):
        text = io.open(path, encoding="utf-8", errors="replace").read()
        blocks = list(iter_scss_blocks(text))
        focus_selectors = {sel for sel, _, body in blocks if FOCUS_RULE.search(sel)}
        focus_anywhere = bool(FOCUS_RULE.search(text))
        for sel, no, body in blocks:
            if not OUTLINE_NONE.search(body):
                continue
            base = re.sub(r":{1,2}[a-zA-Z-]+.*$", "", sel).strip()
            # 同一选择器（或其 :focus 变体）在本文件里有替代 → 不是缺陷
            replaced = any(fs.startswith(base) or base in fs for fs in focus_selectors)
            findings.append((path, no, sel, replaced, focus_anywhere))
    return findings


def scan_k2(roots):
    out = []
    for path in iter_files(roots, (".ts", ".tsx", ".js")):
        text = io.open(path, encoding="utf-8", errors="replace").read()
        for m in POSITIVE_TABINDEX.finditer(text):
            no = text.count("\n", 0, m.start()) + 1
            out.append((path, no, text.split("\n")[no - 1].strip()[:110]))
    return out


def scan_icon_buttons(roots):
    """A6：`<button>` 内只有图标、且没有可访问名。

    **必须先把标签串裁到 `</button>` 为止**（下面那行 `BUTTON_CLOSE` 的处理）。
    不做裁切时，JS 字符串在同一行收尾的写法会被系统性漏掉：

        html += '<button class="x" data-action="copy"><svg>…</svg></button>';

    `first_line` 取到的是整行（含末尾的 `';`），`VISIBLE_TEXT`（`>\\s*[^\\s<][^<]*`）
    会命中 `>';`，于是按钮被误判为「有文本名」。
    而对多行模板（以 `</button>` + 换行结尾）不命中，于是被正常报出——
    **同一形态的按钮，因字符串是否在同一行收尾而时报时不报**。
    实测该缺陷使 SiYuan 的 A6 由 37 条降到 31 条（漏掉 6 条，
    其中 4 条集中在 `protyle/toolbar/index.ts` 的同一个模板里）。
    """
    out = []
    for path in iter_files(roots, (".ts", ".tsx", ".js")):
        text = io.open(path, encoding="utf-8", errors="replace").read()
        for m in BUTTON_OPEN.finditer(text):
            open_tag = m.group(0)
            if NAME_SIGNALS.search(open_tag):
                continue
            rest = text[m.end():m.end() + 200]
            first_line = rest.split("\n", 1)[0]
            close = BUTTON_CLOSE.search(first_line)
            if close:
                first_line = first_line[:close.start()]
            if not ICON_ONLY.match(first_line):
                continue
            # 紧跟的文本若含可见字符，则按钮有文本名
            tail = ICON_ONLY.sub("", first_line)
            if VISIBLE_TEXT.search(tail):
                continue
            no = text.count("\n", 0, m.start()) + 1
            out.append((path, no, (open_tag + first_line)[:120]))
    return out


def scan_hints(roots):
    out = []
    for path in iter_files(roots, (".ts", ".tsx", ".js")):
        text = io.open(path, encoding="utf-8", errors="replace").read()
        lines = text.split("\n")
        for rx, why in HINT_SIGNALS:
            for m in rx.finditer(text):
                no = text.count("\n", 0, m.start()) + 1
                out.append((why, path, no, lines[no - 1].strip()[:100]))
    return out


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", action="append", default=None,
                        help="源码根目录，可重复。默认 app/src")
    parser.add_argument("--styles", action="append", default=None,
                        help="样式根目录（SCSS/CSS）。不提供则跳过 K5")
    parser.add_argument("--out", default=None, help="输出文件；缺省写 stdout")
    parser.add_argument("--max-list", type=int, default=30, help="每类最多列出多少条")
    args = parser.parse_args()

    roots = args.root or ["app/src"]
    absent = [r for r in roots + (args.styles or []) if not os.path.isdir(r)]
    if absent:
        sys.stderr.write(
            "no such directory: %s\n"
            "零发现与没扫到在输出上无法区分，故以退出码 2 报错而不是输出 0 个。\n"
            % ", ".join(absent))
        return 2

    out = []
    out.append("a11y 行为反模式候选（判据 I3）")
    out.append("=" * 74)
    out.append("源码根 : %s" % ", ".join(roots))
    out.append("样式根 : %s" % (", ".join(args.styles) if args.styles
                              else "未提供（跳过 K5）"))
    out.append("")
    out.append("**边界**：本脚本只覆盖「行为」类反模式（可达性 / 焦点 / 语义）。")
    out.append("对比度、配色、字号、动效属「外观」，不在本 skill 范围——")
    out.append("那些用 a11y 工具（axe / Lighthouse）与设计审查，不要在此报告。")
    out.append("")
    out.append("**产出是候选不是结论**：每条都要回读使用点确认。")
    out.append("")

    # K2
    k2 = scan_k2(roots)
    out.append("-" * 74)
    out.append("K2 正整数 tabindex（破坏 DOM 顺序）：%d 个" % len(k2))
    out.append("-" * 74)
    if not k2:
        out.append("  （无）—— 这是干净的信号，正整数 tabindex 没有任何正当场景")
    for path, no, line in k2[:args.max_list]:
        out.append("  %s:%d" % (rel_path(path, roots), no))
        out.append("     %s" % line)
    out.append("")

    # A6
    a6 = scan_icon_buttons(roots)
    out.append("-" * 74)
    out.append("A6 纯图标按钮无可访问名：%d 个" % len(a6))
    out.append("-" * 74)
    if not a6:
        out.append("  （无）")
    for path, no, line in a6[:args.max_list]:
        out.append("  %s:%d" % (rel_path(path, roots), no))
        out.append("     %s" % line)
    if len(a6) > args.max_list:
        out.append("  ...另有 %d 个" % (len(a6) - args.max_list))
    out.append("")

    # K5
    if args.styles:
        k5 = scan_styles(args.styles)
        unreplaced = [f for f in k5 if not f[3]]
        # 再用源码交叉核对：只看类名确实落在可聚焦元素上的（否则是容器，非缺陷）
        confirmed, container_like = [], []
        for path, no, sel, _, focus_anywhere in unreplaced:
            tokens = CLASS_TOKEN.findall(sel)
            hit = None
            for token in tokens:
                hit = class_lands_on_focusable(roots, token)
                if hit:
                    break
            (confirmed if hit else container_like).append(
                (path, no, sel, focus_anywhere, hit))

        out.append("-" * 74)
        out.append("K5 `outline:none` 且同选择器无 `:focus` 替代")
        out.append("    经源码核对落在可聚焦元素上：%d 个" % len(confirmed))
        out.append("    未见落在可聚焦元素上（多为容器，**不是缺陷**）：%d 个"
                   % len(container_like))
        out.append("    （候选总数 %d，其中 %d 个已有 :focus 替代）"
                   % (len(k5), len(k5) - len(unreplaced)))
        out.append("-" * 74)
        if not confirmed:
            out.append("  （无）")
        for path, no, sel, focus_anywhere, hit in confirmed[:args.max_list]:
            out.append("  %s:%d" % (rel_path(path, roots), no))
            out.append("     选择器: %s" % sel[:88])
            out.append("     类名命中可聚焦元素: %s" % hit)
            out.append("     （本文件其它位置%s `:focus` 规则）"
                       % ("有" if focus_anywhere else "无"))
        if len(confirmed) > args.max_list:
            out.append("  ...另有 %d 个" % (len(confirmed) - args.max_list))
        out.append("")
        out.append("  提醒：K5 的判定是启发式的两层过滤（选择器有 :focus 替代 → 类名落在可聚焦元素）。")
        out.append("  全局 `:focus-visible` 样式（写在别处）仍会让本项成为假阳性——")
        out.append("  报告前必须在真实渲染环境里用 Tab 键确认焦点指示器是否可见。")
        out.append("  下方「未见落在可聚焦元素上」的 %d 条**不要报告**，它们多半是容器。"
                   % len(container_like))
        out.append("")

    # Hints
    hints = scan_hints(roots)
    out.append("-" * 74)
    out.append("提示位点（**需人工判定，不是结论**）：%d 个" % len(hints))
    out.append("-" * 74)
    by_why = {}
    for why, path, no, line in hints:
        by_why.setdefault(why, []).append((path, no, line))
    for why, items in sorted(by_why.items()):
        out.append("  %s —— %d 处" % (why, len(items)))
        for path, no, line in items[:4]:
            out.append("     %s:%d  %s"
                       % (rel_path(path, roots), no, line[:80]))
        if len(items) > 4:
            out.append("     ...另有 %d 处" % (len(items) - 4))
    out.append("")
    out.append("=" * 74)
    out.append("下一步（不可省）：")
    out.append("  1. K2 可直接判定——正整数 tabindex 无正当场景，逐条回读确认非测试数据即可")
    out.append("  2. A6 要确认该 `<button>` 是否真有可见文本名（脚本只看首行）")
    out.append("  3. K5 必须在真实渲染环境用 Tab 键确认焦点指示器，脚本只是启发")
    out.append("  4. 提示位点逐条按 P40 的检查法语义判定，不要按数量报告")
    out.append("  5. 「业务表现」要写成键盘操作路径，例如")
    out.append("      「设置 - 外观，按 Tab 走到 X 按钮时看不到焦点位置」")
    out.append("   6. **不要报对比度/配色/字号/动效** —— 那属外观，不在本 skill 范围；")
    out.append("      且不要把「Lighthouse 通过」当成无障碍的证明（上游方法论明确警告）")
    text = "\n".join(out) + "\n"
    if args.out:
        io.open(args.out, "w", encoding="utf-8", newline="\n").write(text)
        print("已写入 %s" % args.out)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""找出「受约束容器中的翻译文本膨胀」候选（判据 I4）。

用途：固定宽度 / `white-space: nowrap` / 单行截断的元素，配上非英文翻译会溢出或截断。
同一布局问题**只在部分语言下显形**——实测 `ja` / `zh-CN` 各仅 2 个候选，
而 `de` 85 个 / `fr` 89 个（`Sync` -> `Synchronisierung`、`Skip` -> `Überspringen`）。

降噪的关键是**按英文长度分档**，而不是只看比值：

- 英文 <= --short-len（默认 12）：多为按钮 / 页签 / 菜单项 / 列名，处在受约束容器里 -> 候选
- 英文更长：多为设置项说明与提示文案，**可换行**，膨胀无害 -> 单列，默认不计入主清单

用法：
    python scan_i18n_text_expansion.py --langs app/appearance/langs --base en.json
    python scan_i18n_text_expansion.py --langs app/appearance/langs --lang de.json --min-ratio 2.5

**产出是候选不是结论**：脚本只算长度比，它**不知道谁在使用这个键**。
每一条都必须回读该键的使用点（模板 / 菜单 / 对话框）确认容器是否真的受约束——
`en.json` 里的键名（`xxxTip` / `xxxDesc`）可作为线索，但不能代替回读。

输出为纯 ASCII 表头 + UTF-8 正文。语言目录不存在时以退出码 2 报错——
零发现与没扫到在输出上无法区分，静默输出「0 个」会让使用者以为没有问题。
"""

import argparse
import io
import json
import os
import re
import sys

# 语言后缀（新增语言时在此登记，否则会被当成基准以外的未知文件）
LANG_SUFFIXES = ("zh-CN", "zh-TW", "ja", "tr", "ar", "fr", "de", "es", "ko", "ru")

# 键名线索：这些更可能出现在受约束容器里（按钮 / 页签 / 菜单项 / 列名）
CONSTRAINED_HINT = (
    "title", "label", "name", "tab", "menu", "button", "btn",
    "toolbar", "dock", "icon", "chip", "tag", "status",
)
# 键名线索：这些基本可换行，膨胀无害
FREE_HINT = ("tip", "desc", "help", "placeholder", "message", "confirm", "warn")

# 受约束容器的源码信号（需要 --source）。这些容器**不换行**，配长译必然溢出/截断。
# 经实测验证：`historySync`（en="sync"）用在 `<option>` 里，而 de/ar 译作
# `synchronisieren (sync)` / `مزامنة (sync)`，在下拉框里会溢出。
CONSTRAINED_SIGNALS = (
    ("<option", "select 下拉项不换行"),
    ("nowrap", "CSS nowrap"),
    ("ellipsis", "单行省略号截断"),
    ("text-ellipsis", "单行省略号截断"),
)

# 从 SCSS 反推「受约束类名」——**这是原版的盲区**：
# 真实约束写在样式文件里（实测 SiYuan 的 `app/src/assets/scss/`：
# `white-space: nowrap` 70 处、`text-overflow: ellipsis` 39 处、固定宽度 340 处），
# 而原版只在 TS 的同一行找这些关键字，于是**系统性低估候选**。
# 正确做法：先从样式里提取「哪个类被约束成不换行」，再在 TS 的使用点按类名匹配。
SCSS_IGNORE_DIRS = {"node_modules", "dist", "build", "stage", ".git"}
CLASS_RULE = re.compile(r"\.([A-Za-z_][\w-]*)")
CONSTRAIN_DECL = re.compile(
    r"white-space\s*:\s*nowrap|text-overflow\s*:\s*ellipsis|"
    r"(?<!max-)(?<!min-)width\s*:\s*\d+(?:\.\d+)?(?:px|rem|em)\b|"
    r"overflow\s*:\s*hidden")
OVERFLOW_FREE = re.compile(r"white-space\s*:\s*(?:normal|pre-wrap|break-spaces)")


def scan_styles(styles_roots):
    """从 SCSS/CSS 提取「被约束成不换行或宽度固定」的类名集合。"""
    constrained = set()
    for root in styles_roots:
        if not os.path.isdir(root):
            continue
        for dir_path, dir_names, file_names in os.walk(root):
            dir_names[:] = [d for d in dir_names
                            if d not in SCSS_IGNORE_DIRS and not d.startswith(".")]
            for name in file_names:
                if not name.endswith((".scss", ".css")):
                    continue
                path = os.path.join(dir_path, name)
                text = io.open(path, encoding="utf-8", errors="replace").read()
                # 以 `{` 分块，粗粒度地把声明与选择器配对
                chunks = re.split(r"([^{}]*)\{", text)
                for i in range(1, len(chunks), 2):
                    sel = chunks[i].split("\n")[-1] if chunks[i] else ""
                    body = chunks[i + 1] if i + 1 < len(chunks) else ""
                    if not CONSTRAIN_DECL.search(body):
                        continue
                    if OVERFLOW_FREE.search(body):
                        continue
                    for cls in CLASS_RULE.findall(sel):
                        constrained.add(cls)
    return constrained
# 显式像素/rem 宽度（同行的 style 或 CSS 声明）
EXPLICIT_WIDTH = re.compile(r"(?:width|min-width|max-width)\s*:\s*\d+(?:\.\d+)?(?:px|rem|em)")
# i18n 取值：`languages.xxx` 或 `languages["xxx"]`
I18N_REF = re.compile(
    r"languages\.([A-Za-z0-9_$]+)|languages\[\s*[\"']([A-Za-z0-9_$]+)[\"']\s*\]")


def iter_sources(roots):
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dir_path, dir_names, file_names in os.walk(root):
            dir_names[:] = [d for d in dir_names
                            if d not in {"node_modules", "dist", "build", "stage", ".git"}
                            and not d.startswith(".")]
            for name in file_names:
                if name.endswith((".ts", ".tsx", ".js", ".html")):
                    yield os.path.join(dir_path, name)


def scan_usage(roots, constrained_classes=None):
    """返回 key -> [(相对路径, 行号, 约束说明或 None, 行内容)]。

    `constrained_classes` 来自 `--styles`：TS 行里含这些类名即视为受约束容器。
    不做这道关联就只能看到内联样式，而真实约束在样式文件里。
    """
    constrained_classes = constrained_classes or set()
    usage = {}
    for path in iter_sources(roots):
        try:
            lines = io.open(path, encoding="utf-8", errors="replace").read().split("\n")
        except OSError:
            continue
        for no, line in enumerate(lines, 1):
            for m in I18N_REF.finditer(line):
                key = m.group(1) or m.group(2)
                reason = None
                for signal, why in CONSTRAINED_SIGNALS:
                    if signal in line:
                        reason = why
                        break
                if reason is None and EXPLICIT_WIDTH.search(line):
                    reason = "同行声明了固定宽度"
                if reason is None and constrained_classes:
                    for cls in CLASS_RULE.findall(line):
                        if cls in constrained_classes:
                            reason = "类 `%s` 在样式中被约束" % cls
                            break
                usage.setdefault(key, []).append((path, no, reason, line.strip()[:120]))
    return usage


def flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.update(flatten(value, prefix + key + "."))
    else:
        out[prefix[:-1]] = obj
    return out


def load(path):
    return flatten(json.load(io.open(path, encoding="utf-8")))


def hint_of(key):
    leaf = key.rsplit(".", 1)[-1].lower()
    if any(h in leaf for h in FREE_HINT):
        return "free"
    if any(h in leaf for h in CONSTRAINED_HINT):
        return "constrained"
    return "unknown"


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--langs", default="app/appearance/langs",
                        help="语言文件目录（默认 app/appearance/langs）")
    parser.add_argument("--base", default="en.json", help="基准语言（默认 en.json）")
    parser.add_argument("--lang", action="append", default=None,
                        help="要比对的语言文件，可重复；缺省比对全部已登记后缀")
    parser.add_argument("--short-len", type=int, default=12,
                        help="英文不超过该长度视为「受约束容器候选」（默认 12）")
    parser.add_argument("--min-ratio", type=float, default=2.0,
                        help="长度比阈值（默认 2.0）")
    parser.add_argument("--min-base-len", type=int, default=4,
                        help="英文短于该长度不参与比对（默认 4，过短的值噪声大）")
    parser.add_argument("--max-list", type=int, default=25,
                        help="每种语言最多列出多少条候选（默认 25）")
    parser.add_argument("--out", default=None, help="输出文件；缺省写 stdout")
    parser.add_argument("--source", action="append", default=None,
                        help="源码根目录（如 app/src），用于交叉核对使用点是否受约束；"
                             "**强烈建议提供**——不给则无法区分「受约束」与「可换行」")
    parser.add_argument("--styles", action="append", default=None,
                        help="样式根目录（如 app/src/assets/scss）。**建议提供**："
                             "约束常写在样式文件里（nowrap/ellipsis/固定宽度），"
                             "只给 --source 会系统性低估候选")
    args = parser.parse_args()

    if not os.path.isdir(args.langs):
        sys.stderr.write(
            "no such directory: %s\n"
            "零发现与没扫到目录在输出上无法区分，故以退出码 2 报错而不是输出 0 个。\n"
            % args.langs)
        return 2

    base_path = os.path.join(args.langs, args.base)
    if not os.path.isfile(base_path):
        sys.stderr.write("no such file: %s\n" % base_path)
        return 2
    base = load(base_path)
    if not base:
        sys.stderr.write("no strings: %s 中未提取到任何字符串\n" % base_path)
        return 2

    if args.lang:
        targets = [(os.path.splitext(n)[0], os.path.join(args.langs, n))
                   for n in args.lang]
    else:
        targets = []
        for name in sorted(os.listdir(args.langs)):
            if not name.endswith(".json") or name == args.base:
                continue
            stem = name[:-5]
            if stem in LANG_SUFFIXES:
                targets.append((stem, os.path.join(args.langs, name)))

    usage = None
    if args.source:
        missing_src = [r for r in args.source + (args.styles or [])
                       if not os.path.isdir(r)]
        if missing_src:
            sys.stderr.write("no such directory: %s\n" % ", ".join(missing_src))
            return 2
        constrained = scan_styles(args.styles) if args.styles else set()
        usage = scan_usage(args.source, constrained)

    out = []
    out.append("i18n 文本膨胀候选（判据 I4：受约束容器）")
    out.append("=" * 72)
    out.append("语言目录      : %s" % args.langs)
    out.append("基准          : %s（%d 个键）" % (args.base, len(base)))
    out.append("源码交叉核对  : %s" % (", ".join(args.source) if args.source
                                        else "未提供（不区分受约束与可换行）"))
    out.append("样式交叉核对  : %s" % (", ".join(args.styles) if args.styles
                                        else "未提供（会漏掉写在样式里的约束）"))
    if args.styles:
        out.append("                （从 %s 提取到 %d 个受约束类名）"
                   % (os.path.basename(args.styles[0]), len(constrained)))
    out.append("候选判据      : 英文长度 %d-%d 且长度比 >= %.1f"
               % (args.min_base_len, args.short_len, args.min_ratio))
    out.append("")
    out.append("【本输出是候选，不是结论】长度比只说明「该语言更长」，"
               "不说明「容器装不下」。")
    if usage is not None:
        out.append("已用源码交叉核对，主清单只保留**使用点确实受约束**的键。")
    else:
        out.append("未给 --source，无法区分「受约束」与「可换行」——"
                   "请自行回读使用点后再报告。")
    out.append("")

    total_confirmed = 0
    for stem, path in targets:
        if not os.path.isfile(path):
            out.append("-" * 72)
            out.append("%s：文件不存在，跳过" % stem)
            continue
        other = load(path)

        constrained, loose, free = [], [], []
        for key, evalue in base.items():
            ovalue = other.get(key)
            if not isinstance(evalue, str) or not isinstance(ovalue, str):
                continue
            if len(evalue) < args.min_base_len or len(ovalue) <= len(evalue):
                continue
            ratio = len(ovalue) / len(evalue)
            if ratio < args.min_ratio:
                continue
            row = (ratio, len(evalue), len(ovalue), key, evalue, ovalue)
            hint = hint_of(key)
            if hint == "free" or len(evalue) > args.short_len:
                (free if hint == "free" else loose).append(row)
            else:
                constrained.append(row)

        # 有源码信息时，再按「使用点是否受约束」过一道，主清单只留真候选
        confirmed = []
        if usage is not None:
            for row in constrained:
                hits = usage.get(row[3]) or []
                reasons = [(p, n, r, s) for p, n, r, s in hits if r]
                if reasons:
                    confirmed.append(row + (reasons,))
            constrained_main = confirmed
        else:
            constrained_main = constrained

        constrained.sort(reverse=True)
        loose.sort(reverse=True)
        confirmed.sort(reverse=True)
        total_confirmed += len(constrained_main)

        out.append("-" * 72)
        if usage is not None:
            out.append("%s：受约束且**使用点确认受约束** %d 个（长度候选 %d 个，"
                       "其中 %d 个使用点未见约束）"
                       % (stem, len(confirmed), len(constrained),
                          len(constrained) - len(confirmed)))
        else:
            out.append("%s：受约束候选 %d 个 / 长文案 %d 个 / 明确可换行 %d 个"
                       % (stem, len(constrained), len(loose), len(free)))
        out.append("-" * 72)
        if not constrained_main:
            out.append("  （无）")
        for row in constrained_main[:args.max_list]:
            ratio, le, lo, key, evalue, ovalue = row[:6]
            out.append("  %.1fx  %2d->%-3d  %s" % (ratio, le, lo, key))
            out.append("        base: %s" % evalue.replace("\n", " ")[:70])
            out.append("        %-4s: %s" % (stem[:4], ovalue.replace("\n", " ")[:70]))
            if len(row) > 6:
                for p, n, r, s in row[6][:2]:
                    rel = os.path.relpath(p).replace("\\", "/")
                    out.append("        使用点 %s:%d（%s）" % (rel, n, r))
                    out.append("            %s" % s)
        if len(constrained_main) > args.max_list:
            out.append("  ...另有 %d 个" % (len(constrained_main) - args.max_list))
        if loose:
            out.append("")
            out.append("  长文案（英文 >%d 字符，多半可换行，仅供核对）：%d 个"
                       % (args.short_len, len(loose)))
            for ratio, le, lo, key, _, _ in loose[:5]:
                out.append("    %.1fx  %2d->%-3d  %s" % (ratio, le, lo, key))
        out.append("")

    out.append("=" * 72)
    if usage is not None:
        out.append("使用点已确认受约束的候选合计：%d 个（%d 种语言）"
                   % (total_confirmed, len(targets)))
    else:
        out.append("受约束候选合计：%d 个（%d 种语言）" % (total_confirmed, len(targets)))
    out.append("")
    out.append("下一步：")
    out.append("  1. 逐条看上面的「使用点」行，确认容器真的不能容纳该语言的长度")
    out.append("  2. 长度比与使用点都成立才是可报告的发现")
    out.append("  3. 报告的「业务表现」要写出**语言 + 操作路径 + 实际看到什么**，例如")
    out.append("     「切到德语后，历史面板的操作下拉框显示 `synchronisieren (sync)` 被截断」")
    out.append("  4. 修法优先「容纳」而非「改译文」：放宽宽度 / 允许换行 / 缩短该语言的文案"
               "（三者付出不同，报告里要说清选了哪个）")

    text = "\n".join(out) + "\n"
    if args.out:
        io.open(args.out, "w", encoding="utf-8", newline="\n").write(text)
        print("已写入 %s" % args.out)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

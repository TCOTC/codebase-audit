#!/usr/bin/env python3
"""比对同一文档的多语言版本：结构指纹与语言无关内容。

用途：`docs/` 下有 10 组多语言文档（`X.md` + `X.<lang>.md`，`API` 有三语）。
`AGENTS.md` 明确要求这些文档保持对齐，但**它们多为手写、各自独立维护**——
实测 `kernel/apicontract/cmd/apigen` 只生成 `app/src/types/api/index.d.ts`、
`kernel/apicontract/schema.json` 与 petal 的 `index.d.ts`，**不生成 `docs/API*.md`**。
因此版本间漂移不会被任何生成步骤发现。本脚本补上这个机械检查。

两类比对（互补，单看一类会漏）：

1. **结构指纹**——各级 Markdown 标题（`#`…`######`）的数量。
   标题文本是翻译过的，不能直接比字符串；数量差异能抓出「某版本少一节」。
2. **语言无关内容**——反引号里的标识符（`/api/...`、文件路径、配置键、函数名）。
   这些**不该被翻译**，所以可以直接取差集，精确定位「哪一版少了哪个端点/参数」。

实测基线（SiYuan，`API.md` / `API.zh-CN.md` / `API.ja.md`）：
端点集合三语一致（各 79 个），但 `API.ja.md` 的 `###` 标题比另两版少 1 个——
少的是**说明性章节**（`TypeScript contracts`），不是端点。
**这说明两类比对缺一不可**：只看端点会判为「一致」，只看标题数量则无法定位缺的是什么。

用法：
    python scan_doc_parity.py --docs docs
    python scan_doc_parity.py --docs docs --pair API     # 只看某一组

输出为纯 ASCII。目录不存在时以退出码 2 报错——**零发现与没扫到目录在输出上
无法区分**，静默输出「0 组」会让使用者以为全部对齐。
"""

import argparse
import os
import re
import sys
from collections import defaultdict

# 语言后缀（新增语言时在此登记，否则该版本会被当成主版本）
LANG_SUFFIXES = ("zh-CN", "zh-TW", "ja", "tr", "ar", "fr", "de", "es", "ko", "ru")

HEADING = re.compile(r"^(#{1,6})\s+\S")
FENCE = re.compile(r"^\s*(```|~~~)")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
# 反引号内的行内代码（单反引号，不跨行；排除围栏）
INLINE_CODE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")

# 只保「像标识符」的内容：含路径分隔符、点号、下划线，或全大写/驼峰
IDENT_SHAPE = re.compile(r"[/_.\-#]|[a-z][A-Z]")
# 含 CJK 的反引号内容 = 被翻译过的自然语言或本地化示例，**不是**语言无关标识符
CJK = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u4e00-\u9fff\uff00-\uffef]")
# JSON 示例结构（内含被本地化的示例值）
JSONISH = re.compile(r"[{}\[\]]|\":")
# 语言/工具无关的通用值，出现次数差异无意义
NOISE = {
    "true", "false", "null", "none", "json", "yaml", "yml", "toml", "utf-8",
    "get", "post", "put", "delete", "patch", "head", "options",
    "string", "number", "boolean", "object", "array", "int", "float", "bool",
    "http", "https", "localhost", "127.0.0.1", "content-type", "user-agent",
    "id", "type", "value", "name", "key", "data", "code", "msg", "error",
}


def discover_pairs(docs_dir):
    """返回 [(base, {lang: path})]，base 是不含语言后缀的基名。"""
    entries = [n for n in os.listdir(docs_dir)
               if n.endswith(".md") and os.path.isfile(os.path.join(docs_dir, n))]
    groups = defaultdict(dict)
    for name in entries:
        stem = name[:-3]                       # 去掉 .md
        lang = None
        base = stem
        for suffix in LANG_SUFFIXES:
            if stem.endswith("." + suffix):
                base, lang = stem[: -(len(suffix) + 1)], suffix
                break
        groups[base][lang or ""] = os.path.join(docs_dir, name)
    # 只保留真有多个语言版本的组
    return sorted((b, v) for b, v in groups.items() if len(v) > 1)


def read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def fingerprint(text):
    """结构指纹：各级标题数、围栏块数、表格行数。"""
    headings = [0] * 6
    fences = 0
    table_rows = 0
    in_fence = False
    for line in text.split("\n"):
        if FENCE.match(line):
            fences += 1
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING.match(line)
        if m:
            headings[len(m.group(1)) - 1] += 1
            continue
        if TABLE_ROW.match(line):
            table_rows += 1
    return {"headings": headings, "fences": fences // 2, "table_rows": table_rows}


def identifiers(text):
    """反引号里的**语言无关标识符**集合。

    过滤掉三类：含 CJK（被翻译过的）、JSON 示例结构（内含本地化示例值）、
    含空格的多词内容（可能是自然语言短语，降级另计）。
    实测：不加这三条时，`API.ja.md` 会因「示例值被译成 1行目」而报出 12 条假差异。
    """
    strict, loose = set(), set()
    in_fence = False
    for line in text.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        for m in INLINE_CODE.finditer(line):
            value = m.group(1).strip()
            if not value or len(value) > 80:
                continue
            if value.lower() in NOISE:
                continue
            if not IDENT_SHAPE.search(value):
                continue
            if CJK.search(value) or JSONISH.search(value):
                # 语言无关内容不该含 CJK，也不该是含本地化示例值的 JSON
                continue
            (loose if " " in value else strict).add(value)
    return strict, loose


def cancel_localized_xrefs(missing, extra, lang):
    """抵消「交叉引用被本地化」造成的假差异。

    中文版把 `[格式规范](./SY-FORMAT.md)` 写成 `SY-FORMAT.zh-CN.md` 是**正确行为**，
    不是漂移。实测不加此规则时，SY-FORMAT / TAB-BLOCK / WORKSPACE 三组会各报 1 条假差异。
    入参是已排序的 list，返回值同型（调用方直接拿去遍历/计数）。
    """
    if not lang:
        return missing, extra
    consumed_m, consumed_x = set(), set()
    for m in missing:
        if not m.endswith(".md"):
            continue
        counterpart = "%s.%s.md" % (m[:-3], lang)
        if counterpart in extra:
            consumed_m.add(m)
            consumed_x.add(counterpart)
    # 入参可能是 list（已排序）或 set，故统一按集合运算后再恢复为 list
    return ([m for m in missing if m not in consumed_m],
            [x for x in extra if x not in consumed_x])


def fmt_heading_delta(fp_a, fp_b):
    out = []
    for level in range(6):
        a, b = fp_a["headings"][level], fp_b["headings"][level]
        if a != b:
            out.append("h%d %d->%d" % (level + 1, a, b))
    for key in ("fences", "table_rows"):
        if fp_a[key] != fp_b[key]:
            out.append("%s %d->%d" % (key, fp_a[key], fp_b[key]))
    return out


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--docs", default="docs", help="文档目录（默认 docs）")
    parser.add_argument("--pair", default=None,
                        help="只看基名匹配该值的组（如 API）；缺省看全部")
    parser.add_argument("--max-list", type=int, default=20,
                        help="每组最多列出多少条差异项（默认 20）")
    args = parser.parse_args()

    if not os.path.isdir(args.docs):
        # 首行用 ASCII 标记：与其它扫描脚本共用同一个可 grep 的契约。
        sys.stderr.write(
            "no such directory: %s\n"
            "零发现与没扫到目录在输出上无法区分，故以退出码 2 报错而不是输出 0 组。\n"
            % args.docs)
        return 2

    pairs = discover_pairs(args.docs)
    if args.pair:
        pairs = [(b, v) for b, v in pairs if b == args.pair]
    if not pairs:
        sys.stderr.write(
            "no doc pairs: 在 %s 下未找到多语言文档组%s。\n"
            "若是新增了语言，请把语言后缀登记到脚本的 LANG_SUFFIXES。\n"
            % (args.docs, ("（--pair %s）" % args.pair) if args.pair else ""))
        return 2

    out = []
    out.append("多语言文档一致性")
    out.append("=" * 66)
    out.append("文档目录 : %s" % args.docs)
    out.append("文档组   : %d" % len(pairs))
    out.append("")
    out.append("说明：标题文本是翻译过的，故只比**数量**（结构指纹）；")
    out.append("反引号内的标识符不该被翻译，故可直接取差集。")
    out.append("两类都要看——只看标识符会漏掉说明性章节，只看数量则无法定位缺什么。")
    out.append("")

    dirty = 0
    for base, versions in pairs:
        langs = sorted(k for k in versions if k)
        if not langs:
            continue
        # 主版本：无语言后缀的那份；没有就用第一个语言版当基准
        ref_lang = "" if "" in versions else langs[0]
        ref_text = read(versions[ref_lang])
        ref_fp = fingerprint(ref_text)
        ref_ids, ref_loose = identifiers(ref_text)

        out.append("-" * 66)
        out.append("%s  （基准 %s）" % (base, os.path.basename(versions[ref_lang])))
        out.append("-" * 66)
        out.append("  版本        h1-h6 标题数                          IDs")
        for lang in [ref_lang] + [l for l in langs if l != ref_lang]:
            text = read(versions[lang])
            fp = fingerprint(text)
            ids, _ = identifiers(text)
            out.append("  %-10s  %-36s %4d"
                       % (lang or "(base)",
                          " ".join("%d" % n for n in fp["headings"]), len(ids)))

        group_dirty = False
        for lang in langs:
            text = read(versions[lang])
            fp = fingerprint(text)
            ids, loose = identifiers(text)

            struct = fmt_heading_delta(fp, ref_fp)
            if struct:
                group_dirty = True
                out.append("")
                out.append("  [结构][%s] %s" % (lang, "; ".join(struct)))
                out.append("    （数量差异可能是「少一节」或「合并/拆分」，需回读定位）")

            missing = sorted(ref_ids - ids)
            extra = sorted(ids - ref_ids)
            missing, extra = cancel_localized_xrefs(missing, extra, lang)
            if missing:
                group_dirty = True
                out.append("")
                out.append("  [标识符][%s] 基准有而本版无（%d 个）——高置信：这些不该被翻译"
                           % (lang, len(missing)))
                for value in missing[:args.max_list]:
                    out.append("    - %s" % value)
                if len(missing) > args.max_list:
                    out.append("    ...另有 %d 个" % (len(missing) - args.max_list))
            if extra:
                group_dirty = True
                out.append("")
                out.append("  [标识符][%s] 本版有而基准无（%d 个）" % (lang, len(extra)))
                for value in extra[:args.max_list]:
                    out.append("    + %s" % value)
                if len(extra) > args.max_list:
                    out.append("    ...另有 %d 个" % (len(extra) - args.max_list))

            # 含空格的内容可能是命令，也可能是被翻译的自然语言——低置信，单列
            loose_missing = sorted(ref_loose - loose)
            loose_extra = sorted(loose - ref_loose)
            loose_missing, loose_extra = cancel_localized_xrefs(
                loose_missing, loose_extra, lang)
            if loose_missing or loose_extra:
                out.append("")
                out.append("  [低置信][%s] 含空格的差异 %d 个——多为自然语言短语，"
                           "**需人读**判断是命令还是被翻译的句子"
                           % (lang, len(loose_missing) + len(loose_extra)))
                for value in loose_missing[:6]:
                    out.append("    - %s" % value)
                for value in loose_extra[:6]:
                    out.append("    + %s" % value)

        if not group_dirty:
            out.append("")
            out.append("  一致")
        else:
            dirty += 1
        out.append("")

    out.append("=" * 66)
    out.append("有差异的文档组：%d / %d" % (dirty, len(pairs)))
    out.append("")
    out.append("注意：本输出是【候选】。差异可能是**有意省略**（如某语言尚未翻译某节），")
    out.append("也可能是有维护义务的漂移——必须回读该节与 `AGENTS.md` 的对齐要求再定性。")

    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

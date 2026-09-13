#!/usr/bin/env python3
"""把历轮发现的 `file:line` 建成索引，并对照一次改动报出「回归风险位置」。

用途：修复验证时回答两个问题——
1. 这次改动是否碰到了**历轮已报告过的位置**（改了又犯，或修复不到位）；
2. 某个文件历史上被报过什么（决定要不要一次看全）。

数据来源是 [实证数据](../references/evidence.md) 里的 `file:line` 与 issue 编号——
这些数据**本来就存在**，此前只能靠人眼在千行文档里翻，所以本脚本不引入新数据源。

用法：
    # A. 只看索引概览
    python scan_regression_index.py --index-only

    # B. 对照一次改动（文件列表从 stdin 读，兼容 git diff --name-only）
    git diff --name-only | python scan_regression_index.py

    # C. 直接给文件
    python scan_regression_index.py --file kernel/model/sync.go --file app/src/layout/Wnd.ts

    # D. 自己跑 git
    python scan_regression_index.py --git d:/CodeProjects/siyuan --rev HEAD~1

输出为纯 ASCII。证据库不存在时以退出码 2 报错——**空索引与「没有历史发现」在输出上
无法区分**，静默输出「0 条命中」会让使用者以为这个文件历史上很干净。
"""

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
DEFAULT_EVIDENCE = os.path.join(SKILL_DIR, "references", "evidence.md")

# file:line —— 路径限定在这些顶层目录下，避免把散文里的 `foo.go:1` 当成引用
PATH_LINE = re.compile(
    r"\b((?:kernel|app/src|app/electron|app/tests|scripts|docs)/"
    r"[\w./\-]+\.(?:go|ts|tsx|js|mjs|py|json|md|yml|yaml)):(\d+)\b")
ISSUE = re.compile(r"#(19\d{3})")
ROUND = re.compile(r"^(#{2,3})\s*第([一二三四五六七八九十]+|\d+)轮")
CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}


def round_no(text):
    if text.isdigit():
        return int(text)
    if text == "十":
        return 10
    if text.startswith("十"):
        return 10 + CN_DIGITS.get(text[1:], 0)
    if "十" in text:
        head, _, tail = text.partition("十")
        return CN_DIGITS.get(head, 0) * 10 + (CN_DIGITS.get(tail, 0) if tail else 0)
    return CN_DIGITS.get(text, 0)


def norm(path):
    return path.replace("\\", "/").lstrip("./")


def parse_evidence(path):
    """返回 (file -> [entry])，entry = {round, issue, line, text}。"""
    index = defaultdict(list)
    current_round = None
    last_issue = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            m_round = ROUND.match(line)
            if m_round:
                current_round = round_no(m_round.group(2))
                continue
            m_issue = ISSUE.search(line)
            if m_issue:
                last_issue = m_issue.group(1)
            for m in PATH_LINE.finditer(line):
                file_path, line_no = norm(m.group(1)), int(m.group(2))
                # 同一行可能有多个引用，issue 取本行或最近一次出现的
                index[file_path].append({
                    "round": current_round,
                    "issue": m_issue.group(1) if m_issue else last_issue,
                    "line": line_no,
                    "text": line.strip()[:150],
                })
    return index


def git_changed(repo, rev):
    try:
        proc = subprocess.run(
            ["git", "-C", repo, "diff", "--name-only", rev],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        sys.stderr.write("错误：无法执行 git：%s\n" % exc)
        return None
    if proc.returncode != 0:
        sys.stderr.write("错误：git diff 失败：%s\n"
                         % proc.stderr.decode("utf-8", "replace").strip())
        return None
    return [norm(p) for p in proc.stdout.decode("utf-8", "replace").split() if p.strip()]


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence", default=DEFAULT_EVIDENCE,
                        help="证据库路径（默认本 skill 的 references/evidence.md）")
    parser.add_argument("--file", action="append", default=None,
                        help="要对照的文件，可重复；缺省时从 stdin 读")
    parser.add_argument("--git", dest="repo", default=None,
                        help="仓库路径；给了就用 git diff 取变更文件")
    parser.add_argument("--rev", default="HEAD~1",
                        help="配合 --git 的 revision（默认 HEAD~1）")
    parser.add_argument("--index-only", action="store_true", help="只打印索引概览")
    parser.add_argument("--min-round", type=int, default=0,
                        help="只列出 >= 该轮次的条目（默认 0，全部）")
    args = parser.parse_args()

    if not os.path.isfile(args.evidence):
        # 首行 ASCII 标记：与三个扫描脚本共用同一个可 grep 的契约。
        sys.stderr.write(
            "no such file: %s\n"
            "空索引与「没有历史发现」在输出上无法区分，故以退出码 2 报错。\n"
            % args.evidence)
        return 2

    index = parse_evidence(args.evidence)
    if args.min_round:
        for key in list(index):
            index[key] = [e for e in index[key]
                          if (e["round"] or 0) >= args.min_round]
            if not index[key]:
                del index[key]

    out = []
    out.append("历轮发现回归索引")
    out.append("=" * 64)
    out.append("证据库        : %s" % args.evidence)
    out.append("登记的文件    : %d 个" % len(index))
    out.append("登记的引用点  : %d 处"
               % sum(len(v) for v in index.values()))
    rounds = sorted({e["round"] for v in index.values() for e in v if e["round"]})
    out.append("覆盖轮次      : %s" % (
        "第 %d–%d 轮" % (rounds[0], rounds[-1]) if rounds else "（未识别到轮次标题）"))
    out.append("")
    out.append("注意：行号是**当时**的位置，后续提交会让它偏移。命中按文件级判定，")
    out.append("行号只作定位线索；判定「是否同一处」必须回读当前源码。")
    out.append("")

    repeated = sorted(((len(set(e["line"] for e in v)), f, v)
                       for f, v in index.items()), reverse=True)

    if args.index_only:
        out.append("-" * 64)
        out.append("索引全览（文件 / 引用点数 / 首末轮次）")
        out.append("-" * 64)
        for count, file_path, entries in repeated:
            rs = [e["round"] for e in entries if e["round"]]
            span = "第 %d–%d 轮" % (min(rs), max(rs)) if rs else "-"
            out.append("  %-56s %2d 处  %s" % (file_path, count, span))
        text = "\n".join(out) + "\n"
        sys.stdout.write(text)
        return 0

    if args.repo:
        changed = git_changed(args.repo, args.rev)
        if changed is None:
            return 2
    elif args.file:
        changed = [norm(f) for f in args.file]
    else:
        # 交互式终端下**不裸读** stdin：read() 会永久阻塞等输入，看上去像卡死。
        # 不在这里单独报错——否则会与下面的「空输入」守卫重叠，
        # 两条路径给出同一个后果却无法分别验证（实测：改坏下面那条，上面那条仍会兜住）。
        changed = ([] if sys.stdin.isatty()
                   else [norm(l) for l in sys.stdin.read().split() if l.strip()])

    if not changed:
        sys.stderr.write(
            "no changed files: 没有拿到任何变更文件。\n"
            "用 --file / --git / stdin 之一提供；空输入会让「没检查」被当成「没风险」。\n"
            "例：git diff --name-only | python %s\n" % os.path.basename(__file__))
        return 2

    by_suffix = {}
    for file_path, entries in index.items():
        by_suffix.setdefault(os.path.basename(file_path), []).append((file_path, entries))

    hits, clean = [], []
    for target in changed:
        entries = index.get(target)
        matched_path = target
        if entries is None:      # 路径前缀不同（相对/绝对）时按「同目录同名」兜底
            for cand_path, cand_entries in by_suffix.get(os.path.basename(target), []):
                if os.path.dirname(cand_path).endswith(os.path.dirname(target)):
                    entries, matched_path = cand_entries, cand_path
                    break
        (hits if entries else clean).append((target, matched_path, entries or []))

    out.append("-" * 64)
    out.append("命中：变更文件中有历轮发现记录（%d 个文件）" % len(hits))
    out.append("-" * 64)
    if hits:
        for target, matched_path, entries in hits:
            rounds_here = sorted({e["round"] for e in entries if e["round"]})
            issues = sorted({e["issue"] for e in entries if e["issue"]})
            out.append("")
            out.append("  %s" % target)
            if matched_path != target:
                out.append("    （登记为 %s）" % matched_path)
            out.append("    轮次: %s    issue: %s    引用点: %d"
                       % (", ".join("第 %d 轮" % r for r in rounds_here) or "-",
                          ", ".join("#" + i for i in issues) or "-",
                          len(set(e["line"] for e in entries))))
            for e in entries[:6]:
                tag = "第 %s 轮" % e["round"] if e["round"] else "轮次未知"
                out.append("      L%-6d %-10s %s" % (e["line"], tag, e["text"][:96]))
            if len(entries) > 6:
                out.append("      ...另有 %d 处，用 --index-only 看全" % (len(entries) - 6))
    else:
        out.append("  （无）")
    out.append("")

    out.append("-" * 64)
    out.append("无历史记录的变更文件：%d 个（不代表无风险，只说明此前未报过）"
               % len(clean))
    out.append("-" * 64)
    for target, _, _ in clean:
        out.append("  %s" % target)
    out.append("")

    out.append("-" * 64)
    out.append("高复发文件（历轮累计引用点最多的 10 个）")
    out.append("-" * 64)
    for count, file_path, entries in repeated[:10]:
        flag = "  <-- 本次变更也命中" if any(t == file_path for t, _, _ in hits) else ""
        out.append("  %-56s %2d 处%s" % (file_path, count, flag))

    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

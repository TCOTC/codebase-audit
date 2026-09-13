#!/usr/bin/env python3
"""本 skill 自身文档结构的机械检查。

用法：
    python scripts/skill_self_check.py

检查的是**实际踩过的坑**，不是通用的 Markdown lint：

1. `已知误报` 与 `更新记录` 两张表必须连续（表内不得有空行）。
   实测：追加条目时在末尾留了空行，表被切成两张，末行渲染成**没有表头的表**；
   之后那条 MIME 记录就在表外，按「查表」去重的人根本看不到它。
   两张表已移出 `SKILL.md`（见 `contributing.md` 第 10 条），检查点随之迁到
   `references/known-false-positives.md` 与 `references/changelog.md`。
2. 各 Markdown 文件里的 `##` 标题不得重复。
   实测：同一条结论曾以两行并列形式存在（一行说「已列入已知误报」、下一行说「已改判为真缺陷」），
   两行各自看似成立，按「先读登记表」去重时会采用错的那一半。
3. `evidence.md` 的轮次章节必须按轮次号递增，且**不得嵌在另一个轮次之下**
   （第 1–11 轮嵌在「历轮已确认的发现」下是有意设计，属例外）。
   实测：第十八轮一度写成 `###` 并嵌在「第十六轮（B 线）」之下——按 `##` 扫章节会整轮漏掉。
4. 表格单元格内不得出现未转义的 `|`（如代码里的 `||`）。
   实测：`已知误报` 表的原因列写了 `this.mobile || …`，该行因此在 Markdown 里被拆成 4 列，整张表渲染错位。
5. SKILL.md 里引用的本地文件（`](./...)`）必须存在。
6. `references/` 下的 Markdown 必须被 SKILL.md 引用。孤儿文件按判据 A 是「无人消费的定义」，
   实际后果是本轮写的方法论下一轮没人会读到。
7. SKILL.md 的判据字母（`### X. `）不得重复。
8. `patterns.md` 的 P 编号不得重复且必须递增。
   实测：并行会话曾撞号，重复编号会让「按编号查既有结论」这一步给出错误答案。

退出码 0 表示全部通过。仅依赖标准库。
"""

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
EVIDENCE = os.path.join(SKILL_DIR, "references", "evidence.md")

FAILURES = []


def _round_no(title):
    """把轮次标题里的中文数字转成整数，用于顺序检查。"""
    m = re.search(r"第([一二三四五六七八九十]+)轮", title)
    if not m:
        m2 = re.search(r"第(\d+)轮", title)
        return int(m2.group(1)) if m2 else 0
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
    text = m.group(1)
    if text == "十":
        return 10
    if text.startswith("十"):
        return 10 + digits.get(text[1:], 0)
    if "十" in text:
        head, _, tail = text.partition("十")
        return digits.get(head, 0) * 10 + (digits.get(tail, 0) if tail else 0)
    return digits.get(text, 0)


def check(condition, label, detail=""):
    if condition:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s%s" % (label, ("  -- " + detail) if detail else ""))
        FAILURES.append(label)


def read(path):
    return io.open(path, encoding="utf-8").read().split("\n")


print("[1] 表格必须连续（表内不得有空行）")
# 两张长表已移出 SKILL.md，检查点随之迁移（见 contributing.md 第 10 条）
TABLES = [
    (os.path.join(SKILL_DIR, "references", "known-false-positives.md"),
     "## 已知误报（不要报告）"),
    (os.path.join(SKILL_DIR, "references", "changelog.md"), "# 更新记录"),
    # SKILL.md 里的路由表：格内出现未转义 `|` 会让「按需加载」的索引错位
    (SKILL_MD, "## 工作模式"),
    (SKILL_MD, "## 全栈层面导航"),
    (SKILL_MD, "## 参考资源"),
]
for path, heading in TABLES:
    lines = read(path)
    name = os.path.basename(path)
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith(heading))
    except StopIteration:
        check(False, "找到章节：%s @ %s" % (heading, name))
        continue
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
               len(lines))
    seg = lines[start:end]
    rows = [i for i, l in enumerate(seg) if l.startswith("|")]
    gaps = [(rows[k] + start + 1, rows[k + 1] + start + 1)
            for k in range(len(rows) - 1) if rows[k + 1] - rows[k] > 1]
    check(bool(rows) and not gaps,
          "%s 的表格连续（%d 行）" % (name, len(rows)),
          "空行在第 %s 行" % gaps if gaps else "未找到表格行")
    if rows:
        # 单元格里的 `||` 等未转义竖线会把该行拆成更多列，Markdown 表格因此错位
        def unescaped_pipes(line):
            return len(re.findall(r"(?<!\\)\|", line))
        base = unescaped_pipes(seg[rows[0]])
        inconsistent = [(i + start + 1, unescaped_pipes(seg[i]))
                        for i in rows if unescaped_pipes(seg[i]) != base]
        check(not inconsistent,
              "%s 的列数一致（%d 列分隔）" % (name, base),
              "不一致行（应写 \\| 转义）：%s" % inconsistent[:3])

print()
print("[2] ## 标题在文件内不得重复")
REF_DIR = os.path.join(SKILL_DIR, "references")
MD_FILES = [SKILL_MD] + sorted(
    os.path.join(REF_DIR, n) for n in os.listdir(REF_DIR) if n.endswith(".md"))
for path in MD_FILES:
    lines = read(path)
    name = os.path.relpath(path, SKILL_DIR).replace(os.sep, "/")
    seen = {}
    for i, l in enumerate(lines, 1):
        if l.startswith("## "):
            seen.setdefault(l.strip(), []).append(i)
    dups = ["%s (第 %s 行)" % (title[:40], at)
            for title, at in seen.items() if len(at) > 1]
    check(not dups, "%s 无重复 ## 标题" % name, "; ".join(dups[:3]))

print()
print("[3] evidence.md 轮次章节不得嵌在别的轮次之下")
ev = read(EVIDENCE)
rounds = []
parent = ""
for i, l in enumerate(ev, 1):
    if l.startswith("## "):
        parent = l.strip()
    m = re.match(r"^(#{2,3}) 第([一二三四五六七八九十]+|\d+)轮", l)
    if m:
        rounds.append((i, len(m.group(1)), l.strip(), parent))
check(bool(rounds), "找到轮次章节")
# 第 1–11 轮有意嵌在「历轮已确认的发现」下；同一个轮的 `### xxx轮的方法论教训` 也合法。
# 只有「轮次号不同」的嵌套才是隐患——那意味着整轮会被按 `##` 扫章节的动作漏掉。
nested_in_round = []
for ln, lv, title, parent in rounds:
    if lv != 3 or not re.match(r"^## 第([一二三四五六七八九十]+|\d+)轮", parent):
        continue
    if _round_no(title) != _round_no(parent):
        nested_in_round.append((ln, title[:34], parent[:24]))
check(not nested_in_round,
      "无轮次被嵌在别的轮次之下（%d 个轮次章节）" % len(rounds),
      "; ".join("%s 嵌在 %s" % (t, p) for _, t, p in nested_in_round[:3]))
bad_order = []
for k in range(len(rounds) - 1):
    if _round_no(rounds[k][2]) > _round_no(rounds[k + 1][2]):
        bad_order.append("%s → %s" % (rounds[k][2][3:22], rounds[k + 1][2][3:22]))
check(not bad_order, "轮次号递增", "; ".join(bad_order[:3]))

print()
print("[4] SKILL.md 引用的本地文件必须存在")
sk_text = "\n".join(read(SKILL_MD))
missing = []
for m in re.finditer(r"\]\(\./([^)]+)\)", sk_text):
    if not os.path.exists(os.path.join(SKILL_DIR, m.group(1).replace("/", os.sep))):
        missing.append(m.group(1))
check(not missing, "引用路径均存在", ", ".join(sorted(set(missing))))

print()
print("[5] references/ 下的 Markdown 必须被 SKILL.md 引用（防孤儿文档）")
referenced = set()
for m in re.finditer(r"\]\(\./([^)]+)\)", sk_text):
    referenced.add(m.group(1).replace("\\", "/"))
ref_dir = os.path.join(SKILL_DIR, "references")
ref_mds = sorted(n for n in os.listdir(ref_dir) if n.endswith(".md")) if os.path.isdir(ref_dir) else []
# 孤儿文件按判据 A 就是「无人消费的定义」：方法写了但下一轮没人会读到
orphans = [n for n in ref_mds if ("references/" + n) not in referenced]
check(bool(ref_mds) and not orphans,
      "references/ 下无孤儿 Markdown（%d 个文件均被引用）" % len(ref_mds),
      "未被 SKILL.md 引用：%s" % ", ".join(orphans))

print()
print("[6] SKILL.md 的判据字母不得重复")
sk = read(SKILL_MD)
letters = [m.group(1) for m in re.finditer(r"(?m)^### ([A-Z])\. ", "\n".join(sk))]
dup_letters = sorted({c for c in letters if letters.count(c) > 1})
# 并行会话撞过号；重复编号会让「按编号查既有结论」这一步给出错误答案
check(bool(letters) and not dup_letters,
      "判据字母唯一（%s）" % "".join(sorted(letters)),
      "重复：%s" % ", ".join(dup_letters))

print()
print("[7] patterns.md 的 P 编号不得重复且必须递增")
pat = read(os.path.join(SKILL_DIR, "references", "patterns.md"))
nums = [int(m.group(1)) for m in
        (re.match(r"^#{2,3} P(\d+)\b", l) for l in pat) if m]
dup_p = sorted({n for n in nums if nums.count(n) > 1})
check(bool(nums) and not dup_p, "P 编号唯一（%d 条）" % len(nums), "重复：%s" % dup_p)
bad_seq = ["P%d → P%d" % (nums[k], nums[k + 1])
           for k in range(len(nums) - 1) if nums[k] >= nums[k + 1]]
check(not bad_seq, "P 编号递增", "; ".join(bad_seq[:3]))


print()
if FAILURES:
    print("失败 %d 项：" % len(FAILURES))
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("全部通过")
sys.exit(0)

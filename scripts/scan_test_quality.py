#!/usr/bin/env python3
"""审计**测试套件自身**：判定器是否在实现之外、测试有没有判定力、夹具是否外部权威、
以及测试是否被接进反馈回路。

为什么值得单列一个扫描器：本 skill 的判据 A–I 都在审产品代码，
而「测试写得再多也不产生信心」这件事**产品代码里没有任何痕迹**——
它只在测试语料的聚合形态上显形（判定器指向自己、断言缺席、夹具与实现同错、
测试根本不在执行集内）。这类问题与判据 A–I 同属"单侧看着都对"：
每个测试文件单独看都正常，只有把判定器与实现对照才暴露。

用法：
    python scan_test_quality.py --repo d:/CodeProjects/siyuan
    python scan_test_quality.py --repo <repo> --section gate oracle
    python scan_test_quality.py --repo <repo> --min-funcs 3

输出**全是候选**，不是结论：判定器是否真在实现外面，必须回读调用点。
退出码 0 正常，2 表示扫描根不存在（零发现与没扫到在输出上无法区分）。
"""

import argparse
import os
import re
import sys
from collections import defaultdict

EXCLUDE_DIR_NAMES = {
    "node_modules", "build", "stage", "dist", "vendor", ".git",
    "__pycache__", "coverage", "win-unpacked",
}

# --- 通用工具 ---------------------------------------------------------------


def rel_path(path, roots):
    """输出以扫描根为基准的相对路径。

    **必须传 `start`**：`os.path.relpath(path)` 不传第二个参数时以 **cwd** 为基准，
    而 `--repo` 可以是任意路径；两者不同盘时（Windows：`d:\\...` 与 `c:\\...`）
    直接抛 `ValueError: path is on mount 'd:', start on mount 'C:'`，
    **整个脚本崩溃、一条结论都输不出**。教训：**测试结果依赖 cwd 的通过是假通过**。
    """
    for root in roots or ():
        try:
            return os.path.relpath(path, root).replace("\\", "/")
        except ValueError:
            continue
    return path.replace("\\", "/")


def iter_files(roots, exts):
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dir_path, dir_names, file_names in os.walk(root):
            dir_names[:] = [d for d in dir_names
                            if d not in EXCLUDE_DIR_NAMES and not d.startswith(".")]
            for name in file_names:
                if name.endswith(exts):
                    yield os.path.join(dir_path, name)


GO_STRIP = re.compile(
    r"//[^\n]*"                       # 行注释
    r"|/\*.*?\*/"                     # 块注释
    r"|`[^`]*`"                       # 原始字符串
    r"|\"(?:\\.|[^\"\\])*\""          # 解释字符串
    r"|'(?:\\.|[^'\\])*'"             # 字符字面量
    , re.S)

JS_STRIP = re.compile(
    r"//[^\n]*"
    r"|/\*.*?\*/"
    r"|`(?:\\.|[^`\\])*`"
    r"|\"(?:\\.|[^\"\\])*\""
    r"|'(?:\\.|[^'\\])*'"
    , re.S)


def strip_code(text, pattern):
    """把注释与字符串内容清空，**保持字节长度**（非换行字符换成空格）。

    保留长度是必需的：头部正则要在**原文**里找（JS 的测试名就是字符串，
    被清空后 `test("…"` 根本不匹配），而花括号配对必须在清空后的文本上做
    （否则字符串里的 `{` 会打乱深度）。两者用同一套偏移量才对得上。
    """

    def blank(match):
        return "".join("\n" if ch == "\n" else " " for ch in match.group(0))

    return pattern.sub(blank, text)


def blocks(head_text, brace_text, header_re, max_head=400):
    """按 `header_re` 找出每个块的头与花括号配对区间。

    返回 [(match, body_start, body_end, start_line)]；body 不含最外层花括号。

    **`header_re` 不得吃掉开括号**：头正则里若写了 `\\{?`，`find("{", end)` 会
    落到**函数体内的下一个块**，于是 body 被截成子块——实测这一处退化会把
    2582 个测试函数误报成「无断言」，而输出里的函数名还会变成跨行文本片段。

    **末位实参才是测试体**：Node 的 `test(name, options, fn)` 会把 options 对象
    放在函数之前，取「头之后第一个 `{`」会拿到 **options 对象**（`{skip: …, timeout: …}`），
    于是整条测试被误报成「无断言」——实测本仓库 12 个前端候选里 8 个由此而来
    （`skip` 只有在 Linux 无 DISPLAY 时才为真，形态很隐蔽）。判定条件三合一，
    避免误伤 `test(name, fn, timeout)` 里的函数体：① 头与该 `{` 之间**只有空白**
    （函数体前面必有 `async`/`=>`/`function`）；② 该组内容像**对象字面量**
    （以 `key:` 或 `...` 开头）；③ 该组之后紧跟 `,`（末位实参之后是 `)`）。

    表达式体（箭头函数不写花括号）没有可界定的范围，按 `max_head` 放弃，
    宁可漏报也不产出跨函数的假体。
    """
    out = []
    for match in header_re.finditer(head_text):
        pos = match.end()
        block = None
        while True:
            brace = brace_text.find("{", pos)
            if brace < 0 or brace - match.end() > max_head:
                break
            depth = 0
            end = None
            for i in range(brace, len(brace_text)):
                ch = brace_text[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end is None:
                break
            nxt = end + 1
            while nxt < len(brace_text) and brace_text[nxt] in " \t\r\n":
                nxt += 1
            between_is_blank = not brace_text[match.end():brace].strip()
            inner = brace_text[brace + 1:end].lstrip()
            looks_like_object = re.match(r"(?:[A-Za-z_$][\w$]*\s*:|\.\.\.)", inner) is not None
            if between_is_blank and looks_like_object and brace_text[nxt:nxt + 1] == ",":
                pos = end + 1          # 这是 options 对象，继续找末位的函数体
                continue
            block = (match, brace + 1, end, brace_text.count("\n", 0, match.start()) + 1)
            break
        if block:
            out.append(block)
    return out


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


# --- 判据：GO 侧的断言形态 --------------------------------------------------

GO_TEST_ONLY = re.compile(r"(?m)^func\s+(Test[A-Za-z0-9_]*)\s*\(")
GO_TEST_FUNC = re.compile(r"(?m)^func\s+(Test[A-Za-z0-9_]*|Benchmark[A-Za-z0-9_]*|Fuzz[A-Za-z0-9_]*)\s*\(")
GO_ASSERTION = re.compile(
    r"\bt\.(?:Error|Errorf|Fatal|Fatalf|FailNow|Fail)\b"
    r"|\b(?:assert|require|is|check)\s*\.\s*[A-Z]\w*\s*\("
    r"|\breflect\.DeepEqual\s*\("
    r"|\bcmp\.Diff\s*\("
    r"|\bexpect\s*\(")
GO_SKIP_ONLY = re.compile(r"\bt\.Skip(?:f|Now)?\s*\(")
# 断言常常封装在自定义 helper 里（`func mustNoError(t *testing.T, err error)`），
# 只看 `t.Error` 会把这类全部误报成「无断言」——这是本小节最大的假阳性来源。
# 判定分两步：先找函数声明，再在**签名区间**（到第一个 `{` 为止）里找
# `testing.T` / `testing.TB`。不把两步写进一个正则的两个原因：
#   ① 泛型声明名后有 `[...]` 类型参数（`func compareSettingConfig[Request …, Data, Config any](t *testing.T, …)`）——
#      实测这一条让 `kernel/api` 的 7 个契约测试被误报，而它们的断言
#      全部在那个泛型 helper 里；
#   ② 签名里可含括号（`factory func() Config`），`[^)]*` 会提前收口。
GO_FUNC_DECL = re.compile(r"(?m)^func\s+([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)?\(")

# 断言两侧都是函数调用 → 期望值由实现自己产生，判定器可能就在被测实现里
GO_EQ_CALL = re.compile(
    r"\b(?:assert|require|is)\s*\.\s*(?:Equal|Equalf|EqualValues|ElementsMatch|DeepEqual)"
    r"\s*\(\s*[^,()]+,\s*([^,]+?),\s*([^,]+?)\s*[,)]")
GO_DEEPEQUAL_CALL = re.compile(r"\breflect\.DeepEqual\s*\(\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)")
GO_IF_CMP = re.compile(r"\bif\s+(.+?)\s*(?:!=|==)\s*(.+?)\s*\{")

CALL_ONLY = re.compile(r"^([A-Za-z_][\w.]*)\s*\((.*)\)$")
# 曾在此处再设一道 `LITERAL_ONLY`（期望值是字符串/数字/true/false/nil 时跳过）。
# **已删除：它是死守卫**——字面量不匹配 `CALL_ONLY`，`callee()` 已先返回 None。
# 实测：把它改成恒假，偏答案、结论与候选数全都不变（负向用例抓不到它），
# 而按 `contributing.md` 第 13 条，不能被负向用例区分的守卫就是噪声。
# 两侧都来自格式化/转换工具族时，比较的是「工具的确定性输出」，不构成自我参照
UTIL_CALLEES = (
    "fmt.", "strings.", "bytes.", "strconv.", "sort.", "slices.", "maps.",
    "filepath.", "path.", "time.", "errors.", "unicode.", "regexp.", "hex.",
    "base64.", "binary.", "json.", "url.", "utf8.", "math.",
)


def callee(expr):
    expr = expr.strip()
    match = CALL_ONLY.match(expr)
    if not match:
        return None
    name = match.group(1)
    # 内建转换 len(x)/string(x) 也走这里，但它们是转换而非"实现"
    if name in ("len", "string", "int", "int64", "float64", "bool", "byte", "rune",
                "append", "make", "cap"):
        return None
    return name


def both_calls(lhs, rhs):
    a, b = callee(lhs), callee(rhs)
    if not a or not b:
        return None
    if a.rpartition(".")[0] or b.rpartition(".")[0]:
        # 至少一侧带包限定；两侧都是纯工具族时跳过
        if a.rpartition(".")[0] in UTIL_CALLEES and b.rpartition(".")[0] in UTIL_CALLEES:
            return None
    return (a, b)


def go_oracle_candidates(text):
    """返回 [(line, marked_expr, lhs, rhs)]，标记见下方。

    标记的含义（**都只是信号，不是结论**）：
      `[same]`   断言两侧调用了同一个函数——既可能是「用实现算期望」（可疑），
                 也可能只是「同一变换作用于两个不同输入」（正常）。区分法看输入：
                 两侧的**实参**是否都来自外部（字面量、夹具、另一实现）。
      `[local]`  两侧都是本包函数，没有任何包限定 → 期望值可能同样出自被测包。
      `[pkg]`    含包限定，跨包/跨实现对照的可能性更高（更可能是好断言）。
      `[repeat]` 同一个函数在**同一个测试函数**里被调用 >= 2 次、且该函数内有比较——
                 这是「改前 / 改后结果应相同」的状态差分式断言（本仓库实测形态：
                 `before` 与 `after` 都由 `SelectBlocksRawStmt` 产生）。
    """
    hits = []
    pairs = []
    for pattern in (GO_EQ_CALL, GO_DEEPEQUAL_CALL):
        for match in pattern.finditer(text):
            pairs.append((match.start(), match.group(1), match.group(2)))
    for match in GO_IF_CMP.finditer(text):
        pairs.append((match.start(), match.group(1), match.group(2)))
    for offset, lhs, rhs in pairs:
        got = both_calls(lhs, rhs)
        if not got:
            continue
        a, b = got
        if a == b:
            mark = "[same]"
        elif "." not in a and "." not in b:
            mark = "[local]"
        else:
            mark = "[pkg]"
        hits.append((line_of(text, offset), mark, lhs.strip()[:48], rhs.strip()[:48]))
    hits.extend(go_repeat_candidates(text))
    return hits


def go_repeat_candidates(text):
    """状态差分式断言：比较的两个操作数**都由同一个本包函数产生**。

    判定必须落到「被比较的那一对」上，不能只看「同一函数出现多次」：
    后者实测在 872 个文件上给出 **375 条**候选，而绝大多数只是
    `requireX(a); requireX(b)` 这类对多个输入做同样检查的正常写法。
    收紧后只认：比较的两侧是裸变量、且这两个变量分别由同一函数赋值。
    """
    assign = re.compile(r"(?<![\w.])([a-z_]\w*)\s*:?=\s*([A-Za-z_]\w*)\s*\(")
    ident = re.compile(r"^[a-z_]\w*$")
    out = []
    for match, start, end, line in blocks(text, text, GO_TEST_ONLY):
        body = text[start:end]
        produced = {}
        for call in assign.finditer(body):
            produced.setdefault(call.group(1), call.group(2))
        if not produced:
            continue
        pairs = []
        for pattern in (GO_EQ_CALL, GO_DEEPEQUAL_CALL):
            for got in pattern.finditer(body):
                pairs.append((got.group(1).strip(), got.group(2).strip()))
        for got in GO_IF_CMP.finditer(body):
            pairs.append((got.group(1).strip(), got.group(2).strip()))
        for lhs, rhs in pairs:
            if not (ident.match(lhs) and ident.match(rhs)):
                continue
            if lhs in produced and produced[lhs] == produced.get(rhs):
                out.append((line, "[repeat]", match.group(1),
                            "%s(%s) vs %s(%s)" % (produced[lhs], lhs, produced[lhs], rhs)))
    return sorted(set(out))


def go_helpers(texts):
    """从**同一个包（目录）**的全部测试文件里收集断言 helper 名。

    按单文件收集会漏掉跨文件的 helper：实测 `kernel/plugin/encoding` 里
    `mustNoError`/`mustEqual` 定义在另一个文件中，只扫本文件时整个包
    的测试都被误报成「无断言」。

    另外**不得只看函数名后紧跟 `(`**：泛型 helper 的名后是 `[...]`，
    实测 `kernel/api` 的 7 个契约测试因为断言全在泛型 helper
    `compareSettingConfig[...]` 里而被整批误报。
    """
    names = set()
    for text in texts:
        stripped = strip_code(text, GO_STRIP)
        for match in GO_FUNC_DECL.finditer(stripped):
            brace = stripped.find("{", match.end())
            if brace < 0 or brace - match.end() > 400:
                continue
            signature = stripped[match.end():brace]
            if "testing.T" in signature or "testing.TB" in signature:
                names.add(match.group(1))
    return (re.compile(r"\b(?:%s)\s*\(" % "|".join(re.escape(h) for h in names))
            if names else None)


def go_no_assertion(text, helper_call):
    """测试函数体内完全没有断言构造 → 无判定力候选。

    只统计 `Test*`：Benchmark 本来就不该有断言，Fuzz 的判定在 f 函数里。
    自定义断言 helper 的调用点算「有断言」。
    """
    stripped = strip_code(text, GO_STRIP)
    out = []
    for match, start, end, line in blocks(stripped, stripped, GO_TEST_ONLY):
        body = stripped[start:end]
        if GO_ASSERTION.search(body) or (helper_call and helper_call.search(body)):
            continue
        if GO_SKIP_ONLY.search(body):
            continue      # 只跳过的不算测试
        out.append((line, match.group(1)))
    return out


# --- 判据：JS/TS 侧的断言形态 -----------------------------------------------

JS_TEST_BLOCK = re.compile(
    r"(?m)^\s*(?:test|it)\s*\(\s*[\"'`]([^\"'`]{0,70})[\"'`]\s*,")
# 曾试过用 `=>` 启发式识别「不写花括号的表达式体测试」（如 `test("x", () => f())`）。
# 已移除：`=>` 在测试体内到处出现（`.map(c => parseInt(c, 16))`），
# 按行内包含 `test(` 过滤会漏进一大批 `.map` / `.filter` 回调，产出率低而噪声高。
# 表达式体测试的判定改为写进判据文字（见 SKILL.md 判据 J2）。
JS_ASSERTION = re.compile(
    r"\bassert\s*(?:\.\w+)?\s*\(|\bexpect\s*\(|\bchai\b")
# 前端同样会把断言包进箭头 helper（`const assertSubDoc = (t, e) => { assert.equal… }`）。
# 实测不认这类 helper 时，`app/src/util/parseNewDocTarget.test.ts` 一个文件
# 的 52 个测试全被误报成「无断言」——这是本小节第二大假阳性来源。
JS_HELPER_DECL = re.compile(
    r"(?m)^\s*(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)\s*(?:=\s*)?(?:async\s*)?"
    r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?:=>|\{)")
JS_EQ_CALL = re.compile(
    r"\bassert\s*\.\s*(?:strictEqual|deepStrictEqual|equal|deepEqual)\s*\(\s*([^,]+?)\s*,\s*([^,)]+?)\s*[,)]")


def js_helpers(texts):
    """从**同一个目录**的全部测试文件里收集断言 helper 名。

    与 Go 侧同因：helper 常定义在本文件，但目录级共享也常见；
    helper 跨文件声明时按单文件扫会漏。
    """
    names = set()
    for text in texts:
        stripped = strip_code(text, JS_STRIP)
        for match, start, end, _ in blocks(text, stripped, JS_HELPER_DECL, max_head=2000):
            if JS_ASSERTION.search(stripped[start:end]):
                names.add(match.group(1))
    return (re.compile(r"\b(?:%s)\s*\(" % "|".join(re.escape(n) for n in names))
            if names else None)


def ts_no_assertion(text, helper_call):
    stripped = strip_code(text, JS_STRIP)
    out = []
    # 头部在**原文**里找（测试名是字符串），花括号配对在清空后的文本上做。
    for match, start, end, line in blocks(text, stripped, JS_TEST_BLOCK, max_head=200):
        body = stripped[start:end]
        if JS_ASSERTION.search(body) or (helper_call and helper_call.search(body)):
            continue
        out.append((line, match.group(1)))
    return sorted(set(out))


def ts_oracle_candidates(text):
    hits = []
    for match in JS_EQ_CALL.finditer(text):
        got = both_calls(match.group(1), match.group(2))
        if not got:
            continue
        a, b = got
        mark = "[same]" if a == b else ("[local]" if "." not in a and "." not in b else "[pkg]")
        hits.append((line_of(text, match.start()), mark,
                     match.group(1).strip()[:48], match.group(2).strip()[:48]))
    return hits


# --- 判据：夹具是否外部权威 -------------------------------------------------

FIXTURE_HINT = re.compile(r"legacy|old[_A-Z]?format|\bv1\b|previous[_A-Z]?format",
                          re.I)
# 「提到 legacy」不够：注释里提一句、或字段名叫 legacy 都会命中。
# 但**宽到「任意 legacy 命名的赋值」同样不够**——迁移期把旧实现存成闭包做对照
# （`legacy := func(c *gin.Context) (result *gulu.Result) {…}`）很常见，那不是夹具；
# 实测旧的宽判据在本仓库给出 4 条候选，**全部为假阳性**（2 条闭包名、2 条 `legacyStats`
# 字段名），同时把 P53 的样板案例 `kernel/model/crypto_asset_legacy_test.go` 挡在门外。
# 新的判据是：legacy 命名的符号**自己产出旧格式的字节/串**——返回 `[]byte`/`string` 的函数，
# 或被赋值一个字节字面量。实测 4 条 → **2 条，且 2/2 为真**（第四十九轮）。
# 已知盲区：JS 侧用 `Buffer.from` / `new Uint8Array` 构造的旧格式夹具检测不到
# （本仓库 0 例，故不设未被用例覆盖的分支）。
FIXTURE_SITE = re.compile(
    r"func\s+\w*(?:Legacy|Old|V1)\w*\s*\([^)]*\)\s*(?:\[\]byte|string)\b"
    r"|\b\w*(?:legacy|old)\w*\s*:?=\s*\[\]byte\s*[\({]"
    r"|\b\w*(?:legacy|old)\w*\s*:\s*\[\]byte\s*[\({]", re.I)
FIXTURE_BUILD = re.compile(
    r"\[\]byte\s*\{|bytes\.Repeat|hex\.DecodeString|binary\.BigEndian|binary\.LittleEndian"
    r"|new Uint8Array|Buffer\.from|\.setUint\d")
# 只认「读捕获产物」。**不能写成 `os\.ReadFile|os\.Open`**：旧格式往返测试常读
# 自己刚写出的导出文件（`os.ReadFile(exportPath)`）做校验，那与「读夹具」无关——
# 实测该写法在 8 个文件里生效，而其中恰好包含 P53 的样板案例。
# 判据是**路径里出现 testdata/fixtures 这类夹具目录**，而不是「用过读文件 API」。
FIXTURE_CAPTURED = re.compile(
    r"testdata|//go:embed|embed\.FS|readFileSync|fixtures")


def fixture_candidates(path, text):
    """自建旧格式夹具：只在代码里现场构造、不读捕获产物。

    两个条件缺一不可：有构造点（`FIXTURE_BUILD`）、有夹具位点（`FIXTURE_SITE`）。
    只看「提到 legacy + 出现 []byte{」时，任何在注释里提一句旧版本的契约测试
    都会入选（实测 9 条里至少 4 条是这种）。
    """
    if not FIXTURE_HINT.search(text):
        return None
    if FIXTURE_CAPTURED.search(text):
        return None
    if not FIXTURE_SITE.search(text):
        return None
    builds = FIXTURE_BUILD.findall(text)
    if not builds:
        return None
    return sorted(set(builds))


# --- 判据：结构绑定 ---------------------------------------------------------

JS_HANDWRITTEN_TABLE = re.compile(
    r"\b(?:sources|modules|stubs?|mocks?|registry)\s*[:=]\s*\{")
GO_CALL_ORDER = re.compile(
    r"\b(?:wantCalls|expectedCalls|calledWith|callOrder|calls\s*=\s*append\()")


def binding_candidates(path, text):
    out = []
    for match in JS_HANDWRITTEN_TABLE.finditer(text):
        out.append((line_of(text, match.start()), match.group(0).strip()))
    for match in GO_CALL_ORDER.finditer(text):
        out.append((line_of(text, match.start()), match.group(0).strip()))
    return out


# --- 判据：反馈回路 ---------------------------------------------------------

ON_BLOCK = re.compile(r"(?m)^on:\s*(.*)$")
TEST_CMDS = (
    "go test", "pnpm test", "npm test", "yarn test", "pytest",
    "python -m unittest", "node --test", "cargo test", "npx jest",
)


def workflow_triggers(text):
    """粗解析 `on:` 块，返回 (trigger_keys, kinds)。

    `kinds` 是 trigger 下**限定条件**的形状集合：
    `branches`（分支 push 上跑）、`tags`（仅发布 tag）、`paths`（路径过滤）、
    `pull_request`。不引入 PyYAML：只需要触发条件的形状，
    而 YAML 解析会掩盖「写得对但跑不到」这类问题。
    """
    lines = text.split("\n")
    keys, kinds = [], set()
    for i, line in enumerate(lines):
        match = ON_BLOCK.match(line)
        if not match:
            continue
        inline = match.group(1).strip()
        if inline.startswith("["):
            keys.extend(k.strip() for k in inline.strip("[]").split(",") if k.strip())
            break
        if inline:
            keys.append(inline.split(":")[0].strip())
        for follow in lines[i + 1:]:
            if follow.strip() and not follow.startswith((" ", "\t")):
                break
            stripped = follow.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(follow) - len(follow.lstrip())
            if indent <= 2:
                name = stripped.split(":")[0].strip()
                keys.append(name)
                if name in ("pull_request", "pull_request_target"):
                    kinds.add("pull_request")
            elif indent == 4:
                name = stripped.split(":")[0].strip()
                if name in ("branches", "branches-ignore", "tags", "tags-ignore",
                            "paths", "paths-ignore"):
                    kinds.add(name.split("-")[0])
        break
    return sorted(set(k for k in keys if k)), kinds


def gate_section(repo, roots):
    lines = []
    workflows = []
    for path in sorted(iter_files([os.path.join(repo, ".github", "workflows")],
                                  (".yml", ".yaml"))):
        text = open(path, encoding="utf-8", errors="replace").read()
        cmds = sorted({c for c in TEST_CMDS if c in text})
        if not cmds:
            continue
        keys, kinds = workflow_triggers(text)
        workflows.append((rel_path(path, roots), keys, kinds, cmds))
    if not workflows:
        lines.append("未找到含测试命令的工作流 —— 测试没有任何自动化入口。")
        return lines, "none"
    verdicts = []
    for name, keys, kinds, cmds in workflows:
        lines.append("%s" % name)
        lines.append("  触发条件      : %s" % (", ".join(keys) or "(未解析到)"))
        lines.append("  限定条件      : %s" % (", ".join(sorted(kinds)) or "无"))
        lines.append("  测试命令      : %s" % ", ".join(cmds))
        # 门禁强度：PR > 分支 push > 仅 tag > 仅手动。
        # 「push 有 tags 限制但没有 branches」是 tag-only：分支上的每次提交都不跑。
        if "pull_request" in kinds:
            verdicts.append("pr")
        elif "branches" in kinds:
            verdicts.append("branch")
        elif "tags" in kinds:
            verdicts.append("tag")
        else:
            verdicts.append("manual")
    order = {"pr": 4, "branch": 3, "tag": 2, "manual": 1, "none": 0}
    best = max(verdicts, key=lambda v: order[v]) if verdicts else "none"
    return lines, best


# --- 主流程 -----------------------------------------------------------------

SECTIONS = ("gate", "oracle", "assert", "fixture", "binding")

# 成建制引入的上游/移植子树不在审计范围内（改了只会增大后续同步成本），
# 与 SKILL.md 「范围边界」一致。它们的断言习惯与目标仓库不同（如把断言
# 全放在跨文件 helper 里），不排除会污染候选量。
PORT_HEADER = re.compile(r"移植自|ported from|\\bPort of\\b", re.I)

_CACHE = {}


def load(path):
    if path not in _CACHE:
        _CACHE[path] = open(path, encoding="utf-8", errors="replace").read()
    return _CACHE[path]


def is_ported(path):
    head = "\n".join(load(path).split("\n")[:8])
    return bool(PORT_HEADER.search(head))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".",
                        help="目标仓库根目录（默认 cwd）")
    parser.add_argument("--section", action="append", choices=SECTIONS, default=None,
                        help="只跑指定小节，可重复（如 --section gate --section oracle）")
    parser.add_argument("--min-funcs", type=int, default=1,
                        help="只列出 >= N 个函数的文件（默认 1）")
    parser.add_argument("--include-ported", action="store_true",
                        help="不排除移植子树的测试文件（默认排除）")
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    if not os.path.isdir(repo):
        # 首行 ASCII 标记：stderr 可能在任何控制台编码下被读，
        # 且几个扫描脚本共用同一个可 grep 的契约（既有脚本用 no such directory）。
        sys.stderr.write(
            "no such directory: %s\n"
            "零发现与没扫到文件在输出上无法区分，故以退出码 2 报错而不是输出 0 条。\n"
            % args.repo)
        return 2

    roots = [repo]
    wanted = set(args.section or SECTIONS)
    go_all = [p for p in iter_files([os.path.join(repo, "kernel")], ("_test.go",))]
    js_all = [p for p in iter_files(
        [os.path.join(repo, "app", d) for d in ("src", "tests", "electron", "scripts")],
        (".test.ts", ".test.js"))]

    if not go_all and not js_all:
        sys.stderr.write(
            "no test files: 在 %s 下未找到 *_test.go 或 *.test.ts/js。\n"
            "请确认 --repo 指向仓库根目录（内含 kernel/ 与 app/）。\n" % repo)
        return 2

    ported = [p for p in go_all + js_all if is_ported(p)]
    if args.include_ported:
        go_files, js_files, ported = go_all, js_all, []
    else:
        go_files = [p for p in go_all if p not in ported]
        js_files = [p for p in js_all if p not in ported]

    # 断言 helper 按**目录（包）**聚合：跨文件的 helper 很常见
    go_by_dir = defaultdict(list)
    for path in go_files:
        go_by_dir[os.path.dirname(path)].append(load(path))
    helper_of_dir = {d: go_helpers(texts) for d, texts in go_by_dir.items()}
    js_by_dir = defaultdict(list)
    for path in js_files:
        js_by_dir[os.path.dirname(path)].append(load(path))
    js_helper_of_dir = {d: js_helpers(texts) for d, texts in js_by_dir.items()}

    out = []
    out.append("测试套件自身的审计（判定器 / 判定力 / 夹具 / 结构绑定 / 反馈回路）")
    out.append("=" * 72)
    out.append("扫描根      : %s" % repo)
    out.append("Go 测试文件 : %d" % len(go_files))
    out.append("前端测试文件: %d" % len(js_files))
    out.append("已排除移植文件: %d%s" % (len(ported),
                                    "（--include-ported 可关闭）" if not args.include_ported else ""))
    out.append("")
    out.append("本输出全是【候选】。判定器究竟在不在实现之外，必须回读调用点；")
    out.append("「两侧都是函数调用」只是信号，不是结论。")
    out.append("")

    if "gate" in wanted:
        out.append("-" * 72)
        out.append("[1] 反馈回路：测试是否接进自动化门禁")
        out.append("-" * 72)
        gate_lines, level = gate_section(repo, roots)
        out.extend(gate_lines)
        out.append("")
        VERDICT = {
            "pr": "有 PR 级门禁",
            "branch": "有分支 push 级门禁",
            "tag": "**只有 tag（发布）级门禁**——分支上的每次提交都不跑测试",
            "manual": "**只有手动触发**，测试不在任何自动路径上",
            "none": "**没有任何工作流包含测试命令**",
        }
        out.append("门禁结论    : %s" % VERDICT.get(level, level))
        out.append("判定法：门禁强度看 `on:` 的**限定条件**，不是看有没有 `on:`。")
        out.append("`push: tags: [...]` 只让打 tag 时跑，与 `branches:` 不是一回事。")
        out.append("")

    if "oracle" in wanted:
        out.append("-" * 72)
        out.append("[2] 自我参照判定器候选（断言两侧都是函数调用）")
        out.append("-" * 72)
        out.append("标记  [same]=两侧同一函数（最强）  [local]=两侧都是本包函数  [pkg]=含包限定")
        out.append("")
        per_file = defaultdict(list)
        for path in go_files:
            text = strip_code(load(path), GO_STRIP)
            for line, mark, lhs, rhs in go_oracle_candidates(text):
                per_file[rel_path(path, roots)].append((line, mark, lhs, rhs))
        for path in js_files:
            text = strip_code(load(path), JS_STRIP)
            for line, mark, lhs, rhs in ts_oracle_candidates(text):
                per_file[rel_path(path, roots)].append((line, mark, lhs, rhs))
        ordered = sorted(per_file.items(),
                         key=lambda kv: (-sum(1 for h in kv[1] if h[1] == "[same]"), kv[0]))
        total = sum(len(v) for v in per_file.values())
        strong = sum(1 for v in per_file.values() for h in v if h[1] == "[same]")
        for name, hits in ordered:
            if len(hits) < args.min_funcs:
                continue
            out.append("%s  (%d 条)" % (name, len(hits)))
            for line, mark, lhs, rhs in sorted(hits)[:12]:
                out.append("    %-8s %s:%d  %s  vs  %s" % (mark, name, line, lhs, rhs))
            if len(hits) > 12:
                out.append("    ... 另有 %d 条" % (len(hits) - 12))
        out.append("")
        out.append("命中文件 %d 个 / 候选 %d 条，其中同函数对照 %d 条。" % (len(per_file), total, strong))
        out.append("")

    if "assert" in wanted:
        out.append("-" * 72)
        out.append("[3] 无判定力候选：测试函数体内没有任何断言构造")
        out.append("-" * 72)
        rows = []
        for path in go_files:
            helper_call = helper_of_dir.get(os.path.dirname(path))
            hits = go_no_assertion(load(path), helper_call)
            if hits:
                rows.append((rel_path(path, roots), hits))
        for path in js_files:
            js_helper_call = js_helper_of_dir.get(os.path.dirname(path))
            hits = ts_no_assertion(load(path), js_helper_call)
            if hits:
                rows.append((rel_path(path, roots), hits))
        for name, hits in sorted(rows):
            out.append("%s  (%d 个)" % (name, len(hits)))
            for line, title in hits[:10]:
                out.append("    %s:%d  %s" % (name, line, title))
            if len(hits) > 10:
                out.append("    ... 另有 %d 个" % (len(hits) - 10))
        out.append("")
        out.append("无断言测试文件 %d 个 / 测试函数 %d 个。" % (len(rows),
                                                      sum(len(h) for _, h in rows)))
        out.append("只调用 t.Skip 的不计入；「只跑通不报错」与「验证了行为」不是一回事。")
        out.append("")

    if "fixture" in wanted:
        out.append("-" * 72)
        out.append("[4] 夹具外部性候选：提到旧格式，但只在代码里现场构造")
        out.append("-" * 72)
        rows = []
        for path in go_files + js_files:
            builds = fixture_candidates(path, load(path))
            if builds:
                rows.append((rel_path(path, roots), builds))
        for name, builds in sorted(rows):
            out.append("%s" % name)
            out.append("    现场构造: %s" % ", ".join(builds))
        out.append("")
        out.append("候选 %d 个文件。对照面：读 testdata/fixtures 的测试 %d 个文件。"
                   % (len(rows),
                      sum(1 for p in go_files + js_files
                          if FIXTURE_CAPTURED.search(load(p)))))
        out.append("自建旧格式夹具本身不是缺陷，但它**由实现者同时编写**时与实现同错，")
        out.append("可信度低于捕获的真实旧产物或跨实现产物（后者见判据 J3）。")
        out.append("")

    if "binding" in wanted:
        out.append("-" * 72)
        out.append("[5] 结构绑定候选：手写模块表 / 断言内部调用序列")
        out.append("-" * 72)
        rows = []
        for path in go_files + js_files:
            hits = binding_candidates(path, load(path))
            if hits:
                rows.append((rel_path(path, roots), hits))
        for name, hits in sorted(rows):
            for line, what in sorted(hits)[:8]:
                out.append("%s:%d  %s" % (name, line, what))
        out.append("")
        out.append("候选 %d 个文件。结构绑定的判定标准是「纯重构是否会让它变红」——" % len(rows))
        out.append("这类测试红的时候与被测行为无关，因此失败信息无法归因。")
        out.append("")

    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

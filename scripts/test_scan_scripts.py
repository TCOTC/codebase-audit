#!/usr/bin/env python3
"""两个扫描脚本的自检。

用法：
    python scripts/test_scan_scripts.py [目标仓库根目录]

目标仓库根目录也可用环境变量 `AUDIT_TARGET_REPO` 提供；不提供则只跑前两组
检查（它们不依赖任何外部仓库）。

**第 [4] 组是历史空档**（原第 [4] 组的内容已并入第 [3] 组），
组号**不重排**，同 patterns 里 P33 空缺的约定——因此输出从 [3] 直接跳到 [5]，
不是漏跑。

自检项（都是实际踩过的坑，不是通用断言）：

1. 根目录不存在时**不得**输出「0 个文件 / 0 条发现」并以 0 退出
   —— 零发现与没扫到文件在输出上无法区分，会把「没扫」当成「没问题」。
2. `--min-files` 的默认值必须与 SKILL.md 的建议一致（4）。
   默认 2 会产出约 4 倍噪声（实测 SiYuan 仓库：274 → 1060 条）。
3. 给了目标仓库时做冒烟：脚本能扫到文件并给出结论，
   防止正则或遍历被改坏后静默返回空。
4. `scan_unescaped_html` 的过滤规则不能过度放行：
   这里既固定「应当被过滤」的形态，也固定「必须保持不安全」的形态。
   后者更重要——规则写法退化（比如某条规则能匹配空串）会把全部候选判为安全，
   而脚本仍然输得出看起来正常的报告。
5. `scan_dom_type_literals`：不得把正则误取的非标识符形态（带 `[`、`^`、`(`）
   当成契约值——实测第一版把选择器片段 `tag[^` 报成了一个「契约值」。
   同时 `--kind node` 必须只出 `Node*`。
6. `scan_regression_index`：**空输入不得静默成功**。
   没拿到变更文件、或证据库不存在时，空索引与「没有历史发现」在输出上无法区分，
   会让使用者以为这个文件历史上很干净。另：它在交互式终端下**不得阻塞等 stdin**
   （会看起来像卡死），且子进程必须显式关掉 stdin 继承。
7. `scan_doc_parity`：目录不存在时不得输出「0 组」；且**交叉引用被本地化**
   必须被抵消（中文版指向 `X.zh-CN.md` 是正确行为）。实测不加抵消规则时，
   SY-FORMAT / TAB-BLOCK / WORKSPACE 三组会各报 1 条假差异。
8. `scan_i18n_text_expansion`：受约束容器的识别是承重的（`<option>` / `nowrap` /
   `ellipsis` / 同行固定宽度）；它必须**默认就不区分受约束与可换行**，
   不得假装自己知道谁在使用某个键。
9. `scan_a11y_antipatterns`：K5 的两层降噪都是承重的——
   ① 同选择器无 `:focus` 替代；② 类名落在可聚焦元素上（否则是容器，**不是缺陷**）。
   实测不做第 ② 层时，`.av` / `.emojis` / `.b3-form` 这类容器会被报成缺陷。
10. **扫描根与 cwd 不同盘时不得崩溃**。`os.path.relpath(p)` 不传第二个参数时以 cwd 为基准，
    扫描根在另一个盘（如仓库在 `D:` 而本 skill 在 `C:`）时抛
    `ValueError: path is on mount`，整个脚本崩溃、一条结论都输不出。
    该缺陷长期存在而未被发现，因为自检恰好在与仓库同盘的 cwd 下跑过——
    **测试结果依赖 cwd 的通过是假通过**。
    本组必须同时断言「不抛异常」与「输出不含绝对路径」：
    后者是必需的，只靠 `try/except` 吞掉异常并退回绝对路径也能“不崩”而输出不可读。

仅依赖标准库，无需第三方包。退出码 0 表示全部通过。
"""

import importlib.util
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")

SCAN_DUP = os.path.join(HERE, "scan_duplicated_literals.py")
SCAN_HTML = os.path.join(HERE, "scan_unescaped_html.py")
SCAN_DOM = os.path.join(HERE, "scan_dom_type_literals.py")
SCAN_IDX = os.path.join(HERE, "scan_regression_index.py")
SCAN_PARITY = os.path.join(HERE, "scan_doc_parity.py")
SCAN_I18N = os.path.join(HERE, "scan_i18n_text_expansion.py")
SCAN_A11Y = os.path.join(HERE, "scan_a11y_antipatterns.py")
SCAN_FOCUS = os.path.join(HERE, "scan_focus_coverage.py")
EVIDENCE = os.path.join(SKILL_DIR, "references", "evidence.md")

FAILURES = []


def run(script, *args, **kwargs):
    # stdin 必须显式关掉：子进程会继承父进程的 stdin，而 scan_regression_index
    # 无 --file/--git 时会读它——继承一个不结束的管道会让子进程永久阻塞，
    # 表现为「自检卡死」而不是「用例失败」。
    # cwd 可覆盖：跨盘用例必须显式指定，见第 10 组。
    proc = subprocess.run(
        [sys.executable, script, *args],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        cwd=kwargs.get("cwd"),
    )
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def check(condition, label, detail=""):
    if condition:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s%s" % (label, ("  -- " + detail) if detail else ""))
        FAILURES.append(label)


def load_html_scanner():
    # 用 importlib 从文件加载会写出 __pycache__，而这是要提交的仓库；关掉字节码写入。
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("scan_unescaped_html", SCAN_HTML)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


print("[1] 根目录不存在时必须报错，而不是假成功")
missing = os.path.join(HERE, "___no_such_dir___")
for script, name in ((SCAN_DUP, "scan_duplicated_literals"),
                     (SCAN_HTML, "scan_unescaped_html"),
                     (SCAN_DOM, "scan_dom_type_literals"),
                     (SCAN_PARITY, "scan_doc_parity"),
                     (SCAN_I18N, "scan_i18n_text_expansion"),
                     (SCAN_A11Y, "scan_a11y_antipatterns"),
                     (SCAN_FOCUS, "scan_focus_coverage")):
    flag = "--docs" if script == SCAN_PARITY else (
        "--langs" if script == SCAN_I18N else (
            "--styles" if script == SCAN_FOCUS else "--root"))
    argv = [flag, missing]
    if script == SCAN_FOCUS:
        # 该扫描器 `--root` 与 `--styles` 都是必填；只给一个会先触发 argparse
        # 的「参数缺失」错误，断言「stderr 说明原因」就会失败。
        argv += ["--root", missing]
    code, out, err = run(script, *argv)
    check(code != 0, "%s 退出码非 0（实际 %d）" % (name, code))
    check("no such directory" in err,
          "%s 在 stderr 说明原因" % name, repr(err[:120]))
    # 退出码非 0 也可能是**崩溃**而非主动报错。实测：把守卫改成 `if False:` 后，
    # 脚本会因后续逻辑抛异常而返回非 0，「退出码非 0」这条断言照样通过——
    # 只有断言「不是 traceback」才能区分「报错」与「炸了」。
    check("Traceback" not in err,
          "%s 是主动报错而非崩溃" % name, repr(err[:160]))
    check("files scanned: 0" not in out,
          "%s 不输出「files scanned: 0」" % name, repr(out[:120]))

print()
print("[2] --min-files 默认值须与 SKILL.md 一致")
code, out, err = run(SCAN_DUP, "--help")
m = re.search(r"--min-files[^\n]*?默认\s*(\d+)", out)
check(bool(m), "能从 --help 解析出默认值", repr(out[:200]))
if m:
    default = int(m.group(1))
    doc = io.open(SKILL_MD, encoding="utf-8").read()
    # SKILL.md 里对建议起点的表述可能改写（「从 4 起步」/「默认 4」），
    # 这里同时接受两种措辞，否则改文档措辞会让自检自己假失败。
    dm = (re.search(r"`--min-files`[^\n]{0,20}?(\d+)\s*起步", doc)
          or re.search(r"`--min-files`[^\n]{0,20}?默认\s*(\d+)", doc))
    check(dm is not None, "SKILL.md 写明了建议起点", "正则未命中，检查措辞是否又变了")
    if dm:
        expected = int(dm.group(1))
        check(default == expected,
              "默认值 %d == SKILL.md 的 %d" % (default, expected),
              "两者不一致时，不带参数运行会落到噪声档")
    check(default >= 4, "默认值不低于 4（当前 %d）" % default)

print()
print("[3] 过滤规则：既不能漏报已知安全形态，也不能把不安全形态放行")
scanner = load_html_scanner()
SAFE_CASES = [
    ("escapeHtml(userInput)", "项目约定的转义包装"),
    ("escapeAriaLabel(window.siyuan.languages.reset)", "属性语境的转义包装"),
    ("updateHotkeyTip(\"⌘Home\")", "固定串拼接的快捷键提示"),
    ("Constants.ZWSP", "仓库常量表"),
    ("ZWSP", "裸常量"),
    ("1", "纯数字"),
    ("++window.siyuan.zIndex", "自增计数"),
    ("true", "布尔字面量"),
    ("window.siyuan.languages.all", "受控 i18n 文案"),
    ("!this.collapsed", "布尔取反"),
    ("!this.protyle.disabled", "布尔取反（属性链）"),
    ("this.selectIds.length", "取长度"),
    ("this.pageCount.toString()", "数字转字符串"),
    ('filter === item.value ? " b3-chip--current" : ""', "三元两侧都是字面量"),
    ("hljsElement.firstElementChild.clientWidth + 16", "几何量参与运算"),
]
UNSAFE_CASES = [
    ("html", "裸变量可能是拼好的 HTML"),
    ("rowHTML", "拼好的表格行"),
    ("item.label", "可能来自用户数据的字段"),
    ("options.icon", "插件传入的值"),
    ("response.data.pageCount || 1", "跨模块返回值，无类型保证"),
    ("dayjs().format(\"YYYYMMDDHHmmss\")", "函数调用结果不可静态判定"),
    ("window.siyuan.config.export.imageWatermarkStr", "用户自填字符串会进 innerHTML"),
    ("getColIconByType(target.dataset.colType)", "由 dataset 驱动，值来自 DOM"),
]
for expr, why in SAFE_CASES:
    check(not scanner.looks_unsafe(expr, ""), "放行：%s（%s）" % (expr[:40], why))
for expr, why in UNSAFE_CASES:
    check(scanner.looks_unsafe(expr, ""), "保留候选：%s（%s）" % (expr[:40], why))

print()
print("[5] scan_doc_parity：目录缺失不得静默成功，且交叉引用本地化必须被抵消")
code, out, err = run(SCAN_PARITY, "--docs", missing)
check(code != 0, "目录不存在时退出码非 0（实际 %d）" % code)
check("no such directory" in err, "在 stderr 带 no such directory 标记", repr(err[:120]))
check("Traceback" not in err, "是主动报错而非崩溃", repr(err[:160]))
check("0 组" not in out, "不输出「0 组」", repr(out[:120]))
# 交叉引用抵消是承重规则：中文版指向 X.zh-CN.md 属正确行为
sys.path.insert(0, HERE)
spec = importlib.util.spec_from_file_location("scan_doc_parity", SCAN_PARITY)
parity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parity)
miss, extra = parity.cancel_localized_xrefs(
    ["SY-FORMAT.md", "WORKSPACE.md"], ["SY-FORMAT.zh-CN.md"], "zh-CN")
check(miss == ["WORKSPACE.md"] and extra == [],
      "本地化交叉引用被配对抵消（仅剩真差异）",
      "得到 miss=%s extra=%s" % (miss, extra))
# 「语言匹配」这个条件要用**能区分两种行为**的数据，「A.md vs A.ja.md」测不出：
# 它在「只抵消语言匹配的后缀」和「抵消任意 .md 后缀」两种逻辑下都不抵消。
# 必须让 extra 同时含匹配与不匹配的后缀，才能验证不过度抵消。
miss2, extra2 = parity.cancel_localized_xrefs(
    ["A.md"], ["A.zh-CN.md", "A.ja.md"], "zh-CN")
check(miss2 == [] and extra2 == ["A.ja.md"],
      "只抵消语言匹配的那一个（不过度抵消）",
      "得到 miss=%s extra=%s" % (miss2, extra2))
# 语言后缀完全不匹配（en 基准 vs ja 版本）时不得抵消任何项
miss3, extra3 = parity.cancel_localized_xrefs(["A.md"], ["A.zh-CN.md"], "ja")
check(miss3 == ["A.md"] and extra3 == ["A.zh-CN.md"],
      "基准语言与版本语言不符时不抵消",
      "得到 miss=%s extra=%s" % (miss3, extra3))

print()
print("[6] scan_i18n_text_expansion：受约束容器识别不得静默失效")
spec = importlib.util.spec_from_file_location("scan_i18n", SCAN_I18N)
i18n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i18n)
# `<option>` 是最确切的受约束容器（select 下拉项不换行）；实测历史面板的筛选下拉
# 有 7 个 <option> 取自 history* 一族键，而 de/ar 译文长 2-4 倍
OPTION_LINE = ('<option value="sync">${window.siyuan.languages.historySync}</option>')
hit_signals = [why for sig, why in i18n.CONSTRAINED_SIGNALS if sig in OPTION_LINE]
check(bool(hit_signals), "`<option>` 被识别为受约束容器",
      "CONSTRAINED_SIGNALS 是否被削弱")
check(bool(i18n.EXPLICIT_WIDTH.search('style="width: 80px"')),
      "同行固定宽度被识别", "EXPLICIT_WIDTH 是否被削弱")
check(not i18n.EXPLICIT_WIDTH.search('style="color: red"'),
      "无宽度声明不误报为固定宽度")
# i18n 取值的两种写法都要能抓到（含双引号下标形式）
refs = [m.group(1) or m.group(2) for m in i18n.I18N_REF.finditer(
    'languages.foo + languages["bar"]')]
check(refs == ["foo", "bar"], "能同时提取点号与下标两种取值", "得到 %s" % refs)
# 默认不得声称自己知道容器是否受约束
code, out, err = run(SCAN_I18N, "--langs", missing)
check(code != 0 and "no such directory" in err,
      "语言目录缺失时主动报错而非崩溃", repr((out + err)[:140]))

print()
print("[7] scan_a11y_antipatterns：K5 的两层降噪都不得静默失效")
spec = importlib.util.spec_from_file_location("scan_a11y", SCAN_A11Y)
a11y = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a11y)
check(bool(a11y.POSITIVE_TABINDEX.search('tabindex="3"')),
      "正整数 tabindex 能被识别（K2）", "POSITIVE_TABINDEX 是否被削弱")
check(not a11y.POSITIVE_TABINDEX.search('tabindex="0"'),
      "tabindex=\"0\" 不误报")
check(not a11y.POSITIVE_TABINDEX.search('tabindex="-1"'),
      "tabindex=\"-1\" 不误报")
check(bool(a11y.OUTLINE_NONE.search("outline: none;")),
      "`outline: none` 能被识别（K5）", "OUTLINE_NONE 是否被削弱")
check(not a11y.OUTLINE_NONE.search("outline-offset: 2px;"),
      "`outline-offset` 不误报为移除轮廓")
# 选择器分块：容器与可聚焦元素要能区分（第二层降噪的前提）
blocks = list(a11y.iter_scss_blocks(".a {\n  outline: none;\n}\n"))
check(len(blocks) == 1 and ".a" in blocks[0][0],
      "SCSS 选择器分块可用", "得到 %s" % (blocks[:1],))

# A6 的裁切：JS 字符串在同一行收尾时，末尾的 `';` 不得被当成按钮内文字。
# 实测未裁切时 SiYuan 的 A6 由 37 条降到 31 条（漏掉 6 条，其中 4 条集中在
# `protyle/toolbar/index.ts` 的同一个模板里）——同一形态的按钮因字符串
# 是否同行收尾而时报时不报。
tmpd6 = os.path.join(HERE, "___tmp_a6___")
os.makedirs(tmpd6, exist_ok=True)
try:
    io.open(os.path.join(tmpd6, "a.ts"), "w", encoding="utf-8").write(
        # ① 单行字符串收尾（末尾有 `';`）—— 必须被报出
        "const a = '<button class=\"x\" data-action=\"copy\">"
        "<svg><use xlink:href=\"#iconCopy\"></use></svg></button>';\n"
        # ② 多行模板收尾 —— 必须被报出
        "const b = `<button class=\"x\" data-action=\"cut\">"
        "<svg><use xlink:href=\"#iconCut\"></use></svg></button>\n"
        "<button class=\"x\" data-action=\"del\">"
        "<svg><use xlink:href=\"#iconDel\"></use></svg></button>`;\n"
        # ③ 有可见文本 —— 不得被报出
        "const c = '<button class=\"x\"><span>Copy</span></button>';\n"
        # ④ 有 aria-label —— 不得被报出
        "const d = '<button class=\"x\" aria-label=\"Copy\">"
        "<svg><use xlink:href=\"#iconCopy\"></use></svg></button>';\n")
    found6 = [no for _p, no, _t in a11y.scan_icon_buttons([tmpd6])]
    # 夹具的行号：1 = 单行收尾的图标按钮；2、3 = 多行模板里的两个图标按钮；
    # 4 = 有可见文本；5 = 有 aria-label。前三条必须报出，后两条不得报出。
    check(len(found6) == 3,
          "A6 同时报出单行与多行模板的图标按钮（%d 条，期望 3）" % len(found6),
          "得到行号 %s；为 2 说明单行收尾的按钮被误判为有文字名" % found6)
    check(1 in found6,
          "单行字符串收尾的按钮被报出（末尾 `';` 不被当成文字）",
          "若缺第 1 行，说明 BUTTON_CLOSE 裁切失效")
    check(2 in found6 and 3 in found6,
          "多行模板里的段落按钮也被报出", "得到行号 %s" % found6)
    check(4 not in found6, "有可见文本的按钮不被报出",
          "第 4 行按钮内含 <span>Copy</span>")
    check(5 not in found6, "有 aria-label 的按钮不被报出")
finally:
    for f in os.listdir(tmpd6):
        os.remove(os.path.join(tmpd6, f))
    os.rmdir(tmpd6)

print()
print("[11] scan_focus_coverage：四个判定前提都不得退化")
spec = importlib.util.spec_from_file_location("scan_focus", SCAN_FOCUS)
focus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(focus)

# ① SCSS 嵌套语义：不含 `&` 的子选择器是**后代**，祖先不得丢。
# 实测退化形态（只替换 `&`）会把 `.a button:focus` 降成裸 `button:focus`，
# 从而把一条局部规则当成全局兜底，把真缺口判成「已覆盖」。
resolved = focus.resolve([".a"], "button")
check(resolved == [".a button"],
      "不含 `&` 的子选择器按后代拼接（祖先不丢）", "得到 %s" % resolved)
resolved2 = focus.resolve([".a"], "&__b")
check(resolved2 == [".a__b"], "含 `&` 的子选择器按替换处理",
      "得到 %s" % resolved2)
# 组合用例：解析后必须保留祖先，否则会被当成全局规则
tmpd = os.path.join(HERE, "___tmp_focus___")
os.makedirs(tmpd, exist_ok=True)
try:
    io.open(os.path.join(tmpd, "a.scss"), "w", encoding="utf-8").write(
        ".protyle-preview__action {\n  button {\n    &:focus {\n      outline: none;\n"
        "    }\n  }\n}\ninput:focus {\n  box-shadow: 0 0 0 1px red;\n}\n")
    got = focus.parse_style_rules([tmpd])
    sels = [s for s, _d in got]
    check(".protyle-preview__action button:focus" in sels,
          "解析结果保留祖先（后代关系）", "得到 %s" % sels)
    check("protyle-preview" not in str(
        [s for s in sels if s.strip().startswith("button")]),
        "局部 button 规则未被提升成全局", "得到 %s" % sels)
finally:
    for f in os.listdir(tmpd):
        os.remove(os.path.join(tmpd, f))
    os.rmdir(tmpd)

# ② transform 必须算作「可见变化」：`.b3-slider` 的焦点指示是滑块放大
check(bool(focus.VISIBLE_RX.search("transform: scale(1.5)")),
      "`transform` 被算作可见焦点变化",
      "退化会把 .b3-slider 误报成缺口")
check(not focus.VISIBLE_RX.search("transform: none"),
      "`transform: none` 不算可见变化")
check(bool(focus.VISIBLE_RX.search("box-shadow: 0 0 0 1px red")),
      "盒阴影被算作可见变化")
check(bool(focus.VISIBLE_RX.search("outline: 2px solid red")),
      "真实的 outline 被算作可见变化")
check(not focus.VISIBLE_RX.search("outline: none"),
      "`outline: none` 不算可见变化")

# ③ 判定单位必须是**完整类集合**：焦点样式可能来自兄弟类。
# 实测 `.block__icon.block__icon--show.b3-tooltips.b3-tooltips__n`
# 的焦点样式来自 `.b3-tooltips:focus-within`，按单类查会误报。
# 注意：这里必须调用**扫描器自己的** verdict（模块级函数），
# 不能另写一份副本——测副本等于没测。
#
# 夹具要用**能区分两种行为**的类名：若让被覆盖的类恰好排在最前，
# 「按类集合」与「只按第一个类」会得出相同结果，用例就不承重。
# `zzz__covered` 排序在 `aaa__naked` 之后，因此只有类集合逻辑才能通过。
by_class, by_tag = focus.index_focus_rules(
    [(".zzz__covered:focus-within", "background: red")])
has, why = focus.verdict(frozenset(["aaa__naked", "zzz__covered"]), "button",
                         by_class, by_tag)
check(has and "zzz__covered" in why,
      "按完整类集合判定：兄弟类的焦点规则被采纳", "得到 %s / %s" % (has, why))
# 反面：类集合里没有任何成员有焦点规则时不得判为已覆盖
has_no, _ = focus.verdict(frozenset(["aaa__naked"]), "button",
                          by_class, by_tag)
check(not has_no, "类集合里无成员命中则不判为已覆盖")

# ④ 全局兜底必须**按标签**匹配：`button:focus` 不得覆盖 `<input>`
by_class4, by_tag4 = focus.index_focus_rules(
    [("button:focus", "box-shadow: 0 0 0 1px red")])
has_in, why_in = focus.verdict(frozenset(["b3-switch"]), "input",
                               by_class4, by_tag4)
check(not has_in,
      "`button:focus` 不覆盖 `<input>`（兜底按标签匹配）",
      "若为 True，说明标签匹配失效，.b3-switch 会被判成已覆盖")
has_btn, why_btn = focus.verdict(frozenset(["x"]), "button",
                                 by_class4, by_tag4)
check(has_btn, "`button:focus` 覆盖 `<button>`", "得到 %s" % why_btn)
# ⑤ 无祖先的全局规则才算兜底；带祖先的不得算
by_class5, by_tag5 = focus.index_focus_rules(
    [(".protyle-preview__action button:focus", "box-shadow: 0 0 0 1px red")])
has5, _ = focus.verdict(frozenset(["somebutton"]), "button", by_class5, by_tag5)
check(not has5,
      "带祖先的 button 焦点规则不算全局兜底",
      "若为 True，说明局部规则被提升成全局，真缺口会被判成已覆盖")


print()
print("[8] scan_regression_index：空输入与缺失证据库不得静默成功")
code, out, err = run(SCAN_IDX, "--evidence", missing)
check(code != 0, "证据库不存在时退出码非 0（实际 %d）" % code)
# 首行 ASCII 标记是四个脚本共用的契约（stderr 可能在任何控制台编码下被读）。
# 这一条才是承重的：退出码非 0 可能来自崩溃（见第 1 组的说明）。
check("no such file" in err, "在 stderr 带 no such file 标记", repr(err[:120]))
check("Traceback" not in err, "是主动报错而非崩溃", repr(err[:160]))
code, out, err = run(SCAN_IDX, "--evidence", EVIDENCE)
check(code != 0, "没拿到变更文件时退出码非 0（实际 %d）" % code,
       "否则「没检查」会被当成「没风险」")
check("no changed files" in err, "在 stderr 带 no changed files 标记", repr(err[:160]))
check("Traceback" not in err, "是主动报错而非崩溃", repr(err[:160]))
code, out, err = run(SCAN_IDX, "--evidence", EVIDENCE, "--index-only")
check(code == 0 and "登记的文件" in out, "证据库存在时能建成索引",
       repr((out + err)[:160]))
m = re.search(r"登记的文件\s*:\s*(\d+) 个", out)
check(bool(m) and int(m.group(1)) > 0, "索引里的文件数 > 0（%s）"
       % (m.group(1) if m else "?"))

print()
print("[9] 目标仓库冒烟：能扫到文件并给出结论")
repo = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AUDIT_TARGET_REPO", "")).strip()
if not repo:
    print("  SKIP  未提供目标仓库（传入路径参数或设 AUDIT_TARGET_REPO 即可启用）")
else:
    roots = [os.path.join(repo, "kernel"), os.path.join(repo, "app", "src")]
    roots = [r for r in roots if os.path.isdir(r)]
    if not roots:
        print("  FAIL  %s 下未找到 kernel/ 或 app/src/" % repo)
        FAILURES.append("目标仓库目录结构不符")
    else:
        for script, name in ((SCAN_DUP, "scan_duplicated_literals"),
                             (SCAN_HTML, "scan_unescaped_html")):
            args = []
            for r in roots:
                args += ["--root", r]
            code, out, err = run(script, *args)
            n = re.search(r"files scanned: (\d+)", out)
            check(code == 0 and bool(n) and int(n.group(1)) > 0,
                  "%s 扫到文件（%s）" % (name, n.group(1) if n else "?"),
                  repr(err[:120]))
        app_src = os.path.join(repo, "app", "src")
        if os.path.isdir(app_src):
            code, out, err = run(SCAN_DOM, "--root", app_src, "--kind", "node")
            m = re.search(r"不同契约值\s*:\s*(\d+)", out)
            check(code == 0 and bool(m) and int(m.group(1)) > 0,
                  "scan_dom_type_literals 提取到 Node* 契约值（%s）"
                  % (m.group(1) if m else "?"), repr(err[:120]))
            if m:
                # 回归：早期版本的正则过松，会把选择器片段当成契约值
                check("tag[^" not in out and "[" not in re.findall(
                    r"^\s+(\S+)\s+\d+ 文件", out, re.M)[:1],
                    "未把选择器片段当成契约值", "检查 VALUE_SHAPE 是否被放宽")
        else:
            print("  SKIP  %s 下无 app/src" % repo)
        docs = os.path.join(repo, "docs")
        if os.path.isdir(docs):
            code, out, err = run(SCAN_PARITY, "--docs", docs)
            m = re.search(r"文档组\s*:\s*(\d+)", out)
            check(code == 0 and bool(m) and int(m.group(1)) > 0,
                  "scan_doc_parity 找到多语言文档组（%s）"
                  % (m.group(1) if m else "?"), repr(err[:120]))
            if m:
                # 回归：本地化交叉引用被误报时，会有「X.md 有而本版无」而没有配对的
                # 「X.<lang>.md 本版有而基准无」——两者成对出现才算抵消成功。
                check("一致" in out or "有差异的文档组" in out,
                      "能给出结论行", repr(out[-160:]))
        else:
            print("  SKIP  %s 下无 docs" % repo)
        langs = os.path.join(repo, "app", "appearance", "langs")
        if os.path.isdir(langs) and os.path.isdir(app_src):
            code, out, err = run(SCAN_I18N, "--langs", langs, "--source", app_src)
            # 冒号用字符类兼容半角/全角：脚本的汇总行用全角，
            # 而早期断言写的是半角，造成了一次假失败（断言与实现的格式漂移）。
            m = re.search(r"已确认受约束的候选合计[：:]\s*(\d+)", out)
            check(code == 0 and bool(m) and int(m.group(1)) > 0,
                  "scan_i18n_text_expansion 给出受约束候选（%s）"
                  % (m.group(1) if m else "?"), repr(err[:160]))
            # 回归：给 --source 后必须真的按使用点过滤，不得等于未过滤的总数
            raw = re.search(r"受约束候选合计[：:]\s*(\d+)", out)
            if m and raw:
                check(int(m.group(1)) < int(raw.group(1)),
                      "--source 产生了实际过滤（%s < %s）"
                      % (m.group(1), raw.group(1)),
                      "否则交叉核对形同虚设，等于没做")
        else:
            print("  SKIP  %s 下无 app/appearance/langs 或 app/src" % repo)
        scss = os.path.join(repo, "app", "src", "assets", "scss")
        if os.path.isdir(app_src):
            args = ["--root", app_src]
            if os.path.isdir(scss):
                args += ["--styles", scss]
            code, out, err = run(SCAN_A11Y, *args)
            k2 = re.search(r"K2 正整数 tabindex[^：:]*[：:]\s*(\d+) 个", out)
            a6 = re.search(r"A6 纯图标按钮无可访问名[：:]\s*(\d+) 个", out)
            check(code == 0 and bool(k2) and bool(a6),
                  "scan_a11y_antipatterns 给出 K2/A6 结论（%s / %s）"
                  % (k2.group(1) if k2 else "?", a6.group(1) if a6 else "?"),
                  repr(err[:140]))
            if os.path.isdir(scss):
                m = re.search(r"经源码核对落在可聚焦元素上[：:]\s*(\d+) 个", out)
                c = re.search(r"未见落在可聚焦元素上[^：:]*[：:]\s*(\d+) 个", out)
                # 断言必须**无条件**做：早先写成 `if m and c:`，
                # 于是正则一旦失配（输出格式改了）整条断言就**静默消失**，
                # 自检仍然全绿——这正是「假成功」在自检自己身上的表现。
                check(m is not None and c is not None,
                      "K5 的两条计数行都能解析",
                      "经核对=%s 容器=%s" % (m.group(1) if m else "?",
                                            c.group(1) if c else "?"))
                if m and c:
                    check(int(m.group(1)) + int(c.group(1)) > int(m.group(1)),
                          "K5 的容器筛除确实生效（%s 确认 / %s 容器）"
                          % (m.group(1), c.group(1)),
                          "若容器数为 0，说明源码核对失效，容器会被当成缺陷上报")
            else:
                print("  SKIP  %s 下无 app/src/assets/scss，K5 未测" % repo)
        # scan_focus_coverage 冒烟：必须给出计数，且必须显式声明「不等于缺陷」
        if os.path.isdir(app_src) and os.path.isdir(scss):
            code, out, err = run(SCAN_FOCUS, "--root", app_src,
                                 "--styles", scss, "--styles",
                                 os.path.join(repo, "app", "appearance"))
            mn = re.search(r"无焦点指示\s*:\s*(\d+)", out)
            mu = re.search(r"表单控件使用点\s*:\s*(\d+)", out)
            check(code == 0 and mn is not None and mu is not None,
                  "scan_focus_coverage 给出使用点与缺口计数（%s / %s）"
                  % (mu.group(1) if mu else "?", mn.group(1) if mn else "?"),
                  repr(err[:140]))
            # 承重断言：必须写出「不等于缺陷」的限界，否则使用者会把
            # 462 条计数当成 462 个缺陷直接上报。
            check("必须回读使用点" in out,
                  "限界声明未被删掉（无焦点指示不等于缺陷）",
                  "缺失则计数会被当成结论")
            if mn and mu:
                check(0 < int(mn.group(1)) < int(mu.group(1)),
                      "缺口数介于 0 与总数之间（%s < %s）"
                      % (mn.group(1), mu.group(1)),
                      "为 0 说明降噪过度，等于总数说明没在判定")
        else:
            print("  SKIP  %s 下无 app/src 或 scss，焦点覆盖未测" % repo)

print()
print("[10] 扫描根与 cwd 不同盘时不得崩溃")
# 回归：`os.path.relpath(path)` 不传第二个参数时以 **cwd** 为基准，
# 当扫描根在另一个盘（Windows 上 `d:\...` 与 `c:\...`）时抛
# `ValueError: path is on mount 'd:', start on mount 'C:'`，整个脚本崩溃。
# 这个缺陷长期存在而未被发现，因为自检恰好在与仓库同盘的 cwd 下跑过——
# **测试结果依赖 cwd 的通过是假通过**。
if repo:
    app_src = os.path.join(repo, "app", "src")
    scss = os.path.join(app_src, "assets", "scss")
    if os.path.splitdrive(os.path.abspath(repo))[0].lower() != \
            os.path.splitdrive(HERE)[0].lower():
        for script, name, extra in (
                (SCAN_A11Y, "scan_a11y_antipatterns",
                 ["--styles", scss] if os.path.isdir(scss) else []),
                (SCAN_I18N, "scan_i18n_text_expansion", None)):
            if not os.path.isdir(app_src):
                print("  SKIP  %s 下无 app/src" % repo)
                continue
            if extra is None:
                langs = os.path.join(repo, "app", "appearance", "langs")
                if not os.path.isdir(langs):
                    print("  SKIP  无 langs 目录，%s 未测" % name)
                    continue
                extra = ["--source", app_src]
                code, out, err = run(SCAN_I18N, "--langs", langs, *extra, cwd=HERE)
            else:
                code, out, err = run(SCAN_A11Y, "--root", app_src, *extra,
                                     cwd=HERE)
            check("Traceback" not in err and "relpath" not in err,
                  "%s 在异盘 cwd 下不抛 relpath 异常" % name,
                  repr(err[:200]))
            check(code == 0, "%s 在异盘 cwd 下退出码为 0（实际 %d）"
                  % (name, code), repr(err[:200]))
            # 只测「不崩」不够：若退化成「吞掉异常后返回绝对路径」，
            # 不崩但输出不可读。所以还得断言输出里没有绝对路径。
            # 这两条合起来才覆盖 rel_path 的两种退化方式。
            leak = [l for l in out.split("\n")
                    if re.match(r"\s*[A-Za-z]:[/\\]", l)]
            check(not leak, "%s 输出路径为相对路径而非绝对路径" % name,
                  "绝对路径泄漏：%s" % repr(leak[:2]))
    else:
        print("  SKIP  目标仓库与本 skill 同盘（%s），异盘用例不适用"
              % os.path.splitdrive(os.path.abspath(repo))[0])
else:
    print("  SKIP  未提供目标仓库")

print()
if FAILURES:
    print("失败 %d 项：" % len(FAILURES))
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("全部通过")
sys.exit(0)

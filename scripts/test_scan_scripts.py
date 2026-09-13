#!/usr/bin/env python3
"""两个扫描脚本的自检。

用法：
    python scripts/test_scan_scripts.py [目标仓库根目录]

目标仓库根目录也可用环境变量 `AUDIT_TARGET_REPO` 提供；不提供则只跑前两组
检查（它们不依赖任何外部仓库）。

自检项（都是实际踩过的坑，不是通用断言）：

1. 根目录不存在时**不得**输出「0 个文件 / 0 条发现」并以 0 退出
   —— 零发现与没扫到文件在输出上无法区分，会把「没扫」当成「没问题」。
2. `--min-files` 的默认值必须与 SKILL.md 的建议一致（4）。
   默认 2 会产出约 4 倍噪声（实测 SiYuan 仓库：274 → 1060 条）。
3. 给了目标仓库时做冒烟：两个脚本能扫到文件并给出结论，
   防止正则或遍历被改坏后静默返回空。
4. `scan_unescaped_html` 的过滤规则不能过度放行：
   这里既固定「应当被过滤」的形态，也固定「必须保持不安全」的形态。
   后者更重要——规则写法退化（比如某条规则能匹配空串）会把全部候选判为安全，
   而脚本仍然输得出看起来正常的报告。

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

FAILURES = []


def run(script, *args):
    proc = subprocess.run(
        [sys.executable, script, *args],
        capture_output=True,
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
    spec = importlib.util.spec_from_file_location("scan_unescaped_html", SCAN_HTML)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


print("[1] 根目录不存在时必须报错，而不是假成功")
missing = os.path.join(HERE, "___no_such_dir___")
for script, name in ((SCAN_DUP, "scan_duplicated_literals"),
                     (SCAN_HTML, "scan_unescaped_html")):
    code, out, err = run(script, "--root", missing)
    check(code != 0, "%s 退出码非 0（实际 %d）" % (name, code))
    check("no such directory" in err,
          "%s 在 stderr 说明原因" % name, repr(err[:120]))
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
print("[4] 目标仓库冒烟：能扫到文件并给出结论")
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

print()
if FAILURES:
    print("失败 %d 项：" % len(FAILURES))
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("全部通过")
sys.exit(0)

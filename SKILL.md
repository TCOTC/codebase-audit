---
name: codebase-audit
description: 'Audit a codebase for hidden design and correctness problems that tests and linters cannot catch. Covers duplicated single-source-of-truth literals (hardcoded paths, keys, route strings), same-semantics implementations that drifted apart, state lost during async or lifecycle transitions, enumeration sets missing new members, unescaped interpolation into HTML, sibling code blocks that diverged, and assumptions about cross-repo or cross-platform behavior. Use when hunting latent design flaws, checking for design drift, finding duplicated hardcoded paths or constants, reviewing whether logic is duplicated across packages, auditing test blind spots, or preparing a large refactor. NOT for style or lint issues, not for runtime debugging, not for security review.'
argument-hint: '[scope: package or directory] [focus: literals | drift | state | all]'
---

# 代码库审计（隐藏问题扫描）

> **当前调校目标**：本 skill 的判据与实例围绕 SiYuan 仓库（`kernel/` Go + `app/src/` TypeScript）提炼。
> 用于其他仓库时，判据 A-G 与模式库仍然适用，但「已知误报」表、路径示例、`AGENTS.md` 约束需按目标仓库重新校准。
> 校准结论回写 [实证数据](./references/evidence.md)。

## 适用场景

找出**测试和 linter 抓不到**的问题。这类问题的共同特征是「单侧看着都对，只有交叉或跨状态才暴露」，所以加单测无用。

**不适用**：代码风格（用 lint 工具）、运行时调试、安全审计（那是另一套方法论）。

## 核心原则

### 1. 判据可验证

报告任何一条前，必须能回答：「用什么命令或文件行号证明它？」给不出证据的发现不要写进报告。

### 2. 三层漏斗，不要直接读代码

本仓库约 1282 个非测试源文件，逐个人工阅读不可行。必须逐层收缩：

```
全部文件  →  机械筛选（脚本/grep，产出候选）  →  语义判断（只对候选）
  1282              百量级候选                       top 20-30
```

**机械的事交给脚本，AI 只做语义判断。** 不要让 AI 做统计计数——既浪费又不可靠（本仓库曾有 agent 手写模拟依赖逻辑，漏掉三条规则差点得出反向结论）。

### 3. 机械判据与语义判据分开

| 类型 | 特征 | 产出 |
|---|---|---|
| 机械判据 | 可用脚本/grep 穷举，有明确阈值 | 候选清单，仍需人工确认 |
| 语义判据 | 判据是「是否语义同一件事」，grep 只能给候选 | 结论 + 证据 |

不要把机械判据包装成「AI 扫描」，也不要把语义判断降级成 grep 匹配。

### 4. 发现必须过挑战门

AI 审计最大的风险是合理化（rationalization）——把「代码可以更好」当成「这是 bug」。每条发现都要过 [挑战门](./references/challenge-gate.md)，尤其安全类、文档未定义行为类。

### 5. 结论必须落回业务表现

代码层的「变量写反了」「两侧逻辑不一致」**不是报告终点**。人类判断一条发现是否值得修，看的是「用户实际看到什么、应看到什么」。因此每条发现必须给出：

- **业务表现**：从用户可见入口走到该行为的具体路径 + 实际观察到的结果。要能写成「打开 A - B，就会看到 C」
- **预期表现**：应该是什么，且必须给出**权威依据**（项目文档、上游定义、既有正确实现、前端渲染契约、功能 issue 的意图）。给不出依据的「预期」只是审计者个人意见，按挑战门规则应驳回
- **可验证不变量**：一条能用输入/输出关系判定真假的等式或断言（如「各类型计数之和 = 总数」），供人工快速验证

写不出业务表现的发现，通常说明影响范围未查清，应降级为附录观察项而不是主报告条目。

### 6. 判据库要累积

每轮审计的产出除了问题清单，还包括**新增的有效判据**和**新发现的误报**，两者都写回 [模式库](./references/patterns.md) 与本文「已知误报」。这是「反复扫描」能越来越准的唯一机制，否则每次从零开始。

## 判据清单

### A. 单一真源缺失（机械，脚本覆盖）

充当标识符的字符串字面量（路径、键名、路由）在多处重复。**重复本身不是问题，重复的是「本该有单一真源」的东西才是问题。**

**风险分级**——只看重复次数会把三类混为一谈：

| 情形 | 风险 | 例 |
|---|---|---|
| 受类型系统校验，写错则编译失败 | 低 | 前端 API 路由字面量，受 `app/src/types/api/index.d.ts` 约束 |
| 裸字符串，无任何校验 | **高** | 内核里的 `"filesys_status_check"`、`"storage/local.json"` |
| 同目录已有同义常量却未复用 | **高** | 已有 `boxDocMetaName` 常量，但 `conf.json` 在各处裸写 |

**发现方式**：

```bash
python "<skill-dir>/scripts/scan_duplicated_literals.py" \
  --root kernel --root app/src --min-files 4 --out <工作区外临时路径>
```

`<skill-dir>` 指本 SKILL.md 所在目录。`--root` 按需替换为目标仓库的源码目录。

按 P1（路径类）/ P2（文件名类）/ P3（标识符类）分段，按跨文件数降序。**只看头部**。`--min-files` 从 4 起步，降到 2 会引入大量偶然命中。

### B. 语义漂移（语义判断）

同一语义存在两份实现，且已出现行为差异。**这是最高优先级**：两份规则必须人工同步维护，迟早失配。

**发现**：grep 疑似同义的函数名（`isIgnore`/`skippedDir`/`ignored`/`sanitize`），再用 subagent 并行比对。

**验证**：写临时测试，**两侧都调用真实代码**——不要模拟对侧逻辑。模拟本身会引入误差，且误差正好落在最需要验证的地方。

### C. 状态保持（语义判断，本仓库最高频）

本仓库 2499 条提交里 `preserve`/`keep`/`restore` 共 **344 次**，是最大的单一类别。典型形态：

- 异步回调覆盖用户此前的输入
- 重建 UI 时未回填原值（如写 `value: ""` 而非读取当前值）
- 生命周期切换（只读与编辑互切、标签页切换、键盘弹出）时状态丢失
- 并发更新互相覆盖

**发现**：找「重建 / 重置 / 重新渲染」的位置，检查是否从当前状态读值，而非写死初始值。

### D. 一致性与对称（半机械）

- **D1** 相邻或镜像代码块不对称：`upsert`/`remove`、`add`/`delete`、`save`/`load`、`encode`/`decode`
- **D2** 同一操作存在多个 API 表面（直接方法 vs 包装视图、构造器 vs setter、同步 vs 异步），边界行为分歧
- **D3** 闭合集合漏项：switch／白名单／枚举未包含上游新增成员。**上游定义即权威源，逐项比对；调用方自行补偿不算修复**
- **D4** 归约方向反转：把一组值聚合为单个标量时写成 `element += accumulator` 而非 `accumulator += element`，
  累加器恒为初值。**发现**：对「归约成标量」的循环，grep 该标量在函数内的全部出现；无赋值即恒为初值。
  重构是此类缺陷的高产入口，用 `git log -L <range>:<file>` 对照重构前的正确实现

**发现**：对可疑函数 grep 分派条件（`HasPrefix`/`HasSuffix`/`case`），检查成对分支条数与顺序是否一致。闭合集合可用脚本机械提取后与权威源 diff。

### E. 隐式假设（语义判断，风险最高）

- **E1** 对跨仓库依赖的内部行为做出假设（内核依赖 dejavu 的忽略语义即属此类，且升级无感知）
- **E2** 平台假设：Windows 隐藏属性、大小写敏感性、路径分隔符
- **E3** 匹配语义过宽或过窄：后缀匹配（`HasSuffix`）会误伤同形路径；前缀匹配缺边界检查（`startsWith("/api")` 会匹配到 `/api-docs`）
- **E4** 解析结构化值时用朴素字符串操作，而非按规范分词（逗号列表、大小写折叠、空白裁剪）

**验证 E3/E4**：构造一个「按规范合法但会被该实现误判」的输入，能构造出来即为候选缺陷。

### F. 插值转义（机械，脚本覆盖）

把动态值插入 HTML 时未转义。本仓库约定是 `escapeHtml` / `sanitizeKernelHTML`。

**发现方式**：

```bash
python "<skill-dir>/scripts/scan_unescaped_html.py" \
  --root app/src --out <工作区外临时路径>
```

`<skill-dir>` 指本 SKILL.md 所在目录。

**脚本产出的是候选，不是结论**。优先看表达式来自用户数据、文档名、标签名的位置；CSS 值与数值索引属噪声。

### G. 契约缺口

- **G1** 两个实现之间没有任何测试要求它们结论一致 → 缺交叉断言
- **G2** 序列化语义假设：JSON 数字精度、时间字段是字符串还是数字、空值与缺失的区别

**本仓库实证**：200 个 bug 修复提交中 **30% 同时补了测试**（详见 [实证数据](./references/evidence.md)），说明这些正是原有测试的盲区。**修复时补的测试类型，就是下一轮该主动检查的测试类型。**

## 执行流程

1. **确认范围**。全仓库还是指定包？先问清楚，避免无边界扫描。
2. **跑机械筛选**。执行 A、F 的脚本，产出候选清单。
3. **并行语义判断**。对候选头部逐条判断；B/C/D/E 类用 subagent 并行核查，避免污染主上下文。
4. **过挑战门**。对每条发现按 [挑战门](./references/challenge-gate.md) 做两轮对抗审查。
5. **强制取证**。每条发现给出文件:行与复现方式；能写测试的写测试。
6. **落回业务表现**。为每条发现写出「业务表现 / 预期表现 / 可验证不变量」三元组；预期表现的权威依据必须可引用。
7. **输出报告**。
8. **写回判据库**。新判据进 [模式库](./references/patterns.md)，新误报进本文「已知误报」。

## 输出格式

```
判据:     A / B / C / D / E / F / G + 编号
位置:     kernel/model/sync_path.go:153, kernel/util/runtime.go:345
证据:     <可复现命令或行号引用>
置信度:   高（已实测复现）/ 中（代码可证，未实测）/ 低（需人工确认）
挑战门:   CONFIRMED / DOWNGRADED（原因）/ 未触发
触发条件: <什么输入/状态才会出现该行为；说明是否常见>
业务表现: <用户可见入口（用 `设置 - 快捷键` 这种路径写法）- 实际看到什么>
预期表现: <应该是什么；权威依据一句>
可验证:   <一条可判定真假的等式/断言>
影响:     <具体后果，不要写"可能有问题">
建议:     <最小修复方向，不做大重构提议>
```

置信度必须诚实标注。低置信度条目保留但明确标注，交由人工判断，不要凑数。

「业务表现 / 预期表现 / 可验证」三项为强制项。写不出业务表现且给不出预期表现权威依据的发现，不得进入报告主列表，只能作为附录观察项。

## 已知误报（不要报告）

| 类别 | 示例 | 原因 |
|---|---|---|
| UI 类名/选择器 | `fn__none`、`b3-list-item__text`、`.protyle-wysiwyg--select` | UI 框架固有约定 |
| 带标签名的选择器 | `input.b3-text-field.search__label` | 同上，未被 `.` 前缀规则过滤 |
| 模板公式片段 | `.action{` | 模板语法 |
| 导入路径 | `github.com/siyuan-note/siyuan/kernel/util` | 模块路径，脚本已排除 |
| HTTP 固定值 | `Content-Type`、`application/json`、`utf-8` | 协议约定 |
| 纯扩展名 | `.json`、`.png` | 无信息量 |
| 数值字符串 | `0.38` | 样式比例等，需上下文判断 |
| i18n 索引 | `Conf.Language(147)` | 数字索引，非路径标识 |
| CSS 值插值 | `style="z-index: ${n}"` | 非 HTML 注入面 |
| 跨行已转义 | `${src}` 紧邻上一行的 `const src = Lute.EscapeHTMLStr(...)` | 脚本看不到前文赋值，候选需回读上下文 |
| 测试内重复 | `*_test.go`、`*.test.ts` 中的字面量 | 构造值，脚本已排除 |

## 修复时的硬约束

排查结论**不是**动手改动的授权。修改前必须遵守 `AGENTS.md`：

- **禁止** `git commit` / `git push`，除非用户明确要求
- 改 Go 代码后跑 `gofmt`，但不要编译内核或重启内核
- 改 `app/` 下代码后，以 `app/` 为工作目录跑 `pnpm run lint`；**不要**跑 `pnpm build`
- 改 i18n 后跑 `python scripts/check-lang-keys.py`
- 涉及同步忽略规则、加密笔记本、快照格式时，先读 `AGENTS.md` 兼容性条款——**忽略集合变动会导致其它设备签出时删除文件**，属高危改动

## 本 Skill 的版本管理（强制）

本 skill 目录是一个独立 Git 仓库，远程为 `origin`（`TCOTC/codebase-audit`）。**每次修改本 skill 的任何文件后，必须立即提交并推送**，不得只改不推。

这条规则**优先于**上文「修复时的硬约束」中的禁止提交条款——那一节约束的是被审计的目标仓库，本节约束的是 skill 自身的仓库。

固定流程（在 skill 目录下执行）：

```bash
git add -A
git commit -m "<本次修改摘要>"
git push
```

约定：

- 一次修改一次提交，提交信息说明改了什么（如「新增判据 D4」），不要攒多个改动一起提交
- 推送失败（无网络、需认证、远程有新提交）时，**不要静默跳过**：向用户报告失败原因，并说明本地已提交、待推送
- 若远程已有新提交，先 `git pull --rebase` 再 `git push`；冲突无法自动解决时停下询问用户
- 首次使用若 `origin` 未配置，先向用户索取远程地址再推送

## 参考资源

- [模式库](./references/patterns.md) — 缺陷模式定义、跨领域实例、更新机制
- [挑战门](./references/challenge-gate.md) — 两轮对抗审查，防误报
- [实证数据](./references/evidence.md) — 本仓库问题分布与修复形态的量化结论

## 更新记录

| 日期 | 变更 |
|---|---|
| 2026-09-13 | 初版。判据 A-G、挑战门、两个扫描脚本、实测数据 |
| 2026-09-13 | 移出仓库至用户级 `~/.agents/skills/`，脚本路径改为 `<skill-dir>` 形式 |
| 2026-09-13 | 第二轮：新增判据 D4（归约方向反转）、模式 P10；新误报「跨行已转义」；实证见 evidence.md |
| 2026-09-13 | 新增核心原则「结论必须落回业务表现」；输出格式加「触发条件 / 业务表现 / 预期表现 / 可验证」强制项 |
| 2026-09-13 | 新增「本 Skill 的版本管理（强制）」：skill 仓库每次修改后必须提交并推送 |

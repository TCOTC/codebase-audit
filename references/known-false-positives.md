# 已知误报（去重过滤集）

> **本文件是审计的过滤集，每轮必读**（`SKILL.md` 执行流程第 1 步）。
> 命中此表的位置不得重复立论，只允许追加证据。
> 新增条目时**保持表格连续**（表内不得有空行）——曾被空行切成两张，末行渲染成没有表头的表，
> 等于从过滤集中消失。单元格内的 `|` 必须写成 `\|`。

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
| 跨语言同名常量表的差异 | Go `SiYuanAssetsImage` 缺 `.tif`、TS `SIYUAN_ASSETS_IMAGE` 含 `.tif` | **不能一律判为漏项**：差异方向可能相反（TS 侧超收了浏览器渲染不了的格式），需先判定权威侧。只有能用「该差异产生可观测错误行为 + 存在可引用权威源」证明时才报告 |
| 同义解析函数的边界差异 | `getAssetPathWithoutQuery` 只切 `?` 不切 `#` | **需先验证多片段输入是否可达**：`split("?", 1)[0]` 在同时含 `?` 与 `#` 时会把片段一并丢弃，只有「无 `?` 的裸片段」才出错。且若主要消费点已被上游保护（如 `openLink` 先经 `resolvePdfAssetLink` 剥离片段），则报告的后果不成立——挑战门据此 DOWNGRADED。此类只作低危一致性清理 |
| 跨语言重复的枚举字符串 | Go `CalcOperatorPercentChecked = "Percent checked"` 与 TS `TAVCalcOperator` / i18n `percentChecked` 各自持一份同名值 | **协议名而非单一真源**：枚举名本身就是线协议的一部分，调用方逐字比对是必要形态；只有「**同一枚举的多个计算路径量纲/格式不一致**」才是缺陷（见 P18） |
| 跨端同源实现的「设置项不生效」差异 | 断言「移动端文件树未响应 `fileTree.docIconClickExpand`，属漏实现」 | **先确认该设置项在目标端是否被编译期剔除**：`app/src/config/tabs/fileTab.ts` 把这两个开关包在 `/// #if !MOBILE` 里，移动端根本没有该设置，`PinnedDocs` 的 `this.mobile \|\| …` 正是有意的平台区分。跨端对比前先 grep `/// #if` 保护块，再看是否有同端内的自相矛盾 |
| 声明了但永不填充的模型集合 | `app/src/layout/getAll.ts:64-113` 的 `models.inbox` 恒为空数组（`getTabs` 的 `instanceof` 链无 Inbox 分支） | **恒空但无消费者**：全仓无任何代码读取该字段，`resizeTabs()` 也不依赖它（收件箱面板是纯列表）。属「声明与实现不同步」的代码卫生问题，无业务表现，已列为观察项 |
| 「不跟随符号链接」的文件系统断言 | 断言 `os.RemoveAll` / `filelock.Remove` 对软链「只删链接本身、不递归进目标」，据此把路径越界发现降级为「防御纵深不一致」 | **只对叶子成立**：`unlink` 会解析全部前导组件，`RemoveAll` 打开 parentDir 时也无 `O_NOFOLLOW`，因此「中间组件软链」会操作链接目标（目录场景是递归删除目录外整棵树）。分析文件系统语义时必须分别讨论叶子与中间组件，否则会把真缺陷误判成主观项 |
| 断言「只读角色可调用漏挂 `CheckReadonly` 的端点」 | 报告 `/api/av/changeAttrViewLayout` 漏挂 `CheckReadonly` 时断言只读角色仍可改数据库布局 | **必须按中间件顺序核对角色可达性**：路由为 `CheckAuth → CheckAdminRole → handler`，`CheckAdminRole` 会把 `RoleReader`/`RoleVisitor` 直接 403，只读角色根本进不到 handler；真正可达的只有内核 `--readonly` 模式（管理员身份）。顺序读错会把「只读模式下的脏写」写成越权，被维护者一句驳回。附带：handler 内针对只读角色的分支（`IsReadOnlyRoleContext`）因此是死代码，可作为「作者曾考虑但未实现」的线索，不能作为可达性依据 |
| 审计者自行推断的上游状态码/协议映射 | 断言「DELETE 不存在的资源应返回 404」；断言「404 不可表达」 | **推断链的每一环都要读源码**：RFC 4918 §9.6 只规定「成功 DELETE **之后**的 GET 返回 404」，不要求 DELETE 本身返回 404；上游 `ServeError` 对普通 `errors.New` 一律映射 500，而根包又导出 `NewHTTPError` 使 404 可表达。**未逐一核实前不得写入「权威依据」**——错误的预期会让修法把「成功的幂等重试」变成 500，比原缺陷更糟 |
| 同族菜单项 `data-id` 复制未改 | 图片「高度」子菜单项写成 `id: "width_" + label`（`app/src/menus/protyle.ts:2139`） | **无消费方即无业务表现**：宽/高是两个不同的 `.b3-menu__items` 子树，不产生同层 `data-id` 冲突；`entryVisibility/catalog.ts` 与键盘导航都不读它。属发布物卫生问题，只能列观察项 |
| 只读下「菜单项显示了但点击必然失败」判为权限泄漏 | 标签面板右键菜单无 `readonly` 守卫，而书签面板有 | **先确认内核是否已兜底**：`kernel/api/router.go` 对应路由带 `CheckReadonly` 时不存在任何实际写入，最坏后果是「弹一个必然失败的错误提示」（重命名失败还会因 `cb` 不执行而卡住对话框，见 `app/src/util/noFetch`→`processMessage.ts:70`）。定性必须是 **UX 一致性（低）**，不能写成安全/数据缺陷 |
| 请求字段的 `trim` 看似只是宽松化 | 报告规范化标记时断言「最坏后果是接受了多余空白」 | **规范化有方向之分**：`trim` 对展示类、ID 类字段是「宽进」（无害），但对**密钥派生输入、签名原文、已落盘的等值匹配键**是「收窄后重算」，会让既有数据派生出不同结果。定性前先看该字段的消费端是否做密码学运算或持久化等值比较，不能按标记名一律判为宽松 |
| `var(--x)` 无 fallback 且样式表里找不到 `--x:` 定义 | `--drag-indent`、`--b3-table-frame-left`、`--b3-width-protyle-wysiwyg` | **CSS 自定义属性是本仓库里 JS→CSS 的运行时通道**，不是纯静态的样式表变量：这些令牌全部由 `element.style.setProperty(...)` / `removeProperty(...)` 或注入的 CSS 模板串写入。实测 34 条「无 fallback 的疑似缺失」**逐条回读后 17/17 全为假阳性**。判「令牌没人定义」必须三条件**合取**：① 引用侧无 fallback ② 所有样式根（**含主题目录**）无定义 ③ 源码里从未提及。条件 ③ 用**源码提及的宽规则**，不要把形态匹配（`setProperty("--x")` 之类）当成排除依据——窄规则漏过一次：`--b3-font-family-editor` 与 `--b3-font-size-editor` 写在同一个注入的 CSS 模板串里，带 backtick 锚点的规则抓不到同串第二个变量名。（本项原有专用脚本，因产出太低已于第二十三轮移除，检查法保留在 SKILL.md 判据 I 与层面地图 L11） |
| 同一 CSS 类组件的调用点属性不一致 | `.b3-switch` 有 25 种属性集形态、`.b3-button` 有 87 种 | **差异几乎全部来自调用点各自的 `data-*` 标识**，属合法。实测契约属性其实执行得很齐：`.b3-switch` 的 `type` 覆盖 **114/114**、`.b3-tooltips` 的 `aria-label` 覆盖 **159/159**；而 `.b3-button` / `.b3-label__text` / `.b3-dialog__action` / `.b3-select` / `.b3-menu__item` **根本没有契约属性**（契约就是那个类本身）。本仓库用 CSS 类作组件、模板字符串手写 HTML，**「没抽成 TS 组件」是设计意图而不是缺陷**。要谈漂移，先用**覆盖率**把「契约属性」与「调用点自有标识」分离（覆盖率 ~100% 才是契约，40–99% 需回读，<35% 基本是调用点数据） |
| 从第三方移植的样式里引用了本仓库已裁剪的令牌 | `--loading-icon`（`app/src/assets/scss/pdf/_pdf.scss:589`）、`--main-color`（同文件 `:740`） | **唯一使用点已被裁剪，规则不可达**。`_pdf.scss` 是从 Mozilla PDF.js 移植的（文件头为 Apache-2.0 声明），这两个变量在 PDF.js `viewer.css` 的 `:root` 里定义，移植时未带上。但它们的唯一使用点 `.toolbarField.pageNumber.visiblePageIsLoading` 中，类名 `visiblePageIsLoading` 在全仓出现 **0 次**；`#errorWrapper` 只在模板里出现一次且写死 `hidden='true'`，无任何 JS 取消隐藏。按既有标准属「无消费方即无业务表现」的**观察项**，不是缺陷。**判移植文件的令牌缺口前，先确认引用方是否还在** |

## 曾被误判为误报、实为真缺陷（不要据此排除）

上表是「不要报告」的过滤集，但历史上有条目**被错误地放进这里**，后来证实是真缺陷。
下列条目保留仅作为方法论提醒：**「该问题是环境噪声」这类降级结论本身也要过挑战门**，
尤其当降级理由是一条技术断言（「浏览器会忽略它」「CI 跑不到」「上游不会这样分派」）时。

- **宿主 MIME 注册表差异**（原误报，已改判，已修复）：Windows 上 `mime.TypeByExtension` 由注册表覆盖 Go 内置表
  （`initMimeWindows` → `setExtensionType`，仅 `.js` 有硬编码豁免）。当时以「测试与函数早于本次改动数周、CI 不复现」
  为由判为环境噪声，理由不成立——**测试在 Windows 上确定失败说明它不可移植，而白名单来源可被本机改写是产品层设计缺陷**。
  已提 #19475，维护者改为固定扩展名映射并显式写死 `Content-Type`（`2d0561daf5`）。
  **可复用教训：「CI 跑不到」不是免报牌，它是判据 G4 的独立发现。**

## 维护

- 新误报由审计轮次追加（`SKILL.md` 执行流程第 9 步）
- 追加后跑 `python "<skill-dir>/scripts/skill_self_check.py"` 确认表格未被破坏
- 抽查既有条目时不能只看它「说得通」，要看它的**降级理由能否被一次实验或一段源码推翻**

# 实证数据

本文记录本仓库的可量化事实与历轮审计的实际命中情况，供后续审计校准判据与阈值。**数据均为实测，非估算。**

## 代码库规模（2026-09-13）

| 范围 | 数量 |
|---|---|
| Go 非测试源文件（`kernel/`） | 512 |
| Go 测试文件（`kernel/`） | 408 |
| TS/TSX 非测试源文件（`app/src/`） | 770 |
| **审计扫描的文件总数** | **1282** |
| `kernel/` 顶层包 | 25 |

1282 个文件不可能逐个阅读，这是「三层漏斗」设计的直接依据。

## 问题类型分布（Git 历史）

样本：2499 条非 merge 提交，按 gitmoji 前缀与标题首词分类。

### 提交类别

| 类别 | 数量 | 占比 |
|---|---|---|
| bug fix | 1025 | 41% |
| UI/style polish | 823 | 33% |
| new feature | 265 | 11% |
| security | 117 | 5% |
| docs | 100 | 4% |
| performance | 34 | 1% |
| refactor | 25 | 1% |

### 标题动词（前 10）

| 动词 | 次数 | 含义 |
|---|---|---|
| improve | 403 | 改进 |
| support | 233 | 新增支持 |
| **preserve** | **159** | 状态保持类 |
| **prevent** | **123** | 防错／竞态类 |
| **keep** | **112** | 状态保持类 |
| refine | 93 | 打磨 |
| **restore** | **73** | 状态恢复类 |
| fix | 67 | 修复 |
| align | 56 | 对齐／一致性 |
| unify | 22 | 统一／一致性 |

### 关键结论

**状态保持类（preserve + keep + restore = 344 次）是本仓库最大的单一问题类别**，约占总提交的 14%，远超「重复实现」类（unify + align + correct ≈ 127 次）。

这意味着：**只覆盖「同一语义多处实现」的审计范围是不够的**。判据 C（状态保持）必须与判据 A/B 同等对待。

## 修复形态（200 个 bug 提交抽样）

| 指标 | 数值 |
|---|---|
| 改动 ≤10 行 | 65（32.5%） |
| 改动 11-50 行 | 55（27.5%） |
| 改动 51-200 行 | 48（24%） |
| 改动 >200 行 | 32（16%） |
| 只碰 1-2 个文件 | 117（58.5%） |
| 碰 3-5 个文件 | 45（22.5%） |
| 中位数改动行数 | 31 |
| 平均改动行数 | 87.1 |
| **修复同时补测试** | **61（30%）** |

### 关键结论

1. **近六成修复只碰 1-2 个文件**，中位数 31 行——问题是**局部的、隐蔽的**，不是大重构。这印证了扫描式审计的价值：这类缺陷无法靠架构层面的审视发现。
2. **30% 的修复同时补了测试**——这些正是原有测试的盲区。**修复时补的测试类型，就是下一轮该主动检查的类型。**

## 扫描脚本的阈值校准

`scan_duplicated_literals.py` 的调参过程（1282 个文件）：

| 配置 | 结果 | 结论 |
|---|---|---|
| 初版 | 1153 条 | import 模块路径霸榜（GitHub 路径 274 次） |
| 排除 import 块 | 694 条 | CSS 类名霸榜（`fn__none` 1287 次 / 198 文件） |
| 排除 CSS 类名与选择器，加分类 | 123 条 | 可用 |
| `--min-files 4` | **124 条** | 最终值：P1 88 / P2 16 / P3 20 |

**2026-09-14 复测**（1434 个文件，脚本形态未变）——用来给「默认值该取几」定量：

| `--min-files` | 候选条数 | 输出行数 |
|---|---|---|
| 2 | **1060** | 4355 |
| 4 | **274** | 1633 |

倍数约 **3.9×**。`--min-files 2` 多出来的几乎都是「只在 2 个文件里出现的偶然重复」，
而判据 A 的目标是「本该有单一真源的东西」，偶然重复不属此列。

**因此脚本的 `default` 已从 2 改为 4**：默认值落在噪声档上会让「不带参数运行」这个最常见用法
直接产出 4 倍噪声，而调用方（AI）很难意识到自己拿到的是噪声档——它只会看到「候选很多」。
参数默认值属于「机械的事」，应当与文档给出的建议值一致，而不是留一个需要读文档才能避开的坑。
`scripts/test_scan_scripts.py` 现在会断言两者一致。

### `scan_unescaped_html.py` 的误报率（2026-09-14 首次量化）

785 个文件 / **244 个候选点** / 95 个文件，与历史记录的「244 条 / 95 文件」一致（稳定基线）。

**抽样核对 100+ 条候选（含候选数最多的前 18 个文件的全部候选），判为真缺陷 0 条。**
抽样覆盖的误报类及判据：

| 误报类 | 条数 | 为什么不是缺陷 |
|---|---|---|
| 仓库常量表 `Constants.*` | 31 | 常量值 |
| 三元两侧均为字面量 | 16 | 分支里不可能含动态数据 |
| 裸大写下划线常量 | 16 | 同上 |
| 已转义的 HTML 变量（`html`、`rowHTML`） | 多条 | **转义发生在变量的拼装处**（逐项 `escapeHtml`），脚本只看到 sink 那一行 |
| 数字与几何量（`.length`、`.toString()`、`clientWidth + 16`） | 9 | 非注入面 |
| 受控 i18n 文案、`Lute.*` 生成值 | 5 | 值不受用户控制 |
| **用户自己配置里的字符串**（导出水印文本） | 2 | 功能本就以 HTML 为输入（`imageWatermarkDesc` 是刻意的 HTML 水印），属自注入而非安全边界 |

**关键结论：244 条候选归一化后只有 43 种表达形态**（把标识符替换成 `X`），前 6 种覆盖一半以上。
**「条数」不等于工作量，应按形态逐类判定**；实测把 244 条压到 48 种形态、再把可机械判定的 6 类剔除后，
真正需要读上下文的只剩三类：裸变量、DOM/接口驱动的值、跨模块返回值。

**按此校准扩充过滤规则后，候选 244 → 168（-31%）**，涉及文件 95 → 79。
同理也给 `scan_duplicated_literals.py` 的默认值做了校准（见上表）。

**脚本过滤器的写法陷阱（本轮自己踩过）**：第一版把多条规则写成一个 alternation 并统一用 `match`，
其中一条备选 `|\s*` 能匹配**空串** → 整个正则匹配一切 → **全部候选都被判为安全**，
而输出仍然是一份看起来正常的报告（只是候选数为 0）。
修法是拆成 `(正则, 是否锚定, 说明)` 的规则表，并加单元测试**同时锁定**「应放行」与「应保留」两类形态——
后者的价值更高，因为退化方向是静默的。

**必须排除的噪声类型**（否则报告被淹没）：

- import 模块路径（`github.com/...`）
- CSS 类名与选择器（`fn__none`、`.protyle-wysiwyg--select`、`input.b3-text-field.search__label`）
- HTML/模板片段（`</div>`、`${item.id}`、`.action{`）
- 纯扩展名（`.json`）
- 数值字符串（`0.38`）

## 历轮已确认的发现

### 第一轮（2026-09-13）

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| B | `PathsAffectSync` 与 dejavu `builtInIgnore` 对 5 个文件给出相反判定 | 高（已实测） | 已提 issue #19397 |
| A | `filesys_status_check` 在 3 处各自硬编码，无单一真源 | 高 | 已提 issue #19397 |
| E3 | dejavu 用 `HasSuffix` 匹配，隐含「数据目录必须名为 data」 | 高（测试复现） | 已提 issue #19397 |
| D1 | `repository.go` 的 `Upserts`/`Removes` 双循环逻辑不对称 | 中 | 已提 issue #19397 |
| A | `conf.json` 在 18 个文件裸写 28 次，而同目录已有 `boxDocMetaName` 常量 | 高 | 待处理 |
| F | 未转义插值 242 个候选（94 文件），需人工确认 | 低 | 待确认 |

### 第一轮的方法论教训

1. **不能模拟对侧逻辑**：验证两侧不一致时，曾手写代码模拟 dejavu 的 `builtInIgnore`，漏掉三条硬编码规则，导致首次测试得出**反向结论**。修正为「两侧都调用真实代码」后才得到正确结果。这是判据 B 验证方法必须强调「调用真实代码」的原因。
2. **模拟环境必须忠实于真实布局**：临时测试中 `util.DataDir` 未以 `data` 结尾，导致 dejavu 的后缀匹配未命中——这既暴露了测试设计问题，也**顺带印证了该实现的脆弱性**（依赖目录名）。
3. **`read_file` 可能读到陈旧内容**：脚本刚写入文件后立即读取会拿到旧版本，曾据此误判「CSS 过滤失效」。改用 `Select-String` 定位行号交叉验证。**验证脚本输出时优先用行号精确查询。**
4. **风险分级不可省略**：`/api/block/getDocInfo` 在 29 个文件硬编码，看似高价值目标，但受 `app/src/types/api/index.d.ts` 联合类型约束，写错会编译失败——风险远低于裸字符串。**只看重复次数会把这类混为一谈。**

### 第二轮（2026-09-13）

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1（新 P10） | `statTypesByPath`（`kernel/model/repository.go:1043`）聚合方向反转，`Other.Count` 恒为 0；提交 `e73f38390b` 重构引入的回归 | 高（代码可证 + git 对照） | 已确认，待修复 |

### 第二轮的方法论教训

1. **重构是缺陷的高产入口**。本次缺陷不是「写错」，而是「改写时写反」——原实现 `otherCount += count`
   是正确的，重构为「排序取前 N + 遍历剩余」时角色互换。
   启示：git 对照比单看当前代码更有力，`git log -L <range>:<file>` 能同时给出引入者与正确基线。
2. **变量「只出现不赋值」是强信号**。grep 某标量在函数内的全部出现次数，若只有声明与使用、无赋值，
   则其值恒为初值，围绕它的逻辑必然是错的。这是比模式匹配更硬的机械判据。
3. **前端渲染是「预期行为」的权威来源之一**。归约结果是否被展示、是否会显示 `Other 0`，
   可直接从前端 `forEach` 无过滤 + JSON tag 无 `omitempty` 推出，无需臆测。
4. **脚本误报新模式：跨行转义**。`scan_unescaped_html.py` 报 `app/src/asset/index.ts:115`
   的 `${src}` 未转义，实际上一行前已写 `const src = Lute.EscapeHTMLStr(...)`。
   脚本只按插值表达式名判断，看不到同一函数内前文的赋值——**这类候选需回读上下文**。

### 第三轮（2026-09-13）

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D3 / B（新 P11） | `kernel/util/path.go:341` `SiYuanAssetsAudio` 漏 `.aac`，TS `app/src/constants.ts:878` 含之；`IsDisplayableAsset` 为 false 使快照中的 `.aac` 退化为文本路径 | 高（代码可证，挑战门两轮 CONFIRMED） | 已提 issue #19400 |
| D3（反向漂移，观察项） | `SiYuanAssetsImage`（`path.go:340`）缺 `.tif`/`.tiff`，TS 侧含之；方向相反，需先定权威侧 | 中 | 观察项，不并入上条 |

### 第三轮的方法论教训

1. **「同名」是跨语言常量表配对的唯一线索**：两处列表既无共享常量也无 codegen，
   靠名字（`SiYuanAssetsAudio` ↔ `SIYUAN_ASSETS_AUDIO`）才能机械配对。这类候选应优先核对其**消费点**而非成员本身。
2. **漂移方向可能相反，不能笼统「对齐两侧」**：同一次审计在同一对表上同时发现
   内核漏 `.aac` 与 TS 超收 `.tif`/`.tiff`。前者该补内核，后者该收 TS——修复方向逐成员独立判定。
3. **同包内的自相矛盾是判定权威侧的硬证据**：内核 `commonSuffixes`（`kernel/util/file.go:169`）含 `.aac`，
   而 `SiYuanAssetsAudio` 不含 → 「有意排除」的解释不成立。这比引用提交历史更直接（历史需 git，成本高）。
4. **`content=""` 型静默降级**：内核门控为 false 时不写 `else`，返回空串；
   前端 `content || title` 兜底把内部路径当文本显示。**「门控 + 空值兜底」组合会把失败伪装成正常展示**，
   审计时对「只有 if 分支、无 else 赋值」的返回值要多看一眼。
5. **挑战门第二轮自动给出了「不要扩大修复面」的建议**：维护者立场反驳虽未推翻发现，
   但成功指出 `IsDisplayableAsset` 是安全敏感白名单（加密明文落盘 + `/repo/diff` 鉴权路由），
   据此把发现从「两处漏项」收窄为「仅 `.aac`」。**挑战门的价值不只在判真假，也在收窄边界。**

### 第四轮（2026-09-13）

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1 / B（新 P12） | `app/src/util/pathName.ts:174` `getAssetName` 的资源 ID 后缀正则未锚定结尾，剥**首个**匹配而非**结尾** ID，泄漏内部资源 ID 到重命名默认名 / 另存为默认名 / 数据库资源单元格 / 资源提示链接文字 | 高（Node 实测 + 5 处权威实现对照，挑战门两轮 CONFIRMED，严重度 low） | 已提 issue #19419 |
| F / A / E3 | 未转义插值、重复字面量、`HasSuffix`/`HasPrefix` 边界等机械候选（本轮复扫 128/243 条）均逐条核对为误报或低危 | — | 未命中 |
| C（状态保持） | 逐条核对了快捷键面板搜索重置、AV 插入行清空搜索、历史面板切换仓库清空搜索：均有两处以上同类实现或存在功能性理由，判为有意设计 | — | 不报告 |
| D1 | `kernel/av/sort.go` 的 `KeyTypeNumber`/`KeyTypeDate` 空值分支逻辑不满足反对称性，但唯一调用方 `sort.SliceStable` 已在外层用 `isSortValueEmpty` 过滤空值 → 死代码，无观测行为 | 高 | 观察项，不报告 |

### 第四轮的方法论教训

1. **挑战门两次都拦住了「后果被夸大」的发现**：`getAssetExtension` 不剥 `#` 的候选，代码事实为真，
   但审计者主推的后果（`openLink` 误判 PDF 不可预览）实际已被上游 `resolvePdfAssetLink` 消化，
   且 `split("?", 1)[0]` 在含 `?` 时会把片段一并丢弃——只有「无 `?` 的裸片段」才触发。**引用消费点前必须读完整调用链，
   而不是只看函数签名。**
2. **「两处以上同类实现」既是缺陷线索也是「有意设计」的反证**。AV 插入行 / 画廊插入卡片的清空搜索
   在两处出现且无注释，但清空能让新增行可见，属功能性理由；快捷键面板重置列表也如此。
   **同一异常行为在多个独立位置出现时，先假设它是有意的。**
3. **权威侧优先取「写盘路径」上的实现**。本轮判定「应剥结尾 ID」的依据是内核 `LastID`/`RemoveID`/`AssetName`/`assetNameWithoutID`
   四个写盘/命名函数，而非展示层函数；再加同仓前端两处锚定实现，形成 6 处对 1 处的格局，权威侧无争议。
4. **无单测的同义函数是漂移高发区**。`getAssetName` 在 `app/src` 中零测试覆盖，而它能长期保持错误。
   扫描时把「同义函数在多处出现但无任何测试」列为高优先候选。
5. **正则的「锚定」与「字符集」是两个独立漂移维度**：本轮同时发现 `\w{7}` 与内核 `ast.IsNodeIDPattern`（`[0-9a-z]{7}`）不一致；
   锚定问题有可观测后果，字符集问题没有，因此只报前者、后者记为观察项。**同一处发现内部也要分级。**
6. **本轮同时确认了前几轮的修复已落地**：`a0c881ebfb`/`2eddfddcba`（Other 计数）、`f7d758cf4f`（`.aac`）、
   `f781da1ceb`（同步忽略规则统一）均为本 skill 前几轮发现对应的修复提交。**回读这些提交可校准判据的有效性。**

### 第五轮（2026-09-13）

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1（同构分支判空缺失） | `kernel/av/calc.go` 中 relation 与 rollup 的 `CalcOperatorCountValues` 只做裸非空判断（`:1687`、`:1778`），而同函数的 `CountEmpty`/`CountNotEmpty` 按 `len(BlockIDs)`/`len(Contents)` 判空。因单元格在 `Calc` 之前已被 `fillAttributeViewBaseValue`（`kernel/sql/av.go:553`）经 `FillAttributeViewNilValue`（`:1100`）/`GetAttributeViewDefaultValue`（`kernel/av/value.go:3194`）无条件补成 `&ValueRelation{}`/`&ValueRollup{}`，该守卫恒真 → 「值数量」恒等于「条目数」 | 高（归一化链逐环核实；挑战门两轮 CONFIRMED，严重度 low） | 已提 issue #19422 |
| A / F / E3 | 机械复扫：重复字面量 135 条、未转义插值 244 条、前端 `/api/` 路由字面量 462 个、前端 i18n 键 0 缺失、内核 `Conf.Language(n)` 索引 0 越界；逐条核对后无新命中 | — | 未命中 |
| P10 | 把「累加器恒为初值」一般化为脚本（零值变量在函数内无二次赋值）后复扫全仓，`assigns=0` 仅 8 处，逐条核对均为结构体字段初始化或合法守卫 | — | 未命中（该 bug 类已随 #19398 修复） |
| C | 并行核查编辑器 / 设置对话框 / 移动端的状态保持，确认存在 `valid()`/`epoch`/`revision` 二次校验与显式 scroll/focus/展开态保存恢复；仅 AI 设置的三处开关存在「旧数组快照整段覆盖」的丢失更新（窄窗口，未报告） | 中 | 观察项，不报告 |

### 第五轮的方法论教训

1. **「同一函数族」是 D1 的最高产形态**。`kernel/av/calc.go` 里同名 `case` 分支重复 13 次，
   逐处 diff 判定条件后，只有 2 处漏了语义判空 —— 逐行 diff 近同构分支的成本远低于通读整文件。
2. **恒真守卫要靠「值的构造路径」证伪**，不能只看局部。本轮的证据链是
   `av_table.go:128 → av.go:553 → av.go:1100 / value.go:3194`，缺任一环结论都不成立。
   **读消费点不算完，要读生产者。**
3. **「同款写法」既可能是惯例也可能是照搬**。`calcFieldCreated` 同样用裸非空检查，但 Created 字段
   自动填充后「非空 ⟺ 有值」，故其写法正确。**先判定该写法在每一类字段上是否语义等价，再下结论。**
4. **反例要选「无争议语义」的那个**。本轮最初给出的不变量是 `Count values == Count not empty`，
   但多值字段（MSelect/MAsset）的 `Count values` 累加的是值的个数，该等式并不普遍成立。
   挑战门据此收窄为「全空关系列应显示 0 而非行数」——这个反例不依赖任何语义解释，无法被辩护。
   **选反例时优先选择任何合理语义下都错的输入。**
5. **机械脚本要把「归约方向反转」一般化后再复扫**。把第二轮的个案判据写成
   「零值变量在函数内无二次赋值」脚本后，全仓仅剩 8 条候选且全为误报，可确认该类已清零，
   后续轮次不必再投入。

### 第六轮（2026-09-13）

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1b（新 P13）/ E3 | `kernel/util/file.go:417` `IsCompressibleAssetImage` 的 `HasPrefix(p, "assets/")` 守卫恒为 false（唯一调用点 `kernel/model/assets.go:237` 传绝对路径），函数体却用 `strings.Cut(p, "assets/")` 按绝对路径切片；后果是 `temp/thumbnails/assets/**` 永不失效 | 高（调用链逐点核实；挑战门第一轮 CONFIRMED、第二轮 DOWNGRADED 严重度为低） | 已提 issue #19424 |
| 候选（未过挑战门） | `kernel/av/filter.go:799-807` 汇总筛选 `None + Is empty` 在「存在空目标值」时 `return true`，与同输入的 `Any`（`:716` 亦 true）、`All`（`:758` false）冲突，且与本分支紧随的循环（发现空即 `return false`）方向相反 | 中 | 附录观察项 |
| A / F | 机械复扫：重复字面量 136 条、未转义插值 244 条；逐条核对仍为已知噪声（`conf.json`、CSS 选择器、受类型约束的 `/api/` 路由、数值字符串） | — | 未命中 |

### 第六轮的方法论教训

1. **恒假守卫是独立于恒真守卫的缺陷形态**。第五轮确立的「恒真守卫」靠上游归一化证伪；本轮确立的「恒假守卫」靠**下游调用点的实参形态**证伪。二者方向相反：恒真看生产者，恒假看调用者。已把 D1b 与 P13 写入判据库。
2. **「守卫与函数体自相矛盾」是最省力的取证**。同一函数里守卫假定相对路径、函数体却按绝对路径 `Cut`，二者必有一错，不回读全部调用点也能初判。若无这处矛盾，本发现需完整调用链才能定性。
3. **严重度由「应用自身是否会走进这条路径」决定，不由代码形态决定**。本缺陷代码层无可辩驳，但应用写资源时**永远追加新 NodeID**（`kernel/model/upload.go:133` `newAssetFileName` 注释、`storeAssetForBox` 同名不同内容强制换名），使正常流程不触发。挑战门第二轮据此把严重度从「功能失效」下调为「低危、可自愈的缓存陈旧」。
4. **缓存类缺陷要同时确认「唯一的失效路径」**。本轮逐一排除了 mtime 比较、启动清理、退出清理、cache-busting URL：启动清理（`kernel/util/working.go:365-368`）与退出清理（`kernel/model/conf.go:1500-1513`）的目录清单都不含 `thumbnails`，只有用户手动的 `clearTempFiles`（`kernel/model/box.go:870-873`）含之。**确认「无替代失效机制」后，死守卫才等价于永久陈旧。**
5. **子代理并行侦察 + 主上下文自验的组合有效但需强约束**。三个 Explore 子代理各返回 2-3 条候选，其中 4 条经自验后为误报或不可达；要求「必须给出反证检查结果与置信度」显著降低了噪声。**子代理产出只能当候选，取证必须在主上下文重做。**

### 第七轮（2026-09-13）

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D3（新 P14） | `kernel/treenode/blocktree.go:499` `IsContainerType` 白名单漏掉 `"tab"`（页签项）→ `CheckContainerParent`（`:511`）对页签项报 `type "tab" is a leaf block and cannot have children`（`:524`）。上游 lute `IsContainerBlock`/`CanContain` 与同包 `CanContainBlock`（`block_structure.go:29`）都认定页签项是容器块；同包 `NormalizeTabs` 还主动为其补段落子块。受影响的写路径共 14 处：API（`kernel/api/block_op.go:452,534,575,624,738`）、MCP（`kernel/mcp/tools/block.go:202,259,303,456`）、CLI（`kernel/cli/cmd/block.go:208,250,290,470`）、`kernel/model/block_operation.go:34`、`kernel/model/attribute_view_create.go:58` | 高（实测复现：同一页签项 ID `get_children` 返回 5 个子块、`append(parentID=该ID)` 被拒，报错串与 `:524` 完全一致） | 已提 issue #19428 |
| D3（同源第二处） | `kernel/model/block.go:87` `Block.IsContainerBlock()` 同样漏掉 `NodeTabs`/`NodeTabItem`。唯一消费点 `kernel/model/search.go:528`（`((` 引用候选排除父块，issue #4538）；仅当用户在「搜索 - 页签项」开启该类型（`kernel/conf/search.go:47,93` 默认 false、`app/src/search/menu.ts:150`）时才可达，未实测 | 中 | 观察项，随主条目一并修复 |
| A / F | 机械复扫：重复字面量 136 条（P1 100/P2 16/P3 20）、未转义插值 244 条/95 文件；逐条核对仍为已知噪声（`assets/`、`/stage/loading-pure.svg`、受 `app/src/types/api/index.d.ts` 联合类型约束的 `/api/` 字面量、CSS 选择器、`z-index` 插值） | — | 未命中 |
| D4（脚本化复扫） | 子代理按「零值变量在函数内无二次赋值」复扫 `kernel/model`、`kernel/av`、`kernel/sql`、`kernel/search`、`kernel/treenode`，定式 `\w+\.\w+ \+= \w+$` 全仓 16 处逐一读毕，无反转 | — | 未命中（该类已随 #19398 清零） |

### 第七轮的方法论教训

1. **「同包自相矛盾」是闭合集合漏项的最省力入口**。本轮不必先证明可达性：同包 `CanContainBlock`（委托上游）说页签项能容纳段落，而 `IsContainerType` 说它是叶子块，二者必有一错。**在一个包里找同一语义的两份判定，diff 它们的成员集合，比通读调用链快一个数量级。**
2. **手写能力白名单要按「特性时间线」核对**。白名单 `db266e7fab`（2026-06-20）早于页签特性 `5b8556e965`（2026-09-05）2.5 个月——**用 `git log -S` 定位白名单与新特性的引入顺序，能一眼判定「漏项」而非「有意排除」**。
3. **权威侧判定的顺序：上游库类型方法 > 同包委托上游的函数 > 同包主动构造该结构的函数 > 手写枚举**。本例三者一致指向「页签项是容器」，白名单是唯一少数派。
4. **差异方向要逐成员定性，修法不是「往多的一侧补」**。上游 `IsContainerBlock` 含 `NodeTabs` 与 `NodeTabItem` 两个成员，但 `CanContain(NodeTabs, …)` 只允许 IAL——直接补齐两个会放行非法嵌套。**写建议时必须给出「只补 `tab`，或改用 `CanContain` 语义判定」这类精确修法。**
5. **一票否决的实测优势：拒绝型缺陷可以零副作用复现**。`append(parentID=页签项ID)` 预期失败，执行后工作区无任何写入，因此可以放心在真实实例上取证；相比之下「写入成功型」缺陷需要建临时文档并回删。**优先挑选零副作用的复现场景。**
6. **MCP 工具可直接充当内核 API 的取证探针**，无需本机 HTTP：`mcp_siyuan_block` 的 `append/move/insert` 走的就是 `CheckContainerParent` 同一条路径，`get_children` 则是读路径对照。注意 `mcp_siyuan_sql` 只暴露主库，`blocktrees` 表不可查（`no such table: blocktrees`），页签项的 `type='tab'` 只能在 `blocks` 表验证，`blocktrees` 侧靠 `blocktree.go:837` 的写入代码佐证。

### 第八轮（2026-09-13）

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D3c（新 P15）/ A / P4 | 搜索「保存条件」静默丢弃 `tabs`/`tabItem` 两个类型过滤开关：权威集合 `kernel/conf/search.go:46-47` 的 `conf.Search.Tabs`/`TabItem`（`TypeFilter()` 与 `kernel/model/search.go:2090-2091` 的 `buildTypeFilter` 都按这两个键读），但 `kernel/model/storage.go:142` 的 `model.CriterionTypes` 与 `kernel/apicontract/criterion.go:20` 的 `apicontract.CriterionTypes` 都只有 18 字段。前端 `app/src/search/menu.ts:347` 把 20 键的 `config.types` 整体 POST，经 `criterionModel` 指针强转落盘；读回时 `app/src/search/config.ts:198` 又用条件的 `types` 整体替换当前 config。实测 POST 20 键 → GET 18 键，`tabs`/`tabItem` 消失 | 高（本机运行实例实测；挑战门两轮 CONFIRMED） | 已提 issue #19429 |
| 观察项（未过业务表现门槛） | `app/src/protyle/wysiwyg/index.ts:2172` 划选探测的容器类名表含 `callout` 但不含 `tabs`/`tab-item`，而同一调用链 `app/src/protyle/wysiwyg/getBlock.ts:235` 的块级判定含之；因 `elementFromPoint` 基本命中 `.tab-item-content` 内的段落，无法稳定构造输入 → 不上报 | 低 | 附录观察项 |
| 观察项（未过业务表现门槛） | `app/src/protyle/wysiwyg/getBlock.ts:172` `getNoContainerElement` 的容器类名表缺 callout/tabs/tab-item，唯一调用点是面包屑兜底；容器块自身 ID 本就可查面包屑，倾向有意省略 | 低 | 附录观察项 |
| A / F | 机械复扫：重复字面量 136 条（P1 100/P2 16/P3 20）、未转义插值 244 条；逐条核对仍为已知噪声 | — | 未命中 |
| 子代理自验推翻 | `app/src/gutter/index.ts:1926-1978` 列表转换菜单的 `UL2TL`/`OL2TL` 疑似写反 → lute 中两个方法实现逐行相同（都只置 `ListData.Typ = 3`），调用结果等价，推翻；`app/src/protyle/toolbar/index.ts:1262` `indexOf("text")` 疑似 -1 误删末项 → 位于 `types.includes("text")` 的 else 分支且上行刚去重，必 ≥ 0，推翻 | — | 自行推翻 |

### 第八轮的方法论教训

1. **契约迁移把「漏项」从一致性缺陷升级为数据丢失**。同一处漏项在 P4 场景下只是某次判定走错分支，
   一旦 DTO 位于序列化边界且解码用标准 `encoding/json`，就变成「用户显式配置在往返中静默消失」。
   **扫描闭合集合时，把「是否跨序列化边界」作为严重度分级的首要因子。**
2. **指针强转（`(*B)(a)`）是「镜像 DTO」的指纹**。见到它就能断定两侧 struct 必须逐字段同布局同顺序，
   因此写修复建议时必须给出「在等价位插入」这一约束，否则修复本身会引入整体错位的数据损坏。
3. **「写后读键集合守恒」是最省力的不变量**。`len(sent) == len(returned)` 不需要理解语义即可判定真假，
   而且取证成本极低（两次 API 调用），比追完整条前端链路更快。**优先给每条发现找一个键数/计数级别的等式。**
4. **`git log -S <key> -- <file>` 逐文件跑，能一眼看出「同一次改动改了谁、漏了谁」**。
   本轮把这条命令对 6 个候选文件各跑一次，5 秒内定位到 `5b8556e965` 只改了 4 处、漏了 2 处，
   比读 diff 更快。**时间线证据要落成「哪些文件命中、哪些没有」的清单。**
5. **子代理本轮的最大价值是「找到那块没被看过的地」**。第四轮以来首次有子代理产出被正式采纳
   （本轮 2 号子代理给出 3 条候选，主上下文采纳 1 条并实测）。要求其「必须给出权威依据与用户可见路径、
   自我推翻要写明」之后，候选质量明显高于前几轮。**侦察范围要给「未被历史轮次覆盖」的排除清单。**
6. **文档只描述 API 接受面的枚举，不构成「用户可见限制」**。挑战门第二轮的最强反论证是
   `docs/API.md` 只列 18 个键，但同一对话框在 UI 上渲染了 20 个开关——**UI 的承诺强于文档的枚举**，
   且丢失是单向的（写 20 读 18），本地缓存还会被同一次点击写坏。判定「有意设计」时要问：
   这个「有意」是否解释了全部可观测后果？

### 第八轮补记（2026-09-13，主条目之外的追加取证）

1. **类型过滤真实门控结果（把「丢键」升级为「结果变化」）**：在同一运行实例上对
   `/api/search/fullTextSearchBlock` 用同一关键字做对照，`types` 其余 18 键完全相同，仅切
   `tabs`/`tabItem`：`matchedBlockCount` 由 **301（关闭）→ 311（开启）**。
   即丢失这两个键会让搜索结果少掉页签/页签项容器块的 10 条命中，
   **不是纯展示差异**，而是「保存的条件不能复现保存时的结果集」。
2. **同一契约内的严格度不对称（P15 新增检查点）**：`apicontract.Criterion.SubTypes`
   （`kernel/apicontract/criterion.go:71-75`）是 `map[string]bool`，未知键在往返中被**保留**；
   同一请求里的 `Types` 是 struct，未知键被**丢弃**。
   → 「宽松解析」不是一条被声明的契约原则，而是 struct/map 选择的副作用；
   同一个载荷里两个字段的保真度不同，这正是漂移能长期不被察觉的原因。
   检查闭合集合 DTO 时，**优先怀疑 struct 型（而非 map 型）成员**。
3. **零副作用的复现脚本（三次 API 调用）**：
   1. POST `/api/storage/setCriterion`，`criterion.types` 带 20 个键（含 `tabs`/`tabItem`）
   2. POST `/api/storage/getCriteria`，该条件 `types` 只剩 18 个键
   3. POST `/api/search/fullTextSearchBlock` 两次（仅切这两个键），比较 `matchedBlockCount`
   最后用 `/api/storage/removeCriterion` 删除测试条件，工作区恢复原状。
   **写入型缺陷也可以做到零残留取证**：关键是「写入 → 回读 → 删除」三步同轮完成并回读确认删除。
4. **文档枚举会随契约生成物一起被「冻结成看似有意」**：`docs/API.md:2824`、
   `API.zh-CN.md:2779`、`API.ja.md:2761` 三语版都精确列出 18 个键，`kernel/apicontract/schema.json`
   与生成的 `app/src/types/api/index.d.ts:147,149` 也是 18 个。
   契约迁移（`debc9a74cb`，2026-09-13）晚于页签特性（`5b8556e965`，2026-09-05），
   于是把漏项**复制进了文档与生成物**。判定权威侧时不能把「生成物/文档也这么说」当作独立证据——
   它们与 DTO 同源，只能算同一份证据的多个副本。5. **列举同一集合的副本时，别漏掉 CLI flag 帮助文案**：同一「搜索类型过滤」集合实际有 **12 处副本**，
   本轮新增的一处是 `kernel/cli/cmd/search.go:217` —— `--type` 帮助文案枚举 18 个类型名，
   但 `--type` 值经 `stringSliceToMap` 直通 `model.FullTextSearchBlock`，
   `buildTypeFilter`（`kernel/model/search.go:2061`）读 `types["tabs"]`（`:2089`）与
   `types["tabItem"]`（`:2090`），故 `--type tabs` 实际生效、只是 `--help` 里看不到。
   **这类副本「行为正确、仅可发现性受损」，极易被判为不可达而跳过**，
   但它的修法与 DTO 漏项同源（补一处枚举），应并入同一条目而非另开一条。
   同轮清点：`conf/search.go`(20) / `getDefault.ts`(20) / `search/menu.ts`(20) /
   `config/tabs/searchTab.ts`(20) / `config.d.ts` 两个 interface(20) 为完整副本；
   `model/storage.go` / `apicontract/criterion.go` / `schema.json` / `api/index.d.ts` /
   三语 `docs/API*.md` / CLI 帮助文案共 8 处为 18 键残缺副本。
6. **「缺失副本 + 无回填」共同决定丢失是否持久**：`app/src/protyle/util/compatibility.ts:837`（`replaceTypes`）
   与 `:842`（`subTypes`）都有历史回填，`types` 没有。因此点击条件写入 `LOCAL_SEARCHDATA` 的 18 键版本
   **不会被本地缓存层修复**。注意这一条本身不是缺陷（新增类型默认未勾选与 `conf.Search` 默认值一致），
   它只是「丢失持久性」的证据 —— **同一 feature 内兄弟字段有回填而它没有，是判断丢失能否自愈的关键**。
### 第九轮（2026-09-13）：架构层定向扫描

本轮任务与前八轮不同：用户明确要求「扫描出一个**明确架构设计上的缺陷**（不是具体代码层面）」。
结果是**一条降级保留的发现 + 一个被排除的候选**。

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| A / D3 / G1（新 P16） | 内核本地化消息以**整数下标**为身份（396 条 × 21 语言），格式契约（131 条带占位符）只隐含在译文副本里；无载体（AGENTS.md 未提占位符）、无表达能力（显式实参索引 `%[n]` 全量 0 次使用）、无有效校验（键集合门对无义整数退化为存在性；译文门 `sorted()` 抹顺序、正则 `%[sdf]` 漏 `%v`、无 `exit(1)`、不在 CI）。实测已漂移 10 处：hi/ko/tr 的 89/90/234 换位 → `%!s(int=3)`/`%!d(string=…)`；ar 的 210 丢 `%v` → `%!(EXTRA int=7, int=9)` | 高（Go 探针实跑 + 21 文件全量比对 + 两道门实跑） | 已提 issue #19430（严重度低） |
| — | 候选：API 契约层是否有旁路。**排除**：`kernel/api/contract_test.go:59` `TestAPIContractRouterCoverage` 对 gin 实际路由与「apicontract 声明 + legacy 清单」做**双向**覆盖断言，`kernel/apicontract/contract_test.go:172` `TestRouteCoverage` 额外断言「新无类型路由被拒」「handler 绑错契约被拒」，`TestGeneratedArtifacts`（`:203`）断言 TS 声明与 schema 与生成器同步——该层无缺口 | 高 | 排除，不报告 |
| C / D1 | 机械复扫与状态保持类未取得新的可判定发现 | — | 未命中 |

#### 第九轮的方法论教训

1. **「架构级」定性必须过挑战门，而且往往会被降级**。第一轮把候选定性为「架构缺陷（无名字的整数跨 4 个边界且无契约载体）」，
   第二轮维护者反驳成立并推翻该定性：位置编号在**同一发布内由同一份物理文件**保证「同号同义」，
   它是 append-only ID 空间（与 `AGENTS.md` 第 9 条的 `data-id`/`data-type` 同一哲学），
   而且**从未有一例「同号不同消息」**——失效的只是与身份正交的格式维度。
   最终裁决 DOWNGRADED：真实、用户可见、可修，但不是「身份方案有缺陷」。
2. **区分「标识符自洽」与「契约完整」**。身份方案自洽不等于契约完整；
   报告必须把「身份」与「格式契约」拆成两件事，否则维护者一句「这个设计是有意的」就能整体驳回（本轮实际发生）。
   已固化为 P16 的三件套诊断：**载体 / 表达能力 / 校验**，缺任一则不成立。
3. **「契约无法表达副本的合法需求」是本模式最硬的支点**。
   本轮的决定性证据不是「有 10 处漂移」，而是「21 个语言文件里显式实参索引 `%[n]` 出现 0 次」——
   译者在语序与基准不同时除了换位无路可走，因此 3 种语言独立地都换位，这是**系统性倾向**而非笔误。
   同理，若发现契约提供了出口（如 `%[3]s` 被实际使用），应立即降级为作者失误。
4. **校验门要看「判据字段与被保护对象是否同维度」**。
   `check-lang-keys.py` 本身实现正确、且有 CI 之外的项目约定要求跑它，
   但它的判据是**键名集合**，而被保护对象的键名是无义整数 → 门退化为「条目数比对」。
   **一个正确的门保护错维度，等价于没有门**，且更难被发现（因为「有校验」这个事实会劝退审计者）。
5. **同文件内的对照块是最省力的反证**。同一份 lang 文件里另外 5 个块（`replaceTypes`/`_time`/`_taskAction`/`_trayMenu`/`_attrView`）
   全部用符号键，且被同样的内核与前端消费 —— 一句话排除「语言/框架限制」与「有意统一用整数」两种解释。
6. **实跑格式化比推导更有说服力**。用一个独立的小 Go 程序（仓库外临时目录，`go run`，不编译内核）
   读取**真实语言文件**并复刻**真实调用形状**，直接打印出 `%!s(int=3)`；
   同轮还实跑了两个校验脚本（`check-lang-keys.py` 退出码 0；`check-translations.py` 报 385 条却**不含**目标 4 个下标），
   把「门失明」从推断变成实测。**注意 `check-translations.py` 在 Windows 默认 GBK 控制台会因 emoji 抛 UnicodeEncodeError，需设 `PYTHONIOENCODING=utf-8`。**
7. **子代理的价值在「找到没被看过的地」**。本轮 2 号子代理补出了两个我没覆盖的事实：
   前端 TS 侧 88 处 / 39 文件硬编码同一套整数、以及 Electron 宿主页面（`app/electron/connections.js`）是第 5 个边界；
   1 号子代理则顶住压力给出了降级理由。**两轮都用全新子代理**是这条机制生效的前提。
8. **本轮把「既有发现登记表」当过滤集用满了**。开扫前先读了 `references/evidence.md` 的历轮表与仓库 memory，
   排除了同步忽略规则、`statTypesByPath`、`.aac`、`getAssetName`、`av/calc.go` 恒真守卫、缩略图恒假守卫、
   `IsContainerType` 漏 `tab`、搜索条件 DTO 丢键这 8 组——本轮**零重复报告**。
   先前几轮只核过「键完整性 / 索引越界」，故本条不属于重复。

### 第十轮（2026-09-13）：架构层定向扫描（跨仓公开类型契约）

本轮同样是「非代码层面」的定向扫描，命中一个**跨仓契约**缺口。

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| A / D3 / G1（新 P17） | 插件公开契约 `TOperation`（petal 的 npm 包 `siyuan`，经 `petal/types/protyle.d.ts:316 protyle.transaction(...)` 消费）是 `app/src/types/index.d.ts` 同名联合类型的手工镜像，仓内**无任何子集断言**；`AGENTS.md` 明文要求同任务同步 petal，实测积压 **15 项**（2026-06-16 → 2026-09-04），而 petal 仍在主动增补（2026-08-24 两项）→ 积压而非冻结；第二维是 `IOperation` 的 `cellUpdates`/`viewIDs` 载荷字段也缺 | 高（三方成员集合与差集实测、生产者逐条定位、两侧 git 历史核对；挑战门两轮分别 CONFIRMED / DOWNGRADED 至低） | 已提 issue #19432（严重度低） |
| — | 候选：内核→前端 WS 推送命令集是否有双向漂移。**排除**：机械提取 70 个内核推送 cmd 与前端 396 个句柄字面量做双向 diff，仅 `updateids` 无前端 `case`——但它由 `emitToPlugins("ws-main", data)` 原样转给插件（issue #13434 的原意即「给插件用」），非缺口。**本轮的教训：前端分派大量使用 Yoda 写法 `"msg" === response.cmd`，只 grep `case` 会造出大批假漂移**（首版脚本报 9 条，修正后仅 1 条） | 高 | 排除，不报告 |
| — | 候选：AV 定义存放在笔记本容器之外（普通库全局 `data/storage/av/`、加密库 `<boxID>/storage/av/`），归属只能靠进程级 `pendingAVBox` + 磁盘探测推断。**排除**：跨加密边界的守卫极完整（`IsSameCryptoBoundary` 覆盖文档移动、块移动、块引、资源、AV 镜像、关系共 47 处），且「加密笔记本是资源孤岛」在两处有显式注释 | 中 | 排除，不报告 |
| A / F | 机械复扫：重复字面量 153 条（P1 117 / P2 16 / P3 20）、未转义插值沿用历轮阈值；逐条核对仍为已知噪声（`assets/`、`/api/` 受类型约束路由、CSS 选择器、`conf.json`） | — | 未命中 |

#### 第十轮的方法论教训

1. **子代理纠正了我两处承重事实，其中一处本想当作主证据**。我以为「第 4 处副本（`apicontract` 的 9 项 `enum=`）与内核 96 项同集合」——子代理指出 `kernel/api/contract_block_transaction.go:15` **显式拒绝 AV 载荷**（`operation.Srcs != nil || len(operation.CellUpdates) > 0`），该 enum 属标题转换端点的载荷域，不含 `setAttrView*` 是设计正确。另一处：petal 的 `TOperation` 在 2026-08-24 仍被增补了两项，我「9 个月未同步」的说法不成立。
   **教训：跨仓/跨作用域的集合配对，必须先确认两侧「消费域相同」再 diff 成员**，否则成员数差异会被读成漏项。已写入「已知误报」。
2. **机械提取前端分派时必须覆盖 Yoda 写法**。首版脚本只抓 `case "..."`，报出 9 个「无前端处理」的内核 cmd；补上 `"x" === cmd` 形式后只剩 1 个（且经查为插件通道）。**「差集很大」要先怀疑提取器，而不是先立论。**
3. **历史轮次的「排除清单」本身就是资产**。本轮开扫前先读登记表，直接跳过同步忽略规则、`statTypesByPath`、`.aac`、`getAssetName`、`calc.go` 恒真守卫、缩略图恒假守卫、`IsContainerType` 漏 `tab`、搜索条件丢键、i18n 契约 9 组，零重复报告。
4. **「有生成器」不等于「覆盖该集合」**。本仓 `apigen` 已有「声明 → 生成 → `TestGeneratedArtifacts` 断言」的成熟模式，且它也写 petal——但唯一写入是 `petal/types/api/index.d.ts`（`kernel/apicontract/cmd/apigen/main.go:85-86`），**完全不碰 `siyuan.d.ts`**。查「是否存在自动化修复机制」时必须读到**写入路径的具体行**，不能停在「有生成器」。
5. **不变量要取单向子集，不要取相等**。本轮的不变量最终定为 `petal.TOperation ⊆ app.TOperation`：内核 `switch`（96）与 app 的 `TOperation`（94）**本来就不等**（`create` 仅内核内部建文档树、`updateAttrs` 仅内核下推给前端，见 `kernel/model/blockial.go:544` + `app/src/protyle/wysiwyg/transaction.ts:947`）。**先找出合法非对称成员，再写不变量**，否则修复方案会把它们判成假阳性。
6. **严重度由「权威侧是否承诺稳定」定档**。本轮决定性降级依据是 `docs/API.md:139` 明文把 `/api/transactions` 操作列为内部实现、不承诺兼容性，`docs/API-CONTRACTS.md:91` 又说明跨仓同步不进入 CI。**判定「应补全」前先找反向声明**；找不到反向声明的「应补全」只是审计者意见。
7. **运行时无兜底分支会让「声明漏项」仅停留在类型层**。内核 `switch op.Action` 无 `default:`（事务开关在 `kernel/model/transaction.go:466` 闭合，`ret` 保持 nil）→ 未知 action 静默 no-op。因此本轮的后果**必须**限定为「伪造编译错误」，不能写成功能阻断。**审计「闭合集合漏项」时要分开写「声明层后果」与「运行层后果」。**
8. **零副作用的取证方式：只读跨仓对比**。本轮全程未写入任何工作区数据，未建临时文档、未调写接口；机械脚本与比对脚本都放在仓库外 `%TEMP%\audit-r10\`。**跨仓契约类审计天然可零副作用完成。**

#### 第十轮提交记录

- 已提 issue #19432（state=open，标题与正文经逐字符回读校验一致：title 完全相等、body 2521/2521）
- 写入流程：临时 payload 置于系统临时目录（`siyuan-gh-issue-20260913-tooperation.json`），`gh api --method POST` 不带 `--jq`，
  随后与 payload 逐字比对；已删除 payload 与全部临时物并确认不存在
- 仓库内零残留（`app/pnpm-lock.yaml` 的改动非本轮产生）
- **本机坑（新增）**：PowerShell 5.1 的 `>` 重定向默认写 **UTF-16LE**，Python 以 `utf-8-sig` 读会报 `UnicodeDecodeError: byte 0xff`。
  回读 `gh api` 输出时要么用 `Out-File -Encoding utf8`，要么按 `encoding='utf-16'` 读取

### 第十一轮（2026-09-13）：汇总列「已完成占比」量纲与格式漂移

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1 / B（新 P18） | 数据库汇总列（rollup）的 `Percent checked` / `Percent unchecked` 算成了裸整数：`kernel/av/value.go:3167`/`:3179` 的 `(*ValueRollup).calcContents` 用 `float64(countChecked*100/len(r.Contents))` + `NumberFormatNone`（赋值 `:3177`/`:3189`）；而同 switch 的三个兄弟分支（`:2824`/`:2834`/`:2846`）与**同一算子的另一条路径** `calcFieldCheckbox`（`kernel/av/calc.go:1654-1679`）都用比值 + `NumberFormatPercent`。`formatNumber`（`:2247`）对 Percent 会乘 100 并补 `%`，故错误分支是「先乘 100 再不打百分号」。业务表现：汇总列选「已完成占比」，2/3 显示 `66`（应 `66.67%`），**1/200 显示 `0`**（应 `0.5%`，整数除法截断）。渲染链 `kernel/sql/av.go:816` → `BuildContents` → `calcContents`，前端 `attributeValue.ts:78` / `cell.ts:1387` 直出 `formattedContent`，无二次归一化 | 高（代码可证 + 同包两处权威侧对照；挑战门两轮 CONFIRMED / 第二轮把严重度收窄至低） | 已提 issue #19435 |
| A / F | 机械复扫：重复字面量 153 条（P1 117 / P2 16 / P3 20）、未转义插值 244 条 / 95 文件；逐条核对仍为已知噪声（`assets/`、`/stage/loading-pure.svg`、受 `app/src/types/api/index.d.ts` 约束的 `/api/` 字面量、`conf.json`、CSS 选择器、`z-index` 插值） | — | 未命中 |
| 子代理候选（未通过本上下文取证或挑战门） | `kernel/model/export.go:1898` PDF 书签 `bms[h.ID]` 无 `ok` 判断（兄弟分支 `:1886` 有）；`kernel/model/import.go:2240` 图片 `title` 建 `NodeLinkTitle` 时未写 `Tokens`（`<a>` 分支 `:2300` 有）；`kernel/model/carddav.go:625` 多卡 vCard 拆分时 map key 用循环不变量 `path.Base(filename)`；`kernel/model/template.go:156` 对必为空的 `ret` 排序；`app/src/protyle/render/av/col.ts:723` 列名未 `escapeHtml` | 中 | 附录观察项，未核 |
| 已核实为误报/已存在覆盖 | `SetAssetHash` 的 `assets/` 守卫（调用点均传 `assets/` 前缀）、agent SSE 事件集（内核 14 个 emit 与前端 16 个 `case` 双向覆盖）、`SiYuanAssetsImage` 缺 `.tif`（第三轮已登记为观察项）、`query_embed` 六处引用 | — | 不报告 |

#### 第十一轮的修复影响面（实测，供修复者参考）

用户追问「改数据类型吗 / 影响模板字段吗 / 补百分号会怎样」，逐项取证如下。

**类型层零改动**：列类型仍是 `number`（`kernel/av/value.go:3177` 写死 `Type: KeyTypeNumber`），JSON 结构与前端 `IAVCellValue.number`（`app/src/types/index.d.ts:1521-1525`）都不变，`"percent"` 本就是数字列的合法格式（`AttributeViewKeyNumberFormats` 含之）。变的只是三个字段的值：`content` 33→0.3333、`format` `""`→`"percent"`、`formattedContent` `"33"`→`"33.33%"`。

**补 `%` 必须与量纲同时改，三者实测对照**（用临时数字列在真实实例上跑，测完已删）：

| 改法 | 数值 | format | 实际显示 |
|---|---|---|---|
| 只补格式、不动量纲 | 33 | percent | `3300%`（灾难：`formatNumber` 会再乘 100） |
| 只改量纲、不补格式 | 0.3333 | 空 | 数字列显示 `0.3333333333333333`；汇总路径按 `%.5f` 分支约为 `0.33333` |
| 两者同时改 | 0.3333 | percent | `33.33%`（正确） |

结论：分母里的 `*100` 本身就是多余的，正解就是 `calcFieldCheckbox` 那样「比值 + `NumberFormatPercent`」，乘 100 与补 `%` 都交给格式化函数。

**模板字段受影响，且补 `%` 对它无效**：`kernel/sql/av.go:421` 把汇总的 number 值以 `[]float64` 放进模板 dataModel，取的是 `content.Number.Content`（原始值），完全不读 `formattedContent`。实测：模板内容 `.action{.勾选占比}` 现在输出 `[33]`，改成比值后输出 `[0.3333333333333333]`；`.action{.勾选占比_str}` 现状即为 `<no value>`（rollup 分支不提供 `_str`）。要让模板也可读，得在 dataModel 构建处单独处理，这不属于「改两行」的范围。

**其余消费点**：
- 筛选受量纲影响：`kernel/av/filter.go:1086` 用 `number.content` 直接比大小，0-100 改 0-1 会让用户已设好的百分比阈值失效（写 `> 50` 将永不成立）
- 列底部 Sum/Average 显示变化：`kernel/av/calc.go:1772` 起求和读原始 `content`，而汇总列不能设置数字格式（`kernel/model/attribute_view_key_config.go:68`），3 项相加会从 `99` 变成 `0.9999`
- 排序不受影响：`kernel/av/sort.go:452` 读同一个 `content`，乘 0.01 是单调变换
- 无需数据迁移：`Rollup.Contents` 虽会写盘（`CloneStoredValue` 只剥离 `RenderedContent`，`kernel/av/render_template.go:25`），但每次渲染由 `BuildContents` 重算并置空（`kernel/av/value.go:2663`）

**复现夹具（用户工作区，非仓库内）**：文档 `/db test 2`，两个数据库分别演示「截断」（3 行勾 1 行 → 页脚 `33.33%` vs 汇总 `33`）与「归零」（103 行勾 1 行 → 页脚 `0.97%` vs 汇总 `0`），并把复选框列的页脚计算设为同一算子做同屏对照。

**已提 issue #19435**（state=open；title 74/74、body 1549/1549 逐字符回读一致；labels 被静默丢弃，符合已知权限限制）

## 第十二轮（2026-09-13）：机械复扫 + 三个未覆盖区域的子代理侦察

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1d（新 P19） | `kernel/model/carddav.go:398`（`LoadAndDelete` 无 `else`）→ `:411` `os.RemoveAll(addressBook.DirectoryPath)`；`kernel/model/caldav.go:331` → `:344` 逐字同构。同族的 `DeleteAddress`/`GetAddressBook`/`DeleteObject`/`GetCalendar` 都有 not-found 分支且常量已存在；上游 `go-webdav@v0.7.0` 按**路径深度**分派、无存在性预检；panic 被 `model.Recover` 吞掉后 `net/http` 补 **200** | 高（实测复现 + 栈帧逐帧核对，`caldav.go` 那条为静态可证） | 挑战门两轮 CONFIRMED，第二轮 DOWNGRADED 至低严重度；已提 issue #19439 |
| A / F | 机械复扫：重复字面量 **166** 条（P1 130 / P2 16 / P3 20，文件数 1360）、未转义插值沿用历轮阈值；逐条核对仍为已知噪声（`assets/`、`/stage/loading-pure.svg`、受 `app/src/types/api/index.d.ts` 联合类型约束的 `/api/` 路由、CSS 选择器、`conf.json`、`0.38`、`INPUT`/`SPAN` 等 DOM 名） | — | 未命中 |
| 候选（未取证） | `kernel/model/flashcard.go:815-828`：`custom-riff-new-card-limit` 解析失败时 `strconv.Atoi` 把 **0** 写进 `newCardLimit`，而 0 在 `getDeckDueCards` 里是最严格值 → 该文档复习时新卡全部消失，只有一行 `invalid ... limit` 日志；同仓其它非法配置一律回落默认 | 中高 | 附录观察项 |
| 候选（未取证） | `kernel/model/flashcard.go:560-570`：卡片管理排序比较器混用 Due 与 ID 两把键，不满足严格弱序，入参来自 map 遍历（每次顺序随机）→ 混合新卡/旧卡时分页可能重复或漏卡 | 中 | 附录观察项 |
| 候选（未取证） | `kernel/model/template_doc_tree_render.go:295`：重生成块 ID 后未调 `treenode.RemapTabsActiveIDs`/`WalkWithTabTitles`，而 `tree.go:102`、`import.go:666`、`template.go:1010` 三处同构实现都调了（全仓仅 4 个调用点） | 中 | 附录观察项 |
| 候选（未取证） | `app/src/asset/renderAssets.ts:67-85`：`genAssetHTML` 的 audio/image/video/a 分支裸插 `pathString`，而同文件 `renderAssetsPreview` 与安全公告修复 `2229686df9` 覆盖的 `asset/index.ts` 都转义了；Windows 文件名限制使其不可达 | 中低 | 附录观察项 |
| 子代理自验推翻 | 候选 4 条：`carddav.go:625` 多卡 vCard 用原文件名做 key（可达性需手工放文件，且重启自愈）、`export.go:4830` 把行 ID 当定义块 ID 写入 `defBlockIDs`（当前无可见后果）、`export.go:1580` 聚焦导出对页签项丢容器（GUI 传文档 ID 不可达，仅 MCP/API 可达）、`publish_access.go:1717` 用 `passwordID` 作守卫（遍历可达状态后确认不可达） | 中 | 自行降级，未上报 |

### 第十二轮的方法论教训

1. **「同族方法只有一个缺守卫」是 D1 的独立高点位**。本轮不必先证明可达性：同文件四个兄弟方法都有 not-found 分支、
   两个常量已定义却无人使用，**自相矛盾本身就是强证据**（与第七轮「同包自相矛盾」同一手法，但范围缩小到一个文件内）。
   `if ...; loaded { x = v }` 缺 `else` 是这类缺陷的机械指纹，可脚本化。
2. **「有 recover 中间件」不是安全网，而是缺陷的隐身衣**。第五、六轮分别确立了恒真/恒假守卫；本轮补上第三条：
   **panic 被吞掉后 `net/http` 补 200**，使「无法处理的请求」表现为成功。审计「panic 是否等于崩溃」时，
   必须读到 middleware 的 `recover()` 之后**有没有写状态码**，而不是停在「有 recover 就没事」。
3. **「不得 panic」不需要外部规范背书，「应返回 404」需要**。挑战门第一轮推翻了我误引的 RFC 4918 §9.6
   （它只规定成功 DELETE **之后**的 GET 返回 404），第二轮又推翻了我「404 不可表达」的断言
   （根包 `go-webdav@v0.7.0/server.go:50` 已导出 `NewHTTPError`）。**推断链的每一环都必须读源码**，
   否则「预期表现」这一栏会变成审计者自造的权威。已把这一类写成新误报。
4. **修法不能照抄兄弟路径**。本例兄弟路径返回普通 `errors.New`，经上游 `ServeError` 映射为 **500**；
   若照抄，报告自己援引的「幂等重试」场景反而从「200（无害）」变成「500（客户端持续重试）」。
   **挑战门在收窄严重度的同时，还阻止了一次会让缺陷变严重的修复**——这是它的第二个价值点。
5. **拒绝型缺陷是最省力的取证目标**。`DELETE` 不存在的路径预期失败，panic 发生在全部变更动作之前，
   因此可以在真实工作区直接实测，无需建临时对象再回删。第七轮的 `append(parentID=页签项)` 也是同一形态。
   **选复现场景时优先挑零副作用的那个。**
6. **零副作用不等于零痕迹**：本次请求触发了该工作区**首次** CardDAV 访问，`load()` 顺带初始化了
   `data/storage/carddav/principals/main/contacts/address-books.json` 与空 `default/` 目录（内容仅默认地址簿）。
   这是任何一次 DAV 访问都会产生的正常行为，但审计时应在报告中披露，避免被误当成缺陷或残留。
7. **子代理产出仍是候选**：本轮 3 个子代理共给出 12 条候选，主上下文采纳 1 条并实测，4 条经自验降级/推翻。
   有效的做法是给它们**历轮排除清单**并强制「必须给出权威依据与用户可见路径、自我推翻要写明」。
8. **skill 仓库出现工作树回退事故（本轮发现）**：`SKILL.md`/`references/evidence.md`/`references/patterns.md`
   三个文件的工作树被回退到**第十一轮之前**的状态（第十一轮的 D1c、P18、各轮 issue 编号全部丢失，
   `git diff` 表现为 138 行删除）。`HEAD`（`24a3e6f`）与 `origin/main` 一致且内容完整，
   已备份工作树后用 `git checkout -- .` 恢复。**教训：每轮开扫前不仅要读登记表，还应确认登记表本身是最新的**——
   本轮若不是先读 `evidence.md` 再核对工作树，会基于残缺的判据库做去重，重现第八轮的重复报告。
   备份留在 `%TEMP%\skill-bak-r12\`，确认无误后删除。

## 第十三轮（2026-09-13）：前端定向扫描（app/src）

范围：`app/src` 全量前端（770+ TS 非测试文件）。机械复扫：重复字面量 64 条（P1 44/P2 5/P3 15，files 778）、
未转义插值 244 条/95 文件，逐条核对后除下述条目外均为噪声（UI 选择器、ID、i18n 文本、内部 HTML 片段）。

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1e / C（新 P20） | `app/src/protyle/render/av/kanban/render.ts:128` 读 `searchInputElement?.value`（该元素是 `genTabHeaderHTML` 生成的 `contenteditable` div，无 `value`），同族九处读 `textContent` → 看板视图搜索恒不过滤；全量重渲时 `showSearch` 为假 → 搜索框被折叠清空 | 高（代码可证；挑战门两轮 CONFIRMED，严重度中） | 已提 issue #19440 |
| A / D3（新 P21） | `app/src/config/entryVisibility/catalog.ts` 与实际菜单声明 4 处不一致：漏 `transposeTable`/`cancelMerged`/`copyMirror`/`inline.image.openBy`；`inline.text.more` 与 `gutter.multi.copy` 含永不出现的幽灵键。违反 `AGENTS.md` 第 9 条 | 高（挑战门两轮 CONFIRMED，严重度低） | 已提 issue #19441 |
| B / D1（新 P22） | `app/src/mobile/menu/search.ts:319-330` 的 `searchParam` 缺 `searchHPath: !hasReplace`（桌面 `search/util.ts:1520` 有；内核默认 true；同一提交 `fa44649fa7` 把 `FindReplaceInBox` 改为 `false`，两者本是一对）→ 移动端替换模式列表多出仅命中 HPath 的行 | 高（挑战门两轮 CONFIRMED，严重度由「数据差异」DOWNGRADED 为低） | 已提 issue #19442 |
| D1 | `app/src/mobile/util/setEmpty.ts:42` 只读判据方向反了（`getOpenNotebookCount() > 0 \|\| !readonly`）→ 发布/读者角色在移动端空页看到「新建文档」，点击必然 403（提示未本地化 "Forbidden"）；同屏另 3 项、移动端菜单、桌面端共 5 处均隐藏 | 高（挑战门两轮 CONFIRMED，严重度低） | 已提 issue #19443 |

### 已审查并驳回

- 「移动端主文件树未响应 `fileTree.docIconClickExpand`/`parentDocClickExpand`」：这两个设置项在
  `app/src/config/tabs/fileTab.ts` 被 `/// #if !MOBILE` 编译剔除，移动端本无此设置；`PinnedDocs` 的 `this.mobile || …`
  是显式的平台区分。属有意设计，已写入「已知误报」。
- `app/src/sync/syncGuide.ts:115/119/121` 云端目录名未转义：`dejavu.cloud.IsValidCloudDirName`
  拒绝 `"`、`<`、`'` 等字符，正常路径下列不出该形态的名字（仅当用户在自己云盘外部创建了非法目录名才可达），
  且影响限于自己的远端目录，降为观察项。

### 未取证候选（勿重报，除非有新证据）

- `app/src/protyle/util/compatibility.ts`：保存侧对 `LOCAL_SEARCHDATA`/`LOCAL_FILESPATHS`/`LOCAL_CLOSEDTABS` 都调 sanitizer，
  加载侧只对 closedTabs 调 → 存量未脱敏 storage 可被还原（需跨版本/跨客户端写入前提）。
- `app/src/config/tabs/syncUi.ts:414-435`：保存响应 `.finally` 用服务端快照逐字段回填整个第三方存储表单，
  无 `editing`/revision 守卫（对比 `bodyGradient.ts:12-18`、`keymapUi.ts:717-750` 的做法）。
- `app/src/boot/globalEvent/keydown.ts:190` 与 `keyup.ts:79` 的 `getFullHPathByID` 回调无 reqId/版本校验
  （对比 `util/fetch.ts:22-24` 的 `reqIds` 白名单）；`app/src/protyle/hint/extend.ts:482` 的 `searchTag` 同理。
- `app/src/editor/databaseRow.ts:63` 行窗口 body 整体 `replaceWith`，无「单元格有焦点则延后」判断
  （对比 `BacklinkContent` 的 `markDirty()` 延后刷新）。
- `app/src/mobile/dock/MobileFiles.ts:1467-1495` 的 `selectItem` 缺桌面版 `Files.ts:1993-2017` 的路径归一化与
  `visitedPaths` 防死循环（未构造出稳定可达路径）。
- `app/src/protyle/gutter/index.ts:153`（`*Block` 系）与 `app/src/protyle/wysiwyg/backlinkTypeFold.ts:3`、
  `app/src/protyle/render/av/richText.ts:124`（短名系）是同一块类型闭合集合的三份副本；`langs/*.json` 中
  `HTML`/`IFrame` 键不存在，反链折叠按钮回退显示英文（可能是有意保留英文名，故仅记录）。

### 方法论教训

1. **子代理的「跨端/跨实现差异」候选必须回到同一端内找自相矛盾**。本轮驳回的移动端文件树候选，
   子代理的内部矛盾论据（PinnedDocs 会展开）看似有力，实则被 `/// #if !MOBILE` 编译块解释掉。
   **跨端对比前先 grep 编译期保护块**，否则会把有意的平台区分当成漏实现。
2. **`git log -S <x> -- <path>` 的 `--stat` 只统计该路径**，本轮据此误判为「1 file changed, 1 insertion」，
   实际提交改了 6 个文件（含内核配套改动）。要判断「是否只改了一侧」，必须不带 pathspec 看完整 diffstat。
3. **挑战门能纠正业务表现的因果链**：本轮 D1e 最初写成「打字时输入被清空」，实际 `renderAll=false` 时
   `afterRenderGallery` 提前 return，输入不会被吃；清空只发生在 `renderAll=true` 的重渲。症状描述错了会直接影响修法与优先级。
4. **「前端列表」≠「服务端作用的集合」**：P22 最初被描述成「替换目标集不一致」，实际替换目标由内核
   `FindReplaceInBox` 内决定，前端字段只影响列表与计数。**断言数据层后果前先读服务端的取数实现。**
5. **机械扫描的增量仍然为 0**：64 条重复字面量与 244 条未转义候选全部为噪声/已知项，
   本轮四条发现全部来自**定向语义核查**（判据 D1/D3）而非脚本产出——与第十一、十二轮结论一致。

## 第十四轮（2026-09-13）：布局 / 宿主 / 历史 / AV 定位

范围：`app/electron/`、`app/src/window/`、`app/src/layout/`、`app/src/history/`、`app/src/sync/`、
`app/src/protyle/render/av/` 的虚拟滚动与定位。四个只读侦察子代理 + 主线逐条取证，五条主报告条目全部过两轮挑战门。

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1g / E2（新 P25） | `app/electron/boot.html:562` 与 `init.html`/`workspace.html` 共用的 `connectionEntry.js`，在 boot 窗口因 `createBootWindow`（`main.js:2368-2370`）缺 `nodeIntegration` 而抛 `ReferenceError`（Electron 44 下无 `require`）→ 远端内核模式下「连接远程内核」按钮永不渲染，取消/换服务器入口失效 | 高（挑战门两轮 CONFIRMED，严重度中） | 已提 issue #19446 |
| D4（新 P23） | `app/src/layout/Wnd.ts:955` 已关闭页签栈裁剪端方向反了（消费端 `pop` 取最新，裁剪端也 `pop`），且裁剪在 `push` 之前 → 稳态长度 65，超过 64 条后每次关闭挤掉「上一次关闭」；⇧⌘T 第二次起跳序 | 高（挑战门两轮 CONFIRMED，第二轮由中降为低） | 已提 issue #19447 |
| C（新 P26） | `app/src/protyle/render/av/locate.ts:368-370` 定位到折叠分组只改 DOM 不写状态，且 `finishAVLocate` 无条件清理请求 → 任意 AV 数据操作触发的重渲会把分组折回、目标行与光标一起消失 | 高（挑战门两轮 CONFIRMED，严重度中） | 已提 issue #19448 |
| C / D1f | `app/src/layout/dock/index.ts:308` 同一表达式写两遍（第二个 `elements[0]` 应为 `elements[1]`）→ 下半组实现 `resize` 的插件停靠面板收不到通知、上半组被调用两次 | 高（挑战门两轮 CONFIRMED，严重度低，可顺手修） | 已提 issue #19449 |
| C | `app/src/history/diff.ts:485-492`「交换对比方向」只重渲 header 与侧栏（`genHTML`），editors 子面板初始 `fn__none` 且不调 `renderCompare`，选中态也不回填 → 对比区空白、高亮丢失 | 高（挑战门两轮 CONFIRMED，第二轮由中降为低） | 已提 issue #19450 |

### 方法论教训

1. **挑战门第二轮连续纠正了三处严重度与因果**：`Wnd.ts` 的「每次关闭都丢一条」实为「超过 64 条后才丢」（受 `length > SIZE_UNDO` 守卫）；
   `dock/index.ts` 的「每个停靠区有上下两组」与 DOM 不符（左右停靠区实为 3 个 `.dock__items`，第 3 个属底部栏）；
   `history/diff.ts` 的「必须重新点文件」漏了方向键也能恢复（`keydown.ts:54` 合成 click）。
   **症状描述错会直接影响修法与优先级**，第二轮不是形式。
2. **「有意的临时态」与「缺少载体」要分开写**。P26 的候选最初写成「补写 `groupFolded` 与缓存即可修复」，
   第二轮指出这是错的：该字段随 AV 持久化、跨端同步，写回等于替用户永久改偏好。修法描述错了比不写修法更糟。
3. **不要把「调用两次」当成无害**。`dock/index.ts` 同时存在「漏一组」与「重复一组」，两者都要写出；
   只写前者会让人以为修法是补一行而忽略重复调用的副作用。
4. **新增机械可查的形态**：P24（同一行重复同一表达式）可用 grep 穷举，本轮首次把它形式化；
   同族陷阱 `splice(indexOf(x), 1)` 在未命中时删末尾，需先证可达性。
5. **已驳回/观察项**：`app/src/layout/getAll.ts:64-113` 的 `models.inbox` 恒为空数组（无消费者，已写入「已知误报」）；
   `app/src/layout/dock/Inbox.ts:123/129` 的 `splice(indexOf(x), 1)` 在未命中时删末尾（渲染与数组同源，未证可达）；
   `app/src/history/doc.ts:27-84` 的 `renderDoc` 无在途守卫与请求序号（同族 `renderRepo` 有 `data-loading`）；
   `app/src/history/diff.ts:433-436` 对比用的 Protyle 从不 `destroy()`（同族 `docDiff.ts:163-169` 会销毁）；
   `app/src/history/history.ts:834` 展开日期无在途标记，快速重复点击会插入两个 `<ul>`；
   `app/src/protyle/render/av/virtualScroll.ts:252` 表格的 `galleryColumn` 被算成 2（性能面，非正确性）；
   `app/src/protyle/render/av/select.ts:626` 批量替换分支的 `mSelect` 访问是族内唯一未加可选链处。

## 第十五轮（2026-09-13）：前端设置项 / 内核契约 / 路径校验 / MCP 租约

范围：`app/src/protyle/wysiwyg` + `app/src/protyle/util`、`app/src/ai` + `app/src/plugin`、
`app/src/config`（除 entryVisibility）+ `app/src/boot` + `app/src/util` + `app/src/dialog`、
`kernel/{bazaar,job,plugin,mcp,task,cache,heif}`。四路只读侦察 + 主线取证，五条候选过挑战门。

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D3c（新 P27） | 设置 - 外观 - 通知 的「全选不完整提示」开关永不生效：前端 `APPearanceTab.ts:1149-1160` 有 7 项，内核 `kernel/util/appearance.go:63-70` 只有 6 字段（镜像 `apicontract/bazaar.go:360-368` 同），静默丢弃后被广播覆盖；消费点 `keydown.ts:229-234` 永远为假。附带 `objEquals` 恒不成立 → 每次关闭该对话框都写一次 `setAppearance` | 高（挑战门两轮 CONFIRMED，严重度中） | 已提 issue #19452 |
| D1h（新 P28） | `kernel/model/template.go:106-121` `RemoveTemplate` 只做词法校验，`templates/link -> ..` 时 `RemoveTemplate("link/conf")` 会递归删除目录外的 `<data>/conf`；同族四处均有 realpath / 逐级 Lstat / `os.Root` 防护且带软链测试。`kernel/mcp/tools/template.go` 的读取路径同样缺校验 | 高（挑战门：第一轮误判降级，复活轮纠正后 CONFIRMED，严重度中） | 已提 issue #19453 |
| F | `app/src/config/render/render.ts:72` 的 `textarea` 分支不转义（同函数 `:76`/`:80` 转义），7 个配置项受影响；`</textarea>` 提前闭合 + RCDATA 解码实体 → 面板显示值≠配置值并静默回写 | 高（挑战门两轮 CONFIRMED，严重度低） | 已提 issue #19454 |
| D3（新 P29 附带） | `kernel/mcp/tools/box_lease.go:30-47` 的加密租约白名单缺 `inbox`（`inbox.go:208` 与白名单内的 `document.go:134` 调用同一句 `CreateDocByMd(notebook, …)`，且 resolver 已支持 `notebook` 键）；根因是 `performCreateDocTransaction` 吞掉落盘错误（`model/file.go:2422-2430` + `transaction.go:120/488`）→ 报成功却删云端原件 | 高（挑战门两轮 CONFIRMED；第一轮把 `tag`/`bookmark` 一并列入属误报，已剔除；严重度低） | 已提 issue #19455 |
| D1 | `kernel/plugin/api_agent.go:174` 注册用局部名作键，返回值 `{id, name}` 都不等于该键，`unregisterCapability` 未命中时静默 resolve | — | **REJECTED**：petal `kernel.d.ts` 明确 `unregisterCapability` 接收注册时的局部名，按文档调用可正常注销；残留易用性问题见「未取证候选」 |

### 已审查并驳回

- **`tag` / `bookmark` 缺租约**（原与 `inbox` 同列一条）：这两个工具只能从**全局索引**取候选文档
  （`model/tag.go:39/146` → `sql.QueryTagSpansByLabel`、`model/bookmark.go:41/113` → `sql.QueryBookmarkBlocks`，
  均只查全局库），而加密笔记本的内容索引在独立 SQLCipher 库、未解锁时 fail-closed 不回退全局；
  `docs/ENCRYPTED-NOTEBOOK.md` 明确标签/书签不支持加密笔记本。因此加入白名单是死代码，判为**有意排除**。
- **`kernel/plugin/api_agent.go` 注册/注销键不一致**：见上表 REJECTED 理由。

### 未取证候选（勿重报，除非有新证据）

- `kernel/heif/convert.go:155-170` `ImageSize` 无 ctx/超时地阻塞在单槽信号量上（`convert` 侧有 `select` + 超时）。
- `kernel/mcp/client/oauth_store.go:157-170` `removeOAuthCredential` 缺少另外三个函数都有的「Endpoint/Resource 归一化」
  （当前唯一调用点传 `""` 故不可达）。
- `kernel/plugin/api_agent.go` 的 API 易用性：`registerCapability` 返回 `{id, name}` 但两者都不是注销所需的局部名，
  与前端 `addAgentCapability`（`app/src/plugin/index.ts:575-612` 返回 `id`、`uninstall.ts:80-84` 按 `id` 注销）
  的约定不一致；且未命中时无日志。属契约回显缺口，非功能缺陷。
- `kernel/model/template.go` 的 `RemoveTemplate` 与 MCP `resolveTemplatePath` 之外，
  `kernel/cli/cmd/template.go:202-214` 的 `resolveTemplateAbs` 用 `strings.HasPrefix(rel, "..")`，
  会把名为 `..foo` 的合法子目录误判为越界（同族实现口径不一致）。
- `app/src/protyle/util/table.ts:258/377/403` 与 `tableControl.ts:2050/2652` 的 `querySelectorAll("col")` 缺 `:scope > colgroup > col`
  作用域（同族 4 处已加），需表格缺 `<colgroup>` 且含嵌套表格才可达。
- `app/src/protyle/util/tableControl.ts:2004-2011` 删除行/列不传 `options`，故 `table.ts:1201-1219` 的光标与滚动恢复不执行
  （同函数为另一调用方实现了该恢复）。
- `app/src/protyle/util/viewFold.ts:247-266` `applyFold` 展开时缺 `applyFoldState` 的三步收尾
  （行号重排、`clearSelect`、`scrollCenter`）。
- `app/src/plugin/index.ts:629-635` 的 `removePluginDock(this, id)` 按 id 在全部 dock type 中匹配，
  同 id 跨 type 时会误删另一个停靠栏（需插件复用 id）。
- `app/src/config/tabs/ai/aiUi.ts:164-172`/`:497-505` 用每帧 rAF 轮询 `document.contains` 来清理 `setInterval`。
- `app/src/layout/dock/Inbox.ts:123/129` 的 `splice(indexOf(x), 1)` 未命中时删末尾（第 14 轮已记，仍未证可达）。

### 方法论教训

1. **文件系统语义必须区分「叶子」与「中间组件」**。本轮 `RemoveTemplate` 的第一轮审查只验证了「叶子是软链」，
   据此把发现降级为「防御纵深不一致」；复活轮指出 `unlink` 会解析全部前导组件、`RemoveAll` 打开 parentDir 时无
   `O_NOFOLLOW`，因此中间组件软链会操作链接目标（目录场景是**递归删除目录外整棵树**）。
   **挑战门的第一轮也可能错**，对「降级理由本身是技术断言」的情况必须再验一次断言。
2. **逐条核对行号与「同列发现」的独立性**。本轮把 `tag`/`bookmark` 与 `inbox` 合并成一条，前者实为误报
   （候选来源是全局索引，物理上不含加密笔记本）；合并表述会让一条正确发现背上两条错误论据。
3. **「一致性缺陷」要写清它是谁的不一致**：`appearanceTab` 的守门函数在同文件另一处能正常工作，
   证明问题在键集合而不在守门逻辑——这类「同文件对照组」比引用外部规范更有说服力。
4. **机械扫描的增量仍为 0**：`kernel/` 首次扫描得 27 条重复字面量（592 文件），逐条核对后无新命中；
   本轮的 4 条发现全部来自定向语义核查。
5. **白名单类缺陷要先判定「筛选标准是什么」**。`encryptedBoxScopedToolNames` 的真实标准不是「会不会碰到加密笔记本」
   而是「会不会把加密笔记本的明文带进响应」，按此标准 `inbox` 的取舍才清楚；
   同时 `docs/ENCRYPTED-NOTEBOOK.md` 的成文政策（MCP 编辑操作应持租约）与实现不一致，属「白名单语义未对齐政策」。



## 第十六轮（2026-09-13）：未覆盖区域定向（kernel/api、kernel/sql|search|treenode、app/src/menus、app/src/asset|card|search|editor）

范围取舍：`app/src/data/**` 与 `app/src/export/**` **在本仓库不存在**（导出前端在 `app/src/protyle/export/**`），子代理已当场纠正范围。
四路只读侦察 + 主线逐条取证，五条候选全部过两轮挑战门（其中四条 DOWNGRADED 到低，一条 CONFIRMED 到低）。

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1d（P19 增补） | `/api/av/changeAttrViewLayout`（`kernel/api/router.go:621`）是 `/api/av/*` 全部 48 条路由中**唯一**缺 `model.CheckReadonly` 的写端点；handler（`kernel/api/av.go:345`）→ `model.ChangeAttrViewLayout`（`kernel/model/attribute_view.go:1421`）确实落盘（`setNodeAttrs` 写 `.sy` IAL + `av.SaveAttributeView` 写 `storage/av/<avID>.json` + `ReloadAttrView`）。`kernel/av/` 全包 grep `util.ReadOnly` = 0，model 层无兜底 | 高（挑战门两轮：一轮 CONFIRMED、二轮维护者反驳后仍确认） | **与并行 B 线会话重复**：由该会话提为 issue #19461（本会话不重复提交，已在该 issue 下补入机制层证据：`apicontract.Route` 只有 Method/Path/Handler 三字段、无全路由中间件断言），严重度低 |
| D1j（新 P30） | `kernel/sql/upsert.go:445-499` 的 `upsertTree` 先无条件删除 `spans`/`attributes`/`assets`/`refs`/`file_annotation_refs`，再调 `insertTree0`（:501-510），而 `insertTree0` 的**第一句**才是 indexignore 判断 → 命中忽略规则的文档在增量保存路径上「删了不插」。同族 `indexTree`（:438-443）无前置删除，是干净 no-op | 中（可达性逐环核实，未实测；挑战门一轮 DOWNGRADED、二轮维护者仍认为是真实结构不一致但低） | 已提 issue #19462，严重度低 |
| D1l（新 P32） | `app/src/search/toggleHistory.ts:14-18` 的 `toggleReplaceHistory` 把 storage 对象绑成 `list` 后按数组用（`list.length === 1 && list[0] === ...`），第三子条件恒 false；同族 `toggleAssetHistory`（:161-166）先取 `keys` 数组。替换一次「foo」即可复现「弹出只剩『清除历史』的菜单」 | 高（挑战门一轮 DOWNGRADED：只有第三个子条件恒假，不能写「守卫等于不存在」） | 已提 issue #19463，严重度低 |
| D1k（新 P31）/ D1e | `app/src/card/openCard.ts` 的 `allDone`（:911-922）隐藏 `[data-type="more"]` 及其 `previousElementSibling`，`nextCard`（:888-910）只恢复 `card__block`/`count`，漏 `more` → 换卡包后 ⋮（设置到期时间/统计/重置/移除卡片）不出现。`previousElementSibling` 在移动端是 `[data-type="filter"]`，连带隐藏筛选 | 高（挑战门两轮 CONFIRMED，二轮指出「同函数恢复了 `card__block` 却漏 `more`」是不对称而非设计） | 已提 issue #19464，严重度低 |
| D1 | `app/src/menus/tag.ts:19-40` 的 `openTagMenu` 无 `readonly` 守卫，而同族 `app/src/menus/bookmark.ts:19/52` 两处都有；`/api/tag/renameTag`、`/api/tag/removeTag`（`kernel/api/router.go:227-228`）与对应书签路由都带 `CheckReadonly`。同文件 `app/src/layout/dock/Tag.ts:49/50/83` 在只读下隐藏了 sort 与「更多」图标，唯独 `:81` 的 `rightClick` 无条件调用该菜单 | 高（挑战门两轮 CONFIRMED，二轮纠正「移动端无此入口、桌面与发布页才有」） | 已提 issue #19465，严重度低 |

### 第十六轮补记（2026-09-13，提交阶段）

本轮与另一个并行会话（B 线：内核 CLI / server / sql）**同时且互不知情地跑第十六轮**，提交阶段才发现重叠。处理如下：

1. **发现重复，不重复提交**：本会话的第 1 条（`changeAttrViewLayout` 漏挂 `CheckReadonly`）与 B 线的 #19461 是同一处缺陷（同 `file:line`、同结论）。**未另开 issue**，改为在该 issue 下补一条「机制层证据」评论
   （`apicontract.Route` 只有 `Method`/`Path`/`Handler` 三字段结构上容不下中间件声明；`contract_test.go:61` 只断言路由集合；全仓唯一一处 `CheckReadonly` 断言是手写路由不覆盖真实路由表）。评论已逐字符回读校验（2146/2146）。
2. **编号避让**：本会话先提交并推送了 `4f4d752`（P30/P31/P32 + D1j/D1k/D1l），B 线随后改用 **P34/P35/P36/P37 + D1m**，未发生编号冲突。
   **教训：并行会话同时在跑时，编号分配必须「先提交先占用」并及时 push**；若双方都只在本地写、最后才合并，必然撞号。
3. **去重手段**：提交前用 `gh api -X GET search/issues` 逐条检索（覆盖 open + closed）。注意 PowerShell 下带 `&per_page=` 的 URL 会被 `gh api` 拆成多个位置参数（报 `accepts 1 arg(s), received 3`），
   改用 `gh api -X GET <endpoint> -f q=... -f per_page=8 --jq ...` 或写入 Python 脚本（本轮用后者）。
4. **提交结果**：#19462（indexignore 先删后判）、#19463（替换历史守卫读错对象）、#19464（闪卡 ⋮ 不恢复）、#19465（标签菜单只读）——
   四条均逐字段回读一致（title 与 body 完全相等，长度分别为 92/85/77/69 与 2580/1710/1770/1697）。

### 子代理自验推翻 / 已驳回（勿重报，除非有新证据）

- `kernel/sql/upsert.go` 同族的 `indexTree` 忽略早退本身**正确**，不是缺陷。
- `kernel/sql/block_query.go:1225` 的 `containsLimitClause`（朴素 `strings.Contains(...," limit ")`）与同包 `query_limit.go:31` 的 `containsOuterLimitClause`（引号/注释/括号感知）语义分叉。误判为「有 LIMIT」会让 `Conf.Search.Limit` 失效，但需用户 SQL 含 `' limit '` 字面量才触发；`/api/query/sql` 路径不受影响。**未取证，仅观察项。**
- `kernel/sql/block_query.go:307` 的 `queryDocTitles` 是四兄弟（`queryNames`/`queryAliases`/`queryRefTexts`）中唯一无 `LIMIT 10240` 的实现。是否「文档标题本就该全量」无法判定，仅记录。
- `kernel/sql/encrypted_query.go:682` 的 `GetChildBlocksInBox` 缺 `CheckSingleStatement`/`CheckReadonlyStatement`（全局版 `block_query.go:1023` 有）。已逐调用点确认 `condition` 恒为 `""` → 当前不可达，纯 latent。
- `kernel/treenode/node.go:504` 写两套键（裸 `defID` + `boxID\x00defID`），`:525-535` 的 `RemoveDynamicRefTexts(boxID)` 只按前缀删 box-aware 键 → 裸键永不逐出。对照 `kernel/cache/ial.go` 把「空 box」显式建模成 `"\x00"+id` 并把三种键一起删。已登记，未取证。
- `kernel/api/router.go:119-122` 的 `updateRecentDocOpenTime/ViewTime/CloseTime/batchUpdateRecentDocCloseTime` 无 `CheckReadonly`，替代守卫 `skipReadonlyStorageMutation`（`kernel/api/contract_storage.go:11`）只看**角色**不看 `util.ReadOnly`；`kernel/model/storage.go` 全文件 grep `util.ReadOnly` = 0。影响限于应用态文件，未取证。
- `kernel/api/storage.go:388` 的 `removeViewState` 成功路径复用 `contractFailure`（同族其它成员是「错误分支 failure、正常分支 Success」）。已逐字比对 `Response.MarshalJSON` 与 `Null`：线协议完全一致，属「成功构造点缺失」的潜在陷阱，无当前后果。
- `kernel/api/system.go:217/226` 对 `custom["items"] = items` 写了两次，中间无读回，当前无副作用。
- `app/src/menus/workspace.ts:85-99` 的「重命名布局」缺 `btnsElement[3]` 新建分支的 `hadName` 重名确认（`LOCAL_LAYOUTS` 全程以 `name` 为主键）→ 可产生同名布局，此后 `find` 只命中第一条。已读码确认，未过挑战门。
- `app/src/menus/navigation.ts:311-316` 多选文档菜单的 `unpinDoc` 在 `canPin`（含 `isEncryptedBox`）之外，单选分支 `:849-857` 则 pin/unpin 同受该判据约束。已读码确认，未过挑战门。
- `app/src/asset/index.ts:109` 的 `this.path.substr(this.path.lastIndexOf(".")).toLowerCase().split("?")[0]` 自解析扩展名（全仓其余 20+ 处走 `getAssetExtension`）。query 含点号（如 `?dataPath=/docs/a.sy`）时 `type` 落空 → 所有分支不命中 → 页签空白。**可达性未证实**（`?dataPath=` 主要由 `getAssetsPreviewPath` 生成给预览元素，且其 dataPath 末段扩展名与资源一致），仅观察项。
- `app/src/menus/protyle.ts:2139` 图片「高度」子菜单项 `id: "width_" + label`。无消费方，已写入「已知误报」。
- `app/src/menus/navigation.ts:1055-1065` `reloadDocTree` 的 `liElement.querySelector` 未判空。导入后节点通常仍在 DOM，未证可达。
- 子代理自验推翻（不计入）：`menus/protyle.ts:1784` 的 `splice(indexOf("a"), 1)`（全部调用点都有 `includes("a")` 守卫）、`menus/protyle.ts:2556` `colIsPure` 不判空（合并单元格保留占位，行始终等宽）、`menus/navigation.ts:187` 多选笔记本隐藏导出（`exportNotebooksSYBundle` 对加密库直接 return）、`menus/dataMigration.ts:107` Obsidian 按钮不 disabled（导入时可新建笔记本）、`sql/av.go:1224` 与 `av/filter.go:1323` 都不注入繁简归一化（整体设计取舍）、`sql/span.go:107/129` 两处 `GROUP BY` 不同（只用返回 map 的 key）、`search/mark.go:90-96` 上下文多截 1 rune（`mark_test.go` 已固化为预期）、`asset/index.ts` 的 `pdfResize` 先读 `clientHeight` 后判空（仅 PDF 模板存在该元素）。
- 机械复扫：重复字面量 **231** 条（P1 195 / P2 16 / P3 20，文件 1373）、未转义插值 **244** 条 / 95 文件，逐条核对仍为已知噪声；本轮 0 重复报告（开扫前已用登记表排除 15 组）。

### 方法论教训

1. **「同族其它实现都挂了该守卫」需要先分类再定论**。第二轮维护者指出：`CheckReadonly` 在本仓是**保守惯例**，连 `getAttributeViewItemStatuses`、`getAttributeViewSearchTarget`、`getAttributeViewKeysByAvID` 等**纯读**端点也挂着。因此「兄弟都有」不能单独证明此处是漏项。真正让本轮结论成立的是另外两条硬证据：用户指南明写「`--readonly=true` … **所有写入操作将被禁止**」（`app/guide/.../20200828105441-r76vmu5.sy:164`），以及**同一个能力经 `/api/transactions` 是被禁止的**（`kernel/api/router.go:457` 带 `CheckReadonly`，`kernel/model/transaction.go:440` 的 `doChangeAttrViewLayout`）——「布局属视图、可以豁免」的解释因此站不住。
2. **维护者视角能挖出「机制层缺失」这个更大的问题**。二轮指出：`apicontract.Route`（`kernel/apicontract/routes.go:15-19`）只有 `Method/Path/Handler` 三个字段，**结构上容不下中间件声明**；`TestAPIContractRouterCoverage` 只断言路由集合相等，不看中间件。所以真正值得修的是「给契约加写属性元数据 + 一条覆盖全路由的断言」，只补一行等于把结构性盲区再埋回去。**报告应把「本行修复」与「机制缺失」分开写。**
3. **守卫的「绝对位置」比守卫的「有无」更难发现**。P30 的形态是同族两条路径各有守卫、守卫内容也相同，唯一差别是它相对副作用的位置。判别法已固化为：先找共享函数里守卫在第几句，再问「调用方在调用它之前做了什么」。
4. **`previousElementSibling` 在双模板下必然跨端漂移**。本轮 `allDone` 想隐藏的是分隔符，移动端同一位置却是功能按钮。凡见到位置选择器 + `/// #if MOBILE`，应直接把「两端命中的元素分别是谁」写成必答项。
5. **挑战门第一轮的「描述失准」也要照单修**。第二轮把 `toggleHistory` 从「守卫等于不存在」纠正为「只有第三个子条件恒假」——这直接决定了修复面（改一个条件 vs 重写守卫），也决定了严重度（纯外观 vs 功能缺失）。**症状描述错会改变修法，不只是措辞问题。**
6. **子代理纠正了本次的范围前提**：`app/src/data/**` 与 `app/src/export/**` 不存在。派发侦察前先让对方确认目录存在，比事后修补量少。
7. **本轮机械扫描增量仍为 0**，五条发现全部来自定向语义核查（D1 及其子型），与前四轮结论一致。重复字面量条目数从 166 涨到 231 纯因扫描文件数从 1360 涨到 1373 与阈值波动，无新增可报项。

## 第十六轮（B 线，2026-09-13）：内核 CLI / server 装配 / sql 与文件系统

> 本轮与另一个并行会话同时进行。为避免冲突：使用独立临时目录 `%TEMP%\audit-r16b`（不触碰对方的 `audit-r16`）、
> 建 issue 前用 search API 遍历 open+closed 去重、写回 skill 前先 `git pull --rebase`。范围刻意避开对方的
> 前端/外观方向（对方当轮产出见 #19444 `custom-attr__avbacklinks 布局`、#19445 `boot window 冷启动`）。

范围：`kernel/cli/`、`kernel/server/`、`kernel/sql/` + `kernel/search/` + `kernel/filesys/` + `kernel/conf/`。
三路只读侦察 + 主线取证，六条发现过挑战门（其中一条经挑战门**纠正可达性并降级**）。

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1h / D1g（新 P34） | `kernel/server/serve.go:742-806` 的 `/appearance/*filepath` 只做词法 `IsSubPath` 后 `c.File`，而 `kernel/model/session.go:276-281` 对该前缀免鉴权（已设锁屏密码时连 Origin 检查也跳过）→ `conf/appearance/` 下的越界软链可被匿名读取，目标是 `conf/conf.json`（`api.token`/`cookieKey`）。同族四处静态出口都做了 realpath 复核并有软链测试；同 handler 的 `langs` 分支另有 `os.ReadFile` 泄漏路径 | 高（挑战门两轮 CONFIRMED，严重度中；集市渠道已封闭，前置需手工/git 带入软链） | 已提 issue #19456 |
| D1d / D1 | `database clean --av <在用ID>` 删除在用数据库定义（`kernel/model/attribute_view.go:55-91` 无「未引用」判定，同族资产侧与复数版都有）→ 前端默认 `createIfNotExist` 会把数据库重建成空表；clean 历史在 `<workspace>/history` 不参与同步，多设备不可恢复 | 高（挑战门两轮 CONFIRMED，严重度高） | 已提 issue #19457 |
| D3（新 P36） | `kernel/server/serve.go:320` 的 `gzip.WithExcludedExtensions` 是**赋值**语义，把 gin-contrib/gzip v1.2.3 默认的 `{png,gif,jpeg,jpg}` 整体替换 → 所有图片被 gzip；作者已排除 `.gz`/HEIF，属同类漏项 | 高（上游 v1.2.3 源码逐行核对，严重度低） | 已提 issue #19458 |
| D1m 变体（新 P35） | `kernel/cli/cmd/export.go:34-105` 三个导出命令不检查空结果 → `os.WriteFile` 把 `--output` 截断为 0 字节且退出 0；dry-run 被 `&& output != ""` 吞掉；同一族还有 `block delete` 与 `repo checkout` 报假成功 | 高（严重度低） | 已提 issue #19459 |
| E3/E4（新 P37） | `kernel/model/graph.go:695-702` + `kernel/conf/search.go:135-146` 拼 `LIKE` 未转义 `%`/`_` → 关系图搜索输入 `_` 时几乎不过滤；权威侧 `kernel/sql/span.go:28-38` 的 `escapeLikePattern` | 高（严重度低） | 已提 issue #19460 |
| D2/G | `kernel/api/router.go:621` 的 `/api/av/changeAttrViewLayout` 漏挂 `CheckReadonly`（同段唯一），`--readonly` 模式下仍改写 av 文件与镜像块 IAL | 高（严重度低） | 已提 issue #19461 |
| D1 | `kernel/sql/index_queue.go:104-133`/`:316-319` 的 `dbOpToIndexEntry` 与 `indexEntryToOp` 均缺 `update_block_content`（`kernel/sql/queue.go:49` 的注释与 `:393` 的 execOp 都承认该 action）→ 该操作永不写入 `queue/index.queue`，崩溃后丢失，嵌入块内容保持陈旧 | 中高 | 待提 issue |
| D1 | `kernel/cli/cmd/outline.go:34-49` 把「文档无标题」判为失败（HTTP 侧同名端点返回空数组 + code 0），脚本无法区分「不是文档」与「没有标题」 | 高 | 待提 issue |
| D1 | `kernel/cli/cmd/history.go:153` 的 `--op` 帮助文案枚举 `delete/update/create`，而真实集合是 `clean/update/delete/format/sync/replace/outline`（`kernel/model/history.go:1127-1133`）；且 `--op` 是唯一未做过滤就拼进 SQL 的筛选参数 | 中 | 待提 issue |

### 挑战门纠正（本轮最重要的过程记录）

`/api/av/changeAttrViewLayout` 一条在第一轮被写成「只读角色下仍可改数据库布局」，**挑战门按中间件顺序推翻了这一半**：
路由链是 `CheckAuth → CheckAdminRole → handler`，而 `CheckAdminRole`（`kernel/model/session.go:456-462`）对
`RoleReader`/`RoleVisitor` 直接 403，发布服务 JWT 的角色正是 `RoleReader`（`kernel/model/auth.go:290-310`），
因此只读角色根本进不到 handler；真正可达的只有内核 `--readonly` 模式。
附带发现：handler 内 `kernel/api/av.go:365-369` 针对只读角色的 `IsReadOnlyRoleContext` 分支因此是死代码。
→ 已把「按中间件顺序核对角色可达性」写入「已知误报」，并把该条严重度从「中」降为「低」。

### 方法论教训

1. **并行会话下的隔离三原则**：独立临时目录、建 issue 前用 search API 去重（覆盖 open+closed；`gh search issues --state all` 不被支持，
   改用 `gh api search/issues`）、写回 skill 前 `git pull --rebase`。另外主动确认对方的产出（本轮 #19444/#19445）并避开其方向。
2. **鉴权类发现的定级必须交叉两个事实**：路径校验强度 **×** 鉴权豁免范围。任一单独都不足以定级；
   本轮把「词法校验」与「`/appearance/` 免鉴权」两条线交叉后才有完整攻击链。
3. **修法陷阱要写进报告**：本轮外观软链的修复若照抄同族的「敏感目录前缀黑名单」，会让所有外观资源 403
   （因为外观根就在 `conf/` 下）；若一律禁止符号链接，会破坏仓库**有意支持**的软链主题目录（#8263）。报告里写明这两条，
   比只给「加 EvalSymlinks」有用得多。
4. **第三方库选项要先读库源码**：`WithExcludedXxx` 是赋值还是追加、默认集合是什么，只能从库源码确认；
   判据是「库默认 − 调用方」的差集。
5. **「无返回值 + WS-only 错误通道」是 CLI 的普遍盲区**：本轮一条发现串起了 `block delete`、`repo checkout`、
   `export *` 三类命令，说明按「CLI 子命令 → model 函数签名」的机械扫描（grep 是否有返回值）是高效入口。

## 第十七轮（2026-09-13）：已提 issue 的修复验证

范围：本 skill 历轮产出的 **37 条 issue 全量核对**（#19397–#19465，含并行 B 线的 #19456–#19461）。
方法固定为四步：**issue 状态 → 修复提交 → 代码现状 → 回归测试**。

### 结论

| 项 | 结果 |
|---|---|
| issue 状态 | 37/37 `closed`（#19432 在 `petal` 仓库修复，非本仓） |
| 代码已改 | 37/37，位置与本轮报告一致 |
| 新增/补测 | 21 处（含 1 条 i18n CI workflow） |
| 受影响包完整测试 | `av` `sql` `conf` `treenode` `apicontract` `mcp/tools` `api` `cli/cmd` `model` 全绿；`server` 仅 1 处**宿主 MIME 差异**失败（见下，非回归） |
| 前端（09-14 补正） | 本轮相关 105 条全绿；**全量套件有 13 处失败，其中 10 处为源码测试的真实失败**（原记录「1 处」是我只读输出尾部造成的误判，见下） |
| **由修复引入的回归** | **0** |

### 方法要点（新增，可复用）

- **编号 → 提交的映射必须回读代码补齐**：`git log --format="%h|%ad|%s" -500 | Select-String "issues/194"` 只覆盖「提交信息带该编号」的情形。
  #19429（保存条件丢页签过滤器）的修复藏在 `2b26d96ec6`（提交信息写的是 #19378）里，`git log --grep=19429 --all` 空手而归。
  **只看提交信息会把已修的判成未修**，最终以代码现状为准。
- **修复可能换思路，验证要落到显示链路末端**：#19435 维护者没按「比值 + percent」改量纲，而是保留 `content = ratio*100`
  以维持筛选/模板/底部统计的既有语义，只把 `FormattedContent` 覆盖为 `formatNumber(ratio, NumberFormatPercent)`
  （`kernel/av/value.go:3186-3192` 的 `newRollupCheckboxPercent`）。验证时必须回读消费端：
  `app/src/protyle/render/av/cell.ts:1242` 与 `attributeValue.ts:131` 都取 `formattedContent || content`，
  而筛选 `filter.ts:615` 读原始 `content` —— 两条路径各取到正确的那个字段，修复成立。
- **修复常比最小改动更彻底**：`buildSearchRequest` 提取为单一真源并同时替换桌面与移动端两处复制（#19442）；
  新建 `app/src/protyle/render/av/locateState.ts` 承载「临时展开态」（#19448）；
  `scripts/check-lang-keys.py` 新增占位符维度校验并接入 `.github/workflows/i18n.yml`（#19430，直接补掉了本轮报告的「无有效校验 + 不在 CI」）。
- **本轮预警的修法陷阱被全部规避**（可视为判据有效性的正反馈）：
  #19448 未写回 `groupFolded`（改存 WeakMap + 交互事件清理）；#19439 用 `webdav.NewHTTPError(http.StatusNotFound, …)`
  而非兄弟路径的普通 error（避免把幂等重试变 500）；#19464 改用 `[data-type="more"], [data-type="more-space"]` 选择器取代
  `previousElementSibling`（避开移动端语义差异）；#19456 未复用按前缀判定的敏感目录黑名单、也未一律禁软链。

### 宿主 MIME 注册表决定内联白名单（09-14 从「误报」改判为**真缺陷**）

`kernel/server/serve.go:917` 的 `isAssetInlineUnsafe` 用 `mime.TypeByExtension` 取媒体类型再按白名单判内联，
而 Windows 上 Go 的 `initMimeWindows`（`$GOROOT/src/mime/type_windows.go`）会遍历 `HKEY_CLASSES_ROOT`
用 `setExtensionType` **覆盖内置表**（仅 `.js` 硬编码豁免 `text/plain`，Go issue #32350）。
本机 `.jpg` 注册为 `application/jpg`、`.jpeg` 仍为 `image/jpeg`；逐扩展名比对 19 项只有 `.jpg` 与内置表不同，
而 `.js` 的注册表值 `text/plain` 恰在白名单内 —— **证明注册表确实能给出「内联安全」的类型**。

影响面已夹逼且**不可夸大**：Chromium 忽略子资源上的 `Content-Disposition` 与错误 Content-Type
（四个对照端点正常/仅附件头/仅 `application/jpg`+nosniff/两者兼具，`<img>` 全渲染成功），
真正受影响的是顶层导航（仓库注释自述该头用于让 `window.open` 触发下载）。

**教训（已写入 SKILL.md「曾被误判为误报、实为真缺陷」）**：上轮以「测试早于改动数周、CI 不复现」为由判为环境噪声，
理由不成立 —— **测试在 Windows 上确定失败说明它不可移植，而白名单来源可被本机改写是产品层设计缺陷**。
**「CI 跑不到」不是免报牌，它是判据 G4 的独立发现。**

### 前端测试套件实况（09-14 补正，新判据 G3/G4）

`cd app && pnpm test`（`dev` = `e4960b6553`）：`tests 2474 / pass 2455 / fail 13`，去重后共 13 个失败用例。
**上一轮只读了输出尾部（`Select-Object -Last 15`）就写下「仅 1 处无关失败」，实为 13 处 —— 误判直接进了结论。**
逐个单跑仍失败，排除了测试间干扰。

按根因分四类：

| 类别 | 数量 | 机制 | 实例 |
|---|---|---|---|
| 测试发现非 hermetic | 3 | `"test": "node --import tsx --test"` 未限定路径，递归扫到被 `.gitignore:14` 忽略的 `app/build/win-unpacked/resources/app/`（electron-builder 副本）。把 `app/build` 移出 `app/` 后：`tests` 2474→2427、`fail` 13→10 | `build\win-unpacked\...\{connectionManager,remoteKernel,windowMessaging}.test.js` |
| 测试替身/白名单漂移（G3） | 5 | 桩对象存在但缺新导出（`TypeError: (0 , m_1.f) is not a function`）；模块白名单缺新 import；DOM 替身缺新调用的方法 |  `topBar.test.ts:270` 缺 `isInMobileApp`；`transactionAV.test.ts`×2 缺 `getEditorTransaction`；`backlinkReference.test.js` 缺 `setBacklinkTypeFoldExpandHandler`；`mobileBacklinks.test.js` 缺 `editor/assetOpen`；`image.test.ts` 的 `classList` 只有 `toggle` 没有 `remove` |
| 断言未随生产变更更新 | 4 | 断言写死了实现细节 | `fontPreview.test.ts:45` 要求 `rootMargin === undefined` 而实现传 `"100px 0px"`；`fileTreeReorder.test.ts:54` 用 `strictEqual` 要求返回原对象而实现已改为投影；`entryVisibility.test.ts:32` 插件槽位期望基于字体项位于 `text` 之后（默认条目 09-09 已移到之前） |
| 行尾敏感 | 1 | 按 `"\n    });\n"` 切片源码；`.gitattributes` 对 `.js` 只写 `* text=auto`，本机 `core.autocrlf=true` 检出为 CRLF → 锚点不匹配 | `electron/windowMessaging.test.js:100`；`app/electron/main.js` 实测 4497 CRLF / 0 孤立 LF，`b"\n    });\n" in file` = False、`b"\r\n    });\r\n"` = True。同目录 `crashHistory.test.js:10` 用 `"\n};"`（无尾随换行）故不受影响 |

**引接各条的生产提交**：`27d54e1809`(#19467)、`0a1b5b424e`(#19378)、`99e5bd19ac`(#19257)、`6ed4866976`(#19378)、
`4de337d316`(#19407)、`ff239fd9b3`(#19323)、`aaf5f44829`(#19378)、`b1077b520a`(#19226)。
其中 `aaf5f44829` 的改动经核验对消费方安全：`Files.ts:1031`、`MobileFiles.ts:502`、`PinnedDocs.ts:499` 都只读 `result.notebook` 与 `result.parentPath`。

### CI 执行集缺口（新判据 G4，已提 #19472）

`.github/workflows/api-contracts.yml` 是唯一跑单测的 workflow，且是白名单式：
内核只跑 `./apicontract/...` 与带 `-run` 过滤的 `./api ./plugin ./model`；前端 `pnpm exec tsx --test` 只列 7 个文件。
对照 `go list ./...` 的 30 个包与 358 个前端测试文件，未覆盖面极大（`server` `sql` `av` `conf` `treenode` `mcp/tools` `cli/cmd` 等）。
**后果**：本地全量一跑就红、CI 恒绿，于是没人能区分新回归与存量噪声 —— 我自己的误判就是这套机制的直接产物。

### 本轮已提 issue 与最终归宿

四条均 title/body 逐字符回读一致（长度差 1 为 GitHub 自动追加的尾部换行）；取证工具在 `%TEMP%` 下（已删除），仓库内零残留。

| issue | 状态 | 修复提交 | 说明 |
|---|---|---|---|
| #19472 | open（CI 已通过，维护者未关闭） | `a846821ec2` + `8f0071886c` + `22a727db07` | CI 从白名单改为 `go test -tags "fts5 sqlcipher" ./... -count=1` + `pnpm test`，文档同步 |
| #19473 | closed | `d32b6592f6` | `"test"` 加四个 glob 排除 `app/build`；并发先 4 后降到 1 |
| #19474 | closed | `dc55a0635a` | 补齐替身与响应字段、更新断言、消除 CRLF 敏感匹配 |
| #19475 | closed | `2d0561daf5` | 新增固定映射 `assetInlineMediaType`，并在 `secureAssetContentHeaders` 里显式写死 `Content-Type` |

**本地复验（Windows，`8f0071886c`）**：`pnpm test` = `tests 2418 / pass 2412 / fail 0 / skipped 6`（改前 2474/13）；
`go test -tags "fts5 sqlcipher" ./...` 26 个包全部 `ok`。两端均全绿。

**#19475 的修法与报告建议一致且更完整**：除了判断本身，还顺带把允许内联资产的 `Content-Type` 固定下来
（`context.Header("Content-Type", mediaType)`），理由是宿主 MIME 同样会影响预览行为——这比我报告里只写
「替换判定的输入」更彻底；`.svg`/`.html`/`.js` 依旧不在映射表内即强制下载，安全公告的约束保持不变。

#### 教训：CI 覆盖补全后必然以「三连提交」暴雷

`a846821ec2`（把 CI 改为全量）→ **failure**，且失败原因与我的 issue 描述**不同**，是新增暴露的**测试环境前提冲突**：

- `contracts` 失败 1（Linux）：`kernel/model` 的 `import_obsidian_test.go:92`
  `Obsidian Vault path is unsafe: selected Vault path is sensitive`；
  同因还挂了 `kernel/server` 的 `TestRegisterStaticFileHandlers`/`TestWidgetResponseCacheControl`/
  `TestTemplatesAndExportRequireAdministrator`/`TestSnippetPublishAccess`/`TestPluginPublishAccess`。
  根因：这些夹具建在 `t.TempDir()`，而 GitHub Linux runner 的 `TMPDIR` 默认是 `/tmp`，
  `kernel/util/path.go` 的 `isSensitivePath` 系统前缀黑名单含 `/tmp` 与 `/var`。
- `frontend-tests` 失败 1（Windows）：`Error: spawn EBUSY`（Electron 并发启动争用）。

于是 `8f0071886c` 两处修：CI 加 `TMPDIR: ${{ runner.temp }}`、并发降到 1。
但**又把前提推过头**：`TestIsSensitivePathSymlinkWorkspace` 的末句断言
（`isSensitivePath(realWorkspace+"-outside/public.txt")` 必须为 `true`）**依赖夹具落在黑名单前缀下**，
`TMPDIR` 变到 runner 目录后就不再成立 → 该 commit 的 CI 仍 `failure`（`kernel/util`）。
`22a727db07` 再给这一个测试 `t.Setenv("TMPDIR", "/var/tmp")`，CI 才 `success`。

**可复用判据（已并入 G4）**：同一套夹具里存在**互相矛盾的环境前提**——一组要求临时根目录命中系统路径黑名单、
另一组要求不命中。检查法：grep 夹具的 `TempDir`/`MkdirTmp` 与环境变量，再 grep 路径黑名单常量，
找出「断言真值依赖二者前缀关系」的测试。可靠修法是构造显式路径（工作空间内、或直接指向黑名单目录），
而不是依赖环境的临时根。

**并记一条验证纪律**：`a846821ec2` 的提交信息写着「Run all kernel and frontend tests in CI」，
看起来一次性修好了，但该 commit 的 CI 实际是 `failure`；**判定 `fixed` 必须用
`gh run list --json conclusion` → `gh run view <id> --json jobs` 看真实结论**，
维护者评论里的「本地全量测试通过」同理不能等同 CI 通过。

#### 矛盾前提的 2×2 取证（三次 CI 运行即为完整证明）

`kernel/util/path.go:470` 的 `isSensitivePath` 对**工作空间外**路径做硬编码 UNIX 前缀匹配
（`/.` `/etc` `/root` `/var` `/proc` `/sys` `/run` `/bin` `/boot` `/dev` `/lib` `/srv` `/tmp` `/usr` `/opt` `/sbin`，
`path.go:487-509`）。两组测试把这一事实当作**相反的前提**：

- **A 组必须命中前缀**：`kernel/util/path_test.go:173` `TestIsSensitivePathSymlinkWorkspace` 末句
  `path_test.go:220-225` 断言 `isSensitivePath(realWorkspace+"-outside/public.txt")` 为 `true`。
  该路径与工作空间是**字符串前缀相同但路径边界不同**的兄弟目录，`IsSubPath` 判定为工作空间外，
  所以它只能靠系统前缀黑名单命中；而黑名单是 `HasPrefix(path, "/var")` 这种**锚定路径开头**的匹配，
  夹具路径里那层 `.var/app/org.b3log.siyuan/SiYuan` 帮不上忙 → 必须 `TMPDIR` 以 `/tmp` 或 `/var` 开头。
- **B 组必须不命中前缀**：`kernel/model/import_obsidian.go:576` 的 `validateObsidianVaultRoot` 对 vault 根调
  `util.IsSensitivePath`，`kernel/server` 的静态伺服同理；夹具全是 `t.TempDir()`。若 `TMPDIR=/tmp`，
  则 root = `/tmp/TestXxx…/001` → 命中 `/tmp` → 报 `Obsidian Vault path is unsafe: selected Vault path is sensitive`
  而非期望的 `errObsidianVaultConfigMissing`。

| CI 运行 | commit | `TMPDIR` | A 组 `kernel/util` | B 组 `kernel/model` + `kernel/server` |
|---|---|---|---|---|
| 34771606033 | `a846821ec2` | 未设 → Linux 默认 `/tmp` | `ok … kernel/util 2.318s` ✓ | **FAIL**（15 个用例） |
| 34771876307 | `8f0071886c` | `${{ runner.temp }}` | **FAIL**（`TestIsSensitivePathSymlinkWorkspace`） | 通过 ✓ |
| 34772185308 | `22a727db07` | `runner.temp` + 用例级 `/var/tmp` | 通过 ✓ | 通过 ✓ |

第三行不是「找到了兼顾的取值」，而是那个测试**在自己的作用域内把变量改回去**——
因为 A 通过要求 `TMPDIR` 命中黑名单、B 通过要求不命中，**同一变量上不可同时满足**，
这是由黑名单定义直接推出的，不需要实测反例。

**修复的残余脆弱点（值得再修）**：
1. 修复把「夹具可用」寄托在 CI 的 `TMPDIR` 取值上，而非让夹具自造所需路径。后果是
   **`go test ./...` 在 macOS（`TMPDIR` 天然为 `/var/folders/…`，同属 `/var` 前缀）上仍会红 B 组**。
2. `t.Setenv("TMPDIR", …)` 生效的前提是 `GOTMPDIR` 为空：`t.TempDir()` 走
   `os.MkdirTemp(os.Getenv("GOTMPDIR"), pattern)`（`$GOROOT/src/testing/testing.go` 的 `makeTempDir`），
   仅当 `GOTMPDIR` 为空才回落到 `os.TempDir()`（`$GOROOT/src/os/file_unix.go:390` 的 `tempDir`，**不缓存** `TMPDIR`）。
   一旦 CI 或本地设了 `GOTMPDIR`，该用例级覆盖会**静默失效**。
3. A 组断言整体包在 `filepath.Separator == '/'` 里，**Windows 上该分支被跳过**——本机全绿不代表 CI 绿。

#### GOTMPDIR 会架空用例级 TMPDIR 覆盖（已提 issue #19480）

维护者用 `t.Setenv("TMPDIR", "/var/tmp")` 满足 A 组前提，但这句只在 `GOTMPDIR` 为空时有效：
`t.TempDir()` → `c.makeTempDir()` → `os.MkdirTemp(os.Getenv("GOTMPDIR"), pattern)`
（`$GOROOT/src/testing/testing.go`），仅当 `GOTMPDIR` 为空时 `os.MkdirTemp` 才用 `os.TempDir()`
（`$GOROOT/src/os/file_unix.go:390` 的 `tempDir`，**不缓存** `TMPDIR`）。

**两向对照实验（与平台无关，可在 Windows 复现）**——同一测试跑两次，只差 `GOTMPDIR`：

```text
A) GOTMPDIR=""          → t.TempDir() = <系统临时目录>/TestTempDirHonorsGOTMPDIR3895509988/001
B) GOTMPDIR=<自定义目录> → t.TempDir() = <自定义目录>/TestTempDirHonorsGOTMPDIR4182409269/001
                          （用例内 TMPDIR="…/forced" 被忽略）
```

`cmd/go` 自身不写 `GOTMPDIR`（`cmd/go/**` 内无写入点，只经 `cfg.Getenv` 读取），
所以这是**条件性**触发，不是必然——但一旦触发，失败信息完全看不出与环境变量有关。

**残留缺陷的完整清点（已提 issue #19480，24 小时内第 5 条）**：
① 不预设 `TMPDIR` 时按文档命令跑 `go test ./...`，Linux 上必红 10 个用例，且报错指向 Obsidian 校验而非夹具位置；
② `GOTMPDIR` 非空时用例级覆盖静默失效（上面的实验）；
③ A 组断言在 Windows 被平台守卫跳过；macOS 的 `TMPDIR` 默认 `/var/folders/…` 同属 `/var` 前缀、
按同一机制会红，而文档只写了 Linux（此条**未在 macOS 实机验证**，属机制推断，报告中已如实标注）。

**修复趋势**：维护者对 #19472 的处置是「让环境满足夹具」（CI 设变量 + 单用例再设回去），
而不是「让夹具自足」。这类修复的特征是**把测试正确性外包给环境配置**，
代价是同一命令在开发机与 CI 上结论不同。审查这类修复时，应逐一问：
「换一台机器/换一个默认值，这条断言还成立吗？」「覆盖它依赖的那个前提，有没有被显式断言过？」



#### 第十一轮的方法论教训

1. **「同一算子的多条实现路径」是 P11/P12 之外的新入口，比跨仓比对省力**。本轮无需跨语言、跨包，
   仅在一个包内比对「枚举常量名 → 两条赋值路径」即可定位权威侧。把 `grep` 的目标从「函数名」改为
   **「枚举常量名 + 该枚举的字符串字面量」**，能同时覆盖定义点与所有消费点。
2. **整数除法是最硬的反例**。`countChecked*100/len(...)` 在 Go 中先截断，1/200 得 `0`。
   这个反例**不依赖任何单位约定**——无论维护者主张量纲是 0–1 还是 0–100，「200 条里勾了 1 条显示 0」都错。
   第五轮的教训（选「任何合理语义下都错的输入」）在本轮再次生效。**先找不需要解释就错的输入。**
3. **挑战门第二轮给出了「不要承诺一行修复」的约束**。维护者立场指出：改量纲会同时改变
   `av/sort.go` 排序、`av/filter.go` 的数值筛选阈值、嵌套汇总的 Sum/Average、`model/export.go` 导出文本。
   因此报告的建议必须写成「对齐 + 评估下游筛选语义」，而非「改一行」。
   **凡是会改变已落盘/已消费数值量纲的修复，都要先列下游消费点。**
4. **「同一个 UI 菜单项落到两个不同内核函数」是最有说服力的业务表现**。
   目标字段是复选框时，`app/src/protyle/render/av/calc.ts:169` 的菜单只给四个算子；
   同一项用于列底部计算走 `calcFieldCheckbox`（正确），用于汇总列走 `calcContents`（错误）。
   用户在同一数据集里能直接对比出 `66.67%` 与 `66`。**把「同一入口、两条后置路径」写成业务表现，比描述代码更有效。**
5. **本轮的先验收益来自「未覆盖区域清单」而非更聪明的搜索**。开扫前先排除历轮 10 组，
   再把子代理的侦察范围限定在 `export/import/template`、`flashcard/av/sql`、`card/search/history/export/protyle-render-av`
   三个从未被系统看过的区域，命中率明显高于历史轮次的散点搜索。
   **子代理产出仍只能当候选**：3 个候选里有 2 个经本上下文核对后不可达或已被上游保护。

## 第十八轮（2026-09-14）：API 契约重构（#19378）遗留的类型与契约缺陷

用户要求核查「端到端类型契约重构完成后是否还有实际问题」。范围是契约层本身：生成器、schema、路由覆盖、
跨仓产物、声明与实现一致性、请求绑定语义。

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1n（新 P38）/ D1 / G2 | 加密笔记本主密码在 API 边界被新增 `api:"trim"`：`kernel/apicontract/notebook.go:92`/`:106`/`:107` 的 `Password`/`OldPassword`/`NewPassword`，经 `kernel/apicontract/decode.go:116-121` 实现为「`strings.TrimSpace` + trim 后非空」。主密码是 `deriveKEK`（`kernel/model/crypto.go:1220`）的直接输入，无任何规范化；既有 KEK 按未裁剪的密码派生 → 首尾含空格的用户升级后无法解锁，`changeMasterPassword` 同样失败。重构前 `util.BindJsonArg(..., true, true)` 的第 4 参数是 `rejectEmpty` 而非 trim，旧 `ParseJsonArg` 函数体内无裁剪 → 规范化由契约迁移引入。实测三处 `"   "` 均返回 `Field [...] must not be empty`。附带：同一标记让 `NotebookIDRequest.Notebook` 由「非法 ID」变为「被静默接受」 | 高（机制链逐环核实 + 实测确认 trim 生效；未做端到端加密复现，需高危写入故未执行） | 已提 issue #19477 |
| — | 机械与实证核对为**无缺陷**的环节（同一批结论，供后续轮次跳过） | — | 排除，不报告 |
| 无 | 未取得其他可判定发现 | — | — |

### 本轮判为干净的环节（附实测口径，后续轮次不必重做）

1. **契约与真实响应一致**：把 `kernel/apicontract/schema.go` 的 `validate` 与 `schema_numbers.go` 的辅助函数
   忠实移植到 Python（`decodeSchemaJSON` 需 `parse_float/parse_int=Decimal`，`equalSchemaValue` 需两边同为 Decimal，
   否则类型敏感比较会误判），用 `contract_test.go` 的 16 组夹具自检 16/16 一致后，对运行中的内核探测 **145 次**
   （98 个 `body=none` 端点 + 带真实块 ID 的 `NonNullable`/`api:"nonnullable"` 端点），**0 违约**。
   必须抽样回读原始 payload 确认落在 `code=0` 分支——失败信封能轻松通过校验，会让「全部通过」失去意义。
2. **声明与实际业务错误码一致**：613 个 `contractHandler` 绑定的 handler，实际返回码与 `ErrorCodes` 声明零不一致。
   提取器必须同时支持函数字面量与**具名 handler**（`contractHandler(apicontract.X, xContract)`），
   否则会误配到同文件后面某个无关函数体，既产生假阳性也掩盖真缺陷。另一处必须排除的假阳性是 `ret.Code = 0`
   （成功路径赋值，不是错误码）。
3. **生成器无偏差**：1061 个纯对象定义，属性名集合、`required` 与 TS `?` 的可选性、属性类型文本零不一致。
4. **闭合集合完整**：`viewType` 恰等于 `av.LayoutType{Table,Gallery,Kanban}`；AV 筛选算子 17 + `""` 与 `filterenum` 一致；
   `BlockTransaction` 的 9 项 `enum=` 恰等于 `/api/block/*` 事务端点实际产出的 action 集合
   （`move` 只出现在 `moveBlock`，而它返回 `Null`，不进响应）。
5. **未靠类型抑制压平报错**：重构窗口内 `app/src` 只新增 1 处 `as unknown as`，且位于测试替身。
6. **跨仓产物同步**：petal `origin/main` 的 `types/api/index.d.ts` 与当前契约逐字节等价
   （586648 字符 / 620 路由 / 1116 类型全等），生成器 `api:check --petal` 通过。

### 第十八轮的方法论教训

1. **「有生成器 + 有 CI 门禁」不等于「已验证」**。本轮先按经验怀疑响应校验有盲区，实测后反而证明响应面很干净；
   真正的缺口在**请求绑定语义**——它是唯一「转换用户输入」的环节，而门禁只比对声明集合与产物一致性，
   不比对「解码后的值是否等于用户提交的值」。**审计适配层要问「这个转换有没有改变值」，而不只是「类型对不对」。**
2. **同一语义在旧代码里的载体常常是布尔参数名**。`BindJsonArg(..., true, true)` 的两个尾参无法从调用点看出语义，
   必须回读函数定义；而新契约把它写成具名标记后，作者容易把两个语义合并，且**旧参数名会误导判断方向**
   （`rejectEmpty` 不含 trim，但新标记 `trim` 含非空拒绝）。
3. **本地跨仓引用会伪装成漂移**。首轮比对 petal 生成物「缺 370 KB」，实为本地 `origin/main` 落后 97 个提交；
   `git fetch` 后差距归零。**跨仓核对前必须先 fetch**，否则会把「本地引用过期」报成跨仓不同步。
4. **提取器缺陷会同时制造假阳性与假阴性**。误报 `/api/network/echo` 有 9 个未声明错误码，根因是提取器只认函数字面量；
   同一缺陷还会让真正的具名 handler 完全不被检查。「差集很大」或「结果异常干净」时都要先怀疑提取器。
5. **零副作用的密码学路径取证**：用**全空格密码**探测，输入校验在进入模型层之前就返回，
   不接触任何密钥材料、不触发 Argon2id、不产生写入。这类「预期失败」的输入是加密相关代码最安全的探针。
6. **第三方 Python 校验器不可用时，移植 + 自检是可行路线**。本机无 `jsonschema`，但**不能**直接 `pip install`
   （仓库校验器是自定义子集：类型敏感的 `equalSchemaValue`、`minItems`/`maxItems` 与 `anyOf` 语义都与 JSON Schema 有差异），
   移植后用 Go 侧原有夹具自检，比引入一个语义不同的库更可靠。
## 第十九轮（2026-09-14）：多语言文档漂移（新判据 D3d + 模式 P39，已提 #19482）

范围：`docs/` 下 10 组多语言文档。工具：新增 `scripts/scan_doc_parity.py`（本轮为此功能而写）。

### 确认的发现（3 处，均已提 issue #19482）

| # | 缺失内容 | 引入提交 | 证据 |
|---|---|---|---|
| 1 | 「渲染模板」节的 `mode` 参数与整个 `docTreePlan` 返回值 | `b1da7c0e74` 2026-08-30（#18119 模板创建子文档树） | `API.md:1333` 该节 61 行；`API.zh-CN.md:1329` 26 行；`API.ja.md:1311` 27 行 |
| 2 | 整个 `### TypeScript contracts` 节 | `0627dd6a2a` 2026-09-12（#19378 端到端类型契约） | `API.md:122` / `API.zh-CN.md:122` 均有；`grep -c 'TypeScript' API.ja.md` = 0 |
| 3 | CI 运行说明 2 段（`TMPDIR` 要求 + 前端测试发现范围与 `app/build` 排除） | `a846821ec2` 2026-09-14（#19472 全量跑 CI） | `API-CONTRACTS.md:166`、`:168`；中文版从 L164 直接跳到下一段，`grep -c 'TMPDIR'` = 0 |

附带一处格式不一致（严重度低）：`docs/SY-FORMAT.zh-CN.md:670` 的 `TextMark` 丢了反引号
（英文版 `SY-FORMAT.md:671` 为反引号包裹的 `TextMark`）。

### 关键前提（先验证，否则判据完全不同）

`docs/API*.md` **不是生成物**。`kernel/apicontract/cmd/apigen/main.go:82-86` 只写三个产物：
`app/src/types/api/index.d.ts`、`kernel/apicontract/schema.json`、petal 的 `types/api/index.d.ts`。
三语 API 文档是**手写、各自维护**的，因此语言版本间的漂移不会被任何生成步骤或 CI 发现。

### 工具误报率与四类假阳性（全部实测）

首版扫描报「5 组有差异 / 30+ 条标识符缺失」，逐条回读后**只有 3 处是真缺口**，其余全部是翻译差异。
四类假阳性及修法：

| 假阳性 | 实例 | 修法 |
|---|---|---|
| 占位符名被译 | `<relative-path>` 与 `<相对路径>`、`<ancestorID>` 与 `<父ID>`、`<workspace>` 与 `<工作区>` | 归一化：`<...>` 统一成 `<>` |
| 代码示例的实参名被译 | `filepath.Base(path)` 与 `filepath.Base(路径)` | 归一化：只保留被调名 |
| 自然语言示例路径 | `/Parent/Child/Current` 与 `/父标题/子标题/当前标题` | 整类排除（真实路径段几乎全小写） |
| 交叉引用被本地化 | 中文版指向 `X.zh-CN.md`（**正确行为**） | 配对抵消 |

**两个「修法自身出错」的陷阱**（都由负向验证暴露）：

1. **示例路径规则必须在归一化之后判定**。第一版按原始值判定，只丢掉了英文形式、留下中文的 `/#/#/#`，
   规则自身变成不对称的——报出「`<>/` 有而本版无」与「`/#/#/#` 本版有而基准无」这对假差异。
2. **分桶要按归一化后的值**。第一版按原始值判「是否含空格」，`<>/data/<>/`（英）与
   `<>/data/<>/`（中，占位符内含空格）落入不同桶，两边明明相等却报成缺失。

归一化后：假阳性清零，**4 / 10 组有差异**（其中 3 组是真缺口所在，1 组为格式类低置信项）。

### 两者的盲区互补（本轮的判据校准）

| 手段 | 抓到 | 漏掉 |
|---|---|---|
| 结构指纹（各级标题数/围栏数/表格行数） | `API.ja.md` 的 `###` 少 1 个，据此定位到缺整节 | `API.zh-CN.md` 标题数与英文版**相同**，只缺节内 4 个标识符 |
| 语言无关标识符（反引号内，归一化后） | 上述 4 个标识符 | 「整节都在但全部被改写」 |

**两类都留，缺一会漏掉其中一半。** 这与判据 F「条数不等于工作量」是同一类经验：
单一机械手段的盲区必须用另一种手段补，而不是调阈值。

### 第十九轮的方法论教训

1. **脚本输出是候选，回读才是结论**。首版输出里 3 组「高置信标识符缺失」回读后全是翻译选择。
   若直接据脚本输出报 issue，会把「译文如此」报成缺陷，被维护者一句驳回，且损害后续报告的可信度。
2. **修假阳性要在正确的层次上修**。「把含 CJK 的值剔除」看似干净，实际是把中文版整条丢掉、英文版留着，
   于是产生「有而本版无」——**正确做法是归一化（名字不要求一致、结构必须一致），不是过滤**。
3. **规则写完后要做对称性检查**。「只对英文形式生效」的规则会产生成对假差异；发现一对
   「X 缺失 + Y 多余」且 X、Y 语义相同时，先怀疑规则不对称。
4. **写工具的负向验证要证明用例承重**。本轮验证抵消规则时写了三版补丁才得到能测出「语言匹配」条件的那个：
   第一版两种逻辑下结果相同、第二版分支永不触发。已写入维护规范第 12 条。
5. **低可见性是本项最大的特征**：文档漏项没有任何运行期信号、没有测试、CI 也不比文档，
   读者只会「不知道有这个功能」而不会报 bug。这类只能靠机械比对。

## 第二十轮（2026-09-14）：UI/UX 层面整合（新判据 I + 模式 P40 + 层面 L11）

### 起因：一个量化出来的空白

`evidence.md` 早就记录了提交分类：**bug fix 1025（41%）/ UI/style polish 823（33%）**。
本 skill 的判据与实例几乎全在 bug fix 一侧，**UI/style polish 是零覆盖**——
33% 的提交类别从未被任何判据覆盖，而它恰恰符合本 skill 的核心定义
（「单侧看着都对，只有交叉或跨状态才暴露」）。

### 关键设计判断：UI/UX 不是同质的，只有一半属于本 skill

| 半区 | 内容 | 归属 |
|---|---|---|
| **外观/风格** | 配色、间距、字体、图标风格、动效曲线 | **不属本 skill**（`description` 已声明 NOT for style）。需要设计审查与视觉对比工具，是另一套方法论 |
| **行为/契约** | 状态覆盖、交互态残留、焦点与键盘可达性、文本膨胀、破坏性操作确认 | **正是本 skill 的命题** |

**边界划错的两种代价**：把外观纳进来会让本 skill 退化成「什么都管」的清单；
把行为也排除掉则丢掉 33% 的提交类别。因此判据 I 开头即写明边界，并要求
**不得用审计者的个人偏好当预期依据**（「我觉得应该加确认框」不是缺陷）。

### 新增判据 I 的五个检查点，及其与既有判据的关系

| 检查点 | 与既有判据的关系 |
|---|---|
| I1 状态矩阵漏项（空/加载/错误/只读/超长） | UI 层的 **D3**（闭合集合漏项） |
| I2 交互态残留（loading/disabled/遮罩/拖拽占位） | **C 的镜像**——C 问「该保的有没有保住」，此问「该清的有没有清掉」 |
| I3 焦点与键盘可达性 | **全新推理形态**：功能存在但用户够不到。不是对称性问题 |
| I4 受约束容器中的文本膨胀 | 跨 i18n × UI（A 与 I 的交叉） |
| I5 破坏性操作确认不一致 | UI 层的 **D1**（同族不对称） |

**写明这种映射关系是刻意的**：让审计者知道 I1/I5 可以直接套 D1/D3 的检查法，
而 I2/I3 需要新的取证手段（真实渲染 + 键盘）。

### I4 的实测数据（本轮唯一机械化的部分）

`scan_i18n_text_expansion.py`，判据是「英文长度 4–12 且长度比 ≥2.0」：

| 语言 | 长度候选 | 经源码核对后确认 |
|---|---|---|
| zh-CN / zh-TW | 2 / 2 | 极少 |
| ja | 1 | 少 |
| ko | 4 | 少 |
| tr | 59 | 部分 |
| ar | 76 | 11 |
| de / es | 84 / 84 | 部分 |
| fr / ru | 88 / 88 | 部分 |
| **合计** | **488** | **70** |

**两条关键结论**：

1. **语言分布本身就是证据**：CJK 语言 1–4 个候选，拉丁/西里尔/阿拉伯语 59–88 个。
   同一个布局缺陷**只在一半语言下显形**——只在自己惯用的语言下审计会完全漏掉本层。
2. **不做源码交叉核对就没有可用性**：488 条无法逐条读。加上 `--source` 后按
   `<option>` / `nowrap` / `ellipsis` / 同行固定宽度过滤，收敛到 70 条（86% 是噪声）。
   负向验证确认了这一过滤是承重的：退化为「全部视为受约束」后候选从 70 涨到 409。

**实证案例**：历史面板的操作筛选 `<select>`（`app/src/history/doc.ts:183-187`、
`app/src/history/history.ts:534-540`）有 7 个 `<option>` 取自 `history*` 一族键，
英文值都是单个动词（4–7 字符）；`<option>` **不换行**，而：

| 键 | en | de | ar |
|---|---|---|---|
| `historySync` | `sync` (4) | `synchronisieren (sync)` (22) | `مزامنة (sync)` (15) |
| `historyOutline` | `outline` (7) | — | `الخطوط العريضة (outline)` (26) |
| `historyUpdate` | `update` (6) | `aktualisieren (update)` (22) | `تحديث (update)` (16) |

**这一条仍标注为「候选」而非「已确认缺陷」**：`<select>` 若无固定宽度会自行变宽，
是否真的溢出取决于 CSS。这正是脚本输出的定位——它负责把 488 条缩到 70 条可读的候选，
结论必须回读样式得出。

### 第二十轮的方法论教训

1. **「占 33% 提交的类别零覆盖」比「某个判据不够细」严重得多**。此前的优化都在既有判据内
   做增量（D1b…D1n、G3、G4、D3d），从未回头核对**提交分类与判据覆盖是否对齐**。
   `evidence.md` 里的分类数据一直都在，只是没人拿它去质问覆盖度。
2. **「加一个判据」要先答「它和既有判据是什么关系」**。本轮把 I1/I5 明确定位为 D3/D1
   在 UI 层的实例、I2 为 C 的镜像、I3 才是全新形态。不写这层映射的话，
   审计者会重复发明 D1 的检查法，或者误以为 I3 也能靠 grep 做。
3. **没有既有校验器的层面值得单列**。L11 的「既有校验器」栏如实写「**没有**」——
   `tsc` / `eslint` / 单测都不看 UI 行为。这不是缺陷，而是本层需要独立取证方法的理由。
4. **断言与实现的格式漂移会伪装成脚本故障**。自检里断言用半角冒号、脚本汇总行用全角，
   导致一次假失败。已改用字符类 `[：:]` 兼容两者——**断言里的字面格式是脆弱点**，
   凡跨「脚本输出 → 断言解析」的边界都要放宽字符集。

## 第二十一轮（2026-09-14）：整合外部 UI/UX 与无障碍实践

上一轮新增了判据 I 与层面 L11，但只机械化了 I4（文本膨胀）。本轮把外部实践中
**能落进本 skill 边界**的部分整合进来，并修掉上一轮留下的一个工具盲区。

### 第一步的取舍：从外部 UI/UX 来源里只取「行为」那一半

外部候选很多，但大多数属**外观设计**，与本 skill 的 `description`（NOT for style）冲突。
逐个判定的结果：

| 来源 | 采纳 | 理由 |
|---|---|---|
| `github/awesome-copilot` 的 `a11y.instructions.md`（MIT） | ✅ 反模式的**语义/ARIA/键盘焦点**三类 | 有明确检出手法与严重度，且属行为 |
| 同上 | ❌ 其 **V（视觉与颜色）/ D（媒体）** 两类 | 对比度、配色区分度、字号可缩放、字幕——需颜色计算与视觉基线，取证手段完全不同 |
| `accessibility-runtime-tester.agent.md`（MIT） | ✅ 键盘优先的测试流程 + 两条硬约束 | 直接服务 I3 的取证 |
| `web-design-reviewer`（MIT） | ⚠️ 只借「截图前后对比 + 一次只修一个问题」的工作方式 | 其检查项多为配色/间距/视觉一致性，属外观 |
| `anti-ui-slop`（MIT） | ❌ | 核心是「用真实界面参考做视觉设计」，且需付费 UIZZE MCP |
| `premium-frontend-ui` / `penpot-uiux-design` / `gsap-framer-scroll-animation` | ❌ | 动效与视觉设计实现指南 |

**采纳的两条硬约束（写进判据 I3）**：
① **不得把推测的辅助技术行为当作事实**——没有运行期证据只能写「需确认」；
② **「Lighthouse / axe 通过」不是无障碍的证明**，静态语义正确也不代表运行期没问题。

### 新增扫描器：三层降噪，缺一层就不可用

`scan_a11y_antipatterns.py`，实测数据（`app/src` 837 文件 + 56 个 SCSS）：

| 检查项 | 原始命中 | 经降噪 |
|---|---|---|
| K2 正整数 `tabindex` | 0 | 0（干净） |
| K5 `outline:none` 无同选择器替代 | 35 处 `outline: none` | 候选 27 → **18 确认 / 8 容器** |
| A6 纯图标按钮无可访问名 | 261 个含 `<svg>` 的按钮 | **33 个** |
| A2 `aria-hidden="true"` | 8 | **8 处全在装饰性 `<svg>`/`<span>` 上，用法正确，零缺陷** |
| 提示位点（需人工） | — | 143 |

**三次降噪，每一次都必要**：

1. **不看原始计数**。第一次粗扫得到「539 个 click 监听」，其中绝大多数在真按钮上，全是噪声。
2. **按选择器分块**（K5）。`outline: none` 在不同选择器里含义不同，要先看同选择器有无 `:focus` 替代。
3. **再用源码交叉核对**（K5）。**这一步最关键**：`outline: none` 写在**容器**上是无害的，
   只有写在**可聚焦元素**上才是缺陷。被剔除的 8 个全是容器类（`.av` / `.emojis` / `.b3-form`）。
   不做这层就会把它们报成缺陷——而这正是上游 a11y 文档警告的「把推测当作事实」。

### 修掉上一轮自己的盲区：I4 只在 TS 里找约束

上一轮的 `scan_i18n_text_expansion.py` 用 `--source` 核对「使用点的同一行是否含
`nowrap` / `ellipsis` / 固定宽度」。**这个假设是错的**：真实约束写在样式文件里。
本轮实测 SiYuan 的 `app/src/assets/scss/`（56 个文件）：

| 声明 | 处数 |
|---|---|
| `white-space: nowrap` | 70 |
| `text-overflow: ellipsis` | 39 |
| 固定 `width: <n>px/rem/em` | 340 |

新增 `--styles` 后从 SCSS 反推出 **107 个受约束类名**，候选由 70 增至 **80**。

**方法论意义**：这是「工具自身的盲区」而不是「候选不够多」。上一轮我在 `stack-map`
里写了「`--source` 强烈建议提供」，却没验证它是否真的覆盖约束来源——
**声明一个检查有效，与验证它有效，是两件事**。

### 附带发现：样式位置容易找错

`app/appearance/themes/` 下只有 `daylight/theme.css` 与 `midnight/theme.css`，
各约 10KB / 245 行，**且 `outline` / `:focus` 出现 0 次**。只扫这个目录会得出
「本仓库没有焦点相关 CSS」的错误结论。真正的主样式在 `app/src/assets/scss/`
（sass-loader + MiniCssExtractPlugin 编译）。已写入层面地图 L11。

### 第二十一轮的方法论教训

1. **整合外部实践的第一件事是划边界，不是抄内容**。外部 UI/UX 来源里真正能落进本 skill 的
   只有「行为」那一半——键盘可达性、焦点管理、ARIA 语义、状态宣告。外观那一半
   （对比度、配色、动效）**必须明确排除并写下理由**，否则本 skill 会退化成什么都管的清单，
   而两类内容的取证手段（颜色计算 vs 走键盘流程）本就不同。
2. **拒绝也要记录理由**。未采纳的四个来源与理由写进了 `stack-map` 的「来源与许可」——
   否则下一轮会重复评估同一批候选。
3. **「声明检查有效」不等于「验证它有效」**。I4 的 `--source` 上一轮就写了，
   但从未验证约束的真正来源；本轮才发现它在样式文件里。凡在自己的文档里写
   「建议提供 X」，都要问一句「不给 X 会漏什么、漏多少」。
4. **自检里的断言可能静默消失**。K5 的容器筛选断言原先写成 `if m and c:`——
   正则一旦失配（输出格式改了）整条断言就不执行，自检仍然全绿。
   已改为先**无条件**断言「两条计数行都能解析」，再比较。这与「两个重叠守卫无法分别验证」
   是同一类问题：**断言的存在性本身要断言**。

## 第二十二轮（2026-09-14）：设计令牌契约与「组件化」的量化证伪

**起因**：用户要求整合「组件化 / 设计组件 / 设计交互」类 UI/UX skill。
上一轮整合的是 UI/UX 的**行为**半区（无障碍、状态、焦点、文本膨胀），
本轮要处理的是**组件架构与设计系统**半区。按既有方法论：先量化，再决定挂接还是新增。

### 一、「组件化」在本仓库不构成可检缺陷类（量化证伪）

| 探针 | 实测 | 结论 |
|---|---|---|
| 重复 HTML 片段（≥4 次） | **264 种**，但靠前的全是自带工具类：`fn__space` 526 次、`fn__hr` 179、`fn__flex` 116、`fn__flex-1` 105、`b3-list-item__text` 156 | 与误报表已有的「UI 类名/选择器」同类，**不新增判据** |
| 组件调用点属性集形态 | `.b3-switch` 25 种、`.b3-button` 87 种，看似漂移严重 | 逐条看：差异几乎全是调用点各自的 `data-*` 标识（合法） |
| 契约属性的实际覆盖率 | `.b3-switch` 的 `type` **114/114**、`.b3-tooltips` 的 `aria-label` **159/159** | 契约执行得很齐 |
| 是否存在契约属性 | `.b3-button` / `.b3-label__text` / `.b3-dialog__action` / `.b3-select` / `.b3-menu__item` / `.b3-list-item__text` **都没有** | 契约就是那个 CSS 类本身 |
| 组件目录 / 注册表 / 组件文档 | `components.json`、`COMPONENTS.md`、`catalog`、`designTokens` 全部**无命中** | 依赖组件目录的 skill 无可挂接对象 |

**结论**：本仓库用 CSS 类作组件、模板字符串手写 HTML，**「没抽成 TS 组件」是设计意图而不是缺陷**。
因此不建扫描器、不新增判据，只把量化结论与「覆盖率分离法」写进误报表与层面地图。
**这也是「拒绝要记录理由」的又一次应用**——不记下来，下一轮会重新评估同一批候选。

### 二、设计令牌（CSS 自定义属性）契约：三条件合取

| 条件 | 含义 |
|---|---|
| ① 引用侧无 fallback | `var(--x)` 而非 `var(--x, #fff)` |
| ② 所有样式根（**含主题目录**）无 `--x:` 定义 | 主题是令牌的合法来源 |
| ③ 源码里从未提及 | `setProperty` / `removeProperty` / 样式对象键 / 内联 `style` / `cssText` / 模板串 / 注释 |

实测 SiYuan（`--styles` 两个根 + `--source app/src`）：

```
引用到的令牌 192（无 fallback）     ← 条件 ① 之后
  条件 ② 排除 167（样式里有定义）
  条件 ③ 排除  20（写入形态）+ 3（仅源码提及）
  另有 fallback 引用排除 5
  → 候选 2 条
```

**只做条件 ①② 时得到 34 条候选，逐条回读后 17/17 全是假阳性。**
即 **CSS 自定义属性在本仓库是 JS→CSS 的运行时通道**：

```ts
htmlTarget.style.setProperty("--drag-indent", `${indent}px`);        // listDragTarget.ts:52
["--b3-table-frame-left", …].forEach(n => action.style.removeProperty(n)); // tableControl.ts:1277
protyle.element.style.setProperty("--b3-width-protyle-wysiwyg", w + "px"); // initUI.ts:440
```

`removeProperty` 也算写入——**清理调用本身就是该变量存在的证据**。

**条件 ③ 用宽规则是被一次漏检逼出来的**：窄的形态匹配把 `--b3-font-family-editor`
报成候选，而它与 `--b3-font-size-editor` 写在**同一个注入的 CSS 模板串**里
（`util/assets.ts:404` 起），带 backtick 锚点的规则抓不到同串第二个变量名。
改为「源码里任何位置提及过即算」后修复。**教训：形态匹配只用于输出说明，排除判定要用宽规则。**

### 三、两条残留候选都是死规则

`app/src/assets/scss/pdf/_pdf.scss` 是从 Mozilla PDF.js 移植的（文件头 Apache-2.0）。
`--loading-icon` / `--main-color` 在 PDF.js `viewer.css` 的 `:root` 里定义，移植时未带上，
被脚本正确列为候选。但：

- `.toolbarField.pageNumber.visiblePageIsLoading` 的类名 `visiblePageIsLoading` 在全仓出现 **0 次**
- `#errorWrapper` 只在模板里出现一次且写死 `hidden='true'`，无任何 JS 取消隐藏

→ 按既有标准属「无消费方即无业务表现」的**观察项**。**判移植文件的令牌缺口前，先确认引用方是否还在。**

### 四、修掉一个自己的真缺陷：跨盘崩溃

`scan_a11y_antipatterns.py`（5 处）与 `scan_i18n_text_expansion.py`（1 处）写的是
`os.path.relpath(p)` —— 不传 `start` 时以 **cwd** 为基准。当扫描根在另一个盘
（Windows 上 `d:\...` 与 `c:\...`）时直接抛：

```
ValueError: path is on mount 'd:', start on mount 'C:'
```

**整个脚本崩溃、一条结论都输不出。** 该缺陷长期存在而未被发现，
因为自检恰好在与仓库同盘的 cwd 下跑过——**测试结果依赖 cwd 的通过是假通过**。
统一改为以扫描根为 `start` 的 `rel_path(path, roots)`，并加第 11 组自检（异盘 cwd）。

### 第二十二轮的方法论教训

1. **「用户要什么」与「仓库里有什么可检的」是两件事**。用户要「组件化」，
   而量化显示本仓库的组件约定执行得很齐、且依赖组件目录的做法在这里没有载体。
   正确产出是**一个带数据的否定结论 + 一套可复用的分离方法**，不是硬造一个判据。
2. **一个「新维度」往往要求把检查拆分到不同层次**。「设计交互」的组件状态覆盖
   在 CSS 侧可检，但**取证前提错了就全错**：`.b3-button` 按选择器文本判为
   「缺 hover / active / focus」，按大括号配对后它实际拥有 `:active,:disabled,:focus,:hover`
   ——因为 SCSS 的状态样式主要写成嵌套的 `&:伪类`，选择器文本里**不含组件类名**
   （全仓嵌套 `&:hover` 154 处、`&:focus` 32 处、`:active` 16 处、`:disabled` 7 处，
   嵌套是主流写法）。
3. **排除判定要用最宽的规则，输出说明可以用窄的形态匹配**。窄规则漏了
   `--b3-font-family-editor`（同一个注入 CSS 串里的第二个变量名）。
   凡「排除某人」的判定，宁可宽一点——**宽了只是少报，窄了会假报**。
4. **两条断言在负向验证中被发现不承重**（这是本轮最有价值的自查）：
   - 第 11 组原只测「不崩」，但带 `try/except` 的退化会「吞掉异常 + 返回绝对路径」，
     脚本不崩 → 用例看起来漏过。补测「输出不含绝对路径」。
   - 第 10 组原断言「条件 ③ 排除 > 0」，而那实际测的是**窄**规则（`writes`）；
     把宽规则关掉后它照样通过。改断言宽规则本身，并把阈值从
     「< 无 fallback 总数」收紧为「< 1/10」。
   **断言选错对象时，负向验证才是唯一能发现它的手段。**
5. **负向验证的补丁要按函数体打**。想把 `rel_path(path, roots)` 退化成
   `os.path.relpath(path)` 而做整串替换时，**定义行 `def rel_path(path, roots):` 也含这个子串**，
   被一起改成 `def os.path.relpath(path):` → import 期 `SyntaxError`，
   后续组根本没跑到。用例确实「失败」了，**但失败的原因不是你以为的那个**。
6. **补丁必须真的复现原缺陷形态**。我给 `rel_path` 加了 `try/except ValueError` 作为兜底，
   于是「退回不传 start」的补丁被 try 吞掉、退化成「返回绝对路径」→ 不崩 → 用例看起来漏过。
   **补丁没复现原缺陷，用例就不承重。**

### 本轮的未决事项

- ~~本轮的扫描器产出极低，保留它的理由是降噪规则可复用~~ → **已在第二十三轮移除**
  （用户定调：零产出的脚本不该进 skill）。检查法改写为纯文字判据，见下。
- 尚未处理：用户提过的「测试有效性（变异测试思路）」——G3/G4 只查「有没有测试」「在不在 CI」，
  不查「测试能不能发现缺陷」；以及性能维度（`性能`/`基准` 在 `SKILL.md` 里 0 命中）。

## 第二十三轮（2026-09-14）：按「零产出不进 skill」的标准移除脚本

**触发**：用户定调「零产出的脚本不该进 skill」。

**移除了什么**：`scripts/scan_css_token_contract.py`（第二十二轮加入）。
它在目标仓库降至 2 条候选、回读后 0 条真缺陷。

**边界：移除的是脚本，不是知识**。三条件合取规则、条件 ③ 的宽规则教训、
两条死规则的案例全部保留，只是从「可执行」改写为「可阅读」：

| 保留在哪 | 保留了什么 |
|---|---|
| `SKILL.md` 判据 I 的「CSS 侧取证的两条硬前提」 | 三条件合取 + 条件 ③ 必须用宽规则（含 `--b3-font-family-editor` 漏检案例） |
| `known-false-positives.md` 三条条目 | 运行时通道、调用点属性差异、移植样式的引用方已裁剪 |
| `stack-map.md` L11 的既有校验器 + 取证陷阱 | 五种 JS 写入形态清单 + 三条件检查法与实测数据 |
| `evidence.md` 第二十二轮 | 全部实测数据与六条方法论教训 |

**新增一条准入标准**（写入 `SKILL.md` 的脚本清单）：
脚本的价值要按**在目标仓库的产出**衡量，不是按它的规则有多启发性。
一个规则换成「一两条还要人工回读的候选」，它就是文档而不是脚本；
脚本位与维护/自检成本是实成本。
附带写下：**「值得知道」与「值得自动化」是两件事**。

**顺带发现的两处小问题**：

1. `test_scan_scripts.py` 的组号**从 [3] 直接跳到 [5]**（原 [4] 组已并入 [3]，但没有记录）。
   跳号会让人以为漏跑一组。按既有「编号只增不重排」约定（同 patterns 的 P33 空缺）
   **不重排**，改为在 docstring 里显式登记这个空档。
2. docstring 里的 `d:\...` 触发 `SyntaxWarning: invalid escape sequence`。
   改为不带反斜杠的写法（如仓库在 `D:` 而 skill 在 `C:`）——
   普通字符串里的 Windows 路径写法**必须转义或避开**。

## 第二十四轮（2026-09-14）：补齐「组件化 / 设计系统 / 交互设计」半区

**起因**：用户质疑「整合 UI UX skill 是不是一直都没做」。先量化覆盖，再补做。

### 一、量化：确认两处失败

| 维度 | 全 skill 命中 | `SKILL.md` | 判定 |
|---|---|---|---|
| 无障碍 a11y | 106 | 17 | 做了 |
| 焦点与键盘 | 185 | 36 | 做了 |
| 反馈 / 撤销 | 183 | 31 | 做了 |
| 状态矩阵 / 交互态残留 | 22 / 24 | 4 / 4 | 只有判据文字 |
| 设计令牌 | 34 | 4 | 只剩文字（脚本上轮删了） |
| **组件化** | **8** | **1** | **`SKILL.md` 那 1 处是否定结论** |
| **组件设计 / 设计系统** | **12** | **0** | **热路径里完全不存在** |
| **交互设计** | **4** | **2** | 几乎没做 |

**两处失败**：

1. **过度推广**：第二十二轮用弱探针（只查「重复 HTML 字符串」）就断言
   「组件化不构成可检缺陷类」。那个探针只能否掉「组件抽取」这一种形态，
   却被写成了整个维度的结论。
2. **更严重：发现方法学陷阱后没有改正重测**。判「组件状态覆盖」时用
   「选择器文本里是否含组件类名」判定，而 SCSS 的状态主要写成嵌套 `&:hover`
   （选择器文本不含类名）。我发现并记录了这个陷阱，**然后把这一维度丢掉了**。
   正确做法是改正方法重跑。

### 二、补闭环：把上一轮的候选变成发现

上一轮工具已产出候选（K5 18 条「确认」、A6 31 条），但**一条都没有变成发现或 issue**。
本轮逐条回读后提了两个 issue：

**#19493 —— 开关无焦点指示**

`app/src/assets/scss/component/_switch.scss:9` 的 `outline: none`（自 2022-05-26
的首次开源界面提交 `f40ed985e1` 起存在），而 `.b3-switch` 是原生可聚焦的
`<input type="checkbox">`（约 28 处使用），全仓 `:focus` 规则 **0 条**。

运行时取证（运行中的 3.8.4-alpha.9，真实渲染环境）：

| 元素 | 可聚焦 | 聚焦后计算样式变化 |
|---|---|---|
| `.b3-button` | 是 | 1 项（两层阴影） |
| `.b3-text-field` | 是 | 1 项（`rgba(53,117,240,.38) 0 0 0 .6px` 环） |
| `.b3-select` | 是 | 1 项（内阴影 + 蓝环） |
| **`.b3-switch`** | **是** | **0 项** |

并排除了「`:focus-visible` 有兜底但未触发」：聚焦时 `matches(":focus-visible")`
为 `true`，伪类确实命中，只是没有规则响应它。

**#19494 —— 图标按钮无可访问名（37 处）**

四处都是**同一段模板里部分按钮有可访问名、其余没有**的同族不一致：

- `mobile/util/keyboardToolbar.ts:1396-1434` 28 个按钮仅有 `data-type`，
  而**同一模板的 1414-1415 行**写了 `aria-label`
- `protyle/toolbar/index.ts` 7 个（`:2374/2376/2377/2381/2382/2388/2474`），
  而**同一模板的 `:2385`** 有 `aria-label`、`:2468/2470/2472` 用 `<span>` 提供可见文本
- `dialog/remoteConnection.ts:42`、`protyle/render/av/newItemTemplate.ts:148`

### 三、系统性根因（作为评论补到 #19493）

`util/_reset.scss:287-296` 对 `button, input, select, textarea` **一律 `outline: none`**：

```scss
button,
input,
select,
textarea {
  margin: 0;
  font-size: 100%;
  vertical-align: middle;
  font-family: var(--b3-font-family);
  outline: none;
}
```

因此**焦点可见性完全依赖每个组件自己定义 `:focus`**。全仓不存在全局兜底
（解析后「无祖先」的焦点规则为 **0 条**）。已定义的有 `.b3-button` /
`.b3-text-field` / `.b3-select` / `.b3-slider`。

量化（按元素上的**完整类集合**判定）：

| 项 | 数量 |
|---|---|
| 表单控件使用点总数 | 1103 |
| 有焦点指示 | 641（58%） |
| **无焦点指示** | **462（42%）** |
| 其中 vendored PDF.js | 39 |
| **SiYuan 自研代码** | **423** |

自研代码前几位：`.b3-switch` 112、`.b3-menu__item` 63+、`.keyboard__action` 38、
`.b3-menu__separator` 35、`.color__square` 22、`.keyboard__slash-item` 21、
`.b3-form__upload` 20、`.block__icon` 家族约 20、`.b3-list-item` 7。

`.b3-menu__item` 也做了运行时验证：可聚焦、`:focus-visible` 命中、聚焦前后**零变化**，
且真实菜单项的 `tabindex` 为 `null`（未被设为 `-1`）。

### 四、新增 `scan_focus_coverage.py`

**它的核心价值是四个判定前提——四个都是我实测写错过才对的**：

| 陷阱 | 错误做法 | 后果 | 正确做法 |
|---|---|---|---|
| SCSS 嵌套语义 | 只替换 `&` | 不含 `&` 的子选择器是**后代**，祖先被丢掉 → `.protyle-preview__action button:focus` 被读成全局 `button:focus`，局部规则被当成全局兜底，**真缺口被判成「已覆盖」** | 含 `&` 替换，不含 `&` 则 `父 + " " + 子` |
| 焦点指示的形态 | 只看 outline/box-shadow/border/background | 漏掉 `transform` → `.b3-slider` 被误报成缺口 | 把 `transform`/`filter`/`opacity`/`color` 一并计入 |
| 判定单位 | 按**单个类**查 | 焦点样式可能来自兄弟类（`.block__icon.b3-tooltips` 靠 `.b3-tooltips:focus-within`）→ 误报 | 按**元素上的完整类集合**判定 |
| 全局兜底 | 只看「存在原生标签的焦点规则」 | `.b3-switch` 是 `<input>`，而规则是 `button:focus`，**不匹配** | 兜底**按该元素的真实标签**匹配 |

另外把 `verdict()` 从 `main()` 提到模块级——**逻辑嵌在 `main()` 里时自检只能测副本，而测副本等于没测**。

### 五、修掉 A6 的系统性漏检

`VISIBLE_TEXT`（`>\s*[^\s<][^<]*`）会把 JS 字符串末尾的 `';` 当成按钮内文字：

```js
html += '<button class="x" data-action="copy"><svg>…</svg></button>';
//                                                          first_line 末尾是 `>';`
```

于是**单行收尾的图标按钮被静默跳过**，而多行模板（以 `</button>` + 换行结尾）正常报出
—— **同一形态的按钮，因字符串是否在同一行收尾而时报时不报**。
实测 SiYuan 的 A6 由 **37 条降到 31 条**，漏掉的 6 条里 4 条集中在
`protyle/toolbar/index.ts` 的同一个模板里。
修法是先把标签串裁到 `</button>` 为止（`BUTTON_CLOSE`）。

### 第二十四轮的方法论教训

1. **「我把这个坑写下来了」不是产出，产出是用对方法后的结果。** 发现方法学陷阱时，
   改正重测与记录陷阱是两件事，后者不能代替前者。
2. **弱探针只能否掉它真正测过的那种形态**。「只查重复 HTML 字符串」只能否掉「组件抽取」，
   不能推广成「组件化不构成可检缺陷类」——而后者被我写进了热路径。
   **否定结论也要标注它的适用范围。**
3. **工具产出候选不等于工作完成，闭环才算。** 上一轮建了工具、跑了、拿到 18 条确认候选，
   然后下一轮就去重构 skill 的文件结构了。**这是把「做工具」当成了「做工作」。**
4. **误差是叠加的**：这一轮我在同一个检查上连续犯了四个错，每个都让结论偏向
   「已覆盖」（假阴性）。SCSS 祖先丢失 → 局部规则变全局兜底；`(?!none)` 的 `\s*` 匹配空串
   → 移除轮廓被判成可见变化；按单类查 → 漏掉兄弟类；兜底不按标签 → `<input>` 被 `button` 覆盖。
   **四个错误方向一致，说明了为什么真缺陷会长期无人发现。**
5. **负向验证能发现「用例不承重」**：本轮 4 个用例里 1 个首次运行时不承重——
   夹具让被覆盖的类恰好排在字母序最前，「按类集合」与「只按第一个类」结果相同。
   换成能区分的夹具后才承重。**夹具数据必须能区分两种行为。**
6. **断言标签与夹具行号要逐一对应**：多行模板占两行，我按一行算，于是
   「有可见文本的按钮不被报出」指向了错误的行（那一行其实是图标按钮）。
   自检当场失败才暴露出来——**这正是保留「不该报出」类断言的价值。**

## 第二十五轮（2026-09-14）：定位参照帧检查点（**无确认实例**）

**起因**：上一轮结尾列出两个候选改进方向——补 I1 的实证、补 z-index/定位上下文。
本轮先做量化侦察，选择了后者：`SKILL.md` 里 `z-index` 与「定位上下文」命中数为 **0**，
而 `AGENTS.md` 第 7 条明文要求「改 `position` / `transform` / `contain` / `overflow` 时
检查对后代定位参照帧、overlay 覆盖、裁剪的影响」——是**项目自己的规范**，属现成权威依据。

### 一、属性表是实测的（纠正了三个常见误解）

本地 HTML + `offsetParent !== null` 判定，19 个用例。**会让后代 fixed 改参照帧**：
`transform` / `filter` / `backdrop-filter` / `perspective` / `contain: layout|paint|strict` /
`will-change: transform|filter`。

**不会**：`will-change: opacity` / `isolation: isolate` / `opacity: 0.99` /
`position: relative|absolute` + `z-index` / `position: sticky` / `mix-blend-mode` / `mask-image`。

**这张表最容易记错的地方**：`isolation` / `opacity` / `position + z-index`
都会创建 **stacking context**，但**不创建包含块**。把两者等同会产出大量假阳性——
判这件事只能看**包含块**。这也是我不凭记忆写表、而是搭一个本地 HTML 实测的原因。

### 二、业务表现的实测（不是推断）

同一段 CSS 的 fixed 元素（`top:0; left:0`）：

| 祖先 | `offsetParent` | 实际 `getBoundingClientRect().top` |
|---|---|---|
| 无创建包含块的属性 | `null` | **0**（视口左上角） |
| `transform: translateX(1px)` | 宿主容器 | **400**（容器位置） |

**偏了 400px**。注意 `translateX(1px)` 这种「几乎等于没有」的 transform 同样生效——
这正是它隐蔽的原因：**改动者看不出任何视觉变化，坏的是后代**。

### 三、判定方法必须有对照组

```js
[...document.querySelectorAll("*")]
  .filter(el => getComputedStyle(el).position === "fixed" && el.getClientRects().length)
  .filter(el => el.offsetParent !== null)
```

第一次在运行中的实例上跑时得到 `totalFixed=4, trappedCount=0`。
**这个「0」当时是不可信的**——同一次执行里我注入了「有 transform 祖先」与
「无 transform 祖先」两个 fixed 元素作对照，确认前者 `trapped=true`、后者 `false`，
才敢认定页面确实干净。**没有对照的「0 个」分不清「干净」与「方法失效」。**

### 四、静态规模与本仓库的隐式假设

| 项 | 数量 |
|---|---|
| 会创建包含块的声明 | `transform` 113、`filter` 21（含 `backdrop-filter` 12）、`will-change` 8、`contain` 6 |
| `position: fixed` 选择器 | 51，另有 5 处内联 |
| `position: sticky` | 16 |
| `z-index` 取值 | 24 种；动态分配基数为 **10**（`app/src/index.ts:295`），硬编码最大 `1000000` |

**隐式假设（判据 E 的形态）**：`.mobile-topbar` / `.mobile-bottom-bar` / `.side-panel` /
`.b3-menu--sheet` / `#editor > .protyle-breadcrumb` 都是移动端**容器**且带
`will-change: transform`。它们当前的后代里没有 fixed 元素，但这些属性使它们成为**禁地**——
将来在其中插入 `position: fixed` 的元素会静默跑偏。

**权威侧**：`.av__mask` 用 `document.body.insertAdjacentHTML("beforeend", ...)` 挂到 body 下
（`app/src/protyle/render/av/cell.ts:648`），在任何容器里都不会被围住。同族互查以它为准。

### 五、为什么诚实地不给它判据字母

**本轮没有找到本仓库已存在的该缺陷**。按既有规范（「从一次已确认的缺陷出发」，
与「资源与生命周期检查点」同一处理），它写在层面地图的**待实证检查点**里，
不占判据字母、不建 P 条目。

同时**不建脚本**：静态判定需要后代的 DOM 祖先链，而这在 SiYuan 由模板字符串拼装
（`insertAdjacentHTML` / `innerHTML`），无法可靠还原嵌套。运行时判定已零假阳性、
只需一次 `evaluate`——按 `SKILL.md` 的脚本准入标准（零产出或极低产出的不进来），
它更适合放在**验证闭环**里当必查项。

### 第二十五轮的方法论教训

1. **「我查了但没找到」也是一个结果，前提是把它和「我没查」区分开**。
   本轮的价值不在产出缺陷，而在：机制被实测、方法有对照组、规模被量化、
   隐式假设被点名。**下一轮命中时不必从零开始。**
2. **空白不必用判据去填**。`z-index` 在 `SKILL.md` 里 0 命中确实是个缺口，
   但「有权威依据 + 有实测方法」不等于「有确认缺陷」。**按规范放进检查点，
   比硬塞一个判据字母更诚实，也不会污染判据清单的「全部有实证」性质。**
3. **属性表必须实测**。`isolation` / `opacity` / `position + z-index` 都会创建
   stacking context——凭这个印象写表，会把三个高频属性全部误判为危险，
   而它们恰好是布局里最常用的。**一次 19 用例的本地 HTML 就解决的事，
   不要用记忆去赌。**
4. **零假阳性的判据也需要对照组**。`offsetParent` 判据本身是规范的确定行为，
   但「跑出 0 个」这个**观测结果**可能来自方法失效（选择器写错、时机不对）。
   **对照组的成本很低，缺了它整次检测的结论不可用。**

## 第二十六轮（2026-09-14）：聚焦临时展开机制（#8956 / #19483）定向审计

用户提问「目前的机制会产生 BUG 吗」。范围＝`f91cf6b9ed`（列表项）+ `60fa553984`（标题）两个提交引入的前端纯视图态机制：
`protyle/util/focusFold.ts`、`viewFold.ts` 的 loader、`heading.ts` 的 `getFocusedHeadingChildren`、`blockFold.ts` / `onGet.ts` / `destroy.ts` 的接入点。

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D3 | 自动展开的块类型集合只含 `NodeListItem`/`NodeHeading`（`focusFold.ts:41`），而仓内两处权威集合都是 **5 类**：`blockFold.ts:287` 的 `isFoldable` 与 `gutter/index.ts:3542` 的 `foldRecursive` 菜单门控（`NodeHeading`/`NodeListItem`/`NodeBlockquote`/`NodeCallout`/`NodeSuperBlock`）；CSS `_wysiwyg.scss:889` 起对 `.bq`/`.callout` 折叠隐藏第 2 个起的子块、对其余类型 `line-clamp: 1` 压成一行。用户折叠引述/标注/超级块后聚焦，仍只显示一行 | 高（内核 DOM + 真实样式产物渲染双实测；见下方取证） | 已提 issue #19498（低） |

- **业务表现**：光标放进引述块 → 块菜单「折叠/展开」→ 块折叠（只剩第一行）→ 块菜单「聚焦」→ 期望与列表项/标题一致地临时展开，实际仍是一行；全程无任何反馈。
- **预期表现的权威依据**（不是审计者偏好）：`blockFold.ts:287` 与 `gutter/index.ts:3542` 两处独立给出同一个 5 类可折叠集合，而机制自身已为其中两类实现展开。
- **修法量级同列表项**：`.bq`/`.callout`/`.sb` 折叠时子块**仍在 DOM**（内核只对标题做可见性裁剪，见 `kernel/model/render_fold_test.go` 的 `TestCleanRenderNodesKeepsFoldedContainerChildren`），因此去掉 `fold` 即可，不需要新请求、不涉及内核。


### 第 26 轮取证明细（D3，issue #19498）

三条独立证据，缺一不可（只读源码会漏掉「内核是否保留 fold」，只看 DOM 会漏掉「样式是否真的隐藏」）：

1. **内核侧**：`POST /api/filetree/getDoc {"id":<块ID>,"mode":0,"size":1000000}`（即聚焦时前端发出的请求）
   返回的根元素**仍带 `fold="1"`**，且子块全部在 DOM 里。三类块逐个实测均如此。
   → 说明前端有责任主动摘 `fold`，不是内核已经处理过。
2. **样式侧**：把上述 DOM 放进 `.protyle-wysiwyg` 容器、引入 `stage/build/desktop/base.*.css` 真实产物渲染，
   量测对照（同一 DOM、只差一个 `fold` 属性）：

   | 块类型 | 保留 `fold="1"` | 去掉 `fold` |
   |---|---|---|
   | `NodeCallout` | 高 72px，第 2、3 段 `display: none` | 三段全可见 |
   | `NodeBlockquote` | 高 42px，第 2、3 段 `display: none` | 三段全可见 |
   | `NodeSuperBlock` | 高 38px（`overflow:hidden`+`line-clamp:1` 裁掉 336px 内容） | 完整可见 |
   | `NodeListItem`（对照组） | 子列表 `display: none` | 子项全可见 |

   **超级块只有 `line-clamp` 裁切、没有 `display:none`**——只看 CSS 选择器文本容易误判它「不受影响」，
   必须量高度（38px vs 内容 336px）才能确认。
3. **前端侧**：`focusFold.ts:41` 的守卫；入口可达性由 `renderMenu`（`gutter/index.ts:1607` 起，
   聚焦项在 `:2818-2827`）确认——条件只有 `!protyle.options.backlinkData`，**无块类型门控**。

**定性要点（写 issue 时必须交代，否则会被维护者以「需求范围」驳回）**：原始需求
（#6496 / #8956 / #19483）只提「标题和列表」，且折叠的标注块聚焦后仍折叠是**改动前就有的行为**，
不是回归 → 只能写成「同族覆盖不全 / 一致性改进」，不能写成「破坏性缺陷」或「内容丢失」。

**本轮取证的两条新教训**（已写入 stack-map L6）：

- **产物新鲜度**：`pnpm dev` 只重建 Electron 的 `app` 产物，浏览器用的 `desktop`/`mobile` 不随之更新。
  实测 `desktop/main.*.js` 里 `applyFocusFold` 命中 0 → 在浏览器验证新前端逻辑会得到假阴性。
  判据：在 bundle 里 grep 新符号。**绕开办法**：把内核返回的真实 DOM + 真实 CSS 产物放进独立页面渲染，
  这样验的是「样式与 DOM 的因果」而不是「尚未构建的 JS」，不受产物新鲜度影响。
- **不要向运行中的应用发键盘输入**：`Ctrl+P` 未生效时后续键入落进文档标题输入框，把用户文档改名
  （块引用文本被内核同步改名），需用 `/api/history` 快照比对定位并还原。UI 取证用 DOM 合成 click
  或真实鼠标坐标点击（`page.hover` 在本机多次未触发块标，改用 `page.mouse.move` 两步移动成功）。

**核过但未发现缺陷的环节（后续轮次勿重做）**：

- 快照/还原：`data-view-fold-source` 与视图折叠共用，`sanitizeViewFoldHTML`（`viewFold.ts:485`）与 `clear.ts:17` 的 `clearViewState` 都会把它翻回真实 `fold`，所以复制、剪切、事务序列化都不会把临时态写进文档；`clearBlockElement` 只作用于克隆（`paste.ts:1114`、`commonHotkey.ts:332/339/377/382` 全是 clone/temp 元素）。
- 手动接管：`stopFocusFold` 由 `setFold` 的 toggle 分支（`blockFold.ts:67`）与 `prepareViewFoldTransaction`（按 op 的 fold 值）覆盖 `setFold`/`toggleListFold`/`foldBlocksRecursively`/`foldHeadingGroup` 的全部折叠写入口；`setFoldById`（远端 `unfoldHeading` 推送）用显式 `isOpen`，既不触发接管也不误清快照。
- 竞态：`generation` + `isValid()` 覆盖「加载中切聚焦 / 加载中编辑 / 元素被替换 / destroy」四种；`transaction.ts:576` 的 `invalidateViewFoldRequests` 与 `transaction.ts:614` 的 `applyViewFoldStates` 顺序保证被作废的加载在同一轮重新发起。
- 写入面：loader 只做 DOM 合并（按 `data-node-id` 去重、保留已有元素），`renderHeadingChildren` 的重渲染与 `queueHeadingNumberRefresh` 的 `/api/outline/getDocHeadingNumbers` 都是只读 →「不写文档、不产生撤销记录」成立。
- 测试：`focusFold.test.ts` + `focusHeading.test.ts` 共 18 例本地全绿；CI 前端 job 已是**全量** `pnpm test`（`.github/workflows/api-contracts.yml` 的 frontend-tests），新测试在 CI 执行 —— 早先的 G4「白名单式 CI」问题已不成立。

**观察项**（无业务表现，勿单独立项）：`data-view-heading-owner` 在聚焦路径写了但没有消费者；`restoreElement` 在退出聚焦路径上是死代码（`showAll` 只在 `onGet` 变 false，而 `onGet` 必替换内容），仅在「聚焦期间元素被替换」时生效。

**未取证候选**（勿重报，除非有新证据）：临时展开的标题子块是**异步**插入的（`viewFold.ts:161` 的 loader 内 `await fetchSyncPost`），而 `onGet` 之后同步运行的消费者仍按「DOM 已完整」假设 —— `menus/protyle.ts:1105-1132`（`zoomOut` 的 `focusId` 定位，失败才回落 `getUnfoldedParentID`）与 `setHTML` 内的滚动/光标定位是候选点；需要一条「`focusId` 落在本次临时展开区间内」的可达路径才能定性。

**取证陷阱（新，重要）**：本机 `pnpm dev` 只重建 **Electron 用的 `app` 产物**；浏览器/平板使用的 `stage/build/desktop` 与 `mobile` 产物不会随之更新。实测 `stage/build/desktop/main.*.js` 中 `applyFocusFold` / `getFocusedHeadingChildren` / `invalidateFocusFoldRequests` 命中 **0**（`data-view-fold-source` 命中，因为视图折叠是旧代码）。据此在浏览器里验证该功能会得到「完全没生效」的**假阴性**。改前端后要在浏览器验证，必须先确认对应产物已重建，或改用 Electron 端。

**方法论教训（新）**：**不要向运行中的应用发送键盘输入来导航**。本轮用 `Ctrl+P` 想打开搜索但并未打开，随后的键入落进了文档标题输入框，把用户文档「db test 2」改名成「fold focus auditdb test 2」，并新增了一个空段落（块引用文本被内核同步改名）。用 `/api/history` 的 14:22 快照比对确认改动来源后，rename 回原名 + 删除空段落，并逐项回读三个块引用（现均为 `db test 2`）。UI 取证改用 DOM 合成 click 与真实鼠标坐标点击（hover 块 → 点块标图标 → 点菜单项）。

## 第二十七轮（2026-09-14）：修 `scan_focus_coverage.py` 的双向失准

起因：`fa729c7c49`（#19493 的修复）给 `util/_reset.scss` 加了一条全局兜底，扫描器**两个方向都错**——
报出的 326 条缺口里大部分已被兜底覆盖，同时它看不到运行时赋的类名（#19499 第 2 点就是这类漏报）。
修法分三段，**每一段都对应一种已经发生的错误**。

**修法：选择器归一化 + 特异性比较 + 使用点枚举补全**（不做完整级联，不引第三方库）。
判定的问题不是「最终 outline 计算值是什么」，而是「聚焦后有没有可见变化」，
所以**只需在匹配到的规则之间比较特异性**，不需要属性级级联。
元素上的完整类集合是精确已知的（来自字面量或回推），因此嵌套 `:not` 可以**确定性求值**而非猜测。

**实测数字（`app/src` + `assets/scss` + `appearance`）**

| | 修前（旧脚本） | 修后（本脚本） |
|---|---|---|
| 表单控件使用点 | 1106 | **1186**（HTML 带 class 1106 / 运行时回推 32 / 无 class 48） |
| 无焦点指示 | 326（大部分假阳性） | **2** |
| 涉及类集合组合 | 87 | 118 |

**留下的 2 条正是 #19499 第 2 点**：`.protyle-toolbar__item`（`FormatPainter.ts:209` 与 `ToolbarItem.ts:12`），
其唯一的焦点规则是 `.protyle-toolbar__item:focus { outline: none }`（特异性 (0,2,0) > 兜底的 (0,1,1)）。

**五个判定前提（前四个是第二十四轮的，第五、六个本轮新增；每个都实测写错过）**

1. SCSS 嵌套的后代语义（只替换 `&` 会把局部规则读成全局兜底）
2. `transform` / `filter` / `opacity` / `color` 也算可见变化（否则 `.b3-slider` 误报）
3. 按**完整类集合**而非单类判定（焦点样式可能来自兄弟类）
4. 兜底**按真实标签**匹配（`button:focus` 不覆盖 `<input>`）
5. **`:is()` / `:where()` 必须展开**，否则以 `:is(` 开头的上游兜底永远匹配不上 → 多报。
   展开时**不得进入 `:not()` 内部**：`:not(:is(a, b))` 是「既不是 a 也不是 b」，
   拆成两条是「不是 a 或不是 b」，语义相反。`:not()` 由 `match_compound()` 三态求值
   （`True`/`False`/`None`，`None` 按宽松处理）。
   嵌套 `:not` 也必须逐层求解——兜底靠 `:not(.b3-text-field:not(.b3-text-field--text))`
   让 `--text` 变体吃轮廓，把外层拍平会判成「已排除」，与设计意图相反。
6. **特异性比较，且分属性**：`:where()` 记 0、`:is()`/`:not()` 取参数**最大值**
   （上游兜底因此是 (0,1,1)；把 `:not()` 里的类算进去会变成 (0,3,1)，反压组件自身样式）。
   抑制只压得住 `outline`，压不住 `box-shadow`（`.b3-button` 就靠 box-shadow）。
   提供者的 outline 必须**严格大于**抑制者才算覆盖（同特异性时抑制方胜 = 宁多报）。

**一个只在跑起来才发现的解析缺陷**：`resolve()` 用的是 `sel.split(",")`，
会把 `:is(button, input, select, textarea)` 里的逗号也切开，选择器被切成碎片
→ 兜底解析不出来 → 缺口数从 326 **升到 435**。改成顶层逗号切分后才降到 2。
另外 at-rule（`@media` / `@supports`）的前置部分不是选择器，不能当祖先拼进去
（会得到 `.b3-select @supports (appearance: base-select) option:focus` 这种永不匹配的选择器）。

**第三个盲区（交接文件未写）**：`collect_usages()` 要求标签上有 `class=` 属性，
**完全不带 class 的表单标签从不进入任何清单**——实测 48 处（input 33 / button 11 / select 3 / textarea 1）。
`protyle/preview/index.ts:67,70` 就是这一类（#19499 第 2 点的另一半）。
它们仍会被兜底覆盖（无排除类），**但若祖先里有更高特异性的 `outline: none` 就仍然没有指示**，
所以单独成节并标注「类集合与祖先未知」。

**运行时赋类名的枚举**：`.className =` / `classList.add|toggle`，只取引号字面量。
形如 `const el = document.createElement("button")` 后接 `el.className = "…"` 时
**标签可以回推**（实测 32 组走同一套判定）；回推不出的按「标签未知」单列
（352 个类名，其中 347 个在样式里完全没有焦点规则）——**这是上界不是缺口数**，`div` 上也常赋同类名。

**输出改成分四节**（前两节是判定，后两节是待人工回读）：
确定无焦点指示 / 含祖先的抑制规则（祖先未知，**不计入缺口数**，`.protyle-preview__action button:focus` 落在本节）/ 运行时赋类名中标签未知的 / 不带 class 的表单标签。
vendored 的 `asset/pdf/**`（23 处）单列，不按自研标准要求。

**自检**：第 11 组从 14 条扩到 **31 条**，新增六类断言（`:is()` 展开条数与结果、`:where()` 计 0 的特异性数值、
`:not()` 内部不展开、嵌套 `:not` 的正反两向、特异性翻转的三组数据、`createElement` 回推、无 class 收集），
外加一条**负向用例**：把展开函数退化成恒等后，`b3-menu__item` 必须不再被判为已覆盖
（先断言补丁真的生效，再断言补丁行为与正确实现不同）。

## 第二十八轮（2026-09-14）：三条已上报发现（#19501 / #19502 / #19503）

### 一、前端 CI 是红的：替身表漏项（#19501，bug）

`dev` 顶端 `API contracts` workflow 的 `frontend-tests` job 失败，`ℹ tests 2468 / fail 2`。

| 测试 | 报错 | 机制 |
|---|---|---|
| `app/tests/mobileBacklinks.test.js` | `AssertionError: unexpected module util/zIndex` | `:10-15` 的 `sources` 名单缺新模块 |
| `app/electron/connectionManager.test.js` | `Uncaught Error: ../util/zIndex` | `:175-182` 的 `modules` 映射缺新模块 |

引入提交 `ae226f6ad6`（#19481）新增 `app/src/util/zIndex.ts` 并给 `app/src/dialog/index.ts:2` 加 import
（使用点 `:100`）。**与 #19474 是同一类问题**（该 issue 已由 `dc55a0635` 于 01:26 修复），
本次是**约 13 小时后的再次打破**；`ae226f6ad6` 自己带了 `app/src/util/zIndex.test.ts`（39 行）
但没同步那两份**手写替身表**——「给新模块补了单测、没给新依赖补替身」。
全仓只有这两个测试加载 `dialog/index.ts`，影响范围精确。

**关于 #19493 的验证结论**：CI 对修复提交 `fa729c7c49` 的结论是 `failure`，
但失败与它无关（它只改 3 个 SCSS 文件，父提交 `a9b32a1395` 同样红）。
按 `AUDIT-HANDOFF.md` 第 5 节，结论应写「**部分修复**：剩余两处由 #19499 跟踪」，不是 fixed。

### 二、移动端历史操作筛选固定 96px（#19502）

`app/src/history/history.ts:538` 在移动端加 `fn__size96`（`_function.scss:115` → `width: 96px`），
而 `.b3-select` 是 `padding: 4px 26px 4px 8px` + `overflow: hidden` → **可用文字宽仅 62px**。

| 语言 | 最长选项 | 文字宽 | 超出 62px |
|---|---|---|---|
| en | All operations | 90px | 28px |
| ru | синхронизировать (sync) | 172px | 110px |
| ar | الخطوط العريضة (outline) | 147px | 85px |
| de / es / fr | 146 / 144 / 143px | | 84 / 82 / 81px |
| ko / tr / zh-CN / zh-TW | 115 / 102 / 89 / 89px | | 53 / 40 / 27 / 27px |

**桌面端不受影响**（无 `fn__size96` 时自适应，超出 ≤ 0：de 180 / ru 207 / ar 181）。
**这条最有价值的一点是它与候选清单的定性相反**：清单（判据 I4 文本膨胀）按「长度比」把它标为「译文过长」，
实测是**容器对英文就不够宽**，修法应是放宽容器而不是改译文。

### 三、表情动态图标 89px 标签压到相邻输入框（#19503）

`app/src/emoji/index.ts:983` 的「自定义」标签写死 89px，而 `.fn__flex-center` 只有 `align-self: center`、
**没有任何 overflow 处理**。用 `Range` 取文本实际绘制矩形与相邻输入框左边界（117px）比对：

| 语言 | 文案 | 文本右边界 | 交叠 |
|---|---|---|---|
| ru | Пользовательский | 171px | 54px |
| de | Benutzerdefiniert | 155px | 38px |
| es / fr | 129 / 120px | | 12 / 3px |
| ar | السمات المخصصة | — | 折成两行（高 23px → 47px） |

**同族**：同页签内 `language`（`:941`）/ `date`（`:954`）/ `format`（`:964`）/ `custom`（`:983`）
是同一套 89px 固定宽，只有译文最长的 `custom` 溢出 —— 候选项清单只看单条「长度比」，
因此看不到「同族只有一个成员溢出」这种形态。入口：块标 - 表情 - 动态图标（`:903` / `:926`）。

### 方法论教训（新）

1. **「文本膨胀」候选必须用真实渲染量测区分「容器太窄」与「译文太长」**。
   两条实测都是容器侧问题：一条对**英文**就已溢出，另一条同族四个标签共用一个宽度。
   只按长度比排序就会把修法指向错误的侧（改译文），而改译文既不能改英文那条，也修不好另一条。
2. **量测必须取「文本实际绘制矩形」而不只是盒宽**。`.fn__flex-center` 的分数是
   `over(文本宽-盒宽)=58px`，但真正能观察到的症状是 `textRect.right - nextBox.left = 54px`（与相邻控件交叠）；
   前者是推导，后者是观测量。用量测集合完整覆盖选项（本轮先把 `historyOutline` 漏在集合外，
   导致 ar 的「最长项」报错 —— 报错项被替换后数值从 46px 变成 85px）。
3. **「修复后又复发」的同类问题要写成同一类而非重复**：#19474 修的是「替身/白名单/断言未随生产更新」，
   本轮是同一机制在 13 小时后被新提交再次打破。上报时必须引用前一 issue 与修复提交，
   否则会被当成重复上报。

## 第二十九轮（2026-09-14）：把 a11y 提示位点与剩余候选处理完（#19505 / #19506 / #19507）

上轮清理完 `.audit-*.md` 后，本节把剩下的三类候选（a11y 的 143 个提示位点、K5 的 18 条「确认」、
i18n 的 1 条未上报）逐条判定完，产出 3 条 issue。

### 一、tooltip 的键盘可达性（#19505，机制层）

`component/_tooltips.scss` 的提示**只有一个显示入口，且是鼠标专用**：

| 行 | 规则 | 作用 |
|---|---|---|
| `:70` | `.b3-tooltips::after { opacity: 0 }` | 基线不可见 |
| `:74-77` | `&:hover, &:focus-within { overflow: initial }` | **`:focus-within` 只放开裁剪，不设 opacity** |
| `:79-83` | `&:hover::after { opacity: 1; ... }` | 唯一的显示入口 |

**对照实验**（真实产物 CSS `app/stage/build/app/base.*.css` + 真实 DOM 形态）：

| 状态 | 伪类命中 | `::after` opacity |
|---|---|---|
| 基线 | — | 0 |
| **键盘聚焦** | `:focus-within` **true** | **0（不可见）** |
| **鼠标悬停** | `:hover` true | 轨迹 `0 → 0.004(301ms) → 0.686 → 0.935 → 1(451ms)` 起稳定 |
| 对照组：无 `.b3-tooltips` 类 | — | `content: none`（排除「伪元素不存在」的干扰） |

**规模**：`.b3-tooltips` 共 160 个标签（34 文件），**键盘可聚焦 46 个**（28 `button` + 15 `input` + 3 `a[href]`），
其中 10 个属 vendored PDF.js → 自研 **36 个**。

**业务表现最有说服力的一处**：闪卡复习界面 `card/openCard.ts:122/127/135/142/149/156/163` 的 7 个按钮，
`aria-label` 承载的正是**快捷键提示**（`空格 / 回车`、`0 / x`、`1 / j / a`、`2 / k / s`、`4 / ; / f`）——
鼠标悬停能看到，Tab 过去看不到；而这些提示的用途恰恰是告诉键盘用户有哪些快捷键。
同类还有关系图配置的 15 个 `input[type=range]`（`layout/dock/Graph.ts`）与 `config/tabs/keymapRow.ts:8`。

**依据**：WCAG 2.1 **1.4.13 Content on Hover or Focus** 要求由悬停或聚焦触发的附加内容
**必须同时**可由两者触发。**修法**：显示入口补 `:focus-within`（另需补 `:126-127` 与 `:145-146`
两个方向变体的 `transform`，否则四个方向在聚焦时停在 `scale(.8)`）。

**取证陷阱（新）**：`.b3-tooltips::after` 有 `transition: opacity 150ms 300ms`，
在 `mouseover` 事件里**立即**读 computed style 只能得到过渡中间态（实测得 `opacity=0`，会误判为「悬停也不显示」）。
必须在过渡完成后采样（本轮用 `requestAnimationFrame` 逐帧记录轨迹，300ms 后才发现真实值为 1）。

### 二、对话框关闭后不恢复焦点（#19506，架构层）

`dialog/index.ts` 的 `Dialog` 类**没有任何焦点管理**：`:76` `document.body.append(this.element)` 不记录触发元素，
`:96-104` 的 `destroy()` 只 `classList.remove` + `element.remove()`。
`dialog/inputDialog.ts` 有打开时的初始焦点（`inputElement.focus()`），但关闭后同样不恢复。

**同族不一致是本条的主要论据**：`Dialog` 有 **103 个调用点**，其中 **10 个**自己在 `destroyCallback` 里
调 `focusByRange` 恢复（`editor/rename.ts:62`、`util/pathName.ts:291`、`protyle/wysiwyg/list.ts:115`、
`business/openRecentDocs.ts:118`、`protyle/wysiwyg/callout.ts:90`、`search/spread.ts:155`、
`protyle/render/av/cell.ts:596`、`menus/commonMenuItem.ts:85/289`、`config/bazaar/rating.ts:595`），
其余 **93 个**没有 —— 不是「作者认为不需要」，而是「没在类里统一做，只有想起来的调用点做了」。

**浏览器行为对照实验**（本地页面复现 `Dialog` 的行为）：
```
触发元素聚焦 → activeElement = trigger
焦点移入对话框 → activeElement = inner
element.remove() → activeElement = BODY   是否回到触发元素 ? false   触发元素 isConnected = true
对照组（手动 focus 回触发元素）→ activeElement = trigger
```
第 3 行是规范行为，第 4 行证明恢复可行、只是没做；触发元素仍在文档里，不涉及元素消失。

**去重**：#14399（focus return id）与 #12349 → #16073 → #16862（Windows 上原生 `alert`/`confirm` 后整窗失焦）
是**原生弹窗**问题，与 `Dialog` 类的焦点恢复不是同一问题。

### 三、微信提醒的 100px 标签（#19507，i18n 固定宽度的第二个实例）

`menus/commonMenuItem.ts:74`（`openWechatNotify`）与 `:144`（`openFileWechatNotify`）各一处：
`style="text-align: right;white-space: nowrap;width: 100px"`。用 `Range` 取文字绘制矩形，
与右侧日期输入框左边界比对：

| 语言 | 文案 | 文字宽 | 超出盒 | 压到输入框 |
|---|---|---|---|---|
| es | Tiempo de notificación | 171px | 71px | **63px** |
| ru | Время уведомления | 158px | 58px | **50px** |
| de | Benachrichtungszeit | 153px | 53px | **45px** |
| tr / fr | 117 / 112px | | 17 / 12px | **9 / 4px** |
| en / ar / ko / zh-CN / zh-TW | 86 / 79 / 68 / 64 / 64px | | — | 无 |

`text-align: right` 是干扰项：它只影响对齐，文字比盒宽时**既不被裁掉也不换行**，照常绘制覆盖右侧。
这与 **#19503**（89px 标签）、**#19502**（96px 下拉）构成同一形态的三个实例，区别是这一处用行内 `style`。

### 四、本轮判为**非缺陷**的候选（勿重报）

| 候选 | 数量 | 排除依据 |
|---|---|---|
| A2 `aria-hidden="true"` 内是否含可聚焦内容 | 8 处 | 逐条判定**全部排除**：都是装饰性 svg/span（`rating.ts` 的星级与分布条、`export/index.ts` 的 pdf 图标、`fontControls.ts` 的图标）。`aria-hidden` 用在装饰图标上是**正确实践** |
| A3 带 `role="combobox"` 是否缺必需 aria-* | 1 处 | **实现完整**：`fontFamilyMenu.ts:164` 同时有 `role` + `aria-expanded` + `aria-controls`（指向 `role="listbox"` 的列表）+ `aria-label`，选项有 `role="option"` + `aria-selected`，且 `syncActiveDescendant()` 动态维护 `aria-activedescendant`。**比多数实现更完整** |
| K6 `mouseenter`/`mouseover` 是否缺配对 focus | 11 处 | 逐条回读：① `config/bazaar/rating.ts:647` 的评分预览**有完整键盘支持**（方向键/Home/End + `aria-checked` + roving tabindex + 初始 focus）；② `AgentSessionPanel.ts:410` 的 `--current` 高亮是菜单键盘导航的同一状态；③ 其余（资源/文档预览、浮动停靠栏 hover 展开、`AgentChat` 导航栏展开）属**辅助信息或鼠标特性**，键盘无等价物也不阻断功能 |
| K5 的 18 条「确认」 | 18 处 | 上轮已逐条回读：真正成立的只有 `.b3-switch`（已修）与 `.b3-menu__item`（被 #19493 的全局兜底覆盖）；其余是容器与 contenteditable 内容区 |

### 五、仍未处置的候选（下轮入口）

- **K3/K7 的 123 处「焦点陷阱」**：本轮只从「关闭后回焦」一个角度处理了（#19506）。
  剩余的是「打开弹层时是否把焦点移入」与 `Esc` 键配对，需要在真实渲染环境逐个走；
  其中大部分是 `.b3-menu__popover` / `dialog--open` 这类正常弹层，预期假阳性高。
- **判据 I1「状态矩阵」已做人工对照，结论是「本仓库当前没有确认实例」**（详见下节）。

### 六、判据 I1 人工对照：**未发现确认实例**（2026-09-14）

`AUDIT-HANDOFF.md` 要求「先用人工对照拿到至少一个真案例，再决定要不要机械化」。
本轮完成了对照，结论是**没有实例**，因此**不建脚本、不占判据字母**，
结果写成层面地图的「状态矩阵检查点（待实证）」。

**对照范围**：桌面/移动的 **6 对兄弟实现**（书签、标签、大纲、文件树、反链、收件箱）
+ **26 个菜单文件**的只读守卫分布。

**先做的关键一步是「找到四种态的统一实现」**——不做这一步，按关键字统计会得到完全错误的矩阵：

| 状态 | 统一实现 | 位置 |
|---|---|---|
| 空态 | `b3-list--empty` + `languages.emptyContent` | `util/Tree.ts:72`（用 `Tree` 的面板自动就有） |
| 加载态 | **三种并存**：`loading-pure.svg`（44 处）/ 图标旋转 `fn__rotate` / `fn__loading` | 分布在各调用点 |
| 错误态 | `processMessage` 在 `code < 0` 时 `showMessage` 并 `return false` → **回调不执行** | `util/processMessage.ts:77` + `util/fetch.ts:95` |
| 只读态 | **两种表示并存**：`window.siyuan.config.readonly` 与 `protyle.disabled` | `protyle/util/onGet.ts:503` 的 `disabledProtyle()` |

**逐项排除的六个「看起来像缺陷」**：移动端空态为 0（空态来自 `Tree`）、移动端加载态为 0
（用的是 `loading-pure.svg`）、桌面无加载态而移动有（桌面用图标旋转，平台适配）、
`menus/block.ts` 的 `transferBlockRef` 无 `readonly` 守卫（**调用点** `protyle/gutter/index.ts:2910`
用 `!protyle.disabled` 守卫，且内核路由已带 `CheckReadonly`）、
「回调里不检查 `code`」（`processMessage` 保证失败时回调不执行）、
标签面板桌面/移动加载态实现不同（平台适配）。

**本轮第二次踩到「按关键字统计」的坑**（第一次见第二十七轮的特异性）：

1. 用 `fn__loading` 作加载态信号 → 报「6 个面板里 5 个没有加载态」；
   改用 `loading-pure.svg` 与 `fn__rotate` 后绝大多数都有。
2. 用 `readonly` 作只读守卫信号 → 报「`menus/block.ts` 完全没有只读守卫」；
   实际守卫是 `protyle.disabled`，**语义正确**。

**教训**：状态的「有没有」不能按类名或关键字统计，必须**先确定该状态的统一实现落在哪一层**
（面板 → `Tree` → 全局工具 → 内核），再问「谁绕过了它」。**绕过统一实现才是信号。**

**环境事实（本轮）**：运行中的实例（3.8.4-alpha.9）的浏览器页面**反复加载超时**（30s，
`http://127.0.0.1:6806` 与其 `/stage/build/desktop/index.html` 都失败），而同一内核的
`POST /api/system/version` 正常响应 —— 所以本轮的真实渲染取证全部走
「**真实产物 CSS + 真实 DOM 形态 + 对照组的本地 HTML**」，结论不依赖运行实例。

## 第三十一轮（2026-09-14）：对话框焦点陷阱（#19510）+ 六条修复验证 + 工作树落后的重大陷阱

### 一、新发现：Tab 会跑到遮罩后的编辑器并改到背后的文档（#19510）

`Dialog` 打开后焦点不进入弹层，也没有任何焦点约束。**当前权威基线（`origin/dev`）**上的事实：

| 检查项 | 命中 |
|---|---|
| `event.key === "Tab"` 处理 | **0 处** |
| `focusTrap` / `trapFocus` / `focus-trap` | **0 处** |
| `aria-modal` | **0 处** |
| `role="dialog"` | 1 处（`protyle/render/av/richTextEditor.ts:106` 的独立实现，非 `Dialog` 类） |
| 打开弹层时给背景加 `inert` | **0 处** |

`dialog/index.ts:35-43` 只**记录** `previousFocus`、不移动焦点；`:65-66` 的模板只有视觉遮罩；
`_dialog.scss:24-31` 的遮罩是全视口 `position:fixed` + 40% 透明覆盖层；
`:74` 的遮罩点击是 `destroy()`（背景对鼠标不可操作）→ **设计上是模态的**。

**真实路径复现**（真实产物 CSS + 逐字取自 `:65-66` 的 DOM + 真实 Tab 按键）：

```
打开后 activeElement = [背景!] SPAN#trig1(工具栏按钮A)   ← 焦点留在遮罩后的触发元素
1: [背景!] SPAN#trig1                     ← Tab 仍在背景
2: [背景!] SPAN#trig2                     ← 第 1 次 Tab 后仍是背景元素
3: [背景!] DIV#doc(文档编辑区)              ← 第 2 次 Tab 落到可编辑文档区
   继续输入 → 文档内容变为 "WENTBEHIND原始文档内容"（对话框仍打开）
```

**业务表现是「输入落到错误位置」而不是无障碍细节**：键盘用户按 Tab 找弹层按钮，
第 2 次 Tab 就把焦点交给背后的文档，接着打字会静默修改文档。

### 二、六条上报全部被修复（并已逐个核对代码）

`#19501`/`#19502`/`#19503`/`#19505`/`#19506`/`#19507` 在 2026-09-14T09:19Z 前后被同一批修复
（提交 `c0cada223`/`b15fced73`/`f04dc4803`/`b412ff8dd`/`8d880fe1e`/`30126652e`）。
**按验证模式的要求核对了代码而非评论**：

- `_tooltips.scss`：`&:hover::after, &:focus-within::after { opacity: 1 }` 且四个方向变体
  （`:129-130`、`:150-151`）都补了 `:focus-within` —— 与本 issue 的建议一致
- `dialog/index.ts`：新增 `previousFocus`（`:17`/`:37`）与 `restoreFocus` 分支（`:121-141`），
  含 `isConnected` / `getClientRects().length` / `visibility` / `!closest("[inert]")` 多重守卫
- `_content.scss` 与 `_toolbar.scss` 的 `:focus { outline: none }` **两条都被删除** → **#19499 也已修复**

### 三、**重大方法论陷阱：工作树落后于 `origin/dev`**

本轮在写验证结论时发现：本地工作树停在 `bc64d1677b`（17:12:30），`origin/dev` 已到
`51e0174081`（17:29:08），**落后 9 个提交**，其中包含刚被修复的那 6 个。

**表现与判据**：

- 修复提交**存在于本地对象库**（`git cat-file -t <sha>` → `commit`），
  但 **`git merge-base --is-ancestor <sha> HEAD` 退出码非 0** ——
  「对象存在」不等于「工作树包含它」。我第一遍据此读出「修复不存在」，
  与维护者评论冲突，靠 `--is-ancestor` 才定位。
- 对**新方向**的源码级判定同样受影响：焦点陷阱一轮最初是在旧树上做的（`block/Panel.ts`、
  `keydown.ts`、`Menu.ts` 等都读过旧版），最终**在 `origin/dev` 上整个重做**。

**在只读仓库上取得当前基线的办法**（零改动目标仓库）：

```
git archive --format=tar --output=<tmp>/dev.tar origin/dev app/src app/appearance
cd <tmp> && mkdir devsrc && cd devsrc && tar -xf ../dev.tar
```

**用它得到的当前权威状态**（与旧树对比）：

| 维度 | 旧工作树 | `origin/dev` |
|---|---|---|
| 焦点可见性缺口 | 2（`.protyle-toolbar__item`） | **0** |
| K2 正整数 tabindex | 0 | **0** |
| A6 纯图标按钮无访问名 | 0 | **0** |
| K5「经核对落在可聚焦元素上」 | 18 | **16**（剩下的正是已判为容器/内容区的那些） |

**教训**：`git status` 干净**不代表**代码是最新的。凡是要做「验证」或依据源码下结论，
**先 `git fetch` + `git rev-list --count HEAD..origin/dev`**；与「产物新鲜度」陷阱的区别是
——那条讲 bundle 旧，这条讲**源码本身**旧，且读源码时不会有任何「我在读旧代码」的自觉。

### 四、本轮判为非缺陷的候选（勿重报）

**K3/K7 的 123 处逐条筛过**：信号（`classList.(add|remove)` 命中 `dialog|modal|popover|menu`）
非常松，实际构成是 **38 处 `b3-menu__item--current`**（菜单键盘导航的高亮）、
15 处 `b3-menu__item--show`（图标显隐）、其余多为菜单外观类；**真正涉及弹层开合的只有 7 处**
（`b3-dialog--open`、`block__popover`、`b3-menu__scrim--open`、两个移动端弹层、`hint--menu`）。

**K7（Esc 配对）判定为完备**：`boot/globalEvent/keydown.ts` 的 Escape 分支按 9 级优先级处理
——`formatPainter` → `cancelDrag` → 图片预览 → **菜单**（含「对话框高于菜单时先关对话框」）→
`av__panel` → **对话框** → **块浮层** → 光标在文档树时回到编辑器（#4289）→ `focusByRange` 兜底。
这是一处做得相当完整的地方，**不要按「有没有 Esc」一律怀疑**。

**K3（焦点移入）的另一半**：菜单不移动 DOM 焦点（靠方向键 + `--current`，维护者在 #19493 评论里
已确认这是有意设计）；`block__popover` 是 hover 触发，无需移入焦点。唯一成立的就是 `Dialog`，
已提 #19510。

### 五、自检里一条**会挡住正确状态**的断言（本轮修正）

第 9 组的冒烟断言原为 `0 < 缺口数 < 使用点总数`，理由是「为 0 说明降噪过度」。
上游把缺口全部修完后，**本仓库的真实状态就是 0**，于是自检把「正确地报 0」判成失败
（`FAIL 缺口数介于 0 与总数之间（0 < 1186）`）。

这类问题的性质与「假成功」相反但同样有害：**断言在正确的状态上失败，会让人反过来怀疑实现**。
修法不是删掉断言，而是把它拆成两件不同的事：

- **活体检查（liveness，可在真实仓库上稳定做）**：样式侧必须解析出焦点规则
  （`含可见焦点变化的类 > 0`）、每个使用点都必须拿到判定（`有焦点指示 + 无焦点指示 == 总数`）、
  **缺口为 0 时必须同时有大量「有焦点指示」**（否则 0 来自「使用点全被丢弃」而不是「都被覆盖」）；
- **降噪过度的检查（用夹具，与仓库状态无关）**：留在第 11 组的 `:is()` / 特异性 / 嵌套 `:not` 用例里
  —— 它们构造已知答案的样式，能稳定区分「正确判定」与「恒真」。

**负向验证 3/3**（变异后自检退出码非 0 且失败清单含相关标签）：

| 变异 | 结果 |
|---|---|
| `collect_focus_rules` 返回空（CSS 解析失效） | 抓住（含新增的「样式侧解析出了焦点规则」） |
| `collect_usages` 返回空（使用点收集失效） | 抓住（由同组的无 class 收集断言拦下，**不是**我原本预期的标签） |
| `verdict` 恒真（降噪过度） | 抓住（由夹具断言拦下，如「更高特异性的 `outline: none` 反杀兜底」） |

第二行印证了维护规范第 13 条的判定方式：**「拦住」要放宽到「该组任一相关断言失败」**，
锚定单一标签会得出「没抓住」的错误结论。

## 第三十二轮（2026-09-15）：块选择模式借用原子标记导致残留与方向键跳块（已提 #19556）

**用户问题**：按 `Esc` 选中块之后按方向键是什么逻辑；为什么 `protyle-wysiwyg--navigation` 很难理解。

**范围**：`app/src/protyle/wysiwyg/` 里纵向导航与块选择两个子系统的交叉（`verticalNavigation.ts`、
`verticalNavigationState.ts`、`blockSelection.ts`、`keydown.ts`），外加 `util/clear.ts`、`ai/editor.ts`、
`transaction.ts` 的清理载体。

**唯一实质发现（已提 #19556）**：`focusAtomicRegion`（`verticalNavigation.ts:94-113`）三条分支
**最后都会**加 `protyle-wysiwyg--navigation`，包括「`focusBlock` 成功」的普通可编辑块分支；
块选择模式每次 ↑/↓ 都调用它的导出包装（`keydown.ts:531`、`:566`），于是普通段落被打上原子标记。
退出模式只清 `--select-mode` / `--select`（`blockSelection.ts:49`），全仓无一处清理 `--navigation`。
后果两条：退出后残留 2px 轮廓；**下一次同向方向键走原子分支（`keydown.ts:1008-1020`），
跳过当前多行块的其余行**。

**取证（真实渲染 + 真实键盘，3.8.4-beta.2）**：

| 步骤 | caret | `--navigation` | `--select-mode` |
|---|---|---|---|
| 起始 | A | 无 | 无 |
| Esc | A | 无 | A |
| ↓ | B（首行） | B | B |
| Esc | B | **残留** | 已清除 |
| ↓ | **C** | 已清除 | 无 |

对照（手工移除该类、光标复位到 B 首行）：真实 ↓ 连续 4 次，光标顶部 244 → 270 → 296 → 322，
每次正好一个行高 26px，即**块内逐行移动**；B 高 164px（6 行），所以单行块看不出跳块。
逐退出路径验证：**Esc 与 Enter 残留、鼠标点击不残留**（`pointerdown` 的捕获监听兜底）。

**判为非缺陷（勿重报）**：临时类确实随事务载荷发往内核（挂钩 `fetch` 捕获到
`class="p protyle-wysiwyg--navigation"`），但内核丢弃 block DOM 的 `class`，读回 `.sy` 不含该字符串
→ 无数据污染，前端清理缺项只是观察项。

**关键证据获取路径（可复用）**：本机 `?id=` 打开时被服务端判为 Electron UA（`kernel/server/serve.go:757`
命中 `Electron` → `/stage/build/app/`），该产物的 `4157(i){i.exports=require("electron")}` 在无 nodeIntegration
的页面里抛 `require is not defined`，表现为「点击刷新」错误页；**直接加载 `/stage/build/desktop/`
（非 Electron 的桌面浏览器目标）即可正常渲染**。产物新鲜度判据：在 bundle 里 grep 新符号
（本轮 `protyle-wysiwyg--navigation` 命中，且 `app/stage/build/app` 与 `app/build/win-unpacked` 副本同名同大小）。
删除文档用 `/api/filetree/removeDocByID`：`/api/filetree/deleteDoc` 返回 **200 + 空 body 且不生效**
（易误判为成功）。

**清场**：取证用临时文档 `20260915205142-jsl9usn` 已删除并三项回读确认（SQL 无块、`.sy` 404、
workspace 下无 `.trash`），目标仓库 `git status` 干净。

**新判据/模式**：新增 **D3e**（临时 UI 标记类的清理载体构成闭合集合）与模式 **P42**
（借用型临时标记类无人释放）；已知误报 **+2 条**（临时类进入载荷 ≠ 落盘；清理载体缺项 ≠ 缺陷）。

## 第三十三轮（2026-09-15）：块选择模式的第二个入口缺状态位（已提 #19557）

**起点**：用户质疑上轮范围太窄（「就只存在我提出的这一个问题而已吗」）。上轮是**定向审计**，
只回答了提问所处的那个交叉点，不是该功能域的全量审计。本轮把同一功能域的其余路径补齐。

**方法论第一步：变体分析先于取证**。`grep` 全部「移动当前块」的调用点（`setBlockSelectionModeElement` 11 处）
与全部「移动导航标记」的调用点（`focusVerticalBlockSelection` 2 处），做差集。
差集里逐条实测，区分**自愈**与**残留**两类（结论见误报表新增条目「同族移动函数不移动标记 ⇒ 缺陷」）。

**唯一实质发现（已提 #19557）**：块选择模式有两个入口，建立的状态集合不等价。

| 入口 | 建立者 | 状态位 |
|---|---|---|
| 光标置于块内按 Esc | `setBlockSelectionModeElement` | 只有「当前块」`--select-mode` |
| 跨块划选后按 Esc | `selectBlocksByRange`（`util/selection.ts:167`） | 只有「标记块」`--select` |

实测（真实鼠标划选 + 真实键盘，3.8.4-beta.2）：

| 按键 | 划选转换入口 | 光标入口（对照组） |
|---|---|---|
| 空格 | 标记全清 + **P3 正文 `P3short` → `P3short `** | 标记当前块成功，**文档逐块比对未变** |
| ↓ | 三个标记全丢，只剩相邻叶子块 | 当前块移动，标记保留 |
| Enter | 标记全清 | 退出并定位 |

**根因（分派链）**：空格专用分支要求 `blockSelectionModeElement`（`keydown.ts:571`），缺失时**不停下**，
继续落到 `isRegularTextInput`（`:594-596`，它只排除了「有当前块」，**没排除「有标记块」**）→ 空格当普通输入 →
`hideElements(["select"])`（`:618`）清标记 → 字符写入正文。方向键分支同理（`:511-513`）。

**关键洞察（已写入判据 I1 的第二个维度）**：缺失状态位导致的是**退化**而不是**无操作**。
专用分支在前、通用分支在后，状态位缺失筛掉的是专用分支，于是控制权落到后果更严重的通用分支。
报此类缺陷必须沿分派链追到**实际执行的那一个分支**。

**排除的候选（勿重报）**：`insertEmptyBlock` 收到 `undefined` 有兜底（回退到标记块，`block/util.ts:334-350`），
A/B 不崩溃；`⇧↓` / PageUp/PageDown / Tab / 鼠标退出四条路径都不残留。

**清场**：取证文档 `20260915210339-rtaynz0` 已删并三项回读确认（SQL 无块、`.sy` 404、无 `.trash`）。

## 第三十四轮（2026-09-15）：只读模式下块选择转换不可达（已提 #19558）+ 两个已提 issue 的修复

**用户要求**：继续审计该功能（上轮列了 5 处未覆盖区域）。

**一、产物过期这个前提差点毁掉整轮结论（最重要的教训）**

实测中我发现「退出块选择模式后按 ↓ 仍然跳块」，与 #19556 已被修复的预期不符，一度准备写成「修复不完整」。
核对后确认：**本机浏览器产物时间戳 19:09 早于修复提交 21:11**，我测的是修复前的代码。
同期工作树已从 `9a91fc35d6` 推进到 `c8dc2e50f0`（**我上轮报的两个 issue 都已被修复**）。
教训：**开测前先比产物时间戳与 `git log -1 --date` 的时间**，而不是先怀疑修复不完整；
在本仓库浏览器产品（`stage/build/desktop`）不随 `pnpm dev` 更新，这个陷阱会周期性重现。
后续改用「代码审查 + 需求提交时间核对」代替浏览器复验，并在报告中**如实标注取证基线**。

**二、唯一实质发现（已提 #19558）**：只读模式下跨块划选 + Esc 不转换为块选择。

- 需求侧权威：#19116《只读模式跨块选择文本，按 ESC 支持选中块》，实现于 `14bb963279`（09-03），
  含专为此写的 `selectReadonlyBlocksByRange`（`boot/globalEvent/keydown.ts:95`），调用点 `:1677`；
  用户指南亦写明「只读模式下同样适用」；`readonlyKeydown.test.ts` 断言只读下 Escape 不得被 wysiwyg 层吞掉。
- **差分对照（决定性）**：同一文档、同一跨块选区、同一按键，仅只读状态不同——
  只读（`contenteditable=false`）→ 无标记、无当前块、选区保持 101 字符；
  编辑（解锁后）→ 建立 R1/R2/R3 标记、选区折叠为 0。
- **取证手段（可复用）**：用文档级只读属性 `custom-sy-readonly` 建立只读态，**不改任何全局配置**；
  并用面包屑锁定按钮走一遍真实用户路径，确认两者得到完全一致的状态
  （`data-subtype="lock"` / `contenteditable="false"` / 属性为 true）。
- **排除清单（本次的主要工作量，也是 issue 中最有价值的部分）**：跨块、两侧 `hasClosestBlock` 可识别、
  `protyle.disabled` 为真（`data-subtype="lock"`）、起点在 `.protyle-content` 内、编辑器唯一且含起止块、
  无抢返回的分支（菜单/对话框/浮层/formatPainter）、`Protyle` 类确有 `protyle` 字段所以不存在属性访问异常。
- **两条一致证据**：MutationObserver 监听 `class` 变更 → Esc 后记录数为 **0**（`selectBlocksByRange` 未执行）；
  选区长度保持 101 未变（而该函数末尾的 `range.collapse(false)` 会折叠选区）。
- 根因**未定位到行**，已诚实标注；给出的线索是只读下 `event.target === document.body`
  而 `windowKeyDown` 对 body 焦点有特殊分派（`:1316`）。

**三、方法教训：插桩位置错误会造出假证据**

我最初在 `document` 的冒泡监听器上读 `event.defaultPrevented`，得到 `false` 并据此推断
「没有任何处理器处理 Escape」。这是错的：`windowKeyDown` 挂在 **window** 上，
**window 的冒泡监听器晚于 document 的**，所以那个读数看不到它。
判「某按键是否被处理」必须在**与处理器同一层或更晚的层**采样（或看副作用）。

**四、顺手完成的两个修复核验**（代码审查层面，产品侧因产物过期无法复验）：

| issue | 修复提交 | 内容 | 判定 |
|---|---|---|---|
| #19556 | `f861bfe304` | `focusAtomicRegion` 改为 `atomic = !getContenteditableElement(element)?.contains(range.startContainer)`，仅有 Range 不在可编辑区时才加类 | 与我建议的方案一致，逻辑成立 |
| #19557 | `c8dc2e50f0` | `selectBlocksByRange` 内新增 `setBlockSelectionModeElement(protyle.wysiwyg.element, currentElement)`（取选区末端所属块） | 与我建议的方案一致，逻辑成立 |

**清场**：取证文档 `20260915211635-7phhixu` 已删并三项回读确认；仓库内零残留。

**本次未完成**（下轮可继续）：页签块与块选择、IME 组合输入取消路径、跨文档/页签切换时的选择状态、
`--hiderange` / `--select-attr` 两个临时类的清理闭合性（仅做了 `--hiderange` 的建/清点计数，未逐条验证）。

## 第三十五轮（2026-09-15）：块选择的两个残留/可达性缺陷（已提 #19559、#19560）+ 四项未覆盖区域全部收口

**背景**：用户批评「每轮都剩下一些没做的」。上轮我只完成了一项、列了四项清单。
本轮把四项全做完，每项给出「确认缺陷」或「已排除 + 依据」，**不留未完成项**。

**一、产物过期陷阱的再次应用（有效）**：开测前先比产物时间戳（19:09）与 `git log -1 --date`，
确认行为验证的覆盖上限，并在每份 issue 里写明「取证基线」。

**二、确认缺陷 1（#19559）：切只读到只读时 `--select-mode` 残留、键盘无法退出**

- `disabledProtyle`（`onGet.ts:503`）用 `hideElements(["gutter","toolbar","select","hint","util"])`（`:505`）
  统一清理临时 UI，但 `hideElements` 的 `select` 分支（`hideElements.ts:55-61`）只移除 `--select` 与
  `select-start`/`select-end`，**不含块选择模式引入的 `--select-mode`**。而只读下
  `wysiwyg/keydown.ts:322` 整段早退，块选择模式的 Esc 分支到不了 → 键盘无法清除。
- 实测矩阵（真实鼠标 + 真实键盘）：可编辑下 3 个类均在 → 切只读后 `--select`、`--navigation` 归 0
  但 `--select-mode` **仍为 1**，且 `::after` 底色实测可见（`rgba(53,117,240,0.12)`）→ 按 Esc 无变化 →
  点击块内才清（`modeCount: 0`）。
- **`--navigation` 单独归零是关键对照**：它另有清理路径（`focusout` 捕获监听），
  这反向证明残留只因该路径漏登记，而不是「只读时都不清」。
- 同一场景下我犯过一次错：首次点击「没清掉 `--select-mode`」，我用它写了「点击也无法退出」；
  实际是点击坐标落在面包屑空白区（`elementFromPoint` 显示 `protyle-breadcrumb__space`）
  → **每次点击前用 `elementFromPoint` 验证命中目标**，否则会把工具误差当成产品行为。

**三、确认缺陷 2（#19560）：块选择模式无法把容器块设为当前块 + 方向不对称**

实测（顶层顺序 `W1`、列表、`W2`、引述、`W3`、callout、`W4`）：

| 容器块 | 向下 | 向上 |
|---|---|---|
| 列表 `NodeList` | 不可达（进内部段落） | 不可达 |
| 引述 `NodeBlockquote` | 不可达 | 不可达 |
| 页签 `NodeTabs` | 不可达（进页签内段落） | 未测 |
| callout `NodeCallout` | **可达（停在块本身）** | 不可达（进内部段落） |

根因：块选择模式直接复用纵向导航的目标解析（`keydown.ts:517`/`:534` → `getAdjacentVerticalBlock`
→ `getVisibleBoundaryBlock` → `findVisibleBoundaryBlock`）。`verticalTarget.ts:56` 的判据里，
`isContainerBlock`（`getBlock.ts:237`，含 list/li/sb/bq/callout/tabs/tab-item）会阻止容器返回自身，
唯一例外是「该块在 `hostRegions` 里有可见标题且方向为 down」——`hostRegions`（`verticalRegion.ts:13`）
只登记了 callout / tab-item / av，因此 callout 仅向下可达（`direction === "down"` 的限定就是不对称的直接来源）。
**对文本光标导航这套规则是对的**（向下进 callout 应停在可编辑标题），错误在于块选择的「当前块」
是**块级选择**语义，与「可编辑区域边界」不同目标。
- 业务表现：键盘无法复制/删除整个列表、整段引述、整个页签组（只能鼠标走块标菜单）；
  同一 callout 从上往下进是块本身、从下往上进是内部段落 → 按 ↓ 再按 ↑ 回不到原位置。
- 权威依据三处：用户指南「按 ↑ 或 ↓ 将上一块或下一块设为当前块」；#19184 的验收判据要求「上下对称性」；
  仓内对照——`fold="1"` 与非容器块都会返回自身（`verticalTarget.ts:56`），说明「跳过容器自身」不是统一样式。

**四、另两项的结论（已排除 + 依据）**

- **页签块的选中视觉（已收敛）**：`_tabs.scss` 对三种选择类各有规则——`:18-20`/`:149-151` 给
  `.tabs` 与 `.tab-item` 设 `border-radius: inherit`（两个提交 `98a9aca888`/`62c6858b12` 针对的缺口），
  `:331-333` 给 `.tabs-header::after` 单独铺底色（因为 `.tabs-header` 是 `z-index: 4` 的 sticky 元素，
  高于块级 `--select::after` 的 `z-index: 3`，顶部区域必须由它自己补）。`--navigation` 用 `outline` 而非 `::after`，
  不参与这个层叠关系。
- **IME 取消路径（已排除）**：`compositionstart` 会清 `--select-mode`/`--select`（`wysiwyg/index.ts:4048` 附近）
  但不清 `--navigation`。看似同类缺口，实际无危害：#19556 的修复让 `--navigation` 
  **只可能存在于 Range 无编辑区的块上**（折叠块、自定义块、嵌入块…），而这些块本来就应该有导航标记，
  残留不会改变行为；且组合提交通常会触发 `input`，`keyup` 的 `clearStaleAtomicFocus` 还会兜底。
  **这是“同形但无害”的典型——必须验证可达性与后果，不能因形状相同就报**。
- **`--hiderange` 的 Esc 取消路径（观察项）**：`cancelDrag` 不清它，实测拖拽列宽时按 Esc → `--hiderange` 仍在（`:true`），
  松手后由 `documentSelf.onmouseup` 清（`:false`）→ **自愈，无用户可见后果**，不报。
  附带确认：列宽拖拽本身工作正常（`data-col-index` 由 `mousemove` 写入、列宽 49→92px），
  我一度怀疑「该分支会抛 TypeError」，核对 `boot/globalEvent/mousemove.ts:285/290` 后推翻。

**五、方法增量**

- **建立“矩阵”而非逐场景探索**：状态位（临时类）× 生命周期事件（Esc/Enter/输入/IME/Tab/点击/切只读/切文档/动态加载）
  两维列表，只对“无人负责”的格子构造场景。本轮两个确认缺陷都是矩阵里先发现空格子、再找可达路径。
- **“同形但无害”的判定要过两道**：该状态位是否只能存在于“本该有它”的载体上（IME 例）；
  残留是否会被后续事件自愈（`--hiderange` 例）。

**清场**：4 个取证文档（`audit-r35-state`/`-table`/`-tabs`/`-container`）已全部删除并逐个回读确认搜索为空。

## 第三十六轮（2026-09-17）：同步错误提示的两处文案缺陷（已提 #19600、#19601）+ 一条被推翻的候选

**触发**：用户提供 Docker 内核的同步失败 system log（DNS 解析失败 + 云端空间不足），要求「确认代码层面的问题，存在就提 issue」。

**去重命中（先读登记表）**：#14193「备份失败：cloud storage limit size exceeded (Provider: SiYuan) v3.1.22」——
同一路径、同一用户可见文案。但它是 `state_reason = completed` 而 `git log --grep=14193` **空手而归**（无任何关联提交），
维护者的处理只是解释「配额确实已满」；该 issue **已锁定**，无法追加评论 → 只能以新 issue 携带新证据，并把「同一处已有报告」如实写进正文。

**发现一（#19600）：快照上传路径漏映射配额 sentinel**

- `UploadCloudSnapshot`（`kernel/model/repository.go:1512`）只映射 `ErrCloudBackupCountExceeded`（1544，Lang 154），
  配额 sentinel 落到 `formatRepoErrorMsg`（`kernel/model/sync.go:870`，无该分支）→ 用户看到
  `备份失败：cloud storage limit size exceeded (Provider: SiYuan)`，中英混排且无处理建议。
- 该 sentinel 由 dejavu 的 `UploadTagIndex` 在剩余空间不足时返回（`backup.go` 的 `uploadTagIndex`，两处 `availableSize` 判断）。
- 同族 4 条同步路径各有一份映射（`repository.go:1947`/`2030`/`2141`/`2287`）→ 新增判据 **P43**。
- 权威依据：同一函数相邻分支已为 `ErrCloudBackupCountExceeded` 本地化，同族 4 处也为该 sentinel 本地化
  → 「数据仓库与同步类错误要本地化」是该子系统在维护的不变量。

**发现二（#19601）：provider 错位的配额文案**

- dejavu `cloud/local.go` 的 `GetAvailableSize()` 返回 `util.GetFreeDiskSpace(endpoint)`（磁盘可用字节数），
  `BaseCloud` 其余 provider 返回 `Conf.AvailableSize`（`buildCloudConf` 只对官方云填账号配额，其余 2 TiB 默认值）。
  因此该 sentinel 实际只可能由**官方云（真实配额）**与**本地文件系统（磁盘可用空间）**触发。
- 4 处映射一律替换为 Lang 43 / Lang 68（云端配额 + 订阅引导），数值取 `userSiYuanRepoSize`，
  且整体替换把「同步失败：」前缀与 ` (Provider: Local File System)` 后缀一起丢掉 →
  本地磁盘将满被报成云端空间不足，trial 账号还会被引导去订阅（订阅不改变本地磁盘）。
- 「遗漏而非取舍」的依据：同文件 1483/1529/1575 的 provider 分支、3383 起的云端配额展示只对官方云生效。

**被挑战门降级、未提 issue 的一条**：`flushdns_other.go` 空实现 + 共享层日志声称已刷新。
第一轮推翻了我的三条功能论断（首次 DNS 错误在 Linux 上**会**重试、节流与 Windows 等价、Go 解析器自身不缓存 DNS），
功能范围是刻意的（#17936 标题与 v3.7.0 三语 changelog 均写 Windows）→ 残留只是日志措辞，写入误报表。

**方法论增量**：

1. **降级理由与发现理由都要验技术断言**。本轮第一轮挑战门直接推翻了我写错的功能论断（「节流会跳过重试」），
   而它当时看起来完全合理——这正是「断言必须再验」的另一个方向。
2. **挑战门第二轮阻止了一个有害修法**：把 4 处映射下沉进 `formatRepoErrorMsg` 会让 Local 的磁盘不足
   被改写成云端文案 + 订阅引导。修法审查与发现审查同等必要，尤其当建议形如「统一到共享函数」。
3. **既往 issue 要看 `state_reason` 与关联提交，不要看 `state`**。`completed` 在本例中不等于修复。
4. **本机取证陷阱（Windows）**：`gh api` 的 UTF-8 stdout 经 PowerShell 管道会按 GBK 解码，
   POST 回执看起来像「正文已损坏」，实际远端数据正确。回读要 `cmd /c "gh ... > file"` 让重定向捕获原始字节，
   再用读取工具核对；不要在 `ConvertFrom-Json` 的管道下游下结论。

## 第三十七轮（2026-09-19）：插件菜单两处候选的定向审计（1 条确认 + 1 条被权威依据驳回）

**触发**：用户给出「顶栏插件菜单里多了几个没见过的插件设置选项」的截图与插件目录，要求审计上一轮报告里
列为「代码层面两处值得修的地方」的两条候选。范围＝`app/src/plugin/openTopBarMenu.ts` 与其挂载/注册链路。

**基线**：`git fetch` 后 `HEAD == origin/dev`（`004efcd8a9`，0 落后）；`app/stage/build/desktop` 与 `mobile`
产物时间戳 2026-09-19 00:24，均**晚于**被审代码的最后改动（`openTopBarMenu.ts` = 2026-09-13 `5470398569`），
故允许做行为断言；产物早于 `80e825888f`（11:35，只改 `loader.ts` 的插件停靠栏图标刷新），与本轮结论无关。

**发现（CONFIRMED，新判据 D1o + 模式 P44）：打开插件菜单会永久注销「未挂载」的插件顶栏按钮，
使移动端「取消固定」在重启后不可逆**

- `app/src/plugin/openTopBarMenu.ts:30-33`：`if (!document.contains(item)) { plugin.topBarIcons.splice(i, 1); ... }`，
  而 `:36-57` 的 pin/unpin 子菜单在**剪枝之后**才构造 → 被剪掉的项永远拿不到「固定」入口。
- 让元素合法离开 DOM 的两个状态位：① 移动端「取消固定」（`index.ts:326-331` 与 `loader.ts:223-227` 都按
  `LOCAL_PLUGINTOPUNPIN` 跳过挂载，`setStorageVal`→`/api/storage/setLocalStorageVal` 持久化，`getLocalStorage` 复原）；
  ② `isWindow()` 宿主（`app/window.tpl` 无 `#toolbar`，但该宿主没有插件菜单入口，不可达）。
- 该 `splice` 由 `19c5a9952e`（2025-08-21，issue #15455）引入，原代码是 `forEach` + `return`（只跳过）；
  #15455 的诉求是「插件应能在任意时机添加顶栏按钮」，即**清理永不再挂载的图标**是有理由的——
  这正是本条容易漏判的原因（单看完全合理）。
- **两路取证**：① 用仓库自身的 VM 手法执行**真实** `openTopBarMenu.ts`：`document.contains=false` 时
  `topBarIcons.length` 1→0、菜单无该项、`是否出现 pin 子菜单 = false`，对照组（`contains=true`）保留且子菜单为
  `["unpin","play"]`；② 真实渲染（`/stage/build/desktop/`，内核 3.8.5-alpha.4）：把 `plugin_Whisper-Plus_0`
  `el.remove()` 后点击 `#barPlugins` → `Whisper-Plus` 的 `topBarIcons` 1→0，菜单 itemIds 只剩其余 4 个图标，
  设置组只有 `snippets`/`top-bar-text`（Whisper-Plus 无设置 → 该插件在菜单里**完全消失**）；刷新后恢复。
- 权威依据：维护者在 #19305 下写明「顶栏插件图标的隐藏入口统一为右键……**移动端行为不变**」，
  且 `openTopBarMenu` 自己提供 `pin` 分支 → 取消固定被设计为**可逆**；`statusBarIcons` 同族只把
  `document.contains` 当「已挂载则跳过」守卫、从不剪枝。
- 触发条件：移动端取消固定某插件的顶栏按钮 → 重启应用 → 打开插件菜单（`mobile/menu/mainMenu.ts:229`）。
  普通桌面操作看不到（桌面走 `data-entry-hidden`，元素始终在 DOM 中）。
- 严重度低：可用「禁用再启用插件」恢复；但菜单内无恢复路径，且完全静默。

**被驳回（不报）：插件菜单里同一插件出现两次、且标签像包名**

- 3.8.4 的 `5470398569`（#19396）把设置项从按钮子菜单提出来、用分隔线分成两组；`#19396` 的诉求原文即
  「上方显示顶栏按钮，下方显示插件设置」「每个插件的设置入口仅显示一次」，维护者在该 issue 下确认并给出该提交
  → **定义行为**，`app/src/plugin/topBar.test.ts` 的首个用例把它固定为契约。
- 标签取 `plugin.displayName`（内核 `GetPreferredLocaleString(DisplayName, Name)`，无本地化显示名时回退包名），
  与集市「已安装」列表同源，不是插件菜单引入的；实测本工作空间 `loadPetals` 的 6 个插件显示名均为中文。
- 结论：属 product 决策（可在标签里带包名以消除歧义），无可引用权威依据 → 按挑战门驳回，写入误报表。

**附录观察项（不报）**

- 用户截图里的 4 个名字（`HZ-recycling-center`、`HZ-optimized-table-insert-style`、`ref_meun_def_fill`、
  `jump_to_ref_location`）**不在本工作空间已加载的插件中**（本机 desktop 只加载 6 个：snippets、install-package、
  top-bar-text、scroll-zoom、Whisper-Plus、image-squeeze）→ 该截图来自另一前端实例/设备，
  与其 `data/plugins` 内容相关，不构成内核或前端缺陷。
- `app/src/plugin/uninstall.ts:88` 清 `statusBarIcons` 的元素但不清空数组（`topBarIcons` 在 `:74` 有
  `length = 0`）——已析构实例无消费方，属代码卫生，按既有先例不报。
- 打开插件菜单会写插件实例状态（`splice`）是**渲染期副作用**：菜单只是展示入口，却改变了注册表，
  这本身是 P44 的成因；`statusBarIcons` 的对照说明该做法不是全仓惯例。

**方法论增量**

1. **「有理由的代码」不等于无缺陷**：该 `splice` 是为修 #15455 而写的正常清理逻辑，单看每处都成立；
   只有把「另一个状态位」与「恢复入口的相对位置」一起看才成立——**顺序即可达性**。
2. **注册类数组要问「它到底是台账还是渲染缓存」**：同族（`statusBarIcons`）不对该谓词剪枝，是最省力的反证。
3. 候选里「菜单不区分来源 / 标签只有显示名」这类**看不到权威依据**的条目，按挑战门必须驳回并写入误报表，
   否则会把 product 决策当缺陷长期占用报告篇幅。

## 第三十八轮（2026-09-19）：块 ID 重映射的跨入口漂移（判据 B / D1，已提 #19659）

**触发**：上一轮回答末尾列出「页签标题的重映射存在两套同语义实现（`kernel/model/tabs.go` 的
`remapTabTitleBlockIDs` 与 `duplicate_doc_tree.go` 的内联实现）」，用户要求判断是否值得改进、值得则提 issue。
范围＝「块 ID 重生成后的正文重映射」。

**基线**：`git fetch origin dev` 后 `HEAD == origin/dev`（0 落后 0 领先），工作树干净。

**发现（CONFIRMED）**：会重建块 ID 的操作（`DuplicateDoc`、历史回滚重建已删除的文档、`recreateTree`、
冲突文档恢复）只重映射块引用，不重映射正文里的块超链接 `[x](siyuan://blocks/<id>)`。

- `kernel/model/tree.go:45` 的 `resetTree` 里唯一写 `TextMarkAHref` 的是 `kernel/model/tabs.go:15` 的
  `remapTabTitleBlockIDs`（`kernel/model/tree.go:103` 调用），守卫为 `ParentIs(ast.NodeTabItem)`。
  **`ParentIs` 在 lute 里是「祖先链匹配」**（`ast/node.go:930`，遍历 `Parent` 链、深至 128 层），不是「直接父节点」，
  因此该函数的作用域是**整个页签项**（含正文），而**页签项外的链接完全无人处理**——
  与它自己的注释「改写页签标题内的块引用和块链接」也不一致。
- 临时同包测试（`kernel/model/zz_audit_tmp_remap_test.go`，用后已删）调用真实实现实测：
  `resetTree` 后 `block-ref = 新 ID (remapped=true)`、`[x](siyuan://blocks/id) = 旧 ID (remapped=false)`、
  `[x](siyuan://blocks/id?focus=1) = 旧 ID (remapped=false)`；`remapTabTitleBlockIDs` 对页签项内的
  `?...` 链接同样不命中（`TrimPrefix` 后整体查表）；`remapDuplicateDocTreeReferences` 三项全部改写并保留后缀。
- **同一操作的两个菜单入口因此行为不一致**：文档树 - 复制 - 创建副本（`duplicateDoc`，走 `resetTree`）不重映射块链接；
  复制 - 带子文档创建副本（`duplicateDocTree`）按 `docs/API-CONTRACTS.md` 的契约重映射
  （Internal block references, block links, and explicit block IDs in query embeds are remapped across the copied tree）。
- 第二条权威依据：`kernel/model/import.go:680` 的 issue #9083 修复注释（导入 .sy.zip 时块超链接必须跟着新块 ID 走）。
- 业务表现：副本里的块引用指向副本、同一段落的块超链接仍指向源文档；`recreateTree` 与历史回滚场景下旧块 ID
  已不存在，链接成为死链。
- 同族共 **6 处**实现（`tabs.go:15`、`import.go:666`、`template.go:1071`、`template_doc_tree_render.go:327`、
  `duplicate_doc_tree.go:213`、前端 `app/src/protyle/util/tabsCopy.ts:31`），只有 `duplicate_doc_tree.go`
  支持 `?`/`#` 后缀（先剥离再查表、保留后缀）。
- 已提 issue **#19659**（state=open；title 73/73、body 2444/2444 逐字符回读一致）。

**去重**：`evidence.md` 第十二轮曾把 `template_doc_tree_render.go:295`「重生成块 ID 后未调
`RemapTabsActiveIDs`/`WalkWithTabTitles`」登记为观察项（未上报）——那是同族的**另一处**（页签选中态与引用未被处理），
本轮的位置（`resetTree` 的链接重映射）与结论（跨入口不一致）不同，属增量。
`gh api search/issues` 以 5 组英文 + 5 组中文关键词覆盖 open + closed 检索，无同类报告。

**方法论增量**

1. **`ParentIs` 是祖先匹配，不是「父节点是」**。按名字读会把「作用域＝整个页签项」误判为「作用域＝标题所在段落」，
   进而把「页签项外的链接无人处理」误判成「所有链接都已处理」。**判作用域前先读谓词实现**——
   这是 D1b 恒假守卫的镜像：那里看调用者，这里看谓词本身的语义。
2. **「两套同语义实现」要按入口做差集，而不是按函数做 diff**。本轮把 `remap*` 家族全部列出后，
   真正的业务表现落在「同一菜单操作的两个入口行为不同」；只比较两个函数的写法会被判为代码卫生，而不是缺陷。
3. **临时同包测试是这类漂移最省力的取证**：直接调用两处真实函数、打印改写前后的字符串，一次
   `go -C kernel test -tags "fts5 sqlcipher" ./model -run <临时用例> -count=1 -v` 就给出「谁改了、谁没改」的对照，
   无需构造端到端夹具。附带坑：`treenode.NewParagraph(id)` 要求块 ID 形态（内部取 `id[:14]`），
   传内容字符串会 panic，传 `""` 才会自动生成。

## 第三十九轮（2026-10-07）：内核 AI / agent / MCP 子系统定向审计（5 条已提 #20186–#20190）

**范围选择**：用户从六个候选范围中选定「内核 AI / agent / MCP 子系统」（`kernel/agent/`、
`kernel/mcp/`（含 `client/`、`tools/`）、`app/src/ai/`）。这是本 skill **首次**定向覆盖该子系统——
此前只有第 15 轮顺手碰到过 `box_lease.go`（#19455）与 `plugin/api_agent.go`（判为误报）。

**基线**：`git fetch origin dev` 后 `HEAD == origin/dev`（`3426cee7cc`，0 领先 0 落后），工作树干净。

**机械扫描（增量极小，是本轮最值得记的负面结果）**：

| 扫描 | 结果 |
|---|---|
| 重复字面量（`--min-files 4`） | **0 条** |
| 重复字面量（`--min-files 2`） | 23 条，逐一回读后无真缺陷（见下） |
| 未转义插值（`app/src/ai`） | 1 条（`editor.ts:593` 的 `icon`）→ 调用点只传 `"iconCopy"`/`"iconRefresh"` 常量，**受控误报** |
| **工具注册表三方交叉比对**（自写脚本） | 34 个工具的 `action` 枚举 × `ActionEffects` 键 × handler 分派 `case` **零漏项** |

「`--min-files 4` 得 0 条」是**真实的零**而不是「没扫到」：脚本在扫描根不存在时以退出码 2 报错（第 22 轮的自审修复），
本轮先用相对路径触发过一次退出码 2、改用绝对路径后才得到 0。

23 条 `--min-files 2` 候选的构成与判定：

- **工具名字面量在 `agent.go` 与 `mcp/tools/*.go` 各出现一次**（`get_children`、`tree_stat`、`web_search`…共 15 组）——
  它们是**同一份声明在两侧的镜像**（工具表 vs 死循环签名的关键参数表），已单列成 `safeActions`/`toolSignatureKeys`
  这类显式表，属**有意的手工副本**而非单一真源缺失；两处不同步只会让死循环检测退化，不会误判功能
- `_sessionID`/`_toolCallID`（`agent/tools.go` 注入 + `mcp/tools/image.go`、`todo.go` 读取）——
  跨包协议字段，且注释已说明「原生工具专用」；判定见误报表新增条目
- `session.json`（10 处 / 3 文件）——`sessions/<id>/session.json` 的路径拼接，同目录已无同义常量可复用，
  且 `runtime.go`/`session.go` 的语义完全一致
- `authorization_required`/`oauth_retrying`（`mcp/client/mcp.go` 与 `oauth.go` 各一份）——
  **是真实的单一真源缺失**（写入 6 处 + 消费 4 处 + 前端 colorMap/switch 各一份），但**两个集合当前完全一致、漂移无可观测后果**，
  按「无可观测后果不报」的既有标准列为观察项；唯一实质缺口是 `MCPStatusItem` 的注释未列 `oauth_retrying`

### 一、发现（5 条，均已提 issue）

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1 / B（新 P45） | MCP 工具的**路由按服务名**（`mcp.go:318` 闭包捕获 `server.Name`、`:864-871` 取首个同名连接），而**注册与运行时状态按 ID**；重名时第二个服务的工具打到第一个服务的会话上，且它的 401 会把**第一个**服务的连接摘掉、凭据标记为 rejected。内核零名字唯一性校验，唯一拦截是对话框（`aiMcpServerNameDuplicate` 在 `kernel/**/*.go` 出现 0 次） | 高（机制逐环可证）/ 可达性中（正常 UI 路径被拦） | 已提 #20186 |
| C / D1 | `agent.go:526-528` 的 `Variables.Resolve` 结果在主路径被丢弃：`currentUserExists` 为真时（前端先落盘再发请求，`AgentChat.ts:2511-2535` → `:2541`，故恒真）走 `:603-609` 只回填 References/EditorContext、不更新 Content → 模型看到 `{{vars.NAME}}` 原文。同一次调用里 `sessionEntries`（`:617-623`）却被改写成解析后的值 **←同一轮里模型所见与会话历史不一致** | 高（代码 + 前端顺序 + 指南文本三重） | 已提 #20187 |
| D1 / B | `app/src/ai/actions.ts:115-118` 的 `filterAI` 大小写敏感（两侧都无 `toLowerCase`），而条目文案是首字母大写的英文（`Continue writing`/`Extract summary`/`Fix grammar, spelling and typos`），且同仓 5 处同类过滤（`menus/layouts.ts:301,319`、`util/fileTree.ts:21,30`、`menus/commonMenuItem.ts:414`、`protyle/toolbar/fontFamilyMenu.ts:188,194`、`protyle/util/index.ts:2034-2040`）一律双向折叠 | 高 | 已提 #20188 |
| D1 / I2 | `app/src/ai/editor.ts:556-567` 的 `fetchAIEditorSSE(...).catch(...)` 不调 `finishTaskReasoning`，而另外三处（`:461`/`:478`/`:505`）都调 → reasoning 阶段传输失败后「思考中 Ns」继续每秒 +1 直到关闭面板。可达性由 `editorSSE.ts:92-95`（非 SSE 响应）与 `:126-130`（无终止事件）保证 | 高 | 已提 #20189 |
| D1 / B | `app/src/ai/skills/manager.ts:379-386` 的前端名称校验（规则在 `util/fileTree.ts:7-12`，仅空/`.`/`..`/`\ : /`）窄于内核（`kernel/util/skill_manage.go:57-75` 另拒结尾点号、`<>"\|?*~`、控制字符、首尾空白、Windows 保留名），且 `:385-386` **先销毁对话框再调 API** → 未本地化的英文错误 + 输入丢失 | 高 | 已提 #20190 |

### 二、第 2 条的权威依据是「用户指南与本轮发现方向相反」的一次例外

按既有方法论「不要用文档证明实现行为」（第 18 轮迁移把新行为追认进文档），本轮**反过来用指南确立预期**：
`app/guide/20210808180117-6v0mkxr/20200923234011-ieuun1p/20210808180303-xaduj2o/20260804185002-secvr03.sy:11`
写明 *Skill bodies and chat messages can use variables. Secret placeholders are not expanded in AI conversations…*
——指南明确承诺「聊天消息可用变量」，而实现丢了这条路径。
**判据：文档可用于证明「承诺了某能力」，不可用于证明「某行为是有意设计」**；前者是需求侧，后者是迁移会追认的。

### 三、被挑战门拦下/降级的候选（勿重报，除非有新证据）

- **`headerRoundTripper` 跨主机重定向转发明文令牌**（`mcp.go:196-204`）：每个出站请求都 `Header.Set` 一遍配置头，
  而 Go 的 `http.Client` 在跨主机重定向时**先**剥离 `Authorization` → 这里在剥离之后又加回去；
  注释声称的「防止密钥被转发到其他主机」只对 `{{secrets.*}}` 占位符成立（`ResolveSecretsVarsForHost` 在 host 未命中时保留原文）。
  机制成立且**明文静态令牌不受 host 约束**，但这属**安全审计范畴**（本 skill 的 `description` 明确排除安全审计）→ 不作为本 skill 的发现，只在报告附录记录建议由安全视角单独评估
- **`sql.go:35-40` 的 `ActionEffects` 含 `"": {LocalRead: true}` 兜底键**：使未知 action 在确认决策里被当成只读。
  但 handler 对未知 action 仍要求 `stmt`，且 `CheckReadonlyStatement`/`CheckReadonlyStatementInBox` 两侧都在 → **无可观测后果**；
  风险是「将来新增 action 时静默放行确认」，属将来引入的坑，记录不报
- **`skill.go` 的 `"": {LocalRead: true}` 兜底**：同上，且 `load`/`""` 都真的只读
- **`log.go` 的敏感串清单**（`accesskey`/`password`/`token`…）被脚本误报为「case 但不在枚举」，实为脱敏关键字表，非 action 分派

### 四、本子系统已完成的排除项（后续轮次省去重复投入）

- **工具注册表三方一致性零漏项**：34 个工具的 `action` 枚举、`ActionEffects` 键、handler `case` 三方 diff 全等；
  `ActionEffects` 无「枚举里没有的键」，枚举里的写操作全部声明了 `LocalWrite`
- **`safeActions` / `safeWholeTools` 全局 action 白名单**：逐工具核对后**未发现写操作与白名单同名**
  （`notebook.open/close`、`template.render`、`ref.refresh`、`export.md` 均为只读语义）；
  `import.md` 有专门的前置拦截（`:1723-1726`）→ 第 15 轮「全局 action 白名单可被新工具撞名」的担忧本轮未命中
- **SQL 工具的双重只读校验**：`sql.go:52-59` 的 `CheckSingleStatement` + `CheckReadonlyStatement(InBox)`，
  底层 `stmt_validate.go:198-228` 另有 `isReadonlyQueryStatement`（提前拒 ATTACH/DETACH/事务控制）+ `sqlite3_stmt_readonly` → 无旁路
- **`Tool.EffectsFor` / `IsAvailable` 的 nil 守卫**：见误报表新增条目（形态上像 D1d，实际自带守卫）

### 五、方法论增量

1. **「同一文件里两层用不同的身份」比「同一份数据写两遍」更值得单列**：本轮 5 条里 3 条是它的变体
   （ID/Name 路由、解析值被丢弃、前端/内核两份校验），归纳为 D1p + P45。
   **跨层比对**是它的唯一入口——静态看每层都对。
2. **`--min-files 4` 得 0 条要先自证「不是没扫到」**：本轮先用相对路径触发退出码 2，改用绝对路径后才得到 0。
   **零发现与没扫到在输出上无法区分**，这正是判据 A 里写的那条，本轮实际用上了一次。
3. **「前端校验窄于内核」的取证要点是「顺序」而非「差异」**：差异只是候选，
   真正决定后果的是 `inputDialog.destroy()` 在调 API **之前**——若它在之后，同样的差异只是「多一次往返」。
   已写入 SKILL.md 判据 B 的第二个入口。
4. **指南文本在本轮是「需求侧权威」**：判据是「文档可用于证明承诺了某能力，
   不可用于证明某行为是有意设计」。这两件事此前被我混用，本轮首次分开。

## 第四十轮（2026-10-07）：内核 util / server / filesys / cache 定向审计（6 条，未提 issue）

**范围选择**：用户从候选范围中选定「内核 util / server / filesys / cache」（103 个非测试文件 ≈ 23.8k 行）。
基线 `git fetch origin dev` 后 `HEAD == origin/dev`（`089a83e5be`，0/0），工作树干净。**取证基线**：本轮全部发现
都只需「读代码 + 读厂商文档/上游源码」即可定性，**不依赖前端产物**（第三十四轮的 ⑦ 号陷阱不适用）。

**机械扫描（增量 = 0，但仍是「真实的 0」）**：`scan_duplicated_literals.py --min-files 4` 对四个目录只出 **7 条**，
逐条回读后全为噪声：`assets/`（5 处路径前缀）、`image/{jpeg,png,webp,gif}`（多模态白名单）、`127.0.0.1`、`conf.json`。
**「少到可以逐条读完」不等于「没扫到」**——脚本在扫描根不存在时以退出码 2 报错，本轮用相对路径时确实触发过一次退出码 2。

### 一、发现（6 条，**均已提 issue**）

| 判据 | 发现 | 置信度 |
|---|---|---|
| D1b / D1d | `kernel/server/serve.go:1935-1937` 的三条**裸类型断言** `request["cmd"].(string)` / `["reqId"].(float64)` / `["param"].(map[string]any)`，唯一守卫是 `s.Get("app")`（只证明**会话**有 app，不约束消息体）→ 任何人发 `{}` 即 panic；panic 发生在 melody 的 read 协程内，**melody 无 recover**（`melody@v1.4.0/session.go:118-153` 直接调 `messageHandler`），`cmd.Exec` 的 `logging.Recover()` 也包不住（在 `NewCommand` 内、`Exec` 之前）→ **整个内核进程被终止** | 高 |
| D4 变体 | `kernel/util/session.go:133` `lockSec := authThrottleLockBaseSec << (throttle.FailCount - authThrottleMaxFail)`：锁定期间每次请求仍 `FailCount++`（调用点 `api/filetree.go:1444`、`model/session.go:332/403`、`server/proxy/publish.go:217`，注释明写「锁定期间持续记录失败」）→ `FailCount ≥ 64` 时移 64 位得 0、`59..63` 位时最高位落到 bit63 得**负数**，`if authThrottleLockMaxSec < lockSec` 钳位失效，`LockUntil` 落在过去 → `AuthThrottleCheck` 删记录并返回 0 → **限流被清零**（本机 `int` 64 位；GOARCH=386 上更早触发） | 高 |
| D3 | `kernel/util/anthropic.go:500-516` 的 `anthropicFinishReason` 只认 5 个 `stop_reason`，厂商枚举共 7 个：漏 `pause_turn`（长 turn 暂停）与 **`model_context_window_exceeded`**（超上下文，长对话里必然出现）→ `default` 返回 error，`message_stop`（`anthropic_stream.go:218`）处把**已经流出来的内容整体丢弃**。对照侧 `openai_completion.go:527-538` 的 `responseFinishReason` 对未知值一律回退 `Stop` | 高 |
| B / D1i | `kernel/util/websearch.go:99-103` 不检查 `resp.StatusCode`，`mcpResponse` 结构体**没有 `Error` 字段** → 401/429/500 与 JSON-RPC error 全部落成 `text == ""` → 返回 `("No search results found. Please try a different query.", nil)`。同族 `webfetch.go:62-64` 对 `>=400` 返回 error、`httprequest.go` 把状态码交调用方判断 | 高 |
| D3 | `kernel/util/misc.go:159-160` 的 `HasUnclosedHtmlTag` 空元素白名单只有 6 个（`br/img/hr/input/meta/link`），HTML 规范的 void elements 是 **14** 个（缺 `area/base/col/embed/param/source/track/wbr`）→ 模板输出只要含这些标签就被判「有未闭合标签」，唯一调用点 `kernel/sql/av.go:497` 把**整段输出 `EscapeHTML`**（本应渲染为 HTML 的模板单元格变成源码文本） | 中 |
| 资源与生命周期 | 包级 map 在**写侧不加锁**且只增不清，读侧在别的 goroutine：`kernel/util/rune.go:88` 的 `NativeEmojiChars`（写侧 `InitEmojiChars` 由 `model.InitAppearance()`/HTTP handler 触发，读侧 `model/assets.go:2523-2526` 的 `emojisInTree`）与 `kernel/util/rhy.go:58`（`cachedRhyResult` 的**快路径在锁外**读 `rhyResultCacheTime` + `len()`，写侧 `getRhyResult0` 持锁并让 `SetSuccessResult(&cachedRhyResult)` **就地**反序列化写入）。Go 的并发 map 读写是 **unrecoverable fatal**，直接终止内核 | 中（机制已证，未跑 `-race`） |

**已提 issue（2026-10-07，逐字段回读一致，title / body 长度均相等）**：
#20193 WS 消息裸断言致内核终止 · #20194 认证限流左移溢出清零 · #20195 Anthropic `stop_reason` 漏 2 个成员 ·
#20196 网页搜索吞掉 HTTP / JSON-RPC 错误 · #20197 数据库模板空元素白名单 6/14 → 误转义 · #20198 两处并发 map 读写。

建前用 `gh api -X GET search/issues` 对 open + closed 检索 15 组关键词：`auth throttle`、`认证 限流 锁定`、`anthropic stop_reason`、
`model_context_window_exceeded`、`pause_turn`、`No search results found`、`websearch exa`、`HasUnclosedHtmlTag`、
`模板 转义 未闭合`、`concurrent map read`、`NativeEmojiChars`、`ws "type assertion" panic` 等全部 `total_count=0`；
仅 `"fatal error"` 命中 **#19346**（create 操作里 AST 树泄漏引起的另一处 map race，位置不同），
已在 #20198 正文中显式区分。未随创建载荷提交 labels（无 push 权限时会被静默丢弃，按 `AGENTS.md` 不做补标签请求）。

### 二、被挑战门拦下/降级的候选（勿重报，除非有新证据）

- **`working.go:171-181` 的 `if ContainerStd != Container { ServerPort = FixedPort }` 是恒假守卫**：`RunInContainer` 只在 `initEnvVars()` 里赋值，而 `initEnvVars` 只被 `InitWorkspace`（`:95`）调用，该守卫却在 `:181` 之前的 `:175` 执行（引入者 `13602b8aed`/PR #9720）。但**当前无可观测后果**：容器内 `ServerPort` 保持 `0` 后由 `proxy/fixedport.go` 的反代兜住 6806，唯一差异是 `UserAgent` 记成 `std`、`Conf.ServerAddrs` 是随机端口 → 降为观察项，不占报告主条目
- **`util/tooloutput.go:46` 的 `filepath.Join("data", …)`**（写盘用绝对 `DataDir`、回给智能体的是相对路径）→ **是既定形式**：`DataDir` 恒为 `<ws>/data`，相对路径正是给智能体 file 工具的输入 → 误报
- **`filesys/tree.go:441/447/461` 的 `filelock.Lock` + 两处 `Unlock`** → 逐分支核对为**配对**（错误分支 `Unlock` 后 return，成功分支 `Close` + `Unlock`），不是重复解锁
- `util/ocr.go:377-405` 的 `TesseractLangs` 守卫查的是**过滤前**的 `langs`，过滤后可能为空数组而 `TesseractEnabled` 仍为 true → `ocr.go:286` 拼出 `-l ""`（需把 `SIYUAN_TESSERACT_LANGS` 设成与已装语言无交集的集合）；机制成立但触发条件苛刻，观察项
- `util/file.go:506` 的 `DataSize()`（`strings.Contains(rel,"assets")`）与 `workspace_storage.go:149` 的 `workspaceStorageAsset` 是同一「资源大小」的两套口径（前者把 `plugins/*/assets`、`myassets` 也算进去）→ 属 B 类漂移但老口径已无 UI 消费点（只在 `Conf.Stat`/日志），观察项
- 另排除：`appearance_ignore_migration.go` 严格匹配 7 行隔离块（有测试、fail-safe）、`path_guard.go` 未发现第二份黑名单实现、`etag.go` 与 qetag 官方实现逐行等价且无远端比对调用点、`ocr_relink_batch.go` 的三重并发守卫完整、`cmux.go`/`operation_watchdog.go`/`kdf.go`/`encrypted_index.go` 逐文件读完无缺陷

### 三、方法论增量

1. **厂商文档是闭合集合的权威源，且能一次核两组**：本轮用一次 fetch 同时确认了 Anthropic 的 `stop_reason` **7 个成员**与 `Base64ImageSource.media_type` **4 个成员**——后者正是 `openai.go:792`/`anthropic.go:335` 那一对白名单的权威依据，从而把它从「疑似漂移」定为「同一策略的两份字面量」（低危，不报）。
2. **「守卫通过」不等于「值合法」**：`s.Get("app")` 只证明**会话**有 app（`AddPushChan` 在 `:139` 先 `Set("app")` 才检查 id/type），完全不约束**消息体**的键；把存在性守卫当成结构校验是 D1b 的另一种形态。
3. **越界把「有界惩罚」反转为「无惩罚」**（D4 的新变体）：`base << n` 在 `n ≥ 位宽` 时为 0、在最高位落到符号位时为负，于是紧随其后的 `if 上限 < 值` 钳位**恒不成立**。凡「指数退避 + 上限钳位」都要检查 `n` 是否有界；本仓 `session_test.go` 只测到 11 次失败，够不到溢出点——**测试盲区与溢出点之间的距离就是这类缺陷能长期存活的原因**。
4. **子代理产出必须逐条回主上下文核对**：3 组子代理共 18 条候选，回读后 **6 条进入报告**；被丢掉的主要是三类——「用途不同的各自白名单」（MIME 三处）、「无消费方」、「可达性未证」（`tooloutput` 相对路径）。
5. **机械扫描为 0 或个位数时，先自证「不是没扫到」再收工**（与第三十九轮同源，本轮再次用到）。

## 第四十一轮（2026-10-07）：内核 bazaar / job / task / conf / search / plugin 定向审计

**范围选择**：用户从候选范围中选定「内核 bazaar / job / task / conf / search / plugin」（112 个非测试 .go 文件 ≈ 24.5k 行）。
这是本 skill 首次定向覆盖该组合：`kernel/plugin/` 此前只有第 15 轮顺手碰过 `api_agent.go`（判为误报）与 `box_lease.go`；
`kernel/bazaar/`、`kernel/job/`、`kernel/task/`、`kernel/conf/`、`kernel/search/` 此前从未系统扫过。
**基线**：`git fetch origin dev` 后 `HEAD == origin/dev`（`089a83e5be`，0 领先 0 落后），工作树干净。
取证全部基于源码阅读与上游源码核对，不依赖前端产物（第三十四轮 ⑦ 号陷阱不适用）。

**机械扫描（真实的零，非「没扫到」）**：

| 扫描 | 结果 |
|---|---|
| `scan_duplicated_literals.py --min-files 4`（六个根，112 文件） | **0 条** |
| 同上 `--min-files 2` | 9 条，逐条回读全为噪声（`/package/` 模板、`icon.png`、`kernel.js`、`JSON`、`X25519`、`Symbol.asyncIterator`） |
| 全仓 `--min-files 4`（kernel + app/src，1822 文件）中涉及本范围的条目 | 仅 MIME 类型（`text/event-stream`、`application/octet-stream`）、配置文件名（`plugin.json`、`template.json`、`widget.json`）、`127.0.0.1` |

两个脚本均以绝对路径运行且退出码 0（先用相对路径确认触发过退出码 2），符合判据 A 的「先自证不是没扫到」。

### 一、发现（2 条进主报告，均已提 issue）

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1 / D4 | `kernel/task/queue.go:85-101` `containTask` 遍历任务时，**遇到第一条同 action 的任务只要参数不匹配就直接 `return false`**，不再扫描其余同 action 项 → `uniqueActions` 的「同一 (action, args) 至多一条」去重失效。两处 `return false` 在 `:89`（参数个数不同）与 `:94`（参数不相等），均在 `if t.Action == task.Action` 块内。权威依据是同文件 `:234` 的注释「uniqueActions 描述了唯一的任务，即队列中只能存在一个在执行的任务」+ 参数比较逻辑本身的存在。受影响的是带实体参数的动作：`RepoCheckout(id)`、`ReloadProtyle(id)`、`ReloadAttributeView(avID)`、`SetDefRefCount(defID)`、`UpdateIDs(blockIDs)`。`git log -L 85,101:kernel/task/queue.go` 显示该结构自 `9560277d0c`（#12393）引入后未变，仅 `63ae805106`/`30bf687d1b` 改过比较器 → **长期潜伏，非新引入**；去重机制本身的原始需求是 #7270「后台任务按任务加入先后顺序去重执行」 | 高（6 行函数，代码可证；`gulu.Str.Contains` 已核为精确匹配 `v == str`，排除子串误判） | 已提 #20199 |
| D1 / 资源与生命周期 | `kernel/plugin/plugin.go:1452` 的 `events.In <- e` 是裸通道写；`events` 为 `chanx.NewUnboundedChan[sse.Event](ctx, 16)`（`:1396`），消费方是 `:1525-1543` 的 `for/select`（`ctx.Done()` 与 `c.Request.Context().Done()` 两条 return）。`ctx` 取消后 chanx 的 `process()` 直接 return（`chanx@v1.2.0/unbounded_chan.go` 外层 select 首支），此后 `In`（容量 16）无人读 → 设 pump 退出时 `In` 内已有 k 项，则再成功入队 16−k 次（这些同样不会被送达）后第 16−k+1 次**永久阻塞**。`port_send` 是 goja 原生函数、在 VM 线程上同步执行 → 整个插件 JS 冻结（`p.worker.Run` 串行化把 `onclose` 也堵住），随后停用/重载/卸载卡在 `invokeHook`，内核正常退出（`force:false` → `model.Close` → `OnKernelPluginsStop` → `PluginManager.Stop` 的 `wg.Wait()`）挂起。同一文件 `done <-`（`:1513`/`:1520`）与 `server.go:346-350` 的 `chunks` 都用了带 `ctx.Done()` 的 select，裸写是唯一异类 | 高（机制逐环 + chanx/goja 源码核对；未做端到端实测） | 已提 #20200 |
| A（观察项） | `.siyuan-package-install-` 前缀在生产者 `kernel/bazaar/install.go:202` 与消费方 `kernel/model/bazaar.go:305`、`kernel/model/boot_appearance.go:146` 三处裸写；其中 `bazaar.go:305` 在 `ParsePackageJSON` **之前**拦截，失效会生成 `invalid-manifest` 记录（承重点与另两处不同），因此不能靠「包名首字符 `.` 一律拒」省掉 | 中 | 附录观察项 |
| 资源与生命周期（观察项） | `kernel/plugin/abort/signal.go:145-149` `AddAbortHook` 只 append、仅在 `triggerAbort` 清空；`api_client.go:155` 每次 `fetch(...,{signal})` 登记一个 hook，`streams/pipe.go` 的 `pipeTo({signal})` 同 → 插件复用长命 `AbortController` 时 `goHooks`/`listeners` 随调用次数单调增长（abort 时多出 O(n) 空转） | 中 | 附录观察项 |
| 资源与生命周期（观察项） | `kernel/bazaar/plugin.go:94-104` `cachedBackend` 包级变量无同步（同包 `installSizeCache`/`bazaarInfoCache` 都带锁）；并发只在「全新进程首次调用」的窗口，判错仅影响该轮插件兼容性标记、下次刷新自愈 | 低 | 附录观察项 |

### 二、被挑战门拦下/降级的候选（勿重报，除非有新证据）

- **`Blob.prototype.stream()` 缺失 → DOWNGRADED 至 LOW（文档级）**：`kernel/plugin/formdata/blob.go:264` 与 `formdata.go:59-60` 都写「沙箱没有 ReadableStream，因此不提供 stream()」，而 `streams/module.go` 的 `Enable` 会把 `ReadableStream` 挂上 globalThis（`sandbox.go:111-112` 依次调用两个 Enable）—— 该理由**从未成立**（不是「后来失效」，两个包由同一提交 `2d0a77e738`/#20118 引入）。但：① 该 shape 被测试锁死（`formdata/blob_test.go` 的 `TestBlobInterfaceShape` 断言 `typeof Blob.prototype.stream === "undefined"` 并锁定成员列表），改它必须同步改测试；② 真正的硬约束是**规范要求 `stream()` 返回 type "bytes" 的字节流，而 `streams` 包明确不实现字节流**（无 `ReadableByteStreamController`/BYOB reader）；③ 备选修法「调用时惰性解析全局 `ReadableStream`」**有害**（违反 `formdata.Host` 注册时捕获内建对象的防篡改设计）。→ 只值得一条「修正注释理由、写明真实约束」的文档修正，不作为缺陷上报。
- **`invokeHook` 无界等待 → DOWNGRADED 至 LOW，且建议修法在全部调用点不可达**：`plugin.go:931` 是裸 `result := <-done`，而同族 `invokeAgentCapability`（`:454`）与 `callRpcMethod`（`:728-732`）都 select ctx。但：① petal `kernel.d.ts` 的 `IRequestInit.timeout` remarks **已明文承认**「`onunload` 中不设超时的 await 会让插件停止与内核退出无限期阻塞」，本条增量仅「`onload`/`onrunning` 同样适用 + 任意不落定 Promise 亦可」；② **按同族加 `case <-p.context.Done()` 在三个调用点全是死代码**——三个调用点（`onload`/`onrunning` ← `start()` ← `StartPlugin`；`onunload` ← `stop()` ← `stopLocked`）都运行在持有 per-plugin mutex 的 goroutine 上，唯一能取消 `p.context` 的 `stop()` 需要先拿同一把锁、`error()` 又必然发生在 `invokeHook` 返回之后 → 等待期间 `p.context.Done()` 永不关闭。真正需要的是**引入取消源或有界等待**（仓库内前端已有同类机制：`app/src/plugin/lifecycle.ts` 的 `teardownTimeout`），属产品取舍而非一行 select。
- `NormalizeEntryVisibility`（`kernel/conf/appearance.go`）末尾两段**逐字重复的 if 块**（仅赋值不同）：第二段只在 `fallback` 本身非法时生效，属「二次回落」防御，非缺陷；不报。
- `kernel/bazaar` 在线安装（`install.go:156` 的 `gulu.Zip.Unzip`）与本地安装（`local.go:139-141` 显式拒符号链接）对归档内容的处理不对称：机制成立，但集市官方打包在 Linux runner 上产出（正斜杠、无符号链接），自有仓库才可能命中 → 降为低，未上报。

### 三、方法论增量

1. **「最新一次改动碰过同一文件」不等于「它是本次缺陷的引入者」**：我（与第一轮子代理）都以为 `events.In <- e` 出自 `2d0a77e738`（该提交确实在 `server.go` 加了同一守卫），`git show 2d0a77e738 -- kernel/plugin/plugin.go` 核出它只动了 25 行且全是 `formdata`/`readableStream` 相关；实际引入者是 `e564ce7b1f`（#17487）/`c4ae1d44e5`（#17670）。**归因前必须看该提交实际改了哪些行**，而不是看提交标题与文件是否重合（与第十七轮「编号→提交不能只看提交信息」同源，方向相反）。
2. **「同一文件/同族的另一处已有守卫」比「兄弟实现更完整」更稳**：`server.go` 的 `chunks` 是**背压**通道、`events` 是**即发即忘**队列，语义并不相同——若按「照抄兄弟实现」立论，会被「两者语义不同」驳回。正确立论是**危害类别相同**（生产者都在事件循环线程上同步执行、消费者都可能提前退出），因此守卫可移植。修法审查还要排除「用 `default:` 做非阻塞版」——那会在 pump 只是暂时积压时丢掉合法事件，比原问题更坏。
3. **「注释声明的已知差异」要分两件事查：理由是否真实、约束是否真实**。`Blob.stream` 一例中理由（无 ReadableStream）是假的，但约束（规范要求字节流、本仓 streams 不实现）是真的，且 shape 被测试锁死 → 三者合起来把「缺陷」降为「文档修正」。**只查「理由是否真实」会得出「应当补实现」的错误结论。**
4. **降级理由本身是技术断言时，要把可达性算到调用点**：`invokeHook` 那条的「对齐同族」建议看似无可指摘，但把取消者（`stop()` 需要 `pluginMu`）与等待者（`invokeHook` 持 `pluginMu`）并列一画，守卫立刻变成死代码。**「与同族写法一致」不构成建议成立的证明**，要额外回答「该守卫在这条调用路径上会不会被触发」。
5. **`gulu.Str.Contains` 是精确匹配**（`string.go` 的 `func (*GuluStr) Contains` 即 `v == str`），不是子串匹配——本轮的子串误判猜测已被源码排除，后续可直接引用此事实。
6. **子代理产出必须逐条回主上下文核验**：本轮 2 个子代理共给 10 条候选，回读后 2 条进主报告、2 条被挑战门降到文档级/观察项、3 条推翻（`parseRequest` 的单次 Read 截断、`writeStreamResponse` 的头序、`fetch` body 只认 ArrayBuffer 的「静默丢弃」），其余列入排除清单。

### 四、本轮排除清单（后续轮次省去重复投入）

- `kernel/search/hanconv_table.go`（2959 条）与 go-sqlite3 fork `sqlite3-binding.c` 的 `aSiYuanHanPages` 逐码点比对：only-in-Go 0、only-in-C 0、值不同 0；C 侧只对 3 字节 UTF-8 查表且 Go 表范围全在其中；`sql/database.go` 的 `han_insensitive` 与 `!hanSensitive` 方向一致 → 无漂移。
- `kernel/job/cron.go` 注册的每个 job 与 `kernel/**` 中全部 `*Job()` 定义逐一对照，无「有定义未注册」；`AutoFixIndex` 的 1 分钟调度与内部 `idleFixThreshold`/`fixCooldown` 不冲突；`RefreshHPathsJob` 先 `sort` 再取 `keys[0]`，map 遍历顺序不影响结果。
- `kernel/task/queue.go` 的锁序（`queueLock` → `currentTaskLock`）在全部路径一致；`StatusJob` 持 `queueLock` 至 `PushBackgroundTask` 不构成跨 I/O 持锁（melody v1.4.0 的 `Write` 是 `select { case output <- msg: default: }` 非阻塞）。
- `kernel/plugin/sandbox.go` 的 `pluginSourceLoader`（`filepath.Separator` 前缀 + `os.OpenRoot`）在 Windows/Linux 均成立；`crypto/` 的 `usageTable`/`formatTable`、AES-CTR 回绕分段、PKCS#7 常时间比较、HKDF/PBKDF2 长度校验、`pipeTo` 的 `prevent*` 分支、`AbortSignal` 的 `addEventListener` 去重/`removeEventListener`/`any` 传播逐条对照 WHATWG/RFC 未见漂移。
- `kernel/bazaar/`：`downloadBazaarFile` 的 `LastIndex("@")`、`isSupportedPackageImageName` 白名单、`installed.go` 的 `installSizeVersion` + singleflight 版本守卫、`local.go` 的五条错误分支均调用 `cleanup()`、`index.go`/`rating.go` 在初始化期捕获 `util.BazaarStatServer`（全仓仅一处常量赋值，捕获安全）。
- `kernel/conf/appearance.go` 的入口可见性路径（`gutter.single.listBlock` + `taskStatusTodo/InProgress/Done/Canceled/customTaskStatus` + `separator_taskStatus`、`gutter.single.height`、`gutter.single.chart.*`）与 `app/src/config/entryVisibility/catalog.ts` 逐项核对一致；`migrateTaskStatusMenu`/`migrateChartHeightMenu` 的迁移目标在当前目录中都存在。
- `kernel/plugin/streams/`、`formdata/`、`encoding/`、`abort/` 为 #20118 新增的 Web API 移植层，除上文两条候选外未发现漂移。

---

## 第四十二轮（2026-10-08）：内核 L1 数据与索引定向审计（1 条确认 + 8 项已核对为干净）

- 基线：目标仓库 `HEAD == origin/dev == 2b02f86fde`（0/0），分支 `dev`，工作树干净；范围由用户选定 =
  `kernel/model` 的导入导出/历史/索引 + `kernel/sql` + `treenode` 读写路径（257 个 Go 文件），**只读审计**
- 机械扫描：`--min-files 4` **14 条**、`--min-files 2` **83 条**，逐条回读**全为已知噪声**
  （`assets/`、`siyuan://blocks/`、`/export/`、`conf.json`、`sort.json`、`petals.json`、`plugin.json`、
  `.sy.zip`、`.action{`、`query_embed`——最后一条第 11 轮已核实为误报）
- **唯一确认（低，判据 D3 闭合集合漏项；第 16 轮已登记为「未取证候选」，本轮只补证据）**：
  `kernel/sql/index_queue.go:110` 的 `dbOpToIndexEntry` 缺 `update_block_content` 分支 →
  `default: return nil`（`:141`）→ `appendToIndexQueue`（`:76`）静默返回 →
  该 op **永不写入 `temp/queue/index.queue`**。
  **同族四处 action 分派 switch 里三处都登记了它**（`queue.go:99` backlinkIndexChange、`:159` boxID、`:472` execOp），
  唯「磁盘序列化」这一处漏 —— 同包自相矛盾再次是最省力的判定入口。
  `git log -S update_block_content -- kernel/sql/index_queue.go` **为空** → 自磁盘队列引入
  （`b0177c4aa1`，2026-05-13）起从未支持；而该 action 自 2023-01-31（`204580bf36`，issue #7213）就存在 → 引入队列时漏项。
  **可达**：`getEmbedBlock(updateIndex=true)` → `model/index.go:463 updateEmbedBlockContent` →
  `UpdateBlockContentQueue`（`queue.go:516`）——前端每次渲染嵌入块（`/api/search/getEmbedBlock`）都走这条路径。
  **后果**：非正常退出（崩溃/断电/被杀）后，嵌入块的 `blocks.content` / `blocks_fts.content`
  （`sql/block.go:135 updateBlockContent`）保持旧值；10 分钟一次的 `IndexEmbedBlockJob`
  （`job/cron.go:43` → `model/index.go:386`）只补 `content = ''` 的嵌入块（`sql/block_query.go:38`），
  因此**非空但过期**的内容不会被自愈（重开该文档触发再次 `getEmbedBlock`，或全库重建才修）。
  正常启动只走 `sql/database.go:133 recoverIndexQueue()` 重放磁盘队列，**不重建全库**
- **修法陷阱（本轮最值得记）**：`indexEntryToOp` 若照抄兄弟分支「`filesys.LoadTree` + `buildBlockFromNode`」，
  写入的是**字面 `{{…}}` 查询脚本**而不是查询结果 —— 比原问题更糟：它非空，于是 10 分钟任务永远不再修它。
  正确修法是重算查询结果（复用 `autoIndexEmbedBlock` 的查询逻辑），或在 entry 中携带足够信息重建该值
- **本轮「已核对为干净」（后续勿重复投入）**：
  ① 删除路径的表集合闭合——`batchDeleteByPathPrefix`/`deleteByRootID`/`batchDeleteByRootIDs` 三者一致覆盖
  blocks_fts/blocks/spans/assets/refs/file_annotation_refs/attributes（`block_embeddings` 由调用方另删），与建表集合一一对应；
  ② 容器块闭合集合三份实现一致（`treenode.IsContainerType` / `model.Block.IsContainerBlock` / sql 委托版，各 10 项），
  缩写表 `typeAbbrMap` 无冲突，与上游 Lute `ast.Node.IsContainerBlock()` 仅差脚注定义块（建文档时脚注已转列表项，属有意排除）；
  ③ `removeDoc` 用路径前缀删除**覆盖文档自身**是有意设计——文档文件名即文档 ID（`path.go:62-110`、`file_test.go:199`）；
  ④ `documentPathPrefixCondition`（`sql/delete_path.go:29`）的范围约束是 LIKE 匹配集的**超集**（非 ASCII/通配符走回退分支）；
  ⑤ `nonEditorTx` 是 nil 接收者但不会 panic（`getAttrViewBoundNodes` 有显式 `nil == tx` 分支）；
  ⑥ `finishAttributeViewMutation` 二次调用幂等（state 置 nil 后早退）；
  ⑦ sort.json 的读-改-写全部持 `fileTreeSortLock`（无丢失更新）；
  ⑧ 索引订正流水线五步的进度推送齐全（1/5–5/5）
- 观察项（未报）：`model/index_fix.go:472` 的 `if nil == root { continue }` 是恒假守卫（map 值来自非 nil block），仅冗余防御
- **已提 issue #20214**（state=open）：`Embed block content index is missing from the crash recovery queue, so it stays stale after an abnormal kernel exit`。
  正文首段为对应中文标题；标题/正文逐字段回读一致（115/115、2164/2164，`rstrip` 后完全相等）。
  **去重检索**（覆盖 open + closed）10 组关键词：`update_block_content`/`dbOpToIndexEntry`/`IndexEmbedBlockJob`/`UpdateBlockContentQueue` 均 0 命中；
  `indexEntryToOp` 命中 #17716（**刷盘过程中崩溃**，症状与位置均不同）、#18034；`embed block index crash recovery` 命中 #20175
  （**恢复/汇总类**批量 issue）——两条均已读正文确认不覆盖本条，非重复报告。labels 未随载荷提交（无 push 权限会被静默丢弃，按 `AGENTS.md` 不做补标签请求）

## 第四十三轮（2026-10-08）：功能架构 / 代码组织定向审计（全仓库；主报告 0 条用户可见缺陷，3 条组织层问题进附录）

- 基线：目标仓库 `HEAD == origin/dev == 2b02f86fde`（0/0），分支 `dev`，工作树干净；**只读审计**（用户选定「全仓库（内核 + 前端，含跨层注册表）」+「缺陷 + 架构观察项」）
- 机械扫描：重复字面量 `--min-files 4` **323 条** / 1851 文件（P1 263 / P2 23 / P3 37），逐条回读全是已知噪声
  （`assets/`、`/stage/loading-pure.svg`、`/api/block/getDocInfo`、`conf.json`、`sort.json`、`petal.json`、
  `plugin.json`、`127.0.0.1`、`image/png`、`separator_1`/`separator_2`、`INPUT`/`SPAN`/`BUTTON`…）；
  `scan_dom_type_literals.py --kind node` 得 **27 个 Node\* 值 / 528 处引用，零疑似拼写漂移**
- **本轮是负面结果为主的一轮**，最值得记的是「哪些看似可疑的注册表其实干净」：

### 已核对为干净（后续轮次勿重复投入）
1. **命令 / 快捷键注册表三方集合零漂移**。自写脚本提取 `Constants.SIYUAN_KEYMAP.general`（72）与
   `.editor.general`（71）、`nativeCatalog.ts` 的 `DESKTOP_COMMAND_PANEL_GENERAL_KEYS`（68）/
   `MOBILE_...`（26）/ `COMMAND_PANEL_EDITOR_KEYS`（2）做差集：**幽灵键 0、重复项 0、移动 ⊆ 桌面成立**。
   未进面板的 4 个（`agentChat`/`agentSend`/`commandPanel`/`openContextMenu`）是「面板自身入口」与
   「上下文/Agent 专用」，属有意排除；`editor.general` 71 个只暴露 2 个也是有意的分类
   （`nativeCatalog.test.ts`/`registry.test.ts` 已钉住）。`registry.ts` 还有 `id` 重复即 `throw` 的自检。
2. **设置页签注册表是单一对象字面量**（`config/setting/tabs.ts` 的 `createSettingTabs()`），
   桌面 `config/index.ts` 与移动 `mobile/menu/mainMenu.ts:273` **都迭代 `getSettingTabDefs()`**，
   不存在第二份；`settingTabToMenuId()` 由同一个 key 生成，无漏项空间。
3. **前端无孤儿模块**。对 1617 个 TS 文件建 import 图，只有 8 个「无人导入」，逐个核实全为合法：
   3 个 webpack 入口（`mobile/index.ts`/`protyle/method.ts`/`window/index.ts`）、3 个 Worker
   （`AgentMarkdownWorker.ts`/`layoutWorker.ts`/`RecordMediaWorker.ts`，按 URL 字符串加载）、
   `config/setting/window.ts`（独立设置窗口入口）、`asset/anno.ts`（**由 `.js` 导入**，见误报表）。
4. **跨文件同名导出只有 10 组**，逐组回读全部合法（见误报表新增条目）。
5. **图标表 267 个 symbol / 预览页 265 个引用**，集合差只有 1 项（见下）。
6. `escapeHtml`/`escapeAttr`/`escapeAriaLabel`/`escapeHtmlTextAndAttr` 只有 `util/escape.ts` 一份；
   `sanitizeKernelHTML` 只有 `util/hostCapabilities.ts` 一份。
7. `app/src/types/dist/**` 与 `app/stage/build/**` 均被 `.gitignore` 排除（`git ls-files` 计数 0），生成物边界正确。
8. `kernel/apicontract` 的 AV 富文本白名单 `isAllowedValueTextRichBlockIAL`（`kernel/av/value.go:1318`）
   与表单元格富文本 `ParseTableCellRich` 是**有意分开的两套白名单**，
   `kernel/av/table_cell_rich_test.go:42` 明确断言「表格代码设置不得扩张数据库富文本白名单」→ 不是漏项。
9. `kernel/av/av.go:1432-1438` 的 `custom-sy-av-s-text` 与前端 4 处 `"custom-sy-av-s-text-"` 前缀
   宽度不同（内核无尾随连字符、前端有），但**构造出的键一致**（内核一律 `+ "-" + avID`）→ 无漂移。

### 附录 A：组织层问题（有权威依据与可验证不变量，但当前无用户可见后果）
1. **AGENTS.md 第 8 条（`custom-sy-*` 属性名常量必须定义在 `app/src/constants.ts`）有多处违背**：
   - `app/src/protyle/util/onGet.ts:441` 裸写 `"custom-sy-readonly"`，而 `Constants.CUSTOM_SY_READONLY`
     （`constants.ts:84`）存在且被 12 处引用
   - `app/src/protyle/util/headingNumberCore.ts:12` 自建 `CUSTOM_HEADING_NUMBER_ATTRIBUTE = "custom-sy-heading-number"`，
     与 `constants.ts:87` 的 `CUSTOM_SY_HEADING_NUMBER` 同值两份；另一处 `breadcrumb/index.ts` 用常量
   - `app/src/protyle/util/tableCellRichValue.ts:2` 自建 `TABLE_RICH_ATTRIBUTE`，与内核
     `kernel/treenode/table_cell_rich.go:17` 的 `TableCellRichTableAttribute` 同值两份
   - `app/src/protyle/util/table.ts:56,57,61,77` 裸写 `custom-sy-table-header-row` / `-column`（无任何常量）
   - `app/src/protyle/hint/extend.ts:651`、`hint/index.ts:712`、`util/clear.ts:53`、
     `wysiwyg/transaction.ts:1446` 四处裸写 `custom-sy-av-s-text-` 前缀，而内核有
     `av.NodeAttrViewStaticText`（`kernel/av/av.go:1436`）
2. **内核侧同类缺位（判据 A 的「同目录已有同义常量却未复用」档）**：
   - `kernel/model/block.go:1581` 与 `kernel/sql/block_ref_query.go:247` 裸写 `"custom-avs"`，
     而 `av.NodeAttrNameAvs`（`kernel/av/av.go:1432`）存在且 `kernel/model` 普遍引用 `av`
   - `kernel/av/value.go:1348`、`:1445` 裸写 `custom-sy-code-tab-spaces`，**内核侧无任何常量**
     （前端有 `Constants.CUSTOM_SY_CODE_TAB_SPACES`）
   - `custom-heading-mode`（5 处裸写）**没有常量**，而它的成对属性 `custom-heading-level`
     有 `embedHeadingLevelAttr`（`kernel/model/embed_heading.go:26`）→ 同族不对称
   - `custom-sy-readonly`（4 处）与 `custom-reminder-wechat`（2 处）同样无内核常量
   - 实测：以上**当前零漂移**（两侧字面量逐字相同），故是潜在分叉风险而非现行缺陷
3. **图标注册表两处一致性问题**（权威依据 = `AGENTS.md` 第 3 条）：
   - `app/appearance/icons/litheness/icon.js:139` 与 `:142` **两个 `<symbol id="iconTurnInto">`**，
     `path` 数据逐字相同 → 重复 `id` 是非法 DOM，第二份是死标记；
     `document.querySelectorAll('#iconTurnInto').length === 2`
   - `iconLayoutLeft` 定义在 `icon.js:375`、被 `app/src/asset/pdf/viewerTemplate.ts:184` 使用，
     但**不在 `app/appearance/icons/index.html`**（预览页 265 个引用里没有它）；
     同仓 `app/src/config/ocr.test.ts:44` 已把「预览页必须含 `#iconOCR`」写成断言，
     说明该页被当作需维护的产物

### 附录 B：分层观察项
- 内核包依赖存在**基础层反向依赖特性包**：
  `kernel/util/chatgpt.go:14 → kernel/chatgpt`、`kernel/util/ocr.go:41 → kernel/ocr`；
  `kernel/treenode/{av.go:20, table_cell_rich.go:13, table_cell_rich_export.go:6} → kernel/av`；
  `kernel/filesys/stat.go:25 → kernel/av`；`kernel/conf/search.go:24 → kernel/treenode`。
  无环（`av → util → chatgpt/ocr` 均单向），但「只想要 `treenode` 的字符串工具也会拉进 AV 引擎与 AI 客户端」。
- `app/src/business/` 目录只剩一个模块 `openRecentDocs.ts`（+ 测试），
  「business 层」未曾成形，是历史命名的残留。

### 本轮零残留
- 临时脚本全部在 `%TEMP%\audit-r43\`（仓库外）：`cmp_keymap.py`、`dup_exports.py`、`custom_attrs.py`、
  `kernel_attrs.py`、`orphans.py`、`dup4.txt`、`domtype.txt`；目标仓库未改任何文件（`git status` 干净）
- **未提 issue**（本轮无用户可见缺陷）

## 第四十三轮（续，2026-10-08）：分层与职责深挖（1 条确认 → #20219；2 条负面结论 + 2 条方法论纠正）

> 用户要求「提交 issue 并且继续审计 附录：分层与职责观察项」。上一段的 3 条组织层问题已提
> **#20216**（内置 `custom-sy-*` 属性名未集中：常量已存在却裸写、跨端各自定义、成对属性一个有一个没有）、
> **#20217**（`icon.js` 重复 `iconTurnInto` + 预览页缺 `iconLayoutLeft`）；本条是同一轮「继续」的部分。

### 确认（→ #20219，中低，架构/职责）
**导出渲染库的依赖边界完全没有约束。** `app/src/protyle/method.ts` 是 export 包入口
（`AGENTS.md` §5：*a rendering library (global `Protyle`, …) for code, math, and diagrams*），
只暴露 13 个静态渲染方法，但**剔除 `import type` 后的运行时闭包 = 929/1617 文件（57%）**：

| 分组 | 闭包内文件数 |
|---|---|
| `protyle/render/av` | 113 |
| `protyle/util` | 101 |
| `config/` | 108（`config/tabs` 33、`config/setting` 18、`config/tabs/ai` 17、`config/entryVisibility` 11） |
| `layout/` | 73（`layout/dock` 33、`layout/dock/agent` 20） |
| `protyle/wysiwyg` | 65 |
| `mobile/` | 59（`mobile/util` 43、`mobile/menu` 8） |
| `menus/` | 24 |

- 产物实测 `app/stage/build/export/protyle-method.js` **4.71 MB（4,936,220 字符）**，另有
  `12.js` 289 KB / `401.js` 160 KB / `429.js` 95 KB 与 `base.css` 224 KB；产物内含
  `JSAndroid` ×55、`window.siyuan` ×6841。
- 消费方确凿：`app/src/protyle/export/index.ts:532`、`:1161` 把
  `<script src=".../stage/build/export/protyle-method.js">` 写进导出页（`:235`/`:1143` 链接 `base.css`），
  内核 `kernel/model/export.go:1274`、`:1450` 把 `stage/build/export` 列入打包来源。
- 核心层直接跨入 UI 层的边共指向 **63 个 UI 模块**，主要是 `protyle/wysiwyg/transaction`、
  `plugin/Menu`、`protyle/ui/hideElements`、`menu`/`dock`/`config`/`mobile` 一族；
  典型例子 `protyle/util/selection.ts:21` 从 `layout/status`（状态栏 UI 模块）引入
  `countBlockWord`/`countSelectWord`，而 `selection.ts` 被 83 个文件引用。
- **不存在单条可切断的根因边**（见方法论第 3 条）→ 结论必须是「边界未被强制」，不是「某处误引用」。
- 附带：`webpack.export.js:62` 为 `MOBILE: true`（`webpack.desktop.js:68` 是 `false`），
  闭包内 113 个文件带 `/// #if MOBILE`/`!MOBILE`（76 / 88 个文件，479 行）。已核查唯一「全函数体被
  `!MOBILE` 包裹且被导出」的 `asset/renderAssets.ts:29 pdfResize`——它在导出包中变空函数，但唯一
  调用点 `layout/tabUtil.ts:238` 在应用侧，导出页不会调用 → **未确认用户可见后果**，只请维护者确认选择。

### 已核对为干净（勿重复投入）
1. **`mobile/**` 目录内 `/// #if` 出现 0 次**是有意约定：移动端目录整体进包，平台差异由
   **共享文件里的 `/// #if MOBILE`** 或**被调函数内部的运行时判断**承担。非 mobile 文件对
   `mobile/**` 的 118 处静态引用、145 个使用点逐类核对后**全部安全**（三种守卫形态见误报表新增条目）。
   **不要按「目录」判跨端违规。**
2. **前端 438 节点大环不是缺陷**：剔除 `import type` 后 1617 个文件构成**单个 438 节点 SCC**
   （小环 0 个），闭包内**顶层读取 `window.siyuan` 的语句 0 处** → 无初始化顺序危害。
3. `protyle/export/index.ts` 的 `/// #if !BROWSER` 三处（`:3`/`:88`/`:195`/`:1207`）与 `export/util.ts`
   的 `:1`/`:24` 是 Electron 专属分支，`BROWSER: true` 下正确剔除。

### 方法论（三条，都可复用）
1. **仪器自检不能省**：`Select-String -SimpleMatch -AllMatches` 对一个 4.7 MB 的**单行** JS 产物
   返回 **0 命中**（用同一个模式在 Python `re` 与 `[regex]::Matches` 下分别得到 55 / 6841）。
   「大文件 + 单行 + PowerShell 管道」会静默给出「干净」的假结果——**先拿一个必然命中的串校准**。
2. **测量模块图必须先剔除 `import type`**：不剔除会（a）闭包虚高 957 → 929，
   （b）凭空造出一个两节点环（`render/listMindmap/model.ts ↔ summary.ts`）。
   剔除方式：先按 `(?:^|\n)\s*(?:import|export)\s+type\b[^;]*?;` 删除整条语句，再匹配模块说明符。
3. **「单边切除」是验证根因归属的便宜手段**：把怀疑的边从图中删掉重算可达集。
   本轮据此**推翻了自己的假设**——删掉 `protyle/util/selection.ts → layout/status.ts` 后闭包
   仍为 929（减少 0），证明耦合弥散而非单点误引用（若不做这一步，报告会写成「根因是这一条边」）。

### 文档纠正
- **`stack-map.md` 的「`protyle/render/` 是纯渲染，不得读 DOM / 发请求」被实测推翻**：
  `app/src/protyle/render/**` 非测试文件有 **100 处**网络请求调用（`render/av/action.ts:923`、
  `render/blockRender.ts:83` 等）并大量读写 DOM。已改写该段，并把「结论不可复用」的理由写明，
  以防后续轮次按此产出上百条假阳性。

### 本轮零残留
- 临时脚本 `%TEMP%\audit-r43b\`：`dedupe.py`、`post.py`、`post3.py`、`body1-3.md`、`layers.py`、
  `cycles{,2}.py`、`ifdef.py`、`crossings.py`、`cut.py`、`counts.py`、`orphans`/`mobile_*`/`kfp2` 等；
  目标仓库未改任何文件
- 已提 issue：**#20216**（属性名常量）、**#20217**（图标注册表）、**#20219**（导出包边界）；
  三条 title/body 均逐字段回读一致（98/2879、100/1175、101/3212）

## 第四十三轮（B 线，2026-10-08）：桌面/移动孪生副本漂移（7 条确认：#20220–#20226）

> 与同日的「第四十三轮」/「第四十三轮（续）」是两个并行会话：那两条覆盖
> 分层/职责与导出包边界（#20216/#20217/#20219），本条覆盖**前端 `app/src` 的桌面 ↔ 移动孪生副本**。
> 编号分配遵循「先提交先占用」，本条编号 20220–20225 与对方的 20216/20217/20219 无交集。
>
> 起因：用户要求审「功能架构、代码组织、冗余逻辑、可能有更简洁直白的做法、可维护性、冗余封装」，
> 并指定用子代理分别覆盖「前端 `app/src`+`app/electron`」「内核未定向覆盖的包」「内核↔前端跨层契约」。

### 基线与范围

- 目标仓库 `d:\CodeProjects\siyuan`，起点 `715129808d`（起步时落后 `origin/dev` 1 个提交，按 `AGENTS.md` 规则 fast-forward；
  中途上游推进到 `41f78a8f2e`，已同步并**在新基线上重新核对全部行号**）
- 全程只读：未修改目标仓库任何文件，未跑 `pnpm lint/test/build`，未编译内核
- 机械扫描：重复字面量 `--root kernel --root app/src` 得 **323 条 / 1851 文件**（P1 263），头部全为已知噪声；
  未转义插值 `--root app/src` 得 **224 处 / 88 文件**（与历轮口径 242–244 一致）。**真缺陷增量 0**，
  两条发现全部来自定向语义核查

### 确认（7 条，均已提 issue，title/body 逐字段回读一致）

| # | 判据 | 结论 | 位置 |
|---|---|---|---|
| #20220 | B + D1 | 移动端不派发 `opened-notebook` / `closed-notebook` 插件事件 | 桌面 `layout/dock/Files.ts:1232`/`:1254`；移动端 `mobile/dock/MobileFiles.ts:708-710`/`:729-733` |
| #20221 | D1b + G | `file` 的 list/find/grep 把 `limit ≤ 0` 当默认 200，与「0 或负数表示不限」的帮助文本和 MCP 工具描述冲突；`kernel/mcp/tools/file.go:1132` 的 `max <= 0` 一支恒不可达 | `kernel/cli/cmd/file.go:291-293`/`:331-333`/`:456`/`:459`；`kernel/mcp/tools/file.go:295-301`/`:49`/`:1132` |
| #20222 | A + E2 | API 生成物随 Go 工具链变化：`networkEchoStandardSchema` 反射标准库类型，go1.27 新增 `ConnectionState.LocalCertificate` 与 `Certificate.RawSignatureAlgorithm` → `api:check` 必失败 | `kernel/apicontract/network_echo.go:44-60` → `schema.json` / `app/src/types/api/index.d.ts` |
| #20223 | B + D1 | `Table.GetField` 的 `for _, column := range` 丢弃下标 → `fieldIndex` 恒为 0，与 `Gallery`/`Kanban` 的 `for i, field` 漂移；**休眠**（`GroupCalc` 全仓无写入端） | `kernel/av/layout_table.go:178-185` |
| #20224 | D1 + B | 移动端 `setCurrent` 的**回溯分支**缺容器排除，而**首分支**有（同一函数内不一致）；`setCurrentById` 先清全部高亮再查找，查不到即 `return` → 无高亮 | `mobile/dock/MobileOutline.ts:440-446` vs `layout/dock/Outline.ts:590-597` |
| #20226 | B + D1 + D1j | 移动端搜索在 `method === 4`（语义搜索）下**不拦截替换**，桌面端拦截；内核只拒绝 `2 == method`，且 `switch method` 无 `case 4` → `default: // 关键字`，于是替换目标集合由**字面关键字**匹配决定，与屏幕上的语义结果集不同 → 移动端可写入桌面端拒绝写入的内容 | 移动端 `mobile/menu/search.ts:44-52`；桌面端 `search/util.ts:1419-1425`；内核 `kernel/model/search.go:633-641`/`:1658+`（成因提交 `c0fdb2a694` #17788 只补了桌面端） |
| #20225 | D3 + A | 两端大纲成员判据只排除 `bq`/`callout-content` 2 类，内核权威源排除 4 类（漏 `NodeTabItem`、`NodeBlockQueryEmbed`） | `layout/dock/Outline.ts:585-594`、`mobile/dock/MobileOutline.ts:434-441`；权威 `kernel/model/heading_number.go:141-156` |

**#20222 的取证（可复现）**：`cd kernel && go run ./apicontract/cmd/apigen -check -root ..`
→ `generated API contract is out of date`，退出码 1；`go version` = go1.27.0 而 `kernel/go.mod:3` = `go 1.26.5`（无 `toolchain` 指令）；
`git grep -c "LocalCertificate\|RawSignatureAlgorithm" -- app/src/types/api/index.d.ts` = 0。
CI 用 `go-version-file: kernel/go.mod`（恰好 1.26.5）→ 按提示重新生成会让 CI 反向失败。

**#20224 / #20225 的权威依据**：`collectOutlineHeadings`（`kernel/model/heading_number.go:141-156`）
**就是**大纲内容的唯一真源——它被 `kernel/model/outline.go:316` 的 `outline()` 调用。
（`kernel/model/outline.go:57` 的同名排除属 `moveOutlineHeading`，**不要**拿它当大纲成员判据。）

### 方法：孪生副本漂移扫描（新判据 → 模式 P47）

按大括号配对提取两个文件的**同名函数体**逐对算比值，再用**全局函数体哈希**补漏。
量化结果（`layout/dock/*` ↔ `mobile/dock/*`）：`Files` 24 个同名函数里 **17 个不同**、
`Outline` 16/21、`Tag` 3/4、`Bookmark` 3/3；全局哈希在 986 个非测试 TS 文件里得到 **15 组**同一函数体，
11 组是孪生对，**4 组是非孪生重复**（`showDeleteConfirm` ×2、`refreshDatabaseAttributePanels` ×2、
`handleCallback` ×2 + `handelCallback` ×1、两个渲染器构造函数 ×2）。

**分类纪律**：比值低不等于缺陷——30+ 处差异逐条回读后归为五类（有意的平台差异 / 该端无消费者 /
同端另有替代机制 / 外层已被守卫挡住 / 二者都对），只有能写出用户可见后果的 7 条升级为主报告。
判据细节与反例全部写入模式 **P47** 与误报表 4 条新条目。

**该方法的假阴性（必须声明）**：按函数名配对只能抓「复制品」。`menus/*` 与 `mobile/menu/*`
的同名函数为 **0**（`search`/`util`/`index` 三对全部 `common=0`）——两套**各自手写**的实现，
本方法报「无发现」**不能**视为该面干净（第 13 轮的 #19442 只能靠「同一配置字段的读写集」比对找到）。

### 已核对为干净 / 已排除（勿重复投入）

- 4 组非孪生重复逐组回读后**都不是缺陷**，全部写入误报表：`handleCallback` 三副本的 `/// #if !MOBILE`
  差异由实例化端决定（`mobile/util/openBacklinks.ts:43` 直接 `new BacklinkContent(...)` 且**不传 `tab`**，
  故回调在移动端未注册；桌面 `Graph`/`Outline` 在移动端不被实例化——`mobile/util/initFramework.ts` 的
  dock 分派无 `graph`）；`refreshDatabaseAttributePanels` 与 `action.ts`/`blockAttr.ts` 的刷新范围差异
  在查清**三条并存刷新路径**（`refreshForOperation` / `refreshAttributeView` WS 推送 / 调用点显式刷新）
  之前推不出陈旧
- 移动端「少一段桌面逻辑」的 4 处（`parentDocClick.cancel()`、`aria-label` 刷新、`draggable`、
  `setCurrentById("")`）逐条验消费者与同端替代机制后**全部排除**（依据见误报表）
- `onMount` 的 `liElement.remove()` 位置差异：被读的 `.counter` 是 `closeElement` 头部那一个（位于被删 `li` 之前）→ 无差异
- `MobileFiles.selectItem` 的布尔漂移是项目级设计（补了规范化 + 环检测的**提交**核实为
  `61ce34707b`（:sparkles: AI Agent，#17797）与 `4e88c1dd30`（#18034 加密笔记本）两次大范围加固顺手加的，
  **不是**针对某个用户复现输入的修复）→ 可达性未证实，只作低置信度候选
- 内核侧近重复函数体 13 组全为平台 build-tag 对或有意分层包装；`cli/cmd/*` 与 `mcp/tools/*` 各持一份的
  `copyPath`/`expandGlobBrace` 等归一化后逐字相同

### 观察项（有依据但无可观测后果）

1. **「容器块」在仓库里至少三份成员集合**：内核 `treenode/blocktree.go:507` `IsContainerType` 10 项（含
   `mindmap`/`mindmap_item`）、前端 `protyle/wysiwyg/getBlock.ts:238` `isContainerBlock` 7 个 CSS 类
   （缺 mindmap 两项）、内核 `collectOutlineHeadings` 4 类父容器。用途不同故不必合并，但**第 3 个判据被搬到
   前端另行枚举**正是 #20225 的根因
2. **同语义的三份 `getNextBlockSibling`**：`blockSelection.ts:14`、`removeRange.ts:6`、`transactionMove.ts:1`
   （后者名 `getNextBlockElement`）；`removeRange` 用 `hasAttribute("data-node-id")`，另两处用 `getAttribute(...)`
   → 对 `data-node-id=""` 判定相反（全仓无该形态节点，不可观测）
3. **`getViewIcon` 两份实现已漂移**：`av/fieldVisibility.ts:9-23` 有 `default: return "iconTable"` 且无 `case "table"`；
   `av/view.ts:581-593` 有 `case "table"` 却**无 `default`**（未知类型返回 `undefined`，模板会拼出 `#undefined`）
4. **`escapeHTML` 是局部别名**：`config/tabs/ai/aiProviderUi.ts:38` 的 `const escapeHTML = (value) => escapeHtmlTextAndAttr(value ?? "")`
   与 `Lute.EscapeHTMLStr` 概念上易混（该文件内用了 16+ 次）
5. `getBlockDragSelectBlock`（`wysiwyg/blockDragSelect.ts:28/33`）对 mindmap 不识别为容器 → 划选落到内部块而非整个
   mindmap 根。**后果未证实**，只请维护者确认选择
6. **CI 的测试信号强度（本轮顺带核实，判据 G4）**：`.github/workflows/cd.yml` 的 `on` 只有
   **版本 tag**（`*-alpha*`/`*-beta*`/`*-rc*`）与 `workflow_dispatch`，**不以 push/PR 触发**；
   `.github/workflows` 下无其它跑测试的工作流。且该文件内**每个测试步骤都带 `continue-on-error: true`**
   （`:132`/`:137`/`:182`/`:190`/`:212`/`:225` 等），唯一例外是 `:228`「Test OCR build and resource scripts」。
   内核选择面已修好（`:183` 是 `go test -tags "fts5 sqlcipher" ./... -count=1`，不再是白名单 → 第 18 轮
   #19472 的「只跑 4 个包」已不成立），但**「CI 绿」不等于「测试通过」**：失败只作为记录。
   **这是有意的政策**（`f4ba6cbe10`「Keep end-to-end tests non-blocking」、`e149329df6`
   「Keep prerelease packaging running after test failures」），**不要当作缺陷上报**；
   它的实践含义是——**用 CI 结论验证修复时必须读该步骤本身的结果，不能读 job 状态**。

### 本轮零残留

- 临时脚本全在 `%TEMP%\audit-r43x5\`（仓库外）：`dedup_outline.py`、`outline_probe.py`、`make.py`、`post.py`、
  `classify.py`、`clones.py`、`menu_twins.py`、`p47.md`、`append_p47.py`；
  另 `%TEMP%\audit-r43x2\`（第二轮）、`%TEMP%\audit-r43x\`（第一轮）已删除
- 目标仓库 `git status --porcelain` 为空；**并行会话的 `%TEMP%\audit-r43`、`%TEMP%\audit-r43b`、
  `%TEMP%\audit-r43x4-20219-verify` 未被触碰**
- 已提 issue：**#20220–#20226**（移动端插件事件、`limit ≤ 0` 契约、`api:check` 随工具链失败、`Table.GetField` 下标恒 0、移动端大纲容器排除、大纲成员判据漏页签、移动端语义搜索可替换）；
  七条 title/body 均逐字段回读一致（75/986、107/1147、91/1074、94/1069、100/1482、89/1546、125/2455）
- 本地内核 3.8.7-alpha.7 在跑，只用只读接口（`/api/system/version`、`/api/outline/getDocOutline`）

### 方法论增量

1. **「同族差异」必须逐条分类，不能按「有差异 = 缺陷」上报**：本轮 30+ 处差异只有 7 处是缺陷，
   其余全部合法。**分类纪律本身就是产出**——它把「17 个函数不同」从噪声变成可复核的清单
2. **同一函数内的两处不一致 > 跨文件比较**：`setCurrent` 的首分支与回溯分支相邻，比对成本最低，
   而「对齐某侧」的提交（`59dd2a0bc3`）**恰好只改了首分支** → **`git show <sha> -- <file>` 要数它覆盖了几个镜像分支**
3. **「休眠缺陷」的可达性要查写入端，不是查读取端**：`GroupCalc` 在读取侧（契约、渲染、计算、消费者）一应俱全，
   只有写入端为空——`grep GroupCalc -- kernel/model` 只剩一个**读**点，`SetAttributeViewGroup` 经逐行阅读确认不写它
4. **不要用权威源之外的同名函数当判据来源**：`kernel/model/outline.go:57` 与 `heading_number.go:147`
   有形状相同的排除，但前者属 `moveOutlineHeading`（文档根第一层标题）——引用错一处会让整条立论失去依据
5. **终端软换行会伪造「字中间有空格」的现象**：`print(repr(slice))` 的长输出被控制台折行后，
   看起来像 CJK 二字之间插了空格。判「文本被篡改」要直接对原字符串做正则或 `find`，不要读 `repr` 的屏幕输出

## 第四十三轮（验证，2026-10-08）：#20219 修复复核（1 条符合预期 + 1 条新提 #20227）

> 用户要求「只读检查 #20219 的修复是否符合预期」。基线：工作树正在修复提交 `41f78a8f2e` 上，
> `git rev-list --count HEAD..origin/dev` = 0；`cd.yml` 只按版本 tag 与 dispatch 触发 → **该提交没有 CI 记录**。

### 复核结论（符合预期，判据 G1 已由新增测试补上）
- 用与新增测试同一算法复现：父提交 `41f78a8f2e^` 闭包 **887** → 修复后 **52**；在 issue 自己的基线
  （`git log --until=<issue 创建时间> -1` → `2b02f86fde`）测得 **886**（issue 报 929，约 5% 测量口径差异，结论不受影响）
- `app/tests/exportDependencyBoundary.test.js` **是有效回归测试**：把它的守卫原样施加到父提交得到 FAIL，
  且首两条命中正是守卫里的 `protyle/util/selection.ts`、`protyle/render/tableCellRichEditor.ts`
  → 那两个显式条目是必要绊线，不是死代码。它也在 CI 执行集内（`cd.yml` frontend-tests → `pnpm test`）
- **不要复报「守卫前缀太窄」**：对 `search/ history/ dialog/ card/ template/ sync/ ai/ emoji/ boot/ util/ plugin/`
  下 21 个模块逐个测闭包（887~948），绝大多数经间接传递命中受守卫前缀；加一条被使用的 `editor/openLink`
  → 闭包 52→888、守卫 FAIL。**未找到能绕过它的入口**
- 搬移合规：`selectionOffsets.ts` 是纯搬移、无第二份实现、`selection.ts` 无转发再导出；`tsc`（typecheck + api）
  与 `npx eslint .` 均 exit 0；本次改动的 17 个测试文件 23 用例全过
- **未能验证**：导出产物早于修复 → 只报「模块图层面的边界已成立」，**不报体积下降**

### 确认（→ #20227，判据 G3）
`app/tests/settingsWindow.test.js:192` 的模块白名单未登记 `app/src/config/setting/nativeWindow.ts:15`
新增的 `../../protyle/toolbar/catalogSnapshot`（引入提交 `f46d1026df`，#20211，2026-10-08 12:49；
该测试文件最后改动是同 00:45 的 `63b1b4001c`）→ 单独运行 exit 1。
同类形态 #19474（`mobileBacklinks.test.js` 缺 `editor/assetOpen`）与 #19501（替身缺 `util/zIndex`）已修，
**但该文件当时不在两者的清单内 → 是新实例，需独立立论**（这也是 G3 会反复复发的原因：修的是实例，不是机制）。
**标题被当场纠正**：首版照搬 #19501 写成「Frontend CI is red because …」，复核 `cd.yml:223-226` 发现
`pnpm test` 步骤带 `continue-on-error: true` 且工作流只按 tag 触发 → **该步骤失败不会让 job/工作流变红**；
改为「Frontend test failure: …」，并按 `AGENTS.md` 把旧标题留作正文首段。

### 方法论增量
1. **「加边实验」必须让 import 被使用**：第一次加边写成 `import {openLink}` 却不使用，闭包不变，
   差点报成「守卫拦住了」——实际是 esbuild 的 DCE 剔除了未使用的 import。
   **设计实验时要考虑工具链自身的死代码消除**
2. **回读校验不能用 PowerShell 管道**：`gh api --jq .body | Out-File -Encoding utf8` 得到的是
   UTF-8 字节被按 GBK 解码的乱码（`鍓嶇`）；**显式 `-Encoding utf8` 修不回已被管道解码破坏的文本**。
   改为 Node `execFileSync("gh", [...])` 取 stdout 按 utf8 解码后，比对立即一致
3. **报缺陷要落到「哪个步骤/哪个对象」，不要用 job 级词**：在 `continue-on-error` 与 tag-only 触发下，
   「CI 变红」是错的。这条与 B 线第 6 项（CI 测试步骤全部非阻塞是有意政策）是同一事实的两面

### 同日收尾（新提 #20228、#20229；#20227 正文补正；全量前端测试汇总）

**1. #20228：G3 的新形态——「按文件名清单装配模块」的测试在模块被拆分后必然失绑**

`app/src/protyle/render/listMindmap/model.test.ts` 报 `ReferenceError: focusByRange is not defined`。
该测试用「文件名清单 + 提取各文件 `export const` 名字」在 `new Function` 里搭假作用域，
**每个文件各自生成一个独立 IIFE**；`#20219` 把 `focusByRange` 搬进 `selectionOffsets.ts` 后，
`selection.ts` 内部仍引用它 9 处且已不在同一作用域。

- **因果取证（不依赖 electron / DOM，比跑用例快且不受既有红干扰）**：用与该测试相同的装配逻辑，
  父提交 `41f78a8f2e^` 得到 BOUND、`41f78a8f2e` 得到 FREE。
- **修法不可只把新文件追加进清单**——那会生成第二个 IIFE，绑定不到原模块内部的引用。
  同一提交已对同类清单做了正确处理：`app/tests/verticalNavigation.test.js:18-22` 把两份语句**合并进同一模块体**。
- **诚实定性**：该文件在父树本来就失败（另一条断言 `native pointer capture saves a drag exactly once`，`0 !== 1`）
  → 不是新回归，而是失败点被提前到装配阶段，该文件其余断言全部失效。

**2. #20229：`webpack.export.js:62` 的 `MOBILE: true` 是依赖闸门，不是平台声明**

- `2065aeded9`（2022-07-01，为修 #5326「导出 PDF 图表无法渲染」）**只翻了这一行**；
  在该提交的源码树上实测：`MOBILE: false` 闭包 **165**、`true` 闭包 **19**，唯一差异是
  `layout/status.ts` 顶部 `#if !MOBILE` 里的 `import {getAllDocks} from "./getAll"`（`getAll` 再引出
  `layout/index`、`editor`、`dock/*`、`asset`、`search`）。
- 该职责已由 `#20219` 替代（拆出 `selectionOffsets.ts` + 边界测试）：今天闭包 **52 与 52**、
  **闭包内 `!MOBILE` 块为 0**、唯一随标志变化的文件是 `util/functions.ts` 的 `getFrontend()`（闭包内 0 个调用）
  → 翻转是严格空操作，已据此建议改 `false`，正文同时给出「若保留则须注释 + 断言 0 个 `!MOBILE` 块」的替代。
- **纠正自己上一轮的一个未验证断言**：预览窗口的 UA 被 `app/electron/main.js` 显式加了 `SiYuan/` 前缀，
  所以 `getFrontend()` 在那里返回 `"mobile"`（不是我先写的 `"browser-mobile"`）。

**3. #20227 正文补正**：根因同一但影响面是 **3 个文件 14 个用例**（`tests/nativeSettingsOwner.test.js` 12、
`tests/settingsWindow.test.js` 1、`src/config/entryVisibility/mobileUi.test.ts` 1），首版只写了 1 个文件。

**4. 全量前端测试汇总**（与 `pnpm test` 同参数，不经 pnpm 以免改写 lockfile）：
`tests 4494 / suites 515 / pass 4459 / fail 27 / skipped 8`，27 条按根因三类：

| 根因 | 处数 | 文件 |
|---|---|---|
| `catalogSnapshot` 白名单未收录（= #20227） | 14 | `nativeSettingsOwner`(12)、`settingsWindow`(1)、`mobileUi.test.ts`(1) |
| `focusByRange` 搬运后未合并（= #20228） | 1 | `listMindmap/model.test.ts`(1) |
| 与本次复核无关 | 12 | `readonlyKeydown`(6)、`contextMenuHotkey`(1) 出自 `4b10638cab`（#20202）；`avRichTextEditor`(1)、`newRefDocAtPath`(1) 出自 `128ec67623`（#20201）；另 4 处未追引入提交 |

**5. 方法论（两条工具坑）**

- **PowerShell 的 `*>` / `>` 重定向默认写 UTF-16LE**：汇总行与失败清单用 `Select-String` 读不到
  （不是正则写错）。正确做法：`[Text.Encoding]::Unicode.GetString([IO.File]::ReadAllBytes($p))` 解码后再按行匹配。
- **判「某测试的失败是否由某提交引入」不能只跑目标树**：该文件在父树也是红的，只是失败在另一条断言上；
  必须先取父树（`git archive <rev>^ app/src` + 复用 `app/stage/protyle` 与 `node_modules` 联接）做对照，
  并优先用不依赖 electron / DOM 的静态装配复现。

### 本轮零残留
- 临时脚本全在 `%TEMP%\audit-r43x4-20219-verify\`（仓库外）：`closure.js`、`sweep.js`、`unresolved.js`、
  `verify-issue.js`、`*.diff.txt`、`i19474.md`、`i19501.md`、导出的 `before/`/`issuebase/`/`after-src/` 源码树
- 目标仓库未改任何文件；两个 payload JSON（建后与改后各一个）已确认删除
- 已提 issue：**#20227**（含正文补正）、**#20228**、**#20229**；三处 title/body 逐字段回读一致（106/1442、122/1499、125/2171）

## 第四十四轮（2026-10-08）：冗余逻辑 / 冗余封装 / 多层封装定向审计（全仓库；主报告 1 条，与 #18699 同源）

- 基线：目标仓库起步落后 `origin/dev` 4 个提交，按 `AGENTS.md` 规则 fast-forward 到 **`bbef0e1f8b`**（`HEAD == origin/dev`），
  分支 `dev`，工作树干净；**只读审计**（用户选定「A 同语义不同名 + B 薄封装/透传链 + C 死函数」，范围＝全仓库）
- 机械扫描增量 **0**：重复字面量 `--min-files 4` = **323 条**（与第四十三轮同值）、未转义插值 **224/88 文件**、
  `scan_dom_type_literals --kind node` 零拼写漂移 → 三支脚本口径与第四十三轮完全一致，无新增噪声
- 该主题**同日已有三个并行会话**覆盖（第四十三轮主线/续/B 线：#20216–#20227）。本轮刻意只做它们**未覆盖**的三条：
  ① 同语义**不同名**的重复实现（它们只比了同名导出）② 薄封装/透传链丢参数 ③ 死函数（它们只查孤儿**文件**）

### 主报告（1 条）：Docker 镜像默认启动失败——内核路径在同一命令行里出现两次（→ 追加到 **#18699**）

- 位置：`kernel/entrypoint.sh:52`、`Dockerfile:83`、`kernel/main.go:27-31`
- 事实链：
  1. `main.go` 里的「无子命令时自动补 `serve`」兼容层在 **`bcbd18658a`**（2026-06-16 / v3.7.0，
     *Kernel serving now requires an explicit `serve` subcommand*，#17866）被**整段删除**，只剩 `cmd.Execute()`；
     同一次改动让 `cmd.HasSubCommand` 变成死函数（全仓 1 处引用＝其自身声明）
  2. `entrypoint.sh:52` 把可执行文件写死在 exec 里，而 `${ARGS}` 由前置循环收集**除 `--workspace=` 外的全部参数**
  3. **同一提交**把镜像默认值改成 `Dockerfile:83` 的 `CMD ["/opt/siyuan/kernel", "serve"]`
  4. 于是默认（不带 `command:` 覆盖）实际执行：
     `/opt/siyuan/kernel --workspace=/siyuan/workspace /opt/siyuan/kernel serve` —— **内核路径出现两次**
  5. cobra v1.10.2：`Find`（`command.go`）只在 `commandFound.Args == nil` 时调 `args.go:28 legacyArgs`，
     后者对「root ＋ 有子命令 ＋ `len(args) > 0`」直接返回 `unknown command "/opt/siyuan/kernel" for "kernel"`；
     `rootCmd` 既无 `Args` 也无 `Run/RunE`（`cli/cmd/root.go` 全文 308 行）
- 触发条件：**任何不带 `serve` 的启动方式**（镜像默认 CMD；docker compose 只写 `--workspace=`/`--accessAuthCode=`）
- 业务表现：`docker run b3log/siyuan`（无额外参数）→ 容器 `Restarting`，日志 `Error: unknown command "/opt/siyuan/kernel" for "kernel"`
- 预期表现：镜像默认即启动伺服——权威依据是**同一提交写进 Dockerfile 的注释**「默认启动伺服」
- 可验证不变量：`entrypoint.sh` 拼出的 argv 中非 flag 参数个数必须 ≤ 1；当前为 **2**
- **既往记录：#18699**（2026-08-13 提交，**4 分钟后被同一账号以「v3.7.3 同样报错，非 3.8.0 引入」自行关闭**）。
  **关闭理由只否定「回归」这一措辞，未否定缺陷本身**。本轮增量：给出 cobra 源码级机制证明、
  指出「`entrypoint.sh` 与 CMD 重复提供同一条命令的一半」才是成因、并核实 HEAD（`Dockerfile` 最后改动 2026-10-01）仍未修复
- 修法（择一）：① `CMD ["serve"]`（与 Dockerfile 注释自陈的语义一致）；
  ② `entrypoint.sh` 改为原样转发 `"$@"`（或跳过 CMD 首元）。**不要**把 `serve` 硬编码进 entrypoint 的固定位置
- 新判据 → 模式 **P48**；误报表 +3 条

### 附录 A：死代码与「伪活」代码量化（判据 A/C）

（Go 口径＝顶层 `func`/`var`/`const`；TS 口径＝export 的 function/class/enum/const ＋ `export {}` 列表；**剥离注释并区分 test/non-test**）

| 面 | 零引用（含测试） | 仅测试引用（「伪活」） |
|---|---|---|
| 内核 Go（排除 vendored `heif/internal/**` 7 条） | **83** | **69** |
| 前端 `app/src` | **10** | **7**（其中 1 条为假阳性，见误报表） |

- 零引用 Go 的分布：`model` 28、`sql` 12、`plugin` 9、`util` 6、`av` 6、`api` 5、`plugin/streams` 5、
  `bazaar`/`cache`/`treenode`/`filesys` 各 2，其余各 1
- **最大一族是「已被 `<X>InBox` / `<X>WithApp` 取代的单签名薄壳」**：`cache.GetTreeData`/`SetTreeData`、
  `model.GetAssetImgSize`、`model.GetBlockRefs`、`model.UploadAssets2Cloud`/`…ByAssetsPaths`、
  `model.resolveEmbedContent`、`model.renderCleanBlockDOMByNodes`、`sql.av_gallery.RenderAttributeViewGallery`、
  `sql.av_kanban.RenderAttributeViewKanban`、`model.resolveAttributeViewNewItemTemplate`、
  `search.fullTextSearchBy*`（5 个）… → 属「同一规则两份实现」的残留，**无用户可见后果**
- **加密域单独核实为「被取代」而非「断裂」**：`av.writeAttributeViewData`（加密 AV 写出）零引用，
  但活路径 `av.saveAttributeView`（`av/av.go:968-1101`）自带加密 ＋ 缓存比对 ＋ `WriteFileByMmap`，是严格超集
  → 封装残留，**不是**加密笔记本读写断裂（避免了一次高危误报）
- **「伪活」样例（判据 B/G1）**：`kernel/agent` 包 12 个函数只被自身测试调用——
  `agent.go:1745 needsCapabilityConfirm`、`:2242 buildInitialMessages`、`:2367 checkpointMessagesToOpenAI`、
  `:2606 agentMessagesToEntries`、`:2657 createStreamWithRetry`、`compaction.go:170/283/308`、
  `attachments.go:356`、`tools.go:39/85`、`session.go:315 SaveSession`；
  各自都有**改名后的活孪生**（`capabilityConfirmRequirement` / `checkpointMessagesToOpenAIWithSummary` /
  `createProtocolStreamWithRetry` / `validateCapabilityCall` / `executeCapability` / `SaveSessionState`）
  → 是运行时从「AgentChat 内联」迁到「runtime ＋ entries」时留下的一整层旧实现
- **假覆盖不成立（必须写明，否则误报）**：12 个里 10 个是**转发壳**（3–5 行 `return <活函数>(…)`），
  且活函数**另有直接测试**（`compaction_test.go:238`、`instructions_test.go:113/117`、`capability_test.go:233`…）
  → 定性只能是「封装残留 ＋ 维护成本」。只有 `buildInitialMessages`（10 行自建组装）、
  `agentMessagesToEntries`（45 行）是真自实现

### 附录 B：同语义不同名 / 近重复函数体（**负面结果为主**）

- 两支扫描器：**字面量归一化后**的函数体近重复（字符串→`"L"`、数字→`N`、保留标识符，
  按「前 4 token ＋ token 数//8」分桶做 `difflib` 比值），**只报字面量不同的对**（结构同、常量异才是漂移高发形态）
- 内核 6449 个 ≥30 token 函数体 → **119 对 ≥0.93**，逐条回读**全部落在有意族**：
  MCP 工具 handler 样板（11 个两两相似）、`sql/queue.go` 的 `*TreeQueue` 包装族、
  `treenode.GetBlockTreesBy*` 查询族、`av.New*View` 构造族、`model/embedding.go` 配置取值族、
  `util/websocket.go` 广播变体、`plugin/crypto` 的 SPKI/PKCS8 对
- 前端 6299 个 ≥40 token 函数体 → **4 组**（`getGalleryHTML`↔`getKanbanHTML`、
  `mountAccessibilitySetting`↔`mountLinuxInputMethodSetting`、`secretsVariablesUi.ts` 两对，
  以及唯一的跨模块同名语义对 **`protyle/render/av/columnWidth.ts:81 getAVDistributedColumnWidth` ↔
  `protyle/util/tableColumnWidth.ts:3 getDistributedTableColumnWidth`**）
  → 最后一组**下限常量本就有意不同**（25 vs `TABLE_DEFAULT_COLUMN_WIDTH`）且各有断言固定
  （`columnWidth.test.ts:152`、`tableColumnWidth.test.ts:11`）→ 判为非缺陷
- **跨模块路径校验两份实现（判据 B，观察项）**：`cli/cmd/template.go:200 resolveTemplateAbs` 与
  `mcp/tools/template.go:89 resolveTemplatePath` **除报错文案外逐字相同**，且都用
  `strings.HasPrefix(rel, "..")`（会把合法文件名 `..foo` 误判为越界）。两处都是活的 → 修一次必须改两处；
  第十五轮已登记为未取证候选，本轮补上「MCP 侧也有一份」
- **薄封装丢参数检测器口径失败（本轮不产出）**：对内核 **902 个单语句包装**做「形参出现过、实参从未出现」判定，
  得 28 条候选，逐条回读**全部是「方法接收者」或 handler 的 `c`/`req` 被误判**（脚本把 receiver 当形参），**零真缺陷**

### 附录 C：组织层观察项

1. `util.Boot()`（`kernel/util/working.go:123`，标准库 flag 入口）**只有测试调用**（`working_home_test.go:158`），
   而 `rootCmd` 不可运行（无 `Run/RunE`）→ 该入口自 #17866 起在发布物里不可达。
   `entrypoint.sh` 与 README 都走 `serve`，**无用户可见后果**；但 `working_home_test.go` 验证的是产品不可达路径，
   且 `cli/cmd/serve.go:64` 的注释「与原 `Boot()` 行为一致」已过期
2. `cmd.HasSubCommand`（`cli/cmd/root.go:301`）随 `bcbd18658a` 删除的 `main.go` 兼容层一起成为死函数
3. `model.LoadAgentTodos`（`model/todo.go:66`）零生产引用，而 `SaveAgentTodos` 被 `mcp/tools/todo.go:95` 调用
   → **`todos.json` 只写不读**。前端待办列表来自工具调用结果的**流式文本**（`AgentMessageRenderer.ts:33`），
   崩溃恢复由 runtime 文件承担（`loadRuntimeState`/`mergeRuntimeIntoSessionLocked`）→ 判为冗余落盘
4. `kernel/agent/session.go:315 SaveSession` 是 `SaveSessionState` 的 4 行转发壳
5. `kernel/heif/internal/h265heic` 有 7 个零引用函数（`DecodeExif`/`RawXMP`/`rotate`…）→ **上游库公开面**，不按自研标准要求

### 方法论增量（三条，都可复用）

1. **死代码检测有三个方向都要防的假信号**（本轮仪器经历完整纠错）：
   ① **注释**会保住一个死函数（初版把 `model/search.go:627 FindReplace` 判为活，剥离注释后才看出**只有测试调用**）；
   ② **测试文件**会保住一个死函数（必须 test / non-test 分开计数，否则「只被自身测试保活」整类不可见）；
   ③ **命名空间导出**（`app/src/plugin/API.ts:14 import * as platformUtils` 再把模块整体展开进插件 API）会让
   模块内每个导出都成为「活」——按名字计数看不见，据此外推曾把 `plugin/platformUtils.ts:24 getStorageVal`
   误判为死代码，回读后推翻。**排除清单五条：命名空间导出 / 字符串与注册表派发 / `.js` 导入方 /
   vendored 目录 / 只被自身测试引用（那是另一类）。**
2. **「只被自身测试引用」不足以定性为缺陷**：先判**转发壳**还是**自实现**；转发壳的测试会顺带覆盖活函数
   （agent 包 12 个里 10 个如此）。判据：函数体是否只有一条 `return <活函数>(…)`。
3. **产物新鲜度陷阱第三次复现**（对应验证模式第 ⑦ 条）：`kernel/kernel.exe` 时间戳 **2026-04-04**，
   而 `kernel/main.go` 最后改动 **2026-08-08**、`#17866` 在 **2026-06-16** → 用它验「重复参数是否被 cobra 拒绝」
   得到的是**修复前**的结论（旧二进制仍带自动补 `serve` 的兼容层，实测「接受并启动」）。
   **改走第三方源码取证**：直接读 `$GOMODCACHE/github.com/spf13/cobra@v1.10.2/{args.go,command.go}`，
   `args.go:28 legacyArgs` ＋ `command.go` 的 `Find` 即完整判据，无需运行任何二进制。
   **教训：回答「某命令行会不会被受理」时，读 CLI 的解析源码比跑一个可能过期的二进制可靠；
   跑之前必须先比「二进制 mtime vs 相关源码最后改动」。**

### 本轮零残留（含一次须如实报告的副作用）

- 临时脚本全在 `%TEMP%\audit-r44-coloc\`（仓库外）：`dead_go.py`、`dead_ts.py`、`dead2.py`、`ctx_go.py`、
  `wrap_go.py`、`near_dup.py`、`dedup.py`、`i18699b.py`、`i19066.py` 及各中间产物；目标仓库**零残留**
- **副作用**：为验证参数解析，我用仓库里已有的 `kernel/kernel.exe` 跑过一次
  `--workspace=<不存在目录> <该二进制> serve`。该二进制是 2026-04-04 的**旧版**（含已删除的兼容层），
  因此它**回退到默认工作区 `C:\Users\Admin\SiYuan` 并进入启动流程**，随后因 `appearance/langs` 不存在在
  `model.InitConf` 阶段 `LogFatalf`（退出码 26）——**未绑定端口、未写数据**；实测副作用仅两条：
  用户工作区更新了 `.lock` 与 `temp/siyuan.log`（18:34:50）。
  **教训：验证「启动参数」不得使用仓库里的历史二进制——它可能带当前源码已删除的兼容层。**

### 第四十四轮（续，2026-10-08）：用户纠正——「可维护性」不得被「写不出业务表现」一票否决

**用户的原话与理由**：「为什么有一堆建议『不提』的？只要是本项目里的代码都要考虑吧，除非是上游依赖我们管不着；
『写不出业务表现的发现不得进主报告』调整一下，对整理代码、提高代码可维护性有帮助的也要报告。」

**这是判据层的误用，不是执行失误**：SKILL.md 原「核心原则 5」把「业务表现」设成唯一门槛，
于是**冗余逻辑 / 冗余封装 / 多层透传 / 重复实现 / 死代码**这一整类（本 skill 的判据 A / B / D1 / C 的主要产出）
在报告里天然只能进附录。用户的诉求与 `description` 的既有范围（「审计…hidden design, contract, and correctness
problems」）不冲突——**冗余正是设计层问题**。

**改动（committed）**：
1. 核心原则 5 改为**两条轨迹**：轨迹 A（行为）保留「业务表现/预期表现/可验证」；轨迹 B（可维护性）改为
   「**维护成本/权威依据/可验证**」，并写明**不得因写不出业务表现而降级**。
2. 新增「**可维护性条目模板（轨迹 B）**」，编号 `M1.`、`M2.` 与行为条目区分。
3. 「适用场景」补**范围边界**：本项目自有代码全在范围内；成建制引入的上游/移植子树不在，
   判定法三条任取一（移植许可声明 / vendored 或依赖覆盖 / 只被原生宿主调用）。
4. 输出格式的「强制项」段改为按轨迹取字段；轨迹 B **必须在「挑战门」字段写明已排除的动态使用面**。

**本轮为此新增的假信号清单（六类动态使用面，实测都给出过假阳性）**：

| 类 | 实例 | 为何按名字搜不到 |
|---|---|---|
| 接口方法实现 | `plugin/websocket.go:48-72` 的 `WsEventHandler.OnOpen/OnClose/OnPing/OnPong/OnMessage` | 类型注释即写 `implements gws.Event`，实例在 `api_client.go:350`/`plugin.go:1056`/`rpc.go:315` 交给 gws → 接口分发 |
| goja / 反射暴露的方法 | `plugin/api_logger.go:36 Warn` | `sandbox.go:103 console.RequireWithPrinter(&Printer{...})` → JS 调 `console.warn(...)` |
| gomobile / 原生导出 | `kernel/mobile/kernel.go:131 VerifyAppStoreTransaction` 等 | 全仓无人 `import ".../kernel/mobile"`，调用者在 Java/Swift/Kotlin |
| 命名空间导出（TS） | `plugin/platformUtils.ts:24 getStorageVal` | `plugin/API.ts:14 import * as platformUtils` 后整体展开给插件 |
| 注册表与字符串派发 | 各处 `register("name")` / `data-type` 表 | 名字只以字符串出现 |
| vendored 子树 | `kernel/heif/internal/**`、`app/src/asset/pdf/**`（PDF.js） | 上游公开面，本就不在范围 |

**本轮在这些排除之后的实质产出（全部按轨迹 B 口径）**：

- **主报告 1 条**（已提 **#20230**）：Docker 镜像默认启动失败——`entrypoint.sh:52` 与 `Dockerfile:83`
  各提供了同一段命令行的一半，拼出 `/opt/siyuan/kernel … /opt/siyuan/kernel serve`；
  cobra `args.go:28 legacyArgs` 对「根命令 ＋ 有子命令 ＋ 非空位置参数」报 `unknown command`。
  与 #18699 同源（该 issue 4 分钟后被报告者自己以「非 3.8.0 回归」关闭，**关闭理由不否定缺陷**）
- **死路由（轨迹 B，值得单独提）**：`plugin/rpc.go:292 HandleRpcWebSocket` 零引用，而其注释写着
  `GET /ws/plugin/rpc/:name`；`kernel/api/router.go:740-741` 注册的是 `pluginJsonRpcWebSocket(ByName)`
  （另一份实现）→ **注释承诺的 URL 与实际处理函数不是同一个函数**
- **被内联取代的方法**：`plugin/rpc.go:222 (*JsonRpcProcessingResponse).JsonRpcResponse` 零引用，
  等价逻辑已在 `rpc.go:487 filterRpcResponses` 内联展开；同型：`plugin/streams/transform.go:270
  setUpTransformStreamDefaultController`（等价逻辑在 `transform_prototype.go:102/111` 内联）
- **文档承诺但未接线**：`plugin/streams` 的 `NewWritableStream`（`writable.go:203`）与
  `NewTransformStream`（`transform.go:320`），doc 注释写「供 kernel/plugin 的 Go 桥接代码使用」，
  实测**无任何调用方**（JS 侧走 `module.go:66/70` 的 `new*StreamConstructor()`）→ 属「未接线的公开入口」
- **同一默认值两份表达（判据 A）**：`mobile/util/mobileBottomBarConfig.ts:59 DEFAULT_MOBILE_BOTTOM_BAR_CONFIG`
  零引用，而活的默认值在 `:110-111` 用 `[...DEFAULT_MOBILE_BOTTOM_BAR_ACTIONS]` 另建一份；
  同型有 `mobile/util/mobileSidePanelConfig.ts:63 DEFAULT_MOBILE_SIDE_PANEL_CONFIG`
- **迁移常量第三份副本**：`LEGACY_DEFAULT_MOBILE_BOTTOM_BAR_ACTIONS`（`mobileBottomBarConfig.ts:57`）
  与 `protyle/util/compatibility.ts:791` 的 `actions: ["documents","search","newDoc","tabs"]` 同值两份
  → 改一个默认动作要同改两处（**这正是轨迹 B 要的「维护成本」表述**）
- **中间状态**：`plugin/rpc.go:234 HandleRpcHttp` 零生产引用（路由走 `api` 包的 contractHandler 包装），
  仅测试引用；`util/misc.go:50 IsNullValue`、`util/sort.go:108 GBK2UTF8`、`util/net.go:413 GetRequestStringParam`、
  `conf/search.go:127 boolPtr`（带 `//go:fix inline` 指令）、`model/session.go:453/464` 的
  `CheckEditRole`/`CheckReadRole`（gin 中间件，而 `CheckAdminRole` 有 584 处使用）零引用

**方法论**：**判断「某项算不算缺陷」时，不能只看它有没有用户可见症状——要先问「它属于哪一类问题」**。
存在一类问题（可维护性）其后果天然就是「修改成本 / 误改风险」，用另一类问题的门槛去筛它，
会系统性地漏报整类。这与第四十四轮前半段「产物新鲜度」的教训是同一形状：
**筛子选错比筛子不严更危险**（前者永远筛不到东西，而报告看起来仍然正常）。

## 如何更新本文

每轮审计后追加：

1. 本轮实际命中（判据编号、发现、置信度）
2. 新增的误报模式
3. 阈值调整（若脚本参数变化）
4. 方法论教训

数据用于校准下一轮的判据与阈值，避免重复劳动。


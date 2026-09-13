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

### 宿主 MIME 注册表决定内联白名单（09-14 从「误报」改判为**真缺陷**，已提 #19475）

`kernel/server/serve.go:917` 的 `isAssetInlineUnsafe` 用 `mime.TypeByExtension` 取媒体类型再按白名单决定是否强制附件下载。
本机 `HKLM\SOFTWARE\Classes\.jpg` 的 `Content Type` 为 `application/jpg`（同机 `.jpeg` 仍为 `image/jpeg`），
于是 `TestSecureAssetContentHeadersAllowsInlineSafeAssets` 在 Windows 上必失败。
**机制**：Windows 上 Go 的 `initMimeWindows`（`$GOROOT/src/mime/type_windows.go`）遍历 `HKEY_CLASSES_ROOT`
并用 `setExtensionType` **覆盖内置表**，仅对 `.js` 硬编码豁免 `text/plain`（Go issue #32350）。
逐扩展名比对 19 项，只有 `.jpg` 与内置表不同；`.js` 注册表值为 `text/plain`（恰在白名单内）—— 说明注册表确实能给出「内联安全」的类型。
**影响面已实测夹逼**：Chromium **忽略子资源上的 `Content-Disposition` 与错误 Content-Type**，
四个对照端点（正常 / 仅附件头 / 仅 `application/jpg`+nosniff / 两者兼具）在 `<img>` 中全部渲染成功；
真正受影响的是顶层导航（`setAssetsAttachmentDisposition` 的注释本身写明该头用于「让浏览器 window.open 触发下载而非内联预览」）。
**教训**：上一轮把这条写成「环境差异、不要报」的误报，实际是「产品行为依赖宿主配置」的真缺陷；
**「因为 CI 跑不到」不能当作排除理由**，那是判据 G4 的独立发现，不是免报牌。

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

### 本轮已提 issue

#19472（绝大多数单测不在 CI 执行集）、#19473（`pnpm test` 收集被忽略的 `app/build`）、
#19474（前端 10 处测试失败：替身/白名单/断言/行尾）、#19475（`isAssetInlineUnsafe` 依赖宿主 MIME 注册表）。
四条均 title/body 逐字符回读一致（长度差 1 为 GitHub 自动追加的尾部换行）。

**取证工具**：`%TEMP%\audit-r18\`（Go 探针 + Python 脚本），事后已删除；本轮未在仓库内留任何文件。

### 收官复核（2026-09-14），四条的最终归宿

| issue | 状态 | 修复提交 | 说明 |
|---|---|---|---|
| #19472 | **open**（CI 已通过，维护者未关闭） | `a846821ec2` + `8f0071886c` + `22a727db07` | CI 从白名单改为 `go test -tags "fts5 sqlcipher" ./... -count=1` + `pnpm test`；文档同步 |
| #19473 | closed | `d32b6592f6` | `"test"` 加 `--test-concurrency=4` 与四个 glob，排除 `app/build` |
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

### 第十二轮（2026-09-13）：机械复扫 + 三个未覆盖区域的子代理侦察

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1d（新 P19） | `kernel/model/carddav.go:398`（`LoadAndDelete` 无 `else`）→ `:411` `os.RemoveAll(addressBook.DirectoryPath)`；`kernel/model/caldav.go:331` → `:344` 逐字同构。同族的 `DeleteAddress`/`GetAddressBook`/`DeleteObject`/`GetCalendar` 都有 not-found 分支且常量已存在；上游 `go-webdav@v0.7.0` 按**路径深度**分派、无存在性预检；panic 被 `model.Recover` 吞掉后 `net/http` 补 **200** | 高（实测复现 + 栈帧逐帧核对，`caldav.go` 那条为静态可证） | 挑战门两轮 CONFIRMED，第二轮 DOWNGRADED 至低严重度；已提 issue #19439 |
| A / F | 机械复扫：重复字面量 **166** 条（P1 130 / P2 16 / P3 20，文件数 1360）、未转义插值沿用历轮阈值；逐条核对仍为已知噪声（`assets/`、`/stage/loading-pure.svg`、受 `app/src/types/api/index.d.ts` 联合类型约束的 `/api/` 路由、CSS 选择器、`conf.json`、`0.38`、`INPUT`/`SPAN` 等 DOM 名） | — | 未命中 |
| 候选（未取证） | `kernel/model/flashcard.go:815-828`：`custom-riff-new-card-limit` 解析失败时 `strconv.Atoi` 把 **0** 写进 `newCardLimit`，而 0 在 `getDeckDueCards` 里是最严格值 → 该文档复习时新卡全部消失，只有一行 `invalid ... limit` 日志；同仓其它非法配置一律回落默认 | 中高 | 附录观察项 |
| 候选（未取证） | `kernel/model/flashcard.go:560-570`：卡片管理排序比较器混用 Due 与 ID 两把键，不满足严格弱序，入参来自 map 遍历（每次顺序随机）→ 混合新卡/旧卡时分页可能重复或漏卡 | 中 | 附录观察项 |
| 候选（未取证） | `kernel/model/template_doc_tree_render.go:295`：重生成块 ID 后未调 `treenode.RemapTabsActiveIDs`/`WalkWithTabTitles`，而 `tree.go:102`、`import.go:666`、`template.go:1010` 三处同构实现都调了（全仓仅 4 个调用点） | 中 | 附录观察项 |
| 候选（未取证） | `app/src/asset/renderAssets.ts:67-85`：`genAssetHTML` 的 audio/image/video/a 分支裸插 `pathString`，而同文件 `renderAssetsPreview` 与安全公告修复 `2229686df9` 覆盖的 `asset/index.ts` 都转义了；Windows 文件名限制使其不可达 | 中低 | 附录观察项 |
| 子代理自验推翻 | 候选 4 条：`carddav.go:625` 多卡 vCard 用原文件名做 key（可达性需手工放文件，且重启自愈）、`export.go:4830` 把行 ID 当定义块 ID 写入 `defBlockIDs`（当前无可见后果）、`export.go:1580` 聚焦导出对页签项丢容器（GUI 传文档 ID 不可达，仅 MCP/API 可达）、`publish_access.go:1717` 用 `passwordID` 作守卫（遍历可达状态后确认不可达） | 中 | 自行降级，未上报 |

#### 第十二轮的方法论教训

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

## 如何更新本文

每轮审计后追加：

1. 本轮实际命中（判据编号、发现、置信度）
2. 新增的误报模式
3. 阈值调整（若脚本参数变化）
4. 方法论教训

数据用于校准下一轮的判据与阈值，避免重复劳动。

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

### 第十八轮（2026-09-14）：API 契约重构（#19378）遗留的类型与契约缺陷

用户要求核查「端到端类型契约重构完成后是否还有实际问题」。范围是契约层本身：生成器、schema、路由覆盖、
跨仓产物、声明与实现一致性、请求绑定语义。

| 判据 | 发现 | 置信度 | 状态 |
|---|---|---|---|
| D1n（新 P38）/ D1 / G2 | 加密笔记本主密码在 API 边界被新增 `api:"trim"`：`kernel/apicontract/notebook.go:92`/`:106`/`:107` 的 `Password`/`OldPassword`/`NewPassword`，经 `kernel/apicontract/decode.go:116-121` 实现为「`strings.TrimSpace` + trim 后非空」。主密码是 `deriveKEK`（`kernel/model/crypto.go:1220`）的直接输入，无任何规范化；既有 KEK 按未裁剪的密码派生 → 首尾含空格的用户升级后无法解锁，`changeMasterPassword` 同样失败。重构前 `util.BindJsonArg(..., true, true)` 的第 4 参数是 `rejectEmpty` 而非 trim，旧 `ParseJsonArg` 函数体内无裁剪 → 规范化由契约迁移引入。实测三处 `"   "` 均返回 `Field [...] must not be empty`。附带：同一标记让 `NotebookIDRequest.Notebook` 由「非法 ID」变为「被静默接受」 | 高（机制链逐环核实 + 实测确认 trim 生效；未做端到端加密复现，需高危写入故未执行） | 已提 issue #19477 |
| — | 机械与实证核对为**无缺陷**的环节（同一批结论，供后续轮次跳过） | — | 排除，不报告 |
| 无 | 未取得其他可判定发现 | — | — |

#### 本轮判为干净的环节（附实测口径，后续轮次不必重做）

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

#### 第十八轮的方法论教训

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

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
| D3 / B（新 P11） | `kernel/util/path.go:341` `SiYuanAssetsAudio` 漏 `.aac`，TS `app/src/constants.ts:878` 含之；`IsDisplayableAsset` 为 false 使快照中的 `.aac` 退化为文本路径 | 高（代码可证，挑战门两轮 CONFIRMED） | 待提 issue |
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
| D1 / B（新 P12） | `app/src/util/pathName.ts:174` `getAssetName` 的资源 ID 后缀正则未锚定结尾，剥**首个**匹配而非**结尾** ID，泄漏内部资源 ID 到重命名默认名 / 另存为默认名 / 数据库资源单元格 / 资源提示链接文字 | 高（Node 实测 + 5 处权威实现对照，挑战门两轮 CONFIRMED，严重度 low） | 待提 issue |
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
| D1（同构分支判空缺失） | `kernel/av/calc.go` 中 relation 与 rollup 的 `CalcOperatorCountValues` 只做裸非空判断（`:1687`、`:1778`），而同函数的 `CountEmpty`/`CountNotEmpty` 按 `len(BlockIDs)`/`len(Contents)` 判空。因单元格在 `Calc` 之前已被 `fillAttributeViewBaseValue`（`kernel/sql/av.go:553`）经 `FillAttributeViewNilValue`（`:1100`）/`GetAttributeViewDefaultValue`（`kernel/av/value.go:3194`）无条件补成 `&ValueRelation{}`/`&ValueRollup{}`，该守卫恒真 → 「值数量」恒等于「条目数」 | 高（归一化链逐环核实；挑战门两轮 CONFIRMED，严重度 low） | 待提 issue |
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
| D1b（新 P13）/ E3 | `kernel/util/file.go:417` `IsCompressibleAssetImage` 的 `HasPrefix(p, "assets/")` 守卫恒为 false（唯一调用点 `kernel/model/assets.go:237` 传绝对路径），函数体却用 `strings.Cut(p, "assets/")` 按绝对路径切片；后果是 `temp/thumbnails/assets/**` 永不失效 | 高（调用链逐点核实；挑战门第一轮 CONFIRMED、第二轮 DOWNGRADED 严重度为低） | 待提 issue |
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
| D3（新 P14） | `kernel/treenode/blocktree.go:499` `IsContainerType` 白名单漏掉 `"tab"`（页签项）→ `CheckContainerParent`（`:511`）对页签项报 `type "tab" is a leaf block and cannot have children`（`:524`）。上游 lute `IsContainerBlock`/`CanContain` 与同包 `CanContainBlock`（`block_structure.go:29`）都认定页签项是容器块；同包 `NormalizeTabs` 还主动为其补段落子块。受影响的写路径共 14 处：API（`kernel/api/block_op.go:452,534,575,624,738`）、MCP（`kernel/mcp/tools/block.go:202,259,303,456`）、CLI（`kernel/cli/cmd/block.go:208,250,290,470`）、`kernel/model/block_operation.go:34`、`kernel/model/attribute_view_create.go:58` | 高（实测复现：同一页签项 ID `get_children` 返回 5 个子块、`append(parentID=该ID)` 被拒，报错串与 `:524` 完全一致） | 待提 issue |
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
| D3c（新 P15）/ A / P4 | 搜索「保存条件」静默丢弃 `tabs`/`tabItem` 两个类型过滤开关：权威集合 `kernel/conf/search.go:46-47` 的 `conf.Search.Tabs`/`TabItem`（`TypeFilter()` 与 `kernel/model/search.go:2090-2091` 的 `buildTypeFilter` 都按这两个键读），但 `kernel/model/storage.go:142` 的 `model.CriterionTypes` 与 `kernel/apicontract/criterion.go:20` 的 `apicontract.CriterionTypes` 都只有 18 字段。前端 `app/src/search/menu.ts:347` 把 20 键的 `config.types` 整体 POST，经 `criterionModel` 指针强转落盘；读回时 `app/src/search/config.ts:198` 又用条件的 `types` 整体替换当前 config。实测 POST 20 键 → GET 18 键，`tabs`/`tabItem` 消失 | 高（本机运行实例实测；挑战门两轮 CONFIRMED） | 待提 issue |
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
| A / D3 / G1（新 P16） | 内核本地化消息以**整数下标**为身份（396 条 × 21 语言），格式契约（131 条带占位符）只隐含在译文副本里；无载体（AGENTS.md 未提占位符）、无表达能力（显式实参索引 `%[n]` 全量 0 次使用）、无有效校验（键集合门对无义整数退化为存在性；译文门 `sorted()` 抹顺序、正则 `%[sdf]` 漏 `%v`、无 `exit(1)`、不在 CI）。实测已漂移 10 处：hi/ko/tr 的 89/90/234 换位 → `%!s(int=3)`/`%!d(string=…)`；ar 的 210 丢 `%v` → `%!(EXTRA int=7, int=9)` | 高（Go 探针实跑 + 21 文件全量比对 + 两道门实跑） | 待提 issue（严重度低） |
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

## 如何更新本文

每轮审计后追加：

1. 本轮实际命中（判据编号、发现、置信度）
2. 新增的误报模式
3. 阈值调整（若脚本参数变化）
4. 方法论教训

数据用于校准下一轮的判据与阈值，避免重复劳动。

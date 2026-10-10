# 缺陷模式库

本文是审计判据的**累积库**。每轮审计后把新验证有效的判据追加进来，把新误报写进 `SKILL.md` 的「已知误报」。

模式的组织方式参考了社区先例 `github/awesome-copilot` 的 `quality-playbook` skill（MIT）。该先例从 56 个确认缺陷中提炼了 7 个模式，本文据本仓库的实际结构调整并增补。

## 统一产出格式

每个模式的产出都应是「候选需求」形态，便于后续验证：

```
### [位置]
- 权威源:   <规范 / 上游定义 / 公共 API / 另一实现>
- 实现 A:   [file:line] — 做了什么
- 实现 B:   [file:line] — 做了什么，差异在哪
- 缺口:     <具体缺什么>
- 可验证性: <如何复现>
- 业务表现: <用户可见入口与实际观察到的结果>
- 预期表现: <应该是什么 + 权威依据>
```

后两项为强制项：只有代码层结论、写不出用户可见行为的，属「影响范围未查清」，不得作为主报告条目。

## P1 降级路径不保持不变量

**定义**：同一目标存在主路径与降级/回退路径时，降级路径必须保持与主路径相同的行为契约。机制可以不同，可观察行为必须等价。

**为何出现**：降级路径写得晚、测得少、审得松。开发者常复制主路径再简化，于是漏掉校验、清理、索引赋值、资源释放等步骤。结果是在常见情况下正确，一旦降级激活就违约。

**本仓库候选位置**：
- 资源下载的按需模式与全量模式
- 同步的多云服务商分支（SiYuan / S3 / WebDAV / Local）
- 加密笔记本与普通笔记本的分支路径
- `kernel/model/asset_download_recovery.go` 的恢复路径

**检查法**：列出主路径与全部降级路径，逐个核对主路径执行的关键操作（校验、资源建立、清理、错误上报）在降级路径是否同样存在。

## P2 分派返回值正确性

**定义**：函数按条件分派并返回状态值时，返回值必须对**所有输入组合**正确，而不仅是对主路径正确。

**为何出现**：分派器通常只为主路径编写与测试。当出现异常组合（仅次要事件触发、无事件、事件并发）时，返回逻辑可能错误——把已处理事件报为未处理、把部分失败报为成功、或返回上一轮的陈旧值。

**本仓库候选位置**：WebSocket 推事件分发、`kernel/api` 的处理器返回码、事务提交结果聚合、`handleLANSyncCommitHint` 这类条件入口。

**检查法**：枚举全部输入组合，**包括隐式的 else / default 分支**；追踪返回值穿过整个处理链，而不只是当前函数。

## P3 跨实现契约一致性

**定义**：同一逻辑操作在多个实现中（不同传输、不同后端、不同协议版本）都必须满足同一规格要求。规格中强制的步骤必须出现在每个实现里。

**对应判据**：B（语义漂移）。

**本仓库候选位置**：
- `PathsAffectSync` 与 dejavu 的 `builtInIgnore`（已确认不一致，见 [实证数据](./evidence.md)）
- 加密笔记本与普通笔记本的导出、历史、备份路径
- 内核与 `app/src` 对同一协议的往返处理

**检查法**：列出共享的规格要求与强制步骤，逐个实现核对。**找到第一个缺口后不要停止**——同类跨实现操作往往不止一处。

## P4 闭合集合完整性

**定义**：代码维护一组「被认可的值」时（switch 白名单、常量数组、枚举、schema 关键字、注册表），权威源中应有的值必须全部出现。缺失项会被静默丢弃。

**对应判据**：D3。

**为何出现**：闭合集合写一次后很少回看。新增能力时，定义该能力的代码和使用它的代码都更新了，但**决定它能否通过过滤的那份闭合集合被遗忘**。功能看起来已支持（已定义、已协商、已使用），却在一个没人记得更新的过滤器中被静默剥离。

**本仓库候选位置**：
- `kernel/model/sync.go` 的同步忽略规则集合
- `app/src/types/api/index.d.ts` 的路由联合类型与内核实际注册的路由（`kernel/api/router.go`）
- `app/src/config/entryVisibility/catalog.ts` 的可配置菜单项（`AGENTS.md` 有专门约束）
- 文件扩展名/类型的分派表

**检查法**：
1. 机械提取闭合集合（case 标签、枚举成员、数组项），存成文件；与权威源逐项 diff。
   **调用方自行补偿不能作为豁免理由**——补偿是变通不是修复，任何不知道要补
2. **前端 DOM 契约已脚本化**：`scan_dom_type_literals.py` 提取 `data-type` 的闭合集合，
   并列出「仅出现一次的值」（漏项的最强候选）。权威源是 **Lute 输出的 NodeType**，
   拿到集合后必须与它逐项 diff；脚本只负责把集合拿出来，**不负责判定漏项**。
3. 内核侧的枚举/白名单仍需手工提取（它们的定义形式不统一），但优先看
   「同包另有一个委托给上游的等价函数」这个信号——自相矛盾比差集更省力。偿的新调用方都会继承该缺陷。

## P5 API 表面一致性

**定义**：同一逻辑操作可通过多个 API 表面完成时（直接方法 vs 包装视图、构造器 vs setter、同步 vs 异步、主 API vs 便捷别名），所有表面对同一输入必须产生等价的可观察行为。

**对应判据**：D2。

**本仓库候选位置**：`fetchPost` / `fetchSyncPost` / `fetchGet` 三类调用；插件的同步与异步 API；`kernel/api` 与 `kernel/mcp` 对同一能力的暴露。

**检查法**：对每一对表面，用同一边界输入（空值、边界值、特殊字符、顺序敏感数据）分别测试，行为分歧（异常类型、编码、顺序、空值语义）即为候选缺陷。

## P6 结构化值解析保真

**定义**：解析由规范定义的值的（HTTP 头、URL、MIME、CLI 参数、JSON Schema 关键字、文件路径）时，解析必须符合规范实际规则。用子串匹配、精确相等、错误分隔符、无边界检查的前缀匹配等捷径，会产生「常见输入可用、合法边界输入失败」或「接受非法输入」的解析器。

**对应判据**：E3、E4。

**实证案例（本仓库）**：dejavu 的 `builtInIgnore` 用 `strings.HasSuffix(path, "data/storage/local.json")` 判断，依赖「数据目录必须名为 `data`」；同目录下 `xxx/data/storage/local.json` 会被误伤。

**本仓库候选位置**：资源路径与链接的解析、`kernel/util/path*.go` 的路径处理、前端 `startsWith`/`includes` 类路由或类型判断、markdown/URL 解析。

**检查法**：确认规范（RFC、格式定义）；检查是否处理了分词、引号、参数、大小写折叠、空白裁剪、边界条件；**构造一个「按规范合法但会被该实现误判」的输入**——能构造出来即为候选。

## P7 组合上下文中的状态选择

**定义**：代码运行在组合上下文中（挂载在子路由、嵌套于父模块、限于子容器、被框架适配器包装）时，框架通常同时维护**规范表示**（当前上下文所确认的活跃状态）与**原始表示**（外层调用方最初传入的）。读取或写入原始表示而非规范表示，在外层恰好正确，在组合下会静默失败。

**对应判据**：C（状态保持）、E1。

**本仓库候选位置**：
- 加密笔记本在解锁/未解锁时的路径与配置解析（`ExtractBoxIDFromAssetsPath` 反查即属此类）
- 工作空间级与笔记本级配置的覆盖关系
- 插件运行时的上下文隔离
- 移动端与桌面端的容器差异（`util.IsMobileContainer()`）

**检查法**：确认框架在组合下维护的规范表示是什么，代码实际读的是哪个；构造一个最小的组合示例，检查行为是否与在外层时一致。

## 补充模式（源自本仓库实证）

### P8 渲染重建时的状态丢失

**对应判据**：C。本仓库最高频类别（`preserve`/`keep`/`restore` 共 344 次）。

**实证案例**：提交 `dfa2c589f2` 把 `value: ""` 改为 `value: element.querySelector("#criteria .b3-chip--current")?.textContent || ""`——重建下拉时未回填当前值。

**检查法**：搜索「重建 / 重置 / 重新渲染 / refresh / rerender / reload」的位置，检查是从当前状态读值，还是写死初始值。

### P9 动态插值未转义

**对应判据**：F。可机械扫描。

**实证案例**：提交 `dfa2c589f2` 与 `f811001983` 把 `${tag}` 改为 `${escapeHtml(tag)}`。

**检查法**：运行 `scripts/scan_unescaped_html.py`，人工确认候选。

### P10 聚合累加方向反转

**对应判据**：D1（相邻代码块不对称）。本仓库第二轮新确认。

**定义**：把一组值归约成单个标量时（求和、计数、合并），代码误把「累加器加到元素上」
写成 `element += accumulator`，而非 `accumulator += element`。累加器因此恒为初值，
归约结果永远等于初值，而被遍历的元素被无意义地改动后再丢弃。

**为何出现**：多为重构的产物。原实现在 map 或另一集合上遍历，改写为「先排序取前 N，
再遍历剩余部分」时，把循环变量与累加器的角色写反，且没有测试锁定归约结果。

**实证案例（本仓库）**：`kernel/model/repository.go` `statTypesByPath`。
提交 `26a11dc3d0` 原本是 `for _, count := range m { otherCount += count }`（正确）；
提交 `e73f38390b` 重构为 `for _, tc := range ret[10:] { tc.Count += otherCount }`（反转，回归）。
`otherCount` 全程无赋值，`Other.Count` 恒为 0，前端 `app/src/history/history.ts` 直接渲染出 `Other 0`。

**本仓库候选位置**：
- 快照/统计类归约（`kernel/model/` 下的 `stat*`、`calc*`、`count*` 函数）
- 流量、耗时、字节数的多处累加（`trafficStat`、`elapsed` 聚合）
- diff/合并结果的计数聚合

**检查法**：对每个「归约成标量」的循环，确认**被写入的变量是累加器本身**。可用脚本机械筛查：
循环体内出现 `X += Y` 且 `X` 是循环变量的字段、`Y` 是循环外的标量——即嫌疑。
再反向确认该标量在函数内是否有任何赋值（无赋值即恒为初值）。

### P11 跨实现常量表漂移

**对应判据**：D3、B、P3。

**定义**：同一份「被认可的值集合」在两种语言或两个包里各维护一份，**同名**且**几乎逐项相同**，
仅个别成员不一致。不一致本身不等于缺陷——必须先判定该差异是否产生可观测的错误行为，
以及「应该是什么」是否有可引用的权威源。

**为何出现**：这类表没有代码生成、没有共享常量、没有跨语言一致性测试；
一边新增成员时另一边被遗漏。且漂移方向**可能相反**：一侧漏项（该有的没有），
另一侧超收（不该有的有了），因此「向成员多的一侧对齐」是错误修法。

**实证案例（本仓库）**：`kernel/util/path.go` 与 `app/src/constants.ts`。
- `SiYuanAssetsAudio`（`kernel/util/path.go:341`）缺 `.aac`；TS `SIYUAN_ASSETS_AUDIO`（`app/src/constants.ts:878`）含 `.aac`。
  内核唯一消费点 `util.IsDisplayableAsset()`（`:380`）被 `OpenRepoSnapshotFile`（`kernel/model/repository.go:521`）调用：
  为 false 时 `content` 保持 `""`，前端 `renderRepoFile`（`app/src/history/repoFile.ts:137`）遂退化为把仓库内路径当纯文本显示。
  同一产品内 `.aac` 在编辑器里是 `NodeAudio`、在快照里是文本路径 —— 可观测的自相矛盾。
- 反向漂移同一对表上同时存在：TS 侧 `SIYUAN_ASSETS_IMAGE` 含 `.tif`/`.tiff`，Go 内核侧不含。
  浏览器通常不渲染 TIFF，故此处更可能是 **TS 超收**，与 `.aac` 的修复方向相反 —— 这条正是「不可一律对齐」的实例。

**检查法**：
1. 机械提取两语言中同名常量表，逐项 diff（成员数、顺序无关）。
2. 对每一处差异，找出该表在两侧的**全部消费点**，判断差异是否落到可观测行为上。
3. 差异不产生可观测行为的（表未被消费、或两侧消费路径等价）→ 降级为观察项，不报告。
4. 产生可观测行为的，分别判定每一侧的权威性：历史是否成对维护（查 `git log -L`）？
   哪一侧是渲染/判定方？同包内是否另有自相矛盾的判定（如 `commonSuffixes` 含 `.aac`）？
5. 结论必须给出**逐成员**的修复方向，不能笼统写「对齐两侧」。

### P12 同义字符串变换的多实现漂移（未锚定首次匹配）

**对应判据**：D1、B，是 P11「跨实现常量表漂移」在**字符串变换**上的特例。

**定义**：同一个「从文件名/路径派生名字」的变换在仓库内有多份实现（内核与前端，或前端的多处），
其中**一份**用未锚定的 `replace`（剥首个匹配），其余用结尾锚定（`$`）。
当输入含有**多个**可匹配片段时，唯一未锚定的实现会剥错片段，把内部生成物（ID、时间戳）泄漏到用户可见名字里。

**为何出现**：该变换没有单一真源（无共享常量、无 codegen、无常量函数），各处按需手写复制；
`$` 是极易漏掉的细节，且只在「输入含多个匹配片段」时才产生差异，
因此常规测试与常见输入都不会暴露。**函数无单测时尤其容易长期漂移。**

**实证案例（本仓库）**：
- `app/src/util/pathName.ts:174` `getAssetName` 用 `.replace(/ -\d{14}-\w{7}/, "")`（未锚定、无 `g`）。
- 同仓前端另两处锚定结尾：`app/src/asset/anno.ts:184`（`/-\d{14}-\w{7}.pdf$/`）、`app/src/protyle/preview/image.ts:54`（`/-\d{14}-\w{7}$/`）。
- 内核四处只处理结尾 ID：`kernel/util/file.go:154` `RemoveID`、`:206` `LastID`、`:189` `AssetName`，
  以及 `kernel/model/upload.go:120` `assetNameWithoutID`（后者还为「纯 ID 名」补 `asset` 前缀）。
- 触发：资源文件名在**结尾 ID 之外**还含 `-<14位数字>-<7位字母数字>`。
  可达路径：上传 `report-20240101120000-abc1234-final.pdf` 时内核只剥结尾 ID、随后追加新 ID，
  落盘为 `...-final-<新ID>.pdf`；或经重命名对话框把资源改成该形态（`RenameAsset` → `util.AssetName` 同样只认结尾）。
- 业务表现：资源重命名默认名 / 另存为默认名 / 数据库资源单元格显示名 / 资源提示链接文字
  会把内部资源 ID 显示给用户（纯展示层，可被用户覆盖，故严重度低）。
- 可验证：`getAssetName("assets/report-20240101120000-abc1234-final-20250901120000-xyz9876.png")`
  应为 `report-20240101120000-abc1234-final`，实为 `report-final-20250901120000-xyz9876`。

**检查法**：
1. 机械提取同一语义的变换调用（同一 `replace` 正则出现在多处），按**有无 `$`** 分组；
   唯一未锚定的一项即嫌疑。
2. 确认「多匹配片段」输入是否**可达**——不可达则降级为观察项。
3. 判定应剥哪个片段时，优先采信**写盘路径**上的实现（磁盘语义比展示语义严格），
   再看前端同义实现是否一致。
4. 注意同一正则的**字符集**也可能漂移（`\w{7}` 含大写与 `_`，内核 `ast.IsNodeIDPattern` 只认 `[0-9a-z]{7}`）。

### P13 恒假守卫（守卫预设的实参形态与调用契约不符）

**对应判据**：D1b、E3。

**定义**：函数以「保护/过滤」为名加了一个前置守卫，但该守卫假定的实参形态与**全部调用点**实际传入的形态不一致，条件恒为 false，守卫之后的全部逻辑成为死代码。
与「恒真守卫」（上游归一化使条件多余）方向相反：恒真让多余的判断吞掉语义，恒假让整个函数失效。

**为何出现**：多为「调用约定变更未同步改守卫」。函数最早可能在相对路径语境下编写，调用方后来改传绝对路径（或反之），守卫那一行被遗漏。
**函数无单测时不会暴露**——守卫把它自己变成了 no-op，永远不报错，也不产生异常输出。

**实证案例（本仓库）**：`kernel/util/file.go:417` `IsCompressibleAssetImage` 要求 `strings.HasPrefix(p, "assets/")`，
但其唯一调用点 `kernel/model/assets.go:237` `removeAssetThumbnail` 传绝对路径；
且函数体本身用 `strings.Cut(p, "assets/")` 按绝对路径切片——守卫与函数体对入参形态的假设互相矛盾。
后果是 `temp/thumbnails/assets/**` 在资源被原地改写后永不失效（生成端 `kernel/server/serve.go:1579` 只在文件不存在时才重建）。

**本仓库候选位置**：
- 以路径形态为前提的守卫（`HasPrefix(p, "assets/")`、`HasPrefix(p, "data/")`、`filepath.IsAbs` 的补集）
- 大小写/编码形态守卫（先 `ToLower` 再比对前缀，而调用方传的是另一种已折叠/未折叠形态）
- 扩展名/协议守卫（守卫用 `HasSuffix(".png")`，调用方传入的却是带 `?`/`#` 的 URL）

**检查法**：
1. 对每个「守卫 + 其后整段逻辑」结构，grep 该函数的**全部调用点**（不是同函数内的用法）。
2. 逐点确认实参形态：绝对/相对、是否带 `?`/`#`、是否已 `ToLower`、跨平台路径拼接。
3. 若守卫条件对全部实参形态为 false → 该函数为死代码；再读函数体，若体内部对同一实参做了另一种形态假设，二者矛盾即强证据。
4. 无测试覆盖的辅助/同义函数优先排查。
5. 定性严重度前先确认**有无替代路径**（缓存类还要确认唯一的失效机制是否存在）。

### P14 能力白名单漏掉上游新增的容器成员

**对应判据**：D3（闭合集合漏项）、D2（同一操作多表面）。

**定义**：一段手写的类型白名单充当「某能力是否适用」的判据（如「能否接收子块」「是否容器块」），
而该能力的权威定义在上游库的类型方法里。上游新增成员后白名单未同步，
于是同一个块在**读路径**与**写路径**上得到相反结论。

**为何出现**：白名单没有单一真源（不是从类型定义 codegen 出来的，也不是跨语言常量表），
新特性落地时只改了功能路径，没人回头核对这份枚举。
**同包或同文件若另有一个委托给上游的等价函数（如 `CanContainBlock`），两者必然开始自相矛盾——
这是最省力的发现信号：不必先确认可达性，自相矛盾本身即强证据。**

**实证案例（本仓库）**：
- `kernel/treenode/blocktree.go:499` `IsContainerType` 白名单 = `"d","b","l","i","s","callout"`，不含 `"tab"`。
- 但 `kernel/treenode/node.go:413` 已登记 `NodeTabItem → "tab"`，`kernel/treenode/blocktree.go:837` 把该缩写写入 `blocktrees`。
- 上游 lute `ast.Node.IsContainerBlock()` 含 `NodeTabs`/`NodeTabItem`；`CanContain(NodeTabItem, NodeParagraph) = true`。
- 同包 `kernel/treenode/block_structure.go:29` `CanContainBlock` 委托上游 → 同包自相矛盾；
  同包 `kernel/treenode/tabs.go` 的 `NormalizeTabs` 还主动为页签项补齐段落子块（`tabs_test.go:19` 断言之）。
- 后果：`CheckContainerParent`（`:511`）对页签项报 `type "tab" is a leaf block and cannot have children`（`:524`），
  而读路径 `kernel/model/block.go:1635` `getChildBlocksFromTree`（用上游方法）能正常列出其子块——
  实测同一个页签项 ID：`get_children` 返回 5 个子块、`append(parentID=该ID)` 被拒。
- 时间线：白名单 `db266e7fab`（2026-06-20），页签特性 `5b8556e965`（2026-09-05）——**晚 2.5 个月且未回头同步**。

**本仓库候选位置**：
- 两份同义白名单：`treenode.IsContainerType`（缩写集合）与 `model.Block.IsContainerBlock`（全名集合），
  后者唯一消费点是 `kernel/model/search.go:528`。
- 任何以 `case "d", "b", …` / `case "NodeDocument", …` 手写枚举「能容纳子块 / 可编辑 / 可搜索 / 可导出」的函数。

**检查法**：
1. grep 出「把类型名或缩写列表写进 `case`」的能力判定函数（容器、可编辑、可搜索、可导出…）。
2. 找同包/同文件**委托给上游类型方法的等价函数**，逐项 diff 两边成员集合；差异即候选。
3. 判定权威侧：优先上游库类型方法（`IsContainerBlock` / `CanContain`），
   再看同包是否有函数主动构造出该结构（如 `NormalizeTabs` 造 `TabItem > Paragraph`）。
4. 用「读路径 vs 写路径」两端对照确认可达性（本例：读子块成功 = 写子块被拒，一条命令即可证）。
5. 注意差异方向可能相反（白名单超收 / 漏收），不要一律向成员多的一侧补；
   本例 `NodeTabs` 是**故意不收**（上游 `CanContain(NodeTabs, …)` 只允许 IAL），
   所以「把上游两个成员都塞进白名单」是错的修法。

### P15 跨契约边界的手写 DTO 漏项（静默丢字段）

**对应判据**：D3c、A（单一真源缺失）、P4。

**定义**：同一个「被认可的值集合」在运行时配置结构体、持久化 struct、API 契约（`apicontract`）struct
与前端类型里各维护一份手写副本。新增成员时只更新了运行时配置与前端，**契约/持久化 DTO 未同步**；
由于请求与响应用标准 `encoding/json` 解码（未启用 `DisallowUnknownFields`），未知字段被静默丢弃，
用户数据在写路径上消失且不报错。若两侧 DTO 通过结构体指针强转互转（`(*B)(a)`），
修复还受「必须逐字段同布局同顺序」的额外约束。

**为何出现**：契约迁移（把处理器参数从 `map[string]any` 收窄为强类型 request struct）时，
DTO 是照既有 model 结构体**抄一份**得到的。抄写发生在某一时点，此后运行时的集合继续演进，
DTO 便成了「冻结的快照」。而 Go 的结构体转换要求底层类型完全相同，抄写双方被绑定为镜像，
一侧加字段而另一侧没加时**编译期不报错**——只在字段缺失处静默丢数据。

**实证案例（本仓库）**：保存的搜索条件丢失「页签 / 页签项」过滤器（详见 `evidence.md` 第八轮）。
- 权威集合：`kernel/conf/search.go:46-47` 的 `conf.Search.Tabs`/`TabItem`；
  `TypeFilter()`（`:261-266`）与 `kernel/model/search.go:2090-2091` 的 `buildTypeFilter` 都按
  `types["tabs"]`/`types["tabItem"]` 读取。
- 缺口两处：`kernel/model/storage.go:142` 的 `model.CriterionTypes`（18 字段）与
  `kernel/apicontract/criterion.go:20` 的 `apicontract.CriterionTypes`（18 字段），均无 Tabs/TabItem。
- 写路径：`app/src/search/menu.ts:347` `saveCriterionData` 把整个搜索 config（20 键，含 `tabs`/`tabItem`，
  见 `app/src/search/getDefault.ts:18-19`）作为 `criterion` POST 到 `/api/storage/setCriterion`
  → `kernel/api/storage.go:186` 绑定 `apicontract.SetCriterionRequest`
  → `kernel/api/contract_storage.go:67` `criterionModel` 指针强转 → `:246` `setCriteria` 落盘。
- 读路径：`criterionContracts`（`kernel/api/contract_storage.go:53`）同样表达不了这两个键；
  前端 `app/src/search/menu.ts:700` 每次渲染面板都从 `/api/storage/getCriteria` 重建条件列表，
  点击 chip 时 `app/src/search/config.ts:198` 用条件的 `types` **整体替换**当前 `config.types`
  （`syncSearchConfig` 先删光所有键再 `Object.assign`），于是 `config.types.tabs` 变为 undefined，
  筛选开关复位、`buildTypeFilter` 读成 false、`configIsSame` 永久为 false 使 chip 不高亮。
- 实测：POST `setCriterion` 时 `types` 带 20 个键（`tabs:true, tabItem:true`），
  随后 GET `getCriteria` 读回只剩 18 个键。
- 时间线：`git log -S tabItem` → `5b8556e965`（2026-09-05，Support tabbed container blocks）改了
  `kernel/conf/search.go`、`app/src/search/getDefault.ts`、`app/src/search/menu.ts`、
  `app/src/types/config.d.ts`，**未**改 `kernel/model/storage.go` 与 `kernel/apicontract/criterion.go`。

**本仓库候选位置**：`kernel/apicontract/*.go` 中从 `kernel/model` 抄来的 DTO（`Criterion`、`RecentDoc`、
`BlockInfo`、`SearchSubTypes`…），尤其与前端 `app/src/types/config.d.ts` 存在同名键集合的那些。

**检查法**：
1. grep 同一 `json` 标签名（如 `"tabItem"`、`"callout"`）在仓内的全部出现，按
   「运行时配置 / 持久化 struct / apicontract struct / 前端类型」分组，逐组 diff 成员。
2. 确认请求与响应解码是否使用标准 `encoding/json` 且无 `DisallowUnknownFields`：
   有则表现为报错（用户当场可见），无则表现为静默丢数据（危害更大）。
3. 检查两侧 DTO 是否用指针强转互转（`(*A)(b)`）——存在则该字段必须在**等价位**插入，否则整体错位。
4. 走一遍写后读往返，比较键集合是否守恒（`len(sent) == len(returned)`）——最省力的不变量。

**与 P4 的区别**：P4 是集合本身漏成员（消费点仍在同一份数据内）；P15 是**集合的副本**漏成员，
且副本位于序列化边界，因此缺陷表现为「数据在往返中消失」，而非「某次判定走错分支」。

### P16 位置编号做身份 + 格式契约无载体（资源契约缺口）

**对应判据**：A（单一真源缺失）、D3（跨语言同名常量/集合表）、G1（缺交叉断言）。

**定义**：一组被多处引用的**资源**（本地化消息、错误文案、模板串）用**位置编号**（整数下标）作为身份，
调用方以裸整数硬编码引用；资源之间还存在**格式契约**（占位符的数量、顺序、类型），
但该契约只隐含在每一份副本里——没有声明、没有载体、没有校验。
当副本所在语言/场景的语序与基准不同时，**换位是唯一可用的手段**，
而按位置填充的格式化（Go `fmt`、C `printf`、Python `%`）换位即破坏输出。

**为何它能躲过审计**：位置编号在**同一发布内**由同一份物理文件保证一致（内核与前端读同一个文件），
因此看上去「自洽」；它甚至常是**有意设计**（append-only ID 空间，为兼容历史数据与旧客户端）。
标识符的**自洽性**被误当成契约的**完整性**。缺的从来不是身份方案，而是格式契约的载体与校验。
**报告时必须把这两件事分开**，否则会被维护者以「身份设计是有意的」整体驳回。

**三件套诊断（缺任一则不成立）**：

| 维度 | 问什么 | 本案例答案 |
|---|---|---|
| 载体 | 格式契约有没有单一真源，还是只隐含在副本里？ | 只隐含在 21 份译文里 |
| 表达能力 | 契约能否表达副本的**合法需求**（如语序调整）？ | 不能：显式实参索引 `%[n]` 在全部副本中 0 次使用，项目也未声明该用法 |
| 校验 | 门是否与被保护对象**正交**？ | 是：键名集合校验对「键名无义」的资源退化为存在性/计数比对 |

**表达能力这一条最关键**：若契约无法表达需求，副本只能以「违规」方式实现意图，
于是漂移不是偶然笔误而是**系统性倾向**（证据：3 种语言独立地都选择了换位）。
反之若契约提供了出口（如 `%[3]s`），漂移就退化为作者失误，不应上报。

**实证案例（本仓库）**：内核本地化消息表 `app/appearance/langs/*.json` 的 `_kernel` 块。
- 身份：整数下标字符串，`kernel/model/conf.go` `initLang()`（`:969` `strconv.Atoi`、`:974` `kernelMap[num]`）
  读入 `util.Langs[lang][num]`；`Language(num int)`（`:1308-1320`）**按同一个数字**回退英文，再回退空串。
- 引用面：Go 侧 `Conf.Language(n)`；TS 侧 `window.siyuan.languages._kernel[142]` 实测 88 处 / 39 文件 / 29 个下标；
  Electron 宿主 `app/electron/connections.js:190`、`remote-auth.html:241`；gomobile `kernel/mobile/kernel.go:309
  func Language(num int) string`、`kernel/harmony/kernel.go:164`。
- 契约规模：`en` 共 396 条，其中 **131 条含占位符**（1 个 80 条、2 个 32 条、3 个 14 条、4 个 3 条、6 个 2 条）。
- 载体缺口：`AGENTS.md` 对该块只规定「新增追加到末尾用下一个递增数字键」，**全文未提占位符**。
- 表达能力缺口：21 个语言文件里 `%[n]` 出现 **0 次**（无显式实参索引能力）。
- 校验缺口：`scripts/check-lang-keys.py` 判据是键名集合（`missing = expected_keys - keys`），
  对无义整数键退化为「条目数/存在性」；`scripts/check-translations.py` 第 48 行正则 `%[sdf]` **漏 `%v`**、
  第 49 行 `sorted(ps)` **抹平顺序**、`main()` 无 `exit(1)`、且未被任何 CI 调用。
- 已漂移 10 处（实测）：hi/ko/tr 的 89/90/234 仅顺序不同（多重集合相同 → 被 `sorted()` 掩盖）；
  ar 的 210 丢了两个 `%v`（`%v` 不在正则里 → 不可见）。
  真实调用形状 `fmt.Sprintf(Conf.Language(90), current, total, blockCount, hash)`（`kernel/model/index.go:459`）、
  `Conf.Language(210), count, total`（`kernel/model/repository.go:3207`）的实跑输出为
  `%!s(int=3)`、`%!d(string=a1b2c3d)`、`%!(EXTRA int=7, int=9)`，经 `util.SetBootDetails` + `util.ContextPushMsg` 展示。
- 同文件反例：同一份 lang 文件里的 `replaceTypes`(25)/`_time`(19)/`_taskAction`(15)/`_trayMenu`(11)/`_attrView`(10)
  全部使用**符号键**，且被同样的内核与前端消费——证明符号方案在本项目可行，非语言/框架限制。
- 同仓对照：HTTP 边界有完整契约纪律（`kernel/apicontract` 的 schema + `TestGeneratedArtifacts` 生成物校验
  + `TestAPIContractRouterCoverage` 路由双向覆盖 + `CheckRoutes` 拒绝新无类型路由），
  **消息边界完全没有**——这排除了「有意省略」的解释。

**其他领域的同类形态**（报告时可就近取证）：

1. **整数错误码 / 事件码 + 模板分离**：错误对象只带 `int`，模板在另一处维护，两侧靠约定对齐。
2. **线协议按字段位置定义**（无标签的 struct 序列化、定长记录）：中间插入字段即静默错位。
3. **SQL 位置绑定参数**与语句文本分离存放，且参数顺序无编译期校验。

**检查法**：

1. 找「被多处引用的资源目录」（langs、locales、messages、templates），确认其**身份方案**与**格式契约的载体**。
2. 对带占位符的条目，把基准语言的占位符**有序序列**（含全部动词，`%v/%t/%q` 都要算）与各副本比对。
   仅比较多重集合是不够的——`sorted()` 会掩盖本类缺陷。
3. 检查契约能否表达副本的合法需求（是否存在显式实参索引或命名占位符的**实际使用**）。
4. 用真实调用形状跑一次格式化，输出含 `%!` 即坐实；同时确认门的判据字段是否与被保护对象同维度。
5. 用 `git log -S` 与文件内的符号键块做对照，区分「有意设计方案」与「遗漏」。

**与 P15 的区别**：P15 是**值集合的副本**漂移导致数据在往返中消失；P16 是**格式契约**只隐含在副本里，
不经序列化边界也会失效，且修复方向通常只是「补一条校验 + 修若干副本」，不需要改身份方案。

### P17 跨仓公开类型契约的手工镜像无子集断言

**对应判据**：A（单一真源缺失）、D3（闭合集合漏项）、G1（缺交叉断言）。

**定义**：一个被**公开 API 消费**的闭合集合（操作名、事件名、配置键）在仓库 A 内是手写的联合类型/枚举，
并被复制到另一个**独立发布**的仓库 B（插件/客户端 SDK 的类型包）。两侧靠人工同步，
仓库 A 内没有任何断言能发现 B 的滞后。**A 的编译期检查会始终为绿——它只能约束 A 自身的使用。**

**为何出现**：复制发生在某一时点，之后新成员只加在 A 侧。因为 B 不在 A 的依赖里（A 无法 import B，也就无法比对），
漂移对 A 完全静默。与 P15 的区别：P15 的漂移导致运行期丢数据；**P17 的漂移只产生「伪编译错误」**——
能力真实存在且可用（内核有处理分支、官方客户端自己也在发送），但公开契约不声明，只有消费方（插件作者）会遇到。

**为何难判（三处易错）**：

1. **两侧本就不应全等**：存在合法的单向成员（仅客户端→服务端、仅服务端下推、仅内部使用），
   所以「应该是什么」不能用「对侧全集」表述。取相等不变量会把合法成员判成假阳性。
2. **权威侧可能明确声明「不承诺稳定」**：若文档写明该操作集是内部实现、不保证兼容性，
   则「应补全」的强度大幅下降，严重度需下调。
3. **只补名字不补载荷字段会造出「说谎的类型」**：被质疑的联合类型往往与另一个带载荷字段的 interface 配套，
   若只加成员名而不补字段，消费方仍需 `as any`，类型层是「假装支持」。

**成立条件（三条同时满足才报告）**：有**书面同步义务** + 有可观测的**伪错误** + 存在**单向子集**这一可判定不变量。

**实证案例（本仓库）**：

- petal（npm 包 `siyuan`，插件官方类型依赖）的 `TOperation` 是 `app/src/types/index.d.ts` 同名联合类型的手工镜像。
- 消费点：`petal/types/protyle.d.ts:316 public transaction(doOperations: IOperation[], undoOperations?: IOperation[]): void`
  + `petal/types/index.d.ts:597 action: TOperation`。
- 书面义务：`AGENTS.md`「Type declarations」明文要求改 `app/src/types/` 下暴露给插件的声明时**在同一任务同步 petal**。
- 实测积压 **15 项**（`duplicateAttrViewRow` 2026-06-16 → `setAttrViewContextFilter` 2026-09-04），
  petal 侧 `git log -S` 对全部 15 项返回空（从未加入）；**同时 petal 仍在主动增补**
  （2026-08-24 加入 `sortAttrViewBinding`/`setAttrViewCustomColors`）——是**积压**而非冻结。
- 第二维：只补名字不够——`app` 侧 `IOperation` 的 `cellUpdates`、`viewIDs` 两个载荷字段 petal 也没有。
- 已排除的反证：内核 `switch op.Action`（96）与 `app` 的 `TOperation`（94）**本来就不等**
  （`create` 仅内核内部建文档树、`updateAttrs` 仅内核下推给前端），故不变量只能取**单向** `petal ⊆ app`。

**其他领域的同类形态**：

1. **浏览器扩展 API 的 `@types` 滞后于运行时**：新 API 已可用但类型包未更新，TS 报「不存在」——经典形态。
2. **客户端 SDK 与后端 proto 漂移**：若有 codegen 则不会发生；一旦改为手抄就会。
3. **组件库的 props 联合类型与运行时校验分离**：类型少列一个可选值时，使用方需 `as any` 才能传合法值。

**检查法**：

1. 找「被公开 SDK/类型包消费的闭合集合」：grep 是否存在**另一份发布物**声明同名类型；
   同名是机械配对的唯一线索（与 P11 同）。
2. 先确认两侧**消费域相同**（同一端点作用域、同一载荷），不同则立即放弃 diff。
3. 不变量优先取**单向子集**（`published ⊆ source`），不要取相等。
4. 用**生产者存在性**检验滞后项是否为真能力：grep 这些成员在源仓是否有实际发送点或处理分支。
5. 查权威义务（书面规则、CHANGELOG 里的同步记录），再查是否存在生成器或断言；
   注意 `apigen` 这类工具可能只覆盖同仓的**另一侧**产物——**「有生成器」不等于「覆盖本集合」**。
6. 比完成员名后**再比载荷字段**，否则修法会产出「说谎的类型」。

### P18 同一算子在多条实现路径上的量纲/格式漂移

**对应判据**：D1（同构分支逐项 diff 判定条件）、B（语义漂移），是 P11/P12 在**同一枚举的多个实现路径**上的特例。

**定义**：同一个语义标识（枚举值、算子名、i18n 键）在同一份代码里存在**两条以上实现路径**
（如「列底部计算」与「行级汇总」），各自算同一个指标。当某一条路径使用了不同的**量纲**
（0–1 比值 vs 0–100 整数）或不同的**格式化标记**（`NumberFormatPercent` vs `NumberFormatNone`）时，
同一个算子在不同位置给出不同的数字与单位。

**为何出现**：两条路径通常由不同时期、不同人实现（先做列计算，后加汇总列；或反之）。
后加的路径**复制了算子名**，但算式与格式是独立写的。因为**算子名相同**，任何按名字做的搜索都看不出差异；
又因为两条路径都要靠具体数据才显形，单测与人工验收都容易只覆盖其中一条。
**「同一个 switch 里的兄弟分支」是本模式最省力的入口**——百分比族的其他成员往往用的是正确量纲。

**与 P11/P12 的区别**：P11 是跨语言/跨包的两份**表**漂移；P12 是同一变换的多个**函数**漂移；
P18 的漂移发生在**同一个函数的相邻分支之间**，或同一功能的两条调用路径之间，范围更小、更易被忽略，
且**常常在同文件内就能找到权威侧**，无需跨仓比对。

**实证案例（本仓库，第 11 轮）**：数据库「汇总」列（rollup）的 `Percent checked` / `Percent unchecked`。

- 错误实现：`kernel/av/value.go:3167` / `:3179`（`(*ValueRollup).calcContents`），
  算式 `float64(countChecked*100/len(r.Contents))`（Go 整数除法，先截断再转 float）配 `NumberFormatNone`（赋值在 `:3177` / `:3189`）。
- 权威侧 1（同一 switch 的兄弟分支）：`kernel/av/value.go:2824`（Percent empty）、`:2834`（Percent not empty）、
  `:2846`（Percent unique values）全部是 `float64(x)/float64(len(r.Contents))` 配 `NumberFormatPercent`。
- 权威侧 2（同一算子的另一条路径）：`kernel/av/calc.go:1654-1679`（`calcFieldCheckbox`，列底部计算）
  用比值 + `NumberFormatPercent`；`calcFieldRollup`（`:1845-1882`）对其余 Percent 算子亦同。
- 格式化语义：`kernel/av/value.go:2247`（`formatNumber`）证明 `NumberFormatPercent` **本身会乘 100 并补 `%`**，
  `NumberFormatNone` 只输出裸数字 → 错误分支是「先乘 100 再不做百分号」。
- 业务表现：汇总列选「已完成占比」时，2/3 显示 `66`（应为 `66.67%`），1/200 显示 `0`（应为 `0.5%`）。
- 渲染链：`kernel/sql/av.go:816` → `BuildContents` → `calcContents`；
  前端 `app/src/protyle/render/av/attributeValue.ts:78`（`genAVRollupHTML` 的 `number` 分支）
  与 `cell.ts:1387` 直接输出 `number.formattedContent`，**没有任何地方补 `%`**。
- 可达性：`kernel/model/attribute_view_key_config.go:25` 的 `AttributeViewKeyRollupOperators` 含这两个算子；
  `app/src/protyle/render/av/calc.ts:169` 在目标字段类型为 `checkbox` 时**只**提供 `Checked`/`Unchecked`/`Percent checked`/`Percent unchecked`；
  `app/src/protyle/render/av/rollup.ts:255` 把 `dataset.colType` 设为目标字段类型 → 普通用户可点出该组合。

**其他领域的同类形态**（报告时可就近取证）：

1. **同一个统计量的「实时」与「离线/快照」两条计算路径**：一条用秒、一条用毫秒，界面不显示单位。
2. **同一个货币金额在「单价计算」与「订单汇总」里分/元混用**，两处都叫 `amount`。
3. **同一个比率在「明细行」与「报表汇总」里一个存 0–1 一个存 0–100**，且都标成「百分比」。

**检查法**：

1. 收集「算子/枚举名 → 全部实现点」：grep 枚举常量名（如 `CalcOperatorPercentChecked`）与
   其**字符串字面量**（如 `"Percent checked"`）在仓内的全部出现，看看是否有两条以上赋值/计算路径。
2. 对每条路径逐项 diff 三件事：**量纲**（是否 ×100）、**数值类型**（整数除法还是 float 除法）、
   **格式标记**（是否 `Percent`）。三者任一不同即候选。
3. 判定权威侧的顺序：同一 switch 内的兄弟分支 > 同一算子的其他计算路径 > 与该值消费方式匹配的格式化函数。
4. 确认渲染层是否会二次归一化（有无补 `%`、有无再乘 100）；**没有二次归一化才成立**。
5. 注意整数除法：`a*100/b` 在 Go/Java/C# 中先截断，`1/200` 得 `0`——这类反例无需任何单位约定即可判错，
   优先用它作为不变量。
6. 修复前检查**下游消费**：排序、数值筛选、嵌套汇总、导出都会读同一个字段，
   改量纲会同时改变筛选阈值语义，必须在报告中提示，不能写成「一行对齐」。

### P19 外部可达路径上缺 not-found 守卫，panic 被 recover 吞成 2xx

**对应判据**：D1d（同族方法只有一处缺前置守卫）、P2（分派返回值正确性）。

**定义**：同一文件里成对的方法族（`DeleteXxx`/`GetXxx`/`UpdateXxx`）大多在「目标不存在」时返回 not-found 错误并 `return`，
唯有个别成员把「查询结果」直接解引用。因为上游 HTTP 框架按**路径形态**（深度、前缀、扩展名）而非**存在性**分派，
该分支对**已认证的外部请求**可达；panic 被项目的 recover 中间件吞掉后，
**handler 未写状态码就 panic，`net/http` 在收尾时补 200**，于是「无法处理的请求」被报告为成功。

**为何出现**：这类方法族通常是同一天批量抄写的（本例两个函数引入时间相差半个月、结构逐字同构、连注释都留着复制粘贴的痕迹）。
`if value, loaded := m.LoadAndDelete(k); loaded { x = value }` 少了 `else`，**没有任何编译器或 linter 会报警**——
Go 不提示「可能为 nil」，项目若未开 nilness 分析就完全静默。
调用方一侧的误判则来自「框架会先校验资源存在」这一**隐含假设**：WebDAV/CardDAV 这类协议的分派是按 URL 深度算资源类型的，
与存在性正交，必须读上游源码才能确认。

**成立条件（三条同时满足才报告）**：

1. 同族方法存在**唯一的**缺守卫成员——一致性权威侧就在同文件内，**无需外部规范背书**；
2. 已确认**调用链上无存在性预检**（逐层读到上游分派函数，给出行号）；
3. 「不得 panic」有依据——这一条**只需类型安全/健壮性常识**，但**不要**把它包装成协议合规主张（见 `SKILL.md`「已知误报」）。

**实证案例（本仓库，第 12 轮）**：

- `kernel/model/carddav.go:398`（`LoadAndDelete` 无 `else`）→ `:411` `os.RemoveAll(addressBook.DirectoryPath)`；
  `kernel/model/caldav.go:331` → `:344` 逐字同构（`:343` 注释仍写着 `// remove address book directory`）。
- 同族正确实现：`DeleteAddress`（`carddav.go:289`，miss → `ErrorCardDavBookNotFound`）、`GetAddressBook`（`:335`）、
  `DeleteObject`（`caldav.go:232`）、`GetCalendar`（`:320`）；两个 not-found 常量已存在于 `carddav.go:93` / `caldav.go:81`，
  **删除路径是唯一未使用者**。
- 上游无预检：`go-webdav@v0.7.0/internal/server.go:92-97` 直接调 `h.Backend.Delete(r)`；
  `carddav/server.go:269-279` 的 `resourceTypeAtPath` 只按**路径深度**判定资源类型；SiYuan 包装 `carddav.go:747-758` 只做 `PathCleanWithSlash`。
- 实测（本机 3.8.4-alpha.8）：`DELETE /carddav/principals/main/contacts/<不存在的名字>` → **200 + 空 body**；
  日志 `E ... logging.go:237: PANIC RECOVERED: runtime error: invalid memory address or nil pointer dereference`，
  栈帧 `carddav.go:411` → `(*CardDavBackend).DeleteAddressBook` → `carddav/server.go:702`。
  捕获链：`serve.go:153` `model.Recover` → `session.go:516` → `logging.Recover`（只 `LogErrorf` 后吞掉，不写状态码）。
- 严重度：**低**。panic 发生在全部变更动作之前——`LoadAndDelete` 未命中、`booksMetaData` 未变更、`os.RemoveAll` 未执行，
  `defer c.lock.Unlock()` 正常执行，因此无数据损坏、无锁泄漏，危害仅为日志刷屏 + 状态码语义错误。
- 可达的现实链路：`load()`（`carddav.go:207-226`）只在元数据文件**不存在**时才重建 default 地址簿 →
  客户端删掉 default 成功后，本地缓存里仍有它，任何重发的 DELETE 都命中。
- 零副作用取证：这是**拒绝型**缺陷（预期失败），可在真实工作区直接实测，无需建临时对象再回删；
  唯一副产物是首次 DAV 访问会初始化 `data/storage/carddav/…`，属正常行为而非缺陷产物。

**其他领域的同类形态**：

1. **REST handler 在 `UPDATE ... WHERE id=?` 后直接读返回对象**：0 行受影响即 nil 解引用，
   而路由层的 `:id` 参数校验只查格式不查存在。
2. **gRPC/gateway 的 map 查询后直接取字段**：拦截器只做鉴权与限流，不做资源存在性校验。
3. **命令行工具的位置参数**：`flag.Args()[0]` 未判长度，而 shell 补全让人误以为参数总是存在。

**检查法**：

1. 对每个方法族（`Delete*`/`Get*`/`Update*`）grep 其 not-found 分支条数，找出**唯一没有**该分支的成员。
2. 逐层读调用链，确认上游是按**路径形态**还是**存在性**分派；报告中必须写明「框架不会兜住」的依据行号。
3. 追 panic 的最终表现：确认项目的 recover 中间件是否吞掉 panic 且不写状态码（`net/http` 会补 200）。
4. **严重度看「panic 之前的副作用」**：位于全部变更动作之前 → 无数据损坏，降级为「日志噪声 + 状态码语义错误」；
   若在部分写盘/部分删除之后，则升级为数据不一致。
5. 修法要给出**语义正确的返回**而非「照抄兄弟路径」：兄弟路径返回普通 error 时，经上游映射可能是 500，
   把「成功的幂等重试」变成服务端故障。优先选协议正确（上游导出的 `NewHTTPError(statusNotFound, …)`）或幂等 `return nil`；
   守卫必须放在**任何变更动作之前**，否则会把「已删除」报成失败，那才是真正的语义错误。

## 如何扩充本库

1. 从一次**已确认的缺陷**出发（而非猜测），确认它为何未被既有判据捕获。
2. 把技术一般化：审计者**本该问什么问题**？
3. 至少给出 3 个来自不同领域的实例，不要全都出自同一模块。
4. 说明可验证性：如何复现、如何取证。
5. 补充到本文，并在 `SKILL.md` 的判据清单里挂接。
6. 若新判据带来新误报，同步写入 `SKILL.md` 的「已知误报」。

目标是让判据库随缺陷发现持续累积，而不是每轮从零开始。

### P20 同族多实现里唯一一处读错 DOM 属性（值恒空）

**对应判据**：D1e、D1、C。

**定义**：同一语义（读搜索框、读标题、读排序值）在多处各有实现，其中唯一一处读取的属性在目标元素上**不存在**
（最典型是把 `contenteditable` 的 `div` 断言成 `HTMLInputElement` 再读 `.value`）。表达式求值为 `undefined`，
再用 `|| ""` 兜底，于是「读不到」被伪装成「没有值」：不报错、不抛异常，只表现为功能静默失效。

**为何出现**：`as SomeElement` 是编译期谎言（TS 不校验 DOM 实际标签），`|| ""` 兜底后连 `undefined` 都不再暴露。
同族其它实现读对了属性，缺陷只落在没被测试覆盖的那一处；共用的渲染函数还会让人误以为「同一控件必然同一读法」。

**实证案例（本仓库）**：`app/src/protyle/render/av/kanban/render.ts:95/:128` 读 `searchInputElement?.value || ""`；
搜索框由共享的 `genTabHeaderHTML`（`render.ts:165`）生成为 `<div contenteditable="plaintext-only" data-type="av-search">`，
表格（`render.ts:642`）、画廊（`gallery/render.ts:248`）、`bindAvSearch`（`search.ts:23`）等九处都读/写 `textContent`。
因 `render.ts:568-576` 按 `data-av-type` 分派到看板且不传 data，看板走自带取数分支 → `query` 恒空 → 搜索恒不过滤；
`locate.ts:251-252` 每次渲染把 `data-av-type` 改写成当前视图类型，关死了「恰好走表格分支」的侥幸路径。

**检查法**：
1. grep 同一变量名的**全部读取点**，按取值方式（`textContent` / `value` / `innerText`）分组，找少数派。
2. 读该元素的**生成 HTML**，确认该属性是否存在（`contenteditable` 的 div 没有 `value`）。
3. 确认**有无写入方**写该属性：没有 → 值恒空；有 → 只算取值时机问题，不要写成恒空。
4. 追分派依据：若上游按 DOM 属性分派到该实现，且该属性每次渲染都被规范化成当前状态，则缺陷稳定复现。
5. **不变量**：断言「该读取结果 == 同族其它实现的读取结果」，用真实 DOM 跑一次即可证伪。

**为何本项没有脚本（需要时再补）**：第 1 步看似可机械做，但变量名是文件局部的，
跨文件按名匹配会产生大量同名噪声；而真正有效的是「按取值方式分组后看少数派」，
那一步需要先知道有哪些读取点。当前用 grep 一次即成，脚本化收益低于维护成本。
若后续这一项反复出现，再考虑做「同一元素选择器 + 属性取值方式」的分组脚本。

### P21 手写配置登记表与实际声明漂移（宽松默认 + 无完整性测试）

**对应判据**：A、D3、P4、P15。

**定义**：一份手写的「可配置项登记表」（catalog／白名单／枚举）与实际的菜单、路由、字段声明逐项不一致：
登记表有而实际没有的键 → 设置面板出现**勾选/拖拽均无效**的条目；实际有而登记表没有的键 → 该条目**无法被配置**
（不能隐藏、不能排序）。因为运行时对未知键**宽松放行**（保留、不改动、不告警），两种不一致都不报错、不失败，
只表现为「配置看着生效了却没效果」或「个别项怎么都关不掉」。

**为何出现**：宽松默认是插件/动态内容的**架构必需**（未知 id 属外部注入，不能当异常处理），于是「漏登记」被降级为静默；
登记表又只被**有选择性的测试**覆盖（只对静态 markup 做全量 diff，不对动态拼装的菜单做扫描），漂移因此长期存活。

**实证案例（本仓库）**：`app/src/config/entryVisibility/catalog.ts` 对 `app/src/menus/protyle.ts`、
`app/src/protyle/gutter/index.ts`：
- 漏项：`transposeTable`（`protyle.ts:2433`，块标 - 单个块 - 表格）、`cancelMerged`（`:2286`）、
  `copyMirror`（`gutter/index.ts:3566`，数据库块的复制项）、`inline.image` 的 `openBy`（`protyle.ts:1520-1521`
  → `commonMenuItem.ts:1052-1061`；`inline.link`/`inline.ref` 都有，唯独图片没有，整棵子菜单因此不可配置）；
- 幽灵项：`inline.text.more` 下的 `separator_insert`／4 个 `insert*`／`separator_delete`／2 个 `delete*`
  （实际由 `tableMenu` push 进 `menus`，作为行内菜单的**顶层**项出现；`more` 子菜单只含
  `otherMenus.concat(other2Menus)`）、`gutter.multi.copy` 下的 `copyAVID`／`duplicateMirror`／`duplicateCompletely`
  （仅在单选 AV 分支生成）；
- 机制：`runtime.ts:316-338` 的 `filterMenuItems` 只在 `getEntryCatalogNode(path)` 存在时才隐藏；设置面板完全由 catalog 生成。

**检查法**：
1. 机械提取两套序列——登记表的 key 序列、实际声明的 `id` 序列（含条件分支与 `git log -S` 引入时间线），逐项 diff。
2. 对每个差异判定方向：**漏项**（无法配置）还是**幽灵项**（无效开关）——两者修法不同，修法都要落到等价位。
3. 检查运行时对未知键的策略（保留／隐藏／报错），宽松放行正是漏项静默的原因。
4. 找现有测试的覆盖边界：只断言「前 N 项」「某段切片」的测试等于放弃完整性，正是漂移的容身处。
5. 不变量取「登记表 key 集合 == 实际可渲染 id 集合（按条件分支取并集）」。

### P22 同源请求构造的复制品漏字段（跨端参数漂移）

**对应判据**：B、D1、P5。

**定义**：同一请求（同一端点、同一契约）在两端各有一份手写的参数构造，字段逐项同构，只差个别字段；而该字段在契约里是
`optional`、内核有默认值，于是缺失**不报错**，只让两端得到不同结果集。与 P12 的区别：漂移的不是字符串变换而是**请求载荷**；
与 P15 的区别：不是 DTO 丢字段，而是调用点漏传。

**为何出现**：optional 字段让「漏传」合法，内核默认值决定了漏传的行为；两份构造来自复制，复制时只带走当时已有的字段，
之后新增的**模式相关派生字段**只出现在被改动的那一份里。

**实证案例（本仓库）**：桌面 `app/src/search/util.ts:1520` 有 `searchHPath: !requestConfig.hasReplace`；
移动 `app/src/mobile/menu/search.ts:319-330` 的同构 `searchParam` 没有该字段；
`kernel/apicontract/search_query.go:58` 是 `*bool api:"optional"`，`kernel/api/search.go:335-337` 省略即 `true`。
同一提交 `fa44649fa7` 把 `FindReplaceInBox` 改为 `FullTextSearchBlockInBoxWithHPath(..., false)` ——
「普通搜索默认展开 HPath、替换目标永不展开」是配套的一对，`FindReplaceRequest` 里根本没有该字段。
后果：移动端替换模式的列表多出「仅命中层级路径」的行（对它们替换是 no-op）、匹配计数偏大。

**检查法**：
1. grep 同一端点的**全部**请求构造点，逐字段 diff（不只比字段个数，要比含 `?!` 的派生值）。
2. 查差异字段是否 `optional` + 内核默认值 → 判断缺失是否静默。
3. `git log -S <字段>` 找引入它的提交，看是否成对改了另一层（内核/另一端点），据此判断意图。
4. 判定影响时先厘清「前端列表」与「服务端实际作用的集合」——**别把展示差异写成数据差异**
   （挑战门实例：这一误判会把低危缺陷抬成高危，修法优先级随之失真）。
5. 修法优先「把派生逻辑收敛到共享装配函数」，而不是在缺失处再抄一遍同样条件（否则制造第三个真相点）。

### P23 有界集合的容量裁剪端与消费端相反

**对应判据**：D4、D1。

**定义**：为有界集合（撤销栈、历史栈、已关闭页签栈）实现容量上限时，**消费端**与**裁剪端**取的不是同一端。
典型的栈语义是「尾部 = 最新」，消费用 `pop()`；裁剪却也在 `pop()` 尾部，于是丢弃的是「次新」而非「最旧」，
并把最旧的条目永久保留。用户的体感是「最近使用」类功能第二次起跳序、中间若干条永远找不回。

**为何出现**：裁剪常被写成「先腾位再入栈」，位置放在 `push` 之前（这还会让稳态长度比常量多 1），
而 `pop`/`shift` 的选择是顺手为之——两者叠加后，`>` + `pop` + 前置的判断看起来「像是配额控制」，实际方向全反。

**实证案例（本仓库）**：`app/src/layout/Wnd.ts:951-960` 维护 `LOCAL_CLOSED_TABS`（快捷键「最近关闭」）。
- 消费端 `app/src/boot/globalEvent/command/global.ts:173` 用 `pop()` 取「最近关闭」；
- 与 `push` 同处的裁剪用 `pop()` 且写在 `push` **之前**（`if (length > Constants.SIZE_UNDO /* 64 */) pop();`），
  因此稳态长度是 65，且每次关闭都会挤掉「上一次关闭」那条；
- 同族权威侧：`app/src/protyle/undo/index.ts:221-225`（`push` 后 `if (length > SIZE_UNDO) shift()`）、
  `app/src/util/backForward.ts:362-368`（`backStack` 同）；
- 业务表现：累计关闭超过 64 个页签后，第一次 ⇧⌘T 正确，第二次起跳过被挤掉的条目、直接恢复到很久以前关闭的页签。
- 可验证：连续关闭 66 个页签后连续 `pop()` 两次，应得到第 66、65 条，实际得到第 66 条与最旧那条。

**检查法**：
1. grep 同一数组/集合的 `push`、`pop`、`shift`、`unshift`、`splice` 全部出现点，列出写入端、消费端、裁剪端。
2. 判定「最新」在哪一端（看消费端的取值方式），再确认裁剪端是否同端。
3. 检查裁剪相对写入的先后：写在 `push` 之前 + `>` 判断 → 稳态长度 off-by-one（容量常量 + 1）。
4. 权威侧优先取同族实现（撤销栈、前进后退栈、搜索历史）的同类裁剪。
5. 不变量：连续写入 N（N > 容量）次后连续读取两次，应得到第 N、N-1 条。

### P24 同一行内同一表达式重复出现（漏改下标）

**对应判据**：D1f、D1。

**定义**：手写展开的循环或序列拼接里，同一表达式被写了两遍，第二处本应改为下一项/下一个下标，
于是「第一项被处理两次、第二项零次」。类型系统与编译期都无法发现；运行时不报错，只表现为某一组配置不生效。

**为何出现**：复制粘贴后忘记改下标，或从「单元素写法」扩写为「多元素写法」时只改了选择器没改索引。
仓库里通常还有成对的正确写法（`[0]`+`[1]`），因此**同文件惯例就是权威侧**。

**实证案例（本仓库）**：`app/src/layout/dock/index.ts:308`（浮动拖拽 `onmouseup`）
```
[...this.elements[0].querySelectorAll(".dock__item--active"), ...this.elements[0].querySelectorAll(".dock__item--active")]
```
第二个 `elements[0]` 应为 `elements[1]`（停靠栏下半组）。同文件 `setSize()`(`:1123-1124`)、`getMaxSize()`(`:1152`)、
`:98-99`、`:572`、`:601-607`、`:722-723` 等 9 处以上都是成对遍历；`this.elements[1]` 恒存在（左/右 3 项、底部 2 项），
不存在「防御性跳过」的解释。后果：下半组中实现了 `resize` 回调的**插件**停靠面板收不到尺寸变化通知，
上半组被调用两次。已构建产物中 8 个历史 bundle 都是同一写法（长期未被发现）。

**检查法**：
1. 机械扫描：同一行内同一复杂表达式（`xxx[0]`、相同 `querySelector*` 选择器）出现 ≥2 次。
2. 确认被跳过的下标是否恒存在——若可能不存在，则可能是防御性写法，需降级。
3. 找同文件/同族的成对惯例作为权威侧。
4. 副作用要逐项说清（谁没被处理、谁被重复处理），并确认是否有其它机制兜底
   （本例 `resizeTabs()` 会全量兜底，但拖动路径不调用它）。

**兄弟陷阱**：`arr.splice(arr.indexOf(x), 1)` 在 `indexOf` 未命中时返回 -1，`splice(-1, 1)` 会删掉**最后一个**元素。
先确认可达性（渲染与数组是否严格同源），再决定上报或列观察项。

### P25 同类宿主页面的配置不对称（共用脚本在个别页面失效）

**对应判据**：D1g、E2、D1。

**定义**：一组结构相同的宿主页面/窗口由同一份模板或构造函数创建，其中个别页面缺少同类页面普遍设置的选项
（Electron `webPreferences` 的 `nodeIntegration`/`preload`、CSP、权限、注入脚本），而被**多个页面共用**的脚本
依赖该能力。脚本在该页面抛异常并终止，后续代码（按钮、事件绑定）全部不执行；异常只出现在 DevTools，用户看不到。

**为何出现**：宿主配置散落在多处构造函数里，新增页面时照抄不完整；共用脚本作者只验证了主页面。
**本地默认路径往往侥幸可用**（例如脚本里有一个「非某页面则提前 return」的分支），只有远端/特殊路径才走到失败代码，
因此长期不被发现。

**实证案例（本仓库）**：`app/electron/boot.html:562` 引用的 `app/electron/connectionEntry.js` 被三个页面共用，
该脚本 `:1-6` 在 boot 页且带 `remote` 参数时执行 `require("electron")`；而 `app/electron/main.js:2368-2370`
的 `createBootWindow` 的 `webPreferences` **只有** `webSecurity: false`，同文件另外 8 处页面窗口都写了
`nodeIntegration: true`（`1949`/`2058-2064`/`3527-3528`/`3605-3608`/`3908`/`3948`/`3999`）。
Electron 44 下 `nodeIntegration` 默认 false、`sandbox` 默认 true → `require` 不存在，按钮永远不渲染。
设计意图的三处证据互为印证：`main.js:2774` 的 `localPages` 只在远端模式把 `boot.html` 列入授权名单、
`main.js:2781-2782` 收到 IPC 后 `remoteBootCanceled = true; bootWindow.destroy()`、脚本自己为 boot 页写了 remote 分支。

**检查法**：
1. 机械提取同类配置块（同一构造函数族的 `webPreferences`/`preload`/CSP），逐项 diff **成员集合**而不是值。
2. grep 共用脚本的 `require`/`import`/全局依赖，确认它在每个页面都成立。
3. 找「提前 return」类分支，判断是否恰好掩盖了本地路径、只在另一条路径暴露。
4. 找宿主侧为该功能准备的配套代码（授权名单、取消/清理分支）——「配套齐全但入口失效」是强证据。
5. 影响面要写清触发路径，并核实是否有兜底（超时、自动回退、强制退出）。

### P26 临时展现态缺少跨重渲载体

**对应判据**：C、D2。

**定义**：为满足一次性导航而临时改变的展现状态（掀开被折叠的分组、展开面板、临时高亮）只写在 DOM 上，
没有前端状态载体。触发重渲（事务推送、去抖刷新、切换视图）后即丢失，用户正在进行的操作被中断。
与 P8「渲染重建时的状态丢失」的区别：这里**不写回持久化数据是正确的**（不污染用户偏好、不跨端扩散），
缺的是**前端临时载体**；因此修法不能是「把状态写回数据」。

**为何出现**：导航请求被建模成「消费一次即释放」的事件（`finish*` 里无条件清理），于是「请求」消失时，
它带来的展现副作用无人接管。测试通常只覆盖「首次渲染包含目标」，不覆盖「第二次渲染仍包含」，形成盲区。

**实证案例（本仓库）**：数据库分组表格定位到折叠分组内的条目。
- `app/src/protyle/render/av/locate.ts:368-370` 只 `classList.remove("fn__none")` 并加箭头类，不写 `groupFolded`；
- `render.ts:313-329` 的 `renderBody`/`fn__none` 完全由 `group.groupFolded` 决定；
- `finishAVLocate`（`locate.ts:437`）结尾无条件 `clearAVLocateRequest`，请求随即销毁；
- 触发路径：任意 AV **数据**操作（改单元格、加行、改列、切筛选）→ `refreshAV` → 去抖 100ms → `avRender` 重新
  `fetchSyncPost("/api/av/renderAttributeView")` → 因为内核不因定位修改 `GroupFolded`（`attribute_view_render.go:668-710`），
  分组被重新折叠，目标行连同正在编辑的光标一起从 DOM 消失；
- 权威侧：把状态写回 `groupFolded` 是**错的**（该字段随 AV 持久化并跨端同步，且不在 ⌥折叠的 undo 基线内）；
  正确方向是保留一个前端临时载体（不清理定位请求，或维护「临时展开集合」），并叠加用户主动折叠时的清理与 TTL。
- 现状证据：`data-av-locate-window`、`virtualData[].locate`、`groupTableVirtual.test.ts` 都在支撑「本次渲染内展开」，
  但**没有**任何测试覆盖「定位后再次渲染仍展开」。

**检查法**：
1. 找「临时改变展现」的位置，问：这个变化有无载体（前端状态 / 请求对象）？下一次重建从哪读值？
2. 找 `finish*`/`clear*`/`reset*` 是否无条件清理掉了承载该展现的对象。
3. 确认「写回持久化数据」是否可行——若该数据会跨端同步、参与服务端渲染或影响用户偏好，则不可行，
   必须采用前端临时载体；否则修法会从「体验缺陷」升级为「数据污染」。
4. 补测试时同时断言「重渲后仍保留」与「用户主动取消后不再保留」。

### P27 前端设置项有键、内核持久化结构无字段（静默无效的开关）

**对应判据**：D3c、A、P15。

**定义**：新增设置项时只改了前端（对话框、类型声明、消费点），**内核持久化 struct 与其镜像 DTO 未同步**。
因解码走标准 `encoding/json` 且无 `DisallowUnknownFields`，多出来的键被静默丢弃；内核随后用少键版本
覆盖前端 config，开关永远回到默认值。用户看到的是「设置项存在、可点、但完全不生效」——不是报错，也不是数据丢失，
比 P15 更难被发现（P15 至少表现为数据消失）。

**为何出现**：P15 是「抄写后冻结」，本模式是**方向反过来**：新字段先在前端落地（因为要在 UI 上先看得见），
内核结构与其镜像 DTO（`apicontract` + `schema.json` + 生成的前端类型）三处都等着后续补，然后被遗忘。
镜像 DTO 的存在会让「内核结构有 6 个键」看起来像「契约就是这样」，从而掩盖缺失。

**附带症状（很有辨识度）**：若前端用对象深比较做保存守门（如 `objEquals` 先比 `Object.keys` 长度），
「对话框 N+1 键 vs 配置 N 键」让守门**恒不成立** → 每次关闭面板都触发一次全命名空间写 + 广播，
即使用户什么都没改。看到「某面板每次关闭都写一次配置」时，先查键数是否对齐。

**实证案例（本仓库）**：设置 - 外观 - 通知 的「全选不完整提示」开关。
- 前端 `app/src/config/tabs/appearanceTab.ts:1149-1160` 的 `NOTIFICATIONS_ITEMS` 有 7 项，`readNotificationsFromDialog`（`:1177-1188`）读 7 键；
- 内核 `kernel/util/appearance.go:63-70` 的 `Notifications` 只有 6 字段（无 `SelectAllIncompleteTip`）；
  镜像 `kernel/apicontract/bazaar.go:360-368` 的 `BazaarNotifications`、`schema.json`、生成物同样 6 字段；全内核 grep 零命中；
- `kernel/api/setting.go:744` 解码无 `DisallowUnknownFields` → 静默丢弃；`:759` 覆盖 `model.Conf.Appearance`；`:775` 广播；
- `app/src/index.ts:91` 的 WS 分支 `appearanceConfigApi.apply` → `applyAppearanceConfig`（`appearanceRuntime.ts:86`）整对象覆盖；
- 消费点 `app/src/protyle/wysiwyg/keydown.ts:229-234` 判断 `=== false`，永远为假 → 该提示**无法关闭**，
  且它没有兄弟项 `selectAllTip` 那样的「不再提醒」按钮，坏开关是唯一入口；
- 附带：`app/src/util/functions.ts:98-106` 的 `objEquals` 先比键数 → 每次关闭对话框都写一次 `setAppearance`；
- 同文件 `mountAppearanceSetStatusBar` 用同一守门且能命中，证明守门本身没问题，是键数不齐。

**检查法**：
1. grep 前端设置项字段名在「内核 struct / 镜像 DTO / schema / 生成物」四处的出现次数，缺即为漏项。
2. 确认解码是否严格（无 `DisallowUnknownFields` → 静默）。
3. 找消费点，确认它读的是「内核持久化配置」而不是前端本地状态（若是本地，则可能是有意设计）。
4. 反证：该字段是否由 localStorage / 其它通道持久化？逐条排除后再定性。
5. 不变量：前端读写路径涉及的键集合 ⊆ 内核 struct 的 `json` 键集合（Go 侧反射枚举 tag 做防漂移测试）。
6. 修法注意：新增字段若用于「默认启用」的开关，**必须用 `*bool` + `omitempty`**——老配置里该对象非 nil，
   整体补默认值不会触发，用 `bool` 会把存量用户反序列化成 `false`，造成反向行为变更。

### P28 词法路径校验在符号链接面前失效（叶子 vs 中间组件）

**对应判据**：D1h、E3、D1。

**定义**：路径守卫用纯词法运算（`filepath.Clean` + `IsSubPath`、`strings.HasPrefix(rel, "..")`）判断「是否在本目录内」，
不解析真实路径。同族其它实现都额外做了 `EvalSymlinks` 双侧校验、逐级 `Lstat` 拒绝 `ModeSymlink`、或改用 `os.Root`，
唯独这一处（往往还是**唯一做破坏性操作**的那一处）只做词法校验。

**关键区分（第一轮审查容易在这里失手）**：
- **叶子是软链**：`unlink` 只删链接本身，`os.RemoveAll` 不会递归进目标 → 影响有限；
- **中间组件是软链**：`unlink` 由内核解析全部前导组件，只对最后一段不 follow；`RemoveAll` 失败后
  `OpenFile(parentDir)` 打开的是**链接目标**（该调用**没有 `O_NOFOLLOW`**，对比 `os.Root` 的 `openDirAt` 带 `O_NOFOLLOW`）
  → 目录场景是**递归删除目录外的整棵树**。

**实证案例（本仓库）**：`kernel/model/template.go:106-121` 的 `RemoveTemplate` 只做 `Clean` + `IsSubPath`，
注释却写「防止任意文件被删除」。同族四处都做了软链防护：
`kernel/api/template.go:159-176` `isPathInTemplatesDir`（`EvalSymlinks` 双侧 + 注释明确写「防止通过符号链接指向模板目录外的敏感文件」）、
`kernel/model/template.go:1221-1245` `resolveDocContentTemplatePath`、
`kernel/model/template_manage.go:98-115` `checkTemplateFilePath`（逐级 `Lstat` 拒绝 `ModeSymlink`）+ `:309-316` 用 `os.Root`、
`kernel/model/template_doc_tree.go:405-434` `resolveTemplatePackageFile`；后三处都有软链测试，唯独 `RemoveTemplate` 没有。
触发形态：`templates/link -> ..`（或任一目录外路径），`RemoveTemplate("link/conf")` 会递归删除 `<data>/conf`。
附带同族缺口：`kernel/mcp/tools/template.go` 的 `resolveTemplatePath` 同样只做词法校验，读取路径也越界。

**检查法**：
1. grep 路径守卫的实现，按「词法 / realpath / `os.Root` / 逐级 Lstat」分组，找少数派与唯一做破坏性操作的那个。
2. **分别构造「叶子软链」与「中间组件软链」两种输入**，确认 `Remove*`/`Read*`/`Write*` 的实际行为；
   不要只验证叶子就下结论。
3. 找同族测试：若其它实现都有软链回归测试而此处没有，是强信号。
4. 注意同族不同实现的**口径**可能互不一致（`HasPrefix(rel, "..")` 会把名为 `..foo` 的合法子目录误判为越界），
   修复应先把解析收敛到单一函数，而不是逐处打补丁。

### P29 异步队列吞掉落盘错误使调用方假成功

**对应判据**：D1i、P1、G2。

**定义**：写入走「入队 + 只等队列排空」（`PerformTransactions` + `FlushTxQueue`）时，提交失败只在内部记日志并推送错误提示，
**函数仍返回成功**。调用方据此判断「已落盘」并继续做破坏性动作（删除源文件、清理临时物、标记完成），
一个可重试的失败就升级为**静默数据丢失**。

**为何出现**：异步队列的接口设计成「排空即返回」，没有把单笔提交的结果回传给调用方；
调用方（尤其是 CLI/MCP/批处理入口）只需要一个 `error`，于是拿到了无意义的 nil。

**实证案例（本仓库）**：`model.CreateDocByMd` → `createDoc0` → `performCreateDocTransaction`
（`kernel/model/file.go:2422-2430`）入队后只 `FlushTxQueue()`；落盘失败经 `kernel/model/transaction.go:120`/`:488`
的 `logging.LogErrorf` + `util.PushTxErr` 上报（弹界面提示），`CreateDocByMd` 仍返回 `tree, nil`。
`kernel/mcp/tools/inbox.go:208` 的 `inbox convert` 因此会在「本地 `.sy` 从未落盘」的情况下记为成功，
并在默认 `remove_after=true` 下**删除云端原件**。

**检查法**：
1. grep 异步事务的排空函数，确认其签名与实现是否传播错误。
2. 列出所有「基于返回 nil 推断落盘成功」的调用方，重点看其中是否有破坏性后续动作。
3. 与同族的同步写入路径对比（同步路径通常会返回真实错误）。
4. 修法优先级：先让调用方能拿到真实结果（或失败时不执行破坏性后续动作），再考虑其它。



### P30 同族路径上「前置守卫」的位置漂移

**对应判据**：D1j、D1、C。

**定义**：同一份守卫（忽略规则、空值检查、存在性检查、只读检查）在两条同族执行路径上位于**不同位置**：一条在副作用之前（被拒即完整 no-op），
另一条在副作用之后（被拒时副作用已发生）。表现是「同一个声明被拒绝的操作，在一条路径上什么都没做，在另一条路径上做了一半」。

**为何出现**：守卫被放在**共享函数**的开头（合理的单一闸门），而某个调用方在调用共享函数之前就有自己的副作用（删除旧行、清缓存、写临时物）。
共享函数的守卫只保护「插入/写入」这一步，不保护调用方的删除步骤。

**实证案例（本仓库）**：`kernel/sql/upsert.go` 的 `upsertTree`（:445-499）先无条件 `deleteSpansByRootID`/`deleteAttributesByRootID`/`deleteAssetsByRootID`/`deleteRefsByPathTx`/`deleteFileAnnotationRefsByPathTx`，
再调 `insertTree0`（:501-510），而 `insertTree0` 的**第一句**才是 `indexignore` 判断，命中即 `return`。
同族的 `indexTree`（:438-443）没有任何前置删除，因此它的忽略早退是干净的 no-op。→ 命中忽略规则的文档在增量保存路径上「删了不插」。

- 可达条件：文档已被索引 + 之后 indexignore 才生效（`IndexIgnoreCached` 是进程级一次性缓存，只在 `fullReindex` 重置；重启时 `InitBoxes` 因 `treenode.CountBlocks() > 0` 不做全量索引）+ 编辑该文档。
- 部分自愈：`IndexRefs`/`upsertRefs` 不看忽略规则，重建时会把 refs 写回 → 只有 `spans`/`attributes` 的丢失是持久的。
- 严重度低：只碰派生库，重建索引一步恢复；且用户按指南「改配置后手动重建索引」操作时不会遇到。

**检查法**：

1. 找到共享守卫函数，确认守卫在函数体内的**第几句**。
2. 列出全部调用方，逐个确认「调用共享函数之前是否有副作用」。
3. 与同族另一条路径对比副作用集合（本轮的权威侧是 `indexTree` 的「无副作用」）。
4. 修法方向：把守卫前移到调用方入口，**不要**反向补齐副作用（会让两条路径更强地不一致，且永远到不了自洽状态）。

### P31 模板条件隐藏集合 ⊋ 运行时恢复集合

**对应判据**：D1k、C、D1e。

**定义**：模板按同一条件给一批同层元素加 `fn__none`；运行时某状态函数把其中一部分隐藏（还常顺手隐藏其相邻兄弟），
而恢复函数只恢复自己语义关心的那部分，`模板隐藏集合 \ 恢复集合` 里的元素永久保持隐藏。用户看到的是「功能入口消失、但主内容正常」。

**为何出现**：隐藏是**一次性状态切换**（按当时的空/非空判断），恢复是**按需最小恢复**（谁隐藏谁恢复）；两侧的集合没有共同的载体，
因此模板新增的隐藏条件、或隐藏时顺手加的相邻元素，都不会被恢复逻辑覆盖。

**实证案例（本仓库）**：`app/src/card/openCard.ts`

- `:100` 模板对 `[data-type="more"]` 按 `cards.length === 0` 加 `fn__none`；
- `allDone`（:911-922）隐藏 `more` 及其 `previousElementSibling`；
- `nextCard`（:888-910）只恢复 `card__block`（模板 `:111` 同样有初始 `fn__none`）与 `count`，**漏了 `more`** → 同函数内「恢复了同批的一个、漏了另一个」即强信号。
- 跨端连带：`previousElementSibling` 在桌面是 `<div class="fn__space">`、移动端是 `[data-type="filter"]` 按钮（`:81-82`）→ 移动端连带隐藏筛选，反而使「切换卡包」这条恢复路径自身不可达。
- 严重度低：关掉对话框重开即恢复；`重置`/`移除卡片` 有替代入口（`app/src/card/viewCards.ts`），`设置到期时间` 没有。

**检查法**：

1. 提取模板中所有条件 `fn__none`（集合 A）。
2. 提取每个恢复函数的 `classList.remove("fn__none")` 目标（集合 B）。
3. `A \ B` 即候选；再确认每个候选是否真的需要被恢复（无卡状态下 ⋮ 菜单确实打不开，此时隐藏是正确的）。
4. `previousElementSibling`/`nextElementSibling` 一律按「跨端语义可能不同」处理，先 grep `/// #if` 双模板。
5. 修复时用稳定选择器（`data-type`/`data-id`）替代位置选择器，并按端区分。

### P32 同族复制粘贴读错绑定对象

**对应判据**：D1l、D1f、D1。

**定义**：同族函数结构相同，但其中一处把**容器对象**绑成局部变量后又按数组用。典型形态：
`const list = storage[KEY]`（对象）之后写 `list.length === 1 && list[0] === value`，而正确的子数组在 `list.replaceKeys` 上。
`list.length` 恒为 `undefined`，该子条件恒为 false。

**与 D1f 的区别**：D1f 是「同一行内同一表达式写两遍」（复制后漏改下标）；本模式是「跨行复制后漏改**绑定对象**」，
机械信号不是「重复」而是「对已知为对象的值读 `.length`/`[0]`」。

**实证案例（本仓库）**：`app/src/search/toggleHistory.ts:14-18` 的 `toggleReplaceHistory`。
storage 键 `local-searchkeys` 的默认值（`app/src/protyle/util/compatibility.ts:691`）是对象 `{keys, replaceKeys, col, row, layout, colTab, rowTab, layoutTab}`，
清洗逻辑 `Object.assign(defaultStorage[key], parseData)` 也保证结果仍是对象。对照同族 `toggleAssetHistory`（:161-166）先取 `keys` 数组再判 `length`/`[0]`。

- 定性注意：恒假的是**第三个子条件**，前两个（`!list.replaceKeys || list.replaceKeys.length === 0`）仍然生效。
  因此报告必须写「守卫被削弱为只判空」，不能写「守卫等于不存在」——后者会被挑战门以「描述失准」降级。
- 业务表现：替换一次「foo」后（`replaceKeys === ["foo"]` 且输入框仍为 `foo`），点历史图标会弹出只剩「清除历史」一项的菜单；`toggleAssetHistory` 同条件下不弹。纯 UI 冗余，无数据损害。
- 修法：条件改为 `list.replaceKeys.length === 1 && list.replaceKeys[0] === ...`，与 `:164` 对齐。

### P34 免鉴权静态出口的符号链接越界（含修法陷阱）

**对应判据**：D1h、D1g、E2、F。

**定义**：静态资源出口用**纯词法**路径校验（`filepath.Clean` + `IsSubPath`）后交给 `http.ServeFile`/`c.File`，
而该出口所属前缀在鉴权 `CheckAuth` 里被**直接豁免**。于是「外观/资源目录下存在符号链接」时，
匿名请求即可读到链接目标——通常是被伺服根目录的兄弟或上级（例如 `conf.json`、TLS 私钥）。

**为何出现**：这类加固通常是**逐路由迁移**的（同族已有若干出口做了 `EvalSymlinks` 复核 + 敏感路径拒绝 + regular-file 判定，
并配了软链回归测试），迁移时漏掉一个；而鉴权豁免清单更早写成、按前缀匹配，两者叠加才构成完整攻击链。
**单看任一半都不足以定级**，必须交叉。

**实证案例（本仓库）**：
- `kernel/server/serve.go:742-747` 的 `/appearance/*filepath` 只做词法 `IsSubPath`，末尾 `c.File`（`:806`）→
  `http.ServeFile` 跟随符号链接；`util.AppearancePath = <workspace>/conf/appearance`（`kernel/util/working.go:111`+`:353`），
  与 `conf.json` 同目录，相对路径 `../conf.json` 即可命中。
- 豁免：`kernel/model/session.go:276-281` 对 `/appearance/` 前缀 `c.Next()`，不校验锁屏密码、**连 Origin/Sec-Fetch-Site 检查也跳过**；
  `corsMiddleware` 无条件 `Access-Control-Allow-Origin: *`，匿名跨站 `fetch` 可读响应体。
- 目标价值：`conf/conf.json` 含 `accessAuthCode`、`cookieKey`（会话签名密钥）、`api.token`、`secrets`（`kernel/model/conf.go:60-95`）。
- 同族权威侧：`serveStaticFile`（`serve.go:604-661`）双向 `EvalSymlinks` + 再次 `IsSubPath` + 敏感路径拒绝 + `IsRegular()`，
  且有 `serve_static_test.go:142/170` 两个软链回归测试；`ensureBootAppearancePathHasNoSymlink`（`kernel/model/boot_appearance.go:647`）
  逐段 `Lstat`；共四处静态出口都调用了敏感路径判定。
- 第二条泄漏路径（同一 handler）：`langs/*.json` 分支用 `os.ReadFile` 读取后把内容当语言包解析并**回吐 JSON**，
  不经 `c.File`；`langs/x.json -> ../../conf.json` 同样泄漏，说明加固点必须在所有分支之前统一做。

**检查法**：
1. 先列鉴权豁免清单（`HasPrefix(RequestURI, ...)` 白名单），标记其中含静态资源前缀的项。
2. 对这些前缀下的每个出口，检查是否做了「解析真实路径 → 再次包含判定」；词法版即为候选。
3. 构造两种输入分别验证：**中间组件是软链**（`themes/x/link -> ../..`，再请求 `link/conf.json`）与叶子是软链。
4. 确认最终消费点（`ServeFile`/`ReadFile`/模板合并）是否跟随软链。
5. 修法两项约束（**容易把修复做成事故**）：
   - 不要复用「按前缀判定」的敏感目录黑名单——被伺服的资源根常位于该前缀之下，会 403 掉全部合法资源；
   - 不要一律禁止符号链接——仓库可能**有意支持**「包目录本身是软链」（主题/图标开发目录外置），
     正确语义是「解析后要求目标落在允许根内，并允许包目录这一层是软链」。
6. 修复必须覆盖同 handler 的所有读文件分支，并补两条回归：包目录软链应 200、包内越界软链应 403。

### P35 CLI/脚本入口的假成功（异步与无返回值）

**对应判据**：D1m、P1、G。

**定义**：命令行入口把动作交给**异步入队**或调用**无返回值**的函数，失败只经 WebSocket 推送上报。
CLI 进程没有 WS 接收方，于是错误被静默吞掉，命令照样打印「结果」并以退出码 0 结束。脚本据此判断成功会得到假阳性。

**为何出现**：内核的写入路径以「编辑器在线」为前提设计错误通道（`util.PushErrMsg`/`PushTxErr` → WS 广播 → 前端弹提示），
CLI 复用同一 model 函数时没有把错误改走返回值。同族的其它子命令若已返回 error，就成了对照证据。

**实证案例（本仓库）**：
- `kernel/cli/cmd/block.go:373-403` `block delete`：`PerformTransactions` + `FlushTxQueue`（只等待不返回结果），
  错误经 `kernel/model/transaction.go:130-160` 的 `flushTx` → `util.PushTxErr` 只做 WS 广播；命令仍 `fmt.Println(id)` 退出 0。
  对照：同文件 `validateBlockMove`（`:448`）与 `block update` 做存在性校验；HTTP 侧 `PerformBlockOperation` 对 delete
  明确校验「外部删除请求必须命中现存节点」（`kernel/model/block_operation.go:39-46`）。
- `kernel/cli/cmd/repo.go:151-170` `repo checkout`：`CheckoutRepoDirect` 无返回值，失败分支只 `util.PushErrMsg`，命令无条件打印 `ok`。
- 变体 A（dry-run 被吞）：`kernel/cli/cmd/export.go:34-52/62-79/92-105` 的 `if dryRun && output != ""`，
  省略 `--output` 时 dry-run 失效并真的执行导出；同文件 `export docx` 无条件处理 dry-run。
- 变体 B（空结果截断文件）：同一处 `os.WriteFile(output, []byte(content), 0644)`，而 `model.ExportMarkdownContent`
  对不存在的块返回空串且不返回 error（`kernel/model/export.go:3109-3132`）→ 目标文件被 `O_TRUNC` 清空为 0 字节，仍退出 0。
  同族守卫：`materializeExportArtifact`（`export.go:224-231`）对空产物返回 `export failed: empty artifact path`。

**检查法**：
1. 逐个 CLI 子命令，看它调用的 model 函数**是否有返回值**；无返回值且错误走 WS 的即为候选。
2. 找同文件 / HTTP 侧的同语义实现作为权威侧，比较错误语义与退出码。
3. 检查 dry-run 条件是否被绑在「某个可选参数非空」上。
4. 检查「空结果 → 写文件」的组合（`os.WriteFile` 默认 `O_TRUNC`）。
5. 不变量：失败时退出码非 0，且不受影响的文件内容保持原样。

### P36 库默认白名单被选项整体覆盖

**对应判据**：D3、A。

**定义**：调用第三方库时用「设置项」传入一份自建列表，而该设置项在库实现里是**赋值**（替换默认值）而非追加，
于是库自带的安全/性能默认项被静默移除。症状是「作者明显有意排除某类输入，却漏了另一类同类输入」。

**为何出现**：库的选项命名（`WithExcludedXxx`）不体现「替换 vs 追加」，默认值又定义在库内部；
调用方只按自己的清单写，不会去读库源码。**判据是「库内默认集合」与「调用方集合」的差集**，不是调用方集合本身。

**实证案例（本仓库）**：`kernel/server/serve.go:316-322` 的 `gzipMiddleware`：
```go
gzip.Gzip(gzip.DefaultCompression,
    gzip.WithExcludedExtensions([]string{".pdf", ".mp3", ..., ".gz"}),
    gzip.WithExcludedPathsRegexs([]string{`(?i)\.hei[cf]$`}))
```
`gin-contrib/gzip` v1.2.3 的 `options.go:18` 定义 `DefaultExcludedExtentions = {".png",".gif",".jpeg",".jpg"}`
（注释即「图片已压缩，不值得再压缩」），`handler.go:34` 用它初始化，而 `options.go:55-57` 的 `WithExcludedExtensions`
直接赋值 → 四个图片扩展名被整体替换掉。同版本 `shouldCompress` 只判 `Accept-Encoding`/`Connection`/扩展名/排除正则，
**不看 Content-Type**，因此所有图片都进入压缩分支，白付 CPU 且体积可能膨胀。
作者已为 `.gz` 与 HEIF 做了排除，说明设计意图正是「已压缩载荷不压缩」，图片属同类漏项。

**检查法**：
1. 对每个「传入列表」的库选项，读库源码确认是赋值还是追加，并记录库内默认集合。
2. 求「库默认 − 调用方」的差集，逐个判定是否属于同类漏项。
3. 用 `Accept-Encoding` 实测响应头（`Content-Encoding`）验证，而不只看代码。
4. 修法优先「在调用方列表里补回默认项」，或在库支持时改用追加形态；同时补一条覆盖默认项的断言。

### P37 谓词通配符未转义（LIKE 语义被用户输入改变）

**对应判据**：E3、E4、P6。

**定义**：把用户关键词拼进 SQL `LIKE '%...%'` 时只转义了引号（防注入），未转义 `%` 与 `_`。
于是用户输入会**改变过滤语义**：`%` 匹配全部、`_` 匹配任意单字符，表现为「搜索框输什么都没过滤」。

**为何出现**：注入防护（转义引号）与通配符转义是两个不同的关注点，前者显式、后者隐含；
同包通常已有 `escapeLikePattern` 之类的工具，但只在部分调用点使用，形成漂移。

**实证案例（本仓库）**：`kernel/model/graph.go:695-702` 拼 `content LIKE '%part%'` 时只做
`strings.ReplaceAll(part, "'", "''")`，并调用 `kernel/conf/search.go:135-146` 的 `NAMFilter`
（同样直接拼 `name/alias/memo LIKE '%keyword%'`）。输入 `_` 生成 `LIKE '%%_%%'` 命中几乎所有块，图不过滤。
权威侧：`kernel/sql/span.go:28-38` 的 `escapeLikePattern` 转义 `%`/`_`/`\`，同包其它 LIKE 查询都遵守它。

**检查法**：
1. grep 所有 `LIKE` 拼接点，按「是否调用通配符转义」分组，找少数派。
2. 确认拼接值来自用户输入（而非内部常量）。
3. 实测：关键词传 `%` 与 `_`，断言不匹配无关行。
4. 修法注意跨包依赖方向——转义 helper 若在 `kernel/sql`，而拼接点在 `kernel/conf`，需避免循环依赖
   （上提至 `kernel/util` 或就地实现等价函数）。

### P38 适配层规范化标记改变了密钥派生等安全敏感的既有输入

**对应判据**：D1n、G2、D1

**定义**：接口适配层为某字段引入了规范化（去空白 / 大小写折叠 / 类型转换），而该字段同时是**密钥派生、摘要、
签名或已落盘等值匹配**的输入。既有数据是按规范化之前的输入生成的，升级后同一个人用同一个密码会派生出不同结果，
表现为**访问既有数据失败**，而不是「输入校验变严格」。

**为何出现**：适配层重构（尤其是把 `map[string]any` 手取改为结构体标签绑定）时，作者会把「非空校验」升级成
「规范化 + 非空校验」，因为两者在旧代码里常挤在同一个布尔参数里。新标记名只描述了新增的一半语义，
另一半（去空白）成为**无人声明的副作用**。

**实证案例（本仓库）**：`kernel/apicontract/notebook.go:92`、`:106`、`:107` 给 `password` / `oldPassword` /
`newPassword` 打 `api:"trim"`，而 `kernel/apicontract/decode.go:116-121` 把它实现为「`strings.TrimSpace` +
trim 后为空则报错」。主密码直接作为 `deriveKEK(password)`（`kernel/model/crypto.go:1220`）的输入，加密链路无任何规范化。
重构前 `util.BindJsonArg("password", &password, true, true)` 的第 4 参数是 `rejectEmpty`，旧 `ParseJsonArg`
函数体内无裁剪。实测 `{"password":"   "}` 返回 `Field [password] must not be empty`，旧实现下会通过 `rejectEmpty`
继续进入业务层。同族不一致：`ImportNotebookCryptoBackupRequest.Password`（`:55`）没有该标记；
前端 `app/src/config/tabs/accessTab.ts:803` 又自行 `value.trim()`。

**检查法**：

1. grep 绑定层的规范化标记与校验参数名，列出全部命中字段
2. 逐字段判定消费端：是否做密码学派生 / 摘要 / 签名 / 持久化等值匹配（是则高危）
3. 做**新旧实现对比**：读重构前的解析函数，确认规范化是新引入还是原有
4. 看同族字段的标记是否一致（不齐说明标记是逐个手加的）
5. 方向定性：宽进（无害）还是收窄（破坏既有数据）

**修法陷阱**：

- 合并语义的标记不能直接删除，否则附带校验（非空拒绝）一起丢失，须先拆成两个独立语义
- 不要用迁移后写的维护文档证明「这是保留行为」——迁移会把新引入的行为追认进文档，
  措辞常写「保留」而实际历史相反

### P39 手写多语言文档的同步漂移（同一事实的 N 份手写副本）

**对应判据**：D3c、A、H（格式与兼容性）

**定义**：同一份事实（API 说明、格式规范、用户指南）以多语言副本的形式**手写各自维护**，
没有生成步骤或一致性断言把它们钉在一起。特性提交只更新了基准语言版，其它语言版留在旧形态，
表现为**某语言的读者拿不到该特性**——文档里根本没提那个参数/返回值。

**为何出现**：多语言文档天生无法收敛为单一真源（译文必须各写一份），于是「单一真源缺失」这个判据
在此被合理地放松了；但放松的是**文本**，不是**结构**与**语言无关标识符**。
作者往往把「译文可以不同」误推成「这份文档可以独立演进」，于是每次特性提交只改基准版。
**与 P15 同源，但更难发现**：P15 的 DTO 漏项会静默丢数据，而文档漏项只表现为「读者不知道有这个功能」，
没有任何运行期信号，因此不会有人报 bug。

**实证案例（本仓库，已提 issue #19482）**：

| 缺失内容 | 引入提交 | 表现 |
|---|---|---|
| `mode` 参数 + 整个 `docTreePlan` 返回值 | `b1da7c0e74` 2026-08-30（#18119 模板创建子文档树） | `API.zh-CN.md` / `API.ja.md` 的「渲染模板」节各只有 26/27 行，英文版 61 行 |
| 整个 `### TypeScript contracts` 节 | `0627dd6a2a` 2026-09-12（#19378 端到端类型契约） | `API.ja.md` 无该节，`grep -c 'TypeScript'` = 0 |
| CI 运行说明 2 段（`TMPDIR` 要求 + 前端测试发现范围） | `a846821ec2` 2026-09-14（#19472 全量跑 CI） | `API-CONTRACTS.zh-CN.md` 直接从 tsconfig 段跳到下一段 |

**关键前提：先确认文档不是生成物**。本仓库 `docs/API*.md` 容易误判为生成物，实测
`kernel/apicontract/cmd/apigen/main.go:82-86` 只写 `app/src/types/api/index.d.ts`、
`kernel/apicontract/schema.json` 与 petal 的 `index.d.ts`，**不写 docs**。
若真是生成物，则「漂移」是生成器的问题，判据完全不同。

**检查法**：`scripts/scan_doc_parity.py`。两类比对**缺一不可**，实测两者各有盲区：

| 手段 | 能抓 | 抓不到 | 实测 |
|---|---|---|---|
| 结构指纹（各级标题数、围栏数、表格行数） | 「少一整节」 | 缺的是哪一节 | `API.ja.md` 的 `###` 少 1 个 → 定位到缺 `TypeScript contracts` |
| 语言无关标识符（反引号内） | 节内漏字段/参数 | 「整节都在但全被改写」 | 反向：`API.zh-CN.md` 三版标题数相同（78/78/77 中 zh 与 en 相同），只有标识符差集抓到「渲染模板」节少 4 个标识符 |

**修法陷阱**：

- **不要把「译文如此」当成漂移**。两类内容**可以**不同，比对前必须归一化，否则假阳性会淹没真差异：
  ① **占位符名被译**：`<relative-path>` ↔ `<相对路径>`、`<ancestorID>` ↔ `<父ID>`、`<workspace>` ↔ `<工作区>`；
  ② **代码示例的实参名被译**：`filepath.Base(path)` ↔ `filepath.Base(路径)`。
  归一化规则是「**结构必须一致，名字不要求一致**」：占位符统一成 `<>`、实参只保留被调名。
- **自然语言示例路径要整类排除**：`/Parent/Child/Current` ↔ `/父标题/子标题/当前标题` 是示例而非标识符
  （真实路径段几乎全小写，如 `/api/notebook/lsNotebooks`）。**该规则必须在归一化之后判定**——
  否则英文形式被丢掉、中文的 `/#/#/#` 留下，规则自身变成不对称的。
- **分桶要按归一化后的值**：若按原始值判定「是否含空格」，`<>/data/<>/`（英）
  与 `<>/data/<>/`（中，占位符内含空格）会落入不同桶，两边明明相等却报成缺失。
- **交叉引用被本地化是正确行为**：中文版指向 `X.zh-CN.md`，需配对抵消（实测不加此规则，
  SY-FORMAT / TAB-BLOCK / WORKSPACE 三组各报 1 条假差异）。
- 定位到差异后**必须回读该节**再定性。实测三组「标识符缺失」回读后是翻译选择（假阳性），
  两处「整段/整节缺失」回读后是真缺口。

**为何值得单独成模式**：本项发现的**可见性极低**——没有测试、没有运行期信号、CI 也不比文档，
只能靠机械比对。在此之前本仓库的 docs 一致性从未被任何工具检查过。

### P40 UI 状态漏项与交互可达性（用户能感觉到但测试抓不到）

**对应判据**：I1–I5、C、D1、D3

**定义**：UI 的行为契约在同类实现之间不一致或缺项，而**没有任何自动化手段会发现**——
类型系统不看运行时状态，linter 不看交互，测试不覆盖真实渲染。
四种具体形态：

1. **状态矩阵漏项**（I1）：UI 状态是闭合集合——**空 / 加载 / 错误 / 只读 / 超长**——
   同一组件族的兄弟实现（多个列表视图、多个面板、多个对话框）中某一处漏了某个状态
2. **交互态残留**（I2）：一次交互结束后应移除的临时态（`loading` / `disabled` / 遮罩 /
   拖拽占位）没有移除。**最典型是异常路径提前返回**：正常路径有移除、抛错分支没有，
   于是按钮永久停在 loading 或遮罩不再消失
3. **交互可达性缺失**（I3）：功能已实现但用户**够不到**——只在 `mousedown` 里处理导致键盘不可达；
   对话框关闭后焦点不回位，键盘用户要从文档开头重新走。**鼠标操作下完全不可见**
4. **受约束容器中的文本膨胀**（I4）：`<option>` / `nowrap` / `ellipsis` / 固定宽度元素配长译文溢出。
   **只在部分语言下显形**

**为何出现**：这是「单侧看着都对，只有交叉或跨状态才暴露」在 UI 层的体现，与本 skill 的核心命题同构。
作者按鼠标 + 自己的语言 + 正常路径开发，三处盲区正好各自屏蔽一类形态。
本仓库实证：2499 条提交里 **UI/style polish 占 823 条（33%）**，仅次于 bug fix 的 41%——
是本 skill 此前零覆盖的最大类别。

**实证案例（本仓库，I4 已跑出候选）**：

历史面板的操作筛选 `<select>`（`app/src/history/doc.ts:183-187`、`app/src/history/history.ts:534-540`）
有 7 个 `<option>`，取自 `historyUpdate` / `historyFormat` / `historyClean` / `historyReplace` /
`historyOutline` / `historySync` / `historyDelete` 一族键，英文值都是单个动词（4–7 字符）。
而 `<option>` **不换行**，且部分语言的译文长度约为英文的 2–4 倍：

| 键 | en | de | ar |
|---|---|---|---|
| `historySync` | `sync` (4) | `synchronisieren (sync)` (22) | `مزامنة (sync)` (15) |
| `historyOutline` | `outline` (7) | — | `الخطوط العريضة (outline)` (26) |
| `historyUpdate` | `update` (6) | `aktualisieren (update)` (22) | `تحديث (update)` (16) |

**语言的分布本身就是证据**：同一布局问题在 `ja` / `zh-CN` 各只有 1–2 个受约束候选，
而 `de` / `es` / `fr` / `ru` 各 80+、`ar` 76。**只在自己惯用的语言下看会完全漏掉本层缺陷。**

**检查法**：

1. **I4 已机械化**：`scan_i18n_text_expansion.py --langs <语言目录> --source <源码根>`。
   它先按「英文长度 ≤ 12 且膨胀 ≥ 2x」取候选，**再用源码交叉核对**，
   只保留使用点确实受约束的键（`<option>` / `nowrap` / `ellipsis` / 同行固定宽度）。
   实测 SiYuan：长度候选 488 个 → **经源码核对收敛到 70 个**（86% 是噪声）。
   `--source` **强烈建议提供**，不给则无法区分「受约束」与「可换行」
2. **I1/I2 半机械**：UI 状态集合需要语义判断。先机械列出同族实现（同文件的多个
   `render*` / `update*`，或同目录的多个面板），再逐项比对状态处理。
   **不要只报「没有加载态」**——要写出该状态下用户看到什么
3. **I3 只能人验**：用键盘走一遍（`Tab` / `Shift+Tab` / `Esc`），
   确认新增入口可达、对话框关闭后焦点回位。**鼠标会把这类问题完全掩盖**
4. 四条都要在**真实渲染环境**里取证（浏览器自动化 / DevTools 系列工具），
   静态阅读看不到「特定操作顺序」下才出现的状态残留

**修法优先级（写进报告的「建议」字段）**：

- I4：**优先「容纳」而非「改译文」**——放宽宽度 / 允许换行 / 缩短该语言文案，
  三者付出不同（改译文会影响其它语言的一致性预期），报告里要说清选了哪个
- I2：把清理放进 `finally` 或统一的收尾函数，而不是在每条返回路径上重复写
- I3：焦点回位应做在**所有关闭路径**上（`Esc`、点击遮罩、确认按钮），漏一条就等于没做
- I1：状态集合一旦定下，用**同一个渲染骨架**处理，避免每处手写

**为何值得单独成模式**：本层是**唯一没有既有校验器可依赖的层面**——
`tsc` / `eslint` 都不看这些，本仓库也没有相关的 UI 测试。
可见性极低（鼠标用户与英文/中文用户永远看不到），但占提交量三分之一。

### P41 无障碍行为反模式（键盘与焦点层面的不可达）

**对应判据**：I3、I1、D1

**定义**：界面在鼠标下工作正常，但键盘或辅助技术用户**够不到、或不知自己在哪**。
四类可靠形态（取自 `github/awesome-copilot` 的 a11y 反模式清单，MIT）：

| 编号 | 形态 | 为何算缺陷 |
|---|---|---|
| K2 | 正整数 `tabindex` | 把元素插进 Tab 序列的固定位置，破坏 DOM 顺序；**没有任何正当场景** |
| K5 | `outline: none` 且同选择器无 `:focus` 替代 | 键盘用户看不到焦点在哪（WCAG 2.4.7） |
| A6 | 纯图标按钮无可访问名 | 屏幕阅读器只能读出「按钮」（WCAG 4.1.2） |
| K7 / K3 | 对话框关闭后焦点不回位 / 焦点陷阱无 `Esc` | 键盘用户要从文档开头重新走，或被卡住（WCAG 2.4.3 / 2.1.2） |

另有 K1（非原生元素上只有 `click` 无键盘处理）、K6（只有 `hover` 无 `focus`）、
A2（`aria-hidden="true"` 包裹可聚焦元素）、A3（`role` 缺必需 `aria-*`）、
A8（动态内容无 live region）—— 这几类需跨行/跨文件语义判断，只能给提示位点。

**为何出现**：开发用鼠标、用自己惯用的语言、走正常路径。三个盲区各自屏蔽一类形态，
而**键盘可达性恰恰是唯一无法用鼠标自检的一类**。上游 a11y 文档明确列出这个陷阱：
不要把「静态语义正确」当成通过，也不要把「Lighthouse 通过」当成无障碍的证明。

**本仓库实测（2026-09-14，`app/src` 837 个文件 + 56 个 SCSS）**：

| 检查项 | 结果 |
|---|---|
| K2 正整数 `tabindex` | **0 个** —— 干净的信号 |
| A6 纯图标按钮无可访问名 | **33 个**（如 `app/src/mobile/util/keyboardToolbar.ts:1396+` 的移动端键盘工具栏） |
| K5 `outline:none` 无同选择器替代 | 候选 27 个 → 经源码核对落在可聚焦元素上 **18 个**，8 个是容器（**不是缺陷**） |
| `aria-hidden="true"`（A2） | **8 处全部在装饰性 `<svg>`/`<span>` 上，用法正确，零缺陷** |
| 提示位点（需人工判定） | 143 个 |

**检查法**：`scan_a11y_antipatterns.py --root <src> --styles <scss>`。

**三层降噪（缺一层就不可用）**：

1. **不看原始计数**。第一次粗扫得到「539 个 click 监听」，其中绝大多数在真按钮上，**全是噪声**。
   判定必须带上下文。
2. **按选择器分块**（K5）。`outline: none` 在不同选择器里的含义完全不同——
   要先看同一选择器（或其 `:focus` 变体）在本文件里有没有替代规则。
3. **再用源码交叉核对**（K5）。**这一步最关键**：`outline: none` 写在**容器**上是无害的
   （容器本就不会出现焦点轮廓），只有写在**可聚焦元素**上才是缺陷。
   实测被剔除的 8 个全是容器类（`.av` / `.emojis` / `.b3-form`）；
   如果不做这道核对就会把它们报成缺陷，被维护者一句驳回。

**取证只能靠真实渲染 + 键盘**（静态阅读与鼠标操作都测不出）：

- 用 `Tab` / `Shift+Tab` / `Enter` / `Space` / `Esc` 走一遍报告里的路径
- `Tab` 顺序、焦点可见性、关闭后焦点回位——**鼠标永远测不出来**
- 「业务表现」要写成键盘路径：「设置 - 外观，按 Tab 走到 X 按钮时看不到焦点位置」
- **不得把推测的辅助技术行为当作事实**；没有运行期证据就只能写成「需确认」

**边界（不可越界）**：本模式**只管行为**。a11y 里的**对比度、配色区分度、字号可缩放**
属**外观**，交给 axe / Lighthouse 与设计审查，不在本 skill 报告——
它们的取证手段（颜色计算 + 视觉基线）与本模式（走键盘流程）完全不同，
混在一起会让两边都做不深。

**修法优先级**：

- K2：删掉正整数，改用 `tabindex="0"` / `-1` + 调整 DOM 顺序
- K5：补 `:focus-visible` 样式，**不要**把焦点轮廓完全去掉
- A6：给图标按钮加 `aria-label`（文案进 i18n），并把装饰性 `<svg>` 标 `aria-hidden="true"`
- K7/K3：焦点回位要做在**所有关闭路径**上（`Esc`、点遮罩、确认按钮），漏一条等于没做

### P42 借用型临时标记类无人释放（临时 UI 标记 × 清理载体的覆盖矩阵）

**对应判据**：I2、D3、D3e

**定义**：一个临时 UI 标记类由功能 A 建立并在 A 的退出路径上清理；功能 B 借用了 A 的建立函数
（因为它需要该函数携带的某个副作用），于是 B 的路径上也会出现这个类，而 B 只清自己的类——
借用来的那个类留在 DOM 上，同时改变后续交互的行为。

**检测法（三步矩阵，可机械）**：

1. 取同一前缀族的全部临时类名（建立点 = `classList.add`），剔除配置驱动的常驻类
   （如 `protyle-wysiwyg--attr` 由设置决定，不是临时态）
2. 取全部清理载体（模块内的 `classList.remove`、`clearXxx()`、`cleanXxxHTML()`），
   写出「类名 × 清理载体」矩阵
3. 只有自己模块覆盖、或零覆盖的那一个是候选

**本仓库实测（2026-09-15，`app/src`）**：`protyle-wysiwyg--*` 族里 `--select` / `--select-mode` / `--hl`
各出现在 2–3 个清理载体（`util/clear.ts:39`、`ai/editor.ts:114`、`wysiwyg/blockSelection.ts:112`、
`ui/hideElements.ts` 的 `select` 分支），唯有 `--navigation` 除自己的 `clearAtomicFocus` 外零覆盖。

**关键区分：自理型 vs 自愈型退出路径**。同一功能的多个退出路径里，有的会顺带清掉它——
典型是绑定在 `input` / `pointerdown` 上的捕获监听（本仓库 `bindVerticalNavigationReset`），
它会把缺陷掩盖成「只有某一条路径有问题」。**必须逐个退出路径分别验证**：
本仓库实测 Esc 与 Enter 残留、鼠标点击不残留。

**定性要求**：**清理载体缺项是候选，不是结论**，必须有可观测行为才能定为缺陷
（本议题是「退出模式后第一次同向方向键跳过整个多行块」，对照实验：手工移除该类后同一按键改为块内逐行移动）。
给不出可观测行为就按「无业务表现」降为观察项。

**为何出现**：建立函数是复用的（借用方需要「安全聚焦」这个副作用），而清理责任留在原作者手里；
叠加自愈型路径兜底后，缺陷只在少数路径显形。

**修法优先级**：

1. **在建立端收紧**（首选）：只在语义成立时加类，借用方在语义不成立的场景不加。
   这同时消除「模式内首次按键时轮廓突然加重」这类观感差异
2. 在退出端补清理：更保守，但语义在窗口期内仍不诚实，且新增退出路径时要重复登记、容易漏改
3. 把该类纳入既有清理集合作为纵深防御——**不能无条件清除**，否则会破坏真正需要它的场景
   （本仓库折叠块与自定义块上的原子位置）

**为何值得单独成模式**：**没有测试会报错**（各模块单测只在自己模块的契约形态上断言），
linter 也看不到；只有「功能 A 的退出路径 × 功能 B 的借用」交叉时才暴露。
这与判据 C（该保的没保住）是同一维度的反面：**该清的没清掉**。

---

### P43 错误文案映射按复制位置铺开（漏掉可达路径、覆盖到不可达路径）

**形态**：同一 sentinel 错误的「→ 本地化文案」映射被复制到 N 个调用点，每个副本独立维护。
映射的覆盖范围因此由**复制发生的位置**决定，而不是由**该错误实际可能产生的路径**决定。

**判定方法**：

1. 先从依赖侧列出该 sentinel 的**全部产生点**（本仓库是 dejavu 的 `cloud/`、`sync.go`、`sync_manual.go`、`backup.go`），
   再从内核侧 `grep` 共享格式化函数的**全部消费点**，做「产生点 × 消费点」矩阵
2. 逐个消费点判可达性——不是每个 `repo.Xxx()` 都能返回该 sentinel。本仓库实测**两个方向都错位**：
   `syncRepoDownload` 的副本**不可达**（`SyncDownload` 没有 `availableSize` 守卫），
   而快照上传 `UploadCloudSnapshot` **可达却漏映射**（`UploadTagIndex` → `uploadTagIndex` 有守卫）
3. **同函数内的相邻分支是最强对照**：`UploadCloudSnapshot` 为 `ErrCloudBackupCountExceeded` 写了 Lang 154，
   对配额 sentinel 却直接落到通用格式化函数 → 属遗漏而非设计

**症状**：漏映射的路径把**上游库的原始英文错误串**嵌进已本地化的模板（`备份失败：%s`），
用户看到中英混排且得不到处理建议；同时共享格式化函数把它记为 `unclassified repository error`，
于是日志与用户提示不一致（日志说「未分类」，用户提示却是分类后的文案）。

**修法陷阱（本条最值得记的部分）**：不能把映射下沉进共享格式化函数了事。
本仓库 4 处副本都是**整体替换 msg**（丢掉「同步失败：」前缀与 ` (Provider: X)` 后缀），
而该 sentinel 的另一个来源是 `Local.GetAvailableSize()`（磁盘可用空间）；
下沉后 provider = 本地文件系统 的磁盘不足会被改写成「云端空间不足 + 订阅引导」——**比原缺陷更坏**。
正确修法是**先 provider 化**（只对官方云用云端文案，其余 provider 另给文案），再抽成单一函数。

**为何出现**：映射产生于「新增一条同类路径时顺手复制」，复制者只关心自己那条路径。

**为何值得单独成模式**：它同时具备 A（单一真源缺失）与 D3（闭合集合漏项）的性质，但**都不是**——
漏项不是「上游新增成员」，而是「复制者当时手上的那条路径」，因此静态枚举检查发现不了，
只能在「该错误能从哪里产生」这一维度上重建矩阵；且它的正确修法与「统一到共享函数」的直觉相反。

---

### P44 注册台账被渲染谓词剪枝（「暂时不渲染」被转成「已注销」）

**形态**：一份「已注册」清单（插件顶栏按钮、状态栏图标、命令、订阅、监听器）同时承担两个职责：
既是 API 的单一真源（`add*`/`remove*`、析构清理、目录/排序遍历都读它），又在**构建界面时**被
`document.contains(...)` 这类**渲染结果谓词**过滤；而过滤被实现成删除（`splice`）而不是跳过。

只要存在**另一个合法的、表示「暂时不渲染」的状态位**（本仓库：移动端 `local-plugintopunpin` 的
「取消固定」；其他项目的隐藏分组、宿主不提供挂载容器、跨端不同的挂载目标），
该状态位下的元素就天然位于 DOM 之外——于是「隐藏」在下一次打开界面时被静默转成「注销」。

**判定方法（三问）**：

1. **剪枝谓词比的是注册语义还是渲染结果**。`document.contains` 回答的是「现在渲染在哪」，
   不是「还注册着吗」；两者只在「挂载是注册的必然结果」时才等价，而隐藏态恰好打破该前提。
2. **枚举让「未渲染」合法成立的状态位**，逐个问「它会不会让元素离开 DOM」（本仓库两个：
   移动端取消固定；`isWindow()` 宿主无挂载目标）。
3. **比较剪枝点与恢复入口的先后——顺序即可达性**。本仓库 `openTopBarMenu` 先 `splice` 再构造
   pin/unpin 子菜单，于是「固定」这一唯一的恢复入口永远看不到被剪掉的项，隐藏态变成不可逆。

**同族对照最省力**：同一文件族里的 `statusBarIcons` 只把 `document.contains` 当「已挂载则跳过」的守卫，
**从不剪枝**；两处的差别不是风格，而是「清单的用途是台账还是渲染缓存」。

**修法方向**（最小）：剪枝只保留「跳过」，把真正的失效清理留给 `removeTopBar`/析构；
或把剪枝谓词换成注册语义（「插件实例是否仍持有它」）。

**为何值得单独成模式**：这段代码长得像正常的失效清理，**单看它还很有理由**
（本仓库它就是为「清理永不再挂载的图标」而引入的，issue #15455）；只有把「另一个状态位」
与「恢复入口的位置」一起看才暴露。且没有任何测试、日志或报错会发现它：
菜单里少了一项，用户与插件作者都只看到「功能不见了」。

---

### P45 同一实体存在两种身份表示（注册/命名层用 ID，路由层用 Name）

**形态**：一个外部实体（MCP 服务、插件、连接、会话）同时持有 `ID` 与 `Name`。
全仓的**注册、去重、运行时状态、生成物命名**都按 `ID`
（`BuildCapabilityID("mcp","backend",server.ID,…)`、运行时状态 map 以 `ServerID` 为键、`Normalize` 用 `serverIDs` 去重），
而**执行路由**却按 `Name`：处理器闭包捕获 `server.Name`，每次调用 `getMCPConnection(name)`
遍历连接列表**取第一个同名者**。

只要还有一种**不经过 UI 校验**的写入路径（HTTP API、配置导入、插件、直接编辑配置文件），重名配置就会出现；
此时第二个实体的调用落到第一个实体的会话上——两边有同名工具则**静默返回错数据**，没有则报 not found。
更隐蔽的是**错误处理也被串味**：第二个实体返回 401 会把**第一个**实体的连接摘掉，
并把它的凭据标记为 rejected，用户在界面上看到「另一个服务突然需要重新授权」。

**判定方法（三问）**：

1. **同一实体族里 ID 与 Name 各用在哪一层**。grep 两个字段名，把出现点按「注册 / 命名 / 运行时状态 / 路由 / 日志」归类。
   **注册层按 ID 而路由层按 Name** 是本形态的核心；若两层都按 ID 就不成立。
2. **是否存在专门的「重名兼容」代码**。这是最强的反证——本仓库为「服务名可能重复」专门写了
   `sanitizedServerNameCollision` 并据此给工具名加 hash，说明**命名层把重名当作合法输入**；
   既然命名层承诺支持重名，路由层按名字就自相矛盾。这也顺带否掉两种辩护：
   「重名不可能出现」与「工具名加了 hash 就能区分」（hash 只解决**注册名**冲突，闭包里的名字仍是同一个）。
3. **重名能否绕过所有校验写入**。名字唯一性往往**只在前端对话框**校验（本仓库 `aiMcpServerNameDuplicate`
   这个 i18n 键在 `kernel/**/*.go` 出现 **0** 次），而 API / 导入 / 插件都不经过它。

**修法方向**：把路由与状态定位改为按 `ID`（或在内核 `Normalize` 里对同名做去重/改名，但那是行为变更，需谨慎）。

**为何值得单独成模式**：它同时具备 A（单一真源缺失）与 D1（同族不对称）的性质，但**都不是**——
问题不在「同一份数据写了两遍」，而在**同一个实体的两种标识被分配给了不同的层**。
静态看每一层都是对的（注册用 ID 对、日志用名字也对），只有**跨层比对**才暴露；
且它不会有测试报错：注册表能正确区分两个服务，只是调用时走错了连接。

### P46 崩溃恢复队列的序列化闭合集合漏项（op 只进内存、不进磁盘）

**判据**：D3（闭合集合漏项）+ 「资源与生命周期」检查点（持久化写入的覆盖集合）。

**形态**：同一套 action 会出现在**多个并列的 switch** 里——内存变更通知、事务路由（`boxID()`）、执行分派（`execOp`）、
以及**磁盘序列化**（`dbOpToIndexEntry`）。新增 action 时补齐了前几个，唯独漏掉写磁盘那一个：
序列化函数的 `default: return nil` 让入队函数**静默返回**（无日志），该 op 永不落盘。
进程被强杀/崩溃后，恢复队列里没有它，索引永久停在旧值——而正常退出、正常重启都看不出任何异常。

**检查法（机械，成本很低）**：把该模块里所有 `case "<action>"` 的 switch 全部提取出来做成员集合比对，
并逐个入队 helper 的 `action:` 字面量核对：**每个被入队的 action 都必须在每个 switch 里有分支**（除明确不适用的）。
本仓库实测：4 处 switch → 3 处登记、1 处漏，唯一漏项即命中者；15 个入队 action 里只有它缺序列化。
再用 `git log -S '<action>' -- <file>` 判断「漏项」还是「有意排除」（本次输出为空 = 从未支持过）。

**严重度看自愈路径**：是否有周期任务或全库重建会修好它。本仓库的 `IndexEmbedBlockJob` 只补 `content = ''` 的行，
于是「非空但过期」的值不会被自愈；若存在无条件重建，应降级。

**修法陷阱**：恢复分支若照抄兄弟实现（`LoadTree` + `buildBlockFromNode`）重建，会把**派生内容**写成原始 Markdown
（本仓库会写成 `{{查询}}` 脚本），比原缺陷更糟——值变成非空，于是周期补全任务永远不再处理它。
正确做法是恢复**派生内容的生成逻辑**（复用原计算路径），或在 entry 中存下重建所需的足够信息。


### P47 桌面/移动孪生副本的漂移（复制后只改一侧）

**判据**：B（同一语义两份实现且已漂移）+ D1（镜像分支不对称）+ D1d（同族缺前置守卫）+ D3（闭合集合漏项）。

**形态**：同一功能在两个目录里各有一份**手工复制的实现**——本仓库是 `app/src/layout/dock/*` 与
`app/src/mobile/dock/*`（`Files`/`MobileFiles`、`Outline`/`MobileOutline`、`Tag`/`MobileTags`、
`Bookmark`/`MobileBookmarks`，`BacklinkContent` 是两者的共同基类）。之后某一次改动只改了其中一侧，
另一侧停在被修改前的状态。**危害会累积**：`AGENTS.md` 第 2 节第 11 条要求的「同步检查」在缺少共享基类时
只能靠人眼，于是同一功能面上反复出现不同表现。

**扫描法（成本低、产出高）**：按大括号配对提取两个文件的**同名函数体**，逐对算
`difflib.SequenceMatcher` 比值，把 `.999` 以下的全列出再人工分类。本仓库实测：
`Files` 24 个同名函数里 **17 个不同**、`Outline` 16/21、`Tag` 3/4、`Bookmark` 3/3。
第二路是**全局函数体哈希**（归一化空白后取 sha1）：986 个非测试 TS 文件得到 **15 组**
「同一函数体出现两次以上」，其中 11 组即上述孪生对，另 **4 组是非孪生的重复**
（`config/tabs/ai/aiUi.ts:332` 与 `config/tabs/secretsVariablesUi.ts:356` 的 `showDeleteConfirm`；
`protyle/render/av/dateFormatMenu.ts:7` 与 `number.ts:6` 的 `refreshDatabaseAttributePanels`；
`layout/dock/Graph.ts:360` 与 `Outline.ts:301` 的 `handleCallback`；
`layout/dock/graph/{canvas,label}Renderer.ts` 的构造函数）。

**分类纪律（决定报告可信度）**：比值低**不等于**缺陷。必须逐条回读并归入下列之一：
① **有意的平台差异**（触摸 vs 鼠标、`this.tree.element` vs `this.element`、缩进常量 18 vs 20、
`multiSelect` 守卫、`bindSort` 的两套独立拖拽实现）；
② **该端无消费者**（移动端不渲染 `.ariaLabel`，故桌面那段 `aria-label` 刷新对它不适用）；
③ **同端另有替代机制**（移动端用中央的 `mobile/util/onMessage.ts:134/143` → `removeMobileBacklinkContent`
代替逐面板清理）；
④ **外层已被守卫挡住**（`MobileOutline` 注册在 `window.siyuan.mobile.docks.outline`，**不进 `models.outline`**，
故桌面 `editor/util.ts:787` 那条 `setCurrent(undefined)` 路径不可达）；
⑤ **二者都对**（`onMount` 里 `liElement.remove()` 的位置差异：被读的 `.counter` 是 `closeElement` 头部那一个，
位于被删 `li` **之前**，`querySelector` 取到的永远是它）。
只有能写出**用户可见后果**的才升级为主报告。

**本仓库由此产出的 7 条（形态样例）**：
- #20220 移动端不派发 `opened-notebook` / `closed-notebook`（桌面 `Files.ts:1232`/`:1254` 有，移动端无）
- #20224 移动端 `setCurrent` 的**回溯分支**缺容器排除，而**首分支**有——**同一函数内**两处不一致
- #20225 两端的大纲成员判据只排除 2 类容器，内核 `collectOutlineHeadings` 排除 4 类（漏 `NodeTabItem`）
- #20226 移动端搜索在语义搜索方式下不拦截替换，而桌面端拦截——**同一个特性的两份实现**（`mobile/menu/search.ts` ↔ `search/util.ts`，共享 4 个同名函数），成因提交 `c0fdb2a694`（#17788）只改了桌面端；内核亦无兜底（只拒 `2 == method`，`switch method` 无 `case 4` → `default: // 关键字`）
- 另有「同族缺空守卫」（`onLsSelect`）、「同族缺路径规范化与环检测」（`selectItem`）两条可达性未证实

**两个高价值检查点**：
1. **同一函数内的两处不一致优先于跨文件比较**——`setCurrent` 的首分支与回溯分支相邻，一眼可辨，
   且对齐提交 `59dd2a0bc3`（#18259「Align mobile outline behavior with desktop」）的 diff 恰好**只改了首分支**。
2. **「对齐某侧」的提交要核它的 diff 覆盖了几个镜像分支**——`git show <sha> -- <file>` 看它漏了哪些分支；
   这类提交最容易留下半成品。

**方法限制（必须声明）**：按**函数名**配对只能抓到「复制品」与**共享部分函数的半孪生对**（#20226 的
`mobile/menu/search.ts` ↔ `search/util.ts` 只共享 4 个同名函数，靠**文件级映射**（每个 mobile 文件对所有
桌面文件算同名函数交集、阈值 ≥4）才被发现——**逐个猜配对会漏掉它**）。
完全两套手写的实现仍会漏：本仓库 `menus/*` 与 `mobile/menu/*` 的多数文件同名函数为 **0**
（`search`/`util`/`index` 三对全部 `common=0`），此时报「无发现」是**假阴性**，不能据此说该面干净。
要覆盖它必须换判据：按**同一配置字段/同一 API 参数的读写集**比对（第 13 轮的 #19442 就是这样找到的）。

**修法方向**：本仓库这类漂移**不建议**大规模抽公共基类（两端的 DOM 结构、面板宿主、拖拽机制差异很大，
抽基类会把差异压进 `if (isMobile())`）。可接受的最小做法是把「同一语义必须一致」的判据抽成**共享谓词**
（如大纲成员判据、容器集合），并给它加交叉断言测试；纯 DOM 操作的分支保持两份，但需在改动时成对修改。

### P48 包装脚本与容器默认值各注入同一段命令行（重复参数被第三方 CLI 当作未知子命令）

**判据**：A（同一标识符——这里是可执行文件路径——在两处重复且无单一真源）＋ B（启动参数两份提供）
＋ E1/E3（对第三方 CLI 的解析行为做假设）。**定性靠「实际拼出的 argv」，不靠「两处都看着对」**。

**形态**：前置脚本以硬编码路径起进程，并把**默认 CMD 的全部 token** 收集进变量后再追加：

```sh
exec su-exec "${UID}:${GID}" /opt/app/kernel --workspace="${WS}" ${ARGS}   # ARGS 含 CMD 的首元
# Dockerfile: CMD ["/opt/app/kernel", "serve"]
# 实际：/opt/app/kernel --workspace=/ws /opt/app/kernel serve   ← 路径出现两次
```

只要 CLI 是**严格解析**的（cobra / click / argparse 的子命令模式），多出来的第一个非 flag 参数就会被
当成子命令名 → `unknown command`；而在旧版 CLI（忽略位置参数）上**完全看不出来**，
所以缺陷会长期潜伏，直到 CLI 改成子命令解析后集中爆发。

**检查法（三步）**：
1. 把**前置脚本 ＋ 镜像默认值 ＋ 用户的 `command:`** 三种来源合起来，**逐 token 拼出真实 argv**，而不是分开看；
2. 用**第三方 CLI 的源码**确认解析规则（本仓库：`cobra@v1.10.2` 的 `args.go:28 legacyArgs`
   对「root ＋ 有子命令 ＋ `len(args) > 0`」报错，`Find` 仅在 `commandFound.Args == nil` 时走它）；
   同时确认根命令**没有** `Args`/`Run` 兜底；
3. 查**「最近的 CLI 结构变更提交」有没有同步改包装脚本**（本仓库 `bcbd18658a` 删掉了 `main.go` 的
   「无子命令自动补 `serve`」兼容层，却把默认值改成带路径的 CMD → 重复）。

**与「文档已写明」的关系**：README 写「必须显式传 `serve`」只解释了**用户传参那条路**，
不能解释**镜像默认值那条路**为什么坏——两者是不同入口，必须分别验。
入口脚本/Dockerfile 的注释（「默认启动伺服」）在本仓库正是**与实现相矛盾**的那一侧，
**它是权威依据（承诺了行为），不是「有意设计」的证据**。

**误报排除**：若 CLI 对位置参数宽容（忽略多余参数）或包装脚本用 `"$@"` 原样转交，则重复不会致错——
必须先读解析源码再定。

**本仓库实证**：`kernel/entrypoint.sh:52` ＋ `Dockerfile:83` ＋ `kernel/main.go:27-31`（第四十四轮，与 #18699 同源）。


### P49 同族多实现中只有一处获得语义升级（改进只命中一个副本）

**判据**：D1q（同族改进只落到一个实现上）＋ B（同一语义两份实现）＋ D1。

**形态**：一条语义（大小写折叠、字面量替换串转义、路径边界校验、前置守卫）在同族里有多份**逐字复制**的实现。
某次改动把其中一份升级为更正确的版本，其余副本停在旧语义。编译器、linter、测试都不会比较两份副本的语义，
因此改动看起来是纯改进（还带着新测试），缺陷只在用户走到另一个分支时显形。

**本仓库实例（第四十七轮，差分审查 `bbef0e1f8b..HEAD`）**：`dee81f8a25`(#20242) 把
`replaceCaseInsensitive` 的替换串改成 `ReplaceAllFunc`（`$1` 不再被当捕获组）。而**大小写折叠**这条语义
自 #9171 起只存在于 `replaceTextNode`（`ast.NodeText`）：`Conf.Search.CaseSensitive` 默认 `false`
（`kernel/conf/search.go:103`），但 `replaceNodeTokens`（`imgSrc`/`imgText`/`imgTitle`/`codeBlock`/
`mathBlock`/`htmlBlock`）与 `replaceEscapedTextMarkContent`（`code`/`blockRef`/`fileAnnotationRef`/`em`/
`strong`/…）以及 `docTitle`/`tag`/`aTitle`/`aHref`/`inlineMath`/`inlineMemo` 共 24 个分支都用精确 `Contains`。
→「搜索 - 替换」在忽略大小写（默认）时，「全部替换」只改正文文本；链接文本、图片标题、加粗等位置的同词不替换。

**检查法**：① 在 diff 里定位**本次新引入/修订的那个语义函数**；② `grep` 它的调用点，看是否只有 1–2 个；
③ 用**同族的枚举清单**（本例是 `replaceTypes` 的 25 个键，权威侧见 `app/src/types/api/index.d.ts` 的
`CriterionReplaceTypes`）逐个问「它走到哪个实现、那个实现是否用了新函数」；④ 对每份副本问
「这条语义是它自己算的还是共享的」。

**取材纪律（关键）**：命中的是**既存**缺陷，只是被同族改进「照出来」，**不得写成本轮引入**。两件取证都要做：
`git log -S <符号> -- <file>` 确认改进何时、只落到哪一处；`gh api repos/<o>/<r>/issues/<n>`
查维护者是否已承认过该缺口（本例 #9171 评论「上面这个问题稍后改进」）。两者一并写进「既往记录」字段。

**修法方向**：把语义收敛到单一 helper（本例是让所有分支复用同一个「按需折叠 + 字面量替换」helper），
而不是在 24 处各补一遍。

**第二形态：被漏掉的是「对外表面」而不是「函数副本」（第五十四轮）**。同族的边界不必是同一文件里的若干函数，
也可以是**同一能力的多个对外入口**——REST 接口、MCP 工具、CLI 子命令、SDK。此时改进者只修自己碰到的那一个，
其余入口停在旧语义，而**编译器与测试都不会比较两个入口的对外行为**。

- **实例**：「SQL 查询在未显式写 LIMIT 时按默认值截断，且截断对调用者不可见」这条语义有三个对外表面。
  `1e9580315e`（#19108，2026-09-03）修了 MCP（`kernel/mcp/tools/sql.go` 加 `possiblyTruncated` 与逐结果提示），
  `f97b7be20b`（#19337，2026-09-12）修了 REST `/api/query/sql`（响应加 `queryLimit.{limit,truncated}`）。
  **CLI `siyuan sql` 是第三处**：`kernel/cli/cmd/sql.go:48` 仍是 `sql.Query(stmt, limit)`，
  `printSQLResult`（`:90` 打印 `%d row(s)`）与 `-f json` 分支都不显示截断。CLI 于 `ade459cf08`（2026-05-14）加入，
  早于两个 issue ⇒ 既存缺陷。
- **决定性证据是 issue 正文自己列的清单**：#19108 与 #19337 的「相关源码」都只写 MCP 与 REST，
  而 #19337 的诉求原文正是「调用方（脚本、SDK、AI Agent）会把 64 行当成全部结果…静默漏数据」——
  CLI 的调用方形态与之完全一致，却被两轮漏掉。**这说明「同族清单」要自己从能力反推**，
  不能沿用别人给出的「相关源码」。
- **附带形态：同一参数在多个表面上语义不同步**。#19108 把 MCP 描述成「default to at most N rows」（承认显式 LIMIT 优先），
  而 CLI 的帮助与四语用户指南写「Maximum rows to return」（隐含硬上限）——而实现里语句自带 LIMIT 时
  `--limit` 完全不参与（`kernel/sql/block_query.go:419`／`:446-455` 只在无 LIMIT 时注入；`:548` 保留自带 LIMIT；
  `:499` 的截断要求 `info != nil`，CLI 走 `info == nil`）。**同一参数在多个表面的措辞不一致，本身就是清单未收口的信号**。
- **检查法**：③ 之前先做一步——**从能力名反推全部对外表面**（本仓库 SQL 查询 = REST `/api/query/sql` +
  MCP `sql` 工具 + CLI `siyuan sql`），再逐个问「它是否实现了这条语义」。

### P50 自我参照判定器（期望值由被测实现自己产生）

**判据**：J1（判定器在实现内部）＋ G1（两实现之间无一致性断言）＋ A（单一真源指向了被审计对象本身）。

**形态**：断言里「实际值」与「期望值」都由被测实现产生。最常见的两种写法：
① 断言两侧都是同一个函数（`f(left)` vs `f(right)`）；
② **状态差分**——改前 / 改后各取一次同一个函数的返回值再比较（`before`/`after`、`got`/`want`）。

第三种形态最隐蔽：**期望值不是调用得到的，而是测试代码把旧格式重新实现了一遍**（见 P53）。

**为什么这算缺陷**：这类测试**不会因为实现出错而红**。它的判定器就是实现本身——实现错，
期望值跟着一起错。ThoughtWorks 技术雷达 Vol 34 把变异测试重新列为 Trial 的理由正是这个：
「AI 生成测试普及后，高覆盖率会掩盖**逻辑空洞**的测试」。覆盖率与文件数都看不出来。

**本仓库实例（第四十八轮）**：
- `kernel/sql/recent_index_test.go` `TestRecentUpdatedBlocksIndexesPreserveResults`：
  `before` 与 `after` 都由 `SelectBlocksRawStmt` 产生，核心断言是 `reflect.DeepEqual(before, after)`
  → 「建索引前后结果一致」这条**判定器就是被测函数自己**。
  **但同一测试还有绝对值断言**（`len(after[0]) != 16`、`after[0][0] != "p-39"`、`after[2][0] != "d-39"`）
  → 结论是「这条断言弱」，**不是「整个测试无效」**。
- 全仓机械候选 31 条 / 25 文件（`scan_test_quality.py --section oracle`），
  其中 `[same]` 12 条；绝大多数是**正常写法**（见下「检查法」第 ② 步）。

**检查法**：`python scripts/scan_test_quality.py --repo <repo> --section oracle`，然后只问一个问题：
**这个测试里有没有任何一处期望值的来源在被测实现之外？**（字面量、`testdata` 捕获产物、
另一实现如 Node WebCrypto / 上游库、规范表如 i18n 语言文件）。
① 一处都没有 → 零判定力，成立；
② 有 → 记「弱」而不报，**不得因为出现了 `[same]` 就报**。

**误报面（必须逐条排除，实测都出现过）**：同一变换作用于**两个不同输入**
（`docDiffBlockSignature(left)` vs `(right)`）——这是正常的同一性断言；
`reflect.ValueOf(f).Pointer()` vs `reflect.ValueOf(util.PushMsg).Pointer()`——比较函数指针；
`strings.Join(a, "")` vs `strings.Join(b, "")`——工具函数对两个输入做同样的确定性变换；
`Conf.Language(315)` vs `err.Error()`——**这一侧是外部权威**（i18n 表），是正例。

**修法方向**：不要删测试，**补一条外部断言**（把期望值写成字面量或夹具）。
保留原断言无害，缺的是「实现坏了会红」的那一条。走修复手册的修法阶梯第 1–2 级即可。

### P51 无判定力测试（跑了但没有可失败的断言）

**判据**：J2 ＋ G4（测试不在执行集内时更不可见）。

**形态**：测试函数体里没有任何断言构造，也没有调用任何断言 helper。
三种来源：① 真无断言（只剩 `f(x)` 的调用）；② 「不得 panic」型（本意如此，但从未声明）；
③ 断言**封装在 helper 里**——扫描器按目录收集 helper 名后这一族会被消掉，
但**仍须回读确认 helper 里真在断言**（存在名为 `checkXxx` 却什么都不校的函数）。

**本仓库实例（第四十八轮）**：全仓 15 个文件 / 19 个测试函数命中；其中 12 个是同一形态的
`kernel/api/contract_*_test.go` 批量（断言全在泛型 helper `compareSettingConfig[...]` 里，
**已由扫描器的按目录 helper 收集排除**，属假阳性族）；残留的真实候选包括
`kernel/util/websocket_test.go:27 TestContextPushMsgIgnoresInvalidContext`（「不 panic」型）。

**为什么值得单列**：这类测试**通过率 100%**，因此既不会被注意到、也不会被删除。
Google《Software Engineering at Google》ch11 的原话是「**A bad test suite can be worse than
no test suite at all**」——它会让人以为该行为被覆盖了。

**检查法**：`scan_test_quality.py --section assert`。**两类回读前置**（不去掉会得到整批假阳性）：
① 断言 helper 可能是跨文件、泛型签名（`func compareSettingConfig[…](t *testing.T, …)`）、
   箭头函数（`const checkTarget = (t, e) => { assert… }`）三种形态——扫描器按**目录**收集后仍要抽查；
② `Benchmark*` 本就不该有断言，`t.Skip` only 也不是测试，两者都已排除。
另外要读**汇总行**而不是尾部若干行（历史上把 13 处失败写成 1 处）。

**修法方向**：先判断它**到底想验证什么**。想验证「不 panic」就写 `defer func(){ if r!=nil {t.Fatal} }()`；
想验证行为就补断言；**确实没有可验证内容时应删掉测试**（Google ch12 对 sunk cost 的表述：
对已经不再提供价值的测试，「按删除键」才是正确的）。

### P52 测试绑定实现结构（纯重构即红）

**判据**：J4 ＋ G3（手写替身白名单）＋ B（同一事实两份实现）。

**形态**：测试断言的是**内部结构**而非公开行为：手写的模块 / 桩 / 导出清单、
内部调用序列、私有符号、内部数据形状。判据只有一条——**纯重构会不会让它变红**。
Google ch12 的表述是 the ideal test is **unchanging**：
「重构、修 bug、加功能都不应需要改已有测试，只有**行为变更**才该改」。

**本仓库实例（第四十八轮）**：前端手写模块表 28 个文件（`sources = {` / `modules = {` / `stubs = {`，
集中在 `app/tests/*.test.js`）+ Go 的调用序列断言（`kernel/av/relation_refresh_test.go` 的 `wantCalls`、
`kernel/model/repository_range_test.go` 与 `kernel/mcp/tools/bazaar_test.go` 的 `calls = append(`）。
**直接后果是失败信息无法归因**：`app/tests/settingsWindow.test.js` 因「模块白名单未登记新模块」
长期红在 dev 上，报错与业务无关（`unexpected module X`），于是既没人修也没人删。

**与 G3 的分工**：G3 把这类失败归到「契约缺口」并声明「与产品缺陷无关，只污染修复验证」；
P52 说的是**它本身就是测试套件的缺陷类别**，两者不重复计分。

**检查法**：`scan_test_quality.py --section binding`。回读时问：
**如果把被测实现内部重排（拆函数、改调用顺序、换内部数据结构）而行为不变，这个测试会红吗？**
会红 → 命中。**不要把「用了 mock」当成命中**——mock 本身不是缺陷（判据 J 的权威依据里
Google 与 Fowler 都只反对**滥用**）。

**修法方向**：把断言从「调用了谁」移到「产生了什么结果」（Google ch12 的
test state, not interactions）；手写模块表改成真实加载（本仓库已有 Playwright 基础设施）。

### P53 兼容性夹具不是外部权威（用测试代码重写旧格式）

**判据**：J3 ＋ H3（缺少上一版格式的回归夹具）。

**形态**：格式变更的回归测试**确实有夹具**，但夹具不是捕获的真实产物，而是**测试代码现场构造**的。
危险在于：夹具与实现由同一个人、同一时期编写，**两边可能共享同一个错误理解**，
于是「旧版仍可读」这个承诺从未被真正验证。

**与 H3 的分工**：H3 问「有没有上一版格式的夹具」，P53 问「这个夹具独立于实现吗」。
**有夹具不等于有外部权威**。

**可信度阶梯（本仓库实测三档）**：
① **跨实现产物**（最高）：`kernel/plugin/crypto/testdata/interop.json` 由 **Node 的 WebCrypto**
   生成（`generate_fixtures.mjs`，`0cb7631941`/`#20041`）、Go 侧消费——判定器是真实浏览器规范实现；
   同理 `app/tests/fixtures/unicode17-emoji.json`、`kernel/treenode/testdata/*-legacy.sy`（捕获的旧 `.sy`）。
② **捕获的真实旧产物**：直接从受支持的旧版本导出。
③ **测试里重写旧格式**（最低）：`kernel/model/crypto_asset_legacy_test.go:19`
   `legacyEncryptedAssetFixture` 注释自陈「按无版本字段的资源格式生成样本，**不调用当前资源编码器**」
   ——这比自我参照强（两份独立实现），但仍可能同错。
   **注释自陈只是必要条件，不是可信度证明。**

**检查法**：`scan_test_quality.py --section fixture`（双条件：提到 legacy/旧版本 **且** 有现场构造点
`[]byte{` / `bytes.Repeat` / `Buffer.from`，且**不读** `testdata`/`fixtures`）。
本仓库 4 条候选；对照面是 **585 个**读 `testdata`/`fixtures` 的测试文件。
**回读时先排除「只是注释里提到 legacy」**——不看「夹具位点」条件时，任何提到旧版本的契约测试都会入选。

**修法方向**：优先把旧版产物**捕获**进 `testdata/`（H3 的要求），或改为跨实现夹具；
必须保留自建夹具时，在测试注释里**显式标注可信度等级**，避免后续读者把它当成旧格式的权威样本。

### P54 批量多值查询缺少参数预算，且失败被呈现为「未找到」

**判据**：G（对外契约）＋ D（对称性：写侧有预算、读侧没有）。

**形态**：`SELECT … WHERE id IN (?, …)` 的占位符个数由入参规模决定，一次拼成**一条**语句。
入参越过后端参数预算后语句失败，而失败处理是「记日志 + 返回空」，
上层再把空结果解释成「这些 id 都不存在」——**接口仍返回成功**。

**本仓库实例（#20373）**：`kernel/sql/block_query.go:1041`（`GetBlocks`）与
`kernel/sql/encrypted_query.go:92`（`GetBlocksInBox`，`strings.Repeat("?,", n-1)`）。
预算来自编译进二进制的 `SQLITE_MAX_VARIABLE_NUMBER`
（`88250/go-sqlite3` 的 amalgamation 里为 32766）。实测（冷缓存、入参全是真实存在的块）：

| 入参 ID 数 | 响应 code | 返回的占位块 / 总数 | 日志 |
| --- | --- | --- | --- |
| 32767 | 0 | 0 / 32767 | 无错误 |
| 33000 | **0** | **33000 / 33000** | `sql query […] failed: too many SQL variables` |

**为什么算缺陷而不是「参数太长」**：① 调用方**无法区分**「不存在」与「查询整体失败」
（`GetBlocks` 出错只 `logging.LogErrorf` 后 `return`，`ret` 为 `nil`，而长度又与入参一致）；
② 触发条件取决于**缓存未命中数**（命中时不进 SQL），同一请求在不同负载下行为不同；
③ 入参本身无任何上限（`kernel/apicontract/riff.go:8`、`kernel/model/flashcard.go:48`）。

**检查法**：搜 `IN \(?` / `strings.Repeat("\?,"` / `VALUES %s` 三类构造，逐站点回答两问——
① 构造函数的入参规模有没有上限？② 执行失败时的返回值与「未命中」是否**可区分**？
对照面（说明这是能做对的）：`kernel/sql/upsert.go:72` 写侧按 **512** 分块；
`kernel/sql/query_limit.go:17` 反过来**拒绝** `limit == math.MaxInt`。

**为什么不写成脚本**：决定性的问题是「这个调用点的入参是否有界」，属**数据流**而非词法；
扫描只能产出都需要人工回读的个位数候选，不值得占 `scripts/` 位（见 [运行时量测](./runtime-measurement.md)「何时把量测写成脚本」）。

**修法陷阱**：只加「入参长度上限」会让合法的大批量调用变成 400，且**不修复「失败不可见」**；
正确修法是**分块执行** + 让 `GetBlocks`/`GetBlocksInBox` 把错误上抛。同族修复必须两处都改（含加密旁路）。

### P55 用固定睡眠充当「异步完成」信号

**判据**：E（隐式假设）＋ D1i 家族（吞掉错误/错误信号缺失使调用方假成功）。

**形态**：等待一个异步入队的操作落盘时，不接真实完成信号，而是先 `Sleep` 一个「经验上够用」的
固定时长，再轮询队列是否为空。

**本仓库实例（#20370）**：`kernel/model/transaction.go:60-67` `FlushTxQueue` 开头**无条件**
`time.Sleep(50ms)`，50 个文件里约 98 处调用；新建文档路径上有 4 处
（`kernel/model/file.go:1356/1387/1396` ＋ `kernel/model/blockial.go:220`）
⇒ 单次 `createDocWithMd` 有 **200 ms 固定下限**。同进程实测：`/api/system/bootProgress` 1.2 ms、
`/api/attr/setBlockAttrs`（1 次 flush，写相同值）57.1 ms、`createDocWithMd` 256 ms
（其中约 200 ms 是睡眠）、`/api/block/getBlockKramdown` 1.4 ms。

**双后果（这是它值得单列的理由）**：空闲时白等（延迟下限 × 调用点数）；负载高时**仍可能不够**
（它本就是为 #12896「日记模板加载失败」加的宽限期，`29f744c7e0`，而排空条件到 `1e534539ecb` 才加上）
⇒ 既是性能缺陷也是正确性隐患。

**检查法**：搜 `time.Sleep` 与 `Deadline`/`Wait`/`Flush` 类命名共现的函数，
问「这个时长是怎么定的、异步侧有没有可等待的句柄」。对照面：同文件已有
`Transaction.prepareCommitWait()`/`WaitForCommit()`/`WaitForTransactions()`
（`kernel/model/transaction.go:69` 注释自陈「等待已提交批次的写入…完成」）。

**修法陷阱**：把 50 ms 调小只是把正确性风险推迟；必须换成真实完成信号（登记完成句柄或条件变量），
并保留「队列排空」等待。

**第二形态：固定超时没有收口（`Context` 到期 ≠ `Wait` 返回）**（判据 E5；本仓库实例 #20378）

**形态**：给 `exec.CommandContext` 设了超时就认为「最多等这么久」。但 `ctx` 到期时 `exec` 只对
**直接子进程**调用 `Cancel`（默认 `Kill`），而 `Output()`/`CombinedOutput()` 还要等 stdout/stderr
管道读到 EOF。若被终止的进程留下了**继承该管道的后代**，管道不关闭，`Wait` 就一直阻塞——
超时形同不存在。它与第一形态的共性是「等待条件不是真实完成信号」，区别是这里的等待发生在
标准库内部，代码里连 `Sleep` 都看不到，**只能靠 `WaitDelay` 是否存在来判定**。

**本仓库实例（第五十五轮）**：`kernel/util/font_platform_linux.go:34-43`（10 秒超时、无 `WaitDelay`，
且超时判断位于 `nil != err` 之后，卡住期间没有任何日志）。放大点在 `kernel/util/font.go:43-51`：
`LoadSysFonts` 全程持有 `sysFontsLock` ⇒ 阻塞期间同进程内后续所有字体枚举一起卡住。
触发面是 `PATH` 上名为 `fc-list` 的包装器（发行版 / 容器 / Nix / Flatpak）在退出前派生持有 stdout 的后代；
stock `fc-list` 不 fork，所以**普通操作看不到**。机制级复现：把 `:34-37` 的调用形态原样复制到独立程序、
超时缩为 3 s、`PATH` 上放一个派生继承 stdout 的后代并长睡的假 `fc-list` ⇒ 不设 `WaitDelay`
**20 s 仍未返回**，设 `WaitDelay = 2s` 则 5.0 s 返回并打印超时。**全仓 `grep WaitDelay` 为 0 处**。

**检查法**：grep `CommandContext`，逐个问 `cmd.WaitDelay` 在哪、`Cancel` 是否覆盖整棵进程树；
再看调用点是否持有**全局锁 / 单例缓存**（那决定它是「一次慢」还是「全局卡死」）。
对照面：同仓库 `kernel/util/ocr.go:286`、`kernel/api/lute_clipboard_math.go:330` 同样有超时而无
`WaitDelay`，但**不持全局锁**，后果量级不同——判严重度时必须看这一点。

**修法**：`cmd.WaitDelay = <与超时同量级的短值>`（标准库 `src/os/exec/exec.go` 的 *"a child process that
exits but leaves its I/O pipes unclosed"* 正为此而设）。**不要**改成「先 `ctx.Err()` 预检再读」——
那是 TOCTOU，挡不住已经在读的 `Wait`。

### P56 声称的写入优化与实际实现不符（全量 copy 冒充差异写）

**判据**：E（隐式假设）＋ H（持久化语义）。

**形态**：issue 或注释声明「改为 mmap 后只写差异字节」，实现是把整份缓冲 `copy` 进映射——
CPU 写为每页置脏、内核不做内容比较 ⇒ **脏页数 = 文件页数**，回写整份。
性能收益真实存在（相对「临时文件 + rename」少写一半），但**承诺的语义没有兑现**。

**本仓库实例（#20367）**：#16956 的结论「mmap 会仅写入 diff 部分的字节」 vs
`kernel/util/mmap.go:37`（`Truncate(len)` → `mmap.Map` → `copy(m, data)` → `Flush()`，全视图）。
实测（23 MB 文档 / 5861 页）：末尾追加只改 362 B、等长覆盖只改 **1 B**，
但每次编辑都等价于整份写（每次编辑 1 次落盘、无合并；23 MB 文档单次编辑 0.65–1.05 s，
且耗时与改动量无关——那段延迟来自全量 JSON 序列化，与写盘量是两个问题）。

**同一函数的另一条不对称（可靠性）**：明文路径走「Truncate + 原址覆写」（崩溃可能留半写文件），
加密路径刻意走临时文件原子替换（`kernel/filesys/tree.go:511-516` 注释自陈理由），
而加密**属性视图** JSON 仍走 mmap（`kernel/av/av.go:1108`）⇒ 同一写路径的持久化保证不一致（#20372）。

**检查法**：看到「优化 / 降级」类注释或契约声明时，**回读实现是否真的做到**；
对 mmap 路径要特别问「copy 的区间是整份还是差异页」。同族信号：同一次改动里**声明**与**实现**分属两个文件时。

**修法陷阱**：把 mmap 换回临时文件是**回退而不是修复**（会丢掉 mmap 的收益）；
正确方向是「只写差异页 ＋ 长度未变时不 `Truncate`」，或对加密路径单独对齐 `.sy` 的原子替换。

### P57 一个位标志驱动整份配置重写，且发生在同步事件处理器内

**判据**：D4 家族（写入放大）＋ E。

**形态**：把「运行时状态」混入对外配置结构，状态翻转时调用整份 `Save()`；
而 `Save()` 的幂等去重是**读回整份文件**再比较 ⇒ 即使不写盘也要付一次「整份序列化 + 整份读回」。

**本仓库实例（#20368）**：`kernel/model/conf.go:90` `DataIndexState`（0/1）——
`kernel/model/index.go:527-535` 在两个事件回调里 `Conf.Save()`，发布点覆盖索引队列全生命周期
（`kernel/sql/index_queue.go:247`、`kernel/sql/queue.go:374/708/716`）。
事件是**同步分发**（`siyuan-note/eventbus` 包装 `asaskevich/EventBus` 的 `Subscribe`，
非 `SubscribeAsync`）⇒ `Save()` **内联在入队路径**上。实测一次 `createDocWithMd` 的窗口内，
`conf.json` 整份重写（15,407 B，尺寸不变）＋ 每次 `saveLocked` 读回 15,407 B
（占该窗口读的 ~52%、写的 ~25%），而该标志**只在启动时被读一次**
（`kernel/model/conf.go:854-859`，`Conf.DataIndexState = 0` 之后不再使用）。

**检查法**：搜对整份配置/清单的 `Save()`/`Write()` 调用点，问「写入的字段是用户配置还是运行时状态」；
再搜该状态的**读取点**——若只在启动读一次，它就是被放错了载体。

**修法陷阱**：只做去抖仍会在退出/周期路径上整份写；**移出配置文件**（或直接用「队列是否非空」代替）
才能消除放大。注意它同时出现在 conf 的 API 契约里（`kernel/apicontract/system_conf.go:39`），
移出时须一并处理契约与生成声明。

### P58 「读—改—整份写」的小状态文件被逐条调用（O(N²)）

**判据**：D（对称/预算）。

**形态**：每次新增一个条目都「读入整份 map → `os.ReadDir` 取现存集合 → 改一项 →
整份序列化 + 写回」。单次 O(N)，连续 N 次即 ΣO(i) = **O(N²)**：条目越多，越晚创建越慢。

**本仓库实例（#20369）**：创建文档后的排序落盘——`kernel/model/file.go:1394`
→ `:3146 placeDocsInSiblingOrder`（`readSortConfMap` 整份读 ＋ `loadSiblingCustomOrder`（`:2824`）
的 `os.ReadDir` ＋ `writeSortConfMap`（`:2535`）整份 marshal ＋ `filelock.WriteFile`＝临时文件+rename+fsync）。
实测同一目录连续新建（每篇 `.sy` 仅 543 B）：`sort.json` 每篇约 28 B，
20 篇 552 B / 120 篇 3,373 B，**累计写入 202,587 B**，与 Σ28i ≈ 14N²（=201,600）吻合
⇒ 相对线性放大 **60×**；每篇耗时 274 ms → 315 ms。外推单目录 1 万篇 ≈ 累计 1.4 GB。

**检查法**：搜「读 JSON/map → 改 → 写回」的小文件写入点，问**这次调用改了几项**；
若只改 1 项却整份写、且该调用会被连续触发（交互式创建、逐条导入、逐条标记），即为该形态。
**必须区分逐条路径与合批路径**：同仓库批量导入走 `setImportSort`（合批）所以不受影响，
只报逐条路径。

**修法陷阱**：把 `filelock.WriteFile` 换成 mmap 只减少常数、不消除 O(N²)；
必须做到「只写变化的条目」或「只追加」。

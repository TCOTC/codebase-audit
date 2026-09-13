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

**检查法**：机械提取闭合集合（case 标签、枚举成员、数组项），存成文件；与权威源逐项 diff。**调用方自行补偿不能作为豁免理由**——补偿是变通不是修复，任何不知道要补偿的新调用方都会继承该缺陷。

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

## 如何扩充本库

1. 从一次**已确认的缺陷**出发（而非猜测），确认它为何未被既有判据捕获。
2. 把技术一般化：审计者**本该问什么问题**？
3. 至少给出 3 个来自不同领域的实例，不要全都出自同一模块。
4. 说明可验证性：如何复现、如何取证。
5. 补充到本文，并在 `SKILL.md` 的判据清单里挂接。
6. 若新判据带来新误报，同步写入 `SKILL.md` 的「已知误报」。

目标是让判据库随缺陷发现持续累积，而不是每轮从零开始。

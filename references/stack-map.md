# SiYuan 全栈层面地图

## 用途

`SKILL.md` 的判据 A–H 回答「**怎么推理**」（按缺陷的推理形态组织：单一真源缺失 / 语义漂移 / 状态保持 …）。
本文件回答「**去哪找**」（按仓库层面组织）。

两者正交，配合使用：先按本文件确定范围与权威源，再回到判据清单取检查法，最后按 [挑战门](./challenge-gate.md) 审查。

## 每层给出的五项

1. **关键路径** —— 该层的源码入口
2. **权威源** —— 该层的「单一真源」在哪，即判据 A / D3 / D3c 的比对基准
3. **高发形态** —— 该层历史上真实出现过、且会反复出现的缺陷形态，附判据编号
4. **既有校验器** —— 该层**仓库自带的**检查命令
5. **取证陷阱** —— 该层特有的坑，多数是本仓库实测踩出来的

> **第 4 项是一条设计约束，不只是索引**：能跑仓库自带的校验器就不要在本 skill 里重写一份。
> 重写等于制造第二份真源，正是判据 A 要抓的东西（`scripts/check-*` 与本 skill 的脚本重复即属此列）。

## 四个组

| 组 | 层面 | 语言/宿主 |
|---|---|---|
| 内核 | L1 数据与索引、L2 API 与契约、L3 属性视图、L4 同步/快照/加密、L5 CLI/MCP/server | Go |
| 前端 | L6 编辑器内核、L7 UI 框架与配置、L8 Electron 宿主与打包 | TypeScript / Electron |
| 横切 | L9 i18n 与文档、L10 CI/测试/发布 | 多语言 |
| **交互与状态** | **L11 交互与状态**（横跨 L6 模板、L9 语言文件与宿主键盘/焦点） | TypeScript + i18n |

---

# 第一组 内核（Go）

## L1 数据与索引

- **关键路径**：`kernel/model`、`kernel/sql`、`kernel/treenode`、`kernel/filesys`
- **权威源**：块类型与容器能力看 `treenode` 的类型方法；索引写入路径看 `sql/upsert.go` 的
  `insertTree0` 与其上方的忽略判断；磁盘格式看 `filesys` 的 `.sy` 读写
- **高发形态**：
  - 索引层面「先破坏再判断」，使命中忽略规则的文档丢失属性/标签 → D1、D1j
  - 闭合集合漏掉上游新增的块成员（块类型、容器类型、可编辑类型）→ D3
  - 异步入队吞掉落盘错误，调用方据返回值推断成功 → D1i、D1m
  - 聚合方向反转（`element += accumulator`）→ D4
- **既有校验器**：`gofmt`；`go test -tags "fts5 sqlcipher" ./...`（工作目录 `kernel/`）
- **取证陷阱**：
  - **游离行（detached）不在 `blocks` 表**，SQLite 查不到；涉及 AV 行去重必须走 API 扫描
  - 内核测试缺 `-tags "fts5 sqlcipher"` 时大量测试**静默跳过**，看到「全绿」不等于跑过
  - 不要编译内核二进制，也不要重启正在运行的内核（`AGENTS.md`）

## L2 API 与契约

- **关键路径**：`kernel/apicontract`、`kernel/api`、`docs/API*.md`、petal 仓库
- **权威源**：`kernel/apicontract` 的定义（经 `contractHandler` 绑定）。
  **`schema.json`、前端 `types/api/index.d.ts` 与 `docs/API*.md` 都由契约生成，与 DTO 同源，不构成独立权威侧**
- **高发形态**：
  - 手写 DTO 漏字段，标准 `encoding/json` 无 `DisallowUnknownFields` → 静默丢字段 → D3c、P15、P27
  - 适配层新增规范化标记，改变了密码学派生等安全敏感的既有输入 → D1n、P38
  - 路由漏挂中间件（如 `CheckReadonly`）→ D1d 变体
  - 契约变更未同步 petal 与文档 → G1、G2
- **既有校验器**：`pnpm run api:generate --petal ../../petal`、`pnpm run api:check --petal ../../petal`（工作目录 `app/`）；
  `go test ./apicontract/...`（工作目录 `kernel/`）；`TestAPIContractRouterCoverage` 双向覆盖
- **取证陷阱**：
  - `legacy_routes.json` **只删不增**；新增无类型路由会被 `CheckRoutes` 拒绝
  - 不要用 `any` 或类型断言绕过契约检查
  - `mcp_siyuan_http_request` **禁止访问 `127.0.0.1`**，本机取证改用 PowerShell `Invoke-WebRequest`
  - 本机内核 `http://127.0.0.1:6806` 可能无需 token 即可 POST
  - `/api/transactions` 载荷必须带 `reqId`
  - **字段名陷阱**：AV 相关端点用 `avID` 而非 `id`；传错会 panic，但 handler 的 defer 仍返回
    `{code:0, data:null}`，极易误判为成功
  - 中间件链是 `CheckAuth → CheckAdminRole → handler`，**角色可达性必须先按顺序核对**，
    否则会把「`--readonly` 下的脏写」写成越权（已列入已知误报）

## L3 属性视图引擎

- **关键路径**：`kernel/av`、`app/src/protyle/render/av`
- **权威源**：`av.Value` 结构（`kernel/av/value.go`）；计算算子的量纲/格式取**同一 `switch` 内的兄弟分支**
- **高发形态**：
  - 同一算子在多条实现路径上的量纲/格式漂移（整数除法截断）→ D1c、P18
  - 汇总/模板读错字段（`content` 与 `formattedContent` 的消费方不同）→ 修复必须回读**消费端**
  - `avID` 与「数据库块 ID」混用 → A
- **既有校验器**：`go test ./av/...`（工作目录 `kernel/`）
- **取证陷阱**：
  - **`avID` ≠ 数据库块 ID**；`renderAttributeView` 的 `id` 参数传 avID
  - 游离行不在 SQLite，去重必须用 `renderAttributeView` 扫，不能靠 SQL
  - 并行的 `item_update` 会互相覆盖（同一次 AV 全量写盘）→ 必须串行
  - 页脚计算与隐藏列 MCP 未暴露，需 `/api/transactions` 的 `setAttrViewColCalc` / `setAttrViewColHidden`
  - **修量纲时必须逐项定性**：排序不受影响、筛选阈值与底部 Sum/Average 会受影响、
    模板字段读原始 `content` 故只补格式无效、无需数据迁移

## L4 同步 / 快照 / 加密

- **关键路径**：`kernel/model/repository.go`、同步实现、`kernel/model/crypto.go`、`kernel/av/encrypted_hook.go`、
  外部 `dejavu`、`docs/ENCRYPTED-NOTEBOOK.md`、`docs/WORKSPACE.md`
- **权威源**：同步忽略规则集合；**加密格式版本与 AAD 语义**（`AGENTS.md` 第 1 节是硬约束）
- **高发形态**：
  - 忽略规则在两侧漂移 → A、B
  - 快照统计聚合方向反转 → D4
  - 格式变更破坏既有密文可读性、或让迁移不可恢复 → I1、I2、I3
  - 把「设备本地的清理历史」误当可恢复手段 → 见下
- **既有校验器**：`go test ./model/...`；格式回归夹具（`AGENTS.md` 要求用**上一版格式**的夹具覆盖读/导出/历史/备份/恢复）
- **取证陷阱**：
  - `util.HistoryDir = WorkspaceDir/history`，而 dejavu 只遍历 `data/` →
    **clean 历史是设备本地的，不随同步走**；多设备下删除不可恢复
  - `clearOutdatedHistoryDir` 会按 `Conf.Editor.HistoryRetentionDays` **整目录删除**
  - **忽略集合变动会导致其它设备签出时删除文件** —— 本仓库最高危的改动面之一
  - 加密笔记本是**已发布特性**，既有密文是兼容性基线；不得要求用户删除或重建，
    不得重新生成 MasterSalt 或丢弃密钥来绕过不兼容
  - 未知格式、损坏、认证失败必须**保留原始数据并返回错误**，不得回退明文或绕过认证

## L5 CLI / MCP / server 装配

- **关键路径**：`kernel/cli/cmd`、`kernel/mcp`、`kernel/server/serve.go`、`kernel/api/router.go`
- **权威源**：cobra 命令定义；路由表 + `apicontract`；MCP 工具的租约白名单
- **高发形态**：
  - CLI 子命令**假成功**（错误只经 WS 推送，CLI 进程没有接收方）→ D1m、P35
  - MCP 白名单漏项（如缺加密租约）→ D3
  - 库默认白名单被选项整体覆盖（`gzip.WithExcludedExtensions` 是赋值语义）→ P36
  - 谓词通配符未转义（`LIKE` 的 `%` / `_`）→ P37
- **既有校验器**：`go test ./api/... ./server/... ./cli/...`（工作目录 `kernel/`）
- **取证陷阱**：
  - `recover` 中间件会把 panic 静默转成 2xx，**严重度看 panic 之前是否已产生副作用**
  - `mcp_siyuan_sql` 只暴露主库（`blocktrees` 表不可查）；页签项 `type='tab'` 只能在 `blocks` 表验证
  - CLI 的 `--help` 文案常与真实枚举不同步，**不能当权威源**

---

# 第二组 前端（TypeScript / Electron）

## L6 编辑器内核（Protyle）

- **关键路径**：`app/src/protyle`（`render/`、`wysiwyg/`、`util/`、`undo/`、`render/av/`、`export/`）
- **权威源**：
  - **DOM 契约（`data-type`）的权威源是 Lute 输出的 NodeType**，不在前端。
    前端只有散落的裸字面量——实测 `app/src` 下约 **2000 处 `data-type` 引用、
    85 个不同值**，而无任何常量表或类型约束。这是判据 A 里风险最高的一类
    （「裸字符串，无任何校验」）。用 `scan_dom_type_literals.py` 提取闭合集合后与 NodeType diff
  - 同一控件在多视图中的取数/取值实现（表格 vs 画廊 vs 看板）——三者是**互查的权威侧**
- **高发形态**：
  - 重建 / 重渲 / 清空时状态丢失（写死初始值而非读当前值）→ C、P8、P26
  - 同族多实现里唯一一处读错 DOM 属性（`contenteditable` 的 div 读 `.value`）→ D1e、P20
  - 动态插值未转义 → F、P9
  - 定位 / 折叠等**临时展现态没有跨重渲载体** → P26
  - `data-type` 闭合集合漏掉 Lute 新增的节点类型 → D3、P14
- **既有校验器**（必读：`pnpm run lint` **会改写文件**，只读审计用下面的等价形式）：
  - `npx tsc -p tsconfig.typecheck.json`（应用代码类型）；`npx tsc -p tsconfig.api.json`（API 契约类型）
  - `npx eslint .`（**不加 `--fix``— 加了就是修复模式；`pnpm run lint` = typecheck + `--fix`）
  - `pnpm test`（`node --test`；会重写 `app/pnpm-lock.yaml`）
- **取证陷阱**：
  - 编辑器是**虚拟滚动**，`querySelectorAll` 拿不到视口外的块 → 必须滚动后分两次采样
  - `/// #if MOBILE` / `/// #if !MOBILE` 是**编译期剔除**，跨端对比前先 grep 保护块，
    否则会把「该端根本没有此设置」写成漏实现（已列入已知误报）
  - 移动端与桌面端用**不同模板**，`previousElementSibling` 指向的对象可能不同
  - 前端测试的桩是手写白名单，源码新增一个 import 就会让多个测试文件一起挂 → G3
  - `--test` 的 glob 包含 `tests/**/*.test.js`，而 `app/build/` 下的构建副本里也有同名目录 →
    构建产物会被当成测试收集，制造与源码无关的失败。取证前先把 `build/` 移开

## L7 UI 框架与配置

- **关键路径**：`app/src/layout`、`app/src/config`（含 `entryVisibility`）、`app/src/menus`、
  `app/src/dialog`、`app/src/util`、`kernel/conf`
- **权威源**：可配置桌面菜单项与停靠项的 `data-id` / `data-type` →
  `app/src/config/entryVisibility/catalog.ts`；配置字段集合以**内核持久化 struct** 为准
- **高发形态**：
  - 手写配置登记表与实际菜单声明漂移 → D1、P21（`catalog.ts` 漏项或含幽灵键）
  - 前端有键、内核 struct 无字段（静默无效的开关）→ D3c、P27
  - 只读守卫缺位或**位置漂移**（副作用夹在守卫与动作之间）→ D1d、D1j、P30
  - 设置面板 textarea 分支未转义 → F
- **既有校验器**：
  - `npx tsc -p tsconfig.api.json`（配置字段与契约类型）
  - `npx eslint .`（只读）；entryVisibility 一致性测试（catalog ↔ 菜单声明 ↔ 顺序迁移）
  - **不要**在只读审计时跑 `pnpm run lint`（带 `--fix`）
- **取证陷阱**：
  - 配置命名空间是**整体写入**：前端缺字段会让「对象深比较」保存守门**恒不成立**，
    把「显示错误」升级为「每次关对话框都无谓落盘」
  - 布尔字段改可选指针（`*bool` + `omitempty`）时，**老配置该对象非 nil**，
    用普通 `bool` 会把存量用户静默改成默认关
  - `catalog.ts` 的顺序定义内置顺序与「新条目并入既有 profile 的位置」，不是纯展示；
    分隔符必须有稳定 `data-id` 并登记
  - 隐藏是靠 catalog 有该 path 时才生效（未知 id 宽松放行），漏登记等于守卫失效
  - L7 的 `data-type` 大量用于**非块** UI 标记（`av-*` 系列、`available-fonts`、
    `backlink` 等），它们与 L6 的块类型**共用同一个属性名**。
    用 `scan_dom_type_literals.py` 时必须分别看待：`--kind node` 只看 `Node*`，
    其余值需逐个人工确认（脚本会列入「仅出现一次的值」段）

## L8 Electron 宿主与打包

- **关键路径**：`app/electron`、`electron-builder*.yml`、`app/nsis`、`app/build`、`Dockerfile`
- **权威源**：宿主页面配置（`webPreferences`）与 `localPages` 白名单
- **高发形态**：
  - 同类宿主页面的配置不对称（9 处有 `nodeIntegration`，唯独 boot window 没有）→ D1g、P25
  - 平台/宿主环境假设（注册表、换行符、临时目录归属）→ E2
  - 构建产物被测试框架收集成假失败 → G4 变体
- **既有校验器**：无专用；靠 `npx tsc -p tsconfig.typecheck.json` 与人工核对
- **取证陷阱**：
  - 本机 `app/electron/*.js` 检出为 **CRLF**（`core.autocrlf=true`）；`.gitattributes` 的
    `*.ts text eol=lf` 只保证 TS，**按 `"\n"` 切片源码的测试在本机必失败**
  - `app/build/win-unpacked` 是构建副本，会被 `node --test` 收集 → 制造与源码无关的失败
  - 远端/降级路径是这类缺陷的**唯一触发场景**，本地常态下看不到

---

# 第三组 横切

## L9 i18n 与文档

- **关键路径**：`app/appearance/langs/*.json`、`app/guide/`、`docs/`、`scripts/check-*.py`
- **权威源**：`en.json` 的键集合；用户指南的格式规范见 `docs/SY-FORMAT.md`
- **高发形态**：
  - 键缺失或多余（前端键集合 ⊆ 内核集合的契约）→ A、D3c
  - `_kernel` 整数键的**占位符顺序**与 `%v` 无有效校验 → H 类契约缺口
  - 术语约束漂移（`zh-TW` 必须用「區塊」而非「塊」）→ D3
  - 设置项说明以句号结尾、用 Unicode 省略号 → 格式约束
  - **多语言文档的结构与标识符漂移**（`docs/` 下的 `X.md` / `X.<lang>.md`）→ A、D3
- **既有校验器**：`python scripts/check-lang-keys.py`；`python scripts/check-translations.py`；
  多语言一致性用 `scan_doc_parity.py`
- **取证陷阱**：
  - 新键加在对象**顶部**；**例外**：`_kernel` 内部在**末尾**追加下一个递增整数键
  - 缩进用 **tab**（每层一个）
  - 各语言必须真翻译，不得复制同一段文本
  - 占位符必须保留 `en.json` 的参数位置与动词；顺序需要变化时用显式索引（`%[4]s`）
  - `check-translations.py` 用 `sorted()` 抹掉顺序、正则漏 `%v`、且不在 CI ——
    **它不能作为「占位符契约已被校验」的证明**（这是它自身的契约缺口）
  - 在默认 GBK 控制台运行会 `UnicodeEncodeError`，需 `PYTHONIOENCODING=utf-8`
  - `docs/API*.md` **不是生成物**：`apigen` 只写 `app/src/types/api/index.d.ts`、
    `kernel/apicontract/schema.json` 与 petal 的 `index.d.ts`——三语 API 文档是手写各自维护的，
    所以版本间漂移不会被任何生成步骤发现。实测基线：10 组文档中 **5 组有真差异**
  - 一致性的两类比对**缺一不可**：只看标识符会漏掉「少一整节」，只看标题数量则无法定位缺什么
    （实测：三语端点集合一致都是 79 个，但 `API.ja.md` 的 `###` 少 1 个——少的是说明性章节）
  - **交叉引用被本地化是正确行为**（中文版指向 `X.zh-CN.md`），一致性检查必须配对抵消，
    否则 SY-FORMAT / TAB-BLOCK / WORKSPACE 三组会各报 1 条假差异

## L10 CI / 测试 / 发布

- **关键路径**：`.github/workflows`、`app/tests`、`app/package.json`、`scripts/`
- **权威源**：CI 配置里声明的执行集合；测试运行器的**实际**收集结果
- **高发形态**：
  - 白名单式 CI 与全量测试集漂移（本地红、CI 绿）→ G4
  - 测试替身白名单过时 → G3
  - 测试环境前提互相矛盾（夹具临时目录 × 硬编码路径黑名单前缀）→ G4 增补
  - 构建产物被测试框架收集 → 假失败
- **既有校验器**：`go test -tags "fts5 sqlcipher" ./...`（`kernel/`）；`pnpm test`、`pnpm run lint`（`app/`）
- **取证陷阱**：
  - **CI 覆盖 ≠ 本地覆盖**；「本地红、CI 绿」本身就是独立发现，不是噪声
  - `pnpm test` 会重写 `app/pnpm-lock.yaml`
  - **禁止** `pnpm build`（会与开发者的 `pnpm dev` 冲突产生坏包）；**禁止**编译内核
  - 判定 `fixed` 必须以**最后一个引用该 issue 的提交的 CI 结论**收口，
    提交信息与维护者评论都不算
  - 测试运行器的**汇总行**必须读全，不能用输出尾部代替（曾因此把 13 处失败写成 1 处）

---

# 第四组 交互与状态（跨前端与 i18n）

## L11 交互与状态

> **为什么单列且编号不连续**：交互行为天然横跨 L6（前端模板）、L9（语言文件）与宿主
> （键盘 / 焦点），按目录归属会同时落进三层而哪一层都不完整。它也是**唯一一类
> 鼠标操作下完全不可见的缺陷**，因此需要独立的权威源与取证方法。

- **关键路径**：`app/src/protyle/**`（编辑器交互）、`app/src/layout/dock/**`（面板与页签）、
  `app/src/dialog/**`、`app/src/menus/**`、`app/src/mobile/**`（键盘与触摸）、
  **`app/src/assets/scss/**`（应用样式，56 个文件）**、`app/appearance/langs/*.json`

  > **样式位置是个容易找错的地方**：`app/appearance/themes/` 下只有两个 ~10KB 的
  > 颜色变量文件（`daylight` / `midnight` 的 `theme.css`），**不是应用主样式**。
  > 真正的主样式在 `app/src/assets/scss/`（sass-loader + MiniCssExtractPlugin 编译）。
  > 只扫 `appearance` 会得出「本仓没有焦点相关 CSS」的错误结论。
- **权威源**：
  - **同族互查**——多个列表视图 / 多个面板 / 多个对话框之间的行为应当一致；
    「某一处有、另一些没有」即候选（这是判据 D1 在本层的应用）
  - **既有交互约定**——对话框的焦点回位、菜单的 `Esc` 关闭、破坏性操作的确认。
    权威侧是**同族中已实现的那一处**，不是审计者的偏好
  - **`en.json` 的键集合与各语言实际长度**（判据 I4 的输入）
- **高发形态**：
  - UI 状态矩阵（空 / 加载 / 错误 / 只读 / 超长）在兄弟实现之间覆盖不一致 → I1、D3
  - **交互态残留**：异常路径提前返回，`loading` / `disabled` / 遮罩 / 拖拽占位不被清理 → I2
  - **焦点与键盘不可达**：新增入口只在 `mousedown` / `click` 里处理、对话框关闭后焦点不回位、
    纯图标按钮无可访问名、焦点指示器被 `outline: none` 移除而未给替代 → I3
  - 受约束容器（`<option>` / `nowrap` / `ellipsis` / 固定宽度）配长译文溢出 → I4
  - 破坏性入口的确认 / 撤销不一致 → I5、D1
- **既有校验器**：`tsc` / `eslint` / 单测**都不看这层**。两个本 skill 的脚本只覆盖其中两项：
  - `scan_i18n_text_expansion.py --langs <langs> --source <src> --styles <scss>`
    覆盖 I4；**`--styles` 不可省**：约束写在样式文件里，只给 `--source` 会系统性低估候选
  - `scan_a11y_antipatterns.py --root <src> --styles <scss>` 覆盖 I3 的三类可靠形态
    （K2 正整数 `tabindex` / K5 `outline:none` 无替代 / A6 纯图标按钮无可访问名），
    其余反模式只给提示位点
  - `scan_focus_coverage.py --root <src> --styles <scss> --styles <appearance>`
    覆盖**焦点可见性**（判据 I3 ⑤）。本仓库实测：1103 个表单控件使用点中
    641 个有焦点指示、**462 个没有**（含 39 条 vendored PDF.js，自研 423 条）。
    **四个判定前提都是实测写错过才对的**：SCSS 嵌套的后代语义、`transform` 也算指示、
    按完整类集合而非单类判定、兜底按真实标签匹配。详见脚本 docstring 的陷阱表
  - I1 / I2 / I5 **无任何机械手段**，只能语义判断 + 真实渲染取证——这正是本层值得单列的原因

  **设计令牌契约（判据 A 在本层的应用）没有脚本**，用三条件合取人工判：
  ① 引用侧无 fallback ② 所有样式根（含主题）无定义 ③ 源码里从未提及。
  本仓库实测：192 个无 fallback 的引用 → 条件 ② 排除 167、条件 ③ 排除 20（写入）+3（仅提及）
  → 只剩 **2 条候选**，且回读后均为移植样式里的死规则。
  曾为此写过专用脚本，因**产出太低已移除**（第二十三轮）；检查法保留在本节与 SKILL.md 判据 I。
- **取证陷阱**：
  - **读数不够**：状态残留与焦点问题常只在**特定操作顺序**下出现
    （先失败一次再成功、中途切走再回来），静态阅读看不到
  - **焦点问题必须用键盘走**（`Tab` / `Shift+Tab` / `Esc`）。鼠标操作会把焦点问题完全掩盖
  - **本仓库的焦点可见性机制（判焦点缺口前必读）**：`util/_reset.scss` 对
    `button, input, select, textarea` **一律 `outline: none`** → 焦点可见性完全依赖
    各组件自己定义 `:focus`，没定义就是「看不见焦点」；且全仓**无任何全局兜底**。
    所以「该组件没有 :focus 规则」在本仓库是一个真信号，而不是「浏览器默认会画轮廓」
  - **判「有没有可见变化」不能只看 outline / box-shadow / border / background**：
    `.b3-slider` 的焦点指示是 `::-webkit-slider-thumb { transform: scale(1.5) }`（滑块放大）。
    `transform` / `filter` / `opacity` / `color` 同样能构成可见变化
  - **判定单位是「元素上的完整类集合」，不是单个类**：元素常带多个类，
    焦点样式可能来自兄弟类（`.block__icon.b3-tooltips` 的样式来自 `.b3-tooltips:focus-within`）。
    **且夹具要能区分这两种逻辑**：若被覆盖的类恰好按字母序排在最前，
    「按类集合」与「只按第一个类」会得出相同结果，用例就不承重
  - **SCSS 解析必须实现真正的嵌套语义**：含 `&` 则替换，**不含 `&` 则作为后代拼接**。
    只替换 `&` 会让不含 `&` 的子选择器丢掉祖先，把局部规则提升成全局兜底，
    从而把真缺口判成「已覆盖」（实测：`.protyle-preview__action button:focus` 被读成全局 `button:focus`）
  - **全局兜底必须按元素的真实标签匹配**：`.b3-switch` 是 `<input>`，
    而全局规则是 `button:focus`，根本不匹配。把「存在某个原生标签的焦点规则」当作兜底
    会把 `<input>` 的缺口全部抹掉
  - **contenteditable 内容区的 `outline: none` 是正确的**：编辑器与渲染容器的
    焦点指示是光标/选区，不是焦点环
  - **CSS 自定义属性是 JS→CSS 的运行时通道**：样式表里查不到定义 **不等于** 没有任何人定义它。
    实测本仓库的写入形态至少有五种：`setProperty` / `removeProperty`（含先收集名字数组再
    `forEach(n => style.removeProperty(n))` 的间接形式）、样式对象键 `["--x"]:`、
    模板串里的内联 `style="--x:..."`、注入的完整 CSS 规则块、`cssText`。
    逐条回读前，**不要把「无定义」当成结论**
  - **SCSS 的状态样式主要写成嵌套的 `&:伪类`**，选择器文本里**不含组件类名**。
    只搜选择器文本时会得出「该组件没有 hover / focus」的错误结论——
    实测 `.b3-button` 按选择器文本判为缺 `:hover/:active/:focus`，按大括号配对后
    实际拥有 `:active,:disabled,:focus,:hover`。全仓嵌套 `&:hover` 154 处、
    `&:focus` 32 处、`:focus-visible` 22 处、`:active` 16 处、`:disabled` 7 处，
    **嵌套是主流写法**。判状态覆盖必须做括号配对并合并「选择器文本」与「块体内嵌套」两种形态
  - **组件调用点的属性差异几乎都是合法差异**：先用覆盖率把「契约属性」与「调用点自有
    `data-*` 标识」分离（~100% 才是契约）。实测 `.b3-switch` 的 `type` 覆盖 114/114、
    `.b3-tooltips` 的 `aria-label` 覆盖 159/159，而多数组件**根本没有契约属性**
  - `<option>` **不换行**：`<select>` 的下拉项是天然的受约束容器。实测历史面板的操作筛选
    `<select>`（`app/src/history/doc.ts:183-187`、`app/src/history/history.ts:534-540`）
    有 7 个 `<option>` 取自 `history*` 一族键，而 `de` / `ar` 的译文含 `(sync)` 之类的
    附加文本、长度约为英文的 2–4 倍（`en="sync"` → `de="synchronisieren (sync)"`）
  - **文本膨胀只在部分语言显形**：实测 `ja` / `zh-CN` 各仅 1–2 个受约束候选，
    而 `de` / `es` / `fr` / `ru` 各 80+、`ar` 76。**只在自己惯用的语言下看会完全漏掉本层缺陷**
  - **移植样式里的令牌缺口先看引用方是否还在**：`app/src/assets/scss/pdf/_pdf.scss`
    是从 Mozilla PDF.js 移植的（文件头 Apache-2.0），其 `--loading-icon` / `--main-color`
    在 PDF.js `viewer.css` 的 `:root` 里定义、移植时未带上；但唯一使用点
    `.toolbarField.pageNumber.visiblePageIsLoading` 的类名在全仓出现 **0 次**、
    `#errorWrapper` 无 JS 取消 `hidden`。**无消费方即无业务表现**，属观察项
  - 虚拟滚动、`/// #if MOBILE` 编译期剔除、跨端模板差异见 L6

---

# 资源与生命周期检查点（**待实证**）

> 本节由通用运行时经验提出，**本仓库尚无确认的缺陷实例**，因此**不占用判据字母、也没有 P 条目**。
> 按模式库「从一次已确认的缺陷出发」的扩充规范，取得实例后再升级为正式判据。
> 命中时必须走完整挑战门——缺少本仓库先例意味着它更容易是「可以更好」而非缺陷。

长驻进程（内核）与长生命周期页面（编辑器）里，资源的**创建点**与**释放点**必须成对且可达。

| 检查点 | 在哪看 | 信号 |
|---|---|---|
| 订阅 / 定时器 / 句柄未释放 | L6 编辑器（`setInterval`、rAF、事件监听、`context.CancelFunc`）、L5 server 装配 | 销毁路径（`destroy` / 页签关闭 / 组件移除）未覆盖全部创建点。**同族实现里只有某一处漏了 `destroy` 是最强形态** |
| 集合无上限增长 | L7 历史栈与已关闭列表、L1 缓存、日志缓冲 | 只有 `push` 没有裁剪。**与判据 D4 分工**：D4 问「裁剪端是否与消费端同端」（已有界但裁错端），此处问「**是否存在界**」 |
| 并发资源泄漏与顺序 | L1 索引队列、L5 异步任务 | goroutine 无退出信号（`goleak` 可检出）、锁持有跨越 I/O、`sync.Pool` / 缓存被并发写入 |

**取证**：前端在销毁前后采样监听器/定时器是否仍在活动；Go 侧优先构造最小复现，
用 `go test -race` 或 `goleak`，不要通读全包。

# 定位参照帧检查点（**待实证**）

> 对应 `AGENTS.md` 第 7 条的硬要求：「改 `position` / `transform` / `contain` / `overflow` 时，
> 检查对**后代定位参照帧**、overlay 覆盖、裁剪的影响」。
> **本仓库尚无确认的缺陷实例**，因此按既有约定不占用判据字母、也没有 P 条目。
> 但机制与判定方法**都已实测**，命中时可直接用。
>
> **为什么值得单列**：`SKILL.md` 里 `z-index` 与「定位上下文」命中数为 **0**，
> 而它正是本项目明文写进规范的雷区之一——属于「没有既有校验器、也没有判据」的空白。

## 机制：属性表是**实测的**，不是凭记忆

CSS 规定：祖先上存在下列属性时，它成为后代 `position: fixed` 的**包含块**——
fixed 元素不再相对视口，而是相对该祖先定位。

本地 HTML 实测（`offsetParent !== null` 判定，19 个用例）：

| 祖先属性 | 会让后代 fixed 改参照帧 |
|---|---|
| `transform`（非 none） | **是** |
| `filter`（非 none） | **是** |
| `backdrop-filter`（非 none） | **是** |
| `perspective`（非 none） | **是** |
| `contain: layout` / `paint` / `strict` | **是** |
| `will-change: transform` / `filter` | **是** |
| `will-change: opacity` | 否 |
| `isolation: isolate` | **否** |
| `opacity: 0.99` | **否** |
| `position: relative` / `absolute` + `z-index` | **否** |
| `position: sticky` / `absolute` | 否 |
| `mix-blend-mode` / `mask-image` | 否 |

> **这张表最容易记错的地方**：`isolation` / `opacity` / `position + z-index`
> 都会创建 **stacking context**，但**不创建包含块**。
> 把「创建 stacking context」等同于「会困住 fixed」会产出大量假阳性——
> 判这件事只能看**包含块**。

## 业务表现（实测，不是推断）

同一段 CSS 的 fixed 元素（`top:0; left:0`）：

| 祖先 | `offsetParent` | 元素实际 `getBoundingClientRect().top` |
|---|---|---|
| 无创建包含块的属性 | `null` | **0**（视口左上角，符合预期） |
| `transform: translateX(1px)` | 宿主容器 | **400**（容器所在位置） |

**偏了 400px**——元素从「固定在视口」变成「固定在容器里」。

## 判定方法（零假阳性，但必须做对照组）

```js
[...document.querySelectorAll("*")]
  .filter(el => getComputedStyle(el).position === "fixed" && el.getClientRects().length)
  .filter(el => el.offsetParent !== null)   // 规范：未被围住的 fixed 元素 offsetParent 为 null
  .map(el => [el.className,
              getComputedStyle(el.offsetParent).transform,
              getComputedStyle(el.offsetParent).filter,
              getComputedStyle(el.offsetParent).contain,
              getComputedStyle(el.offsetParent).willChange]);
```

**对照不可省**：同一次执行里注入「有 `transform` 祖先」与「无 `transform` 祖先」两个 fixed 元素，
确认前者 `offsetParent !== null`、后者 `=== null`，再报真实数字。
否则「0 个」无法区分「真的干净」与「方法失效」——实测必须一正一反才敢下结论。

## 静态规模（本仓库当前，2026-09-14）

| 项 | 数量 |
|---|---|
| 会创建包含块的声明 | `transform` 113 条、`filter` 21 条（含 `backdrop-filter` 12）、`will-change` 8 条、`contain` 6 条 |
| `position: fixed` 选择器 | 51 条，另有 5 处内联 `position: fixed` |
| `position: sticky` | 16 条 |
| `z-index` 取值 | 24 种；动态分配基数是 **10**（`app/src/index.ts:295`），硬编码最大 `1000000`（`.tooltip`） |

**注意 `will-change` 那一组是「禁地」**：`.mobile-topbar`、`.mobile-bottom-bar`、`.side-panel`、
`.b3-menu--sheet`、`#editor > .protyle-breadcrumb` 都是移动端**容器**且带 `will-change: transform`。
它们当前的后代里没有 fixed 元素，但将来在其中插入 `position: fixed` 的元素会**静默跑偏**。
这是判据 E 的隐式假设形态：**容器的这个属性构成了后代必须遵守的隐含前提**。

**权威侧（本仓库已有的正确做法）**：`.av__mask` 用
`document.body.insertAdjacentHTML("beforeend", ...)` 挂到 body 下
（`app/src/protyle/render/av/cell.ts:648`），因此在任何容器里都不会被围住。
同族互查时以它为准。

## 为什么不做脚本

静态判定需要**后代的 DOM 祖先链**，而在 SiYuan 里这由模板字符串拼装
（`insertAdjacentHTML` / `innerHTML` / `innerHTML =`），无法可靠还原嵌套关系。
运行时判定已零假阳性、只需一次 `evaluate`——按 `SKILL.md` 的脚本准入标准
（零产出或极低产出的不进来），它更适合放在**验证闭环**里当必查项，
而不是占一个脚本位并承担维护成本。

# 跨层连带检查表

改一处之前，先按此表确认要不要连带改别处。本表是「爆炸半径」的可操作版本
（修复流程见 [修复与架构调整手册](./repair-playbook.md)）。

| 改动面 | 连带必查 |
|---|---|
| 配置结构体字段 | `apicontract` 镜像、前端类型、petal 声明、老配置反序列化路径 |
| 同步忽略集合 | 其它设备签出会删除文件、加密笔记本、快照差异、`docs/WORKSPACE.md` |
| i18n 键 | 全部语言文件、`_kernel` 整数键、用户指南、快捷键文档 |
| 块类型 / 容器能力 | `treenode` 类型方法、SQL 索引、AV、导出、大纲、模板渲染 |
| AV 列量纲 / 格式 | 消费端字段（`content` vs `formattedContent`）、筛选、排序、底部汇总、模板、导出 |
| 菜单 / 停靠项 `data-id` | `entryVisibility/catalog.ts`、既有 profile 的可见性与顺序迁移、插件槽位 |
| API 契约 | `apicontract` 定义、`docs/API*.md`、petal、生成物、兼容性测试与回归夹具 |
| 加密相关 | 格式版本、AAD 语义、密钥派生、备份/历史/恢复路径的夹具 |
| 文档 / 用户指南 | `docs/SY-FORMAT.md`、快照 `kbd` 写法、列表项不得以句号结尾 |

# 环境与取证前提（本机实测）

- 内核测试需 `-tags "fts5 sqlcipher"`；单包约 5s（编译缓存后 <1s）
- 内核 `http://127.0.0.1:6806` 可能无需 token；`mcp_siyuan_http_request` 禁止访问 `127.0.0.1`
- 含非 ASCII 的 PowerShell 载荷必须**写 UTF-8 文件 + `-InFile`**，否则中文被写成 `?`
- PowerShell 5.1 的 `>` 重定向默认写 **UTF-16LE**；`gh api --jq .body` 的中文在默认控制台会乱码，
  回读比对要走 Python `subprocess` 取字节后按 UTF-8 解码
- 取证优先选**零副作用**场景（预期失败的写入）；成功型写入需建临时对象并回删
- 临时目录用唯一名，清理时**只删自己建的文件**，绝不递归删整个 `audit-r<N>`
- 本机 `mime.TypeByExtension(".jpg")` 返回 `application/jpg`（Windows 注册表覆盖内置表），
  相关测试失败**非回归**；Chromium 会忽略子资源上的 `Content-Disposition`

# 来源与许可

本文件的层面划分与检查点，是把下列公开 Agent Skill 的方法论**用自己的话重新表述**后落到本仓库结构上，
未复制原文：

| 来源 | 许可 | 借鉴的部分 |
|---|---|---|
| `trailofbits/skills` | CC-BY-SA-4.0 | 差分审查的爆炸半径与测试覆盖、`sharp-edges` 的脚枪 API、`insecure-defaults` 的 fail-open、`variant-analysis` 的变体扫描 |
| `github/awesome-copilot` | MIT | `test-gap-audit` 的测试缺口审计、`docs-sync-audit` 的文档漂移、`poka-yoke` 的「让非法状态不可表达」、`github-actions-hardening` |
| `samber/cc-skills-golang` | MIT | `golang-safety`（nil / append 别名 / 并发 map）、`golang-cli`（退出码与信号）、`golang-database`、`golang-context`、`golang-error-handling` |
| `i18n-agent/i18nstack` | MIT | 占位符漂移与 locale 键完整性校验的思路 |
| `github/awesome-copilot` 的 `a11y.instructions.md` | MIT | 无障碍反模式分类（语义 S / ARIA A / 键盘焦点 K / 表单 F / 视觉 V）、ARIA 五规则、键盘交互参考表 |
| `github/awesome-copilot` 的 `accessibility-runtime-tester.agent.md` | MIT | 运行期无障碍测试流程（键盘优先、焦点管理、动态 UI、复合控件）与两条硬约束：「不得把推测的辅助技术行为当作事实」「Lighthouse 通过不是无障碍的证明」 |
| `github/awesome-copilot` 的 `web-design-reviewer` | MIT | 多视口检查与「修复→重验」闭环；**其外观部分（配色/间距/视觉一致性）不属本 skill**，只借了「截图前后对比 + 一次只修一个问题」的工作方式 |

**未采纳的 UI/UX 来源（附理由，避免重复评估）**：

- `anti-ui-slop`（MIT）：核心价值是「用真实界面参考做产品化的视觉设计」，
  且需要付费的 UIZZE MCP。**属外观设计，不在本 skill 范围**。
- `premium-frontend-ui` / `gsap-framer-scroll-animation` / `anti-ui-slop` 的视觉与动效部分：
  属外观设计实现指南，不在本 skill 范围。
- `penpot-uiux-design`（MIT）的 **Penpot MCP 部分**：它从设计文件里读取颜色集、文本样式与组件，
  本仓库没有设计文件也没有该 MCP。**但其 Design Tokens 与 Component Checklist 的概念已被
  部分采纳**（见下行），因此它与上面两个不再同类。
- `oo-component-documentation`（MIT，面向对象组件文档模板，含 Create/Update 两模式）、
  `salesforce-component-standards`（组件质量标准与组件通信规则）、
  `fluentui-blazor` / `mvvm-toolkit*` / `react19-*` / `react-container-presentation-component`
  （React、Vue、LWC、Blazor、.NET 平台专用）：**本仓库是原生 TypeScript +
  模板字符串 + SCSS，无组件目录、无组件注册表（`components.json` / `COMPONENTS.md` 均无命中），
  这些 skill 的载体在目标仓库里不存在**。其中唯一可迁移的原理——「渲染函数归 `ui`、
  含状态/副作用/异步者归 `features`」——在本仓库的对应物是 `protyle/render/`（纯渲染，
  不得读 DOM / 发请求）与 `protyle/util/`（有副作用）的分工，已作为判据 D 的检查点记录。
- `a11y.instructions.md` 里的 **V（视觉与颜色）与 D（媒体）两类反模式**：
  对比度、只用颜色传达信息、固定字号、动效降级、字幕 —— 这些需要颜色计算与视觉基线，
  取证手段与本 skill 完全不同（axe / Lighthouse / 设计审查），**有意不纳入**。

**部分采纳的 UI/UX 来源**（机制已按本仓库改写，记录以免重复评估）：

| 来源 | 许可 | 采纳的部分 | 改写方式 |
|---|---|---|---|
| `penpot-uiux-design` | MIT | Design Tokens（spacing / typography / color scale）作为设计系统第一层；组件检查清单里的**状态覆盖**（default / hover / active / disabled / loading） | 它靠 Penpot MCP **读取**设计文件中的令牌；本仓库无设计文件，故改写为**源码层可判定**的「引用 / 定义 / 源码写入」三条件合取，落到 `scan_css_token_contract.py` 与判据 I 的 CSS 侧取证前提 |

> 未采纳的部分也要记录理由：该 skill 的 Default Spacing Scale（8px 基）、Typography Scale、
> Color Usage、Common Layouts（375×812 / 1440×900）、以及全部「视觉层级、留白、限制颜色/
> 字体数量」类条目，均属**外观**，按 `description` 的声明不在本 skill 范围内。

`trailofbits/skills` 的**内容**许可为 CC-BY-SA-4.0，与本仓库及目标仓库（AGPL-3.0）不兼容：
**只可参考其方法论，不得把正文整段复制进任一仓库。**

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

## 三个组

| 组 | 层面 | 语言/宿主 |
|---|---|---|
| 内核 | L1 数据与索引、L2 API 与契约、L3 属性视图、L4 同步/快照/加密、L5 CLI/MCP/server | Go |
| 前端 | L6 编辑器内核、L7 UI 框架与配置、L8 Electron 宿主与打包 | TypeScript / Electron |
| 横切 | L9 i18n 与文档、L10 CI/测试/发布 | 多语言 |

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
- **权威源**：渲染契约与 DOM 契约（`data-type`、`data-node-id`）；
  同一控件在多视图中的取数/取值实现（表格 vs 画廊 vs 看板）
- **高发形态**：
  - 重建 / 重渲 / 清空时状态丢失（写死初始值而非读当前值）→ C、P8、P26
  - 同族多实现里唯一一处读错 DOM 属性（`contenteditable` 的 div 读 `.value`）→ D1e、P20
  - 动态插值未转义 → F、P9
  - 定位 / 折叠等**临时展现态没有跨重渲载体** → P26
- **既有校验器**：`pnpm run lint`（工作目录 `app/`）；`pnpm test`（`node --test`）
- **取证陷阱**：
  - 编辑器是**虚拟滚动**，`querySelectorAll` 拿不到视口外的块 → 必须滚动后分两次采样
  - `/// #if MOBILE` / `/// #if !MOBILE` 是**编译期剔除**，跨端对比前先 grep 保护块，
    否则会把「该端根本没有此设置」写成漏实现（已列入已知误报）
  - 移动端与桌面端用**不同模板**，`previousElementSibling` 指向的对象可能不同
  - 前端测试的桩是手写白名单，源码新增一个 import 就会让多个测试文件一起挂 → G3

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
- **既有校验器**：`pnpm run lint`；entryVisibility 一致性测试（catalog ↔ 菜单声明 ↔ 顺序迁移）
- **取证陷阱**：
  - 配置命名空间是**整体写入**：前端缺字段会让「对象深比较」保存守门**恒不成立**，
    把「显示错误」升级为「每次关对话框都无谓落盘」
  - 布尔字段改可选指针（`*bool` + `omitempty`）时，**老配置该对象非 nil**，
    用普通 `bool` 会把存量用户静默改成默认关
  - `catalog.ts` 的顺序定义内置顺序与「新条目并入既有 profile 的位置」，不是纯展示；
    分隔符必须有稳定 `data-id` 并登记
  - 隐藏是靠 catalog 有该 path 时才生效（未知 id 宽松放行），漏登记等于守卫失效

## L8 Electron 宿主与打包

- **关键路径**：`app/electron`、`electron-builder*.yml`、`app/nsis`、`app/build`、`Dockerfile`
- **权威源**：宿主页面配置（`webPreferences`）与 `localPages` 白名单
- **高发形态**：
  - 同类宿主页面的配置不对称（9 处有 `nodeIntegration`，唯独 boot window 没有）→ D1g、P25
  - 平台/宿主环境假设（注册表、换行符、临时目录归属）→ E2
  - 构建产物被测试框架收集成假失败 → G4 变体
- **既有校验器**：无专用；靠 `pnpm run lint` 与人工核对
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
- **既有校验器**：`python scripts/check-lang-keys.py`；`python scripts/check-translations.py`
- **取证陷阱**：
  - 新键加在对象**顶部**；**例外**：`_kernel` 内部在**末尾**追加下一个递增整数键
  - 缩进用 **tab**（每层一个）
  - 各语言必须真翻译，不得复制同一段文本
  - 占位符必须保留 `en.json` 的参数位置与动词；顺序需要变化时用显式索引（`%[4]s`）
  - `check-translations.py` 用 `sorted()` 抹掉顺序、正则漏 `%v`、且不在 CI ——
    **它不能作为「占位符契约已被校验」的证明**（这是它自身的契约缺口）
  - 在默认 GBK 控制台运行会 `UnicodeEncodeError`，需 `PYTHONIOENCODING=utf-8`

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

`trailofbits/skills` 的**内容**许可为 CC-BY-SA-4.0，与本仓库及目标仓库（AGPL-3.0）不兼容：
**只可参考其方法论，不得把正文整段复制进任一仓库。**

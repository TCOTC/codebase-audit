# Go 语言与工具链基线（权威依据来源）

> **何时读**：审计 `kernel/` 的 Go 代码，或需要为一条发现的「预期表现」找**上游权威依据**时。
> 纯前端（TS）轮次不需要。
>
> 本文件**不是判据**：不占判据字母、不配 P 编号。它是核心原则 5「预期表现必须有权威依据」在 Go 侧的取用清单，
> 同时是判据 E（隐式假设）与 H（格式与兼容性）的对照基线。

## 一、先划边界：什么能当权威依据，什么不能

**Go 没有一份叫「官方最佳实践」的单一文档**，官方给出的是一组分工明确的来源。它们必须分两类用——
本 skill 的 `description` 明确**不含代码风格与 lint**。

| 可作权威依据（能推出「这是缺陷」） | 不可作依据（只能推出「换个写法更好」，属 style） |
|---|---|
| **语言语义**：求值顺序、方法集、闭包捕获、`for range` 变量语义、整数溢出与整除截断 | 格式与命名偏好（行长、缩写、注释排版）——交给 `gofmt`，没有讨论空间 |
| **标准库的已文档化行为**：`filepath` 路径语义、`encoding/json` 字段匹配、`errors.Is` 匹配链 | 「更地道 / 更惯用」的写法偏好（`Effective Go` 的多数内容） |
| **官方兼容性承诺**：Go 1 兼容性、`go` 指令决定的语言版本语义 | `Code Review Comments` 中**无行为后果**的条目（如「不用 `panic` 做流程控制」当代码本无流程含义时） |
| **目标仓库 `AGENTS.md` 的明文要求**：如改 Go 代码后跑 `gofmt` | 第三方风格指南（Google / Uber）中本仓库未采纳的条条框框 |

**三类用法必须分开（历史上各踩过一次）**：官方文档能证明「承诺了某能力」或「定义了某语义」；
**不能**证明「某行为是有意设计」（那要看 issue / 提交历史 / 同族实现）；**更不能**证明「这是 bug」。

## 二、官方来源（`go.dev` 域内，Go 团队维护）

| 文档 | 取用方式 | 对应判据 |
|---|---|---|
| [Effective Go](https://go.dev/doc/effective_go) | 语言惯用法的事实标准；判「写法是否违背语言设计意图」 | E |
| [Go Code Review Comments](https://go.dev/wiki/CodeReviewComments) | **最接近官方评审清单**；只取带行为后果的条目（错误处理、`context` 首参、接收者语义、`sync` 用法） | C / D / E |
| [Go FAQ](https://go.dev/doc/faq) | 「为什么这样设计」的权威解释；**反向使用**——阻止把刻意设计判成缺陷 | 挑战门 |
| [Go Doc Comments](https://go.dev/doc/comment) | `// Deprecated:`、`//go:` 指令等注释的机器可读语义 | I |
| [Go Modules Reference](https://go.dev/ref/mod) | `go` 指令、`toolchain`、`replace`、`vendor` 的正式规则 | E / H |
| [Go 1 Compatibility Promise](https://go.dev/doc/go1compat) | 兼容性边界：标准库不做破坏性变更，故「某 API 行为」可当稳定权威 | H |
| [Release Notes](https://go.dev/doc/devel/release) · [Blog](https://go.dev/blog/) · [Wiki](https://go.dev/wiki/) | 版本语义变更与专题（`errors.Is/As`、`context`、`slog`、泛型、profiling） | E2 |

## 三、次一级权威（非 Go 团队，**只作补充，不得与官方并列**）

- [Google Go Style Guide](https://google.github.io/styleguide/go/)：颗粒度比 `Effective Go` 细，含 *Style Decisions* 与 *Best Practices*；**只在本仓库未另行规定、且条目有行为后果时**引用。
- [Uber Go Style Guide](https://github.com/uber-go/guide)：工程边界情况覆盖最好（错误包装、并发、测试、类型嵌入）。
- **Go Proverbs**（Rob Pike 演讲）：`Errors are values`、`Don't communicate by sharing memory; share memory by communicating`、`The bigger the interface, the weaker the abstraction`——用于解释「为什么」，不用于直接立论。
- 书：《The Go Programming Language》（Go 团队成员著）、《100 Go Mistakes and How to Avoid Them》（按反模式组织，适合查漏）。
- `evidence.md` 的既有教训是「文档可用于证明承诺了某能力，不可用于证明某行为是有意设计」；**第三方指南连「承诺」都算不上**，引用时必须显式标为补充依据。

## 四、工具链本身就是规范（Go 的独特之处：风格争论交给工具）

| 工具 | 性质 | 在本 skill 里的用法 |
|---|---|---|
| `gofmt` / `goimports` | 格式无讨论空间 | 目标仓库 `AGENTS.md` 明文要求改 Go 代码后跑 `gofmt` → **违反它属仓库规则违规**，可作 A/D 类证据 |
| `go vet` | 标准库自带的可疑构造检查（printf 格式、锁复制、结构体标签、`loopclosure`） | 若缺陷正是 vet 能抓的形态，说明 **CI 缺这一步**，属独立发现（与 G4「测试不在 CI 执行集内」形态相近，对象是检查器而非测试） |
| `staticcheck` / `golangci-lint` | 非官方但事实标准 | 同上；**不在目标仓库依赖里**，只能用于本机验证假设，不能当作「仓库要求」 |
| `go test -race` | 并发正确性 | 判据 C / E 中并发缺陷的取证手段 |

**本仓库实测事实（2026-10-08）**：

- `kernel/go.mod` 的 `go` 指令为 **`go 1.26.5`**——**语言版本语义以它为准**（见第五节）。
- `.github/workflows/*.yml` 中 `go test` 命中 3 处（`cd.yml:183/191/213`），而 `gofmt` / `go vet` / `golangci` / `staticcheck` **零命中**；
  仓库内亦无 `.golangci*` / `staticcheck.conf` / `Makefile`。对照命令自身的有效性已用 `go test` 命中自证。
- 结论：**Go 侧没有「仓库自带的静态检查器」兜底**（`gofmt` 仅由 `AGENTS.md` 以人工步骤要求）。两点含义：
  ① 判「预期表现」时**只能引上游规范或上游源码**，不能引「本仓库会检查它」；
  ② **「缺 linter 配置」本身不构成缺陷**，不要据此立论——它只是取证前提。

## 五、版本语义变更点（判据 E2 的可操作清单）

**第一步永远是读 `kernel/go.mod` 的 `go` 指令**：语言语义随它变化，与工具链版本无关。
下表**只列已知到 Go 1.24 的变更点**（本 skill 知识的可靠边界）；**1.25 及以后必须查官方 Release Notes，不得凭印象补**。

| 版本 | 变更点 | 为什么会变成缺陷 |
|---|---|---|
| 1.22 | **`for` 循环变量按迭代捕获**（此前三个子句共享同一变量） | 1.22 前广泛用 `v := v` 规避；升级 `go` 指令后，**依赖共享变量语义的代码**（延迟读取循环变量、`t.Parallel()` 子测试、批量 `go func(){ …v… }()`）行为改变。审计闭包 / goroutine 捕获循环变量时**必须先确认 `go` 指令**，再判「这是 bug」还是「`v := v` 只是冗余」 |
| 1.22 | `for range` 支持整数（`for i := range 10`）；`math/rand/v2` | 新写法易被误读为「`range` 一个数字变量」；`math/rand` 与 `math/rand/v2` 混用会使**种子与序列语义不同**（同语义两份实现 → D1） |
| 1.23 | `time.Timer` / `Ticker` 的 GC 与 `Stop`/`Reset` 语义放宽（不再要求 drain 通道） | 依赖「必须 drain」的旧规避代码与依赖「未 drain 即泄漏」的旧判断都不再成立；同族里新旧两种写法并存 → 判据 D1 |
| 1.23 | `iter` / range-over-func；`maps.Keys`/`Values` 返回迭代器；`unique` | 此前无标准实现的语义，很多仓库自写过一份 → **与标准库两份实现**（判据 B / D1），注意 `Keys` 由「返回切片」改为「返回迭代器」是**不兼容变更** |
| 1.21 | 内置 `min` / `max` / `clear`；`slices` / `maps` / `cmp` 标准库 | 包级或文件级**自定义 `min`/`max` 会遮蔽内置**；自写工具函数与标准库同语义同存两份 → 判据 B / D1，需核两者对空切片、`NaN` 的边界是否一致 |
| 1.20 | `errors.Join`、多 `%w`；`strings.CutPrefix`/`CutSuffix`；`context.WithCancelCause` | 错误包装链变化会影响 `errors.Is`/`As` 的匹配结果 → 判据 D1c；`WithCancelCause` 与 `WithCancel` 混用时 `context.Cause` 为 `nil` |
| 1.24 | **`os.Root`**（受限根目录的规范做法） | 直接对应判据 **D1h**（词法路径校验被符号链接绕过）：它是上游给出的正确答案，可作「该用而没用」的依据；**但不构成「必须迁移」的理由**——`AGENTS.md` 的兼容性条款与最小改动原则优先 |

**用法（三步）**：

1. 读 `kernel/go.mod` 的 `go` 指令，确定语言版本语义基线；
2. 取该版本区间的官方 Release Notes 与 `Code Review Comments`，**只取有行为后果的条目**；
3. 与目标实现对对照，写出「同一输入在**下界版本**与**当前版本**下的结论差」——这正是判据 E2 要求的两个取值下的结论差。

**写报告时的引用格式**：权威依据必须落成一句可核对的声明，例如
「`go 1.22` 起 `for` 循环变量按迭代捕获（官方 Release Notes），故此处闭包捕获的是每轮新变量，`v := v` 属冗余而非缺陷」——
不要写「按 Go 最佳实践应当……」。后者按挑战门规则应直接驳回。

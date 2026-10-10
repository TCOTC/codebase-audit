# 运行时量测（结论取决于运行期行为时的取证方法）

> **何时读**：发现的结论依赖**运行期行为**——耗时、内存峰值/驻留、IO 量、落盘次数、
> 阈值上限，以及「看起来成功其实没生效」。静态判据 A–J 判不了的都在这里。
> **分工**：[挑战门](./challenge-gate.md) 审「这个发现成立吗」；本文件管「怎么把运行期行为测准」，
> 免得数字本身是错的、而结论看起来成立。环境搭建与取证前提（构建、基线、产物时间戳）见
> [全栈层面地图](./stack-map.md)；历轮实测数字见 [实证数据](./evidence.md)。

## 第 0 条：先确认被测代码路径真的执行了

这是本文件最重要的一条——**唯一一条「违反它会让后面全部工作白做」的**。同一个会话里踩到三次：

| 表象 | 真实原因 | 正确做法 |
| --- | --- | --- |
| 连续三轮测量里目标文件大小始终不变，我据此认定「写入成功」 | 请求其实**静默失败**（`code != 0` 被我忽略） | 每次调用都断言 `code == 0`，并把 `msg` 打进结果行，失败行直接丢弃 |
| 「一次传入 4.4 万个 id 也能成功返回 4.4 万个块」 | **块缓存命中**，那条 SQL 根本没执行 | 需要测 SQL 路径时**冷缓存**（重启内核）；并区分「返回条数」与「入参数」 |
| 「接口成本与容器规模 C 无关」 | 语料加进了**自定义容器**，而该接口只读**内置容器** → 全部走占位分支 | 先用一个「已知必然命中」的对照输入确认匹配生效 |

统一判据：**任何数字在被解读前，必须有一个「对照组确认路径执行」的证据**——响应码、
返回条数与预期一致、日志里出现预期的那句、或一对已知会命中/不命中的样本。

**推论**：不要用「看起来该有变化」代替检查变化。落盘次数、SQL 执行、缓存命中都要**显式测**
（本仓库用 1 ms 轮询 mtime 数「不同 mtime 的个数」即可证明落盘次数，实测它一次性推翻了我对
「带属性值创建会重复写」的猜测：无属性 1 次、有属性 **2** 次）。

## 仪器与其盲区

先选仪器再谈数字。每个仪器都有**系统性看不见的东西**，用错会得到「没问题」的假结论。

| 仪器 | 看得到 | **看不见 / 陷阱** |
| --- | --- | --- |
| 进程 IO 计数（Python ctypes `GetProcessIoCounters`；PowerShell 用 `Win32_Process`，**`Get-Process` 在 5.1 取不到同名属性**） | 该进程的读写操作数与字节数，适合归因「哪个调用写了多少」 | **mmap 写入**——这正是 `util.WriteFileByMmap` 存在的理由（`kernel/util/mmap.go:37` 注释自陈「几乎不计入 IO 计数」）⇒ IO 计数对写**系统性少报** |
| 系统磁盘计数器（`\LogicalDisk(C:)\Disk Write Bytes/sec`） | 全机写入 | 本机背景噪声 1.5–3 MB/s、6 s 窗口内可有 ~4 MB 突发；**1 KB 文档的一次新建也测出 +3.98 MB** ⇒ 隔离 MB 级以下写入**不可用** |
| Go 堆（`/debug/pprof/heap?debug=1[&gc=1]`） | `Sys`/`HeapAlloc`/`HeapIdle`/`HeapReleased`/`MALLOCS`/`MaxRSS` | `MaxRSS` 是**生命周期峰值**不是当前值；`?gc=1` 后 `HeapAlloc` 上升**不等于泄漏**（多次先升后回落，必须看单调性） |
| `psapi.GetProcessMemoryInfo` | RSS / PeakWorkingSet / 私有页 | 需 `OpenProcess(0x0410)`；**`EmptyWorkingSet` 之后的值才是硬需求上界** |
| 修改页列表（`ModifiedPageListBytes`） | 待回写页量 | 回写常在 API 调用内就完成，采样抓不到（实测静置基线 17 MB、编辑后峰值仅 +0.3–1.3 MB） |
| 文件系统归因（`os.walk` 取 `(size, mtime_ns)`） | 哪个文件被改 | **尺寸不变的重写**必须按**整文件大小**计（`conf.json` 15,407 → 15,407）；**只追加**的文件按尺寸差计（`*.db-wal`、`index.queue`），按整文件计会高估 |
| 内容差分（逐字节 + 4 KB 页） | 改动面 | **定长偏移比对会把「尾部平移」报成 94% 变化**——只能得出「必须搬尾」，不能得出「真改了 94% 的字节」 |

## 测量协议（五步，缺一步数字就不可比）

1. **同长度静置基线**。先测「什么也不做」的同长度窗口再扣减。实测本仓库空闲时 `R 0 B/s / W 47 B/s`
   ⇒ 那一轮的组间方差**不是**后台 cron 造成的，而是 SQLite WAL checkpoint 落点。
   基线非零时必须扣，否则方差会吃掉信号。
2. **把异步工作钉进窗口**。索引队列按 `SQLFlushInterval` 周期刷盘
   （`kernel/util/runtime.go:315`，当前 3000 ms）。要测「一次调用引发的全部 IO」，
   每次调用后须等 **≥5.5 s 静默**（连续 22×250 ms 计数无变化）才能把当轮刷新算进本次调用；
   否则刷新的账会记到下一次调用上（曾因此把一次小文档新建算成 `R 487 KB / W 475 KB`，
   受控重测真实值是 ~59 KB / ~50 KB）。
3. **区分冷缓存与热缓存**。块缓存命中会**绕过 SQL**（`kernel/sql/block_query.go:1020` 中
   `notHitIDs` 为空即提前返回），树缓存命中会绕过整份 `.sy` 读（`kernel/cache/tree.go`）。
   测 SQL / 磁盘路径必须冷缓存（重启内核），测稳态则先预热。
4. **长时脚本：分离进程 + 增量写文件**。管道给 `Out-String` 会**缓冲全部输出**，
   而进程被终端清理时会一并收到 `SIGTERM`（日志里是 `process.go:36: received os signal [terminated]`）
   ⇒ 什么都拿不到。做法：`Start-Process python -ArgumentList '-u',<脚本>` 重定向到文件，
   脚本内每完成一组就 `write + flush`，被中断也能保住部分数据。
5. **A/B 变体**。用 `go build -overlay=<json>` 替换单个源文件，**不改工作树**；
   构建后按字节计数自证替换生效。启动变体后**按端口占用者杀进程并校验 exe 路径**——
   按进程名匹配会漏杀（变体不叫 `kernel`），于是 A/B 两侧其实测的是同一个二进制（表现为**两次 pid 相同**）。

## 判据陷阱（全部有本仓库实例，回读时必须先排除）

- **占位值不是空值**。「这个块不存在」在返回体里是**非空的中文占位文案**
  （`kernel/model/flashcard.go:559` 填 `Conf.Language(180)`）。用「`content` 是否为空」判存在性会得出
  「全都在」；正确判据是**占位块只有 `id` 与 `content`，`box`/`path` 为空**。
- **长度相等不代表按位置对齐**。`fromSQLBlocks`（`kernel/model/search.go:3005`）对 `nil` 也 `append`，
  长度保持 ⇒「未命中项造成下标错位」的怀疑**不成立**。先验证再写结论。
- **写路径的预算不等于读路径也有预算**。写侧按 512 分块（`kernel/sql/upsert.go:72`），读侧完全没有
  → [模式 P54](./patterns.md)。
- **单一访问路径的假设**。同一份数据常有「只读内置 X」的约定（`kernel/model/flashcard.go:174`
  只读 `Decks[builtinDeckID]`），用别的容器造语料会得到「匹配为零」，看起来像性能很好。
- **先验地说「参数没有上限只是慢」**。实测它变成**硬失败 + 静默错误结果**（见 P54 与判据 G）。

## 可复制骨架

```python
# 量测骨架：静置基线扣减 + 异步屏障 + 进程 IO delta + 文件归因
# 用法：后台分离进程运行，输出写文件（不要靠管道）。改 3 处尖括号即可复用。
import os, time, json, urllib.request, ctypes, ctypes.wintypes as wt

WS   = r"<临时工作空间>"            # 只归因这个目录：把临时目录之外的噪声挡在外面
BASE = "http://127.0.0.1:6806"

def api(path, body):                # 一定读响应码：忽略它 = 把静默失败当成功
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=3600) as r:
        raw = r.read()
    return json.loads(raw.decode()), (time.perf_counter() - t0) * 1000, len(raw)

class IO(ctypes.Structure):         # GetProcessIoCounters
    _fields_ = [(n, ctypes.c_ulonglong) for n in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype  = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]

def io_counters(pid):
    h = k32.OpenProcess(0x0410, False, pid)
    c = IO()
    k32.GetProcessIoCounters(h, ctypes.byref(c))
    k32.CloseHandle(h)
    return {"Rop": c.ReadOperationCount,  "Wop": c.WriteOperationCount,
            "R":   c.ReadTransferCount,   "W":   c.WriteTransferCount}

def snapshot():                     # 记 (size, mtime_ns)：重写型按整文件大小解读、追加型按尺寸差
    snap = {}
    for root, _, files in os.walk(WS):
        for fn in files:
            p = os.path.join(root, fn)
            try: st = os.stat(p)
            except OSError: continue
            snap[p] = (st.st_size, st.st_mtime_ns)
    return snap

def barrier(pid, quiet=0.25, needed=22):      # 5.5 s 静默，越过 SQLFlushInterval = 3 s
    last, stable = None, 0
    while stable < needed:
        c = io_counters(pid)
        key = (c["R"], c["W"], c["Rop"], c["Wop"])
        stable = stable + 1 if key == last else 0
        last = key
        time.sleep(quiet)

# 1) 先测同长度静置基线 → 背景速率 R_bg / W_bg
# 2) 每个用例：barrier → 取 io0 + snap0 → api(...) → barrier → 取 io1 + snap1
#    净成本 = (io1 - io0) - 背景速率 × 窗口时长；文件变化用 snap 差集逐条展示
# 3) 断言响应 code == 0，否则打印 msg 并整行丢弃（不要让它污染结论）
```

## 何时把量测写成脚本

**运行时量测器不进 `scripts/`**：它需要活的进程与端口，「零依赖、纯静态、异盘 cwd 用例」这三条
脚本准入约定都套不上，硬塞进去只会得到一个无法自检的装饰性脚本。本文件给协议与骨架，按需复制改编。
反之，**可静态判定的检查**才值得进 `scripts/`（准入标准见 [SKILL.md 参考资源](../SKILL.md#参考资源)）：
本轮的两个候选（`IN (?,…)` 的参数预算、固定睡眠充当完成信号）都因为**决定性问题属数据流**
（入参是否有界、异步侧有没有可等待的句柄）而不适合脚本化，最终写成了 [P54](./patterns.md)/[P55](./patterns.md)。

## 与其它文件的分工

| 文件 | 负责 |
| --- | --- |
| 本文件 | 怎么把运行期行为测准：仪器盲区、五步协议、判据陷阱、骨架 |
| [挑战门](./challenge-gate.md) | 这个发现成立吗（含「降级理由是一条技术断言」的再验） |
| [全栈层面地图](./stack-map.md) | 去哪测、环境与取证前提（构建、基线、产物时间戳、pprof 端口、语料入口） |
| [实证数据](./evidence.md) | 历轮实测数字与结论（去重来源） |

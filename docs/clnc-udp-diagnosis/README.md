# clnc UDP 崩溃诊断 · 产物索引

本目录汇总 R3G（Padavan / MT7621 mipsel）上 **CLNC v1.2 的 UDP 崩溃问题**的全部测试脚本、测试配置与结论。

## 结论（速览）

- **根因**：clnc v1.2 mipsel 二进制在收到 SOCKS5 **UDP ASSOCIATE** 时触发 `*** buffer overflow detected ***`（glibc fortify 中止）→ 进程死亡。**这是二进制内存越界 bug，不是配置问题。**
- **证据**：任意 httpUDP 配置（含官方模板）均崩；去掉 httpUDP 段即正常；与 ASSOCIATE 目标地址/类型无关。
- **为何其它设备正常**：官方 magisk 启动脚本写死 `本机UDP=禁网 / 共享UDP=禁网`，UDP 从未进入 clnc。
- **处置**：注释 `httpUDP::udp`（唯一有效）；UDP 走 **udp2raw** C 方案。

详见 [`REPORT.md`](./REPORT.md)。

## 目录

| 路径 | 内容 |
|---|---|
| `REPORT.md` | 完整诊断报告（问题 / 证据 / 排除 / 根因 / 处置 / 方案） |
| `confs/` | 测试用 clnc 配置（含官方模板写法、对照无 httpUDP 写法等） |
| `scripts/` | 诊断与测试脚本（Python 端驱动 + R3G 侧运行脚本） |

## `confs/` 说明

| 文件 | 用途 |
|---|---|
| `mv2_noudp.conf` | 对照：无 `httpUDP` 段（预期存活） |
| `mv2_repro.conf` | 历史写法（仅 `udp_socks5_listen`，`destAddr4=WAP`，`header_host=cns`） |
| `mv2_tproxy.conf` | `repro` + `udp_tproxy_listen` |
| `mv2_official.conf` | **CLNC 官方 CNS/普通免流模板写法** |
| `mv2_noheader.conf` | 最简（无 `encrypt`/`header_host`） |
| `mx_*.conf` | 早期（stage 系列）等价变体 |
| `clnc_test.conf` / `clnc_test_noudp.conf` | 隔离测试用例（含/不含 httpUDP） |
| `tf.conf` / `tf_noudp.conf` / `alt_tf.conf` / `av_tf.conf` | 前台抓取、旧版对照、ASSOCIATE 形态测试用配置 |

## `scripts/` 说明

| 脚本 | 用途 |
|---|---|
| `clnc_udp_inspect.py` | 探查 R3G 上 clnc 路径/运行态/md5/内核/tproxy/当前 conf |
| `clnc_udp_stage2..8.py` | 分阶段受控复现（启动 / 发 ASSOCIATE / 抓退出码 / tproxy / 对照） |
| `clnc_udp_matrix.py` / `clnc_udp_matrix2.py` | 配置变体矩阵（matrix2 为修正版：独立端口 + 清遗留实例） |
| `clnc_udp_fg.py` / `clnc_udp_fg2.py` | 前台模式抓取 clnc 真实 stdout/stderr（fg2 为修正版，抓到 fortify 消息） |
| `clnc_udp_assocvar.py` | ASSOCIATE 请求形态无关性测试 |
| `clnc_udp_altbin.py` | 官方旧版 mipsle 核心对照测试 |
| `clnc_run.sh` / `fg_run.sh` / `av_run.sh` / `alt_run.sh` | R3G 侧运行 wrapper（抓退出码/输出） |
| `mr2_*.sh` | matrix2 各变体的运行脚本 |
| `dns_probe.py` / `udp_test.py` / `udp_direct_test.py` | DNS/UDP 连通性探测 |
| `ttyd_login.py` / `ttyd_diag.py` / `push_via_ttyd.py` | R3G ttyd(7681) WebSocket 交互与文件推送 |
| `gh_push.py` / `gh_release.py` / `git_run.py` | GitHub Contents API 推送 / Release 资产 / 干净 env git |
| `analyze_elf.py` / `deep.py` | clnc 二进制 ELF/字符串分析 |

## 复现（简要）

见 `REPORT.md` 第 8 节。核心：上传任一含 `httpUDP` 的 conf → 前台跑 clnc → 发 SOCKS5 UDP ASSOCIATE → 观察 `*** buffer overflow detected ***`。

## 脱敏

公开版本已对 VPS IP、udp2raw 密钥、登录口令、token 等做占位替换；保留项目既定常量（WAP 网关 `10.0.0.200:80`、CNS `152.136.154.154:443`、内网 `192.168.2.0/24`）。详见 `REPORT.md` 第 9 节。

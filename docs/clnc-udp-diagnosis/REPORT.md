# R3G（Padavan）+ CPE 免流项目 · clnc UDP 崩溃根因诊断报告

> 设备：小米 R3G（MT7621 mipsel 软浮点，Padavan 固件）
> 核心：CLNC v1.2（CuteBi Linux Network Client，官方 `mmmdbybyd/CLNC`，2022-04 停更）
> 结论一句话：**clnc v1.2 的 mipsel 二进制在收到 SOCKS5 UDP ASSOCIATE 时发生 glibc fortify 缓冲区溢出中止（真内存越界 bug），与配置无关。**

---

## 1. 问题

R3G 上 `clnc.conf` 启用 `httpUDP::udp`（UDP over HTTP 隧道，即"TCP 转 UDP"）后，进程一收到 SOCKS5 UDP ASSOCIATE 请求即死亡，导致 UDP 无法代理。此前只能把整段 `httpUDP::udp` 注释掉（仅保留 TCP/DNS）。

## 2. 关键证据（一手）

在非守护化（`-d`，前台）运行 clnc 并重定向 stderr 后，抓到：

```
*** buffer overflow detected ***: /usr/bin/clnc terminated
```

- 这是 glibc `_FORTIFY_SOURCE` 运行时检查（`__chk_fail`）触发的**缓冲区溢出中止**，报错对象即 `/usr/bin/clnc`。
- ⇒ clnc 的 C 层（静态链接的 lwIP / wolfSSL / 胶水代码）存在**真实内存越界写**。

> ⚠️ 抓包要点（曾误判为"静默退出"）：`clnc -d` = **前台运行**（disable daemon）；
> **不带 `-d` 时 clnc 默认守护化，并把 stdout/stderr 重定向到 /dev/null** → 那条 abort 消息被吞掉，
> 只剩"进程没了"。必须 `-d` + 脚本内重定向才能看到真因。

## 3. 受控实验与证据链

所有实验均在 R3G 上用**隔离实例**（独立端口、启动前清干净遗留测试进程）进行，不触碰生产 clnc。

### 3.1 配置变体矩阵（指向：与配置无关）

| 变体 | httpUDP 段写法 | 收 ASSOCIATE 后 |
|---|---|---|
| `noudp` | 无（对照） | ✅ **存活** |
| `repro` | 仅 `udp_socks5_listen`；`destAddr4=WAP`；`httpMod=tunnel`；`header_host=cns` | ❌ 越界中止 |
| `tproxy` | `repro` + `udp_tproxy_listen` | ❌ 越界中止 |
| `official` | **CLNC 官方"CNS/普通免流"模板写法**（两个 listen 齐、`dest_addr=header_host=免流节点`） | ❌ 越界中止 |
| `noheader` | 最简（仅 `udp_socks5_listen`+`destAddr4`+`httpMod`，无 `encrypt`/`header_host`） | ❌ 越界中止 |

⇒ **连官方模板配置也照样崩** ⇒ 不是键名/配置项写错；去掉 `httpUDP` 段即完全正常。

### 3.2 ASSOCIATE 请求形态（指向：与输入无关）

| 场景 | 请求 | 结果 |
|---|---|---|
| S1 | 仅 greeting（`05 01 00`），不发 request | ✅ 存活 |
| S2 | `ASSOCIATE 0.0.0.0:0` | ❌ 越界中止 |
| S3 | `ASSOCIATE 8.8.8.8:53` | ❌ 越界中止 |
| S4 | `ASSOCIATE example.com:53 (atyp3)` | ❌ 越界中止 |

⇒ 只要收到 SOCKS5 UDP ASSOCIATE（不论目标地址/类型）即崩，与请求字节无关。

### 3.3 排除项

| 假设 | 验证 | 结论 |
|---|---|---|
| 第三方重编译损坏 | R3G 上 clnc md5 `e138ac29…` == 官方 v1.2 `linux_mipsle`（== `linux_mipsle_softfloat`，字节相同） | **排除**：就是官方 v1.2 mipsel 原版 |
| 软/硬浮点错配（MT7621 无 FPU） | ELF `.MIPS.abiflags fp_abi=0` → 软浮点 | **排除** |
| 内核缺 tproxy 模块 | `insmod nf_tproxy_core.ko`+`xt_TPROXY.ko` 成功后仍崩 | **排除** |
| 加密层（wolfSSL） | 去掉 `encrypt`（`noheader` 变体）仍崩 | **排除** |
| 旧版核可绕开 | 官方 v1.0/v0.9.1/v0.8.1 mipsle 报 `configuration file format error`（不认 v1.2 语法） | 未直接对比（需换兼容配置） |

## 4. 为什么"手机 / 其他 Linux 设备上正常"

官方 magisk"联通IP 热点修复"启动脚本里**写死了**：

```
本机UDP=禁网     共享UDP=禁网     检测UDP联网=关闭   # 注释：不使用 UDP 代理
```

⇒ 那套配置**根本没把 UDP 流量引进 clnc**，ASSOCIATE 路径从未被触发，因此看起来一切正常。
（次要可能：ARM 等其它架构构建未触发该 fortify 检查——**未验证，仅推断**。）

## 5. 官方 httpUDP 规格（`clncConfig.explain` 原文摘要）

> httpUDP 模块：udp 转为 CONNECT 特征，**通过服务端 CNS 代理**。
> 关键字：`udp_tproxy_listen` `udp_socks5_listen` `destAddr` `header_host` `http_header` `tunnel_header`
> `encrypt` `tls_client` `udp_flag` `httpMod` `tunnelHttpMod` `send_http` `max_sessions` `timeout` `tcp_option`。

配置键我们没写错（官方模板同样崩）。

## 6. 处置与结论

| 途径 | 结论 |
|---|---|
| 改配置规避 | **无解**——所有 httpUDP 配置都崩 |
| 换核心 | v1.2 已是最新版；官方 2022-04 停更、**无源码**（GitHub 仓库仅 confs+二进制包） |
| 自编译修 | 不可行（无源码） |
| **唯一有效处置** | **注释 `httpUDP::udp`**（当前 `clnc.conf` v5-final 即如此，正确） |
| UDP 出路 | **C 方案 udp2raw**（见下） |

- CLNC 官方仓库 `mmmdbybyd/CLNC` 仅含 `README/LICENSE/Changes/confs/*.conf/androidScript/*.zip`，**无任何源码**（`Changes` 亦止于 1.0）。B 方案（改源码重编译）不成立。
- UDP-over-WAP 的唯一现实路径：**udp2raw 隧道**（不依赖 clnc 的 httpUDP，也不依赖 WAP HTTP 代理的 UDP 支持）。

## 7. C 方案：udp2raw（架构）

```
LAN 设备 --UDP--> R3G udp2raw client --faketcp(TCP)--> 公网 VPS udp2raw server --UDP--> 真实目的地
                        (192.168.2.1:4455)                    (VPS:4096 → 8.8.8.8:53)
```

- R3G 跑 **client**（MT7621 mipsel，`udp2raw_mips24kc_le`，静态，实测可跑）。
- 公网 **VPS** 跑 **server**（systemd 常驻 + `while true` 重启循环 + DROP 规则幂等）。
- 端到端验证命令（LAN 设备）：`dig @192.168.2.1 -p 4455 google.com`（应返回真实解析）。
- 说明：udp2raw 是静态点对点隧道（进 client 的 UDP 全中继到 server 的 `-r` 目标），做"任意目的 UDP"需多实例或调整 `-r`。

## 8. 复现方法（脚本见 `scripts/`）

1. 将 `confs/mv2_official.conf`（或任一含 httpUDP 的 conf）上传到 R3G。
2. 用 `scripts/clnc_udp_fg2.py` 起前台实例并抓取 stderr。
3. 向 socks5 监听端口发 `05 01 00` 握手 + `05 03 00 01 00 00 00 00 00 00`（ASSOCIATE）。
4. 观察 `*** buffer overflow detected ***` 与进程终止。
5. 对照：用 `confs/mv2_noudp.conf`（无 httpUDP）重复 → 进程存活。

## 9. 脱敏说明

本目录为公开上传版本，已对以下敏感信息做占位替换：

| 原值 | 占位符 |
|---|---|
| 公网 VPS IP | `<VPS_IP>` |
| udp2raw 预共享密钥 | `<UDP2RAW_KEY>` |
| 设备登录口令（含 base64 形式） | `<CRED>` |
| GitHub token（若出现） | `<TOKEN>` |

保留的固定值（项目既定常量，非密钥）：WAP 网关 `10.0.0.200:80`、CNS 服务器 `152.136.154.154:443`、内网网段 `192.168.2.0/24`。

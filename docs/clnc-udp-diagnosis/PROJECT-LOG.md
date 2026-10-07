# R3G + CPE 免流项目 · 总记录（PROJECT LOG）

> 本文件把整个项目的排查、结论与运维记录**按主题整理**成一份可读文档；原始实验脚本见 `scripts/`、`confs/`，clnc UDP 崩溃的完整报告见 [`REPORT.md`](./REPORT.md)。
> 公开版本已脱敏（见文末「脱敏说明」）。

---

## 0. 环境速览

| 角色 | 说明 |
|---|---|
| 路由器 | 小米 R3G（MT7621 **mipsel** 软浮点 / Padavan 固件），LAN `192.168.2.1` |
| 登录方式 | **SSH `admin@192.168.2.1` + 密钥**（首选）；ttyd `:7681`、httpd `:80`、Clash 面板 `:9091`、clnc 面板 `:9092` |
| 上游 CPE | ZTE F231ZC（USB-CDC 以太网，接口名 `weth0`，USB `19d2:0581`），R3G WAN = `weth0 = 192.168.0.100/24`，网关 `192.168.0.1` |
| 运营商 WAP 网关 | `10.0.0.200:80`（即免流出口 / HTTP 代理）——**项目既定常量，勿改** |
| CNS 服务端 | `152.136.154.154:443`（用户既有，硬编码） |
| 公网 VPS | `<VPS_IP>`（腾讯云，Debian 13 x86_64，root） |
| clnc 配置 | `/etc/storage/clnc/clnc.conf`（v5-final，md5 `8369a9c593ebe153ab2b9e46aa62bb7b`） |

---

## 1. clnc（CLNC v1.2）UDP 崩溃 —— 根因与处置

**结论：clnc v1.2 的 mipsel 二进制在收到 SOCKS5 UDP ASSOCIATE 时触发 glibc fortify 缓冲区溢出中止（真实内存越界 bug），与配置无关。**

| 证据 | 内容 |
|---|---|
| 中止消息 | `*** buffer overflow detected ***: /usr/bin/clnc terminated`（glibc `_FORTIFY_SOURCE`） |
| 复现（100%） | 任意含 `httpUDP::udp` 的配置 + 收 UDP ASSOCIATE → 进程终止 |
| 对照 | 去掉 `httpUDP` 段 → 存活 |
| 与配置无关 | 连 **CLNC 官方 CNS 模板**写法也照样崩 |
| 与请求形态无关 | `0.0.0.0:0` / `8.8.8.8:53` / 域名(atyp3) 全崩；仅 greeting 不发 request → 存活 |
| 排除项 | 非第三方重编译（md5 与官方 v1.2 `linux_mipsle` 一致）、非软/硬浮点、非 tproxy 缺失、非 wolfSSL |
| 为何"手机正常" | 官方 magisk 启动脚本写死 `本机UDP=禁网/共享UDP=禁网`，UDP 从未进入 clnc |

**处置**：`clnc.conf` 注释掉 `httpUDP::udp`（唯一有效手段），仅保留 TCP/DNS。UDP 出路见 §3。

> 详细诊断矩阵见 [`REPORT.md`](./REPORT.md)；实验脚本 `scripts/clnc_udp_*.py`。

---

## 2. 上游链路特性与"没网"事故（关键约束）

### 2.1 🔴 关键约束：该 CPE 在 WAP 模式下**不给 R3G 通用公网出口**

| R3G 去往 | 结果 |
|---|---|
| `10.0.0.200:80`（WAP 网关） | **通** ✅ |
| 经 WAP HTTP 代理取网页 | **通** ✅（免流正常） |
| 任意公网 IP（`<VPS_IP>:22/443/4096`、`223.5.5.5:443`、`110.242.74.102:80`） | **全不通** ❌ |
| CPE 网关 `192.168.0.1:53` 解析域名 | **失败** |

- `ip route get <VPS_IP>` = `via 192.168.0.1 dev weth0`（**有路由**，不是缺路由）→ 是 CPE 侧只放行 WAP 网关。
- ⇒ R3G 的公网访问**只能**走 `10.0.0.200:80` 这个 **HTTP 代理**。

### 2.2 事故：「开 clnc 后没网」的根因 = CPE 的 USB 网卡消失（与 clnc 无关）

| 项 | 现象 |
|---|---|
| 症状 | 全 LAN 断网；R3G 无默认路由、clnc DNS/代理不可用 |
| 真因 | CPE 的 USB 以太网口 `weth0`（`19d2:0581` CDC-Ethernet）掉了，USB 设备重新枚举成 **`19d2:0197 "ZTE Trap"`**（只剩 GSM modem `ttyUSB0/1`，**没有网卡**） |
| 连锁 | weth0 消失 → WAN 回落物理口 `eth3`（有载波但 `RX=0`，无对端）→ 无 DHCP → 无默认路由 → 断网 |
| 恢复 | **重插 CPE 的 USB**（软件 `unbind/bind` 强制重枚举无效，模式由设备端持久决定）→ 重新以 `0581` 枚举 → `weth0=192.168.0.100`、默认路由恢复 |

> 该事故**不是 clnc 引起**：clnc 进程/端口/配置全程未变，只是"没有上行可用"。

---

## 3. udp2raw（C 方案）—— 绕过 clnc UDP 崩溃的隧道

**架构**：

```
LAN 设备 --UDP--> R3G udp2raw client(192.168.2.1:4455) --faketcp(TCP)--> VPS udp2raw server(:4096) --UDP--> 真实目的地
```

| 项 | 状态 |
|---|---|
| VPS server | ✅ `active`，监听 `0.0.0.0:4096` → 转发 `8.8.8.8:53`；`iptables INPUT policy ACCEPT` |
| 腾讯云 SG 4096 | ✅ 已放通（PC 从外网连 `<VPS_IP>:4096` = OPEN） |
| R3G client | ✅ 在跑，监听 UDP `192.168.2.1:4455` |
| **端到端**（`LAN→R3G:4455` 查 DNS） | ❌ **超时** |

**端到端不通的根因**：见 §2.1 —— **R3G 没有通用公网出口**，无法直接 TCP 到 VPS:4096；而 udp2raw **不支持 HTTP 代理**，无法借道 `10.0.0.200:80`。⇒ **在纯 WAP 免流架构下，udp2raw 走不通。**

**出路**：让 R3G 具备通用公网出口（换回能通用上网的 CPE，或使用 NET 类 APN 而非 WAP 免流 APN）。VPS 侧与 SG 本身已验证正常。

---

## 4. CNS 服务端（部署在 VPS 上）

| 项 | 值 |
|---|---|
| 版本 | CNS **v0.4.3**（`mmmdbybyd/CNS`，`linux_amd64`） |
| 路径 | `/opt/cns/cns`，配置 `/opt/cns/cns.json` |
| 常驻 | systemd `cns.service`（enabled + active，Restart=always） |
| 监听 | `*:443` |
| 密码 | `encrypt_password = "<CNS_PWD>"` |
| proxy_key | `Meng`（按 clnc 免流惯例，clnc 用 `Meng: [H]` 携带真实目标） |
| 其它 | `udp_flag=httpUDP`、`Enable_httpDNS=true`、`Enable_dns_tcpOverUdp=true`、`Enable_TFO=false` |
| 验证 | 本机 TCP 443 OK、HTTP-DNS(`?dn=`)→200、**外网 `<VPS_IP>:443` OPEN** ✅ |

> 注意：设置 `encrypt_password` 后，`proxy_key` 头的值需按 CNS 约定做 **Base64+XOR 加密**（明文 curl 测不通属正常，需 clnc 客户端）。
> 部署脚本见 [`cns/`](./cns/)（`deploy_cns.py` / `verify_cns.py` / `cns.json`）。

---

## 5. 运维备忘（踩过的坑）

| 坑 | 说明 / 对策 |
|---|---|
| ttyd(7681) 弱信号不稳 | 频繁 `ConnectionReset` / 超时；**优先用 SSH**：`ssh -i id_ed25519 admin@192.168.2.1`（user 是 `admin`，不是 root） |
| R3G busybox 无 `/dev/tcp`、无 `timeout` | 测 TCP 连通用 `nc -w N ip port </dev/null`；有 `nc`/`socat`/`wget`/`curl`（`nc` 无 `-v`） |
| R3G 测 https 别用 busybox wget | 它不带 SSL，会误报 `Connection reset by peer`；**用 `curl`** |
| CPE USB 掉线变 "ZTE Trap" | 软件重枚举无效，**只能物理重插/断电重启 CPE** |
| Windows python 路径 | Windows python 把 `/tmp/x.py` 当 `C:\tmp\x.py`；脚本写到工作区路径下再跑 |
| clnc 抓错误输出 | `-d` 是**前台**；不带 `-d` 会守护化并把 stdout/stderr 丢 `/dev/null`，看不到真实报错 |
| 上传 GitHub 被墙 | `git push` 不通，用 **Contents API**（`gh_push.py`）逐个推 |

---

## 6. 时间线（2026-10-07）

| 时间 | 事件 |
|---|---|
| 上午 | 换 CPE 后 PC 无 DNS → 定位 CPE 的 WAP 会话断开 → 触发 `CONNECT_NETWORK` 重拨恢复 |
| 白天 | 确认 clnc 收 UDP ASSOCIATE 必崩；官方仓库无源码、无修复版 |
| 下午 | 部署 udp2raw：VPS server（systemd 常驻）+ R3G client（开机自启） |
| 傍晚 | **受控诊断坐实 clnc mipsel 的 httpUDP `buffer overflow` 中止**（真 bug，非配置） |
| 晚 | 上传诊断产物到本仓库 `docs/clnc-udp-diagnosis/` |
| 晚 | 事故「开 clnc 后没网」→ 根因 CPE USB 网卡变 "ZTE Trap" → 重插 USB 恢复 |
| 晚 | VPS 放通 4096 → udp2raw 端到端实测：**不通**（R3G 无通用公网出口） |
| 晚 | 在 VPS 部署 **CNS v0.4.3**（443，密码 <CNS_PWD>） |

---

## 脱敏说明

公开版本对以下敏感信息做占位替换：公网 VPS IP → `<VPS_IP>`；udp2raw 预共享密钥 → `<UDP2RAW_KEY>`；设备口令 → `<CRED>`；token → `<TOKEN>`。
**保留**项目既定常量（非密钥）：WAP 网关 `10.0.0.200:80`、CNS `152.136.154.154:443`、内网 `192.168.2.0/24`。

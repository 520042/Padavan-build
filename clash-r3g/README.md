# padavan-clash-r3g（Clash 集成子目录）

把 **Clash (mihomo)** 控制面板集成进小米 R3G 的 Padavan 固件（基于 hanwckf/rt-n56u）。

本目录是作为分支加进现有 Padavan 仓库的**增量集成包**（`build.sh` + `dev.pseudo` + `payload/`），放在 `clash-r3g/` 子目录下，**不改动原仓库任何已有文件**。它会对一份标准的 rt-n56u 源码打补丁并编译，产出内置 Clash 的 R3G 固件。**不**包含 2.8GB 的 rt-n56u 源码树本身。

## 集成了什么

- **预装 mihomo 核心** `/usr/bin/mihomo`（v1.17.0，mipsle-softfloat，UPX+LZMA 6.3MB）。支持 VLESS / Reality / Hysteria2 / TUIC / SS / VMess / Trojan。
- **经典 clash 核心** `/usr/bin/clash`（2.77MB，作为回退）。
- **后台内嵌控制面板**：在路由器后台「系统管理 → 服务」页（`Advanced_Services_Content.asp`）直接内嵌 iframe 显示面板，无需跳转到独立网页。右上角有「新窗口打开」。
- **控制面板前端** `/www2/index.html` + **yacd** `/www2/ui`（面板内的「yacd 面板」按钮）。
- **面板 CGI 后端** `/usr/bin/clash-ctl` 与 `/www2/cgi-bin/clash`：状态/启停/重启/模式切换(rule·global·direct)/订阅管理/节点列表/一键测速/日志(可清空)/配置(可备份)/核心更新(走国内镜像) 全部动作。
- **面板 Web 服务** `/usr/bin/clash-web.sh`：开机仅起 busybox httpd :9091 提供页面，**不**自动启动代理、不下载、不动 iptables。所有核心/规则/订阅都要你点按钮才跑。断网保护看门狗(进程退出 15 秒内自动摘除规则)内置在 clash-ctl。

## 关键设计点

- **下载全走国内镜像**：gh-proxy.com → ghproxy.net → ghfast.top → gh.llkk.cc → 直连兜底。核心更新与订阅获取都走这条链。
- **核心预装而非下载**：固件已内置 mihomo，首次使用无需下载；面板里仍可一键更新到 `/etc/storage/clash/mihomo`（重启保留）。
- **mihomo 版本选型**：v1.19 是 UPX 压缩版，squashfs 的 xz 压不动，打进固件后 trx 飙到 28MB 超 24MB 上限。改用 **v1.17.0 mipsle-softfloat + UPX+LZMA**，仅 6.3MB，固件约 21MB，余量充足且不砍任何功能。MT7621 无 FPU，必须 softfloat 版。
- **`/dev` 节点修复**：编译容器缺少 `cap_mknod` 权限，原始 `makedevlinks` 一个设备节点都建不出来（会导致刷机后 kernel 挂不上 flash 直接死机）。改用 `mksquashfs -pf dev.pseudo` 把 47 个设备节点直接写进镜像（见 `dev.pseudo`）。**务必使用含此修复的固件**，无此修复的版本会变砖。

## 构建方法

```bash
# 1. 在 clash-r3g/ 目录内克隆 rt-n56u
cd clash-r3g
git clone -b trunk https://github.com/hanwckf/rt-n56u.git
# 目录结构应为:
#   clash-r3g/          (本目录)
#     build.sh
#     payload/
#     rt-n56u/          (trunk 分支, 构建用)

# 2. 先构建 mipsel 工具链 (仅首次, 耗时较长)
cd rt-n56u/trunk && ./build_toolchain

# 3. 运行集成构建脚本
cd ..
bash build.sh
# 产物: clash-r3g/images/MI-R3G_3.4.3.9-099.trx
```

> 若 rt-n56u 不在本目录下，可用环境变量指定：`RT=/path/to/rt-n56u/trunk bash build.sh`。

## 刷机与验证

1. 通过 Breed / 官方修复工具刷入 `images/*.trx`。**建议不要保留旧配置**。
2. 刷完进入后台「系统管理 → 服务」页，页面下方应直接出现 Clash 控制面板。
3. 固件版本号仍是 `3.4.3.9-099`，**别用版本号判断刷没刷成功**——看面板在不在。
4. 在面板里：保存订阅 → 启动 → 切到「全局/规则」模式 → 测速选节点。

## 已验证可用固件（服务器本地编译产出）

| 文件 | 大小 | MD5 |
|---|---|---|
| `MI-R3G_3.4.3.9-099_clash-v5.trx` | 21,001,242 字节 (20.03 MB) | `611e95a6d507749c66fe04ad52021d92` |

> v1~v4 因编译环境的 `/dev` 节点缺陷已作废，请用 v5（含 `dev.pseudo` 修复）。

## 文件清单

| 路径 | 作用 |
|---|---|
| `build.sh` | 给 rt-n56u 打补丁并编译（相对路径，可移植） |
| `dev.pseudo` | squashfs 伪文件，注入 47 个 `/dev` 设备节点 |
| `payload/clash` | 经典 clash 核心 (MIPS32) |
| `payload/mihomo` | 预装 mihomo 核心 (v1.17.0 softfloat, UPX+LZMA) |
| `payload/clash-ctl` | 面板 CGI 后端 |
| `payload/clash-web.sh` | 面板 Web 服务 (busybox httpd :9091) |
| `payload/panel.html` | 控制面板前端 |
| `payload/yacd-ui/` | yacd 面板静态资源 |

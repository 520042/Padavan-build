# padavan-patches — v102 原生 WebUI 源码补丁集

本目录存放 **小米 R3G 定制固件 v102（3.4.3.9-102）** 的完整 Padavan 源码改动，
叠加到 `hanwckf/rt-n56u` 源码树即可复现固件。

相对前序版本的核心变更：**订阅定时自动更新（autocron）** 全链路落地。

## 目录对应（本目录路径 → rt-n56u 源码树路径）

| 本目录文件 | 覆盖到 rt-n56u | 说明 |
|---|---|---|
| `user/clash/clash.sh` | `trunk/user/clash/clash.sh` | Clash(mihomo) 管理脚本，含 autocron |
| `user/clash/config.yaml` | `trunk/user/clash/config.yaml` | 出厂配置：真实 wangka 免流节点 + 8 段 LAN 旁路 |
| `user/httpd/web_ex.c` | `trunk/user/httpd/web_ex.c` | WebUI 后端：注册 `AutoCron` action |
| `user/httpd/variables.c` | `trunk/user/httpd/variables.c` | 注册 `clash_autocron` nvram 变量 |
| `user/www/n56u_ribbon_fixed/Advanced_Clash_Content.asp` | `trunk/user/www/n56u_ribbon_fixed/Advanced_Clash_Content.asp` | Clash 页：订阅自动更新下拉 + 隐藏表单 |
| `trunk/versions.inc` | `trunk/versions.inc` | `FIRMWARE_BUILDS_VER=102` |

## 应用方法

```bash
# 假设已 clone hanwckf/rt-n56u 到 ~/rt-n56u
RT=~/rt-n56u/trunk
PAT=本仓库/padavan-patches

cp "$PAT/user/clash/clash.sh"        "$RT/user/clash/clash.sh"
cp "$PAT/user/clash/config.yaml"     "$RT/user/clash/config.yaml"
cp "$PAT/user/httpd/web_ex.c"        "$RT/user/httpd/web_ex.c"
cp "$PAT/user/httpd/variables.c"     "$RT/user/httpd/variables.c"
cp "$PAT/user/www/n56u_ribbon_fixed/Advanced_Clash_Content.asp" \
                                    "$RT/user/www/n56u_ribbon_fixed/Advanced_Clash_Content.asp"
cp "$PAT/trunk/versions.inc"         "$RT/versions.inc"

cd ~/rt-n56u/trunk && ./build_firmware
```

## autocron 行为说明

- WebUI「订阅管理」区新增下拉：**订阅自动更新** = 关闭 / 每 1·2·3·6·12·24 小时
- 选择后写 nvram `clash_autocron`，由 `clash.sh autocron-apply` 幂等重写
  Padavan 持久 cron 表 `/etc/storage/cron/crontabs/admin`（mtd_storage 落盘，crond 每分钟重扫即生效）
- `clash.sh autocron`（cron 触发的实际任务）含三层守卫：
  1. `clash_enable=1` 才执行
  2. `clash_sub_url` 非空才执行
  3. 存在默认路由（有外网）才执行，否则静默跳过等下一轮
- 守卫通过后**同进程复用 `update_sub`** 全链：下载订阅 → 校验 `proxies` → 备份 → 替换 config → 重启核心

## 与仓库既有 clash-ctl / 9091 面板方案的关系

本补丁集是**原生 WebUI 集成方向**（你此前要求弃用 9091 面板），与仓库
`clash-r3g/payload/clash-ctl` 的 9091 CGI 方案是两套并行架构。
若要让 CI（`build.sh` / `.github/workflows`）实际产出含 autocron 的固件，
需把上述文件注入到构建所用的 Padavan 源码树——这是下一步集成工作，
当前先以源码归档形式落库，保证改动可追溯、可复现。

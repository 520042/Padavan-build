#!/bin/sh
# ============================================================
# clnc 透明代理 (TCP REDIRECT) —— 让 LAN 客户端无需设置代理即可上网
#
# 原理: 内核 3.4.113 无 TPROXY, 但 nat/REDIRECT 可用(实测)。
#       把 LAN 客户端的 80/443/8080 出向 TCP 在 PREROUTING 阶段
#       REDIRECT 到 clnc 的 http_proxy(:6650), 由 clnc 经 WAP 网关转发。
#
# 安全设计(断网保护):
#   1) 下规则前先确认 clnc 活着(预检), 核心不在绝不挂规则
#   2) 看门狗每 10s 查核心, 死了自动摘规则恢复直连
#   3) 一键 "unload" 手动解除, 面板有按钮
#
# 部署: /etc/storage/clnc/clnc-tproxy.sh
# 用法: clnc-tproxy.sh [load|unload|status|watch]
# 注意: 本文件 LF 写入
# ============================================================

D=/etc/storage/clnc
BIN=$D/clnc
PORT=6650
# 劫持的客户端端口(HTTP/HTTPS/ALT-HTTP)
PORTS="80 443 8080"
# 排除的网段(不劫持): 局域网/回环/保留地址, 以及 clnc 自身出口(192.168.0.0/24=CPE侧)
BYPASS="192.168.0.0/16 172.16.0.0/12 10.0.0.0/8 127.0.0.0/8 224.0.0.0/4 240.0.0.0/4"

# clnc 活着? (必须带 -c 才匹配真二进制, 脚本自身路径也含 clnc)
clnc_alive() {
    ps w 2>/dev/null | grep -qE "[c]lnc -c"
}

# 已挂规则? (用自定义链 CLNCTPROXY 是否存在判断 —— 不能用 -m comment,
# busybox iptables 不支持 comment match 会静默失败, 实测踩过)
has_rule() {
    iptables -t nat -S CLNCTPROXY 2>/dev/null | grep -q "CLNCTPROXY"
}

load_rules() {
    if clnc_alive; then
        echo "clnc 活着, 挂透明代理规则..."
    else
        echo "警告: clnc 未运行, 拒绝挂规则(避免断网)"
        return 1
    fi

    # 清掉可能残留的旧规则
    unload_rules 2>/dev/null

    # 建自定义链(REDIRECT 规则的容器; 存在与否用 has_rule 判断)
    iptables -t nat -N CLNCTPROXY 2>/dev/null

    # ---- 规则设计(注意语义, 别写反) ----
    # 目的: 劫持 LAN 客户端的 80/443/8080 出向 TCP -> clnc :6650
    # 但要放过"不能劫持"的包, 否则会死循环/破坏本地服务。
    # 做法: 先用 RETURN 提前跳出本链(等于"不劫持, 继续走正常转发"), 命中的包直接返回;
    #       没被 RETURN 掉的包, 才是我们要劫持的。
    # 必须放过的:
    #   1) 保留/组播段 224.0.0.0/4, 240.0.0.0/4  (组播/保留, 非正常上网流量)
    #   2) 回环 127.0.0.0/8                          (本机进程, 劫持会环路)
    #   3) CPE 侧网段 192.168.0.0/24                 (clnc 自己的出口 weth0, 劫持会无限递归!)
    # 注意: 不能加 -m comment (busybox 不支持, 静默丢规则);
    #       -d 多地址用逗号连接(busybox 不支持空格分隔)。

    # (1) 放过保留段/组播/回环/CPE侧 —— 逗号连接
    iptables -t nat -A CLNCTPROXY -d 127.0.0.0/8,224.0.0.0/4,240.0.0.0/4,192.168.0.0/24 -j RETURN

    # (2) 剩余 LAN 客户端的 目标端口流量 -> REDIRECT 到 clnc
    for p in $PORTS; do
        iptables -t nat -A CLNCTPROXY -p tcp -s 192.168.2.0/24 --dport $p \
            -j REDIRECT --to-port $PORT
    done
    # (3) 其余流量(非目标端口)也放过, 保持原样直连
    iptables -t nat -A CLNCTPROXY -j RETURN

    # PREROUTING: LAN 客户端的全部 TCP 送进本链
    iptables -t nat -A PREROUTING -p tcp -s 192.168.2.0/24 -j CLNCTPROXY

    if iptables -t nat -S CLNCTPROXY 2>/dev/null | grep -q REDIRECT; then
        echo "透明代理已挂载 (LAN TCP $PORTS -> clnc :$PORT)"
        echo "如需解除: clnc-tproxy.sh unload"
    else
        echo "挂载失败(REDIRECT 规则未生效)"
        unload_rules
        return 1
    fi
}

unload_rules() {
    # 先删 PREROUTING 上的跳转, 再清自定义链
    while iptables -t nat -D PREROUTING -p tcp -s 192.168.2.0/24 -j CLNCTPROXY 2>/dev/null; do :; done
    iptables -t nat -F CLNCTPROXY 2>/dev/null
    iptables -t nat -X CLNCTPROXY 2>/dev/null
    echo "透明代理已解除, 恢复直连"
}

status() {
    if clnc_alive; then echo "clnc: 运行中"; else echo "clnc: 未运行"; fi
    if has_rule; then
        echo "透明代理: 已挂载"
        iptables -t nat -S CLNCTPROXY 2>/dev/null | grep REDIRECT | head
    else
        echo "透明代理: 未挂载"
    fi
}

# 看门狗: 自愈 + 防断网
#   核心死 -> 自动摘规则(防断网)
#   核心活但规则缺失 -> 自动补挂(解决开机时序: started_script 里 load 时 clnc 可能还没起来;
#                      也应对规则被意外清掉的情况)
watch() {
    echo "看门狗启动(每10s自愈: 核心死摘规则/核心活补规则), Ctrl-C 退出"
    while true; do
        sleep 10
        if clnc_alive; then
            # 核心活着但规则没挂 -> 补挂
            if ! has_rule; then
                echo "[$(date)] 检测到透明代理规则缺失, 自动补挂..."
                load_rules >/dev/null 2>&1
            fi
        else
            # 核心死了且规则还在 -> 摘规则防断网
            if has_rule; then
                echo "[$(date)] 检测到 clnc 崩溃, 自动摘除透明代理规则防断网!"
                unload_rules
            fi
        fi
    done
}

case "$1" in
    load) load_rules ;;
    unload) unload_rules ;;
    status) status ;;
    watch) watch ;;
    *) status ;;
esac

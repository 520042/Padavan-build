#!/bin/sh
# ============================================================
# clash.sh — Clash(mihomo)/经典 clash 管理脚本
# （对齐 docs/clash-changelog.md 的 clash-ctl 行为契约，原生 WebUI 集成版）
# 用法: clash.sh {start|stop|restart|status|unblock|update-sub|
#                 saveprofile|loadprofile|delprofile|listprofiles|
#                 cfg-get|cfg-set|cfg-check|cfg-restore|cfg-reset|
#                 autocron-apply|autocron|install-autostart}
# 关键约定（与 changelog 一致）:
#   - mihomo 核心 /tmp/mihomo/clash（启动时逐镜像下载），经典 clash 内置 /usr/bin/clash 优先
#   - 启动前配置规范化到 /tmp/clash-run，存储区 /etc/storage/clash/config.yaml 原文件不动
#   - 透明代理: TCP 全量→7891, UDP 53→1053, 私网 RETURN
#   - external-controller 0.0.0.0:9090 + secret 自动生成；yacd 面板 external-ui
#   - fake-ip DNS 全链设计；dnsmasq 自愈 server=127.0.0.1#1053
#   - 看门狗: 核心死亡 15s 内摘规则+重启（最多连续 3 次），/tmp/.clash_stop 区分手动停止
#   - 启动安全门: 核心语法预检(-t)不通过绝不挂劫持规则
#   - hw_nat_mode=0（修 USB WAN 转发吞吐）
#   - autocron: 订阅定时更新（nvram clash_autocron 小时间隔，写持久 cron 表）
# ============================================================
PERSIST_DIR="/etc/storage/clash"
PROFILE_DIR="/etc/storage/clash/profiles"
RUN_DIR="/tmp/clash-run"
CORE_DIR="/tmp/mihomo"
BIN_CLASSIC="/usr/bin/clash"
LOG="$RUN_DIR/clash.log"
STOP_FLAG="/tmp/.clash_stop"
FACTORY_DIR="/etc_ro/clash"

MIHOMO_ASSET="https://github.com/520042/Padavan-build/releases/download/v1.0.0/mihomo-upx-1.19.31"
CLASSIC_ASSET="https://github.com/Dreamacro/clash/releases/download/v1.18.0/clash-linux-mipsle-softfloat-v1.18.0.gz"
MIHOMO_MD5="16ec1b99e3157a164dbd74339eef2b87"
MIRRORS="https://ghfast.top/ https://ghproxy.net/ https://gh-proxy.com/ "

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG" 2>/dev/null || { mkdir -p "$RUN_DIR"; echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }; }

nvget() { nvram get "$1" 2>/dev/null; }

ipt_start() {
    iptables -t nat -L CLASH >/dev/null 2>&1 || iptables -t nat -N CLASH
    iptables -t nat -F CLASH
    # 私网/保留网段 RETURN 放行（对齐 clash-ctl：8 段全量旁路，含 0.0.0.0/8 与 169.254.0.0/16）
    for NET in 0.0.0.0/8 10.0.0.0/8 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 192.168.0.0/16 224.0.0.0/4 240.0.0.0/4; do
        iptables -t nat -A CLASH -d $NET -j RETURN
    done
    # TCP 全量 → 7891；UDP 53 → 1053（fake-ip 应答）；其余 UDP 放行（changelog 策略）
    iptables -t nat -A CLASH -p tcp -j REDIRECT --to-ports 7891
    iptables -t nat -A CLASH -p udp -m udp --dport 53 -j REDIRECT --to-ports 1053
    iptables -t nat -C PREROUTING -j CLASH 2>/dev/null || iptables -t nat -A PREROUTING -j CLASH
}

ipt_stop() {
    iptables -t nat -D PREROUTING -j CLASH 2>/dev/null
    iptables -t nat -F CLASH 2>/dev/null
    iptables -t nat -X CLASH 2>/dev/null
}

# 逐镜像下载核心（changelog: 逐镜像重试 + MD5 校验）
#   - URL 以 .gz 结尾: 下载后解压为二进制
#   - 否则: 视为已压缩二进制（如 mihomo-upx），直下即可
fetch_core() {
    _ASSET="$1"
    _OUT="$2"
    _MD5="$3"
    [ -x "$_OUT" ] && return 0
    mkdir -p "$(dirname "$_OUT")"
    for M in $MIRRORS; do
        U="${M}${_ASSET}"
        logger -t clash "downloading core via $U"
        rm -f "${_OUT}.tmp" "${_OUT}.tmp.gz"
        if echo "$U" | grep -q '\.gz$'; then
            wget -q -T 60 -O "${_OUT}.tmp.gz" "$U" || { rm -f "${_OUT}.tmp.gz"; continue; }
            [ -s "${_OUT}.tmp.gz" ] || { rm -f "${_OUT}.tmp.gz"; continue; }
            _TMP="${_OUT}.tmp.gz"
        else
            wget -q -T 90 -O "${_OUT}.tmp" "$U" || { rm -f "${_OUT}.tmp"; continue; }
            [ -s "${_OUT}.tmp" ] || { rm -f "${_OUT}.tmp"; continue; }
            _TMP="${_OUT}.tmp"
        fi
        if [ -n "$_MD5" ]; then
            _GOT="$(md5sum "$_TMP" 2>/dev/null | cut -d' ' -f1)"
            if [ "$_GOT" != "$_MD5" ]; then
                log "core md5 mismatch ($_GOT), try next mirror"
                rm -f "$_TMP"; continue
            fi
            log "core md5 verified OK"
        fi
        if echo "$U" | grep -q '\.gz$'; then
            gunzip -f "$_TMP" && mv -f "${_OUT}.tmp" "$_OUT" 2>/dev/null; [ -x "$_OUT" ] || mv -f "${_TMP%.gz}" "$_OUT" 2>/dev/null
        else
            mv -f "$_TMP" "$_OUT"
        fi
        chmod +x "$_OUT" 2>/dev/null && return 0
    done
    return 1
}

# 双核自动选择（changelog: mihomo(/tmp/mihomo/clash) / 经典 clash(/usr/bin/clash) 内置优先）
# 选核结果写入 $RUN_DIR/.bin
select_core() {
    CORE="$(nvget clash_core)"
    if [ "$CORE" = "classic" ]; then
        if [ -x "$BIN_CLASSIC" ]; then
            echo "$BIN_CLASSIC" > "$RUN_DIR/.bin"
            log "core: classic clash (builtin $BIN_CLASSIC)"
            return 0
        fi
        if fetch_core "$CLASSIC_ASSET" "$CORE_DIR/clash"; then
            echo "$CORE_DIR/clash" > "$RUN_DIR/.bin"
            log "core: classic clash (downloaded)"
            return 0
        fi
        log "classic core unavailable, fallback to mihomo"
    fi
    # mihomo（默认/兜底，带 MD5 校验）
    fetch_core "$MIHOMO_ASSET" "$CORE_DIR/clash" "$MIHOMO_MD5" || return 1
    echo "$CORE_DIR/clash" > "$RUN_DIR/.bin"
    log "core: mihomo"
}

# secret 自动生成（changelog: secret 自动生成，mihomo 强制要求；与 clash-ctl 一致: panel_secret + 16 位）
ensure_secret() {
    SECRET_FILE="$PERSIST_DIR/panel_secret"
    if [ ! -s "$SECRET_FILE" ]; then
        head -c 8 /dev/urandom | md5sum | cut -c1-16 > "$SECRET_FILE" 2>/dev/null
    fi
}

# dnsmasq 自愈（changelog: 恢复出厂/丢失后自动补回）
dnsmasq_heal() {
    C="/etc/storage/dnsmasq/dnsmasq.conf"
    mkdir -p /etc/storage/dnsmasq
    [ -f "$C" ] || touch "$C"
    _CHANGED=0
    grep -q "server=127.0.0.1#1053" "$C" 2>/dev/null || { echo "server=127.0.0.1#1053" >> "$C"; _CHANGED=1; }
    grep -q "server=223.5.5.5" "$C" 2>/dev/null || { echo "server=223.5.5.5" >> "$C"; _CHANGED=1; }
    grep -q "server=119.29.29.29" "$C" 2>/dev/null || { echo "server=119.29.29.29" >> "$C"; _CHANGED=1; }
    [ "$_CHANGED" = "1" ] && {
        log "dnsmasq.conf healed (1053 + public dns backup)"
        service restart_dnsmasq >/dev/null 2>&1
    }
}

# 启动前配置规范化（changelog: 语义零改动注入，存储区原文件不动）
normalize_config() {
    _CFG="$1"
    SECRET="$(cat "$PERSIST_DIR/panel_secret" 2>/dev/null)"
    grep -q "^allow-lan:" "$_CFG" 2>/dev/null || echo "allow-lan: true" >> "$_CFG"
    grep -q "^redir-port:" "$_CFG" 2>/dev/null || echo "redir-port: 7891" >> "$_CFG"
    grep -q "^mixed-port:" "$_CFG" 2>/dev/null || echo "mixed-port: 7890" >> "$_CFG"
    grep -q "^external-controller:" "$_CFG" 2>/dev/null || echo "external-controller: 0.0.0.0:9090" >> "$_CFG"
    # external-ui 强制指向运行目录（存储副本可能残留旧路径）
    sed -i "s|^external-ui:.*|external-ui: $RUN_DIR/ui|" "$_CFG" 2>/dev/null
    grep -q "^external-ui:" "$_CFG" 2>/dev/null || echo "external-ui: $RUN_DIR/ui" >> "$_CFG"
    # secret：缺失或为空时注入自动生成的（mihomo 强制要求）
    if ! grep -qE '^secret: *".+"' "$_CFG" 2>/dev/null; then
        sed -i 's|^secret:.*|secret: "'"$SECRET"'"|' "$_CFG" 2>/dev/null
        grep -q '^secret:' "$_CFG" 2>/dev/null || echo "secret: \"$SECRET\"" >> "$_CFG"
    fi
    # 运行模式（nvram clash_mode: rule/global/direct）
    MODE="$(nvget clash_mode)"
    case "$MODE" in
        rule|global|direct) sed -i "s/^mode:.*/mode: $MODE/" "$_CFG" 2>/dev/null ;;
    esac
    # 完整 dns 块（fake-ip）——订阅常缺 dns 块，孤儿 listen 行会被 mihomo 忽略
    if ! grep -q "^dns:" "$_CFG" 2>/dev/null; then
        cat >> "$_CFG" <<EOF
dns:
  enable: true
  listen: 0.0.0.0:1053
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  fake-ip-filter:
    - +.lan
    - +.local
    - +.msftconnecttest.com
    - +.msftncsi.com
  nameserver:
    - 223.5.5.5
    - 119.29.29.29
EOF
        log "dns block (fake-ip) injected"
    fi
    # fake-ip-filter 兜底（已有 dns 块但缺 filter：注入到 enhanced-mode 行后，不切断列表）
    grep -q "fake-ip-filter:" "$_CFG" 2>/dev/null || {
        if grep -q "^  enhanced-mode: fake-ip" "$_CFG" 2>/dev/null; then
            sed -i "/^  enhanced-mode: fake-ip/a\\
  fake-ip-filter:\\
    - +.lan\\
    - +.local" "$_CFG"
        fi
    }
}

# hw_nat_mode=0（changelog: 修 USB WAN 转发吞吐）
ensure_hwnat() {
    [ "$(nvget hw_nat_mode)" != "0" ] && nvram set hw_nat_mode=0 2>/dev/null
}

# 看门狗（changelog: 核心无声死亡→15s 内摘规则+自动重启，最多连续 3 次；
#          /tmp/.clash_stop 区分手动停止；WATCHDOG_CHILD=1 防看门狗增殖）
watchdog_start() {
    [ -n "$WATCHDOG_CHILD" ] && return 0
    touch "$RUN_DIR/.watchdog"
    WATCHDOG_CHILD=1 watchdog_loop &
    log "watchdog started"
}

watchdog_loop() {
    _N=0
    while [ -f "$RUN_DIR/.watchdog" ]; do
        sleep 15
        [ -f "$STOP_FLAG" ] && continue
        if ! pgrep clash >/dev/null 2>&1; then
            _N=$((_N+1))
            if [ "$_N" -gt 3 ]; then
                log "watchdog: restart limit (3) reached, giving up"
                ipt_stop
                rm -f "$RUN_DIR/.watchdog"
                break
            fi
            log "watchdog: core died, restarting ($_N/3)"
            ipt_stop
            BIN="$(cat "$RUN_DIR/.bin" 2>/dev/null)"
            [ -x "$BIN" ] && {
                "$BIN" -d "$RUN_DIR" >> "$LOG" 2>&1 &
                sleep 2
                pgrep clash >/dev/null 2>&1 && ipt_start
            }
        fi
    done
}

start() {
    mkdir -p "$RUN_DIR/ui" "$PERSIST_DIR"
    log "==== clash.sh start ===="
    pgrep clash >/dev/null 2>&1 && { echo "clash already running"; return 0; }

    # 首次启动：出厂默认配置写入 /etc/storage（jffs 持久化；romfs 预置的
    # /etc/storage 会被挂载点遮挡，所以必须经 /etc_ro 初始化）
    if [ ! -f "$PERSIST_DIR/config.yaml" ]; then
        cp -f "$FACTORY_DIR/config.yaml" "$PERSIST_DIR/config.yaml" 2>/dev/null
        log "factory default config installed"
    fi

    ensure_secret
    ensure_hwnat

    # 运行副本（存储区原文件不动）
    cp -f "$PERSIST_DIR/config.yaml" "$RUN_DIR/config.yaml" || { echo "no config"; return 1; }
    cp -rf "$FACTORY_DIR/ui/." "$RUN_DIR/ui/" 2>/dev/null
    normalize_config "$RUN_DIR/config.yaml"

    # 双核选择
    select_core || { echo "core download failed"; log "core download failed"; return 1; }
    BIN="$(cat "$RUN_DIR/.bin")"

    # 启动安全门：语法预检不通过绝不挂劫持规则（changelog）
    if "$BIN" -t -d "$RUN_DIR" >/dev/null 2>&1; then
        log "config precheck OK ($BIN)"
    else
        echo "config precheck FAILED - hijack rules NOT applied"
        log "config precheck FAILED - abort"
        return 1
    fi

    rm -f "$STOP_FLAG"
    "$BIN" -d "$RUN_DIR" > "$LOG" 2>&1 &
    sleep 2
    if pgrep clash >/dev/null 2>&1; then
        ipt_start
        dnsmasq_heal
        watchdog_start
        echo "clash started"
    else
        echo "clash start failed"
        log "core failed to start"
        return 1
    fi
}

stop() {
    touch "$STOP_FLAG"
    rm -f "$RUN_DIR/.watchdog"
    ipt_stop
    killall clash 2>/dev/null
    log "clash stopped (manual)"
    echo "clash stopped"
}

# 🛡断网自救：仅摘除透明代理劫持，核心保持运行（changelog: 断网自救按钮）
unblock() {
    ipt_stop
    log "unblock: hijack rules removed (core kept running)"
    echo "clash redirect removed (unblocked)"
}

# 拉取订阅并替换持久配置，成功后重启核心
update_sub() {
    SUB="$(nvget clash_sub_url)"
    if [ -z "$SUB" ]; then
        log "update-sub: subscription url is empty"
        echo "subscription url is empty"; return 1
    fi
    log "update-sub: fetching $SUB"
    rm -f "$RUN_DIR/sub_download.yaml"
    wget -q -T 30 -O "$RUN_DIR/sub_download.yaml" "$SUB"
    if [ ! -s "$RUN_DIR/sub_download.yaml" ]; then
        log "update-sub: download failed"
        echo "download failed"; return 1
    fi
    # 基本校验：必须是 yaml 且包含 proxies 节点
    if ! grep -qE "^[[:space:]]*proxies:" "$RUN_DIR/sub_download.yaml"; then
        log "update-sub: not a valid clash config (no proxies section)"
        echo "invalid config (no proxies)"; return 1
    fi
    cp -f "$PERSIST_DIR/config.yaml" "$PERSIST_DIR/config.yaml.bak" 2>/dev/null
    mv -f "$RUN_DIR/sub_download.yaml" "$PERSIST_DIR/config.yaml"
    log "update-sub: config replaced, restarting core"
    stop
    sleep 1
    start
    echo "subscription updated"
}

# 订阅自动更新（autocron，对齐参考固件 clash-ctl 的同名能力）：
#   clash.sh autocron-apply —— 按 nvram clash_autocron 重写持久 cron 表
#     （/etc/storage/cron/crontabs/admin，mtd_storage 自动落盘；busybox crond 每分钟重扫，改完即生效）
#   clash.sh autocron       —— cron 周期任务体：守卫通过后复用 update_sub
CRON_FILE="/etc/storage/cron/crontabs/admin"

autocron_apply() {
    H="$(nvget clash_autocron)"
    case "$H" in
        1|2|3|6|12|24) ;;
        *) H=0 ;;
    esac
    mkdir -p /etc/storage/cron/crontabs
    touch "$CRON_FILE"
    # 移除旧行（幂等）
    grep -v 'clash.sh autocron' "$CRON_FILE" > "${CRON_FILE}.tmp" 2>/dev/null
    mv -f "${CRON_FILE}.tmp" "$CRON_FILE"
    if [ "$H" != "0" ]; then
        echo "0 */$H * * * /usr/bin/clash.sh autocron > /dev/null 2>&1" >> "$CRON_FILE"
    fi
    mtd_storage.sh save >/dev/null 2>&1
    killall -HUP crond 2>/dev/null
    if [ "$H" = "0" ]; then
        log "autocron: disabled"
        echo "autocron disabled"
    else
        log "autocron: every ${H}h"
        echo "autocron every ${H}h"
    fi
}

autocron_run() {
    # 守卫 1: Clash 功能开关关闭时不做任何事
    [ "$(nvget clash_enable)" = "1" ] || exit 0
    # 守卫 2: 订阅链接为空
    SUB="$(nvget clash_sub_url)"
    [ -n "$SUB" ] || exit 0
    # 守卫 3: 无外网（无默认路由）时跳过，等下一轮
    route -n 2>/dev/null | grep -q '^0\.0\.0\.0' || exit 0
    # 复用 update_sub（同进程函数调用：下载→proxies 校验→备份→替换→重启）
    update_sub >/dev/null 2>&1
}

# ===== 模式管理（changelog: saveprofile / loadprofile / delprofile）=====
valid_name() {
    case "$1" in
        *[!A-Za-z0-9_-]*) return 1 ;;
        "") return 1 ;;
    esac
    return 0
}

saveprofile() {
    P="$1"
    valid_name "$P" || { echo "invalid profile name"; return 1; }
    mkdir -p "$PROFILE_DIR"
    cp -f "$PERSIST_DIR/config.yaml" "$PROFILE_DIR/$P.yaml" && \
        { log "profile saved: $P"; echo "profile '$P' saved"; }
}

loadprofile() {
    P="$1"
    valid_name "$P" || { echo "invalid profile name"; return 1; }
    [ -f "$PROFILE_DIR/$P.yaml" ] || { echo "profile not found"; return 1; }
    # 原配置自动备份，加载后核心运行中自动重启生效（changelog）
    cp -f "$PERSIST_DIR/config.yaml" "$PERSIST_DIR/config.yaml.bak" 2>/dev/null
    cp -f "$PROFILE_DIR/$P.yaml" "$PERSIST_DIR/config.yaml"
    log "profile loaded: $P (backup: config.yaml.bak)"
    stop
    sleep 1
    start
    echo "profile '$P' loaded"
}

delprofile() {
    P="$1"
    valid_name "$P" || { echo "invalid profile name"; return 1; }
    rm -f "$PROFILE_DIR/$P.yaml"
    log "profile deleted: $P"
    echo "profile '$P' deleted"
}

listprofiles() {
    mkdir -p "$PROFILE_DIR"
    for F in "$PROFILE_DIR"/*.yaml; do
        [ -f "$F" ] && basename "$F" .yaml
    done
}

# ===== YAML 配置读写（原生 WebUI YAML 编辑器用）=====
cfg_get() { cat "$PERSIST_DIR/config.yaml" 2>/dev/null; }

cfg_set() {
    # stdin 读入（httpd hook 通过管道写入），非空校验；语法由启动预检兜底
    _TMP="$RUN_DIR/cfg_upload.yaml"
    mkdir -p "$RUN_DIR"
    cat > "$_TMP"
    if [ ! -s "$_TMP" ]; then rm -f "$_TMP"; echo "empty config"; return 1; fi
    if ! grep -qE "^[[:space:]]*(proxies:|proxy-groups:|port|mixed-port|mode)" "$_TMP"; then
        rm -f "$_TMP"; echo "not a clash config"; return 1
    fi
    cp -f "$PERSIST_DIR/config.yaml" "$PERSIST_DIR/config.yaml.bak" 2>/dev/null
    mv -f "$_TMP" "$PERSIST_DIR/config.yaml"
    log "config.yaml updated via WebUI editor"
    echo "config saved"
}

# 仅校验（不落盘不重启）：stdin 读入 → 规范化（与 start 同路径）→ 核心语法预检
cfg_check() {
    _TMP="$RUN_DIR/cfg_check.yaml"
    mkdir -p "$RUN_DIR"
    cat > "$_TMP"
    [ -s "$_TMP" ] || { echo "empty config"; return 1; }
    normalize_config "$_TMP"
    BIN="$(cat "$RUN_DIR/.bin" 2>/dev/null)"
    if [ -z "$BIN" ] || [ ! -x "$BIN" ]; then
        select_core >/dev/null 2>&1 || { echo "no core available for check"; return 1; }
        BIN="$(cat "$RUN_DIR/.bin")"
    fi
    if "$BIN" -t -d "$RUN_DIR" -f "$_TMP" >/dev/null 2>&1; then
        echo "CONFIG OK"
        rm -f "$_TMP"
    else
        echo "CONFIG INVALID:"
        "$BIN" -t -d "$RUN_DIR" -f "$_TMP" 2>&1 | tail -3
        return 1
    fi
}

# 恢复上次备份（changelog: 备份/恢复）
cfg_restore() {
    [ -s "$PERSIST_DIR/config.yaml.bak" ] || { echo "no backup found"; return 1; }
    cp -f "$PERSIST_DIR/config.yaml" "$PERSIST_DIR/config.yaml.bak2" 2>/dev/null
    cp -f "$PERSIST_DIR/config.yaml.bak" "$PERSIST_DIR/config.yaml"
    log "config restored from .bak"
    stop
    sleep 1
    start
    echo "backup restored"
}

# 恢复出厂默认（changelog: DEFAULT_CFG=wangka 免流结构，配置丢失/恢复出厂时兜底）
cfg_reset() {
    [ -f "$FACTORY_DIR/config.yaml" ] || { echo "no factory config"; return 1; }
    cp -f "$PERSIST_DIR/config.yaml" "$PERSIST_DIR/config.yaml.bak" 2>/dev/null
    cp -f "$FACTORY_DIR/config.yaml" "$PERSIST_DIR/config.yaml"
    log "config reset to factory default (wangka)"
    stop
    sleep 1
    start
    echo "factory default restored"
}

install_autostart() {
    # 兼容旧方式；新固件下 rc 已在开机时按 clash_enable 启动
    S="/etc/storage/started_script.sh"
    [ -f "$S" ] || touch "$S"
    grep -q "clash.sh" "$S" || echo '[ "$(nvram get clash_enable)" = "1" ] && (sleep 30 && /usr/bin/clash.sh start) &' >> "$S"
    chmod +x "$S"
    echo "autostart installed -> $S"
}

case "$1" in
    start) start ;;
    stop) stop ;;
    restart) stop; sleep 1; start ;;
    status) pgrep clash >/dev/null 2>&1 && echo "running" || echo "stopped" ;;
    unblock) unblock ;;
    update-sub) update_sub ;;
    saveprofile) saveprofile "$2" ;;
    loadprofile) loadprofile "$2" ;;
    delprofile) delprofile "$2" ;;
    listprofiles) listprofiles ;;
    cfg-get) cfg_get ;;
    cfg-set) cfg_set ;;
    cfg-check) cfg_check ;;
    cfg-restore) cfg_restore ;;
    cfg-reset) cfg_reset ;;
    autocron-apply) autocron_apply ;;
    autocron) autocron_run ;;
    install-autostart) install_autostart ;;
    *) echo "usage: clash.sh {start|stop|restart|status|unblock|update-sub|saveprofile|loadprofile|delprofile|listprofiles|cfg-get|cfg-set|cfg-check|cfg-restore|cfg-reset|autocron-apply|autocron|install-autostart}"; exit 1 ;;
esac

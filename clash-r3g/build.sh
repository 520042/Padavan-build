#!/bin/bash
# R3G Clash 集成构建脚本 — 把 Clash(mihomo) 控制面板编译进 Padavan 固件
# 本脚本放在仓库的 clash-r3g/ 子目录下 (不改动原仓库其它代码):
#   <repo>/clash-r3g/
#     build.sh          <- 本脚本
#     dev.pseudo        <- /dev 设备节点 (容器缺 cap_mknod 时用 mksquashfs -pf 注入)
#     payload/          <- 要打进固件的所有文件
#       clash           <- 经典 clash 核心 (MIPS32, 回退用)
#       mihomo          <- 预装 mihomo 核心 (v1.17.0 mipsle-softfloat, UPX+LZMA)
#       clash-ctl       <- 面板 CGI 后端 (/usr/bin/clash-ctl 与 /www2/cgi-bin/clash)
#       clash-web.sh    <- 面板 Web 服务启动 (busybox httpd :9091)
#       panel.html      <- 控制面板前端 (/www2/index.html)
#       yacd-ui/        <- yacd 面板静态文件 (/www2/ui)
#     rt-n56u/          <- 需自行克隆 hanwckf/rt-n56u (trunk 分支)，放在本目录内
#
# 用法:
#   1) cd clash-r3g/ && git clone -b trunk https://github.com/hanwckf/rt-n56u.git
#   2) cd rt-n56u/trunk && ./build_toolchain     # 先构建 mipsel 工具链
#   3) cd ../ && bash build.sh                    # 产出 clash-r3g/images/*.trx
# 可选环境变量: RT=<rt-n56u/trunk 路径> 可覆盖默认 (本目录下的 rt-n56u/trunk)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RT="${RT:-$SCRIPT_DIR/rt-n56u/trunk}"
PAYLOAD="$SCRIPT_DIR/payload"
PF="$SCRIPT_DIR/dev.pseudo"
OUT="$SCRIPT_DIR/images"
TC="$RT/../toolchain-mipsel/toolchain-3.4.x/bin/mipsel-linux-uclibc-gcc"

echo "=== [0/7] 工具链就位 ==="
if [ ! -x "$TC" ]; then
    echo "ERROR: 工具链未找到: $TC"
    echo "请先构建工具链: cd $RT && ./build_toolchain"
    exit 1
fi
"$TC" --version | head -1

echo "=== [1/7] busybox 启用 httpd applet ==="
cd "$RT"
sed -i 's/# CONFIG_HTTPD is not set/CONFIG_HTTPD=y/' configs/boards/busybox.config
grep -q "^CONFIG_HTTPD=y" configs/boards/busybox.config && echo "busybox httpd: OK"

echo "=== [2/7] rc.c 注入面板服务自启 (仅 Web 页面服务, 不碰 clash/iptables) ==="
python3 - <<'PYEOF'
import os
p = os.path.join(os.environ["RT"], "user/rc/rc.c")
s = open(p).read()
old = '\t// system ready\n\tsystem("/etc/storage/started_script.sh &");\n'
new = ('\t// system ready\n'
       '\tsystem("/etc/storage/started_script.sh &");\n'
       '\t/* Clash panel: busybox httpd static page server on 9091 (no proxy logic) */\n'
       '\tsystem("/usr/bin/clash-web.sh &");\n')
if 'clash-web.sh' in s:
    print("rc.c already patched, skip")
else:
    assert old in s, "rc.c anchor not found"
    open(p, "w").write(s.replace(old, new, 1))
    print("rc.c patched: clash-web.sh launched at boot (panel page only)")
PYEOF

echo "=== [3/7] ASP 服务页内嵌 Clash 控制面板 (iframe 直接显示) ==="
python3 - <<'PYEOF'
import os
p = os.path.join(os.environ["RT"], "user/www/n56u_ribbon_fixed/Advanced_Services_Content.asp")
s = open(p).read()

js_anchor = "function on_ttyd_link(){"
js_new = (
    "function on_clash_link(){\n"
    "\tvar clash_url=\"http\";\n"
    "\tclash_url+=\"://\"+lan_ipaddr+\":9091/\";\n"
    "\twindow_clash = window.open(clash_url, \"clash_panel\");\n"
    "\twindow_clash.focus();\n"
    "}\n"
    "\n" + js_anchor)
if 'on_clash_link' in s:
    print("ASP js already patched, skip")
else:
    assert js_anchor in s, "js anchor not found"
    s = s.replace(js_anchor, js_new, 1)

iframe_block = [
    "",
    '<tr id="clash_panel_box">',
    '<td colspan="2">',
    '<div style="margin:8px 0"><b style="color:#1a73e8">Clash \u63a7\u5236\u9762\u677f</b>'
    ' <a href="javascript:on_clash_link();">[\u65b0\u7a97\u53e3\u6253\u5f00]</a>'
    ' <span style="color:#888;font-size:12px">(\u5df2\u5185\u5d4c\u5728\u540e\u53f0\u9875\u9762\u5185, \u65e0\u9700\u8df3\u8f6c)</span></div>',
    '<iframe id="clash_iframe" src="" style="width:100%;height:1000px;border:1px solid #ccc;border-radius:8px;background:#fff"></iframe>',
    '<script type="text/javascript">document.getElementById("clash_iframe").src="http://"+location.hostname+":9091/";</script>',
    '</td>',
    '</tr>',
]

if 'clash_panel_box' in s:
    print("ASP iframe already present, skip")
elif 'clash_panel_link' in s:
    lines = s.split('\n')
    start = next(i for i, l in enumerate(lines) if 'id="clash_panel_link"' in l)
    end = next(i for i in range(start, len(lines)) if '</tr>' in lines[i])
    lines[start:end + 1] = iframe_block
    open(p, "w").write('\n'.join(lines))
    print("ASP patched: link replaced by inline iframe panel")
else:
    lines = s.split('\n')
    idx = next(i for i, l in enumerate(lines) if 'id="ttyd_webui"' in l)
    close = next(i for i in range(idx, len(lines)) if '</tr>' in lines[i])
    lines[close + 1:close + 1] = iframe_block
    s = '\n'.join(lines)
    open(p, "w").write(s)
    print("ASP patched: inline iframe panel inserted")
PYEOF

echo "=== [4/7] Makefile romfs.post 注入 payload (含预装 mihomo 核心) ==="
python3 - <<PYEOF
import os
p = os.path.join(os.environ["RT"], "Makefile")
PAYLOAD = os.environ["PAYLOAD"]
s = open(p).read()
old = (
    "romfs.post:\n"
    "\t-find \$(ROMFSDIR)/. -name CVS | xargs -r rm -rf ; \\\\\n"
    "\t\$(ROOTDIR)/tools/strip-romfs.sh ; \\\\\n"
    "\t\$(MAKEARCH) -C vendors romfs.post"
)
new = (
    "romfs.post:\n"
    "\t-find \$(ROMFSDIR)/. -name CVS | xargs -r rm -rf ; \\\\\n"
    "\t\$(ROOTDIR)/tools/strip-romfs.sh ; \\\\\n"
    "\tcp -f %s/clash \$(ROMFSDIR)/usr/bin/clash ; \\\\\n"
    "\tcp -f %s/mihomo \$(ROMFSDIR)/usr/bin/mihomo ; \\\\\n"
    "\tcp -f %s/clash-ctl \$(ROMFSDIR)/usr/bin/clash-ctl ; \\\\\n"
    "\tcp -f %s/clash-web.sh \$(ROMFSDIR)/usr/bin/clash-web.sh ; \\\\\n"
    "\tmkdir -p \$(ROMFSDIR)/www2/cgi-bin ; \\\\\n"
    "\tcp -f %s/panel.html \$(ROMFSDIR)/www2/index.html ; \\\\\n"
    "\tcp -f %s/clash-ctl \$(ROMFSDIR)/www2/cgi-bin/clash ; \\\\\n"
    "\tcp -a %s/yacd-ui \$(ROMFSDIR)/www2/ui ; \\\\\n"
    "\tchmod 755 \$(ROMFSDIR)/usr/bin/clash \$(ROMFSDIR)/usr/bin/mihomo \$(ROMFSDIR)/usr/bin/clash-ctl \$(ROMFSDIR)/usr/bin/clash-web.sh \$(ROMFSDIR)/www2/cgi-bin/clash ; \\\\\n"
    "\t\$(MAKEARCH) -C vendors romfs.post"
) % (PAYLOAD, PAYLOAD, PAYLOAD, PAYLOAD, PAYLOAD, PAYLOAD, PAYLOAD)
if "cp -f %s/mihomo" % PAYLOAD in s:
    print("Makefile mihomo already injected, skip")
elif "cp -f %s/clash" % PAYLOAD in s:
    a = "\tcp -f %s/clash \$(ROMFSDIR)/usr/bin/clash ; \\\\\n" % PAYLOAD
    assert a in s, "clash inject line not found"
    s = s.replace(a, a + "\tcp -f %s/mihomo \$(ROMFSDIR)/usr/bin/mihomo ; \\\\\n" % PAYLOAD, 1)
    b = "\tchmod 755 \$(ROMFSDIR)/usr/bin/clash "
    if b in s:
        s = s.replace(b, "\tchmod 755 \$(ROMFSDIR)/usr/bin/clash \$(ROMFSDIR)/usr/bin/mihomo ", 1)
    open(p, "w").write(s)
    print("Makefile patched: mihomo added to existing injection")
else:
    assert old in s, "romfs.post anchor not found"
    open(p, "w").write(s.replace(old, new, 1))
    print("Makefile patched: payload injection (clash+mihomo+ctl+web+panel+yacd)")
PYEOF

echo "=== [4.5/7] 注入 /dev 设备节点 (容器缺 cap_mknod, 改用 mksquashfs -pf) ==="
python3 - <<'PYEOF'
import os
p = os.path.join(os.environ["RT"], "vendors/Ralink/Makefile")
PF = os.environ["PF"]
s = open(p).read()
old = "$(ROOTDIR)/tools/mksquashfs_xz/mksquashfs $(ROMFSDIR) $(RAMDISK) -all-root -no-exports -noappend -nopad -noI -no-xattrs"
new = old + " -pf " + PF
if "-pf " + PF in s:
    print("dev pseudo-file already injected, skip")
else:
    assert old in s, "mksquashfs line not found"
    open(p, "w").write(s.replace(old, new, 1))
    print("Makefile patched: /dev nodes via -pf " + PF)
PYEOF

echo "=== [5/7] 准备 .config (MI-R3G 模板 + 精简无关代理) ==="
cd "$RT"
cp configs/templates/MI-R3G.config .config
sed -i 's/CONFIG_FIRMWARE_INCLUDE_OPENSSL_EXE=n/CONFIG_FIRMWARE_INCLUDE_OPENSSL_EXE=y/g' .config
for f in SHADOWSOCKS SSSERVER DNSFORWARDER ADBYBY FRPC FRPS ALIDDNS SMARTDNS V2RAY XRAY TROJAN KOOLPROXY CADDY ADGUARDHOME WYY ZEROTIER MENTOHUST SCUTCLIENT TUNSAFE SRELAY; do
    sed -i "/CONFIG_FIRMWARE_INCLUDE_$f/d" .config
done
echo "CONFIG_FIRMWARE_INCLUDE_OPENVPN=n" >> .config
echo "CONFIG_FIRMWARE_INCLUDE_DROPBEAR=y" >> .config
echo ".config ready"

echo "=== [6/7] 清理并开始编译 ==="
cd "$RT"
if [ "${SKIP_CLEAR:-1}" = "1" ]; then
    echo "skip clear_tree (incremental); build_firmware_modify force-rebuilds romfs+images"
else
    ./clear_tree
fi
./build_firmware_modify MI-R3G 0
mkdir -p "$OUT"
mv images/*.trx "$OUT/"
ls -la "$OUT/"

echo "=== [7/7] 硬校验: 解包 squashfs 检查 payload (缺一即失败) ==="
cd "$RT"
tools/mksquashfs_xz/unsquashfs -l images/ramdisk > /tmp/rd_list.txt 2>&1 || true
PASS=1
for f in "usr/bin/clash" "usr/bin/mihomo" "usr/bin/clash-ctl" "usr/bin/clash-web.sh" "www2/index.html" "www2/cgi-bin/clash" "www2/ui/index.html" "dev/console" "dev/null" "dev/mtdblock0" "dev/mtd0"; do
    grep -q "$f" /tmp/rd_list.txt || { echo "MISSING: $f"; PASS=0; }
done
[ "$PASS" = "1" ] || { echo "=== PAYLOAD MISSING ==="; exit 1; }
rm -rf /tmp/sqx
tools/mksquashfs_xz/unsquashfs -f -d /tmp/sqx images/ramdisk "www/Advanced_Services_Content.asp" > /dev/null 2>&1
grep -q "clash_panel_box" /tmp/sqx/www/Advanced_Services_Content.asp && echo "=== ASP IFRAME VERIFIED ===" || { echo "=== ASP IFRAME MISSING ==="; exit 1; }
echo "=== ALL PAYLOAD VERIFIED (clash+mihomo+ctl+web+panel+yacd+iframe) ==="
md5sum "$OUT"/*.trx
TRX=$(ls "$OUT"/*.trx | head -1)
SZ=$(stat -c%s "$TRX")
echo "TRX_SIZE: $SZ (limit 25165824)"
[ "$SZ" -lt 25165824 ] || { echo "=== TRX TOO LARGE ==="; exit 1; }
echo "=== BUILD DONE ==="

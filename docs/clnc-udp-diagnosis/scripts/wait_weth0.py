"""守候 CPE USB 网卡 weth0 回来 (最多 ~10 分钟)。
每 10s 经 SSH 探一次 R3G: idProduct / weth0 / 默认路由 / wan IP。回来即抓完整状态。
"""
import subprocess, time, os, sys

WS = r"C:/Users/liang.zhao/WorkBuddy/2026-09-24-15-59-12/r3g-build"
KEY = os.path.join(WS, "id_ed25519")
HOST = "admin@192.168.2.1"
OPTS = ["-i", KEY, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=8", "-o", "BatchMode=yes"]
ENV = {k: v for k, v in os.environ.items()
       if k.upper() not in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}

PROBE = (
    'p=$(cat /sys/bus/usb/devices/1-1/idProduct 2>/dev/null); '
    'w=$(ifconfig weth0 2>/dev/null | grep -c "inet addr"); '
    'r=$(ip route 2>/dev/null | grep -c "^default"); '
    'ip=$(nvram get wan0_ipaddr); '
    'echo "PROBE idProduct=$p weth0=$w default=$r wanip=$ip"'
)

def ssh(cmd, timeout=20):
    try:
        r = subprocess.run(["ssh"] + OPTS + [HOST, cmd],
                           capture_output=True, text=True, env=ENV, timeout=timeout)
        return r.stdout
    except Exception as e:
        return "ERR %s" % e

def main():
    print("[wait] 等待 CPE 重插/重启后 weth0 恢复 ...", flush=True)
    for i in range(1, 61):
        out = ssh(PROBE)
        line = ""
        for l in out.splitlines():
            if l.startswith("PROBE"):
                line = l.strip()
        print("[%02d] %s" % (i, line or ("(SSH无响应) " + out.strip()[:80])), flush=True)
        if "weth0=1" in line:
            print("\n[OK] weth0 已恢复! 抓完整状态 ...", flush=True)
            full = ssh(
                'echo "== ifconfig weth0 =="; ifconfig weth0; '
                'echo "== route =="; route -n; '
                'echo "== wan0 =="; nvram get wan0_ifname; nvram get wan0_ipaddr; nvram get wan0_gateway; '
                'echo "== 探测上行 =="; wget -q -T 6 -O /dev/null http://10.0.0.200/ ; echo "WAP_RC=$?"; '
                'echo "== DNS =="; nslookup baidu.com 127.0.0.1 2>&1 | tail -4', timeout=40)
            print(full, flush=True)
            print("WAIT_DONE_WETH0_BACK")
            return
        if "default=1" in line:
            print("\n[OK] 已出现默认路由(可能走 eth3)。", flush=True)
        time.sleep(10)
    print("\n[TIMEOUT] 10 分钟内未见 weth0 恢复。请确认 CPE 是否已重插/断电重启。")
    print("WAIT_DONE_TIMEOUT")

if __name__ == "__main__":
    main()

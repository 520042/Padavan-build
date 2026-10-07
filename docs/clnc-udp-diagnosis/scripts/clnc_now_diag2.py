"""R3G WAN/上行链路深挖 (只读)"""
import socket, base64, os, json, time

HOST, PORT = "192.168.2.1", 7681
USER, PASS = "admin", "admin"

def sf(s, op, p):
    if isinstance(p, str): p = p.encode()
    mk = os.urandom(4); mp = bytes(b ^ mk[i % 4] for i, b in enumerate(p))
    h = bytes([0x80 | op]); n = len(p)
    h += bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126]) + n.to_bytes(2, "big") if n < 65536 else bytes([0x80 | 127]) + n.to_bytes(8, "big"))
    s.sendall(h + mk + mp)
def rf(s, t):
    s.settimeout(t)
    try:
        h = b""
        while len(h) < 2:
            c = s.recv(2 - len(h))
            if not c: return "closed", b""
            h += c
        op, ln = h[0] & 0x0F, h[1] & 0x7F
        if ln == 126:
            d = b""
            while len(d) < 2: d += s.recv(2 - len(d))
            ln = int.from_bytes(d, "big")
        elif ln == 127:
            d = b""
            while len(d) < 8: d += s.recv(8 - len(d))
            ln = int.from_bytes(d, "big")
        p = b""
        while len(p) < ln:
            c = s.recv(min(65536, ln - len(p)))
            if not c: return "closed", b""
            p += c
        return op, p
    except socket.timeout: return "timeout", b""
    except OSError as e: return "error", str(e).encode()

class R:
    def __init__(self):
        self.s = socket.create_connection((HOST, PORT), timeout=10)
        k = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /ws HTTP/1.1\r\nHost: {HOST}:{PORT}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {k}\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: tty\r\n\r\n").encode())
        b = b""
        while b"\r\n\r\n" not in b: b += self.s.recv(4096)
        self.o = bytearray()
        sf(self.s, 1, json.dumps({"AuthToken": ""})); sf(self.s, 1, "1" + json.dumps({"columns": 200, "rows": 60}))
        self.pump(2.0)
        if self.w("login:", 8):
            self.raw(USER + "\n"); time.sleep(0.5); self.pump(1.0)
            self.o.clear(); self.w("assword:", 8); self.raw(PASS + "\n"); self.w("#", 10)
            self.o.clear(); print("[login] OK", flush=True)
    def pump(self, sec):
        end = time.time() + sec
        while time.time() < end:
            op, p = rf(self.s, max(0.2, end - time.time()))
            if op == "closed": raise RuntimeError("ws closed")
            if op in ("timeout", "error") or not p: continue
            if p[0:1] == b"0": self.o.extend(p[1:])
    def raw(self, d): sf(self.s, 2, b"\x30" + d.encode())
    def w(self, pat, t=15):
        end = time.time() + t
        while time.time() < end:
            if pat in self.o.decode("utf-8", "replace"): return True
            time.sleep(0.3); self.pump(0.3)
        return False
    def cmd(self, c, wait=8):
        self.o.clear(); self.raw(c + "\n"); self.pump(wait); return self.o.decode("utf-8", "replace")
def body(r, c, w=8): return r.cmd(c, w).replace(c, "", 1).strip("\r\n")

CHECKS = [
    ("全部网卡",        "ifconfig -a 2>/dev/null | grep -E '^[a-z]|inet addr|UP|RUNNING' | head -50"),
    ("/proc/net/dev",   "cat /proc/net/dev"),
    ("接口列表",        "ls /sys/class/net"),
    ("所有路由表",      "ip route show table all 2>/dev/null; echo '---'; route -n"),
    ("USB 事件",        "dmesg 2>/dev/null | tail -25"),
    ("nvram WAN",       "nvram get wan0_ifname; nvram get wan0_proto; nvram get wan0_ipaddr; nvram get wan0_gateway; nvram get wan_hwaddr_x; nvram get wan_ifname"),
    ("nvram 彩蛋",      "nvram get wan0_dns; nvram get wan0_dns1_x; nvram get wan0_gw_ifname; nvram get wan0_pppoe_ifname"),
    ("udp2raw 状态",    "ps w | grep '[u]dp2raw'; cat /etc/storage/udp2raw/udp2raw-client.log 2>/dev/null | tail -5"),
    ("clnc 日志",       "ls -la /etc/storage/clnc/clnc.log; tail -8 /etc/storage/clnc/clnc.log 2>/dev/null"),
    ("storage 剩余",    "df -h /etc/storage /tmp 2>/dev/null"),
    ("up 时长",         "cat /proc/uptime; cat /tmp/wan_status* 2>/dev/null"),
]

def main():
    r = R()
    for title, cmd in CHECKS:
        print("\n===== %s =====" % title)
        print(body(r, cmd, 10))
    r.s.close()

if __name__ == "__main__":
    try: main()
    finally: pass

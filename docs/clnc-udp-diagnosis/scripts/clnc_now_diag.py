"""clnc 开启后"没网"现场体检 (PC 侧经 ttyd 7681 驱动 R3G)。
只读诊断, 不改任何配置。
"""
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
def body(r, c, w=8):
    return r.cmd(c, w).replace(c, "", 1).strip("\r\n")

CHECKS = [
    ("clnc 进程",        "ps w | grep '[c]lnc'"),
    ("clnc 监听端口",    "netstat -lnp 2>/dev/null | grep -E ':53 |:6650|:1081|:9092|:4455'"),
    ("dnsmasq 进程",     "ps w | grep '[d]nsmasq'"),
    ("网卡/IP",          "ifconfig 2>/dev/null | grep -E 'Link|inet addr' | head -20"),
    ("默认路由",         "route -n 2>/dev/null | head -6"),
    ("PC↔CPE 192.168.0.1","wget -q -T 5 -O /dev/null http://192.168.0.1/ ; echo RC=$?"),
    ("R3G→WAP 10.0.0.200", "wget -q -T 6 -O /dev/null http://10.0.0.200/ ; echo RC=$?"),
    ("clnc DNS :53",     "nslookup baidu.com 127.0.0.1 2>&1 | head -6"),
    ("clnc DNS LAN",     "nslookup baidu.com 192.168.2.1 2>&1 | head -6"),
    ("clnc http_proxy",  "wget -q -T 6 -O /dev/null -e http_proxy=127.0.0.1:6650 http://www.baidu.com/ ; echo RC=$?"),
    ("httpd 面板",       "netstat -lnp 2>/dev/null | grep ':9091'"),
    ("nat PREROUTING",   "iptables -t nat -L PREROUTING -n -v 2>/dev/null | head -12"),
    ("CLNCTPROXY 链",    "iptables -t nat -L CLNCTPROXY -n -v 2>/dev/null | head -12"),
    ("clnc.conf md5",    "md5sum /etc/storage/clnc/clnc.conf 2>/dev/null; grep -c 'httpUDP' /etc/storage/clnc/clnc.conf"),
    ("fw 状态",          "ps w | grep -E '[c]lash|[m]ihomo' "),
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

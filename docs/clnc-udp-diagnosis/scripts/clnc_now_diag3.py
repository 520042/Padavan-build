"""R3G WAN 口(eth3) 链路/DHCP 细查 (只读)"""
import socket, base64, os, json, time
HOST, PORT = "192.168.2.1", 7681; USER, PASS = "admin", "admin"
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
    ("eth2/eth3 carrier", "for i in eth2 eth3; do echo -n \"$i carrier=\"; cat /sys/class/net/$i/carrier 2>/dev/null; echo -n \"  operstate=\"; cat /sys/class/net/$i/operstate 2>/dev/null; done"),
    ("eth3 ifconfig",   "ifconfig eth3"),
    ("DHCP 客户端",      "ps w | grep -E '[u]dhcpc|[d]hcpcd|dhcp'"),
    ("WAN nvram",       "for k in wan0_ifname wan0_proto wan0_dhcp_client wan0_ipaddr wan0_gateway wan0_dns wan0_hwaddr_x; do echo -n \"$k=\"; nvram get $k; done"),
    ("syslog WAN",      "cat /tmp/syslog.log 2>/dev/null | grep -iE 'wan|eth3|dhcp|usb|link' | tail -20; echo '--- logread ---'; logread 2>/dev/null | tail -20"),
    ("ARP 表",          "cat /proc/net/arp"),
    ("尝试 arping CPE",  "ping -c 2 -W 2 192.168.0.1 2>&1 | head -4"),
]
def main():
    r = R()
    for t, c in CHECKS:
        print("\n===== %s =====" % t)
        print(body(r, c, 10))
    r.s.close()
if __name__ == "__main__":
    try: main()
    finally: pass

"""ttyd 诊断: 路由器为什么没外网"""
import socket, base64, os, json, time, sys

HOST, PORT = "192.168.2.1", 7681
USER, PASS = "admin", "admin"

def send_frame(s, opcode, payload):
    if isinstance(payload, str):
        payload = payload.encode()
    mk = os.urandom(4)
    masked = bytes(b ^ mk[i % 4] for i, b in enumerate(payload))
    hdr = bytes([0x80 | opcode])
    ln = len(payload)
    if ln < 126:
        hdr += bytes([0x80 | ln])
    elif ln < 65536:
        hdr += bytes([0x80 | 126]) + ln.to_bytes(2, "big")
    else:
        hdr += bytes([0x80 | 127]) + ln.to_bytes(8, "big")
    s.sendall(hdr + mk + masked)

def recv_frame(s, timeout):
    s.settimeout(timeout)
    try:
        hdr = b""
        while len(hdr) < 2:
            c = s.recv(2 - len(hdr))
            if not c:
                return "closed", b""
            hdr += c
        op, ln = hdr[0] & 0x0F, hdr[1] & 0x7F
        if ln == 126:
            d = b""
            while len(d) < 2:
                d += s.recv(2 - len(d))
            ln = int.from_bytes(d, "big")
        elif ln == 127:
            d = b""
            while len(d) < 8:
                d += s.recv(8 - len(d))
            ln = int.from_bytes(d, "big")
        p = b""
        while len(p) < ln:
            c = s.recv(min(65536, ln - len(p)))
            if not c:
                return "closed", b""
            p += c
        return op, p
    except socket.timeout:
        return "timeout", b""
    except OSError as e:
        return "error", str(e).encode()

class Router:
    def __init__(self):
        self.s = socket.create_connection((HOST, PORT), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /ws HTTP/1.1\r\nHost: {HOST}:{PORT}\r\nUpgrade: websocket\r\n"
                        "Connection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                        "Sec-WebSocket-Protocol: tty\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            c = self.s.recv(4096)
            if not c:
                raise RuntimeError("no handshake")
            buf += c
        head, _ = buf.split(b"\r\n\r\n", 1)
        if b"101" not in head:
            raise RuntimeError("handshake failed")
        self.output = bytearray()
        send_frame(self.s, 0x1, json.dumps({"AuthToken": ""}))
        send_frame(self.s, 0x1, "1" + json.dumps({"columns": 120, "rows": 30}))
        self.pump(2.0)
        if self.wait_for("login:", 8):
            self.run_raw(USER + "\n")
            time.sleep(0.5); self.pump(1.0)
            self.output.clear()
            self.wait_for("assword:", 8)
            self.run_raw(PASS + "\n")
            self.wait_for("#", 10)
            self.output.clear()
            print("[login] OK", flush=True)

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            op, p = recv_frame(self.s, max(0.2, end - time.time()))
            if op == "closed":
                raise RuntimeError("ws closed")
            if op in ("timeout", "error") or not p:
                continue
            cmd, data = p[0:1], p[1:]
            if cmd == b"0":
                self.output.extend(data)

    def run_raw(self, data):
        send_frame(self.s, 0x2, b"\x30" + data.encode())

    def wait_for(self, pattern, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if pattern in self.output.decode("utf-8", errors="replace"):
                return True
            time.sleep(0.3)
            self.pump(0.3)
        return False

    def cmd(self, command, wait_seconds=8):
        self.output.clear()
        self.run_raw(command + "\n")
        self.pump(wait_seconds)
        return self.output.decode("utf-8", errors="replace")

def main():
    r = Router()
    checks = [
        ("WAN 协议/账号", "nvram get wan_proto; nvram get wan_pppoe_username_ifname; nvram get wan_ipaddr"),
        ("WAN 口 IP", "ifconfig | grep -A1 'eth3\\|ppp0' | head -10"),
        ("默认路由", "ip route | head -5"),
        ("DNS", "cat /etc/resolv.conf 2>/dev/null | head -3"),
        ("ping 外网IP", "ping -c 2 -W 2 223.5.5.5 2>&1 | tail -3"),
        ("ping 网关外?", "ip route | grep default"),
        ("残留 iptables", "iptables -t nat -L PREROUTING | head -6"),
        ("clash 残留", "ps w | grep clash | grep -v grep; ls /usr/bin/clash 2>&1"),
        ("started_script", "ls -la /etc/storage/started_script.sh 2>&1; cat /etc/storage/started_script.sh 2>&1 | head -2"),
    ]
    for title, cmd in checks:
        text = r.cmd(cmd, 6 if "ping" not in cmd else 12)
        body = text.replace(cmd, "", 1).strip()
        print(f"\n=== {title} ===\n{body[:700]}")
    r.s.close()

main()

"""Stage-1 探查: R3G 上 clnc 的路径/运行态/当前 conf/二进制 md5。
基于 ttyd_diag.py 的 WebSocket harness（admin/admin）。
"""
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
            if not c: return "closed", b""
            hdr += c
        op, ln = hdr[0] & 0x0F, hdr[1] & 0x7F
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
            if not c: raise RuntimeError("no handshake")
            buf += c
        if b"101" not in buf.split(b"\r\n\r\n",1)[0]:
            raise RuntimeError("handshake failed")
        self.output = bytearray()
        send_frame(self.s, 0x1, json.dumps({"AuthToken": ""}))
        send_frame(self.s, 0x1, "1" + json.dumps({"columns": 200, "rows": 40}))
        self.pump(2.0)
        if self.wait_for("login:", 8):
            self.run_raw(USER + "\n"); time.sleep(0.5); self.pump(1.0)
            self.output.clear()
            self.wait_for("assword:", 8)
            self.run_raw(PASS + "\n"); self.wait_for("#", 10)
            self.output.clear()
            print("[login] OK", flush=True)
    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            op, p = recv_frame(self.s, max(0.2, end - time.time()))
            if op == "closed": raise RuntimeError("ws closed")
            if op in ("timeout","error") or not p: continue
            if p[0:1] == b"0": self.output.extend(p[1:])
    def run_raw(self, data): send_frame(self.s, 0x2, b"\x30" + data.encode())
    def wait_for(self, pat, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if pat in self.output.decode("utf-8","replace"):
                return True
            time.sleep(0.3); self.pump(0.3)
        return False
    def cmd(self, command, wait=8):
        self.output.clear()
        self.run_raw(command + "\n"); self.pump(wait)
        return self.output.decode("utf-8","replace")

def main():
    r = Router()
    def show(title, cmd, wait=8):
        out = r.cmd(cmd, wait)
        # strip echo of the command
        body = out.replace(cmd, "", 1).strip("\r\n")
        print(f"\n===== {title} =====\n{body}")
    show("clnc 位置", "ls -la /etc/storage/clnc/ 2>&1; echo '---'; which clnc 2>&1; ls -la /usr/bin/clnc 2>&1; ls -la /usr/sbin/clnc 2>&1")
    show("运行态", "ps w | grep -i clnc | grep -v grep")
    show("二进制 md5", "md5sum /etc/storage/clnc/clnc /usr/bin/clnc 2>&1")
    show("内核版本", "uname -a")
    show("TPROXY 模块/支持", "ls /lib/modules/ 2>/dev/null; find / -name '*tproxy*' 2>/dev/null | head; cat /proc/net/netfilter/nf_tproxy 2>/dev/null; zcat /proc/config.gz 2>/dev/null | grep -i tproxy")
    show("当前 clnc.conf (v5-final)", "cat /etc/storage/clnc/clnc.conf 2>&1")
    r.s.close()

if __name__ == "__main__":
    main()

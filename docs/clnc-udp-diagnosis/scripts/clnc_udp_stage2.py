"""Stage-2: 在 R3G 上以隔离端口启动测试 clnc(httpUDP 启用), 抓取启动期表现。
PC 侧起 http.server 供 R3G wget conf; 用 start-stop-daemon 隔离 PID 启动, 不影响在跑 clnc。
"""
import socket, base64, os, json, time, sys, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import glob

HOST, PORT = "192.168.2.1", 7681
USER, PASS = "admin", "admin"
PC_IP = "192.168.2.165"
HTTP_PORT = 18099
CONF_NAME = "clnc_test.conf"
TEST_DIR = "/tmp/clnc_test"

# ---- PC http server ----
class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
here = os.path.dirname(os.path.abspath(__file__))
srv = HTTPServer((PC_IP, HTTP_PORT), H)
srv.daemon = True
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()
time.sleep(0.5)
print(f"[pc] http server on http://{PC_IP}:{HTTP_PORT}/ serving {here}", flush=True)

# ---- ttyd harness ----
def send_frame(s, opcode, payload):
    if isinstance(payload, str): payload = payload.encode()
    mk = os.urandom(4)
    masked = bytes(b ^ mk[i % 4] for i, b in enumerate(payload))
    hdr = bytes([0x80 | opcode]); ln = len(payload)
    if ln < 126: hdr += bytes([0x80 | ln])
    elif ln < 65536: hdr += bytes([0x80 | 126]) + ln.to_bytes(2,"big")
    else: hdr += bytes([0x80 | 127]) + ln.to_bytes(8,"big")
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
            d = b"";
            while len(d) < 2: d += s.recv(2 - len(d))
            ln = int.from_bytes(d,"big")
        elif ln == 127:
            d = b"";
            while len(d) < 8: d += s.recv(8 - len(d))
            ln = int.from_bytes(d,"big")
        p = b""
        while len(p) < ln:
            c = s.recv(min(65536, ln - len(p)))
            if not c: return "closed", b""
            p += c
        return op, p
    except socket.timeout: return "timeout", b""
    except OSError as e: return "error", str(e).encode()

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
        if b"101" not in buf.split(b"\r\n\r\n",1)[0]: raise RuntimeError("handshake failed")
        self.output = bytearray()
        send_frame(self.s, 0x1, json.dumps({"AuthToken": ""}))
        send_frame(self.s, 0x1, "1" + json.dumps({"columns": 200, "rows": 40}))
        self.pump(2.0)
        if self.wait_for("login:", 8):
            self.run_raw(USER + "\n"); time.sleep(0.5); self.pump(1.0)
            self.output.clear()
            self.wait_for("assword:", 8)
            self.run_raw(PASS + "\n"); self.wait_for("#", 10)
            self.output.clear(); print("[login] OK", flush=True)
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
            if pat in self.output.decode("utf-8","replace"): return True
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
        body = out.replace(cmd, "", 1).strip("\r\n")
        print(f"\n===== {title} =====\n{body}")
    show("建目录+拉取 conf", f"mkdir -p {TEST_DIR}; wget -q -O {TEST_DIR}/test.conf http://{PC_IP}:{HTTP_PORT}/{CONF_NAME}; echo WGET=$?; wc -c {TEST_DIR}/test.conf")
    show("校验 conf 端口", f"grep -nE 'listen|tcp_listen|dns_listen' {TEST_DIR}/test.conf")
    # 清理可能的旧测试实例
    show("清理旧测试实例", f"start-stop-daemon -K -p {TEST_DIR}/clnc.pid 2>/dev/null; kill $(cat {TEST_DIR}/clnc.pid 2>/dev/null) 2>/dev/null; echo done")
    # 隔离启动(独立 PID/端口, 输出到 log)
    show("启动测试 clnc(隔离)",
         f"start-stop-daemon -S -b -m -p {TEST_DIR}/clnc.pid -x /usr/bin/clnc -- -c {TEST_DIR}/test.conf -d >> {TEST_DIR}/clnc.log 2>&1; echo SSD=$?; sleep 2; echo '--- log ---'; cat {TEST_DIR}/clnc.log; echo '--- ps ---'; ps w | grep clnc | grep -v grep; echo '--- listen 1181 ---'; netstat -lnp 2>/dev/null | grep 1181")
    r.s.close()

if __name__ == "__main__":
    try:
        main()
    finally:
        srv.shutdown()
        print("\n[pc] http server stopped", flush=True)

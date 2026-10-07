"""Stage-6: 确认 tproxy 模块是否加载 / 测试 IP_TRANSPARENT 是否可用 / 清理测试产物。"""
import socket, base64, os, json, time, sys, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

HOST, PORT = "192.168.2.1", 7681
USER, PASS = "admin", "admin"
TEST_DIR = "/tmp/clnc_test"

class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = HTTPServer(("192.168.2.165", 18099), H); srv.daemon = True
threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(0.3)

def send_frame(s, opcode, payload):
    if isinstance(payload, str): payload = payload.encode()
    mk = os.urandom(4); masked = bytes(b ^ mk[i % 4] for i, b in enumerate(payload))
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
            self.output.clear(); self.wait_for("assword:", 8)
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
        self.output.clear(); self.run_raw(command + "\n"); self.pump(wait)
        return self.output.decode("utf-8","replace")

def show(r, title, cmd, wait=8):
    out = r.cmd(cmd, wait); body = out.replace(cmd, "", 1).strip("\r\n")
    print(f"\n===== {title} =====\n{body}")

def main():
    r = Router()
    show(r, "tproxy 模块是否加载", "lsmod 2>/dev/null | grep -i tproxy; echo '---proc---'; cat /proc/modules 2>/dev/null | grep -i tproxy; echo '---IPT---'; cat /proc/sys/net/ipv4/ip_forward 2>/dev/null")
    show(r, "python 是否可用(用于测 IP_TRANSPARENT)", "which python python3 2>&1")
    # 若有 python, 测 IP_TRANSPARENT (SOL_IP=0, IP_TRANSPARENT=19)
    py = r.cmd("which python 2>&1; which python3 2>&1", 4)
    if "python" in py and "/python" in py.replace("which python",""):
        show(r, "测试 IP_TRANSPARENT setsockopt",
             "python -c \"import socket; s=socket.socket(socket.AF_INET, socket.SOCK_STREAM); "
             "s.setsockopt(0,19,1); print('IP_TRANSPARENT_OK')\" 2>&1")
    else:
        print("\n[info] 无 python, 跳过 IP_TRANSPARENT 直接测试")
    show(r, "清理测试产物", f"start-stop-daemon -K -p {TEST_DIR}/clnc.pid 2>/dev/null; kill $(cat {TEST_DIR}/clnc.pid 2>/dev/null) 2>/dev/null; rm -rf {TEST_DIR}; ls -d {TEST_DIR} 2>&1; echo CLEANED")
    show(r, "确认在跑 clnc 仍在", "ps w | grep 'clnc.conf' | grep -v grep")
    r.s.close()

if __name__ == "__main__":
    try: main()
    finally:
        srv.shutdown(); print("\n[pc] http stopped", flush=True)

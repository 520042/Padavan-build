"""Stage-5: 查 R3G 是否有 strace/gdb; 若有则用 strace 跑测试 clnc 抓 ASSOCIATE 前的最后 syscall。"""
import socket, base64, os, json, time, sys, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

HOST, PORT = "192.168.2.1", 7681
USER, PASS = "admin", "admin"
PC_IP = "192.168.2.165"; HTTP_PORT = 18099
TEST_DIR = "/tmp/clnc_test"

class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
here = os.path.dirname(os.path.abspath(__file__))
srv = HTTPServer((PC_IP, HTTP_PORT), H); srv.daemon = True
threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(0.5)

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
    show(r, "查 strace/gdb/busybox applet", "which strace gdb 2>&1; echo '---bb---'; busybox 2>&1 | grep -iE 'strace|gdb' ; echo '---ltrace---'; which ltrace 2>&1")
    # 探测 strace 是否可用(以第一行为准)
    avail = "strace" in r.cmd("which strace 2>&1", 4)
    print("\n[info] strace available:", avail, flush=True)
    if avail:
        show(r, "清理+strace 启动测试 clnc",
             f"{TEST_DIR}/clnc.pid 2>/dev/null; start-stop-daemon -K -p {TEST_DIR}/clnc.pid 2>/dev/null; "
             f"kill $(cat {TEST_DIR}/clnc.pid 2>/dev/null) 2>/dev/null; "
             f"rm -f {TEST_DIR}/strace.log; "
             f"strace -f -e trace=network,exit,signal,setsockopt,socket,bind,connect,close,write,read "
             f"-o {TEST_DIR}/strace.log /usr/bin/clnc -c {TEST_DIR}/test.conf -d >> {TEST_DIR}/clnc.log 2>&1 & "
             f"echo LAUNCHED; sleep 2; ps w | grep 'test.conf' | grep -v grep; netstat -lnp 2>/dev/null | grep 1181")
        print("\n[pc] 发 SOCKS5 UDP ASSOCIATE -> 192.168.2.1:1181")
        try:
            s = socket.create_connection((HOST, 1181), timeout=8); s.settimeout(6)
            s.sendall(b"\x05\x01\x00"); print("[pc] greeting=", s.recv(2).hex())
            s.sendall(b"\x05\x03\x00\x01" + b"\x00\x00\x00\x00" + b"\x00\x00")
            try: d = s.recv(256); print(f"[pc] ASSOCIATE reply hex={d.hex()} len={len(d)}")
            except socket.timeout: print("[pc] ASSOCIATE 无回复(超时)")
            except (ConnectionResetError, ConnectionAbortedError): print("[pc] ASSOCIATE 连接断开")
            s.close()
        except Exception as e: print(f"[pc] 异常: {e}")
        time.sleep(2)
        show(r, "strace 尾部(崩溃前最后 syscall)", f"tail -40 {TEST_DIR}/strace.log")
        show(r, "清理", f"start-stop-daemon -K -p {TEST_DIR}/clnc.pid 2>/dev/null; kill $(cat {TEST_DIR}/clnc.pid 2>/dev/null) 2>/dev/null; sleep 1; echo DONE")
    else:
        show(r, "无 strace: 看 clnc 是否往别处写日志",
             f"ls -la /tmp/ 2>/dev/null | grep -iE 'clnc|log'; ls -la /etc/storage/clnc/; "
             f"cat /etc/storage/clnc/clnc.log 2>/dev/null | tail -20; dmesg | tail -5")
    r.s.close()

if __name__ == "__main__":
    try: main()
    finally:
        srv.shutdown(); print("\n[pc] http stopped", flush=True)

"""clnc 前台诊断: 抓 clnc 收到 UDP ASSOCIATE 前的 stdout/stderr 与退出信息。
步骤: ①clnc -h 看用法/调试开关 ②前台(非-d)跑 repro 配置, 发 ASSOCIATE, 读输出 ③dmesg
"""
import socket, base64, os, json, time, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

HOST, PORT = "192.168.2.1", 7681
USER, PASS = "admin", "admin"
PC_IP = "192.168.2.165"; HTTP_PORT = 18099
TD = "/tmp/clnc_test"
HERE = os.path.dirname(os.path.abspath(__file__))
SOCK = 2191

# 用 mx_repro 的内容但改 socks 端口为 2191
src = open(os.path.join(HERE, "mv2_repro.conf")).read().replace("0.0.0.0:2181", f"0.0.0.0:{SOCK}").replace("127.0.0.1:2381", "127.0.0.1:2381")
with open(os.path.join(HERE, "tf.conf"), "w", newline="\n") as f:
    f.write(src)

class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = HTTPServer((PC_IP, HTTP_PORT), H); srv.daemon = True
threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(0.5)

def send_frame(s, op, payload):
    if isinstance(payload, str): payload = payload.encode()
    mk = os.urandom(4); masked = bytes(b ^ mk[i % 4] for i, b in enumerate(payload))
    hdr = bytes([0x80 | op]); ln = len(payload)
    if ln < 126: hdr += bytes([0x80 | ln])
    elif ln < 65536: hdr += bytes([0x80 | 126]) + ln.to_bytes(2, "big")
    else: hdr += bytes([0x80 | 127]) + ln.to_bytes(8, "big")
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
            if op in ("timeout", "error") or not p: continue
            if p[0:1] == b"0": self.output.extend(p[1:])
    def run_raw(self, data): send_frame(self.s, 0x2, b"\x30" + data.encode())
    def wait_for(self, pat, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if pat in self.output.decode("utf-8", "replace"): return True
            time.sleep(0.3); self.pump(0.3)
        return False
    def cmd(self, command, wait=8):
        self.output.clear(); self.run_raw(command + "\n"); self.pump(wait)
        return self.output.decode("utf-8", "replace")

def body(r, cmd, wait=8):
    return r.cmd(cmd, wait).replace(cmd, "", 1).strip("\r\n")

def main():
    r = Router()
    print("=== clnc -h ===")
    print(body(r, "/usr/bin/clnc -h 2>&1 | head -40; echo '---H_END---'"))
    print("\n=== else: no args / --help ===")
    print(body(r, "/usr/bin/clnc --help 2>&1 | head -20; echo '---H2_END---'"))
    print("\n=== strings: 关键字 ===")
    print(body(r, "strings /usr/bin/clnc 2>/dev/null | grep -iE 'debug|verbose|log|tproxy|udp' | head -40; echo '---S_END---'"))

    print("\n=== 前台跑 repro(非-d), 日志重定向 ===")
    print(body(r, f"mkdir -p {TD}; "
                  f"for p in $(ps w | grep 'clnc_test' | grep -v grep | awk '{{print $1}}'); do kill $p; done; sleep 1; "
                  f"wget -q -O {TD}/tf.conf http://{PC_IP}:{HTTP_PORT}/tf.conf && echo CONF_OK; "
                  f"rm -f {TD}/fg.log; "
                  f"start-stop-daemon -S -b -m -p {TD}/fg.pid -x /usr/bin/clnc -- -c {TD}/tf.conf > {TD}/fg.log 2>&1; "
                  f"sleep 2; echo -n 'INST: '; ps w | grep 'tf.conf' | grep -v grep | wc -l; "
                  f"echo -n 'LISTEN: '; netstat -lnp 2>/dev/null | grep ':{SOCK}' | tr '\\n' '|'; echo"))

    print(f"\n[pc] 发 ASSOCIATE -> {HOST}:{SOCK}")
    try:
        s = socket.create_connection((HOST, SOCK), timeout=8); s.settimeout(6)
        s.sendall(b"\x05\x01\x00"); print("[pc] greet=", s.recv(2).hex())
        s.sendall(b"\x05\x03\x00\x01" + b"\x00\x00\x00\x00" + b"\x00\x00")
        try:
            d = s.recv(256); print("[pc] ASSOCIATE reply=", d.hex(), "(len", len(d), ")")
        except socket.timeout: print("[pc] ASSOCIATE 无回复(6s)")
        except (ConnectionResetError, ConnectionAbortedError) as e: print("[pc] 连接重置:", type(e).__name__)
        s.close()
    except Exception as e:
        print("[pc] 异常:", e)
    time.sleep(2)

    print("\n=== clnc 前台输出(退出前) ===")
    print(body(r, f"echo '--- fg.log ---'; cat {TD}/fg.log 2>/dev/null; echo '--- end ---'; "
                  f"echo -n 'ALIVE: '; ps w | grep 'tf.conf' | grep -v grep | wc -l"))
    print("\n=== dmesg 尾部 ===")
    print(body(r, "dmesg 2>/dev/null | tail -8"))
    print("\n=== 清理 ===")
    print(body(r, f"kill $(cat {TD}/fg.pid 2>/dev/null) 2>/dev/null; "
                  f"for p in $(ps w | grep 'tf.conf' | grep -v grep | awk '{{print $1}}'); do kill $p; done; "
                  f"sleep 1; rm -rf {TD}; echo CLEANED"))
    print("[生产 clnc 仍在?]\n" + body(r, "ps w | grep 'clnc.conf' | grep -v grep"))
    r.s.close()

if __name__ == "__main__":
    try: main()
    finally:
        srv.shutdown(); print("\n[pc] http stopped", flush=True)

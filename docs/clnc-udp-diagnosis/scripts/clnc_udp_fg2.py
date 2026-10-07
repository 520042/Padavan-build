"""抓 clnc 非守护化(-d 去掉)时的真实 stdout/stderr, 看退出根因。
关键: 必须不带 -d, 且 git redirection 写在脚本内部; 带 -d 时 clnc 守护化会把输出丢 /dev/null。
对 3 个场景各跑一次:
  1) repro (有 httpUDP)
  2) noudp (无 httpUDP, 对照)
  3) repro + ASSOCIATE 后不杀, 观察是否自己退
"""
import socket, base64, os, json, time, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

HOST, PORT = "192.168.2.1", 7681
USER, PASS = "admin", "admin"
PC_IP = "192.168.2.165"; HTTP_PORT = 18099
TD = "/tmp/clnc_test"
HERE = os.path.dirname(os.path.abspath(__file__))
SOCK = 2192

# 基于 repro 改端口
src = open(os.path.join(HERE, "mv2_repro.conf")).read()
src = src.replace("0.0.0.0:2181", f"0.0.0.0:{SOCK}").replace("0.0.0.0:2281", "0.0.0.0:2292")
open(os.path.join(HERE, "tf.conf"), "w", newline="\n").write(src)
# noudp 变体
src2 = open(os.path.join(HERE, "mv2_noudp.conf")).read().replace("0.0.0.0:2180", f"0.0.0.0:{SOCK}").replace("0.0.0.0:2280", "0.0.0.0:2292")
open(os.path.join(HERE, "tf_noudp.conf"), "w", newline="\n").write(src2)

class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = HTTPServer((PC_IP, HTTP_PORT), H); srv.daemon = True
threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(0.5)

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
        sf(self.s, 1, json.dumps({"AuthToken": ""}))
        sf(self.s, 1, "1" + json.dumps({"columns": 200, "rows": 40}))
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
        self.o.clear(); self.raw(c + "\n"); self.pump(wait)
        return self.o.decode("utf-8", "replace")
def body(r, c, w=8): return r.cmd(c, w).replace(c, "", 1).strip("\r\n")

def scenario(r, name, conf, do_assoc):
    print(f"\n########## 场景 {name} (conf={conf}, assoc={do_assoc}) ##########")
    print(body(r, f"mkdir -p {TD}; for p in $(ps w | grep 'clnc_test' | grep -v grep | awk '{{print $1}}'); do kill $p; done; sleep 1; "
                  f"wget -q -O {TD}/tf.conf http://{PC_IP}:{HTTP_PORT}/{conf} && echo CONF_OK; "
                  f"wget -q -O {TD}/fg_run.sh http://{PC_IP}:{HTTP_PORT}/fg_run.sh; chmod +x {TD}/fg_run.sh; "
                  f"echo -n 'RUNNING: '; start-stop-daemon -S -b -m -p {TD}/fg.pid -x {TD}/fg_run.sh && sleep 2; "
                  f"ps w | grep 'tf.conf' | grep -v grep | wc -l"))
    if do_assoc:
        print(f"[pc] 发 ASSOCIATE -> {HOST}:{SOCK}")
        try:
            s = socket.create_connection((HOST, SOCK), timeout=8); s.settimeout(6)
            s.sendall(b"\x05\x01\x00"); print("[pc] greet=", s.recv(2).hex())
            s.sendall(b"\x05\x03\x00\x01" + b"\x00\x00\x00\x00" + b"\x00\x00")
            try:
                d = s.recv(256); print("[pc] reply=", d.hex(), "(len", len(d), ")")
            except socket.timeout: print("[pc] 无回复")
            except (ConnectionResetError, ConnectionAbortedError) as e: print("[pc] 重置:", type(e).__name__)
            s.close()
        except Exception as e: print("[pc] 异常:", e)
    time.sleep(2)
    print("--- clnc 的 stdout/stderr(out.txt) ---")
    print(body(r, f"cat {TD}/out.txt 2>/dev/null; echo; echo '--- end ---'; "
                  f"echo -n 'ALIVE: '; ps w | grep 'tf.conf' | grep -v grep | wc -l"))
    body(r, f"kill $(cat {TD}/fg.pid 2>/dev/null) 2>/dev/null; for p in $(ps w | grep 'tf.conf' | grep -v grep | awk '{{print $1}}'); do kill $p; done; sleep 1")

def main():
    r = R()
    scenario(r, "A: repro 启动未发ASSOCIATE", "tf.conf", False)
    scenario(r, "B: repro 发ASSOCIATE", "tf.conf", True)
    scenario(r, "C: noudp 发ASSOCIATE(对照)", "tf_noudp.conf", True)
    print("\n[清理]\n" + body(r, f"rm -rf {TD}; echo CLEANED"))
    print("[生产 clnc]\n" + body(r, "ps w | grep 'clnc.conf' | grep -v grep"))
    r.s.close()

if __name__ == "__main__":
    try: main()
    finally:
        srv.shutdown(); print("\n[pc] http stopped", flush=True)

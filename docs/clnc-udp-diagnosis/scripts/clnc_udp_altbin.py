"""测试官方旧版 mipsle clnc 是否能绕过 httpUDP 的 buffer-overflow abort。
每个候选二进制: 上机 -> 跑 repro 配置 -> 发 UDP ASSOCIATE -> 看 out.txt/存活。
"""
import socket, base64, os, json, time, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

HOST, PORT = "192.168.2.1", 7681
USER, PASS = "admin", "admin"
PC_IP = "192.168.2.165"; HTTP_PORT = 18099
TD = "/tmp/clnc_test"
HERE = os.path.dirname(os.path.abspath(__file__))
SOCK = 2193
CANDS = [("v1.2(R3G原生)", None), ("v1.0", "alt_v10"), ("v0.9.1", "alt_v091"), ("v0.8.1", "alt_v081")]

# 生成端口 2193 的 repro conf
src = open(os.path.join(HERE, "mv2_repro.conf")).read().replace("0.0.0.0:2181", f"0.0.0.0:{SOCK}").replace("0.0.0.0:2281", "0.0.0.0:2293")
open(os.path.join(HERE, "alt_tf.conf"), "w", newline="\n").write(src)
# 生成 runner (接收二进制路径参数)
open(os.path.join(HERE, "alt_run.sh"), "w", newline="\n").write(
    "#!/bin/sh\nrm -f /tmp/clnc_test/out.txt\n"
    '"$1" -c /tmp/clnc_test/tf.conf -d > /tmp/clnc_test/out.txt 2>&1\n'
    'echo "RC=$?" >> /tmp/clnc_test/out.txt\n')

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
        sf(self.s, 1, json.dumps({"AuthToken": ""})); sf(self.s, 1, "1" + json.dumps({"columns": 200, "rows": 40}))
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

def main():
    r = R()
    print(body(r, f"mkdir -p {TD}; for p in $(ps w | grep 'clnc_test' | grep -v grep | awk '{{print $1}}'); do kill $p; done; sleep 1; "
                  f"wget -q -O {TD}/tf.conf http://{PC_IP}:{HTTP_PORT}/alt_tf.conf; "
                  f"wget -q -O {TD}/alt_run.sh http://{PC_IP}:{HTTP_PORT}/alt_run.sh; chmod +x {TD}/alt_run.sh; echo PREP_OK"))
    results = []
    for name, asset in CANDS:
        print(f"\n########## {name} ##########")
        if asset is None:
            binf = "/usr/bin/clnc"
            print(body(r, f"kill $(cat {TD}/b.pid 2>/dev/null) 2>/dev/null; sleep 1; "
                          f"for p in $(ps w | grep 'tf.conf' | grep -v grep | awk '{{print $1}}'); do kill $p; done; sleep 1; echo USE=$binf"))
        else:
            print(body(r, f"kill $(cat {TD}/b.pid 2>/dev/null) 2>/dev/null; sleep 1; "
                          f"for p in $(ps w | grep 'tf.conf' | grep -v grep | awk '{{print $1}}'); do kill $p; done; "
                          f"wget -q -O {TD}/clnc_alt http://{PC_IP}:{HTTP_PORT}/{asset} && chmod +x {TD}/clnc_alt; "
                          f"echo -n 'SZ='; wc -c < {TD}/clnc_alt; echo -n 'MD5='; md5sum {TD}/clnc_alt | cut -c1-32"))
            binf = f"{TD}/clnc_alt"
        print(body(r, f"start-stop-daemon -S -b -m -p {TD}/b.pid -x {TD}/alt_run.sh -- {binf}; sleep 2; "
                      f"echo -n 'INST: '; ps w | grep 'tf.conf' | grep -v grep | wc -l; "
                      f"echo -n 'LISTEN: '; netstat -lnp 2>/dev/null | grep ':{SOCK}' | tr '\\n' '|'; echo"))
        # ASSOCIATE
        print(f"[pc] ASSOCIATE -> {HOST}:{SOCK}")
        try:
            s = socket.create_connection((HOST, SOCK), timeout=8); s.settimeout(6)
            s.sendall(b"\x05\x01\x00"); g = s.recv(2)
            s.sendall(b"\x05\x03\x00\x01" + b"\x00\x00\x00\x00" + b"\x00\x00")
            try:
                d = s.recv(256); print("[pc] reply=", d.hex(), "(len", len(d), ")")
            except socket.timeout: print("[pc] 无回复")
            except (ConnectionResetError, ConnectionAbortedError) as e: print("[pc] 重置:", type(e).__name__)
            s.close()
        except Exception as e: print("[pc] 连接失败:", e)
        time.sleep(2)
        st = body(r, f"cat {TD}/out.txt 2>/dev/null; echo; echo -n 'ALIVE: '; ps w | grep 'tf.conf' | grep -v grep | wc -l")
        print(st)
        alive = "ALIVE: 1" in st
        results.append((name, alive, st.replace("\n", " ")[:120]))
    print(body(r, f"kill $(cat {TD}/b.pid 2>/dev/null) 2>/dev/null; for p in $(ps w | grep 'tf.conf' | grep -v grep | awk '{{print $1}}'); do kill $p; done; sleep 1; rm -rf {TD}; echo CLEANED"))
    print("[生产 clnc]\n" + body(r, "ps w | grep 'clnc.conf' | grep -v grep"))
    print("\n================ 旧版 mipsle 结果 ================")
    for name, alive, snip in results:
        print(f"{name:<16} {'存活' if alive else '自退'}  | {snip}")
    r.s.close()

if __name__ == "__main__":
    try: main()
    finally:
        srv.shutdown(); print("\n[pc] http stopped", flush=True)

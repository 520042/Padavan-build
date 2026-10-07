"""判断 httpUDP 越界是否与 ASSOCIATE 请求的具体形态有关(以及是否 greeting 后即触发)。
每次用全新 clnc 实例(原生 v1.2 + repro conf, 端口 2193)。
请求形态:
  S1 纯 greeting 后保持不动(不发 request)
  S2 ASSOCIATE 0.0.0.0:0 (atyp1)
  S3 ASSOCIATE 8.8.8.8:53 (atyp1, 真实目标)
  S4 ASSOCIATE 域名 example.com:53 (atyp3)
"""
import socket, base64, os, json, time, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

HOST, PORT = "192.168.2.1", 7681
USER, PASS = "admin", "admin"
PC_IP = "192.168.2.165"; HTTP_PORT = 18099
TD = "/tmp/clnc_test"
HERE = os.path.dirname(os.path.abspath(__file__))
SOCK = 2193
src = open(os.path.join(HERE, "mv2_repro.conf")).read().replace("0.0.0.0:2181", f"0.0.0.0:{SOCK}").replace("0.0.0.0:2281", "0.0.0.0:2293")
open(os.path.join(HERE, "av_tf.conf"), "w", newline="\n").write(src)

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

RUN = os.path.join(HERE, "av_run.sh")
open(RUN, "w", newline="\n").write("#!/bin/sh\nrm -f /tmp/clnc_test/out.txt\n"
    "/usr/bin/clnc -c /tmp/clnc_test/av_tf.conf -d > /tmp/clnc_test/out.txt 2>&1\necho \"RC=$?\" >> /tmp/clnc_test/out.txt\n")

def start(r):
    return body(r, f"for p in $(ps w | grep 'av_tf.conf' | grep -v grep | awk '{{print $1}}'); do kill $p; done; sleep 1; "
                  f"mkdir -p {TD}; wget -q -O {TD}/av_tf.conf http://{PC_IP}:{HTTP_PORT}/av_tf.conf; "
                  f"wget -q -O {TD}/av_run.sh http://{PC_IP}:{HTTP_PORT}/av_run.sh; chmod +x {TD}/av_run.sh; "
                  f"start-stop-daemon -S -b -m -p {TD}/av.pid -x {TD}/av_run.sh; sleep 2; "
                  f"echo -n 'INST: '; ps w | grep 'av_tf.conf' | grep -v grep | wc -l")

def probe(name, payloads, hold):
    return name, payloads, hold

CASES = [
    ("S1 greeting only (不发request)", None, True),
    ("S2 ASSOCIATE 0.0.0.0:0", b"\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00", False),
    ("S3 ASSOCIATE 8.8.8.8:53", b"\x05\x03\x00\x01\x08\x08\x08\x08\x00\x35", False),
    ("S4 ASSOCIATE example.com:53", b"\x05\x03\x00\x03\x0bexample.com\x00\x35", False),
]

def main():
    r = R()
    print(body(r, f"mkdir -p {TD}; echo OK"))
    res = []
    for name, payload, hold in CASES:
        print(f"\n########## {name} ##########")
        print(start(r))
        try:
            s = socket.create_connection((HOST, SOCK), timeout=8); s.settimeout(6)
            s.sendall(b"\x05\x01\x00"); g = s.recv(2)
            note = ""
            if payload:
                s.sendall(payload)
                try:
                    d = s.recv(256); note = f"reply={d.hex()} len={len(d)}"
                except socket.timeout: note = "无回复"
                except (ConnectionResetError, ConnectionAbortedError) as e: note = f"重置:{type(e).__name__}"
            else:
                time.sleep(3); note = "greeting后保持3s"
            s.close()
            print(f"[pc] greet={g.hex()} {note}")
        except Exception as e:
            print("[pc] 异常:", e)
        time.sleep(2)
        st = body(r, f"cat {TD}/out.txt 2>/dev/null; echo; echo -n 'ALIVE: '; ps w | grep 'av_tf.conf' | grep -v grep | wc -l")
        print(st)
        res.append((name, "ALIVE: 1" in st, st.replace("\n", " ")[:100]))
    body(r, f"for p in $(ps w | grep 'av_tf.conf' | grep -v grep | awk '{{print $1}}'); do kill $p; done; sleep 1; rm -rf {TD}; echo CLEANED")
    print("\n================ ASSOCIATE 形态结果 ================")
    for name, alive, snip in res:
        print(f"{name:<32} {'存活' if alive else '自退'} | {snip}")
    print("[生产 clnc]\n" + body(r, "ps w | grep 'clnc.conf' | grep -v grep"))
    r.s.close()

if __name__ == "__main__":
    try: main()
    finally:
        srv.shutdown(); print("\n[pc] http stopped", flush=True)

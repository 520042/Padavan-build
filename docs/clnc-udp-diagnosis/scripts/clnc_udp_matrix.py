"""clnc UDP 配置变体矩阵测试 (PC 侧驱动, 经 ttyd WebSocket 控 R3G)
变体:
  noudp    : 无 httpUDP 段 (对照, 期望存活)
  repro    : 历史写法(仅 udp_socks5_listen, destAddr4=WAP, header_host=cns) (期望自退)
  tproxy   : repro + udp_tproxy_listen        (官方示例都有它)
  official : 官方普通免流写法(两个listen, destaddr=header_host=免流节点)
  noheader : 最简(仅 udp_socks5_listen+destAddr4+httpMod, 无 encrypt/header_host)
各变体用独立 conf(端口 6750/1181/5353/6751), 互不冲突, 也不碰在跑的生产 clnc(6650/1081/53)。
"""
import socket, base64, os, json, time, sys, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

HOST, PORT = "192.168.2.1", 7681
USER, PASS = "admin", "admin"
PC_IP = "192.168.2.165"; HTTP_PORT = 18099
TD = "/tmp/clnc_test"
VARIANTS = ["noudp", "repro", "tproxy", "official", "noheader"]

class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
here = os.path.dirname(os.path.abspath(__file__))
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
        if b"101" not in buf.split(b"\r\n\r\n", 1)[0]: raise RuntimeError("handshake failed")
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
    out = r.cmd(cmd, wait)
    return out.replace(cmd, "", 1).strip("\r\n")

def associate():
    """PC -> R3G:1181, 发 greet + UDP ASSOCIATE, 返回 (greet_hex, assoc_reply_hex, state)"""
    try:
        s = socket.create_connection((HOST, 1181), timeout=8); s.settimeout(6)
        s.sendall(b"\x05\x01\x00"); g = s.recv(2)
        s.sendall(b"\x05\x03\x00\x01" + b"\x00\x00\x00\x00" + b"\x00\x00")
        try:
            d = s.recv(256)
            state = "存活(有回复)" if len(d) > 0 else "连接被关闭(进程已退)"
            r = (g.hex(), d.hex(), state)
        except socket.timeout:
            r = (g.hex(), "<6s无回复>", "超时(可能正在退)")
        except (ConnectionResetError, ConnectionAbortedError) as e:
            r = (g.hex(), f"<{type(e).__name__}>", "连接被重置(已退)")
        s.close(); return r
    except Exception as e:
        return ("<无greet>", f"<{e}>", "无法连接(socks5监听不在)")

def main():
    r = Router()
    print("[init] 加载 tproxy 模块(供 tproxy 变体 bind)")
    print(body(r, "lsmod | grep -c tproxy; "
                  "insmod /lib/modules/3.4.113/kernel/net/netfilter/nf_tproxy_core.ko 2>&1; "
                  "insmod /lib/modules/3.4.113/kernel/net/netfilter/xt_TPROXY.ko 2>&1; "
                  "lsmod | grep -E 'tproxy|TPROXY'; echo TPROXY_READY"))
    print("[init] 拉 run.sh, 建目录")
    print(body(r, f"mkdir -p {TD}; wget -q -O {TD}/run.sh http://{PC_IP}:{HTTP_PORT}/clnc_run.sh; "
                  f"chmod +x {TD}/run.sh; echo READY"))

    results = []
    for v in VARIANTS:
        print(f"\n########## 变体 {v} ##########")
        # 清理 + 上传
        print(body(r, f"start-stop-daemon -K -p {TD}/clnc.pid 2>/dev/null; kill $(cat {TD}/clnc.pid 2>/dev/null) 2>/dev/null; "
                      f"sleep 1; : > {TD}/clnc.log; "
                      f"wget -q -O {TD}/test.conf http://{PC_IP}:{HTTP_PORT}/mx_{v}.conf; "
                      f"echo UDP_SEG=$(grep -c -i httpUDP {TD}/test.conf)"))
        # 启动
        print(body(r, f"start-stop-daemon -S -b -m -p {TD}/clnc.pid -x {TD}/run.sh >> {TD}/clnc.log 2>&1 || echo SSD_FAIL; "
                      f"sleep 2; "
                      f"echo -n 'PS: '; ps w | grep 'test.conf' | grep -v grep | wc -l; "
                      f"echo -n 'LISTEN: '; netstat -lnp 2>/dev/null | grep -E '1181|6751' | tr '\\n' '|'; echo"))
        # 发 ASSOCIATE
        g, d, state = associate()
        print(f"[pc] greet={g}  ASSOCIATE_reply={d}  => {state}")
        time.sleep(2)
        # 检查存活 + 退出码
        st = body(r, f"echo -n 'ALIVE: '; ps w | grep 'test.conf' | grep -v grep | wc -l; "
                     f"echo '--- log ---'; cat {TD}/clnc.log 2>/dev/null; echo '--- end ---'")
        print(st)
        alive = "ALIVE: 1" in st or "ALIVE:1" in st.replace(" ", "")
        results.append((v, state, alive))

    # 清理
    print(body(r, f"start-stop-daemon -K -p {TD}/clnc.pid 2>/dev/null; kill $(cat {TD}/clnc.pid 2>/dev/null) 2>/dev/null; "
                  f"sleep 1; rm -rf {TD}; echo CLEANED"))
    prod = body(r, "ps w | grep 'clnc.conf' | grep -v grep")
    print("\n[生产 clnc 仍在?]\n" + prod)

    print("\n================ 矩阵结果 ================")
    print(f"{'变体':<10}{'ASSOCIATE后状态':<28}{'进程存活'}")
    for v, state, alive in results:
        print(f"{v:<10}{state:<28}{'是' if alive else '否(自退)'}")
    r.s.close()

if __name__ == "__main__":
    try: main()
    finally:
        srv.shutdown(); print("\n[pc] http stopped", flush=True)

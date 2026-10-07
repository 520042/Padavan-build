"""clnc UDP 配置变体矩阵 (v2, 修正版)
修正上轮污染: ①每变体独立端口 ②启动前清干净所有遗留测试实例并校验 ③noudp 变体补齐
变体(端口: socks5/tcp/tproxy/dns):
  noudp    2180/2280/-/2380  无 httpUDP 段(对照)
  repro    2181/2281/-/2381  历史写法(仅 udp_socks5_listen, destAddr4=WAP, header_host=cns)
  tproxy   2182/2282/2382/2382 repro + udp_tproxy_listen
  official 2183/2283/2383/2383 官方普通免流写法(两个listen, destaddr=header_host=免流节点)
  noheader 2184/2284/-/2384  最简(仅 udp_socks5_listen+destAddr4+httpMod)
生产 clnc 用 6650/1081/53, 完全不碰。
"""
import socket, base64, os, json, time, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

HOST, PORT = "192.168.2.1", 7681
USER, PASS = "admin", "admin"
PC_IP = "192.168.2.165"; HTTP_PORT = 18099
TD = "/tmp/clnc_test"
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- 生成 conf ----------
GRID = """
tcp::Global {{
tcp_listen = 0.0.0.0:{tcp};
}}
tcpProxy::http_proxy {{
destAddr4 = ${{dst_ip}};
httpMod = http;
}}
httpMod::http {{
save_line = "User-Agent" -> "0";
del_line = host;
del_line = User-Agent;
set_first = "[M] http://[H_P][U] [V]\\r\\nHost: [H_P]\\r\\nUser-Agent: use_value(User-Agent) baiduboxapp\\r\\n";
}}
tcpProxy::https_proxy {{
destAddr4 = ${{dst_ip}};
tunnel_proxy = httpOverTunnel;
tunnelHttpMod = tunnel;
}}
httpMod::tunnel {{
del_line = host;
set_first = "[M] [H] [V]\\r\\nHost: [H]\\r\\n";
}}
tcpAcl::firstConnect {{
tcpProxy = https_proxy;
matchMode = firstMatch;
reMatch = http;
continue: dst_port != 80;
continue: dst_port != 8080;
dst_port != 6650;
}}
tcpAcl::http {{
tcpProxy = http_proxy;
continue: method != IS_NOT_HTTP|CONNECT|OPTIONS;
reg_string != WebSocket;
}}
tcpAcl::CONNECT {{
tcpProxy = https_proxy;
dst_port != 0;
}}
dns::Global {{
dns_listen = 0.0.0.0:{dns};
cachePath = /dev/null;
}}
dnsAcl {{
httpMod = dnshttp;
destAddr4 = ${{dst_ip}};
header_host = 119.29.29.29;
query_type = A;
}}
httpMod::dnshttp {{
set_first = "[M] http://[H_P]/d?dn=[D]&type=[DT]&ttl=1 [V]\\r\\nHost: [H_P]\\r\\nConnection: Close\\r\\n";
}}
socks5::recv_socks5 {{
socks5_listen = 0.0.0.0:{socks};
socks5_dns = 127.0.0.1:{dns};
handshake_timeout = 60;
}}
"""

VARS = """variables {
dst_ip = 10.0.0.200:80;
cns_server = 152.136.154.154:443;
cns_passwd = yaohuo;
}
"""

HDR = {
 "noudp": "// [noudp] 对照: 无 httpUDP 段\n",
 "repro": ("// [repro] 历史写法\n"
   "httpUDP::udp {\nudp_socks5_listen = 0.0.0.0:@SOCKS@\n"
   "destAddr4 = ${dst_ip};\nhttpMod = tunnel;\nencrypt = ${cns_passwd};\nheader_host = ${cns_server};\n}\n"),
 "tproxy": ("// [tproxy] repro + udp_tproxy_listen\n"
   "httpUDP::udp {\nudp_socks5_listen = 0.0.0.0:@SOCKS@\n"
   "udp_tproxy_listen = 0.0.0.0:@TPROXY@;\n"
   "destAddr4 = ${dst_ip};\nhttpMod = tunnel;\nencrypt = ${cns_passwd};\nheader_host = ${cns_server};\n}\n"),
 "official": ("// [official] 官方普通免流写法\n"
   "httpUDP::udp {\nudp_socks5_listen = 0.0.0.0:@SOCKS@\n"
   "udp_tproxy_listen = 0.0.0.0:@TPROXY@;\n"
   "destaddr = ${dst_ip};\nhttpMod = tunnel;\nencrypt = ${cns_passwd};\nheader_host = ${dst_ip};\n}\n"),
 "noheader": ("// [noheader] 最简\n"
   "httpUDP::udp {\nudp_socks5_listen = 0.0.0.0:@SOCKS@\n"
   "destAddr4 = ${dst_ip};\nhttpMod = tunnel;\n}\n"),
}
PORTS = {
 "noudp":    dict(socks=2180, tcp=2280, tproxy=None, dns=2380),
 "repro":    dict(socks=2181, tcp=2281, tproxy=None, dns=2381),
 "tproxy":   dict(socks=2182, tcp=2282, tproxy=2382, dns=2383),
 "official": dict(socks=2183, tcp=2283, tproxy=2383, dns=2384),
 "noheader": dict(socks=2184, tcp=2284, tproxy=None, dns=2385),
}
VARIANTS = ["noudp", "repro", "tproxy", "official", "noheader"]

for v in VARIANTS:
    p = PORTS[v]
    hdr = HDR[v].replace("@SOCKS@", str(p["socks"])).replace("@TPROXY@", str(p["tproxy"]))
    txt = VARS + hdr + GRID.format(**p)
    with open(os.path.join(HERE, f"mv2_{v}.conf"), "w", newline="\n") as f:
        f.write(txt)
    with open(os.path.join(HERE, f"mr2_{v}.sh"), "w", newline="\n") as f:
        f.write(f"#!/bin/sh\n/usr/bin/clnc -c {TD}/t_{v}.conf -d\n"
                f"echo \"CLNC_EXIT=$?\" >> {TD}/{v}.log 2>&1\n")
print("[gen] confs + run scripts written", flush=True)

# ---------- PC HTTP ----------
class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = HTTPServer((PC_IP, HTTP_PORT), H); srv.daemon = True
threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(0.5)

# ---------- ttyd ----------
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

def associate(socks_port):
    try:
        s = socket.create_connection((HOST, socks_port), timeout=8); s.settimeout(6)
        s.sendall(b"\x05\x01\x00"); g = s.recv(2)
        s.sendall(b"\x05\x03\x00\x01" + b"\x00\x00\x00\x00" + b"\x00\x00")
        try:
            d = s.recv(256)
            state = "存活(有回复)" if len(d) > 0 else "连接被关闭"
            return g.hex(), d.hex(), state
        except socket.timeout:
            return g.hex(), "<6s无回复>", "超时"
        except (ConnectionResetError, ConnectionAbortedError) as e:
            return g.hex(), f"<{type(e).__name__}>", "连接被重置"
        finally:
            s.close()
    except Exception as e:
        return "<无greet>", f"<{type(e).__name__}>", "无法连接(监听不在)"

KILL_ALL = ("for p in $(ps w | grep 'clnc_test' | grep -v grep | awk '{print $1}'); do kill $p; done; sleep 2; "
            "echo -n 'LEFTOVER: '; ps w | grep 'clnc_test' | grep -v grep | wc -l")

def main():
    r = Router()
    print("[init] tproxy 模块:")
    print(body(r, "insmod /lib/modules/3.4.113/kernel/net/netfilter/nf_tproxy_core.ko 2>&1; "
                  "insmod /lib/modules/3.4.113/kernel/net/netfilter/xt_TPROXY.ko 2>&1; "
                  "lsmod | grep -E 'tproxy|TPROXY' | tr '\\n' '|'; echo OK"))
    print("[init] 清干净所有遗留测试实例(不碰生产 clnc.conf):")
    print(body(r, KILL_ALL))
    print(body(r, f"mkdir -p {TD}; wget -q -O {TD}/dummy http://{PC_IP}:{HTTP_PORT}/clnc_run.sh && echo NET_OK"))

    results = []
    for v in VARIANTS:
        p = PORTS[v]
        print(f"\n########## 变体 {v} (socks5:{p['socks']}) ##########")
        print(body(r, f"rm -f {TD}/{v}.log; "
                      f"wget -q -O {TD}/t_{v}.conf http://{PC_IP}:{HTTP_PORT}/mv2_{v}.conf && "
                      f"wget -q -O {TD}/r_{v}.sh http://{PC_IP}:{HTTP_PORT}/mr2_{v}.sh; "
                      f"chmod +x {TD}/r_{v}.sh; echo UDP_SEG=$(grep -c -i httpUDP {TD}/t_{v}.conf)"))
        print(body(r, f"start-stop-daemon -S -b -m -p {TD}/{v}.pid -x {TD}/r_{v}.sh >> {TD}/{v}.log 2>&1; "
                      f"sleep 2; echo -n 'INST: '; ps w | grep 't_{v}.conf' | grep -v grep | wc -l; "
                      f"echo -n 'LISTEN: '; netstat -lnp 2>/dev/null | grep -E ':{p['socks']}|:{p['tproxy'] or 'x'}' | tr '\\n' '|'; echo"))
        g, d, state = associate(p['socks'])
        print(f"[pc] greet={g}  reply={d}  => {state}")
        time.sleep(2)
        st = body(r, f"echo -n 'ALIVE: '; ps w | grep 't_{v}.conf' | grep -v grep | wc -l; "
                     f"echo -n 'EXIT: '; cat {TD}/{v}.log 2>/dev/null | tr '\\n' '|'; echo")
        print(st)
        alive = "ALIVE: 1" in st
        results.append((v, state, alive))
        print(body(r, f"kill $(cat {TD}/{v}.pid 2>/dev/null) 2>/dev/null; "
                      f"for pp in $(ps w | grep 't_{v}.conf' | grep -v grep | awk '{{print $1}}'); do kill $pp; done; sleep 1; echo K"))

    print(body(r, f"rm -rf {TD}; echo CLEANED"))
    print("[生产 clnc 仍在?]\n" + body(r, "ps w | grep 'clnc.conf' | grep -v grep"))

    print("\n================ 矩阵结果 (v2) ================")
    print(f"{'变体':<10}{'ASSOCIATE后':<18}{'进程存活'}")
    for v, state, alive in results:
        print(f"{v:<10}{state:<18}{'是' if alive else '否(自退)'}")
    r.s.close()

if __name__ == "__main__":
    try: main()
    finally:
        srv.shutdown(); print("\n[pc] http stopped", flush=True)

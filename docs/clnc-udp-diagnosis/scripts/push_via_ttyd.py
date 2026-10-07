"""通过已认证的 ttyd 通道, 分块 base64 把本地文件推到路由器(绕过超长命令行截断/CRLF/防火墙)。
用法: python push_via_ttyd.py 本地文件 远端路径 [本地文件 远端路径 ...]
- base64 分块(每块<700字符)逐块 echo >> 临时文件, 最后 base64 -d 还原
- 推送后用 md5sum 比对本地/远端, 确保字节一致
- .sh 自动 chmod +x
"""
import os
import sys
import socket
import base64
import hashlib
import json
import time

HOST, PORT = os.environ.get("TTYD_HOST", "192.168.2.1"), int(os.environ.get("TTYD_PORT", "7681"))
CHUNK = 700

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
            if not c:
                return "closed", b""
            hdr += c
        op, ln = hdr[0] & 0x0F, hdr[1] & 0x7F
        if ln == 126:
            d = b""
            while len(d) < 2:
                d += s.recv(2 - len(d))
            ln = int.from_bytes(d, "big")
        elif ln == 127:
            d = b""
            while len(d) < 8:
                d += s.recv(8 - len(d))
            ln = int.from_bytes(d, "big")
        p = b""
        while len(p) < ln:
            c = s.recv(min(65536, ln - len(p)))
            if not c:
                return "closed", b""
            p += c
        return op, p
    except socket.timeout:
        return "timeout", b""
    except OSError as e:
        return "error", str(e).encode()

def main():
    pairs = []
    a = sys.argv[1:]
    i = 0
    while i + 1 < len(a):
        pairs.append((a[i], a[i + 1]))
        i += 2
    if not pairs:
        print("用法: python push_via_ttyd.py 本地 远端 [本地 远端 ...]")
        return

    SRC = os.environ.get("TTYD_SRC") or None
    s = socket.create_connection((HOST, PORT), timeout=10, source_address=(SRC, 0) if SRC else None)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET /ws HTTP/1.1\r\nHost: {HOST}:{PORT}\r\nUpgrade: websocket\r\n"
               "Connection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
               "Sec-WebSocket-Protocol: tty\r\n\r\n").encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        c = s.recv(4096)
        if not c:
            print("no handshake"); return
        buf += c
    if b"101" not in buf.split(b"\r\n\r\n", 1)[0]:
        print("HANDSHAKE FAILED"); return

    out = bytearray()
    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            op, p = recv_frame(s, max(0.2, end - time.time()))
            if op == "closed":
                return False
            if op in ("timeout", "error") or not p:
                continue
            if p[0:1] == b"0":
                out.extend(p[1:])
        return True
    def wait_for(pat, timeout=12):
        end = time.time() + timeout
        while time.time() < end:
            if pat in out.decode("utf-8", errors="replace"):
                return True
            pump(0.3)
        return False
    def run(cmd, wait=1.5):
        out.clear()
        send_frame(s, 0x2, b"\x30" + (cmd + "\n").encode())
        pump(wait)
        return out.decode("utf-8", "replace")

    send_frame(s, 0x1, json.dumps({"AuthToken": ""}))
    send_frame(s, 0x1, "1" + json.dumps({"columns": 200, "rows": 40}))
    pump(2.0)
    if not wait_for("login:", 8):
        if "#" not in out.decode("utf-8", "replace"):
            print("[abort] no login"); return
    else:
        send_frame(s, 0x2, b"\x30" + b"admin\n"); time.sleep(0.5); pump(1.0)
        out.clear(); wait_for("assword:", 8)
        send_frame(s, 0x2, b"\x30" + b"admin\n"); wait_for("#", 10); out.clear()

    for idx, (local, remote) in enumerate(pairs):
        with open(local, "rb") as f:
            data = f.read()
        local_md5 = hashlib.md5(data).hexdigest()
        b64 = base64.b64encode(data).decode()
        tmp = f"/tmp/.push_{idx}"
        # 建目录
        d = os.path.dirname(remote)
        if d:
            run(f"mkdir -p {d}", 0.8)
        # 分块写入临时文件
        run(f"rm -f {tmp}", 0.6)
        for k in range(0, len(b64), CHUNK):
            chunk = b64[k:k + CHUNK]
            if k == 0:
                run(f"echo {chunk} > {tmp}", 0.8)
            else:
                run(f"echo {chunk} >> {tmp}", 0.8)
        # 解码
        run(f"base64 -d {tmp} > {remote}", 1.2)
        run(f"rm -f {tmp}", 0.6)
        if remote.endswith(".sh"):
            run(f"chmod +x {remote}", 0.6)
        # 校验 md5
        r = run(f"md5sum {remote}", 1.2)
        remote_md5 = ""
        for line in r.splitlines():
            line = line.strip()
            if line and all(c in "0123456789abcdef" for c in line.split()[0]) and len(line.split()[0]) == 32:
                remote_md5 = line.split()[0]
                break
        ok = (remote_md5 == local_md5)
        print(f"[push] {local} -> {remote}  {len(data)}B  md5 {'OK' if ok else 'MISMATCH'} ({remote_md5})")
    s.close()

main()

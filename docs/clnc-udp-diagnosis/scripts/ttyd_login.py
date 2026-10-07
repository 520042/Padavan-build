"""ttyd 1.6.2 客户端 — 自动 login 并执行验证命令"""
import os
import socket, base64, os, json, time, sys, urllib.request

HOST, PORT = os.environ.get("TTYD_HOST", "192.168.2.1"), int(os.environ.get("TTYD_PORT", "7681"))
USER, PASS = "admin", "admin"

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
    cmds = sys.argv[1:] or [
        'cat /proc/version',
        'cat /proc/mtd',
        'uptime',
    ]

    # 双网卡环境下必须绑定源地址(公司有线网也是 192.168.2.x, 默认路由会走错口)
    SRC = os.environ.get("TTYD_SRC") or None
    s = socket.create_connection((HOST, PORT), timeout=10,
                                 source_address=(SRC, 0) if SRC else None)
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
    head, _ = buf.split(b"\r\n\r\n", 1)
    if b"101" not in head:
        print("HANDSHAKE FAILED:", head[:200]); return
    print("[ws] connected")

    output = bytearray()

    def pump(seconds, quiet=False):
        end = time.time() + seconds
        while time.time() < end:
            op, p = recv_frame(s, max(0.2, end - time.time()))
            if op == "closed":
                print("[ws closed]"); return False
            if op in ("timeout", "error") or not p:
                continue
            cmd, data = p[0:1], p[1:]
            if cmd == b"0":
                output.extend(data)
        return True

    def wait_for(pattern, timeout=15, echo=False):
        """等待输出中出现 pattern"""
        end = time.time() + timeout
        while time.time() < end:
            chunk = output.decode("utf-8", errors="replace")
            if pattern in chunk:
                return True
            time.sleep(0.3)
            pump(0.3)
        if echo:
            print("[timeout waiting for]", pattern,
                  "| recent:", output.decode('utf-8', errors='replace')[-200:])
        return False

    # 登录序列
    send_frame(s, 0x1, json.dumps({"AuthToken": ""}))
    send_frame(s, 0x1, "1" + json.dumps({"columns": 120, "rows": 30}))
    pump(2.0)

    if not wait_for("login:", 8, echo=True):
        # 可能已是 shell
        if "#" not in output.decode("utf-8", errors="replace"):
            print("[abort] no login prompt, no shell"); return
    else:
        send_frame(s, 0x2, b"\x30" + b"admin\n")
        time.sleep(0.5); pump(1.0)
        output.clear()
        wait_for("assword:", 8, echo=True)
        send_frame(s, 0x2, b"\x30" + b"admin\n")
        # 等登录成功(出现 # 提示符)
        wait_for("#", 10, echo=True)
        output.clear()
        print("[login] done")

    # 执行命令
    wait_s = float(os.environ.get("TTYD_WAIT", "3.5"))
    for cmd in cmds:
        output.clear()
        send_frame(s, 0x2, b"\x30" + (cmd + "\n").encode())
        pump(wait_s)
        text = output.decode("utf-8", errors="replace")
        print(f"\n$ {cmd}")
        print(text.strip()[:4000])
    s.close()

main()

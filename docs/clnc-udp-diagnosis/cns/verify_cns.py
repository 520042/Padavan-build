#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""复验 VPS 上的 CNS 与 udp2raw 状态 (只读)。密码从环境变量 VPS_PASS 读取。"""
import os, paramiko

HOST = "<VPS_IP>"; PORT = 22; USER = "root"
PASS = os.environ.get("VPS_PASS", "")

ssh = paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=20,
            look_for_keys=False, allow_agent=False)

def run(c, t=30):
    _, o, e = ssh.exec_command(c, timeout=t)
    return o.read().decode(errors="replace"), e.read().decode(errors="replace")

CHECKS = [
    ("CNS 服务状态", "systemctl is-active cns; systemctl is-enabled cns"),
    ("CNS 监听", "ss -ltnp | grep -E ':443\\b'"),
    ("CNS 进程", "pgrep -a cns"),
    ("CNS 日志", "journalctl -u cns -n 12 --no-pager 2>&1 | tail -12"),
    ("本机连通(TCP 443)", "python3 -c \"import socket;s=socket.socket();s.settimeout(4);s.connect(('127.0.0.1',443));print('LOCAL443_OK');s.close()\""),
    ("HTTP DNS 自测(dn=baidu)", "curl -s -m 8 'http://127.0.0.1:443/?dn=www.baidu.com&type=A&ttl=1' -o /dev/null -w 'code=%{http_code} size=%{size_download}\\n' 2>&1"),
    ("裸 GET 自测", "curl -s -m 6 -o /dev/null -w 'code=%{http_code}\\n' http://127.0.0.1:443/ 2>&1"),
    ("udp2raw 服务", "systemctl is-active udp2raw; ss -lnptu | grep ':4096'"),
    ("ufw/iptables 443", "iptables -L INPUT -n 2>/dev/null | grep -E '443|policy' | head -4"),
]
for t, c in CHECKS:
    o, e = run(c)
    print("\n===== %s =====" % t)
    print(o, (("ERR:" + e) if e.strip() else ""), sep="")
ssh.close()

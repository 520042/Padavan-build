#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""在 VPS 上部署 CNS (httpUDP / tunnel 服务端, 配 CLNC)。
- 上传 cns_linux_amd64 -> /opt/cns/cns
- 写 /opt/cns/cns.json (listen 443, encrypt_password <CNS_PWD>, proxy_key Meng)
- systemd 常驻 + 启动校验
密码从环境变量 VPS_PASS 读取, 不落盘。
"""
import os, sys, time, paramiko

HOST = "<VPS_IP>"; PORT = 22; USER = "root"
PASS = os.environ.get("VPS_PASS", "")
LOCAL_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cns_linux_amd64")

CNS_JSON = """{
    "Tcp_timeout": 600,
    "Udp_timeout": 30,
    "listen_addr": [":443"],
    "proxy_key": "Meng",
    "udp_flag": "httpUDP",
    "encrypt_password": "<CNS_PWD>",
    "Enable_dns_tcpOverUdp": true,
    "Enable_httpDNS": true,
    "Enable_TFO": false,
    "pid_path": "/opt/cns/cns.pid"
}
"""

UNIT = """[Unit]
Description=CNS (CuteBi Network Server) - CLNC tunnel/httpUDP server
After=network.target

[Service]
Type=simple
ExecStart=/opt/cns/cns -json=/opt/cns/cns.json
WorkingDirectory=/opt/cns
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
"""


def main():
    if not PASS:
        raise SystemExit("缺少 VPS_PASS 环境变量")
    ssh = paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=20,
                look_for_keys=False, allow_agent=False)

    def run(c, t=60):
        _, o, e = ssh.exec_command(c, timeout=t)
        out = o.read().decode(errors="replace"); err = e.read().decode(errors="replace")
        return out, err

    print("=== [0] 现状 ===")
    for c in ["uname -a", "systemctl is-active udp2raw 2>/dev/null; ss -lnptu | grep -E ':4096|:443' || echo '(443 未监听)'",
              "ls -la /opt/ 2>/dev/null | head"]:
        o, e = run(c); print(">>", c, "\n", o, (("ERR:"+e) if e.strip() else ""))

    print("\n=== [1] 建目录 + 上传 CNS ===")
    o, _ = run("mkdir -p /opt/cns && echo MKOK"); print(o)
    sftp = ssh.open_sftp()
    sftp.put(LOCAL_BIN, "/opt/cns/cns")
    sftp.close()
    o, _ = run("chmod +x /opt/cns/cns && ls -la /opt/cns/cns && /opt/cns/cns h 2>&1 | head -6")
    print(o)

    print("\n=== [2] 写 cns.json ===")
    sftp = ssh.open_sftp()
    with sftp.open("/opt/cns/cns.json", "w") as f:
        f.write(CNS_JSON)
    sftp.close()
    o, _ = run("cat /opt/cns/cns.json"); print(o)

    print("\n=== [3] systemd 单元 ===")
    sftp = ssh.open_sftp()
    with sftp.open("/etc/systemd/system/cns.service", "w") as f:
        f.write(UNIT)
    sftp.close()
    o, e = run("systemctl daemon-reload; systemctl enable cns 2>&1; systemctl restart cns; sleep 3; "
               "systemctl is-active cns; echo '--- status ---'; systemctl status cns --no-pager 2>&1 | tail -8")
    print(o)

    print("\n=== [4] 监听校验 ===")
    o, _ = run("ss -lnptu | grep -E ':443' || echo '(443 未监听!)'; echo '--- ps ---'; ps w | grep '[c]ns ' || echo '(无 cns 进程)'")
    print(o)

    print("\n=== [5] 本机自测 (TCP 443 可连?) ===")
    o, _ = run("timeout 4 sh -c 'echo > /dev/tcp/127.0.0.1/443' && echo 'LOCAL443_OPEN' || echo 'LOCAL443_FAIL'")
    print(o)

    ssh.close()
    print("\nCNS_DEPLOY_DONE")


if __name__ == "__main__":
    main()

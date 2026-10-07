import os, paramiko
HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
def run(c):
    stdin,stdout,stderr=ssh.exec_command(c,timeout=60)
    return stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")

# generate a key, persist for client reuse
o,e=run("openssl rand -hex 8")
KEY=o.strip()
print("KEY =", KEY)
run(f"echo '{KEY}' > /opt/udp2raw/key.txt; chmod 600 /opt/udp2raw/key.txt")

PORT="4096"
REAL="8.8.8.8:53"   # test target: public DNS, proves tunnel end-to-end

unit=f'''[Unit]
Description=udp2raw server (WAP UDP tunnel relay)
After=network.target

[Service]
Environment=UDP2RAW_PORT={PORT}
Environment=UDP2RAW_REALUDP={REAL}
Environment=UDP2RAW_KEY={KEY}
ExecStartPre=/sbin/iptables -I INPUT -p tcp --dport {PORT} -j DROP
ExecStart=/opt/udp2raw/bin/udp2raw_amd64 -s -l 0.0.0.0:{PORT} -r {REAL} -k {KEY} --raw-mode faketcp --disable-color -log /var/log/udp2raw.log
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
'''
run("cat > /etc/systemd/system/udp2raw.service <<'EOF'\n"+unit+"EOF\necho unit-written")
run("cat > /opt/udp2raw/run_server.sh <<'EOF'\n#!/bin/sh\nPORT=${UDP2RAW_PORT:-4096}\nREAL_UDP=${UDP2RAW_REALUDP:-8.8.8.8:53}\nKEY=$(cat /opt/udp2raw/key.txt)\niptables -I INPUT -p tcp --dport \"$PORT\" -j DROP 2>/dev/null\nexec /opt/udp2raw/bin/udp2raw_amd64 -s -l 0.0.0.0:\"$PORT\" -r \"$REAL_UDP\" -k \"$KEY\" --raw-mode faketcp --disable-color -log /var/log/udp2raw.log\nEOF\nchmod +x /opt/udp2raw/run_server.sh")

o,e=run("systemctl daemon-reload && systemctl enable --now udp2raw && sleep 2 && systemctl status udp2raw --no-pager | head -15")
print("=== systemctl status ===\n",o,e)
o,e=run("ps w | grep -v grep | grep udp2raw; echo '--- log ---'; tail -n 15 /var/log/udp2raw.log 2>/dev/null")
print("=== proc/log ===\n",o,e)
o,e=run("iptables -L INPUT -n -v | grep -E '4096|DROP' | head")
print("=== iptables DROP rule ===\n",o,e)
ssh.close()

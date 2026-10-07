import os, paramiko, time
HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)

def run(c, out=True):
    stdin,stdout,stderr=ssh.exec_command(c,timeout=60)
    o=stdout.read().decode(errors="replace"); e=stderr.read().decode(errors="replace")
    if out: print(">>",c,"\n",o, ("ERR:"+e if e.strip() else ""))
    return o,e

REL="v20230206.0"
urls=[
 f"https://github.com/wangyu-/udp2raw/releases/download/{REL}/udp2raw_binaries.tar.gz",
 f"https://ghproxy.com/https://github.com/wangyu-/udp2raw/releases/download/{REL}/udp2raw_binaries.tar.gz",
 f"https://ghfast.top/https://github.com/wangyu-/udp2raw/releases/download/{REL}/udp2raw_binaries.tar.gz",
 f"https://mirror.ghproxy.com/https://github.com/wangyu-/udp2raw/releases/download/{REL}/udp2raw_binaries.tar.gz",
]
run("mkdir -p /opt/udp2raw /opt/udp2raw/bin && cd /opt/udp2raw")
ok=False
for u in urls:
    print("TRY",u)
    o,e=run(f"cd /opt/udp2raw && curl -sL --max-time 60 -o udp2raw_binaries.tar.gz '{u}' && ls -l udp2raw_binaries.tar.gz && tar xzf udp2raw_binaries.tar.gz && echo EXTRACTED", out=False)
    print(o,e)
    # verify a binary extracted
    o2,_=run("cd /opt/udp2raw && ls bin 2>/dev/null; ls udp2raw_* 2>/dev/null | head; file udp2raw_amd64 2>/dev/null", out=False)
    if "udp2raw_amd64" in o2 or "amd64" in o2:
        ok=True; print("DOWNLOAD OK via",u); break
print("download ok=",ok)

# place binaries, chmod
run("cd /opt/udp2raw && ls -1 udp2raw_* 2>/dev/null; for f in udp2raw_*; do [ -f \"$f\" ] && cp -f \"$f\" bin/ 2>/dev/null; done; chmod +x bin/udp2raw_* 2>/dev/null; ls -l bin/")
run("cd /opt/udp2raw && ./bin/udp2raw_amd64 --version 2>&1 | head -3")

# write a run script (server). port placeholder 4096, will adjust after SG opens
run(r'''cat > /opt/udp2raw/run_server.sh <<'EOF'
#!/bin/sh
# udp2raw server: listen TCP PORT, forward decapsulated UDP to -r
PORT="${UDP2RAW_PORT:-4096}"
REAL_UDP="${UDP2RAW_REALUDP:-8.8.8.8:53}"
KEY="${UDP2RAW_KEY:-changeme-secret}"
# prevent kernel from RST/SYN-ACK on the raw port (coexists with sshd only if PORT!=22)
iptables -I INPUT -p tcp --dport "$PORT" -j DROP 2>/dev/null
exec /opt/udp2raw/bin/udp2raw_amd64 -s -l 0.0.0.0:"$PORT" -r "$REAL_UDP" -k "$KEY" --raw-mode faketcp --disable-color -log /var/log/udp2raw.log
EOF
chmod +x /opt/udp2raw/run_server.sh''')

# systemd unit (disabled until port ready / key set)
run(r'''cat > /etc/systemd/system/udp2raw.service <<'EOF'
[Unit]
Description=udp2raw server (WAP UDP tunnel relay)
After=network.target

[Service]
Environment=UDP2RAW_PORT=4096
Environment=UDP2RAW_REALUDP=8.8.8.8:53
Environment=UDP2RAW_KEY=changeme-secret
ExecStartPre=/sbin/iptables -I INPUT -p tcp --dport 4096 -j DROP
ExecStart=/opt/udp2raw/bin/udp2raw_amd64 -s -l 0.0.0.0:4096 -r 8.8.8.8:53 -k changeme-secret --raw-mode faketcp --disable-color -log /var/log/udp2raw.log
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
echo unit-written''')

# record auth.log baseline line count for CPE-egress test
o,_=run("wc -l /var/log/auth.log 2>/dev/null || echo 0")
print("auth.log baseline lines:", o.strip())
ssh.close()

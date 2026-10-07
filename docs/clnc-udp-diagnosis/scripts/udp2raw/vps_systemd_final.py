import os, paramiko, time
HOST="<VPS_IP>"; USER="root"; PASS=os.environ["VPS_PASS"]
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=22,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
def run(c, t=60):
    i,o,e=ssh.exec_command(c,timeout=t); return o.read().decode(errors="replace"), e.read().decode(errors="replace")

PORT="4096"; REAL="8.8.8.8:53"

wrapper = r'''#!/bin/sh
# udp2raw server wrapper: idempotent DROP rule + auto-restart loop
PORT=__PORT__
REAL=__REAL__
KEY=$(cat /opt/udp2raw/key.txt 2>/dev/null)
BIN=/opt/udp2raw/bin/udp2raw_amd64
LOG=/var/log/udp2raw.log
# idempotent DROP so the kernel doesn't RST the faketcp handshakes
iptables -C INPUT -p tcp --dport "$PORT" -j DROP 2>/dev/null || iptables -I INPUT -p tcp --dport "$PORT" -j DROP
touch "$LOG"
echo "$(date) wrapper start port=$PORT real=$REAL" >> "$LOG"
while true; do
  "$BIN" -s -l 0.0.0.0:"$PORT" -r "$REAL" -k "$KEY" --raw-mode faketcp --disable-color -log "$LOG"
  echo "$(date) udp2raw exited code=$? restart in 3s" >> "$LOG"
  sleep 3
done
'''.replace("__PORT__",PORT).replace("__REAL__",REAL)

unit = '''[Unit]
Description=udp2raw server (WAP UDP tunnel relay)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/udp2raw/run_server.sh
Restart=always
RestartSec=5
KillMode=control-group

[Install]
WantedBy=multi-user.target
'''

# flush any pre-existing duplicate 4096 DROP rules (leave exactly what wrapper will add)
run("while iptables -C INPUT -p tcp --dport 4096 -j DROP 2>/dev/null; do iptables -D INPUT -p tcp --dport 4096 -j DROP; done; echo flushed")
# write wrapper
o,e=run("cat > /opt/udp2raw/run_server.sh <<'WEOf'\n"+wrapper+"WEOf\necho wrapper-written")
print("wrapper:",o,e)
run("chmod +x /opt/udp2raw/run_server.sh")
# write unit
o,e=run("cat > /etc/systemd/system/udp2raw.service <<'UEOF'\n"+unit+"UEOF\necho unit-written")
print("unit:",o,e)
run("systemctl daemon-reload")
o,e=run("systemctl stop udp2raw 2>/dev/null; systemctl disable udp2raw 2>/dev/null; systemctl enable --now udp2raw")
print("enable:",o,e)
# poll up to ~20s
active=False
for i in range(10):
    o,e=run("systemctl is-active udp2raw"); act=o.strip()
    p,pe=run("ps w -C udp2raw_amd64 -o pid,cmd 2>/dev/null | grep udp2raw_amd64")
    if act=="active" and p.strip():
        print("ACTIVE after", i+1, "poll(s)"); active=True; break
    time.sleep(2)
if not active:
    print("NOT active yet, final state below")
o,e=run("ps w | grep -v grep | grep udp2raw_amd64"); print("=== proc ===\n",o)
o,e=run("tail -n 12 /var/log/udp2raw.log"); print("=== log ===\n",o)
o,e=run("iptables -L INPUT -n -v | grep -c 4096"); print("=== DROP rule count ===", o.strip())
o,e=run("systemctl is-active udp2raw"); print("=== final is-active ===", o.strip())
ssh.close()

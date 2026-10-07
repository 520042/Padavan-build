import os, paramiko
HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
def run(c):
    stdin,stdout,stderr=ssh.exec_command(c,timeout=30)
    return stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")

# 1) kill leftover listener on 4096
o,e=run("fuser -k 4096/tcp 2>/dev/null; pkill -f 'http.server 4096' 2>/dev/null; sleep 1; ss -tlnp | grep 4096 || echo '4096-free'")
print("after kill 4096:",o,e)
# 2) remove duplicate DROP rules for 4096, keep one clean
run("while iptables -C INPUT -p tcp --dport 4096 -j DROP 2>/dev/null; do iptables -D INPUT -p tcp --dport 4096 -j DROP; done; iptables -I INPUT -p tcp --dport 4096 -j DROP; echo rules-reset")
# 3) foreground run to confirm bind ok
KEY=run("cat /opt/udp2raw/key.txt")[0].strip()
cmd=f"timeout 5 /opt/udp2raw/bin/udp2raw_amd64 -s -l 0.0.0.0:4096 -r 8.8.8.8:53 -k {KEY} --raw-mode faketcp --disable-color; echo EXIT=$?"
o,e=run(cmd)
print("=== foreground run ===\n",o,e)
# 4) if ok, enable systemd
if "FATAL" not in o:
    o2,e2=run("systemctl daemon-reload && systemctl enable --now udp2raw && sleep 2 && systemctl is-active udp2raw")
    print("=== systemd enable ===\n",o2,e2)
    o3,e3=run("ps w | grep -v grep | grep udp2raw_amd64 | head")
    print("=== proc ===\n",o3,e3)
else:
    print("STILL FAILING - need manual diagnosis")
ssh.close()

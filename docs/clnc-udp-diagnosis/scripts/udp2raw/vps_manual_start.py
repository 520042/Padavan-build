import os, paramiko
HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
def run(c):
    stdin,stdout,stderr=ssh.exec_command(c,timeout=30)
    return stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")

run("systemctl stop udp2raw 2>/dev/null; systemctl disable udp2raw 2>/dev/null; echo stopped")
# flush ALL 4096 DROP rules, then add exactly one
run("while iptables -C INPUT -p tcp --dport 4096 -j DROP 2>/dev/null; do iptables -D INPUT -p tcp --dport 4096 -j DROP; done; echo flushed")
o,e=run("iptables -L INPUT -n -v | grep -c 4096")
print("remaining 4096 rules:",o.strip())
KEY=run("cat /opt/udp2raw/key.txt")[0].strip()
# start manually, detached, with one clean DROP rule
cmd=(f"iptables -I INPUT -p tcp --dport 4096 -j DROP; "
     f"setsid nohup /opt/udp2raw/bin/udp2raw_amd64 -s -l 0.0.0.0:4096 -r 8.8.8.8:53 -k {KEY} "
     f"--raw-mode faketcp --disable-color -log /var/log/udp2raw.log >/dev/null 2>&1 & "
     f"sleep 3; echo started")
o,e=run(cmd)
print("start:",o,e)
o,e=run("ps w | grep -v grep | grep udp2raw_amd64; echo '--- log ---'; tail -n 6 /var/log/udp2raw.log")
print("=== proc/log ===\n",o,e)
ssh.close()

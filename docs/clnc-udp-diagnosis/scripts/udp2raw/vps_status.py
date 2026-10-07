import os, paramiko
HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
def run(c):
    stdin,stdout,stderr=ssh.exec_command(c,timeout=30)
    return stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")
for c in [
  "systemctl is-active udp2raw",
  "ps w | grep -v grep | grep udp2raw_amd64",
  "tail -n 8 /var/log/udp2raw.log 2>/dev/null",
  "iptables -L INPUT -n -v | grep 4096",
]:
    o,e=run(c)
    print(">>",c,"\n",o,("ERR:"+e if e.strip() else ""))
ssh.close()

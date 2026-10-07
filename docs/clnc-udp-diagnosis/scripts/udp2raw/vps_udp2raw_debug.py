import os, paramiko
HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
def run(c):
    stdin,stdout,stderr=ssh.exec_command(c,timeout=30)
    return stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")

run("systemctl stop udp2raw 2>/dev/null; systemctl disable udp2raw 2>/dev/null; echo stopped")
KEY=run("cat /opt/udp2raw/key.txt")[0].strip()
print("KEY=",KEY)
# run foreground with timeout to capture the exception
cmd=f"timeout 5 /opt/udp2raw/bin/udp2raw_amd64 -s -l 0.0.0.0:4096 -r 8.8.8.8:53 -k {KEY} --raw-mode faketcp --disable-color; echo EXIT=$?"
o,e=run(cmd)
print("=== STDOUT ===\n",o)
print("=== STDERR ===\n",e)
ssh.close()

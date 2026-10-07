import os, paramiko, time

HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
# start a detached listener on 4096 to test security-group reachability
cmd="setsid nohup python3 -m http.server 4096 --bind 0.0.0.0 >/tmp/l4096.log 2>&1 < /dev/null & sleep 1; ss -tlnp | grep 4096 || echo 'listener-not-up'"
stdin,stdout,stderr=ssh.exec_command(cmd,timeout=20)
print(stdout.read().decode(errors="replace"))
print("ERR:",stderr.read().decode(errors="replace"))
ssh.close()
print("listener started, sleeping 3s for PC probe")
time.sleep(3)

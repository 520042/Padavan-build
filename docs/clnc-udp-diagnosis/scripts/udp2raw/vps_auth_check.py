import os, paramiko
HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
stdin,stdout,stderr=ssh.exec_command("tail -n 30 /var/log/auth.log; echo '=== Connection lines ==='; grep -c 'Connection from' /var/log/auth.log",timeout=30)
print(stdout.read().decode(errors="replace"))
print("ERR:",stderr.read().decode(errors="replace"))
ssh.close()

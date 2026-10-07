import os, paramiko
HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
for c in [
  "curl -sL --max-time 30 https://api.github.com/repos/wangyu-/udp2raw/releases/latest | head -c 1500",
  "echo '=== try tags ==='; curl -sL --max-time 30 'https://api.github.com/repos/wangyu-/udp2raw/releases?per_page=5' | grep -oE '\"tag_name\":\"[^\"]+\"'",
]:
    stdin,stdout,stderr=ssh.exec_command(c,timeout=40)
    print(">>",c); print(stdout.read().decode(errors="replace")); print("ERR:",stderr.read().decode(errors="replace"))
ssh.close()

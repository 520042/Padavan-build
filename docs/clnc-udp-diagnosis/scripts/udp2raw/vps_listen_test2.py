import os, paramiko
HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
for c in ["which python3 python nc ncat", "python3 --version 2>&1",
          "ss -tlnp 2>/dev/null | grep -E '4096|9901' || echo none-listening"]:
    stdin,stdout,stderr=ssh.exec_command(c,timeout=20)
    print(">>",c); print(stdout.read().decode(errors="replace").strip()); print("ERR:",stderr.read().decode(errors="replace").strip())
ssh.close()

import socket, struct, random, time, sys

def query(name, server, port, qtype=1, timeout=8):
    tid = random.randint(0, 65535)
    hdr = struct.pack('>HHHHHH', tid, 0x0100, 1, 0, 0, 0)
    q = b''.join(bytes([len(p)]) + p.encode() for p in name.split('.')) + b'\x00'
    pkt = hdr + q + struct.pack('>HH', qtype, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(timeout)
    t0 = time.time()
    s.sendto(pkt, (server, port))
    try:
        d, _ = s.recvfrom(4096)
    except socket.timeout:
        print("[%s:%d] TIMEOUT (%ds)" % (server, port, timeout)); return False
    dt = (time.time() - t0) * 1000
    an = struct.unpack('>H', d[6:8])[0]
    print("[%s:%d] reply len=%d ANCOUNT=%d rtt=%.0fms" % (server, port, len(d), an, dt))
    idx = 12
    qd = struct.unpack('>H', d[4:6])[0]
    for _ in range(qd):
        while d[idx] != 0: idx += d[idx] + 1
        idx += 1 + 4
    for _ in range(an):
        if d[idx] & 0xc0 == 0xc0: idx += 2
        else:
            while d[idx] != 0: idx += d[idx] + 1
            idx += 1
        t = struct.unpack('>H', d[idx:idx+2])[0]; idx += 8
        rdlen = struct.unpack('>H', d[idx:idx+2])[0]; idx += 2
        if t == 1 and rdlen == 4:
            print("   A =", ".".join(str(b) for b in d[idx:idx+4]))
        idx += rdlen
    return an > 0

if __name__ == "__main__":
    print("=== udp2raw C 方案端到端 (LAN -> R3G:4455 -> VPS:4096 -> 8.8.8.8:53) ===")
    query("google.com", "192.168.2.1", 4455)
    query("baidu.com", "192.168.2.1", 4455)
    query("github.com", "192.168.2.1", 4455)

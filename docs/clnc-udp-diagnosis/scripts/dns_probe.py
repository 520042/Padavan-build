"""Send a raw DNS A-query to a server:port and print the answer (or timeout)."""
import socket, sys, struct

def build_query(name, qid=0x1234):
    # header
    flags = 0x0100  # RD=1
    pkt = struct.pack(">HHHHHH", qid, flags, 1, 0, 0, 0)
    for label in name.split("."):
        pkt += bytes([len(label)]) + label.encode()
    pkt += b"\x00"
    pkt += struct.pack(">HH", 1, 1)  # QTYPE=A, QCLASS=IN
    return pkt

def parse_resp(data):
    # minimal: parse answers
    if len(data) < 12:
        return "(too short)"
    ancount = struct.unpack(">H", data[6:8])[0]
    # skip header + question
    i = 12
    # skip question name (handle compression pointer at 0xC0)
    while i < len(data):
        b = data[i]
        if b == 0:
            i += 1; break
        if (b & 0xC0) == 0xC0:
            i += 2; break
        i += b + 1
    i += 4  # QTYPE + QCLASS
    answers = []
    for _ in range(ancount):
        # name may be pointer
        if (data[i] & 0xC0) == 0xC0:
            i += 2
        else:
            while data[i] != 0:
                i += data[i] + 1
            i += 1
        rtype, rclass, ttl, rdlen = struct.unpack(">HHIH", data[i:i+10])
        i += 10
        rdata = data[i:i+rdlen]; i += rdlen
        if rtype == 1:  # A
            answers.append(".".join(str(x) for x in rdata))
        elif rtype == 5 or rtype == 28:
            answers.append("(non-A)")
        else:
            answers.append(f"(type {rtype})")
    return f"ancount={ancount} answers={answers}"

def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.2.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 6653
    name = sys.argv[3] if len(sys.argv) > 3 else "www.baidu.com"
    q = build_query(name)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(8)
    try:
        s.sendto(q, (host, port))
        data, _ = s.recvfrom(4096)
        print(f"[OK] {host}:{port} -> {name}: {parse_resp(data)}")
    except socket.timeout:
        print(f"[TIMEOUT] {host}:{port} no reply within 8s (clnc DNS not answering)")
    except Exception as e:
        print(f"[ERR] {host}:{port}: {e}")
    finally:
        s.close()

if __name__ == "__main__":
    main()

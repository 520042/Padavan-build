#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度取证：字节熵(判断加壳) + 程序头/动态依赖(NEEDED) + 全量字符串 dump。"""
import struct, sys, os, math, collections

def entropy(data):
    if not data:
        return 0.0
    c = collections.Counter(data)
    n = len(data)
    h = 0.0
    for v in c.values():
        p = v / n
        h -= p * math.log2(p)
    return h

def parse_pie(path):
    with open(path, "rb") as f:
        data = f.read()
    out = {"size": len(data), "ph": [], "needed": [], "interp": None,
           "pie": None, "entropy": entropy(data)}
    if data[:4] != b"\x7fELF":
        out["err"] = "not ELF"; return out
    is64 = data[4] == 2
    le = data[5] == 1 and "<" or ">"
    fmt = "<" if le else ">"
    if is64:
        e_phoff = struct.unpack_from(fmt+"Q", data, 32)[0]
        e_phentsize = struct.unpack_from(fmt+"H", data, 54)[0]
        e_phnum = struct.unpack_from(fmt+"H", data, 56)[0]
        e_flags = struct.unpack_from(fmt+"I", data, 48)[0]
    else:
        e_phoff = struct.unpack_from(fmt+"I", data, 28)[0]
        e_phentsize = struct.unpack_from(fmt+"H", data, 42)[0]
        e_phnum = struct.unpack_from(fmt+"H", data, 44)[0]
        e_flags = struct.unpack_from(fmt+"I", data, 36)[0]
    out["e_flags"] = "0x%x" % e_flags
    # PIE detection: e_type==3 (ET_DYN) AND EF_ARM_PIC? for ARM; for ELF generally ET_DYN=>PIE
    e_type = struct.unpack_from(fmt+"H", data, 16)[0]
    out["e_type"] = e_type
    out["pie"] = (e_type == 3)
    PT_DYNAMIC = 2; PT_INTERP = 3; PT_LOAD = 1
    dyn_off = None; dyn_size = None; interp_off=None
    for i in range(e_phnum):
        off = e_phoff + i*e_phentsize
        if is64:
            p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = \
                struct.unpack_from(fmt+"IIQQQQQQ", data, off)
        else:
            p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align = \
                struct.unpack_from(fmt+"IIIIIIII", data, off)
        out["ph"].append((p_type, p_offset, p_filesz))
        if p_type == PT_INTERP:
            interp_off = p_offset
        if p_type == PT_DYNAMIC:
            dyn_off, dyn_size = p_offset, p_filesz
    if interp_off is not None:
        end = data.find(b"\x00", interp_off)
        out["interp"] = data[interp_off:end].decode("latin1", "replace")
    # parse dynamic
    if dyn_off is not None:
        dt = []
        esz = 16 if is64 else 8
        nent = dyn_size // esz
        for k in range(nent):
            base = dyn_off + k*esz
            if is64:
                d_tag, d_val = struct.unpack_from(fmt+"qQ", data, base)
            else:
                d_tag, d_val = struct.unpack_from(fmt+"iI", data, base)
            dt.append((d_tag, d_val))
        # DT_NEEDED=1, DT_STRTAB=5, DT_STRSZ=10
        strtab = None; strsz = 0
        for tag, val in dt:
            if tag == 5: strtab = val
            if tag == 10: strsz = val
        if strtab is not None and strsz:
            strdata = data[strtab:strtab+strsz] if strtab < len(data) else b""
            for tag, val in dt:
                if tag == 1:
                    s = strdata[val:strdata.find(b"\x00", val)]
                    out["needed"].append(s.decode("latin1", "replace"))
    return out

def dump_strings(path, minlen=6, maxout=80):
    with open(path, "rb") as f:
        data = f.read()
    out=[]; buf=bytearray()
    for b in data:
        if 32 <= b < 127 or b in (9,10,13):
            buf.append(b)
        else:
            if len(buf) >= minlen:
                out.append(bytes(buf).decode("latin1"))
            buf=bytearray()
    if len(buf)>=minlen: out.append(bytes(buf).decode("latin1"))
    # dedup keep order
    seen=set(); uniq=[]
    for s in out:
        if s not in seen:
            seen.add(s); uniq.append(s)
    return uniq

def main():
    for path in sys.argv[1:]:
        if not os.path.exists(path):
            print("MISSING", path); continue
        print("="*72)
        print("FILE:", path, "size=%d"%os.path.getsize(path))
        p = parse_pie(path)
        print("  entropy=%.3f (max 8.0; >7.0 => packed/encrypted likely)"%p["entropy"])
        print("  e_type=%d PIE=%s interp=%s e_flags=%s"%(p.get("e_type"),p.get("pie"),p.get("interp"),p.get("e_flags")))
        print("  dynamic NEEDED libs:", p.get("needed"))
        print("  program headers (type,offset,filesz):", p.get("ph")[:12])
        alls = dump_strings(path, 6)
        print("  total unique strings(>=6):", len(alls))
        # show candidates relevant to proxy/protocol/version
        pats = ["cutebi","caml","ocaml","clnc","cns","socks","associate","httpudp",
                "udp","tiny","dns","version","1.","2.","0.","error","panic","rust",
                "go1.","goroot","runtime","gmp","openssl","ssl","tls","token","key",
                "proxy","socks5","welcome"]
        shown=0
        for s in alls:
            sl=s.lower()
            if any(t in sl for t in pats) and shown < 200:
                print("    S|", s[:160]); shown+=1
        print()

if __name__=="__main__":
    main()

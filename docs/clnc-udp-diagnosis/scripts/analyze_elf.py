#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ELF 深度取证：节头 / 动态符号表 / 字符串扫描，判断是否为 OCaml native、版本、UDP/SOCKS5 能力。"""
import struct, sys, re, os

MACHINE = {0x28: "ARM", 0x3e: "X86-64", 0xb7: "AARCH64", 0x8: "MIPS",
           0x14: "PowerPC", 0x28: "ARM", 0x28: "ARM", 0x183: "AARCH64",
           0x3: "x86", 0x08: "MIPS", 0x09: "MIPS(LE?)", 0x40000000+0x8: "MIPS"}
ET = {0: "NONE", 1: "REL", 2: "EXEC", 3: "DYN", 4: "CORE"}

def machine_name(m):
    return {0x28: "ARM(32)", 0x3e: "X86-64", 0xb7: "AARCH64", 0x8: "MIPS",
            0x40000000|0x8: "MIPS", 0x3: "x86(32)", 0x14: "PowerPC",
            0x183: "AARCH64", 0x28: "ARM(32)"}.get(m, "0x%x" % m)

def parse_elf(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"\x7fELF":
        return {"error": "not ELF", "magic": data[:8]}
    ei_class = data[4]      # 1=32bit 2=64bit
    ei_data = data[5]       # 1=LE 2=BE
    is64 = ei_class == 2
    e_type = struct.unpack_from("<H", data, 16)[0]
    e_machine = struct.unpack_from("<H", data, 18)[0]
    if is64:
        e_shoff = struct.unpack_from("<Q", data, 40)[0]
        e_shentsize = struct.unpack_from("<H", data, 58)[0]
        e_shnum = struct.unpack_from("<H", data, 60)[0]
        e_shstrndx = struct.unpack_from("<H", data, 62)[0]
    else:
        e_shoff = struct.unpack_from("<I", data, 32)[0]
        e_shentsize = struct.unpack_from("<H", data, 46)[0]
        e_shnum = struct.unpack_from("<H", data, 48)[0]
        e_shstrndx = struct.unpack_from("<H", data, 50)[0]
    info = {"path": path, "size": len(data), "is64": is64, "le": ei_data == 1,
            "e_type": ET.get(e_type, e_type), "machine": machine_name(e_machine),
            "machine_raw": "0x%x" % e_machine, "sections": [],
            "has_sections": bool(e_shoff and e_shnum)}
    # parse section headers
    shdrs = []
    if not info["has_sections"]:
        info["note"] = "no section headers (likely stripped PIE/EXEC)"
        info["caml_syms"] = []
        return info
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        if is64:
            (sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size,
             sh_link, sh_info, sh_addralign, sh_entsize) = struct.unpack_from(
                "<IIQQQQIIQQ", data, off)
        else:
            (sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size,
             sh_link, sh_info, sh_addralign, sh_entsize) = struct.unpack_from(
                "<IIIIIIIIII", data, off)
        shdrs.append(dict(name=sh_name, type=sh_type, off=sh_offset, size=sh_size,
                           link=sh_link, entsize=sh_entsize, addr=sh_addr))
    # shstrtab
    if e_shstrndx >= len(shdrs):
        info["note"] = "e_shstrndx out of range, no section names"
        info["caml_syms"] = []
        return info
    shstr = shdrs[e_shstrndx]
    shstr_data = data[shstr["off"]:shstr["off"] + shstr["size"]]
    def getstr(tab, idx):
        end = tab.find(b"\x00", idx)
        return tab[idx:end].decode("latin1", "replace")
    for s in shdrs:
        s["name_s"] = getstr(shstr_data, s["name"])
        info["sections"].append(s)
    # symbols
    info["caml_syms"] = []
    for s in shdrs:
        if s["name_s"] in (".dynsym", ".symtab") and s["entsize"]:
            link = s["link"]
            strtab = shdrs[link] if link < len(shdrs) else None
            if strtab is None:
                continue
            strdata = data[strtab["off"]:strtab["off"] + strtab["size"]]
            nsym = s["size"] // s["entsize"]
            for k in range(nsym):
                base = s["off"] + k * s["entsize"]
                if is64:
                    st_name, st_info, st_other, st_shndx, st_value, st_size = \
                        struct.unpack_from("<IBBHQQ", data, base)
                else:
                    st_name, st_value, st_size, st_info, st_other, st_shndx = \
                        struct.unpack_from("<IIIBBH", data, base)
                nm = getstr(strdata, st_name)
                if "caml" in nm.lower():
                    info["caml_syms"].append(nm)
    return info

def extract_strings(data, minlen=6):
    # printable runs
    out = []
    buf = bytearray()
    for b in data:
        if 32 <= b < 127 or b in (9, 10, 13):
            buf.append(b)
        else:
            if len(buf) >= minlen:
                out.append(bytes(buf).decode("latin1"))
            buf = bytearray()
    if len(buf) >= minlen:
        out.append(bytes(buf).decode("latin1"))
    return out

KEYWORDS = ["caml", "CuteBi", "ocaml", "OCaml", "OCAML", "SOCKS", "socks5",
            "ASSOCIATE", "associate", "udp", "UDP", "httpUDP", "HttpUDP",
            "1.2", "1.3", "v1.", "version", "Version", "tiny", "Tiny",
            "clnc", "CLNC", "CNS", "Cns", "dns", "DNS", "welcome to"]

def scan(path):
    with open(path, "rb") as f:
        data = f.read()
    strs = extract_strings(data, 5)
    low = data.lower()
    hits = {}
    for kw in KEYWORDS:
        kwl = kw.lower()
        # count occurrences in lowercase data
        c = low.count(kwl.encode("latin1"))
        if c:
            hits[kw] = c
    # collect interesting strings (version / udp / socks / associate / caml)
    interesting = []
    for s in strs:
        sl = s.lower()
        if any(t in sl for t in ["cutebi", "caml", "ocaml", "socks", "associate",
                                  "httpudp", "welcome to", "version", "tiny 0.",
                                  "clnc", "cns", "udp", "1.2", "1.3", "1.4", "1.5",
                                  ".25beta", "beta"]):
            if len(s) <= 200:
                interesting.append(s)
    return hits, sorted(set(interesting))[:120], strs

def main():
    for path in sys.argv[1:]:
        if not os.path.exists(path):
            print("MISSING:", path); continue
        print("="*72)
        print("FILE:", path, "size=%d" % os.path.getsize(path))
        ei = parse_elf(path)
        if "error" in ei:
            print("  ", ei); continue
        print("  ELF %d-bit %s  type=%s  machine=%s(%s)" % (
            (64 if ei["is64"] else 32), ("LE" if ei["le"] else "BE"),
            ei["e_type"], ei["machine"], ei["machine_raw"]))
        sec_names = [s["name_s"] for s in ei["sections"]]
        print("  sections(%d): %s" % (len(sec_names), ", ".join(sec_names)))
        print("  caml_ symbols found: %d" % len(ei["caml_syms"]))
        if ei["caml_syms"]:
            print("    sample:", ", ".join(ei["caml_syms"][:25]))
        else:
            # fallback: scan raw bytes for OCaml runtime markers
            raw = open(path, "rb").read().lower()
            for marker in [b"caml", b"cutebi", b"ocaml", b"fatal error",
                           b"ocaml runtime", b"caml_call_gc"]:
                if marker in raw:
                    print("    raw-marker present: %s" % marker.decode())
        hits, interesting, _ = scan(path)
        print("  keyword hits:", hits)
        print("  --- interesting strings ---")
        for s in interesting:
            print("    |", s)
        print()

if __name__ == "__main__":
    main()

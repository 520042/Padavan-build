#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GitHub Release 资产管理工具 (R3G 固件项目)

用法:
  python gh_release.py list                       # 列出全部资产
  python gh_release.py put <file> [asset_name]    # 上传/替换资产(自动删旧 + 回读 MD5 校验)
  python gh_release.py rm <asset_name>            # 删除资产
  python gh_release.py get <asset_name> <out>     # 下载资产(清代理直连)

铁律(踩过的坑):
  * 必须清空 HTTP(S)_PROXY/ALL_PROXY(含小写), 否则 TSD 透明代理会注入
    %TSD-Header-###% 损坏二进制(文件变大 ~70KB, tar/zip 解不开)
  * 上传后必须回读校验(大小 + MD5 + 结构), 否则会带着损坏资产去构建
  * 下载签名 URL 必须用 curl(会自动丢弃跨域 Authorization 头), urllib 会 401
"""
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from ctypes import wintypes

OWNER = "520042"
REPO = "Padavan-build"
RELEASE_ID = 397917534  # v1.0.0

BASE = r"C:/Users/liang.zhao/WorkBuddy/2026-09-24-15-59-12/r3g-build"
TMP = os.environ.get("TEMP", "/tmp")

PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
              "http_proxy", "https_proxy", "all_proxy")


class CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
        ("TargetName", ctypes.c_wchar_p), ("Comment", ctypes.c_wchar_p),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.c_void_p),
        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p), ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


def token():
    """从 Windows 凭据库读取 GitHub token (utf-16-le 编码)。"""
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.CredReadW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    advapi32.CredReadW.restype = wintypes.BOOL
    ptr = ctypes.POINTER(CREDENTIAL)()
    if not advapi32.CredReadW("git:https://github.com", 1, 0, ctypes.byref(ptr)):
        raise SystemExit("无法从凭据库读取 GitHub token")
    cred = ptr.contents
    raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
    ctypes.windll.advapi32.CredFree(ptr)
    return raw.decode("utf-16-le").rstrip("\x00").strip()


def clean_env():
    """去掉代理变量的环境副本 (TSD 注入防护)。"""
    return {k: v for k, v in os.environ.items() if k.upper() not in
            tuple(x.upper() for x in PROXY_KEYS)}


def curl_cfg(pairs, path=None):
    path = path or os.path.join(TMP, "gh_cfg.txt")
    with open(path, "w", encoding="utf-8") as fh:
        for key, val in pairs:
            fh.write('%s = "%s"\n' % (key, val))
    return path


def api(url, method="GET", data=None, accept="application/vnd.github+json",
        cfg_path=None):
    tk = token()
    pairs = [("url", url),
             ("header", "Authorization: Bearer %s" % tk),
             ("header", "User-Agent: r3g-build"),
             ("header", "Accept: %s" % accept)]
    if method == "POST":
        pairs.append(("request", "POST"))
        pairs.append(("header", "Content-Type: application/json"))
    elif method == "DELETE":
        pairs.append(("request", "DELETE"))
    path = curl_cfg(pairs, cfg_path)
    cmd = ["curl", "-sSL", "--max-time", "300", "-K", path]
    if data is not None:
        cmd += ["--data-binary", data]
    res = subprocess.run(cmd, capture_output=True, text=True,
                         env=clean_env(), timeout=360)
    try:
        os.remove(path)
    except OSError:
        pass
    body = res.stdout
    try:
        return json.loads(body)
    except ValueError:
        return body


def list_assets():
    return api("https://api.github.com/repos/%s/%s/releases/%d/assets"
               % (OWNER, REPO, RELEASE_ID))


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rm_asset(name):
    for a in list_assets():
        if a.get("name") == name:
            api("https://api.github.com/repos/%s/%s/releases/assets/%d"
                % (OWNER, REPO, a["id"]), method="DELETE")
            print("  删除旧资产: %s (id=%d)" % (name, a["id"]))
            return True
    return False


def put_asset(path, name=None):
    name = name or os.path.basename(path)
    if not os.path.isabs(path):
        path = os.path.join(BASE, path)
    local_md5 = md5_of(path)
    local_size = os.path.getsize(path)
    print("[put] %s -> %s (%d bytes, md5 %s)"
          % (os.path.basename(path), name, local_size, local_md5))

    rm_asset(name)

    tk = token()
    cfg = curl_cfg([
        ("url", "https://uploads.github.com/repos/%s/%s/releases/%d/assets?name=%s"
         % (OWNER, REPO, RELEASE_ID, name)),
        ("header", "Authorization: Bearer %s" % tk),
        ("header", "Content-Type: application/octet-stream"),
    ])
    res = subprocess.run(
        ["curl", "-sS", "-X", "POST", "--max-time", "900", "-K", cfg,
         "--data-binary", "@%s" % path.replace("\\", "/")],
        capture_output=True, text=True, env=clean_env(), timeout=960)
    try:
        os.remove(cfg)
    except OSError:
        pass
    try:
        resp = json.loads(res.stdout)
    except ValueError:
        raise SystemExit("上传响应无法解析: %s | %s"
                         % (res.stdout[:300], res.stderr[:200]))
    if resp.get("state") != "uploaded":
        raise SystemExit("上传失败: %s" % str(resp)[:300])

    # 回读校验 (铁律): 下载到文件, 比对 大小 + MD5
    verify_path = os.path.join(TMP, "asset_verify.bin")
    if os.path.exists(verify_path):
        os.remove(verify_path)
    vcfg = curl_cfg([
        ("url", resp["url"]),
        ("header", "Authorization: Bearer %s" % tk),
        ("header", "User-Agent: r3g-build"),
        ("header", "Accept: application/octet-stream"),
    ], os.path.join(TMP, "gh_verify_cfg.txt"))
    subprocess.run(["curl", "-sSL", "--max-time", "600", "-K", vcfg,
                    "-o", verify_path, "-w", "%{http_code} %{size_download}"],
                   capture_output=True, text=True, env=clean_env(), timeout=660)
    try:
        os.remove(vcfg)
    except OSError:
        pass
    got_size = os.path.getsize(verify_path)
    got_md5 = md5_of(verify_path)
    if got_size != local_size or got_md5 != local_md5:
        raise SystemExit("回读校验失败: %d/%s != %d/%s"
                         % (got_size, got_md5, local_size, local_md5))
    print("  [OK] 回读校验通过: %d bytes, md5 %s" % (got_size, got_md5))
    return resp


def get_asset(name, out):
    for a in list_assets():
        if a.get("name") == name:
            cfg = curl_cfg([
                ("url", a["url"]),
                ("header", "Authorization: Bearer %s" % token()),
                ("header", "User-Agent: r3g-build"),
                ("header", "Accept: application/octet-stream"),
            ])
            if os.path.exists(out):
                os.remove(out)
            subprocess.run(["curl", "-sSL", "--max-time", "600", "-K", cfg,
                            "-o", out, "-w", "%{http_code} %{size_download}"],
                           capture_output=True, text=True, env=clean_env(),
                           timeout=660)
            try:
                os.remove(cfg)
            except OSError:
                pass
            print("downloaded %s -> %s (%d bytes, md5 %s)"
                  % (name, out, os.path.getsize(out), md5_of(out)))
            return
    raise SystemExit("找不到资产: %s" % name)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    if cmd == "list":
        for a in list_assets():
            print("%-40s %10d bytes  %s" % (a["name"], a["size"], a["state"]))
    elif cmd == "put":
        put_asset(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "rm":
        print("removed" if rm_asset(sys.argv[2]) else "not found")
    elif cmd == "get":
        get_asset(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()

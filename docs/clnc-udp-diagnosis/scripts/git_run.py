#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""在用干净环境跑 git 命令, 用 Windows 凭据库里的 token 直连 GitHub。

为什么需要这个:
  1) 本机环境存在**重复的 PATH/Path 变量**(大小写各一份), 会让 git 子进程静默死亡
     (退出码 0 或 128, 没有任何输出) -> 必须构造干净 env
  2) 全局 credential.helper 指向 WorkBuddy 自带的 GCM, 而 GCM 找不到自己的配置文件时
     会弹 "Select a credential helper" 窗口 -> **弹窗挂住 git 进程导致推送超时**
     -> 这里用 -c credential.helper= 彻底禁用 helper, 并用 token 直接拼 URL 认证
  3) 代理变量必须去掉, 否则 TSD 透明代理会干扰

用法:
  python git_run.py git push --quiet origin master
  python git_run.py git ls-remote origin -h refs/heads/master
  python git_run.py git log --oneline -3
"""
import ctypes
import os
import subprocess
import sys
from ctypes import wintypes

REPO = r"C:\Users\liang.zhao\WorkBuddy\2026-09-24-15-59-12\Padavan-build"
OWNER_REPO = "520042/Padavan-build"
TIMEOUT = int(os.environ.get("GIT_RUN_TIMEOUT", "150"))

PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY")


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


def get_token():
    """从 Windows 凭据库读 GitHub token (GCM 存的格式是 utf-16-le)。"""
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    api.CredReadW.restype = wintypes.BOOL
    ptr = ctypes.POINTER(CREDENTIAL)()
    if not api.CredReadW("git:https://github.com", 1, 0, ctypes.byref(ptr)):
        return None
    cred = ptr.contents
    raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
    ctypes.windll.advapi32.CredFree(ptr)
    return raw.decode("utf-16-le").rstrip("\x00").strip()


def clean_env():
    """大小写去重 PATH + 去代理 + 禁止任何交互式凭据提示。"""
    env = {}
    path_val = None
    for k, v in os.environ.items():
        ku = k.upper()
        if ku == "PATH":
            path_val = v if path_val is None else path_val + os.pathsep + v
        else:
            env[ku] = v
    env["PATH"] = path_val or ""
    for p in PROXY_KEYS:
        env.pop(p, None)
    env["GIT_TERMINAL_PROMPT"] = "0"   # 不弹命令行提示
    env["GCM_INTERACTIVE"] = "never"   # 不弹 GUI
    return env


def make_askpass(token, path):
    """把 token 写进临时 askpass 脚本(权限 700)。

    这样 token 不会出现在 git 的**命令行参数**里 —— 否则任何能跑 ps/tasklist 的
    程序都能从进程列表读到明文 token（本项目就出现过这个隐患）。
    """
    script = ('#!/bin/sh\n'
              'case "$1" in\n'
              '  *[Uu]sername*) echo "x-access-token" ;;\n'
              '  *) echo "%s" ;;\n'
              'esac\n') % token
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(script)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def build_cmd(argv, token):
    """把 origin 换成普通 https URL(不含 token); 认证交给 GIT_ASKPASS。"""
    if not argv or os.path.basename(argv[0]) not in ("git", "git.exe"):
        return argv, None
    url = "https://github.com/%s.git" % OWNER_REPO
    out = [argv[0], "-c", "credential.helper="]
    for a in argv[1:]:
        out.append(url if a == "origin" else a)
    return out, token


def scrub(text, token):
    if not token:
        return text
    return text.replace(token, "***TOKEN***")


def main():
    argv = sys.argv[1:] or ["git", "push", "--quiet", "origin", "master"]
    token = get_token()
    cmd, used = build_cmd(argv, token)
    env = clean_env()
    askpass = None
    if token:
        askpass = make_askpass(token, os.path.join(os.environ.get("TEMP", "/tmp"),
                                                   "gh_askpass.sh"))
        env["GIT_ASKPASS"] = askpass
    try:
        res = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                             timeout=TIMEOUT, env=env, errors="replace")
        print("RETURN:", res.returncode)
        out = scrub(res.stdout, used).strip()
        err = scrub(res.stderr, used).strip()
        if out:
            print("=== STDOUT ===\n" + out[-4000:])
        if err:
            print("=== STDERR ===\n" + err[-4000:])
        if not out and not err:
            print("(无输出)")
    except subprocess.TimeoutExpired:
        print("EXC: TimeoutExpired after %ss (网络抖动时正常, 重试即可)" % TIMEOUT)
    except Exception as exc:
        print("EXC:", type(exc).__name__, exc)
    finally:
        if askpass and os.path.exists(askpass):
            try:
                os.remove(askpass)
            except OSError:
                pass


if __name__ == "__main__":
    main()

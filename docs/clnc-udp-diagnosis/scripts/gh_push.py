#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用 GitHub Contents API 推送文件。

适用场景: github.com:443 被墙/超时(git push 必失败), 但 api.github.com 仍可达。
实测某网络环境下 api.github.com 返回 200 而 github.com 完全超时, 此时本脚本可替代 git push。

用法: python gh_push.py <.github/workflows/xxx.yml 之类的仓库相对路径> ["commit message"]
"""
import base64
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gh_release import api, curl_cfg, clean_env, token  # noqa: E402

OWNER = "520042"
REPO = "Padavan-build"
LOCAL = r"C:/Users/liang.zhao/WorkBuddy/2026-09-24-15-59-12/Padavan-build"


def push(path, message):
    full = os.path.join(LOCAL, path.replace("/", os.sep))
    if not os.path.isfile(full):
        raise SystemExit("本地文件不存在: %s" % full)
    data = open(full, "rb").read()
    url = "https://api.github.com/repos/%s/%s/contents/%s" % (OWNER, REPO, path)

    cur = api(url)
    sha = cur.get("sha") if isinstance(cur, dict) else None
    if not sha:
        print("警告: 取不到远端 sha(可能是新文件), 将以新建方式提交")

    body = {"message": message, "content": base64.b64encode(data).decode("ascii")}
    if sha:
        body["sha"] = sha

    cfg = curl_cfg([
        ("url", url),
        ("header", "Authorization: Bearer %s" % token()),
        ("header", "User-Agent: r3g-build"),
        ("header", "Accept: application/vnd.github+json"),
        ("header", "Content-Type: application/json"),
    ])
    # 大文件(base64 可达数 MB)必须走 -d @文件, 否则整段塞命令行会触发 Windows [WinError 206] 过长
    import tempfile
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
    tf.write(json.dumps(body)); tf.close()
    res = subprocess.run(
        ["curl", "-sS", "-m", "120", "-X", "PUT", "-K", cfg,
         "-d", "@" + tf.name, "-w", "\nHTTP:%{http_code}"],
        capture_output=True, text=True, env=clean_env(), timeout=180)
    try:
        os.remove(tf.name)
    except OSError:
        pass
    try:
        os.remove(cfg)
    except OSError:
        pass

    out = res.stdout
    code = out.rsplit("HTTP:", 1)[-1].strip() if "HTTP:" in out else "?"
    print("HTTP", code, "|", out[:220].replace("\n", " "))
    return code in ("200", "201")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    p = sys.argv[1]
    msg = sys.argv[2] if len(sys.argv) > 2 else "update %s" % p
    ok = push(p, msg)
    print("PUSH_OK" if ok else "PUSH_FAIL")
    sys.exit(0 if ok else 1)

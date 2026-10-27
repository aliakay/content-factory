#!/usr/bin/env python3
"""Studio users (factory/accounts.py). The first user turns the login on.

  users.py add <id> "<Name>" [owner|member]   -> prints a new random password
  users.py passwd <id>                         -> prints a new random password
  users.py list
"""
import os, secrets, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory import accounts  # noqa: E402

cmd = sys.argv[1:] or ["list"]
if cmd[0] == "add":
    uid, name = cmd[1].lower(), cmd[2]
    role = cmd[3] if len(cmd) > 3 else ("owner" if uid == accounts.OWNER else "member")
    pw = secrets.token_urlsafe(9)
    accounts.add_user(uid, name, pw, role)
    print(f"{uid} ({role}) şifre: {pw}")
elif cmd[0] == "passwd":
    rec = accounts.users()["users"][cmd[1]]
    pw = secrets.token_urlsafe(9)
    accounts.add_user(cmd[1], rec["name"], pw, rec["role"])
    print(f"{cmd[1]} yeni şifre: {pw}")
else:
    for k, v in accounts.users()["users"].items():
        print(k, v["name"], v["role"], "claude:", accounts.claude_status(k)["connected"])

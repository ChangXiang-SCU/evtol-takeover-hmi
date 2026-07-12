# -*- coding: utf-8 -*-
"""上传 controller/<file> 到 sim 并远程运行(本地跑 127.0.0.1:5000)。
用法: python -X utf8 _probe_remote.py <file> [remote args...]
例:   python -X utf8 _probe_remote.py _push_throttle.py 11.99 8"""
import os, sys, posixpath
from _ssh_deploy import connect, run, REMOTE_DIR, HERE

fname = sys.argv[1] if len(sys.argv) > 1 else "dump_fields.py"
args = " ".join(sys.argv[2:])

c = connect()
print("CONNECTED, 上传", fname, ("args=" + args) if args else "")
sftp = c.open_sftp()
try:
    sftp.mkdir(REMOTE_DIR)
except IOError:
    pass
sftp.put(os.path.join(HERE, fname), posixpath.join(REMOTE_DIR, fname))
sftp.close()

cmd = 'cd /d "%s" && python -X utf8 %s %s' % (REMOTE_DIR.replace("/", "\\"), fname, args)
rc, o, e = run(c, cmd, timeout=120)
print("rc=", rc)
print("--- STDOUT ---")
print(o)
if e:
    print("--- STDERR ---")
    print(e)
c.close()

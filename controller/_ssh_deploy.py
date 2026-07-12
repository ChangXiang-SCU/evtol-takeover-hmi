# -*- coding: utf-8 -*-
"""用 paramiko 从笔记本 SSH 到 sim（绕开坏掉的 ssh.exe）。
connect 测试 + 可选 SFTP 部署 controller + 远程跑命令。
用法:
  python _ssh_deploy.py test          # 只测连接+环境
  python _ssh_deploy.py deploy        # 上传 controller 文件到 sim 并 --check
  python _ssh_deploy.py run "<cmd>"   # 在 sim 上跑任意命令
"""
import os, sys, time, posixpath, paramiko

HOST, PORT, USER = "10.7.144.111", 22, "flightsimulator"
KEY = os.path.expanduser(r"~\.ssh\sim_evtol")
REMOTE_DIR = "C:/Users/FlightSimulator/evtol_controller"   # sim 上的部署目录
HERE = os.path.dirname(os.path.abspath(__file__))
UPLOAD = ["config.py", "controller.py", "devkit_client.py", "event_server.py",
          "geo.py", "real_trials.py", "sim_check.py", "control_panel.py",
          "_panel_selftest.py", "_ap_swaptest.py", "_ap_route_test.py", "hmi_test.html",
          "_simconnect_probe.py", "_simconnect_replay.py", "sc_client.py", "_throttle_test.py",
          "_teleport_fix.py", "_rate_test.py", "_bandB_probe.py", "_planA.py", "_planB.py"]

def load_key(path):
    for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return cls.from_private_key_file(path)
        except Exception:
            pass
    raise RuntimeError("无法加载私钥: " + path)

def connect():
    key = load_key(KEY)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, PORT, USER, pkey=key, timeout=10,
              allow_agent=False, look_for_keys=False)
    return c

def run(c, cmd, timeout=60):
    stdin, out, err = c.exec_command(cmd, timeout=timeout)
    o = out.read().decode("utf-8", "replace").strip()
    e = err.read().decode("utf-8", "replace").strip()
    rc = out.channel.recv_exit_status()
    return rc, o, e

def do_test(c):
    for cmd in ["whoami", "hostname", "python --version"]:
        rc, o, e = run(c, cmd)
        print("%-16s => rc=%s %s %s" % (cmd, rc, o, ("ERR:" + e) if e else ""))
    # 本机 DevKit 是否活着（sim 本地 127.0.0.1:5000）
    rc, o, e = run(c, 'powershell -NoProfile -Command "try{(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/get -TimeoutSec 4).StatusCode}catch{\'DEVKIT_DOWN:\'+$_.Exception.Message}"')
    print("devkit_local     => rc=%s %s %s" % (rc, o, ("ERR:" + e) if e else ""))

def do_deploy(c):
    sftp = c.open_sftp()
    # 建目录
    try:
        sftp.mkdir(REMOTE_DIR)
    except IOError:
        pass
    for f in UPLOAD:
        lp = os.path.join(HERE, f)
        if not os.path.exists(lp):
            print("skip(缺失):", f); continue
        rp = posixpath.join(REMOTE_DIR, f)
        sftp.put(lp, rp)
        print("uploaded:", f)
    sftp.close()
    # 本地跑 --check（sim 上连 127.0.0.1:5000）
    rc, o, e = run(c, 'cd /d "%s" && python -X utf8 sim_check.py' % REMOTE_DIR.replace("/", "\\"), timeout=60)
    print("=== sim_check.py (真机 DevKit, sim 本地) ===\nrc=%s\n%s\n%s" % (rc, o, e))

def do_panel(c):
    wd = "C:/Users/FlightSimulator/evtol_controller"
    start = ('powershell -NoProfile -Command "Start-Process python -ArgumentList \'-X\',\'utf8\',\'control_panel.py\' '
             '-WorkingDirectory \'%s\' -WindowStyle Hidden"' % wd)
    run(c, start)
    time.sleep(3)
    rc, o, e = run(c, 'powershell -NoProfile -Command "try{(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/status -TimeoutSec 5).Content}catch{\'PANEL_DOWN:\'+$_.Exception.Message}"')
    print("=== 控制面板 /status ===\nrc=%s\n%s\n%s" % (rc, o, e))

def do_stoppanel(c):
    cmd = ('powershell -NoProfile -Command "$p=(Get-NetTCPConnection -LocalPort 8000 -State Listen -EA SilentlyContinue).OwningProcess; '
           "if($p){$p | Select-Object -Unique | % {Stop-Process -Id $_ -Force; 'killed '+$_}}else{'none'}\"")
    rc, o, e = run(c, cmd)
    print("stoppanel:", o, e)

def do_openfw(c):
    cmd = ('powershell -NoProfile -Command "New-NetFirewallRule -Name evtolpanel '
           "-DisplayName 'eVTOL Panel 8000' -Enabled True -Direction Inbound -Protocol TCP "
           "-Action Allow -LocalPort 8000 -EA SilentlyContinue | Out-Null; 'FW8000_DONE'; "
           "(Get-NetIPAddress -AddressFamily IPv4 | ? {$_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.*'}).IPAddress\"")
    rc, o, e = run(c, cmd)
    print("=== 防火墙8000 + sim 局域网IP ===\nrc=%s\n%s\n%s" % (rc, o, e))

def do_restart(c):
    for _ in range(5):
        rc, o, e = run(c, 'powershell -NoProfile -Command "$p=(Get-NetTCPConnection -LocalPort 8000 -State Listen -EA SilentlyContinue).OwningProcess; if($p){$p|Select-Object -Unique|%{Stop-Process -Id $_ -Force -EA SilentlyContinue}; \'killed\'}else{\'free\'}"')
        if o and 'free' in o:
            break
        time.sleep(1.5)
    time.sleep(1.5)
    do_panel(c)

def do_diag(c):
    rc, o, e = run(c, 'cd /d C:\\Users\\FlightSimulator\\evtol_controller && python -X utf8 -c "import urllib.request,json;d=json.load(urllib.request.urlopen(\'http://127.0.0.1:8000/status\',timeout=5));print(\'KEYS\',sorted(d.keys()));print(\'FILE_HAS_HELIPAD\',\'teleport_helipad\' in open(\'control_panel.py\',encoding=\'utf-8\').read())"')
    print("diag:\n", o, e)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "test"
    try:
        c = connect()
    except Exception as ex:
        print("CONNECT_FAIL:", repr(ex)); sys.exit(2)
    print("CONNECTED %s@%s" % (USER, HOST))
    try:
        if mode == "test":
            do_test(c)
        elif mode == "deploy":
            do_test(c); do_deploy(c)
        elif mode == "panel":
            do_panel(c)
        elif mode == "stoppanel":
            do_stoppanel(c)
        elif mode == "openfw":
            do_openfw(c)
        elif mode == "restart":
            do_restart(c)
        elif mode == "diag":
            do_diag(c)
        elif mode == "run":
            rc, o, e = run(c, sys.argv[2], timeout=300)
            print("rc=%s\n%s\n%s" % (rc, o, e))
        elif mode == "put":
            sftp = c.open_sftp()
            for f in sys.argv[2:]:
                sftp.put(os.path.join(HERE, f), posixpath.join(REMOTE_DIR, f)); print("put", f)
            sftp.close()
        elif mode == "bg":
            scr = sys.argv[2]; wd = "C:/Users/FlightSimulator/evtol_controller"
            # 先杀掉可能残留的同名脚本进程
            run(c, 'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"name=\'python.exe\'\\" | '
                   "Where-Object {$_.CommandLine -like '*%s*'} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue}\"" % scr)
            cmd = ('powershell -NoProfile -Command "Start-Process python -ArgumentList \'-X\',\'utf8\',\'%s\' '
                   "-WorkingDirectory '%s' -WindowStyle Hidden\"" % (scr, wd))
            run(c, cmd); print("bg launched", scr)
    finally:
        c.close()
    print("DONE")

if __name__ == "__main__":
    main()

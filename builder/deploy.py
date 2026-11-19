# -*- coding: utf-8 -*-
"""
JDC-1 官改固件 · 去广告与系统监控套件 — Windows 一键部署（exe 源码模板）

本文件是「一键部署.exe」的源码模板，**不直接运行**。
打包流程：
    1. 运行 build_deploy.py，把父目录的 install.sh + scripts/ + web/ 内容
       以 base64 注入本模板，生成 deploy_final.py
    2. 用 PyInstaller 把 deploy_final.py 打包成 一键部署.exe

运行后：收集路由器 IP/账号/密码 → 上传内置脚本到路由器 → 远程执行 install.sh。
内置了所有部署文件内容，用户只需一个 exe，双击即用，无需 PuTTY / Python。
"""
import os
import sys
import time
import base64

# 强制 stdout/stderr 用 UTF-8，避免 Windows GBK 控制台无法编码 ✓ 等字符导致崩溃
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 内置部署文件内容（由 build_deploy.py 通过 base64 注入）
# 格式：{ "远程相对路径": "base64字符串", ... }
EMBEDDED_FILES = {}

REMOTE_DIR = "/tmp/jdc1-adblock"


def getpass_prompt(msg):
    """读取密码（不回显）。exe 下用 getpass 会隐藏输入。"""
    try:
        import getpass
        return getpass.getpass(msg)
    except Exception:
        return input(msg)


def main():
    import paramiko

    print("=" * 50)
    print("  JDC-1 去广告与系统监控套件 一键部署")
    print("=" * 50)
    print()
    print("  提示：如本窗口一闪而过（被杀毒软件拦截），")
    print("        请在杀毒软件中把本程序加入信任/白名单后重试。")
    print()
    # --- 收集连接信息（IP/用户名有默认值，可直接回车跳过）---
    ip = os.environ.get("JDC1_IP", "").strip()
    if not ip:
        ip = input("请输入路由器 IP（默认 192.168.68.1）: ").strip()
    if not ip:
        ip = "192.168.68.1"
    user = os.environ.get("JDC1_USER", "").strip()
    if not user:
        user = input("请输入 SSH 用户名（默认 root）: ").strip()
    if not user:
        user = "root"
    pwd = os.environ.get("JDC1_PWD", "")
    if not pwd:
        pwd = getpass_prompt("请输入 SSH 密码: ")
    print()

    if not EMBEDDED_FILES:
        print("[错误] 内置部署文件缺失，exe 打包异常")
        input("按回车退出...")
        sys.exit(1)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print("正在连接 %s@%s ..." % (user, ip))
        client.connect(ip, username=user, password=pwd,
                       look_for_keys=False, allow_agent=False, timeout=10)
    except Exception as e:
        print("[错误] 连接失败：%s" % e)
        print("       请检查 IP、账号、密码、网络连接")
        try:
            input("按回车退出...")
        except (EOFError, KeyboardInterrupt):
            pass
        sys.exit(1)

    def run(cmd):
        _i, o, _e = client.exec_command(cmd)
        out = o.read().decode(errors="replace")
        return out

    def put_bytes(data, remote_path):
        chan = client.get_transport().open_session()
        chan.exec_command("cat > %s" % remote_path)
        chan.sendall(data)
        chan.shutdown_write()
        time.sleep(0.3)
        while chan.recv_ready():
            chan.recv(65536)
        return chan.recv_exit_status()

    try:
        # --- 1. 准备远端目录 ---
        print("[1/2] 上传部署文件到路由器 %s ..." % REMOTE_DIR)
        run("rm -rf %s && mkdir -p %s/scripts %s/web" % (REMOTE_DIR, REMOTE_DIR, REMOTE_DIR))

        # --- 2. 上传所有内置文件 ---
        total = 0
        for rel, b64 in EMBEDDED_FILES.items():
            data = base64.b64decode(b64)
            remote_path = "%s/%s" % (REMOTE_DIR, rel.replace("\\", "/"))
            st = put_bytes(data, remote_path)
            if st != 0:
                raise RuntimeError("上传失败：%s (exit %s)" % (rel, st))
            total += 1
        print("  已上传 %d 个文件" % total)

        # --- 3. 远程执行 install.sh ---
        print()
        print("[2/2] 在路由器上执行 install.sh ...")
        print()
        stdin, stdout, stderr = client.exec_command("cd %s && sh install.sh" % REMOTE_DIR)
        # 实时透传输出
        for line in iter(stdout.readline, ""):
            sys.stdout.write(line)
            sys.stdout.flush()
        err = stderr.read().decode(errors="replace")
        if err.strip():
            print("[stderr]", err)
        exit_status = stdout.channel.recv_exit_status()
        print()
        if exit_status != 0:
            print("[错误] install.sh 执行失败（exit %s）" % exit_status)
        else:
            print("=" * 50)
            print("  部署完成！")
            print("  接下来请按 install.sh 末尾提示：")
            print("  1. sh /usr/bin/adguard_install.sh install")
            print("  2. sh /usr/bin/adblock_update.sh")
            print("  3. reboot")
            print("=" * 50)

    except Exception as e:
        print("[错误] %s" % e)
    finally:
        client.close()

    print()
    try:
        input("按回车退出...")
    except (EOFError, KeyboardInterrupt):
        pass


# ==== 内置文件内容（由 build_deploy.py 生成并注入，必须位于 main() 调用之前）====
# ===EMBED_START===


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
构建脚本：把父目录的 install.sh + scripts/ + web/ 内容 base64 注入 deploy.py 模板，
生成 deploy_final.py（含内置文件），供 PyInstaller 打包成单个 exe。

用法：
    cd builder
    python build_deploy.py        # 生成 deploy_final.py
    python -m PyInstaller --onefile --console --name "一键部署" deploy_final.py
    # 产物在 dist/一键部署.exe，把它复制到项目根目录即可

以后 install.sh / scripts/ / web/ 有任何改动，只需重跑本脚本 + 重新打包即可。
"""
import os
import base64
import shutil
import subprocess
import sys


def ensure_deps():
    """检查并自动安装依赖（paramiko + pyinstaller），解决系统 Python 缺依赖导致的失败。

    paramiko 固定 2.12.0：较新版本（5.x）移除了 ssh-rsa 支持，而路由器 dropbear 只提供 ssh-rsa。
    """
    missing = []
    try:
        import paramiko  # noqa: F401
        if tuple(map(int, paramiko.__version__.split(".")[:2])) >= (5, 0):
            # 装了 5.x 也要降级，因为 ssh-rsa 被移除
            missing.append("paramiko==2.12.0")
    except ImportError:
        missing.append("paramiko==2.12.0")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        missing.append("pyinstaller")

    if missing:
        print("[提示] 缺少/需修正依赖：%s，正在自动安装（首次需联网）..." % ", ".join(missing))
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + missing,
            cwd=BUILDER_DIR,
        )
        if r.returncode != 0:
            print("[错误] 依赖安装失败，请手动执行：")
            print("       %s -m pip install %s" % (sys.executable, " ".join(missing)))
            sys.exit(1)
        print("[提示] 依赖安装完成")


# builder/ 目录
BUILDER_DIR = os.path.dirname(os.path.abspath(__file__))
# 项目根目录（jdc1-adblock/）
BASE = os.path.dirname(BUILDER_DIR)

# 要内置的文件清单（相对项目根的路径）
FILES = {
    "install.sh": os.path.join(BASE, "install.sh"),
    "scripts/adblock.cgi": os.path.join(BASE, "scripts", "adblock.cgi"),
    "scripts/adblock_status.cgi": os.path.join(BASE, "scripts", "adblock_status.cgi"),
    "scripts/filemgr.cgi": os.path.join(BASE, "scripts", "filemgr.cgi"),
    "scripts/file_dl.cgi": os.path.join(BASE, "scripts", "file_dl.cgi"),
    "scripts/download_web.html": os.path.join(BASE, "scripts", "download_web.html"),
    "scripts/filemgr.html": os.path.join(BASE, "scripts", "filemgr.html"),
    "scripts/fm_upload.lua": os.path.join(BASE, "scripts", "fm_upload.lua"),
    "scripts/downloader.conf": os.path.join(BASE, "scripts", "downloader.conf"),
    "scripts/proc_monitor.sh": os.path.join(BASE, "scripts", "proc_monitor.sh"),
    "scripts/adblock_update.sh": os.path.join(BASE, "scripts", "adblock_update.sh"),
    "scripts/adblock_rebuild_sources.sh": os.path.join(BASE, "scripts", "adblock_rebuild_sources.sh"),
    "scripts/adguard_install.sh": os.path.join(BASE, "scripts", "adguard_install.sh"),
    "scripts/sources.list": os.path.join(BASE, "scripts", "sources.list"),
    "web/main_patched.html": os.path.join(BASE, "web", "main_patched.html"),
}


def build(exe_name="一键部署"):
    ensure_deps()  # 自动检查并安装依赖（paramiko + pyinstaller）

    # 读取 deploy.py 模板
    template_path = os.path.join(BUILDER_DIR, "deploy.py")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    # 构建 EMBEDDED_FILES 字典的 Python 源码
    lines = ["EMBEDDED_FILES = {"]
    for rel, path in FILES.items():
        if not os.path.exists(path):
            print("[错误] 文件不存在: %s" % path)
            sys.exit(1)
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        lines.append('    "%s": "%s",' % (rel.replace("\\", "/"), b64))
    lines.append("}")

    embedded_code = "\n".join(lines)

    # 替换占位符
    marker = "# ===EMBED_START==="
    if marker not in template:
        print("[错误] deploy.py 里缺少占位符 %s" % marker)
        sys.exit(1)
    final = template.replace(marker, embedded_code)

    out_path = os.path.join(BUILDER_DIR, "deploy_final.py")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final)

    print("已生成 deploy_final.py，内置文件数: %d" % len(FILES))

    # 用 PyInstaller 打包（单文件 onefile 模式）
    print("正在用 PyInstaller 打包（单文件模式）...")
    dist_path = os.path.join(BUILDER_DIR, "dist")
    workpath = os.path.join(BUILDER_DIR, "build_tmp")
    specpath = os.path.join(BUILDER_DIR, "build_tmp")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--console",
        "--name", exe_name,
        "--distpath", dist_path,
        "--workpath", workpath,
        "--specpath", specpath,
        "--clean",
        out_path,
    ]
    r = subprocess.run(cmd, cwd=BUILDER_DIR)
    if r.returncode != 0:
        print("[错误] PyInstaller 打包失败")
        sys.exit(1)

    # 把单文件 exe 复制到 builder 目录
    exe_path = os.path.join(dist_path, exe_name + ".exe")
    dest = os.path.join(BUILDER_DIR, exe_name + ".exe")
    if os.path.exists(exe_path):
        shutil.copy(exe_path, dest)
        print("已生成 %s（%.1f MB）" % (dest, os.path.getsize(dest) / 1024 / 1024))
    else:
        print("[错误] 未找到打包产物 %s" % exe_path)
        sys.exit(1)

    # 清理中间产物（deploy_final.py 是自动生成的中间产物，一并清理，仓库只保留两个源文件）
    if os.path.exists(workpath):
        shutil.rmtree(workpath)
    if os.path.exists(dist_path):
        shutil.rmtree(dist_path)
    if os.path.exists(out_path):
        os.remove(out_path)
    print("中间产物已清理（仓库只保留 deploy.py 和 build_deploy.py 两个源文件）")


if __name__ == "__main__":
    build()

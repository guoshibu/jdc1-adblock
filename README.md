# JDC-1 官改固件 · 去广告与系统监控套件

> 京东云无线宝一代（JDC-1P，MT7621AT）官改固件增强插件
> 在保留原厂京东云挖豆（PCDN）功能的前提下，为 Web 后台注入 **去广告引擎 + 系统监控管理页**，全部功能持久化到 overlay、开机自启。

**作者**：[guoshibu](https://github.com/guoshibu)

[![Version](https://img.shields.io/badge/Version-v1.1.0-orange.svg)](https://github.com/guoshibu/jdc1-adblock/releases)
[![Platform](https://img.shields.io/badge/Platform-MT7621AT%20MIPS-blue.svg)](#)
[![Firmware](https://img.shields.io/badge/Firmware-JDC4.0.0.r6636_ssh-important.svg)](#)
[![AdGuard Home](https://img.shields.io/badge/AdGuard%20Home-v0.107.80-brightgreen.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

---

## 目录

- [功能特性](#功能特性)
- [架构总览](#架构总览)
- [目录结构](#目录结构)
- [文件清单](#文件清单)
- [固件来源](#固件来源)
- [快速开始](#快速开始)
- [端口与数据流](#端口与数据流)
- [系统监控页详解](#系统监控页详解)
- [原理说明](#原理说明)
- [性能评估](#性能评估)
- [已知问题](#已知问题)
- [致谢](#致谢)

---

## 功能特性

### 去广告（双引擎）

| 引擎               | 角色             | 端口                      | 规则量   |
| ---------------- | -------------- | ----------------------- | ----- |
| **AdGuard Home** | 主力过滤器（DNS 级）   | DNS `5353` / Web `3000` | ~5 万条 |
| **dnsmasq**      | 兜底过滤（hosts 注入） | `53`                    | 视规则源  |

- 支持三种规则格式自动转换：`dnsmasq(address=/域名/)`、`AdBlock(||域名^)`、`hosts(0.0.0.0 域名)`
- 多规则源可合并、可自定义（最多 3 条自定义源）
- dnsmasq 与 AGH 可独立开关，互不影响

**规则源管理（v1.1）**：在管理页「规则源」区，4 个预设源 + 3 个自定义槽位均可勾选启用，操作即时生效、页面不刷新。

- 自定义源填好「名称 + URL」后：
  - 点「保存」→ 后端**真实下载**并数有效规则条数（≥50 条才算有效），成功显示 `✓ 已验证 N 条`，失败显示红色原因且**保留输入内容**可改
  - 或直接勾选复选框 → 一步完成"验证 + 启用"
  - 只有验证通过的源才能启用；无效/超时的源勾不上，杜绝"显示启用但没生效"
  - 点「删除」移除该槽位
- 启用状态存在 `/etc/adblock/preset_flags`（预设）和 `/etc/adblock/custom1~3` 第 3 列（自定义），验证状态存第 4 列（`OK:N` / `FAIL:原因`）；`adblock_rebuild_sources.sh` 据此重建 `sources.list`——停用的源整行注释，`adblock_update.sh` 自动跳过
- 阈值说明：单源 ≥50 条即通过（300 条的小规则源合法）；`adblock_update.sh` 另有"整体规则库 <1000 条不写入"的保护线，两者互不冲突

### 系统监控（Web 管理页）

- **实时系统状态**：CPU 占用 / 频率 / 型号、内存 / swap、负载（1/5/15 分钟）、运行时间
- **进程占用**（类 Windows 任务管理器）：
  - 进程名 + PID + 中文备注分列显示
  - 实时 CPU%（占整机口径，两次采样求差）、累计 CPU 时间、内存 RSS、虚拟地址空间 VmSize
  - 表头点击排序（升/降序）、列宽拖拽（Excel 式）、斑马纹
  - 展开/收起全部进程，默认 TOP5
- 刷新频率可选（1 / 5 / 10 秒 / 手动），手动「立即刷新」

### 其他

- Web 后台菜单栏新增「去广告」入口

---

## 架构总览

```
                          ┌─────────────────────────────────────────┐
                          │            浏览器 Web 管理页              │
                          │   /cgi-bin/adblock.cgi  (HTML+JS 轮询)    │
                          └───────────────────┬─────────────────────┘
                                              │ fetch JSON (5s 默认)
                                              ▼
                          ┌─────────────────────────────────────────┐
                          │   nginx (OpenResty) + fcgiwrap            │
                          │   /cgi-bin/adblock_status.cgi  (JSON 接口)│
                          └───────┬──────────────────────────┬───────┘
                                  │ 读缓存(秒回)              │ 读缓存
                                  ▼                          ▼
                    ┌──────────────────────┐      ┌──────────────────────┐
                    │ /tmp/procs_cache.json │      │ /tmp/cpu_cache        │
                    │ /tmp/adblock.count    │      │ /etc/adblock/disabled  │
                    └──────────▲───────────┘      └──────────▲───────────┘
                               │ 常驻采集(5s/次)              │
                               │                              │
                    ┌──────────┴───────────┐                  │
                    │ proc_monitor.sh 守护  │──────────────────┘
                    │ (awk 零 fork 读 /proc)│
                    └──────────────────────┘

  DNS 数据流（去广告）:
  客户端 ──→ dnsmasq:53 ──→ 127.0.0.1#5353 (AdGuard Home) ──→ 上游 DNS
                                │
                                └─→ 命中规则 → 拦截(0.0.0.0)
```

---

## 目录结构

```
JDC-1-官改插件/
├── README.md                # 本文件
├── LICENSE                  # MIT 许可
├── CHANGELOG.md             # 版本历史
├── .gitignore               # 忽略 exe 等构建产物
├── install.sh               # 一键部署脚本（路由器端执行）
├── builder/                 # Windows 一键部署 exe 的源码与构建工具（详见「重新生成 exe」）
│   ├── 生成exe.bat          # Windows 双击重新生成 exe
│   ├── deploy.py            # exe 源码模板
│   └── build_deploy.py      # 构建脚本（注入脚本内容 + 打包）
├── scripts/                 # 部署到路由器的脚本
│   ├── adblock.cgi          # 管理页主页面（HTML+CSS+JS，约 39KB）
│   ├── adblock_status.cgi   # 实时状态 JSON 接口（供前端轮询）
│   ├── proc_monitor.sh      # 进程数据采集守护（常驻，5s/次）
│   ├── adblock_update.sh    # dnsmasq 去广告规则更新（下载所有源+转换+去重）
│   ├── adblock_rebuild_sources.sh # 规则源重建：从预设标志+自定义源合成 sources.list
│   ├── adguard_install.sh   # AdGuard Home 安装/启动/停止脚本
│   └── sources.list         # dnsmasq 规则源列表（名称|URL）
├── web/                     # Web 后台菜单入口
│   ├── README.md            # 菜单入口 patch 说明
│   └── main_patched.html    # 已注入「去广告」菜单的完整文件
└── firmware/                # 官改过渡固件（刷机用）
    ├── README.md
    └── jdcloud-1-transitional.zip
```

> `一键部署.exe`（一键部署成品）**不在仓库里**，由 `builder/生成exe.bat` 本地构建，发布时上传到 GitHub Releases。

---

## 文件清单

### 部署到路由器的文件

| 文件                   | 路由器路径                             | 用途           | 持久化     |
| -------------------- | --------------------------------- | ------------ | ------- |
| `adblock.cgi`        | `/www/cgi-bin/adblock.cgi`        | 管理页主页面       | overlay |
| `adblock_status.cgi` | `/www/cgi-bin/adblock_status.cgi` | JSON 状态接口    | overlay |
| `proc_monitor.sh`    | `/usr/bin/proc_monitor.sh`        | 进程采集守护       | overlay |
| `adblock_update.sh`  | `/usr/bin/adblock_update.sh`      | dnsmasq 规则更新 | overlay |
| `adblock_rebuild_sources.sh` | `/usr/bin/adblock_rebuild_sources.sh` | 规则源重建（v1.1 新增） | overlay |
| `adguard_install.sh` | `/usr/bin/adguard_install.sh`     | AGH 安装/启动    | overlay |
| `sources.list`       | `/etc/adblock/sources.list`       | dnsmasq 规则源  | overlay |
| `web/main_patched.html` | `/www/PC/main.html`             | 注入「去广告」菜单项   | overlay |

### 运行时生成（非持久，重启清空）

| 路径                                         | 说明                   |
| ------------------------------------------ | -------------------- |
| `/tmp/procs_cache.json`                    | 进程数据缓存               |
| `/tmp/cpu_cache`                           | CPU 占用缓存             |
| `/tmp/proc_monitor.pid`                    | 进程守护 PID 锁           |
| `/tmp/adblock.count` / `/tmp/adblock.time` | 拦截计数/更新时间            |
| `/tmp/dnsmasq.d/adguard_*.conf`            | dnsmasq 上游指向 AGH 的配置 |

> **持久化状态标志**（在 `/etc/adblock/`，overlay 持久，重启后保留）：
> - `/etc/adblock/disabled` — dnsmasq 去广告停用标志（存在 = 已停用）
> - `/etc/adblock/agh_disabled` — AGH 停用标志（存在 = 已停用，开机自启会跳过）

### AGH 本体（安装脚本下载）

| 路径                              | 说明                          |
| ------------------------------- | --------------------------- |
| `/opt/adguard/bin/AdGuardHome`  | AGH 主程序（v0.107.80）          |
| `/opt/adguard/AdGuardHome.yaml` | AGH 配置（DNS 5353 / Web 3000） |
| `/opt/adguard/agh-backup/`      | AGH 备份                      |

---

## 固件来源

本插件运行在**官改过渡固件**上（非原厂 r6645，也非 OpenWrt 官方）：

| 项目    | 值                                                                                                                                         |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| 固件文件名 | `JDC4.0.0.r6636_ssh.bin`（18,743,300 B，MD5 `a6e1f57449095398105a615458bdb2f0`）                                                             |
| 原始压缩包 | `jdcloud-1-transitional.zip`（sha256 `7008f4b2…af61e`）                                                                                     |
| 来源    | GitHub 仓库 **`cbywyz/jdcloud-re-sp-01b-flash`**（同型号 JDCloud RE-SP-01B、原厂 r6645 的实机记录项目）                                                    |
| 下载方式  | jsDelivr 返回错误页，改用 `ghfast.top` 加速源，约 30 秒完成                                                                                               |
| 固件性质  | 基于官方 JDCOS **4.0.0.r6636** 修改：rootfs 内开 dropbear SSH（`RootPasswordAuth on` + `Port 22` + 预置 host key），根目录塞入 `breed-mt7621-jd-cloud-1.bin` |
| 刷入后版本 | 显示 `4.0.0.r6636`（比原厂 r6645 低一档，正常）                                                                                                        |
| 固件包   | 已随本仓库分发，见 `firmware/jdcloud-1-transitional.zip`                                                                                           |

> **机型说明**：硬件真名是**京东云一代（JD Gen1）**——`/proc/device-tree/model` 为 `MediaTek MT7621 JD Gen1`，内核 board name 为 `mt7621-jd-Gen1`，型号 id `jdcloud_re-sp-01b`（JDC-1P 64G）。
>
> 但官方固件的 `os-release` 里 `DISTRIB_ID=JDbox-luban`、`LEDE_DEVICE_PRODUCT=Luban`（鲁班），即**一代与鲁班 AX1800 共用同一套固件代号体系**，真正的机型区分点是硬件 board name（`Gen1`），而非固件里的 `luban` 标识。FIT 镜像描述为 `MIPS OpenWrt Linux-4.4.198 JDbox-luban 4.0.0.r6636`（魔数 `d00dfeed`）。

---

## 快速开始

### 前置条件

- 京东云无线宝一代（JDC-1P / JDCloud RE-SP-01B），已刷入官改过渡固件 `JDC4.0.0.r6636_ssh.bin`（基于 OpenWrt 17.01，内核 4.4.198）
- SSH 可登录（`root@192.168.68.1`）
- 路由器已联网（用于下载 AGH 与规则源）

### 安装

提供三种部署方式：**一键 exe**（推荐，Windows）或**手动部署**（了解细节）或**自建 exe**。

#### 方式一：一键部署（推荐，Windows）

1. 从 [Releases](../../releases) 下载 `一键部署.exe`（或双击 `builder/生成exe.bat` 自行构建）
2. 双击运行 `一键部署.exe`（**无需安装任何东西**，PuTTY/Python 都不用）
3. 按提示输入路由器 IP、SSH 用户名（默认 root）、密码
4. 脚本自动上传内置的全部脚本到路由器并执行 `install.sh`

> `一键部署.exe` 内置了 `install.sh` + 全部部署脚本，用户只需这一个文件即可完成部署。
> 仓库源码里不含 exe（见 `.gitignore`），请从 Releases 下载或自行构建。

> **⚠️ 杀毒软件误报说明**：`一键部署.exe` 是 PyInstaller 打包的**单文件**程序，运行时会把自身解压到系统临时目录（`%TEMP%\_MEI*`）再加载运行。**360 等杀毒软件常会拦截这一步**，表现为「双击闪退」或报错 `Failed to load Python DLL ... python3xx.dll`。这不是程序问题，是杀毒误报。
>
> **解决办法（任选其一）**：
> 1. 在 360 杀毒中把 `一键部署.exe`（或整个解压目录）加入**信任区/白名单**，然后重新双击；
> 2. 若第一次闪退、第二次正常，直接重试即可（杀毒软件已放行）；
> 3. 若持续拦截，改用**方式二（手动部署 install.sh）**，完全绕开 exe。

#### 方式二：手动部署（Linux / macOS，或了解细节）

```sh
# 把整个项目目录传到路由器 /tmp/jdc1-adblock/（scp -r 或 WinSCP）
scp -r ./jdc1-adblock root@192.168.68.1:/tmp/

# SSH 登录后执行
ssh root@192.168.68.1
cd /tmp/jdc1-adblock && sh install.sh
```

`install.sh` 会自动完成：脚本部署、菜单入口注入（自动备份原文件）、开机自启、每日定时更新、`/AD` 短链接配置、md5 校验。**幂等设计，可重复执行**。

执行完 install.sh 后，还需手动跑最后三步（AGH 安装依赖联网下载，脚本不自动做）：

```sh
sh /usr/bin/adguard_install.sh install   # 安装并启动 AGH（联网下载）
sh /usr/bin/adblock_update.sh            # 更新 dnsmasq 规则
reboot                                   # 重启使自启生效
```

#### 方式二：手动部署

```sh
# 1. 上传所有脚本到对应路径（见「文件清单」）
#    scripts/*.cgi  → /www/cgi-bin/
#    scripts/*.sh   → /usr/bin/
#    scripts/sources.list → /etc/adblock/
#    web/main_patched.html → /www/PC/main.html（注入「去广告」菜单，见 web/README.md）

# 2. 安装并启动 AdGuard Home
sh /usr/bin/adguard_install.sh install

# 3. 更新 dnsmasq 规则
sh /usr/bin/adblock_update.sh

# 4. 写入开机自启（/etc/rc.local 末尾，exit 0 之前）
echo '(sleep 60 && /usr/bin/adblock_update.sh >/dev/null 2>&1) &' >> /etc/rc.local
echo '(sleep 70 && /usr/bin/adguard_install.sh autostart >/dev/null 2>&1) &' >> /etc/rc.local
echo '(sleep 30 && /usr/bin/proc_monitor.sh >/dev/null 2>&1 &) &' >> /etc/rc.local

# 5. 写入每日定时更新（每天 4:30 自动更新规则）
echo '30 4 * * * /usr/bin/adblock_update.sh >/dev/null 2>&1' >> /etc/crontabs/root
/etc/init.d/cron restart

# 6. 添加 /AD 短链接（可选，在 nginx 配置的 location /cgi-bin 前插入）
#    location ~* ^/AD$ { return 302 /cgi-bin/adblock.cgi; }
#    编辑 /etc/nginx/conf.d/jdc-web.conf，然后 nginx -t && nginx -s reload

# 7. 重启验证
reboot
```

> **持久化说明**：京东云固件使用 overlay 文件系统，写入 `/overlay/upper/` 下的文件（即 `/etc`、`/usr/bin`、`/www` 等路径）重启后保留，无需额外 `mtd_storage.sh save`。

> **⚠️ AGH 开机自启务必用 `autostart`（不是 `start`）**：`autostart` 会检查 `/etc/adblock/agh_disabled` 标志，若上次是停用状态则跳过；`start` 会无条件清除标志并启动，导致「停用后重启又自动起」。

### 重新生成 一键部署.exe

`一键部署.exe` 内置了 `install.sh` + `scripts/` + `web/` 的全部内容。**以后改动了这些脚本，需要重新打包 exe**，否则 exe 里的还是旧版本。构建产物输出到 `builder/一键部署.exe`（已被 `.gitignore` 忽略，发布时上传到 Releases）。

源码与构建工具都在 `builder/` 目录。**Windows 用户**直接双击 `builder/生成exe.bat` 即可（自动检查 Python、按需安装 PyInstaller、生成 exe）；**命令行**方式如下：

```sh
# 前置：本机安装 Python 3.9+ 和 PyInstaller
#   pip install pyinstaller

cd builder
python build_deploy.py
```

`build_deploy.py` 会自动完成四步：

1. 读取项目根目录的 `install.sh` + `scripts/` + `web/` 内容
2. 以 base64 注入 `deploy.py` 模板，生成 `deploy_final.py`（构建中间产物，自动生成）
3. 用 PyInstaller 打包成单个 `一键部署.exe`，输出到 `builder/` 目录
4. 清理中间产物

> 仓库里只保留 `deploy.py`（源码模板）、`build_deploy.py`（构建工具）和 `生成exe.bat`（Windows 一键构建）三个文件；`deploy_final.py`、`一键部署.exe` 是运行 `build_deploy.py` 时自动生成的产物，无需手动创建或修改，也不会提交到仓库。

### 使用

- **管理页**：浏览器访问 `http://192.168.68.1/AD`（短链接，大小写不敏感，`/ad` 亦可；或 `http://192.168.68.1/cgi-bin/adblock.cgi`，或后台顶栏「去广告」菜单）
- **AGH 控制台**：`http://192.168.68.1:3000`
- **查看日志**：`logread | grep -i adguard` / `tail -f /tmp/syslog.log`

**启停状态跟随**：dnsmasq 去广告与 AGH 的「停用/启用」状态都会持久化到 `/etc/adblock/`，重启后保持之前的状态（不会出现「关了又自己启动」）。

---

## 端口与数据流

| 端口     | 协议   | 归属           | 说明                   |
| ------ | ---- | ------------ | -------------------- |
| `53`   | DNS  | dnsmasq      | 局域网 DNS 入口，上游转发到 AGH |
| `5353` | DNS  | AdGuard Home | 主力过滤引擎               |
| `3000` | HTTP | AdGuard Home | AGH Web 管理控制台        |
| `80`   | HTTP | nginx        | 官改 Web 后台 + 管理页 CGI  |

**去广告数据流**：

```
客户端 DNS 请求
  → dnsmasq (53)
    → 命中 dnsmasq hosts 黑名单? → 拦截
    → 未命中 → 转发 127.0.0.1#5353 (AGH)
        → 命中 AGH 规则? → 拦截
        → 未命中 → 上游公共 DNS (如 223.5.5.5)
```

---

## 系统监控页详解

### 进程占用卡片

| 列       | 含义                 | 排序 | 备注                                 |
| ------- | ------------------ | -- | ---------------------------------- |
| 进程名     | `/proc/[pid]/comm` | ✅  | 含 PID 小字（第二行）                      |
| 备注      | 进程中文名（内置映射表）       | ❌  | 见 `proc_monitor.sh` 的 `get_desc()` |
| CPU %   | 实时占用，占整机百分比（÷4 核，恒 0-100） | ✅  | 两次采样(1s)求差 |
| 累计CPU   | 开机以来累计 CPU 时间      | ✅  | `utime+stime / 100`                |
| 内存(RSS) | 真实物理内存             | ✅  | `VmRSS`                            |
| 虚拟地址空间  | VmSize             | ✅  | 参考价值低，主要看 RSS                      |

**交互特性**：

- 表头点击排序：点一下降序（▼），再点升序（▲），切新列默认降序
- 列宽拖拽：鼠标移到表头右边缘（最后一列左边缘）出现拖拽手柄，横向拖动，只联动相邻一列，其余列不动；位移 <5px 视为点击（触发排序），>5px 视为拖拽
- 列宽恢复默认：仅整页刷新（F5）时恢复，定时刷新/立即刷新不重置
- 斑马纹 + 悬停高亮
- 底部合计：`共 N 个进程 · CPU 合计 X% · 内存合计 Y MB`

---

## 原理说明

### 1. 进程采集为何用「常驻守护 + 缓存」？

最初方案是每次请求 `status.cgi` 时现场 `fork` 遍历 `/proc`，实测单次采集 **14 秒**（shell 循环 `cat/grep/awk` 每个进程 fork 多次）。改为 `proc_monitor.sh` 常驻循环，用 **awk 重定向 `getline < "/proc/..."`** 零 fork 读文件，单次采集降到 **1 秒**（提速 14 倍）。

前端轮询 `status.cgi` 时只读缓存文件，**秒回**，不阻塞。

### 2. CPU% 的口径

- **系统状态卡片的 CPU%**：整机 CPU 占用（`/proc/stat` 求差，÷ 4 核）
- **进程列表的 CPU%**：单个进程实时占用，`(utime+stime)` 两次采样求差后 ÷ 4 核，即「占整机的百分比」，恒 0-100

两者口径不同：前者是"整机现在多忙"，后者是"某个进程占了多少核"。

### 3. 列宽拖拽为何只联动相邻列？

表格用 `table-layout:fixed`，若直接改某列 `th` 宽度，浏览器会按比例重分配所有列。改用 `<colgroup>` + `<col>` 承载列宽，拖拽时只改「当前列 + 相邻列」两个 `<col>`，总宽不变，其余列纹丝不动。

### 4. 持久化机制

京东云固件的根文件系统是 squashfs（只读）+ overlay（可写），`/overlay/upper/` 下对 `/etc`、`/usr/bin`、`/www` 的修改重启后保留。因此脚本直接写入对应路径即可持久，**无需** `mtd_storage.sh save`（那是 `/etc/storage` 的老机制）。

---

## 性能评估

| 项目     | 数值                    | 说明              |
| ------ | --------------------- | --------------- |
| 进程采集   | ~1s / 5s              | awk 零 fork，占用极低 |
| AGH 内存 | ~598 MB VSZ（RSS 见管理页） | 5 万条规则          |
| 前端轮询   | 5s / 次（可选）            | 读缓存秒回           |
| 对挖豆影响  | 无实测影响                 | 采集与过滤均为独立低优先进程  |

> 5 万条规则对 MT7621（双核 880MHz）+ 512MB RAM 负担可接受，AGH 是 MIPS 官方构建，内存占用可控。

---

## 已知问题

暂无已知问题（当前功能均已在实机验证通过）。

---

## 致谢

- [AdGuard Home](https://github.com/AdguardTeam/AdGuardHome) — 开源 DNS 级广告拦截
- [OpenWrt](https://openwrt.org/) — 京东云原厂固件所基于的路由系统
- [cbywyz/jdcloud-re-sp-01b-flash](https://github.com/cbywyz/jdcloud-re-sp-01b-flash) — 官改固件与同型号实机刷机记录来源
- [Breed 不死引导](https://breed.hackpascal.net/) — `breed-mt7621-jd-cloud-1.bin`
- 京东云无线宝一代社区

---

## License

[MIT](./LICENSE) © 2026 [guoshibu](https://github.com/guoshibu)

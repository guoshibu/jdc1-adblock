# Changelog

本项目的所有重要改动记录。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增
- 一键部署脚本 `install.sh`（路由器端），幂等 + 自愈设计
- `一键部署.exe`（Windows 端，零依赖双击即用，内置全部脚本），取代原 `一键部署.bat`
- `builder/` 构建工具目录：`deploy.py`（exe 源码）+ `build_deploy.py`（一键构建）+ `生成exe.bat`（Windows 双击构建，GBK 编码）
- `/AD` 短链接入口（nginx 302 重定向，大小写不敏感）

### 修复
- dnsmasq 去广告「停用后重启又自动启动」——停用标志从易失的 `/tmp` 迁移到持久化的 `/etc/adblock/disabled`
- AGH「停止失败」——`pkill` 在 busybox 精简版不存在，改用 `kill $(pidof AdGuardHome)`
- AGH「停用后重启又自动启动」——新增 `autostart` 子命令 + `/etc/adblock/agh_disabled` 持久标志
- AGH Web 端口文档错误——6060 实为 pprof 调试端口，Web 端口是 3000
- `install.sh` 的 /AD 幂等判断转义 bug——`grep -q "~\* \^/AD\$"` 双引号转义失效导致重复插入，改用 `grep -Fq 'location ~* ^/AD$'`
- `build_deploy.py` 自动安装依赖（paramiko==2.12.0 + pyinstaller），解决系统 Python 缺依赖导致的构建失败
- `一键部署.exe` 被杀毒软件（360 等）误拦截——在 README 与 exe 内加白名单提示

### 文档
- 补齐 README 安装步骤：菜单入口部署、cron 每日更新、/AD 短链接
- 新增 CHANGELOG.md、install.sh、builder/ 构建工具、.gitignore
- 补充「重新生成 exe」与「杀毒软件误报」说明

## [1.0.0] - 2026-11-19

### 初始版本

- AdGuard Home（v0.107.80，DNS 5353 / Web 3000）主力去广告
- dnsmasq 兜底去广告（多规则源合并、三格式自动转换）
- 系统监控管理页（CPU/内存/负载/运行时间 + 进程占用）
- 进程占用：类 Windows 任务管理器（排序、列宽拖拽、斑马纹、进程备注、实时 CPU%）
- Web 后台菜单栏「去广告」入口
- 面板 LED 网络指示
- overlay 持久化 + rc.local 开机自启 + cron 每日更新
- 官改过渡固件 `JDC4.0.0.r6636_ssh`（来源 cbywyz/jdcloud-re-sp-01b-flash）

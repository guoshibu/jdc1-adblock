# Changelog

本项目的所有重要改动记录。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [1.1.0] - 2026-11-20

### 新增
- 一键部署脚本 `install.sh`（路由器端），幂等 + 自愈设计
- `一键部署.exe`（Windows 端，零依赖双击即用，内置全部脚本），取代原 `一键部署.bat`
- `builder/` 构建工具目录：`deploy.py`（exe 源码）+ `build_deploy.py`（一键构建）+ `生成exe.bat`（Windows 双击构建，GBK 编码）
- `/AD` 短链接入口（nginx 302 重定向，大小写不敏感）
- `adblock_rebuild_sources.sh`：规则源重建脚本，从 preset_flags + custom1~3 合成 sources.list

### 修复
- 自定义规则源无法保存——原 URL 解码只处理少数符号导致中文变 `%XX` 乱码；改用通用 `urldecode()`（逐字节还原 UTF-8），并把输入框从单个「名称|URL」合并框改为「名称」+「URL」两个独立框（名称留空自动取域名）
- 自定义规则源保存后页面不回显——刷新后输入框空白误以为没保存，现从 sources.list 读取并回填到对应输入框
- 规则源管理 UX 重构：每个源（预设+自定义）前加启用复选框（勾选即生效，无需保存），自定义源每行独立「保存」按钮，去掉全局「保存规则源」按钮；启用状态存 preset_flags / customN，停用的源在 sources.list 里注释掉（更新脚本自动跳过）
- 空自定义源行勾选无提示——现勾选空行会弹提示并回退；填了地址后直接勾选可一步完成保存+启用（custom_toggle）
- 规则源管理 v2（彻底改造）：自定义源「保存」改为真实下载并数规则条数（≥50 通过，失败保留输入内容+行内显示原因并持久化）；所有源操作改为 fetch + JSON 无整页刷新；未验证的源无法勾选启用，杜绝假启用；`adblock_rebuild_sources.sh` 只把「启用=1 且 验证=OK」的自定义源写入 sources.list
- 规则源 UI 补全：4 个预设源也显示启用状态（勾选即时更新文字）；自定义源每行加红色「删除」按钮（原来只能清空 URL 点保存才能删）
- AGH 只监听 IPv4 导致 IPv6 客户端绕过去广告——`bind_hosts` 增加 `"::"`（YAML 中必须加引号，裸 `::` 会被解析成 map）
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

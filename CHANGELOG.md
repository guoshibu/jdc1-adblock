# Changelog

本项目的所有重要改动记录。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [1.2.0] - 2026-11-27

### 新增：离线下载（aria2）
- 恢复官改固件被 whiteout 屏蔽的原厂 `aria2 1.34.0`（`/sbin/downloader`、`rpcwrapper`、`init.d`、`downloader.conf`），从 `/rom` 只读分区复制到 overlay 上层，重启持久
- `download_web.html` 下载管理页：工具栏统计、任务列表 6 列排序、状态筛选 tab、文件名搜索、ETA 剩余时间、添加时间、批量勾选操作、网页弹窗二次确认
- 新建任务弹窗：多行链接 / magnet / .torrent 上传，保存位置实时读 `aria2.getGlobalOption` + 动态磁盘枚举（内置盘 + U 盘）
- 「下载到本地」：浏览器 HTTP 直传，绕开 Samba 账号问题；nginx sendfile + Range 断点续传
- 操作全量：暂停/继续/置顶/重试/删除/详情/清除，区分「只清记录」与「连文件删」

### 新增：浏览器文件管理器
- `filemgr.html` + `filemgr.cgi`：内置盘/U盘根目录枚举、面包屑、排序、新建文件夹、重命名、删除、文本文件在线编辑
- `fm_upload.lua`（nginx `content_by_lua_file`）：4MB 二进制分片 POST 追加写盘，支持任意大文件、进度条、覆盖确认。实测 5MB 跨两片 MD5 一致
- 统一下载链路 `file_dl.cgi`：`?action=roots` 根枚举 + `?path=` realpath 白名单校验后 302 到 `/dl-mnt` 静态直传，下载页与文件管理器复用
- `install.sh` 新增 [5/6] 步骤：下载器恢复、页面/API 部署、nginx `/fm_upload` location、`/dl-mnt` 符号链接、开机自启，全部幂等

### 安全
- 所有写操作强制 POST（防 CSRF：GET/图片标签不能删改或创建文件）
- 后端 realpath 白名单校验，只允许内置盘 `/mnt/mmcblk0p4` 与运行时枚举的 `/mnt/sdX`，防 `../` 与符号链接逃逸
- nginx 正则 location 限制 `/dl-mnt/` 只放行 `mmcblk0p4/|sdX/`，防止静态链接绕过 CGI 白名单读其他分区
- 上传目标校验父目录、拒绝覆盖目录、拒绝写存储根

### 修复（三轮代码审查累计 8 项）
- `jesc()` 多行文本转义失效导致 JSON 非法、编辑器打不开多行文件
- `write` 用 GET query 传内容，超几 KB 触发 nginx 414；改 POST body 流式写盘
- 命令替换吃掉尾部换行；read 改 awk 直读文件 + 尾换行探测补齐（8 种换行/特殊字符场景全部保真）
- 目录删除用 `rm -f` 永远失败；改 `rmdir` 且非空给明确提示
- 0 字节文件上传不发任何请求、不创建文件
- 弹窗 CSS 漏写 `display:none/.show` 导致文件管理卡片点击无反应
- `fmModal` 与排序数组残留 `up` 列导致 `Cannot set properties of null` 误报为 RPC 失败
- 编辑/下载按钮对二进制文件、目录无意义：按文本白名单过滤，目录不再显示下载

### 文档与工程
- README 补齐离线下载/文件管理功能、目录结构、文件清单、端口 `6800`、访问入口
- `build_deploy.py` FILES 清单加入 7 个新文件；`install.sh` 步骤扩为 6 步
- 源目录 `02_脚本/` → 发布快照 `jdc1-adblock/scripts/` 已同步（统一 LF 行尾）
- 已在设备实测 `install.sh` 全流程通过（幂等、部署前后 md5 一致、nginx -t OK、功能 HTTP 200）

### 已知限制
- U 盘 exFAT 分区本机不支持（固件无 exfat 驱动），需格式化为 NTFS/FAT32；分区识别本身正常
- 文本编辑上限 1MB；不支持目录打包下载（tar 可以但 gzip 压缩实测 32MB 需 38 秒，性价比低）
- RPC token 默认 `jdc2026`，部署后建议修改

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

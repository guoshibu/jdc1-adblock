#!/bin/sh
# ============================================================
# 官改 JDCOS r6636 — AdGuard Home 部署脚本（主力去广告）
#
# 功能：
#   1. 从多镜像源下载 AdGuard Home（mipsle_softfloat）到 eMMC
#   2. 预置配置（DNS 监听 5353，与 dnsmasq 的 53 共存）
#   3. 生成启动/停止脚本 + 开机自启
#   4. 让 dnsmasq 的上游指向 AdGuard(127.0.0.1#5353)
#
# 架构（不抢 53 端口）：
#   客户端 → dnsmasq(53, 保留 DHCP/本地解析) → AdGuard(5353, 过滤) → 上游
#
# 用法：
#   sh /usr/bin/adguard_install.sh install    # 下载+安装+启动
#   sh /usr/bin/adguard_install.sh start      # 启动
#   sh /usr/bin/adguard_install.sh stop       # 停止
#   sh /usr/bin/adguard_install.sh status     # 查看状态
#   sh /usr/bin/adguard_install.sh uninstall  # 卸载（保留数据）
# ============================================================

AGH_VER="v0.107.80"                       # AdGuard Home 版本
AGH_BIN="AdGuardHome_linux_mipsle_softfloat.tar.gz"

# 多镜像下载源（按顺序尝试）
MIRRORS="
https://ghfast.top/https://github.com/AdguardTeam/AdGuardHome/releases/download/${AGH_VER}/${AGH_BIN}
https://gh-proxy.com/https://github.com/AdguardTeam/AdGuardHome/releases/download/${AGH_VER}/${AGH_BIN}
https://github.com/AdguardTeam/AdGuardHome/releases/download/${AGH_VER}/${AGH_BIN}
"

# 安装目录（优先 eMMC，探测不到则退化到 /tmp）
AGH_HOME=""
AGH_DIR="/tmp/adguard"

# 预置配置
AGH_CONF_DIR=""     # 运行时填充
AGH_DNS_PORT=5353
AGH_WEB_PORT=3000

log() { echo "[adguard] $*"; logger -t adguard "$*"; }

# --- 探测 eMMC 挂载点 ---
detect_storage() {
    # 候选挂载点：官改 /opt、Padavan 遗留 /media/JDC-DATA、通用 /media
    for p in /opt /media/JDC-DATA /media /mnt; do
        if [ -d "$p" ] && [ -w "$p" ]; then
            # 排除 tmpfs/只读
            if mount | grep -q "on $p "; then
                AGH_HOME="$p/adguard"
                AGH_CONF_DIR="$p/adguard"
                log "使用存储目录: $AGH_HOME"
                return 0
            fi
        fi
    done
    # 都不可用则退回 /tmp（重启丢失，仅临时）
    AGH_HOME="/tmp/adguard"
    AGH_CONF_DIR="/tmp/adguard"
    log "警告：未找到可写持久存储，临时用 /tmp/adguard（重启会丢）"
    return 0
}

# --- 下载 ---
download_agh() {
    detect_storage
    mkdir -p "$AGH_HOME/bin"
    local tmp="$AGH_HOME/agh.tar.gz"

    if [ -x "$AGH_HOME/bin/AdGuardHome" ]; then
        log "AdGuard Home 已存在，跳过下载"
        return 0
    fi

    for mirror in $MIRRORS; do
        log "尝试下载: $mirror"
        if curl -sSL --connect-timeout 15 --max-time 300 -o "$tmp" "$mirror" 2>/dev/null; then
            if [ -s "$tmp" ] && tar -tzf "$tmp" >/dev/null 2>&1; then
                log "下载成功，解压中..."
                tar -xzf "$tmp" -C "$AGH_HOME/bin" 2>/dev/null
                # 解压后目录结构：AdGuardHome/AdGuardHome
                if [ -x "$AGH_HOME/bin/AdGuardHome/AdGuardHome" ]; then
                    mv "$AGH_HOME/bin/AdGuardHome/AdGuardHome" "$AGH_HOME/bin/AdGuardHome"
                fi
                chmod 755 "$AGH_HOME/bin/AdGuardHome" 2>/dev/null
                rm -f "$tmp"
                log "AdGuard Home 安装完成"
                return 0
            fi
        fi
        log "该镜像失败，尝试下一个..."
        rm -f "$tmp"
    done

    log "所有下载源均失败"
    return 1
}

# --- 预置配置（省掉引导页）---
write_config() {
    detect_storage
    mkdir -p "$AGH_CONF_DIR"

    # 若已有配置则跳过
    if [ -f "$AGH_CONF_DIR/AdGuardHome.yaml" ]; then
        log "检测到已有配置，跳过预置"
        return 0
    fi

    log "写入预置配置"
    cat > "$AGH_CONF_DIR/AdGuardHome.yaml" << CONF_EOF
http:
  address: 0.0.0.0:${AGH_WEB_PORT}
  session_ttl: 720h
users:
  - name: admin
    # ⚠️ 下面是 AGH 默认密码 password123! 的 bcrypt 哈希（公开默认值，非个人密码）
    #    首次登录 Web 界面后请立即修改密码！
    password: \$2y\$05\$CearHYVdSs8xDZxM5HvERuiRzB4NcooBg0xRJ7ZwaukyLIOd1XIQ2
dns:
  bind_hosts:
    - 0.0.0.0
  port: ${AGH_DNS_PORT}
  protection_enabled: true
  filtering_enabled: true
  upstream_dns:
    - 223.5.5.5
    - 119.29.29.29
  bootstrap_dns:
    - 223.5.5.5
  ratelimit: 0
  blocking_mode: default
  edns_cs_enabled: false
  querylog_enabled: true
  querylog_interval: 720h
filters:
  - enabled: true
    url: https://gcore.jsdelivr.net/gh/privacy-protection-tools/anti-AD@master/anti-ad-easylist.txt
    name: anti-AD
    id: 1
  - enabled: true
    url: https://gcore.jsdelivr.net/gh/AdguardTeam/AdguardFilters@master/ChineseFilter/sections/adservers.txt
    name: AdGuard 中文过滤
    id: 2
whitelist_filters: []
user_rules: []
dhcp:
  enabled: false
  interface_name: ""
log_file: ""
verbose: false
schema_version: 20
CONF_EOF
    chmod 644 "$AGH_CONF_DIR/AdGuardHome.yaml"
    log "预置配置完成（DNS=${AGH_DNS_PORT}, Web=${AGH_WEB_PORT}）"
}

# --- 启动 ---
start_agh() {
    detect_storage
    if [ ! -x "$AGH_HOME/bin/AdGuardHome" ]; then
        log "AdGuard Home 未安装，请先 install"
        return 1
    fi
    write_config

    if pidof AdGuardHome >/dev/null 2>&1; then
        log "AdGuard Home 已在运行"
        return 0
    fi

    log "启动 AdGuard Home..."
    "$AGH_HOME/bin/AdGuardHome" \
        --config "$AGH_CONF_DIR/AdGuardHome.yaml" \
        --work-dir "$AGH_CONF_DIR" \
        >/dev/null 2>&1 &
    sleep 2
    if pidof AdGuardHome >/dev/null 2>&1; then
        log "启动成功（DNS:${AGH_DNS_PORT} Web:${AGH_WEB_PORT}）"
        # 让 dnsmasq 上游指向 AdGuard
        setup_dnsmasq_upstream
        return 0
    else
        log "启动失败"
        return 1
    fi
}

# --- 停止 ---
stop_agh() {
    log "停止 AdGuard Home..."
    # 用 pidof 按进程名精确匹配（pgrep -f 会误匹配 shell 自身，busybox 无 pkill）
    kill $(pidof AdGuardHome) 2>/dev/null
    sleep 4
    # 若还没退（AGH 优雅退出较慢），强制杀
    kill -9 $(pidof AdGuardHome) 2>/dev/null
    # 持久化停用状态（重启后不再自动启动）
    mkdir -p /etc/adblock
    touch /etc/adblock/agh_disabled
    # 恢复 dnsmasq 原始上游
    restore_dnsmasq_upstream
    log "已停止"
}

# --- 让 dnsmasq 上游指向 AdGuard ---
setup_dnsmasq_upstream() {
    local f="/tmp/dnsmasq.d/adguard_upstream.conf"
    mkdir -p /tmp/dnsmasq.d
    echo "server=127.0.0.1#${AGH_DNS_PORT}" > "$f"
    echo "no-resolv" > /tmp/dnsmasq.d/adguard_noresolv.conf
    /etc/init.d/dnsmasq restart >/dev/null 2>&1
    log "dnsmasq 上游已指向 AdGuard(127.0.0.1#${AGH_DNS_PORT})"
}

restore_dnsmasq_upstream() {
    rm -f /tmp/dnsmasq.d/adguard_upstream.conf /tmp/dnsmasq.d/adguard_noresolv.conf
    /etc/init.d/dnsmasq restart >/dev/null 2>&1
    log "dnsmasq 上游已恢复"
}

# --- 状态 ---
status_agh() {
    if pidof AdGuardHome >/dev/null 2>&1; then
        echo "running"
    elif [ -x "$(detect_storage >/dev/null 2>&1; echo "$AGH_HOME")/bin/AdGuardHome" ]; then
        echo "installed"
    else
        echo "not_installed"
    fi
}

# --- 卸载 ---
uninstall_agh() {
    stop_agh
    detect_storage
    rm -rf "$AGH_HOME/bin"
    log "已卸载（配置数据保留在 $AGH_CONF_DIR）"
}

# --- 主逻辑 ---
case "${1:-}" in
    install)
        rm -f /etc/adblock/agh_disabled
        download_agh && write_config && start_agh
        ;;
    start)
        rm -f /etc/adblock/agh_disabled   # 手动启动 = 清除停用标志
        start_agh
        ;;
    autostart)
        # 开机自启：若上次是停用状态，则跳过（跟随上次状态）
        if [ -f /etc/adblock/agh_disabled ]; then
            log "上次为停用状态，跳过开机自启"
            exit 0
        fi
        start_agh
        ;;
    stop)
        stop_agh
        ;;
    restart)
        stop_agh; sleep 1; rm -f /etc/adblock/agh_disabled; start_agh
        ;;
    status)
        status_agh
        ;;
    uninstall)
        uninstall_agh
        ;;
    *)
        echo "用法: $0 {install|start|stop|autostart|restart|status|uninstall}"
        exit 1
        ;;
esac

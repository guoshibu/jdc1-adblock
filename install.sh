#!/bin/sh
# ============================================================
# JDC-1 官改固件 · 去广告与系统监控套件 — 一键部署脚本
#
# 用法：
#   1. 把整个项目目录（含本脚本、scripts/、web/、firmware/）上传到路由器任意位置
#   2. cd 到项目目录，执行：
#        sh install.sh
#   3. 按提示重启路由器
#
# 功能（幂等，可重复执行）：
#   1. 部署 scripts/*.cgi → /www/cgi-bin/，scripts/*.sh → /usr/bin/，sources.list → /etc/adblock/
#   2. 部署 web/main_patched.html → /www/PC/main.html（注入「去广告」菜单，自动备份原文件）
#   3. 写入开机自启（rc.local）与每日定时更新（cron），均幂等
#   4. 配置 nginx /AD 短链接（幂等，自动 nginx -t 校验）
#   5. 对每个部署文件做 md5 校验
# ============================================================

set -u

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$BASE_DIR/scripts"
WEB_DIR="$BASE_DIR/web"

log() { echo "[install] $*"; }
fail() { echo "[install][错误] $*"; }

# 颜色（可选，若终端不支持则退化为纯文本）
if [ -t 1 ]; then
    G='\033[32m'; R='\033[31m'; Y='\033[33m'; N='\033[0m'
else
    G=''; R=''; Y=''; N=''
fi

log "==============================================="
log "  JDC-1 去广告与系统监控套件 一键部署"
log "==============================================="

# --- 前置检查 ---
[ "$(id -u)" = "0" ] || { fail "请用 root 执行（ssh root@路由器IP）"; exit 1; }
[ -d "$SCRIPTS_DIR" ] || { fail "找不到 scripts/ 目录，请在项目根目录执行本脚本"; exit 1; }

# --- 1. 部署脚本文件 ---
log ""
log "--- [1/5] 部署脚本文件 ---"

# CGI → /www/cgi-bin/
mkdir -p /www/cgi-bin
for cgi in adblock.cgi adblock_status.cgi; do
    if [ -f "$SCRIPTS_DIR/$cgi" ]; then
        cp "$SCRIPTS_DIR/$cgi" "/www/cgi-bin/$cgi"
        chmod 755 "/www/cgi-bin/$cgi"
        log "  ${G}✓${N} $cgi → /www/cgi-bin/$cgi"
    else
        log "  ${Y}跳过${N} $cgi（不存在）"
    fi
done

# shell 脚本 → /usr/bin/
mkdir -p /usr/bin
for sh in proc_monitor.sh adblock_update.sh adguard_install.sh; do
    if [ -f "$SCRIPTS_DIR/$sh" ]; then
        cp "$SCRIPTS_DIR/$sh" "/usr/bin/$sh"
        chmod 755 "/usr/bin/$sh"
        log "  ${G}✓${N} $sh → /usr/bin/$sh"
    else
        log "  ${Y}跳过${N} $sh（不存在）"
    fi
done

# sources.list → /etc/adblock/
if [ -f "$SCRIPTS_DIR/sources.list" ]; then
    mkdir -p /etc/adblock
    cp "$SCRIPTS_DIR/sources.list" /etc/adblock/sources.list
    log "  ${G}✓${N} sources.list → /etc/adblock/sources.list"
fi

# --- 2. 部署菜单入口 ---
log ""
log "--- [2/5] 部署 Web 菜单入口 ---"
if [ -f "$WEB_DIR/main_patched.html" ]; then
    if [ -f /www/PC/main.html ]; then
        # 备份原文件（只备份一次）
        if [ ! -f /www/PC/main.html.orig ]; then
            cp /www/PC/main.html /www/PC/main.html.orig
            log "  ${G}✓${N} 原 main.html 已备份为 main.html.orig"
        fi
        cp "$WEB_DIR/main_patched.html" /www/PC/main.html
        log "  ${G}✓${N} main_patched.html → /www/PC/main.html（菜单已注入「去广告」）"
    else
        log "  ${Y}跳过${N} /www/PC/main.html 不存在（可能固件版本不同）"
    fi
else
    log "  ${Y}跳过${N} main_patched.html 不存在"
fi

# --- 3. 开机自启 + 定时更新（幂等 + 自愈）---
log ""
log "--- [3/5] 配置开机自启与定时更新 ---"

# 自愈式写入：精确匹配「正确行」，不存在则先删旧的相关行再插入正确行
# 这样既能避免重复（幂等），又能修正之前写错的旧配置（自愈）

# rc.local 自启
if [ -f /etc/rc.local ]; then
    # 三条自启命令（正确版）
    LINE_UPDATE='(sleep 60 && /usr/bin/adblock_update.sh >/dev/null 2>&1) &'
    LINE_AGH='(sleep 70 && /usr/bin/adguard_install.sh autostart >/dev/null 2>&1) &'
    LINE_PROC='(sleep 30 && /usr/bin/proc_monitor.sh >/dev/null 2>&1 &) &'

    ensure_line_rc() {
        local pattern="$1" correct="$2" label="$3"
        if grep -Fq "$correct" /etc/rc.local; then
            log "  ${Y}已存在${N} $label 自启"
            return
        fi
        # 删除可能存在的旧/错误版本（按关键词宽松删除，再补正确行）
        sed -i "/$(echo "$pattern" | sed 's#/#\\/#g')/d" /etc/rc.local
        # 插入正确行：有 exit 0 就在它前面插，否则追加到末尾
        if grep -q '^exit 0' /etc/rc.local; then
            sed -i '/^exit 0/i '"$correct" /etc/rc.local
        else
            echo "$correct" >> /etc/rc.local
        fi
        log "  ${G}✓${N} 已配置 $label 自启"
    }

    ensure_line_rc "adblock_update.sh" "$LINE_UPDATE" "adblock_update.sh"
    ensure_line_rc "adguard_install.sh" "$LINE_AGH" "adguard_install.sh autostart"
    ensure_line_rc "proc_monitor.sh" "$LINE_PROC" "proc_monitor.sh"
else
    fail "/etc/rc.local 不存在"
fi

# cron 每日更新（幂等 + 自愈）
CRONTAB="/etc/crontabs/root"
CRON_CORRECT="30 4 * * * /usr/bin/adblock_update.sh >/dev/null 2>&1"
mkdir -p /etc/crontabs
[ -f "$CRONTAB" ] || touch "$CRONTAB"
if grep -Fq "$CRON_CORRECT" "$CRONTAB"; then
    log "  ${Y}已存在${N} cron 每日更新规则"
else
    # 删除旧的 adblock_update 相关行，再追加正确行
    sed -i '/adblock_update.sh/d' "$CRONTAB"
    echo "$CRON_CORRECT" >> "$CRONTAB"
    log "  ${G}✓${N} 已配置 cron 每日 4:30 更新规则"
fi
/etc/init.d/cron restart 2>/dev/null && log "  ${G}✓${N} cron 已重启" || log "  ${Y}提示${N} cron 重启失败（可能未启用，不影响）"

# --- 4. nginx /AD 短链接（幂等 + 自愈）---
log ""
log "--- [4/5] 配置 /AD 短链接 ---"
NGINX_CONF="/etc/nginx/conf.d/jdc-web.conf"
if [ -f "$NGINX_CONF" ]; then
    if grep -Fq 'location ~* ^/AD$' "$NGINX_CONF" 2>/dev/null; then
        log "  ${Y}已存在${N} /AD 短链接配置"
    else
        # 先删除可能存在的旧格式 /AD（location = /AD），再插入正确格式
        sed -i '/location = \/AD/d' "$NGINX_CONF" 2>/dev/null
        # 在 location /cgi-bin 前插入（用 awk 实现，兼容 busybox）
        awk '
            /location \/cgi-bin/ && !done {
                print "\tlocation ~* ^/AD$ {"
                print "\t\treturn 302 /cgi-bin/adblock.cgi;"
                print "\t}"
                print ""
                done = 1
            }
            { print }
        ' "$NGINX_CONF" > /tmp/jdc-web.conf.new
        cp /tmp/jdc-web.conf.new "$NGINX_CONF"
        rm -f /tmp/jdc-web.conf.new
        log "  ${G}✓${N} /AD 短链接配置已插入"
    fi
    # nginx 语法校验 + reload
    if nginx -t 2>/tmp/nginx_test.err; then
        nginx -s reload 2>/dev/null
        log "  ${G}✓${N} nginx 配置校验通过并已重载"
    else
        fail "nginx 配置校验失败，请检查 $NGINX_CONF"
        cat /tmp/nginx_test.err 2>/dev/null | grep -v lua_code_cache
    fi
else
    log "  ${Y}跳过${N} $NGINX_CONF 不存在"
fi

# --- 5. md5 校验（列出已部署文件，供人工核对）---
log ""
log "--- [5/5] 部署完成，文件清单 ---"
log "已部署文件（可手动 md5sum 核对）："
for f in /www/cgi-bin/adblock.cgi /www/cgi-bin/adblock_status.cgi /usr/bin/proc_monitor.sh /usr/bin/adblock_update.sh /usr/bin/adguard_install.sh /etc/adblock/sources.list; do
    [ -f "$f" ] && log "  $(md5sum "$f" 2>/dev/null | cut -d' ' -f1)  $f"
done

# --- 收尾提示 ---
log ""
log "==============================================="
log "  ${G}部署完成！${N}"
log "==============================================="
log "下一步："
log "  1. 安装并启动 AdGuard Home："
log "       sh /usr/bin/adguard_install.sh install"
log "  2. 更新 dnsmasq 规则："
log "       sh /usr/bin/adblock_update.sh"
log "  3. 重启路由器使开机自启生效："
log "       reboot"
log ""
log "重启后访问：http://路由器IP/AD  （或 /cgi-bin/adblock.cgi）"
log "AGH 控制台：http://路由器IP:3000"
log ""
log "⚠️  AGH 默认密码 admin / password123!，首次登录后务必修改！"
log "==============================================="

exit 0

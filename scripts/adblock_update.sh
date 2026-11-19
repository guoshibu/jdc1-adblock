#!/bin/sh
# ============================================================
# 官改 JDCOS r6636 去广告 — dnsmasq 域名黑名单（多源多格式）
#
# 支持规则源格式（自动识别并统一转成 address=/域名/0.0.0.0）：
#   1. dnsmasq 原生  address=/域名/        （anti-AD 官方等）
#   2. AdBlock 语法  ||域名^$third-party   （anti-AD jsdelivr、AdGuard 等）
#   3. hosts 格式    0.0.0.0 域名           （StevenBlack 等）
#
# 配置：源列表存在 /etc/adblock/sources.list
#   每行一个源，格式：名称|URL
#   空行和 # 开头为注释
#
# 用法：
#   手动更新   sh /usr/bin/adblock_update.sh
#   停用       touch /etc/adblock/disabled
#   启用       rm -f /etc/adblock/disabled
#
# 实测结论（2026-11-18）：
#   - WISP 中继链路下，anti-ad.net 官方和 GitHub raw 极慢（25s 才 91KB）
#   - jsdelivr CDN 10s 下完 2MB，是唯一可用源
#   - anti-AD 的 easylist 现在是 AdGuard 语法（||域名^），必须转换
#   - address=/域名/0.0.0.0 明确写 IP 才能稳定拦截
# ============================================================

CONF_DIR="/tmp/dnsmasq.d"
CONF_FILE="$CONF_DIR/adblock.conf"
SRC_LIST="/etc/adblock/sources.list"
TMP_DL="/tmp/adblock.dl"
TMP_ALL="/tmp/adblock.all"
DISABLE_FLAG="/etc/adblock/disabled"

# 规则条数上限（防 dnsmasq 内存爆掉，官改 512MB 内存下 50000 条安全）
MAX_RULES=50000

log() { logger -t adblock "$@"; }

# --- 停用开关 ---
if [ -f "$DISABLE_FLAG" ]; then
    log "去广告已停用（存在 $DISABLE_FLAG）"
    rm -f "$CONF_FILE"
    /etc/init.d/dnsmasq restart >/dev/null 2>&1
    exit 0
fi

mkdir -p "$CONF_DIR"
: > "$TMP_ALL"

# --- 默认源列表（gcore 节点最快，实测 10s 下完 2MB）---
if [ ! -f "$SRC_LIST" ]; then
    log "未找到源列表 $SRC_LIST，创建默认源"
    mkdir -p /etc/adblock
    cat > "$SRC_LIST" << 'SRC_EOF'
# 去广告规则源列表：名称|URL
anti-AD(gcore)|https://gcore.jsdelivr.net/gh/privacy-protection-tools/anti-AD@master/anti-ad-easylist.txt
anti-AD(ghfast)|https://ghfast.top/https://raw.githubusercontent.com/privacy-protection-tools/anti-AD/master/anti-ad-easylist.txt
SRC_EOF
fi

# --- 逐个源下载并转换 ---
while IFS='|' read -r name url; do
    case "$name" in ""|\#*) continue;; esac
    [ -z "$url" ] && continue

    log "下载源 [$name]"
    curl -sS --connect-timeout 15 --max-time 90 -o "$TMP_DL" "$url" 2>/dev/null
    if [ $? -ne 0 ] || [ ! -s "$TMP_DL" ]; then
        log "源 [$name] 下载失败，跳过"
        continue
    fi

    # 转换三种格式 → address=/域名/0.0.0.0
    # 1. dnsmasq 原生 address=/域名/（可能带 IP 或不带）
    grep -E '^address=/[^/]+/' "$TMP_DL" | sed -E 's#^address=/([^/]+)/.*#address=/\1/0.0.0.0#'
    # 2. AdBlock 语法 ||域名^（排除白名单 @@ 和通配符 *）
    grep -E '^\|\|' "$TMP_DL" | grep -v '^@@' | sed -E 's#^\|\|([^/^*^]+)\^.*$#address=/\1/0.0.0.0#'
    # 3. hosts 格式 0.0.0.0 域名 / 127.0.0.1 域名
    grep -E '^(0\.0\.0\.0|127\.0\.0\.1)[[:space:]]+' "$TMP_DL" | awk '{print "address=/"$2"/0.0.0.0"}'
done < "$SRC_LIST" > "$TMP_ALL"

# --- 去重 + 限流 + 统计 ---
sort -u "$TMP_ALL" | head -n "$MAX_RULES" > "$CONF_FILE"
VALID=$(wc -l < "$CONF_FILE")

if [ "$VALID" -lt 1000 ]; then
    log "有效规则仅 $VALID 条，判定异常，不写入"
    rm -f "$CONF_FILE" "$TMP_DL" "$TMP_ALL"
    exit 1
fi

log "去广告规则已更新: $VALID 条"
echo "$VALID" > /tmp/adblock.count
date "+%Y-%m-%d %H:%M:%S" > /tmp/adblock.time

# --- 重载 dnsmasq ---
/etc/init.d/dnsmasq restart >/dev/null 2>&1 && log "dnsmasq 已重载" || log "dnsmasq 重载失败"

rm -f "$TMP_DL" "$TMP_ALL"
exit 0

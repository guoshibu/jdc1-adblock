#!/bin/sh
# ============================================================
# 去广告管理页 — 实时状态 JSON 接口（供前端 JS 轮询）
# 访问：http://<路由器IP>/cgi-bin/adblock_status.cgi
# 返回：纯 JSON，含 CPU/内存/负载/运行时间/AGH状态/AGH拦截数/dnsmasq状态
# ============================================================

DISABLE_FLAG="/etc/adblock/disabled"
COUNT_FILE="/tmp/adblock.count"
TIME_FILE="/tmp/adblock.time"

# --- 数值读取（统一，避免空值导致 JSON 语法错误）---
get_int() { awk -v k="$1" '$1==k{print $2; exit}' /proc/meminfo 2>/dev/null || echo 0; }

# --- CPU 占用（读后台守护缓存，秒回）---
CPU_PCT=$(cat /tmp/cpu_cache 2>/dev/null || echo "0")
[ -z "$CPU_PCT" ] && CPU_PCT=0

# --- 运行时间 ---
UPTIME_S=$(awk '{print $1}' /proc/uptime 2>/dev/null | cut -d. -f1)
[ -z "$UPTIME_S" ] && UPTIME_S=0

# --- 负载（1/5/15 分钟）---
LOAD1=$(cut -d' ' -f1 /proc/loadavg 2>/dev/null)
LOAD5=$(cut -d' ' -f2 /proc/loadavg 2>/dev/null)
LOAD15=$(cut -d' ' -f3 /proc/loadavg 2>/dev/null)
[ -z "$LOAD1" ] && LOAD1="0.00"
[ -z "$LOAD5" ] && LOAD5="0.00"
[ -z "$LOAD15" ] && LOAD15="0.00"

# --- 内存 ---
MEM_TOTAL=$(get_int MemTotal:)
MEM_AVAIL=$(get_int MemAvailable:)
MEM_USED=$((MEM_TOTAL - MEM_AVAIL))
MEM_PCT=0
[ "$MEM_TOTAL" -gt 0 ] 2>/dev/null && MEM_PCT=$((MEM_USED * 100 / MEM_TOTAL))

# --- swap（虚拟内存）---
SWAP_TOTAL=$(get_int SwapTotal:)
SWAP_FREE=$(get_int SwapFree:)
SWAP_USED=$((SWAP_TOTAL - SWAP_FREE))

# --- CPU 型号 + 频率（MT7621 固定主频，无动态 cpufreq）---
CPU_MODEL=$(grep -m1 "system type" /proc/cpuinfo 2>/dev/null | awk -F: '{gsub(/^[ \t]+/,"",$2); print $2}')
[ -z "$CPU_MODEL" ] && CPU_MODEL="MediaTek MT7621"
CPU_FREQ="${CPU_MODEL} · 880MHz"

# --- dnsmasq 去广告状态 ---
ADB_ENABLED="1"
[ -f "$DISABLE_FLAG" ] && ADB_ENABLED="0"
ADB_COUNT=$(cat "$COUNT_FILE" 2>/dev/null || echo "0")
ADB_TIME=$(cat "$TIME_FILE" 2>/dev/null || echo "从未更新")

# --- AdGuard Home 状态 + 今日拦截数 ---
AGH_RUNNING="0"
AGH_BLOCKED="0"
pgrep -f "AdGuardHome" >/dev/null 2>&1 && AGH_RUNNING="1"

if [ "$AGH_RUNNING" = "1" ]; then
    AGH_COOKIE="/tmp/agh_status_cookie.txt"
    AGH_BLOCKED_CACHE="/tmp/agh_blocked_cache"
    AGH_BLOCKED_TS="/tmp/agh_blocked_ts"

    # 拦截数缓存 30 秒，避免每次轮询都拉 querylog（太重）
    NOW=$(date +%s)
    CACHE_OK="0"
    [ -f "$AGH_BLOCKED_TS" ] && [ -f "$AGH_BLOCKED_CACHE" ] && {
        LAST=$(cat "$AGH_BLOCKED_TS" 2>/dev/null || echo 0)
        [ $((NOW - LAST)) -lt 30 ] && CACHE_OK="1"
    }

    if [ "$CACHE_OK" = "0" ]; then
        # 登录拿 cookie（cookie 文件若 10 分钟内有效则复用）
        if [ ! -f "$AGH_COOKIE" ] || [ $((NOW - $(stat -c %Y "$AGH_COOKIE" 2>/dev/null || echo 0))) -gt 600 ]; then
            curl -s --connect-timeout 3 --max-time 5 -c "$AGH_COOKIE" \
                -X POST http://127.0.0.1:3000/control/login \
                -H "Content-Type: application/json" \
                -d '{"name":"admin","password":"password123!"}' >/dev/null 2>&1
        fi
        # 读 querylog，统计 reason 含 Filtered 的条数
        AGH_BLOCKED=$(curl -s --connect-timeout 3 --max-time 8 -b "$AGH_COOKIE" \
            "http://127.0.0.1:3000/control/querylog?limit=2000" 2>/dev/null | \
            grep -o '"reason":"Filtered[^"]*"' | wc -l)
        [ -z "$AGH_BLOCKED" ] && AGH_BLOCKED="0"
        echo "$AGH_BLOCKED" > "$AGH_BLOCKED_CACHE"
        echo "$NOW" > "$AGH_BLOCKED_TS"
    else
        AGH_BLOCKED=$(cat "$AGH_BLOCKED_CACHE" 2>/dev/null || echo "0")
    fi
fi

# --- 进程占用（读后台常驻守护的缓存，秒回，不实时采集）---
PROCS=$(cat /tmp/procs_cache.json 2>/dev/null)
[ -z "$PROCS" ] && PROCS="[]"

# --- 输出 JSON ---
echo "Content-Type: application/json; charset=utf-8"
echo "Cache-Control: no-cache"
echo ""

cat <<JSON
{
  "cpu": {"pct": ${CPU_PCT}, "freq": "${CPU_FREQ}"},
  "mem": {"total": ${MEM_TOTAL}, "used": ${MEM_USED}, "avail": ${MEM_AVAIL}, "pct": ${MEM_PCT}, "swap_total": ${SWAP_TOTAL}, "swap_used": ${SWAP_USED}},
  "load": {"l1": "${LOAD1}", "l5": "${LOAD5}", "l15": "${LOAD15}"},
  "uptime": ${UPTIME_S},
  "adblock": {"enabled": ${ADB_ENABLED}, "count": ${ADB_COUNT}, "time": "${ADB_TIME}"},
  "agh": {"running": ${AGH_RUNNING}, "blocked": ${AGH_BLOCKED}},
  "procs": ${PROCS}
}
JSON

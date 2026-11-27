#!/bin/sh
# ============================================================
# 去广告管理页 CGI — 官改 r6636
# 访问：http://<路由器IP>/cgi-bin/adblock.cgi
# 功能：
#   1. dnsmasq 去广告（兜底）：开关、选源、自定义源、看状态
#   2. AdGuard Home（主力）：下载源选择、安装、启停、跳转
#   3. 系统状态：CPU / 内存 / 负载 / 运行时间
# ============================================================

SRC_LIST="/etc/adblock/sources.list"
DISABLE_FLAG="/etc/adblock/disabled"
COUNT_FILE="/tmp/adblock.count"
TIME_FILE="/tmp/adblock.time"

AGH_SCRIPT="/usr/bin/adguard_install.sh"
AGH_MIRROR_FILE="/etc/adblock/adguard_mirror"

# 内置预设源（名称|URL）—— 已对齐实测最快的 gcore CDN 镜像
PRESET1_NAME="anti-AD(gcore)"
PRESET1_URL="https://gcore.jsdelivr.net/gh/privacy-protection-tools/anti-AD@master/anti-ad-easylist.txt"
PRESET2_NAME="anti-AD(ghfast)"
PRESET2_URL="https://ghfast.top/https://raw.githubusercontent.com/privacy-protection-tools/anti-AD/master/anti-ad-easylist.txt"
PRESET3_NAME="AdGuard中文过滤(gcore)"
PRESET3_URL="https://gcore.jsdelivr.net/gh/AdguardTeam/AdguardFilters@master/ChineseFilter/sections/adservers.txt"
PRESET4_NAME="AdGuard中文(gcore备用)"
PRESET4_URL="https://ghfast.top/https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/ChineseFilter/sections/adservers.txt"

# --- HTML 转义 ---
esc() { echo "$1" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g'; }

# --- URL 解码（通用 %XX，逐字节还原 UTF-8）---
urldecode() {
    printf '%b' "$(printf '%s' "$1" | sed 's/+/ /g; s/%\([0-9A-Fa-f][0-9A-Fa-f]\)/\\x\1/g')"
}

# --- JSON 输出辅助：前端 fetch 带 format=json 时返回 JSON，普通表单仍 302 ---
json_esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr -d '\n'; }
finish() {
    if [ "$FMT_JSON" = "1" ]; then
        echo "Content-Type: application/json; charset=utf-8"
        echo ""
        echo "{\"ok\":$JSON_OK,\"msg\":\"$(json_esc "$JSON_MSG")\",\"rules\":${JSON_RULES:-0}}"
    else
        echo "Status: 302 Found"
        echo "Location: /cgi-bin/adblock.cgi"
        echo ""
    fi
    exit 0
}
fail_json() { JSON_OK=false; JSON_MSG="$1"; JSON_RULES=0; finish; }

# 取 POST 参数（兼容首参数与 & 分隔）
get_param() {
    _v=$(printf '%s' "$POST_DATA" | sed -n "s/.*[?&]$1=\\([^&]*\\).*/\\1/p")
    [ -z "$_v" ] && _v=$(printf '%s' "$POST_DATA" | sed -n "s/^$1=\\([^&]*\\).*/\\1/p")
    printf '%s' "$_v"
}

# 真实下载并校验自定义源，成功写入 customN 第 4 列 OK:条数
# 参数：$1=slot $2=name $3=url $4=on(可选；不传则保留原启用位)
verify_slot() {
    _slot=$1; _name=$2; _url=$3; _on=$4
    case "$_slot" in 1|2|3) ;; *) fail_json "无效槽位";; esac
    _cf="/etc/adblock/custom$_slot"
    # 验证失败也落盘 FAIL 状态，让行内提示刷新后仍可见；失败即停用，杜绝假启用
    verify_fail() {
        printf '%s|%s|0|FAIL:%s\n' "$_name" "$_url" "$1" > "$_cf"
        sh /usr/bin/adblock_rebuild_sources.sh >/dev/null 2>&1
        JSON_OK=false; JSON_MSG="$1"; JSON_RULES=0; finish
    }
    if [ -z "$_name" ]; then
        _name=$(printf '%s' "$_url" | sed -n 's#^[a-zA-Z]*://\([^/]*\)/.*#\1#p' | sed 's/^.*@//')
        [ -z "$_name" ] && _name="自定义源$_slot"
    fi
    printf '%s' "$_url" | grep -qE '^https?://' || verify_fail "格式错误：需 http(s):// 开头"
    curl -sS --connect-timeout 10 --max-time 25 -o /tmp/adblock.verify.dl "$_url" 2>/dev/null || verify_fail "连接失败/超时"
    [ -s /tmp/adblock.verify.dl ] || verify_fail "下载内容为空"
    # 数有效规则：与 adblock_update.sh 完全相同的三种格式转换 + 整行去重
    _cnt=$(
      {
        grep -E '^address=/[^/]+/' /tmp/adblock.verify.dl
        grep -E '^\|\|' /tmp/adblock.verify.dl | grep -v '^@@' | sed -E 's#^\|\|([^/^*^]+)\^.*#address=/\1/0.0.0.0#'
        grep -E '^(0\.0\.0\.0|127\.0\.0\.1)[[:space:]]+' /tmp/adblock.verify.dl | awk '{print "address=/"$2"/0.0.0.0"}'
      } | sort -u | wc -l
    )
    rm -f /tmp/adblock.verify.dl
    # 单源阈值 50：300 条小规则源合法；1000 是整体规则库保护线，不适用单源
    [ "$_cnt" -ge 50 ] || verify_fail "有效规则仅 $_cnt 条（<50），判定无效"
    if [ -n "$_on" ]; then
        [ "$_on" = "1" ] && _f=1 || _f=0
    else
        _f=$(awk -F'|' '{print $3}' "$_cf" 2>/dev/null)
        [ "$_f" != "1" ] && _f=0
    fi
    printf '%s|%s|%s|OK:%s\n' "$_name" "$_url" "$_f" "$_cnt" > "$_cf"
    sh /usr/bin/adblock_rebuild_sources.sh >/dev/null 2>&1
    /usr/bin/adblock_update.sh >/dev/null 2>&1 &
    JSON_OK=true; JSON_MSG="已验证 $_cnt 条规则"; JSON_RULES=$_cnt
}

# --- 处理 POST ---
if [ "$REQUEST_METHOD" = "POST" ]; then
    read -r POST_DATA
    ACTION=$(printf '%s' "$POST_DATA" | sed -n 's/.*[?&]action=\([^&]*\).*/\1/p')
    [ -z "$ACTION" ] && ACTION=$(printf '%s' "$POST_DATA" | sed -n 's/^action=\([^&]*\).*/\1/p')
    printf '%s' "$POST_DATA" | grep -q 'format=json' && FMT_JSON=1 || FMT_JSON=0
    JSON_OK=false; JSON_MSG=""; JSON_RULES=0

    case "$ACTION" in
        enable)
            rm -f "$DISABLE_FLAG"
            /usr/bin/adblock_update.sh >/dev/null 2>&1 &
            JSON_OK=true; JSON_MSG="已启用"
            ;;
        disable)
            touch "$DISABLE_FLAG"
            /usr/bin/adblock_update.sh >/dev/null 2>&1 &
            JSON_OK=true; JSON_MSG="已停用"
            ;;
        update)
            /usr/bin/adblock_update.sh >/dev/null 2>&1 &
            JSON_OK=true; JSON_MSG="已触发更新"
            ;;
        verify_custom)
            SLOT=$(get_param slot)
            CNAME=$(get_param cname); CNAME=$(urldecode "$CNAME")
            CURL=$(get_param curl); CURL=$(urldecode "$CURL")
            ON=$(get_param on)
            verify_slot "$SLOT" "$CNAME" "$CURL" "$ON"
            ;;
        save_custom)
            SLOT=$(get_param slot)
            CNAME=$(get_param cname); CNAME=$(urldecode "$CNAME")
            CURL=$(get_param curl); CURL=$(urldecode "$CURL")
            case "$SLOT" in 1|2|3) ;; *) fail_json "无效槽位";; esac
            if [ -z "$CURL" ]; then
                rm -f "/etc/adblock/custom$SLOT"
                sh /usr/bin/adblock_rebuild_sources.sh >/dev/null 2>&1
                /usr/bin/adblock_update.sh >/dev/null 2>&1 &
                JSON_OK=true; JSON_MSG="已清空槽位 $SLOT"; JSON_RULES=0
            else
                verify_slot "$SLOT" "$CNAME" "$CURL" ""
            fi
            ;;
        custom_toggle)
            # 兼容旧调用：勾选 = 真实验证 + 启用，一步到位
            SLOT=$(get_param slot)
            CNAME=$(get_param cname); CNAME=$(urldecode "$CNAME")
            CURL=$(get_param curl); CURL=$(urldecode "$CURL")
            ONOFF=$(get_param on)
            verify_slot "$SLOT" "$CNAME" "$CURL" "$ONOFF"
            ;;
        toggle_src)
            # line 1..4=预设 / 5..7=自定义；自定义必须已验证 OK 才能启用
            LINE=$(get_param line)
            ONOFF=$(get_param on)
            [ -z "$LINE" ] && fail_json "缺少 line 参数"
            [ "$ONOFF" = "1" ] && NEWFLAG=1 || NEWFLAG=0
            if [ "$LINE" -ge 1 ] && [ "$LINE" -le 4 ]; then
                PF="/etc/adblock/preset_flags"
                [ -f "$PF" ] || printf '1\n1\n1\n1\n' > "$PF"
                awk -v n="$LINE" -v f="$NEWFLAG" 'NR==n{print f;next}{print}' "$PF" > "$PF.tmp"
                while [ "$(wc -l < "$PF.tmp")" -lt 4 ]; do echo 1 >> "$PF.tmp"; done
                mv "$PF.tmp" "$PF"
                JSON_OK=true; JSON_MSG="已切换预设源 $LINE"
            else
                SLOT=$((LINE-4))
                case "$SLOT" in 1|2|3) ;; *) fail_json "无效槽位";; esac
                CF="/etc/adblock/custom$SLOT"
                [ -f "$CF" ] || fail_json "该槽位尚未保存规则"
                if [ "$NEWFLAG" = "1" ]; then
                    V=$(awk -F'|' '{print $4}' "$CF")
                    case "$V" in
                        OK:*) ;;
                        *) fail_json "该源未验证或验证失败，请先点「保存」验证" ;;
                    esac
                fi
                NAME=$(awk -F'|' '{print $1}' "$CF")
                URL=$(awk -F'|' '{print $2}' "$CF")
                V=$(awk -F'|' '{print $4}' "$CF")
                printf '%s|%s|%s|%s\n' "$NAME" "$URL" "$NEWFLAG" "$V" > "$CF"
                if [ "$NEWFLAG" = "1" ]; then
                    JSON_OK=true; JSON_MSG="已启用槽位 $SLOT"
                else
                    JSON_OK=true; JSON_MSG="已停用槽位 $SLOT"
                fi
            fi
            sh /usr/bin/adblock_rebuild_sources.sh >/dev/null 2>&1
            /usr/bin/adblock_update.sh >/dev/null 2>&1 &
            ;;
        save_mirror)
            MIRROR=$(get_param agh_mirror)
            if [ "$MIRROR" = "custom" ]; then
                MIRROR=$(get_param agh_mirror_custom)
                MIRROR=$(printf '%s' "$MIRROR" | sed 's/%2F/\//g; s/%3A/:/g; s/%3D/=/g; s/%2E/./g; s/+/ /g')
            fi
            [ -n "$MIRROR" ] && [ "$MIRROR" != "custom" ] && printf '%s\n' "$MIRROR" > "$AGH_MIRROR_FILE"
            JSON_OK=true; JSON_MSG="已保存下载源"
            ;;
        agh_install)
            /usr/bin/adguard_install.sh install >/dev/null 2>&1 &
            JSON_OK=true; JSON_MSG="已提交安装"
            ;;
        agh_start)
            /usr/bin/adguard_install.sh start >/dev/null 2>&1 &
            JSON_OK=true; JSON_MSG="已提交启动"
            ;;
        agh_stop)
            /usr/bin/adguard_install.sh stop >/dev/null 2>&1 &
            JSON_OK=true; JSON_MSG="已提交停止"
            ;;
        *) fail_json "未知操作 $ACTION" ;;
    esac
    finish
fi

# ============================================================
# 读取状态（GET 显示）
# ============================================================

# --- dnsmasq 去广告状态 ---
ENABLED="已启用"; EN_CLASS="on"
[ -f "$DISABLE_FLAG" ] && ENABLED="已停用" && EN_CLASS="off"
COUNT=$(cat "$COUNT_FILE" 2>/dev/null || echo "0")
TIME=$(cat "$TIME_FILE" 2>/dev/null || echo "从未更新")

CURRENT=""
[ -f "$SRC_LIST" ] && CURRENT=$(grep -v '^#' "$SRC_LIST" | grep -v '^$')

# 预设源启用状态来自 /etc/adblock/preset_flags（4 行 0/1，缺省 1）
PF="/etc/adblock/preset_flags"
CHK1=""; CHK2=""; CHK3=""; CHK4=""
_i=1
for _v in 1 2 3 4; do
    _f=$(sed -n "${_i}p" "$PF" 2>/dev/null)
    [ -z "$_f" ] && _f=1
    [ "$_f" = "1" ] && eval "CHK$_i=checked"
    eval "PST$_i=\"\"; PSTC$_i=\"\""
    if [ "$_f" = "1" ]; then eval "PST$_i=\"已启用（预设，固定可信）\"; PSTC$_i=ok"; else eval "PST$_i=\"已停用\""; fi
    _i=$((_i+1))
done

# 自定义源回显：从 custom1..3 读 "名称|URL|启用位|验证状态"
CNAME1=""; CURL1=""; CCHK1=""; CSTAT1="未验证"; CSTAT1C=""
CNAME2=""; CURL2=""; CCHK2=""; CSTAT2="未验证"; CSTAT2C=""
CNAME3=""; CURL3=""; CCHK3=""; CSTAT3="未验证"; CSTAT3C=""
for i in 1 2 3; do
    CF="/etc/adblock/custom$i"
    [ -f "$CF" ] || continue
    _line=$(cat "$CF")
    _n=$(echo "$_line" | awk -F'|' '{print $1}')
    _u=$(echo "$_line" | awk -F'|' '{print $2}')
    _f=$(echo "$_line" | awk -F'|' '{print $3}')
    _v=$(echo "$_line" | awk -F'|' '{print $4}')
    [ -z "$_f" ] && _f=0
    case "$_v" in
        OK:*)   _st="✓ 已验证 $(printf '%s' "$_v" | sed 's/^OK://') 条"; _sc="ok" ;;
        FAIL:*) _st="✗ $(esc "$(printf '%s' "$_v" | sed 's/^FAIL://')")"; _sc="err" ;;
        *)      _st="未验证"; _sc="" ;;
    esac
    case "$i" in
        1) CNAME1="$_n"; CURL1="$_u"; [ "$_f" = "1" ] && CCHK1=checked; CSTAT1="$_st"; CSTAT1C="$_sc" ;;
        2) CNAME2="$_n"; CURL2="$_u"; [ "$_f" = "1" ] && CCHK2=checked; CSTAT2="$_st"; CSTAT2C="$_sc" ;;
        3) CNAME3="$_n"; CURL3="$_u"; [ "$_f" = "1" ] && CCHK3=checked; CSTAT3="$_st"; CSTAT3C="$_sc" ;;
    esac
done

# --- AdGuard Home 状态 ---
AGH_STATE="not_installed"
AGH_STATE_TXT="未安装"
AGH_STATE_CLASS="off"
if pgrep -f "AdGuardHome" >/dev/null 2>&1; then
    AGH_STATE="running"
    AGH_STATE_TXT="运行中"
    AGH_STATE_CLASS="on"
elif [ -x "$AGH_SCRIPT" ] && find /opt /media /mnt /tmp -maxdepth 3 -name "AdGuardHome" -type f 2>/dev/null | grep -q .; then
    AGH_STATE="installed"
    AGH_STATE_TXT="已安装（未运行）"
    AGH_STATE_CLASS="mid"
fi

# AdGuard 下载源选择
AGH_MIRROR=$(cat "$AGH_MIRROR_FILE" 2>/dev/null || echo "ghfast")
MIR1=""; MIR2=""; MIR3=""; MIR4=""; MIR_CUSTOM=""; MIR_CUSTOM_VAL=""
case "$AGH_MIRROR" in
    ghproxy) MIR2="selected";;
    ghproxynet) MIR3="selected";;
    github)    MIR4="selected";;
    ghfast)    MIR1="selected";;
    *)
        # 非预设值，说明是自定义 URL
        MIR_CUSTOM="selected"
        MIR_CUSTOM_VAL="$AGH_MIRROR"
        ;;
esac

# --- AdGuard 今日拦截数（读缓存，实时统计由 status.cgi 负责）---
AGH_BLOCKED=$(cat /tmp/agh_blocked_cache 2>/dev/null || echo "0")

# --- 路由器 LAN IP（用于 AdGuard 跳转链接）---
ROUTER_IP=$(ip addr show br-lan 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1)
[ -z "$ROUTER_IP" ] && ROUTER_IP=$(ip route 2>/dev/null | awk '/default/{print $9; exit}')
[ -z "$ROUTER_IP" ] && ROUTER_IP="192.168.1.1"

# --- 系统状态 ---
# 运行时间
UPTIME_S=$(awk '{print $1}' /proc/uptime 2>/dev/null | cut -d. -f1)
UPTIME_TXT=""
if [ -n "$UPTIME_S" ]; then
    D=$((UPTIME_S/86400)); H=$((UPTIME_S%86400/3600)); M=$((UPTIME_S%3600/60))
    [ "$D" -gt 0 ] && UPTIME_TXT="${D}天"
    UPTIME_TXT="${UPTIME_TXT}${H}小时${M}分"
fi

# 负载
LOAD1=$(cut -d' ' -f1 /proc/loadavg 2>/dev/null)
LOAD5=$(cut -d' ' -f2 /proc/loadavg 2>/dev/null)
LOAD15=$(cut -d' ' -f3 /proc/loadavg 2>/dev/null)
[ -z "$LOAD1" ] && LOAD1="-"; [ -z "$LOAD5" ] && LOAD5="-"; [ -z "$LOAD15" ] && LOAD15="-"
LOAD="${LOAD1} / ${LOAD5} / ${LOAD15}"

# 内存（KB → MB 显示）
MEM_TOTAL=$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null)
MEM_AVAIL=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo 2>/dev/null)
MEM_USED=$((MEM_TOTAL - MEM_AVAIL))
MEM_PCT=0
[ "$MEM_TOTAL" -gt 0 ] 2>/dev/null && MEM_PCT=$((MEM_USED * 100 / MEM_TOTAL))
# 转 MB（四舍五入）
MEM_USED_MB=$(( (MEM_USED + 512) / 1024 ))
MEM_TOTAL_MB=$(( (MEM_TOTAL + 512) / 1024 ))
MEM_USED_KB="${MEM_USED_MB} MB"
MEM_TOTAL_KB="${MEM_TOTAL_MB} MB"

# swap（虚拟内存）
SWAP_TOTAL=$(awk '/^SwapTotal:/{print $2}' /proc/meminfo 2>/dev/null)
SWAP_FREE=$(awk '/^SwapFree:/{print $2}' /proc/meminfo 2>/dev/null)
[ -z "$SWAP_TOTAL" ] && SWAP_TOTAL=0
[ -z "$SWAP_FREE" ] && SWAP_FREE=0
SWAP_USED=$((SWAP_TOTAL - SWAP_FREE))
SWAP_USED_MB=$(( (SWAP_USED + 512) / 1024 ))
SWAP_TOTAL_MB=$(( (SWAP_TOTAL + 512) / 1024 ))
SWAP_SIZE="${SWAP_USED_MB} MB / ${SWAP_TOTAL_MB} MB"
SWAP_PCT=0
[ "$SWAP_TOTAL" -gt 0 ] 2>/dev/null && SWAP_PCT=$((SWAP_USED * 100 / SWAP_TOTAL))

# CPU 型号（动态读 /proc/cpuinfo）与频率（MT7621 固定主频）
CPU_MODEL=$(grep -m1 "system type" /proc/cpuinfo 2>/dev/null | awk -F: '{gsub(/^[ \t]+/,"",$2); print $2}')
[ -z "$CPU_MODEL" ] && CPU_MODEL="MediaTek MT7621"
CPU_FREQ="880MHz"
MEM_FREQ="DDR3 1200MHz"

# CPU 占用（读两次 /proc/stat，间隔用 usleep 200000 微秒 = 0.2 秒，兼容 busybox）
cpu_usage() {
    read -r _ u1 n1 s1 i1 _ < /proc/stat
    usleep 200000 2>/dev/null || sleep 1
    read -r _ u2 n2 s2 i2 _ < /proc/stat
    t1=$((u1+n1+s1+i1)); t2=$((u2+n2+s2+i2))
    id1=$((i1)); id2=$((i2))
    d_id=$((id2-id1)); d_t=$((t2-t1))
    if [ "$d_t" -gt 0 ] 2>/dev/null; then
        echo $((100 - d_id*100/d_t))
    else
        echo 0
    fi
}
CPU_PCT=$(cpu_usage)

echo "Content-Type: text/html; charset=utf-8"
echo ""

cat <<HTML
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>去广告管理</title>
<style>
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f5f6f8;margin:0;padding:20px;color:#333}
.card{background:#fff;border-radius:10px;padding:20px 24px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
h2{font-size:17px;margin:0 0 14px;color:#1a1a2e}
.status{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px}
.stat{flex:1;min-width:110px;background:#f8f9fb;border-radius:8px;padding:12px 16px}
.stat .label{font-size:12px;color:#888}
.stat .value{font-size:19px;font-weight:600;margin-top:4px}
.stat .sub{font-size:12px;color:#999;margin-top:2px}
.stat .value.on{color:#16a34a}
.stat .value.off{color:#dc2626}
.stat .value.mid{color:#d97706}
.btn{display:inline-block;padding:8px 18px;border-radius:6px;border:none;cursor:pointer;font-size:14px;margin-right:8px;color:#fff;text-decoration:none}
.btn-green{background:#16a34a}.btn-red{background:#dc2626}.btn-blue{background:#2563eb}.btn-gray{background:#6b7280}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #eee}
th{font-size:12px;color:#888;font-weight:600}
.ci{width:100%;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:13px;margin-bottom:8px;box-sizing:border-box}
.ci-row{display:flex;gap:8px;align-items:center;margin-bottom:8px}
.ci-row .ci{margin-bottom:0}
.src-row{display:flex;gap:8px;align-items:flex-start;margin-bottom:12px}
.src-row>input[type=checkbox]{margin-top:12px}
.src-status{font-size:11px;color:#999;padding-left:2px;margin-top:-2px}
.src-status.ok{color:#16a34a}
.src-status.err{color:#dc2626}
.src-status.wait{color:#d97706}
select{padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px;margin-right:8px}
.hint{font-size:12px;color:#999;margin-top:8px}
input[type=checkbox]{transform:scale(1.15);margin-right:6px}
.bar{height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden;margin-top:6px;width:100%}
.bar-fill{height:100%;background:#2563eb;border-radius:4px;transition:width .3s}
.bar-fill-swap{background:#f59e0b}
.sort-arrow{font-size:10px;color:#999;margin-left:2px}
#procTable{table-layout:fixed;width:100%}
#procTable th{position:relative;overflow:visible}
#procBody tr:nth-child(even){background:#f1f5f9}
#procBody tr:hover{background:#dbeafe}
#procTable th::after{content:"";position:absolute;top:0;right:-4px;width:8px;height:100%;cursor:col-resize;z-index:1}
#procTable th:hover::after{background:rgba(37,99,235,.15)}
.mem-row{display:flex;align-items:center;margin-top:8px;flex-wrap:wrap;row-gap:2px}
.mem-label{font-size:12px;color:#555;margin-right:4px}
.mem-label::after{content:":"}
.mem-val{font-size:12px;font-weight:600;color:#333;margin-right:8px;white-space:nowrap}
.mem-size{font-size:11px;color:#999;white-space:nowrap;margin-left:auto}
.badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600}
.badge.on{background:#dcfce7;color:#16a34a}
.badge.off{background:#fee2e2;color:#dc2626}
.badge.mid{background:#fef3c7;color:#d97706}
/* 离线下载 stat + 弹窗 */
.dl-stat{cursor:pointer;transition:background .15s,box-shadow .15s}
.dl-stat:hover{background:#eff6ff;box-shadow:0 0 0 1px #bfdbfe}
.dl-stat .label{color:#2563eb}
.dl-open{background:#2563eb;color:#fff;border:none;padding:9px 18px;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer}
.dl-open:hover{background:#1d4ed8}
#dlModal,#fmModal{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.55);display:none;z-index:1000;align-items:center;justify-content:center}
#dlModal.show,#fmModal.show{display:flex}
.dl-panel{background:#fff;border-radius:10px;width:min(980px,94vw);height:min(720px,90vh);display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.3)}
.dl-head{display:flex;align-items:center;justify-content:space-between;padding:12px 18px;border-bottom:1px solid #e5e7eb;flex:none}
.dl-head b{font-size:16px;color:#1a1a2e}
.dl-close{background:none;border:none;font-size:22px;line-height:1;color:#888;cursor:pointer;padding:0 4px}
.dl-close:hover{color:#dc2626}
.dl-panel iframe{flex:1;border:none;width:100%;height:100%}
</style>
</head>
<body>
<h1 style="font-size:22px;color:#1a1a2e;margin-bottom:18px">去广告管理</h1>

<!-- ==================== 系统状态 ==================== -->
<div class="card">
<h2>系统状态</h2>
<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap">
  <label style="font-size:13px;color:#666">刷新频率：</label>
  <select id="refreshRate" onchange="setRate()">
    <option value="1">1 秒</option>
    <option value="5" selected>5 秒</option>
    <option value="10">10 秒</option>
    <option value="0">手动</option>
  </select>
  <button class="btn btn-blue" onclick="refresh()">立即刷新</button>
  <span class="hint" style="margin:0" id="refreshInfo"></span>
</div>
<div class="status">
<div class="stat" title="整机 CPU 利用率（100% - 空闲百分比）。表示这台 4 线程 CPU 有多少时间在忙，与下方进程列表的「CPU%」口径不同。">
  <div class="label">CPU 占用</div>
  <div class="value" id="cpuPct">${CPU_PCT}%</div>
  <div class="sub" id="cpuFreq">${CPU_MODEL} · ${CPU_FREQ}</div>
  <div class="bar"><div class="bar-fill" id="cpuBar" style="width:${CPU_PCT}%"></div></div>
</div>
<div class="stat" title="物理内存使用情况。已用 = 总内存 - 可用内存。swap 是硬盘上的交换分区，内存不足时作缓冲。">
  <div style="display:flex;align-items:center;justify-content:space-between">
    <div class="label">内存占用</div>
    <div class="sub" style="margin:0;font-size:11px;color:#999">${MEM_FREQ}</div>
  </div>
  <div class="value" id="memPct">${MEM_PCT}%</div>
  <div class="mem-row">
    <span class="mem-label">物理内存</span><span class="mem-val" id="memPctRow">${MEM_PCT}%</span>
    <span class="mem-size" id="memSize">${MEM_USED_KB} / ${MEM_TOTAL_KB}</span>
  </div>
  <div class="bar"><div class="bar-fill" id="memBar" style="width:${MEM_PCT}%"></div></div>
  <div class="mem-row">
    <span class="mem-label">swap</span><span class="mem-val" id="swapPctRow">${SWAP_PCT}%</span>
    <span class="mem-size" id="swapSize">${SWAP_SIZE}</span>
  </div>
  <div class="bar"><div class="bar-fill bar-fill-swap" id="swapBar" style="width:${SWAP_PCT}%"></div></div>
</div>
<div class="stat" title="负载（1/5/15分钟）是等待 CPU 的平均进程数，本机 4 线程，负载 ≈4 表示满载。运行时间是路由器自开机以来的时长。">
  <div class="label">负载 / 运行时间</div>
  <div class="value" style="font-size:14px" id="loadVal">${LOAD}</div>
  <div class="sub" id="loadRate">负载率 -%</div>
  <div class="sub" style="margin-top:6px" id="uptimeVal">${UPTIME_TXT}</div>
</div>
<div class="stat dl-stat" onclick="openDl()" title="点击打开下载管理（添加链接 / 种子、暂停、删除）">
  <div class="label">离线下载 · 点击打开 →</div>
  <div class="value" id="dlState" style="font-size:15px">检测中…</div>
  <div class="sub" id="dlDown">—</div>
  <div class="sub" id="dlActive">—</div>
</div>
<div class="stat dl-stat" onclick="openFm()" title="点击打开文件管理（内置盘 / U盘，增删改查）">
  <div class="label">文件管理 · 点击打开 →</div>
  <div class="value" style="font-size:14px">内置盘 + U盘</div>
  <div class="sub" id="fmDisk">读取中…</div>
</div>
</div>

<!-- 进程占用（系统状态子块） -->
<div style="border-top:1px dashed #e5e7eb;padding-top:14px;margin-top:14px">
<h2 style="font-size:15px">进程占用</h2>
<p class="hint" style="margin-top:-4px">注：进程 CPU% 表示该进程占用的核数（多线程可超 100%），与上方「CPU 占用」的整机利用率口径不同，两者数值不相等属正常。进程数据每 5 秒采集更新一次。</p>
<div style="background:#f8f9fb;border-radius:8px;padding:14px 16px">
<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap">
  <button class="btn btn-gray" id="procToggleBtn" onclick="toggleProcs()">展开全部</button>
  <span class="hint" style="margin:0" id="procCount"></span>
</div>
<table id="procTable">
<colgroup>
<col><col><col><col><col><col>
</colgroup>
<thead>
<tr>
<th style="cursor:pointer" onclick="setProcSort('name')" id="thName">进程名<span class="sort-arrow" id="arName"></span></th>
<th>备注</th>
<th style="text-align:right;cursor:pointer" title="实时 CPU 占用百分比，表示该进程当前占用了多少个核（多线程累加，可超过 100%）。两次采样求差得出，仅显示此刻正在消耗 CPU 的进程。" onclick="setProcSort('cpu')" id="thCpu">CPU %<span class="sort-arrow" id="arCpu"></span></th>
<th style="text-align:right;cursor:pointer" title="开机以来该进程累计消耗的 CPU 总时间（所有线程累加）。数值越大说明这个进程长期吃 CPU。" onclick="setProcSort('cputime')" id="thCputime">累计CPU<span class="sort-arrow" id="arCputime"></span></th>
<th style="text-align:right;cursor:pointer" title="RSS，进程真实占用的物理内存（不含共享库映射和预留空间）。这是判断"谁占内存大"最准的指标。" onclick="setProcSort('rss')" id="thRss">内存(RSS)<span class="sort-arrow" id="arRss"></span></th>
<th style="text-align:right;cursor:pointer" title="VmSize，进程声明的虚拟地址空间，远大于真实物理内存（含共享库映射、预留未用空间），参考价值低，主要看 RSS。" onclick="setProcSort('vsz')" id="thVsz">虚拟地址空间<span class="sort-arrow" id="arVsz"></span></th>
</tr>
</thead>
<tbody id="procBody">
<tr><td colspan="6" style="color:#999">加载中…</td></tr>
</tbody>
</table>
</div>
</div>
</div>

<!-- ==================== AdGuard Home ==================== -->
<div class="card">
<h2>AdGuard Home（主力去广告）</h2>
<div class="status">
<div class="stat"><div class="label">状态</div><div class="value ${AGH_STATE_CLASS}" id="aghState">${AGH_STATE_TXT}</div></div>
<div class="stat"><div class="label">今日拦截</div><div class="value" style="color:#dc2626" id="aghBlocked">${AGH_BLOCKED}</div></div>
<div class="stat"><div class="label">管理界面</div><div class="value" style="font-size:14px">:3000</div></div>
<div class="stat"><div class="label">默认账号</div><div class="value" style="font-size:14px">admin</div></div>
</div>

<form method="POST" style="margin-bottom:12px">
<label style="font-size:13px;color:#666">下载源：</label>
<select name="agh_mirror" id="aghMirror" onchange="toggleCustom()">
<option value="ghfast" ${MIR1}>ghfast.top 镜像</option>
<option value="ghproxy" ${MIR2}>gh-proxy.com 镜像</option>
<option value="ghproxynet" ${MIR3}>ghproxy.net 镜像</option>
<option value="github" ${MIR4}>GitHub 官方直连</option>
<option value="custom" ${MIR_CUSTOM}>自定义…</option>
</select>
<input class="ci" type="text" name="agh_mirror_custom" id="aghMirrorCustom" placeholder="自定义镜像前缀，如 https://ghfast.top/" value="${MIR_CUSTOM_VAL}" style="width:340px;display:none;margin-top:8px">
<button class="btn btn-gray" name="action" value="save_mirror">保存源</button>
</form>

<form method="POST">
<button class="btn btn-blue" name="action" value="agh_install">下载安装</button>
<button class="btn btn-green" name="action" value="agh_start">启动</button>
<button class="btn btn-red" name="action" value="agh_stop">停止</button>
<a class="btn btn-blue" href="http://${ROUTER_IP}:3000" target="_blank" rel="noopener">打开 AdGuard 界面 →</a>
</form>
<p class="hint">AdGuard Home 是专业的 DNS 过滤引擎（通配符、正则、统计面板、安全过滤），监听 5353 端口与 dnsmasq 的 53 端口共存。<br>默认登录：admin / password123!。<br>今日拦截数 = querylog 中黑名单命中的查询次数（约 30 秒刷新一次）。</p>
</div>

<!-- ==================== dnsmasq 去广告（兜底，含规则源子区块） ==================== -->
<div class="card">
<h2>dnsmasq 去广告（兜底）</h2>
<div class="status">
<div class="stat"><div class="label">去广告</div><div class="value ${EN_CLASS}" id="adbState">${ENABLED}</div></div>
<div class="stat"><div class="label">规则条数</div><div class="value" id="adbCount">${COUNT}</div></div>
<div class="stat"><div class="label">上次更新</div><div class="value" style="font-size:13px" id="adbTime">${TIME}</div></div>
</div>
<form method="POST" style="display:inline;margin-bottom:16px">
<button class="btn btn-green" name="action" value="enable">启用</button>
<button class="btn btn-red" name="action" value="disable">停用</button>
<button class="btn btn-blue" name="action" value="update">立即更新</button>
</form>
<p class="hint" style="margin-bottom:12px">dnsmasq 去广告是兜底方案（AdGuard 挂了才顶上来）。其规则源配置见下方子区块。</p>

<!-- 规则源（子区块） -->
<div style="border-top:1px dashed #e5e7eb;padding-top:14px;margin-top:4px">
<h2 style="font-size:15px">规则源</h2>
<script>
// 统一异步 API：带 format=json，后端返回 JSON，页面不刷新
async function api(action, params){
  var body = new URLSearchParams();
  body.append('action', action);
  body.append('format', 'json');
  for (var k in params) body.append(k, params[k]);
  var r = await fetch('/cgi-bin/adblock.cgi', {method:'POST', body:body});
  return await r.json();
}
function setStatus(slot, msg, cls){
  var el = document.getElementById('st'+slot);
  if(el){ el.textContent = msg; el.className = 'src-status '+(cls||''); }
}
function setBusy(slot, busy){
  var b = document.getElementById('sv'+slot); if(b) b.disabled = busy;
}
// 点「保存」：真下载验证规则数；输入框内容保留不动
async function doVerify(slot){
  var n = document.getElementsByName('cname'+slot)[0].value;
  var u = document.getElementsByName('curl'+slot)[0].value;
  setStatus(slot, '校验中…（最多 25 秒）', 'wait');
  setBusy(slot, true);
  try {
    var res = await api('verify_custom', {slot:slot, cname:n, curl:u});
    setStatus(slot, res.msg, res.ok ? 'ok' : 'err');
  } catch(e){ setStatus(slot, '请求失败：'+e, 'err'); }
  finally { setBusy(slot, false); }
}
// 预设源复选框：只切启用状态，不刷新页面
async function doToggle(line, el){
  try {
    var res = await api('toggle_src', {line:line, on:el.checked?'1':'0'});
    if(!res.ok){ el.checked = !el.checked; alert(res.msg); return; }
    var st = document.getElementById('pst'+line);
    if(st){
      st.textContent = el.checked ? '已启用（预设，固定可信）' : '已停用';
      st.className = 'src-status ' + (el.checked ? 'ok' : '');
    }
  } catch(e){ el.checked = !el.checked; alert('请求失败：'+e); }
}
// 删除自定义源：清空名称/URL 走 save_custom（后端会 rm customN）
async function doDelete(slot){
  if(!confirm('确定删除这个自定义源？')) return;
  try {
    var res = await api('save_custom', {slot:slot, cname:'', curl:''});
    if(!res.ok){ alert(res.msg); return; }
    document.getElementsByName('cname'+slot)[0].value = '';
    document.getElementsByName('curl'+slot)[0].value = '';
    var cb = document.getElementById('ck'+slot); if(cb) cb.checked = false;
    setStatus(slot, '已删除', '');
  } catch(e){ alert('请求失败：'+e); }
}
// 自定义源复选框：勾选时先真实验证再启用；取消只切状态
async function doCustomToggle(slot, el){
  var n = document.getElementsByName('cname'+slot)[0].value;
  var u = document.getElementsByName('curl'+slot)[0].value;
  if(el.checked){
    if(u.replace(/^\s+|\s+$/g,'')===''){
      alert('请先在该行填写规则地址'); el.checked=false; return;
    }
    setStatus(slot, '校验中…（最多 25 秒）', 'wait');
    setBusy(slot, true);
    try {
      var res = await api('verify_custom', {slot:slot, cname:n, curl:u, on:'1'});
      setStatus(slot, res.msg, res.ok ? 'ok' : 'err');
      if(!res.ok) el.checked = false;
    } catch(e){ setStatus(slot, '请求失败：'+e, 'err'); el.checked=false; }
    finally { setBusy(slot, false); }
  } else {
    try {
      var res = await api('toggle_src', {line:slot+4, on:'0'});
      if(!res.ok) el.checked = true;
      else setStatus(slot, '已停用', '');
    } catch(e){ el.checked = true; alert('请求失败：'+e); }
  }
}
</script>
<table>
<tr><th style="width:50px">启用</th><th>名称</th><th>地址</th></tr>
<tr><td><input type="checkbox" ${CHK1} onchange="doToggle(1,this)"></td><td>${PRESET1_NAME}<div class="src-status ${PSTC1}" id="pst1">${PST1}</div></td><td style="color:#666;font-size:12px;word-break:break-all">${PRESET1_URL}</td></tr>
<tr><td><input type="checkbox" ${CHK2} onchange="doToggle(2,this)"></td><td>${PRESET2_NAME}<div class="src-status ${PSTC2}" id="pst2">${PST2}</div></td><td style="color:#666;font-size:12px;word-break:break-all">${PRESET2_URL}</td></tr>
<tr><td><input type="checkbox" ${CHK3} onchange="doToggle(3,this)"></td><td>${PRESET3_NAME}<div class="src-status ${PSTC3}" id="pst3">${PST3}</div></td><td style="color:#666;font-size:12px;word-break:break-all">${PRESET3_URL}</td></tr>
<tr><td><input type="checkbox" ${CHK4} onchange="doToggle(4,this)"></td><td>${PRESET4_NAME}<div class="src-status ${PSTC4}" id="pst4">${PST4}</div></td><td style="color:#666;font-size:12px;word-break:break-all">${PRESET4_URL}</td></tr>
</table>

<p class="hint" style="margin:12px 0 8px">自定义源（最多 3 个）：点「保存」会真实下载并数规则条数（≥50 条通过），失败时输入内容保留可改；勾选会自动验证并启用。未验证的地址无法启用。</p>
<div class="src-row">
<input type="checkbox" ${CCHK1} id="ck1" onchange="doCustomToggle(1,this)" title="启用/停用">
<div style="flex:1;min-width:0">
<div class="ci-row"><input class="ci" style="flex:0 0 24%" type="text" name="cname1" value="$(esc "$CNAME1")" placeholder="名称"><input class="ci" style="flex:1" type="text" name="curl1" value="$(esc "$CURL1")" placeholder="https://... 规则地址"><button class="btn btn-blue" id="sv1" type="button" onclick="doVerify(1)">保存</button><button class="btn btn-red" id="dl1" type="button" onclick="doDelete(1)">删除</button></div>
<div class="src-status ${CSTAT1C}" id="st1">${CSTAT1}</div>
</div>
</div>
<div class="src-row">
<input type="checkbox" ${CCHK2} id="ck2" onchange="doCustomToggle(2,this)" title="启用/停用">
<div style="flex:1;min-width:0">
<div class="ci-row"><input class="ci" style="flex:0 0 24%" type="text" name="cname2" value="$(esc "$CNAME2")" placeholder="名称"><input class="ci" style="flex:1" type="text" name="curl2" value="$(esc "$CURL2")" placeholder="https://... 规则地址"><button class="btn btn-blue" id="sv2" type="button" onclick="doVerify(2)">保存</button><button class="btn btn-red" id="dl2" type="button" onclick="doDelete(2)">删除</button></div>
<div class="src-status ${CSTAT2C}" id="st2">${CSTAT2}</div>
</div>
</div>
<div class="src-row">
<input type="checkbox" ${CCHK3} id="ck3" onchange="doCustomToggle(3,this)" title="启用/停用">
<div style="flex:1;min-width:0">
<div class="ci-row"><input class="ci" style="flex:0 0 24%" type="text" name="cname3" value="$(esc "$CNAME3")" placeholder="名称"><input class="ci" style="flex:1" type="text" name="curl3" value="$(esc "$CURL3")" placeholder="https://... 规则地址"><button class="btn btn-blue" id="sv3" type="button" onclick="doVerify(3)">保存</button><button class="btn btn-red" id="dl3" type="button" onclick="doDelete(3)">删除</button></div>
<div class="src-status ${CSTAT3C}" id="st3">${CSTAT3}</div>
</div>
</div>
</form>
<p class="hint">支持三种格式：dnsmasq(address=/域名/)、AdBlock(||域名^)、hosts(0.0.0.0 域名)，保存时按相同逻辑转换并去重计数。预设源固定可信不参与验证；自定义源必须验证通过才生效。</p>
</div>
</div>

<script>
var refreshTimer = null;
var REFRESH_RATE = 5;
var PROC_SORT = "cpu";      // 排序字段：name/cpu/cputime/rss/vsz
var PROC_DESC = true;       // 是否降序（默认降序，大的在前）
var PROC_EXPANDED = false;  // 是否展开全部
var PROC_DATA = [];         // 缓存进程数据

function toggleCustom(){
  var sel = document.getElementById("aghMirror");
  var box = document.getElementById("aghMirrorCustom");
  if(sel && box){
    box.style.display = (sel.value === "custom") ? "inline-block" : "none";
  }
}

function setProcSort(field){
  // 点同一列：切换升/降序；点新列：默认降序
  if(PROC_SORT === field){
    PROC_DESC = !PROC_DESC;
  } else {
    PROC_SORT = field;
    PROC_DESC = true;
  }
  renderProcs();
}

function toggleProcs(){
  PROC_EXPANDED = !PROC_EXPANDED;
  var btn = document.getElementById("procToggleBtn");
  if(btn) btn.textContent = PROC_EXPANDED ? "收起" : "展开全部";
  renderProcs();
}

function fmtCpuTime(sec){
  sec = parseInt(sec) || 0;
  if(sec >= 3600){ return Math.floor(sec/3600) + "h" + Math.floor(sec%3600/60) + "m"; }
  if(sec >= 60){ return Math.floor(sec/60) + "分" + (sec%60) + "秒"; }
  return sec + "秒";
}

function renderProcs(){
  var body = document.getElementById("procBody");
  var cnt = document.getElementById("procCount");
  if(!body) return;
  var list = PROC_DATA.slice();
  // 排序（支持 name/cpu/cputime/rss/vsz）
  list.sort(function(a,b){
    var r = 0;
    if(PROC_SORT === "name"){
      r = String(a.name).localeCompare(String(b.name));
    } else if(PROC_SORT === "cputime"){
      r = (parseInt(a.cputime)||0) - (parseInt(b.cputime)||0);
    } else if(PROC_SORT === "rss"){
      r = (parseInt(a.rss)||0) - (parseInt(b.rss)||0);
    } else if(PROC_SORT === "vsz"){
      r = (parseInt(a.vsz)||0) - (parseInt(b.vsz)||0);
    } else { // cpu
      r = (parseFloat(a.cpu)||0) - (parseFloat(b.cpu)||0);
    }
    return PROC_DESC ? -r : r;
  });
  // 合计（全部进程，非仅TOP5）
  var sumCpu = 0, sumRss = 0;
  for(var i=0;i<list.length;i++){
    sumCpu += (parseFloat(list[i].cpu)||0);
    sumRss += (parseInt(list[i].rss)||0);
  }
  if(cnt) cnt.textContent = "共 " + list.length + " 个进程 · CPU合计 " + Math.round(sumCpu) + "% · 内存合计 " + sumRss + " MB";
  // 更新表头箭头
  var arrows = {name:"arName", cpu:"arCpu", cputime:"arCputime", rss:"arRss", vsz:"arVsz"};
  for(var k in arrows){
    var el = document.getElementById(arrows[k]);
    if(el) el.textContent = (k === PROC_SORT) ? (PROC_DESC ? " ▼" : " ▲") : "";
  }
  var show = PROC_EXPANDED ? list : list.slice(0, 5);
  var html = "";
  for(var i=0;i<show.length;i++){
    var p = show[i];
    var rss = p.rss > 0 ? p.rss + " MB" : "-";
    var vsz = p.vsz > 0 ? p.vsz + " MB" : "-";
    var cpu = p.cpu > 0 ? p.cpu + "%" : "0%";
    var cputime = fmtCpuTime(p.cputime);
    var desc = p.desc || "";
    html += "<tr>";
    html += "<td>" + esc(p.name) + "<br><span style='color:#bbb;font-size:11px'>pid " + p.pid + "</span></td>";
    html += "<td style='color:#888;font-size:12px'>" + esc(desc) + "</td>";
    html += "<td style='text-align:right'>" + cpu + "</td>";
    html += "<td style='text-align:right'>" + cputime + "</td>";
    html += "<td style='text-align:right'>" + rss + "</td>";
    html += "<td style='text-align:right'>" + vsz + "</td>";
    html += "</tr>";
  }
  body.innerHTML = html;
}

function esc(s){
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function fmtUptime(s){
  s = parseInt(s) || 0;
  var d = Math.floor(s/86400), h = Math.floor(s%86400/3600), m = Math.floor(s%3600/60);
  var t = "";
  if(d>0) t += d + "天";
  t += h + "小时" + m + "分";
  return t;
}
function fmtMB(kb){
  var mb = Math.round((parseInt(kb)||0)/1024);
  return mb + " MB";
}

function refresh(){
  fetch("adblock_status.cgi", {cache:"no-store"})
    .then(function(r){ return r.json(); })
    .then(function(d){
      // CPU
      document.getElementById("cpuPct").textContent = d.cpu.pct + "%";
      document.getElementById("cpuBar").style.width = d.cpu.pct + "%";
      document.getElementById("cpuFreq").textContent = d.cpu.freq;
      // 内存
      document.getElementById("memPct").textContent = d.mem.pct + "%";
      document.getElementById("memPctRow").textContent = d.mem.pct + "%";
      document.getElementById("memBar").style.width = d.mem.pct + "%";
      document.getElementById("memSize").textContent = fmtMB(d.mem.used) + " / " + fmtMB(d.mem.total);
      var swp = d.mem.swap_total > 0 ? Math.round(d.mem.swap_used*100/d.mem.swap_total) : 0;
      document.getElementById("swapPctRow").textContent = swp + "%";
      document.getElementById("swapSize").textContent = fmtMB(d.mem.swap_used) + " / " + fmtMB(d.mem.swap_total);
      document.getElementById("swapBar").style.width = swp + "%";
      // 负载
      document.getElementById("loadVal").textContent = d.load.l1 + " / " + d.load.l5 + " / " + d.load.l15;
      var lr = Math.round(parseFloat(d.load.l1)/4*100);
      document.getElementById("loadRate").textContent = "负载率 " + lr + "%（4线程）";
      // 运行时间
      document.getElementById("uptimeVal").textContent = fmtUptime(d.uptime);
      // AGH
      var st = document.getElementById("aghState");
      if(d.agh.running == 1){ st.textContent = "运行中"; st.className = "value on"; }
      else if(d.agh.running == 0){ st.textContent = "未运行"; st.className = "value off"; }
      document.getElementById("aghBlocked").textContent = d.agh.blocked;
      // dnsmasq
      var adb = document.getElementById("adbState");
      if(d.adblock.enabled == 1){ adb.textContent = "已启用"; adb.className = "value on"; }
      else { adb.textContent = "已停用"; adb.className = "value off"; }
      document.getElementById("adbCount").textContent = d.adblock.count;
      document.getElementById("adbTime").textContent = d.adblock.time;
      // 进程占用
      if(d.procs && d.procs.length){
        PROC_DATA = d.procs;
        renderProcs();
      }
      // 离线下载状态（独立探测，失败不影响其他卡片）
      dlStat();
      // 刷新信息
      var t = new Date();
      document.getElementById("refreshInfo").textContent = "上次刷新 " + t.toLocaleTimeString();
    })
    .catch(function(e){
      document.getElementById("refreshInfo").textContent = "刷新失败";
    });
}

// ============ 离线下载卡片 + 弹窗 ============
function fmtRate(n){
  n = Number(n)||0;
  if(n <= 0) return "—";
  if(n < 1048576) return (n/1024).toFixed(0) + " KB/s";
  return (n/1048576).toFixed(1) + " MB/s";
}
function dlVersion(){
  var rpc = "http://" + location.hostname + ":6800/jsonrpc";
  fetch(rpc, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({jsonrpc:"2.0",id:"v1",method:"aria2.getVersion",params:["token:jdc2026"]})
  })
  .then(function(r){ return r.json(); })
  .then(function(j){ if(j.result) document.getElementById("dlVer").textContent = "· aria2 " + j.result.version; })
  .catch(function(){});
}
function dlStat(){
  var rpc = "http://" + location.hostname + ":6800/jsonrpc";
  fetch(rpc, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({jsonrpc:"2.0",id:"1",method:"aria2.getGlobalStat",params:["token:jdc2026"]})
  })
  .then(function(r){ return r.json(); })
  .then(function(j){
    if(j.error) throw new Error(j.error.message);
    var d = j.result;
    var st = document.getElementById("dlState");
    st.textContent = "运行中"; st.className = "value on";
    document.getElementById("dlDown").textContent = fmtRate(d.downloadSpeed);
    document.getElementById("dlActive").textContent = "进行 " + d.numActive + " · 等待 " + d.numWaiting;
  })
  .catch(function(e){
    var st = document.getElementById("dlState");
    st.textContent = "未启动"; st.className = "value off";
    document.getElementById("dlDown").textContent = "—";
    document.getElementById("dlActive").textContent = "—";
  });
}
function openDl(){
  var m = document.getElementById("dlModal");
  var f = document.getElementById("dlFrame");
  if(!f.src || f.src === "about:blank") f.src = "/dl.html";   // 首次点击才加载
  m.className = "show";
  document.body.style.overflow = "hidden";
}
function closeDl(){
  document.getElementById("dlModal").className = "";
  document.body.style.overflow = "";
}
function openFm(){
  var m = document.getElementById("fmModal");
  var f = document.getElementById("fmFrame");
  if(!f.src || f.src === "about:blank") f.src = "/filemgr.html";
  m.className = "show";
  document.body.style.overflow = "hidden";
}
function closeFm(){
  document.getElementById("fmModal").className = "";
  document.body.style.overflow = "";
}
function fmInfo(){
  fetch("/cgi-bin/file_dl.cgi?action=roots").then(function(r){return r.json();}).then(function(j){
    var rs=j.roots||[];
    var usb=rs.filter(function(r){return r.path.match(/\/mnt\/sd[a-z]/);});
    document.getElementById("fmDisk").textContent = rs.length + " 个盘" + (usb.length?(" · U盘 "+usb[0].name):" · 无U盘");
  }).catch(function(){ document.getElementById("fmDisk").textContent = "—"; });
}
document.addEventListener("keydown", function(e){ if(e.key === "Escape"){ closeDl(); closeFm(); } });

function setRate(){
  REFRESH_RATE = parseInt(document.getElementById("refreshRate").value);
  if(refreshTimer){ clearInterval(refreshTimer); refreshTimer = null; }
  if(REFRESH_RATE > 0){
    refreshTimer = setInterval(refresh, REFRESH_RATE*1000);
  }
  refresh();
}

// ============ 列宽拖拽（类似 Excel，只动当前列+相邻列，刷新恢复默认）============
function initColResize(){
  var table = document.getElementById("procTable");
  if(!table) return;
  var cols = table.querySelectorAll("colgroup col");
  var ths = table.querySelectorAll("thead th");
  var n = cols.length;
  if(n === 0 || ths.length !== n) return;

  var startX = 0, curIdx = -1, curW = 0, adjIdx = -1, adjW = 0, dragging = false;

  // 把手柄：th 右边缘 10px 内才算（最后一列把手柄放在左边缘）
  function isHandle(th, e){
    var r = th.getBoundingClientRect();
    var x = e.clientX;
    if(x > r.right - 10) return true;      // 右边缘
    if(x < r.left + 10) return true;       // 左边缘（用于最后一列）
    return false;
  }

  function onDown(e){
    var th = e.target.closest ? e.target.closest("th") : null;
    if(!th) return;
    var idx = Array.prototype.indexOf.call(ths, th);
    if(idx < 0) return;
    if(!isHandle(th, e)) return;
    // 决定被"吸收"的相邻列：右侧列优先；若是最后一列则用左侧列
    var r = th.getBoundingClientRect();
    if(e.clientX > r.right - 10 && idx < n - 1) adjIdx = idx + 1;
    else if(e.clientX < r.left + 10 && idx > 0) adjIdx = idx - 1;
    else adjIdx = (idx < n - 1) ? idx + 1 : idx - 1;
    if(adjIdx < 0 || adjIdx >= n) return;

    curIdx = idx;
    curW = cols[idx].offsetWidth || ths[idx].offsetWidth;
    adjW = cols[adjIdx].offsetWidth || ths[adjIdx].offsetWidth;
    startX = e.clientX;
    dragging = false;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    e.preventDefault();
  }
  function onMove(e){
    if(curIdx < 0) return;
    var delta = e.clientX - startX;
    if(!dragging && Math.abs(delta) > 5) dragging = true;  // 位移>5px 才算拖拽
    if(!dragging) return;
    var w1 = curW + delta;
    var w2 = adjW - delta;
    if(w1 < 40){ w2 += (w1 - 40); w1 = 40; }   // 当前列最小 40px
    if(w2 < 40){ w1 += (w2 - 40); w2 = 40; }   // 相邻列最小 40px
    cols[curIdx].style.width = w1 + "px";
    cols[adjIdx].style.width = w2 + "px";
  }
  function onUp(){
    if(dragging){
      // 拖拽结束后拦截一次 click，避免触发表头排序
      table.addEventListener("click", function stop(e){
        e.stopPropagation();
        e.preventDefault();
        table.removeEventListener("click", stop, true);
      }, true);
    }
    curIdx = -1; adjIdx = -1; dragging = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }

  table.addEventListener("mousedown", onDown);
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
}

// 启动自动刷新（默认 5 秒）
refresh();
dlVersion();
fmInfo();
setRate();
toggleCustom();
initColResize();
</script>

<div id="dlModal" onclick="if(event.target===this)closeDl()">
<div class="dl-panel">
<div class="dl-head"><b>离线下载管理 <small id="dlVer" style="font-size:11px;color:#888;font-weight:400"></small></b><button class="dl-close" onclick="closeDl()" title="关闭">×</button></div>
<iframe id="dlFrame" src="about:blank" title="离线下载"></iframe>
</div>
</div>

<div id="fmModal" onclick="if(event.target===this)closeFm()">
<div class="dl-panel">
<div class="dl-head"><b>文件管理 <small style="font-size:11px;color:#888;font-weight:400">· 内置盘 / U盘</small></b><button class="dl-close" onclick="closeFm()" title="关闭">×</button></div>
<iframe id="fmFrame" src="about:blank" title="文件管理"></iframe>
</div>
</div>
</body>
</html>
HTML

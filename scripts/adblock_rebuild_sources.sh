#!/bin/sh
# 重建 /etc/adblock/sources.list
# 数据来源：
#   /etc/adblock/preset_flags  — 4 行，每行 0/1，对应 4 个预设源启用状态
#   /etc/adblock/custom1..3    — 每行 "名称|URL|启用位|验证状态"
#                                 验证状态 = OK:条数 / FAIL:原因 / 空(未验证)
# 输出格式：名称|URL|启用位   （adblock_update.sh 只读前两列，第三列被忽略，兼容）
# 注意：adblock_update.sh 会下载 sources.list 里所有行，因此停用的源必须整行注释掉
# 关键：自定义源必须「启用位=1 且 验证=OK:*」才写入，杜绝假启用

SRC_LIST="/etc/adblock/sources.list"
FLAGS="/etc/adblock/preset_flags"
mkdir -p /etc/adblock

# 预设源定义（与 adblock.cgi 保持一致）
P1="anti-AD(gcore)|https://gcore.jsdelivr.net/gh/privacy-protection-tools/anti-AD@master/anti-ad-easylist.txt"
P2="anti-AD(ghfast)|https://ghfast.top/https://raw.githubusercontent.com/privacy-protection-tools/anti-AD/master/anti-ad-easylist.txt"
P3="AdGuard中文过滤(gcore)|https://gcore.jsdelivr.net/gh/AdguardTeam/AdguardFilters@master/ChineseFilter/sections/adservers.txt"
P4="AdGuard中文(gcore备用)|https://ghfast.top/https://raw.githubusercontent.com/AdguardTeam/AdguardFilters/master/ChineseFilter/sections/adservers.txt"

: > "$SRC_LIST.tmp"
echo "# 去广告规则源列表：名称|URL|启用(1/0)" >> "$SRC_LIST.tmp"

# 预设源：读 flags，缺省启用=1（预设固定可信，不参与下载验证）
i=1
for P in "$P1" "$P2" "$P3" "$P4"; do
    F=$(sed -n "${i}p" "$FLAGS" 2>/dev/null)
    [ -z "$F" ] && F=1
    if [ "$F" = "1" ]; then
        echo "$P|1" >> "$SRC_LIST.tmp"
    else
        echo "#$P|0" >> "$SRC_LIST.tmp"
    fi
    i=$((i+1))
done

# 自定义槽位：只有「启用=1 且 验证=OK:*」才生效
for i in 1 2 3; do
    CF="/etc/adblock/custom$i"
    [ -f "$CF" ] || continue
    LINE=$(cat "$CF")
    NAME=$(echo "$LINE" | awk -F'|' '{print $1}')
    URL=$(echo "$LINE" | awk -F'|' '{print $2}')
    F=$(echo "$LINE" | awk -F'|' '{print $3}')
    V=$(echo "$LINE" | awk -F'|' '{print $4}')
    [ -z "$URL" ] && continue
    [ -z "$F" ] && F=0
    # 验证状态：OK:n 视为已验证；FAIL:* 或空视为未验证
    case "$V" in
        OK:*) VERIFIED=1 ;;
        *)    VERIFIED=0 ;;
    esac
    if [ "$F" = "1" ] && [ "$VERIFIED" = "1" ]; then
        echo "$NAME|$URL|1" >> "$SRC_LIST.tmp"
    else
        echo "#$NAME|$URL|0" >> "$SRC_LIST.tmp"
    fi
done

mv "$SRC_LIST.tmp" "$SRC_LIST"

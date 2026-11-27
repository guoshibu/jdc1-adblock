#!/bin/sh
# 统一文件下载 + 存储根枚举
# 用法:
#   /cgi-bin/file_dl.cgi?action=roots          -> JSON 列出可用存储根（内置盘 + U盘）
#   /cgi-bin/file_dl.cgi?path=<完整路径>        -> realpath 校验后 302 到 /dl-mnt/<rel>，nginx sendfile 直传
# 白名单统一在后端：/mnt/mmcblk0p4 + 运行时枚举 /mnt/sdX（U盘），防目录穿越/符号链接逃逸

BASE_INTERNAL='/mnt/mmcblk0p4'

json_err(){
  printf 'Content-Type: application/json; charset=utf-8\n\n{"ok":false,"err":"%s"}\n' "$1"
  exit 0
}

# ---- 枚举可用根（内置盘 + U盘） ----
enum_roots(){
  roots=''
  [ -d "$BASE_INTERNAL" ] && roots="$BASE_INTERNAL"
  for mp in $(awk '{print $2}' /proc/mounts | grep -E '^/mnt/sd[a-z][0-9]*$' | sort -u); do
    [ -d "$mp" ] && roots="$roots $mp"
  done
  printf '%s' "$roots"
}

# ---- action=roots: 输出 JSON ----
QS="${QUERY_STRING:-}"
action=$(printf '%s' "$QS" | sed -n 's/.*[?&]action=\([^&]*\).*/\1/p')
[ -z "$action" ] && action=$(printf '%s' "$QS" | sed -n 's/^action=\([^&]*\)$/\1/p')

if [ "$action" = "roots" ]; then
  printf 'Content-Type: application/json; charset=utf-8\n\n'
  printf '{"ok":true,"roots":['
  first=1
  for r in $(enum_roots); do
    [ "$first" -eq 0 ] && printf ','
    first=0
    label=$(basename "$r")
    size=$(df -k "$r" 2>/dev/null | awk 'NR==2{print $2}')
    avail=$(df -k "$r" 2>/dev/null | awk 'NR==2{print $4}')
    fs=$(awk -v m="$r" '$2==m{print $3}' /proc/mounts | head -1)
    printf '{"path":"%s","name":"%s","size_kb":"%s","avail_kb":"%s","fs":"%s"}' "$r" "$label" "${size:-0}" "${avail:-0}" "$fs"
  done
  printf ']}\n'
  exit 0
fi

# ---- path: 下载 ----
enc=$(printf '%s' "$QS" | sed -n 's/.*[?&]path=\([^&]*\).*/\1/p')
[ -z "$enc" ] && enc=$(printf '%s' "$QS" | sed -n 's/^path=\([^&]*\)$/\1/p')
[ -z "$enc" ] && json_err '缺少 path 参数'

# %XX -> \xXX，+ -> 空格
esc=$(printf '%s' "$enc" | sed -e 's/+/ /g' -e 's/%\(..\)/\\x\1/g')
path=$(printf "$esc")
[ -n "$path" ] || json_err '路径解码失败'
case "$path" in
  /*) ;;
  *) json_err '路径必须是绝对路径' ;;
esac

# realpath 解析（跟随软链，防逃逸）
real=$(readlink -f "$path" 2>/dev/null)
[ -n "$real" ] || json_err '文件不存在或无法解析'

# 白名单校验：必须在任一允许根内（结尾 / 边界防前缀误判）
allowed=0
for r in $(enum_roots); do
  case "$real" in
    "$r"/*) allowed=1 ;;
  esac
done
[ "$allowed" -eq 1 ] || json_err '路径不在允许目录内'
[ -f "$real" ] || json_err '不是普通文件'

# 302 到 /dl-mnt/<去掉 /mnt/ 前缀的路径>
rel=${real#/mnt/}
enc_rel=$(printf '%s' "$rel" | sed -e 's/%/%25/g' -e 's/ /%20/g' -e 's/#/%23/g' -e 's/?/%3F/g')
printf 'Location: /dl-mnt/%s\n' "$enc_rel"
printf 'Content-Type: text/plain; charset=utf-8\n'
printf '\nredirect\n'
exit 0

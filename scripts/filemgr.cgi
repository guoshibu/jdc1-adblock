#!/bin/sh
# 文件管理器 API（阶段1：无上传）
# action=list&path=     列目录 -> {ok,path,writable,items:[{name,path,type,size,mtime}]}
# action=read&path=     读文本 -> {ok,content}
# action=write&path=&content=  写文本（POST content 参数）
# action=mkdir&path=    建目录
# action=rename&from=&to=  重命名/移动
# action=delete&path=   删除文件/空目录
# 所有路径经 realpath 校验白名单（内置盘 + sdX），防穿越/逃逸

BASE_INTERNAL='/mnt/mmcblk0p4'

json_err(){ printf 'Content-Type: application/json; charset=utf-8\n\n{"ok":false,"err":"%s"}\n' "$1"; exit 0; }
json_ok(){  printf 'Content-Type: application/json; charset=utf-8\n\n%s\n' "$1"; exit 0; }

Q="${QUERY_STRING:-}"
# URL decode（awk 逐字节，busybox 兼容）
dec(){
  _v="$1"
  printf '%s' "$_v" | awk '{
    s=$0; out=""; i=1;
    while(i<=length(s)){
      c=substr(s,i,1);
      if(c=="+" ){ out=out " "; i++; continue }
      if(c=="%" && i+2<=length(s)){
        h=toupper(substr(s,i+1,2));
        if(h ~ /^[0-9A-F][0-9A-F]$/){
          d=index("0123456789ABCDEF",substr(h,1,1))-1;
          d=d*16 + (index("0123456789ABCDEF",substr(h,2,1))-1);
          out=out sprintf("%c", d); i+=3; continue;
        }
      }
      out=out c; i++;
    }
    printf "%s", out;
  }'
}
rawpar(){
  _k="$1"; _v=$(printf '%s' "$Q" | sed -n "s/.*[?&]$_k=\([^&]*\).*/\1/p")
  [ -z "$_v" ] && _v=$(printf '%s' "$Q" | sed -n "s/^$_k=\([^&]*\).*/\1/p")
  printf '%s' "$_v"
}

enum_roots(){
  roots=''
  [ -d "$BASE_INTERNAL" ] && roots="$BASE_INTERNAL"
  for mp in $(awk '{print $2}' /proc/mounts | grep -E '^/mnt/sd[a-z][0-9]*$' | sort -u); do
    [ -d "$mp" ] && roots="$roots $mp"
  done
  printf '%s' "$roots"
}
check_root(){
  _p="$1"
  for r in $(enum_roots); do
    if [ "$_p" = "$r" ]; then return 0; fi
    case "$_p" in
      "$r"/*) return 0 ;;
    esac
  done
  return 1
}
# JSON 字符串转义：sed 按行处理无法转义换行，用 awk 逐字符拼接（行间插 \n）
jesc(){
  printf '%s' "$1" | awk 'BEGIN{first=1} {
    if(!first) printf "\\n"; first=0;
    s=$0;
    for(i=1;i<=length(s);i++){
      c=substr(s,i,1);
      if(c=="\\") printf "\\\\";
      else if(c=="\"") printf "\\\"";
      else if(c=="\r") printf "\\r";
      else if(c=="\t") printf "\\t";
      else printf "%s", c;
    }
  }'
}

action=$(rawpar 'action')

# 写操作强制 POST，防 CSRF（GET/图片标签不能删改文件）
case "$action" in
  write|mkdir|rename|delete)
    [ "${REQUEST_METHOD:-GET}" = "POST" ] || json_err '写操作必须使用 POST'
    ;;
esac

case "$action" in
  list)
    p=$(dec "$(rawpar 'path')")
    [ -n "$p" ] || json_err '缺少 path'
    real=$(readlink -f "$p" 2>/dev/null)
    [ -n "$real" ] || json_err '路径不存在'
    check_root "$real" || json_err '路径不在允许目录内'
    [ -d "$real" ] || json_err '不是目录'
    printf 'Content-Type: application/json; charset=utf-8\n\n{"ok":true,"path":"%s","items":[' "$(jesc "$real")"
    first=1
    # 含隐藏文件，排除 . ..
    for f in "$real"/* "$real"/.[!.]* "$real"/..?*; do
      [ -e "$f" ] || continue
      nm=$(basename "$f")
      [ "$nm" = '.' -o "$nm" = '..' ] && continue
      tp=$(stat -c '%F' "$f" 2>/dev/null)
      [ "$tp" = 'directory' ] && ty='dir' || ty='file'
      sz=$(stat -c '%s' "$f" 2>/dev/null || echo 0)
      mt=$(stat -c '%Y' "$f" 2>/dev/null || echo 0)
      [ "$first" -eq 0 ] && printf ','
      first=0
      printf '{"name":"%s","path":"%s","type":"%s","size":%s,"mtime":%s}' "$(jesc "$nm")" "$(jesc "$f")" "$ty" "$sz" "$mt"
    done
    printf ']}\n'
    exit 0
    ;;
  read)
    p=$(dec "$(rawpar 'path')")
    real=$(readlink -f "$p" 2>/dev/null)
    [ -n "$real" ] && check_root "$real" && [ -f "$real" ] || json_err '文件不可读'
    sz=$(stat -c '%s' "$real" 2>/dev/null || echo 0)
    [ "$sz" -le 1048576 ] || json_err '文件超过 1MB，不支持在线编辑'
    # 直接让 awk 读文件，保留所有尾部换行（命令替换会吃掉尾换行）
    printf 'Content-Type: application/json; charset=utf-8\n\n{"ok":true,"content":"'
    awk 'BEGIN{first=1} {
      if(!first) printf "\\n"; first=0;
      s=$0;
      for(i=1;i<=length(s);i++){
        c=substr(s,i,1);
        if(c=="\\") printf "\\\\";
        else if(c=="\"") printf "\\\"";
        else if(c=="\r") printf "\\r";
        else if(c=="\t") printf "\\t";
        else printf "%s", c;
      }
    } END{ if(NR>0 && first==0) printf "" }' "$real"
    # awk 逐行处理：每行之间有换行；文件末尾若以换行结尾，awk 不产生额外空行，需补一个 \n
    # 用文件大小与 awk 输出对比不可靠，改用尾字节探测
    if [ "$sz" -gt 0 ] && [ "$(tail -c 1 "$real" | wc -l)" -eq 1 ]; then printf '\\n'; fi
    printf '"}\n'
    exit 0
    ;;
  write)
    p=$(dec "$(rawpar 'path')")
    real=$(readlink -f "$p" 2>/dev/null)
    # 新文件：父目录必须在白名单内
    if [ -z "$real" ]; then
      parent=$(dirname "$p")
      parentreal=$(readlink -f "$parent" 2>/dev/null)
      [ -n "$parentreal" ] && check_root "$parentreal" || json_err '目标目录不在允许范围'
      real="$parentreal/$(basename "$p")"
    else
      check_root "$real" || json_err '路径不在允许目录内'
    fi
    [ -f "$real" ] && [ ! -w "$real" ] && json_err '文件不可写'
    # content 走 POST body（GET query 有长度限制，大文件会 414）
    # 直接 cat 流式写入，避免命令替换吃掉尾部换行
    cat > "$real" 2>/dev/null || json_err '写入失败'
    json_ok '{"ok":true}'
    ;;
  mkdir)
    p=$(dec "$(rawpar 'path')")
    real=$(readlink -f "$p" 2>/dev/null)
    if [ -n "$real" ]; then check_root "$real" || json_err '路径不在允许目录内'; json_err '目录已存在'; fi
    parentreal=$(readlink -f "$(dirname "$p")" 2>/dev/null)
    [ -n "$parentreal" ] && check_root "$parentreal" || json_err '父目录不在允许范围'
    mkdir -p "$parentreal/$(basename "$p")" 2>/dev/null || json_err '创建失败'
    json_ok '{"ok":true}'
    ;;
  rename)
    from=$(dec "$(rawpar 'from')"); to=$(dec "$(rawpar 'to')")
    fr=$(readlink -f "$from" 2>/dev/null)
    [ -n "$fr" ] && check_root "$fr" || json_err '源不在允许目录内'
    tr=$(readlink -f "$to" 2>/dev/null)
    if [ -n "$tr" ]; then check_root "$tr" || json_err '目标不在允许目录内'; json_err '目标已存在'; fi
    tparent=$(readlink -f "$(dirname "$to")" 2>/dev/null)
    [ -n "$tparent" ] && check_root "$tparent" || json_err '目标目录不在允许范围'
    mv "$fr" "$tparent/$(basename "$to")" 2>/dev/null || json_err '重命名失败'
    json_ok '{"ok":true}'
    ;;
  delete)
    p=$(dec "$(rawpar 'path')")
    real=$(readlink -f "$p" 2>/dev/null)
    [ -n "$real" ] && check_root "$real" || json_err '路径不在允许目录内'
    [ "$real" = "$BASE_INTERNAL" ] && json_err '不能删除存储根'
    case "$real" in /mnt/sd[a-z][0-9]*) json_err '不能删除U盘根目录' ;; esac
    if [ -d "$real" ]; then
      rmdir "$real" 2>/dev/null || json_err '目录非空，请先删除内部文件'
    else
      rm -f "$real" 2>/dev/null || json_err '删除失败'
    fi
    json_ok '{"ok":true}'
    ;;
  *)
    json_err '未知 action'
    ;;
esac

-- 文件管理器上传端点（nginx content_by_lua）
-- POST /fm_upload?path=<urlencoded>&append=<0|1>
-- body = 原始二进制分片。前端分片上传，单片 ≤8MB，支持追加，绕开 multipart 解析。
-- 安全：realpath 校验白名单（内置盘 + /mnt/sdX），禁止覆盖目录，禁止写存储根本身。

local json = require "cjson.safe"
local fs = require "nixio.fs"

local function out(t)
  ngx.header.content_type = "application/json; charset=utf-8"
  ngx.say(json.encode(t))
end
local function fail(msg, code)
  ngx.status = code or ngx.HTTP_BAD_REQUEST
  out({ok=false, err=msg})
end

-- 白名单根（与 file_dl.cgi 一致）
local function allowed_roots()
  local roots = {"/mnt/mmcblk0p4"}
  local f = io.open("/proc/mounts", "r")
  if f then
    for line in f:lines() do
      local mp = line:match("^%S+%s+(/mnt/sd%a%d+)%s")
      if mp then roots[#roots+1] = mp end
    end
    f:close()
  end
  return roots
end
local function in_whitelist(p)
  local real = fs.realpath(p)
  if not real then return nil end
  for _, r in ipairs(allowed_roots()) do
    if real == r then return real, true end  -- 根本身（只读标记）
    if real:sub(1, #r+1) == r .. "/" then return real, false end
  end
  return nil
end

-- 强制 POST，防 CSRF（GET/图片标签不能创建或覆盖文件）
if ngx.req.get_method() ~= "POST" then return fail("上传必须使用 POST", 405) end

local path = ngx.var.arg_path
if not path or path == "" then return fail("缺少 path") end
-- ngx.var.arg_* 不做 URL 解码，需手动 unescape（支持 %2F 等）
path = ngx.unescape_uri(path)
if path:sub(1,1) ~= "/" then return fail("路径必须是绝对路径") end

local append = ngx.var.arg_append == "1"

-- 目标路径校验：已存在文件用 realpath；新文件校验父目录
local dir = path:match("^(.*)/[^/]+$") or "/"
local base = fs.realpath(dir)
if not base then return fail("父目录不存在") end
local _, is_root = in_whitelist(base)
if not _ then return fail("父目录不在允许目录内") end
if is_root and path == base then return fail("不能覆盖存储根") end

local target = path
local existing = fs.realpath(path)
if existing then
  local wl = in_whitelist(existing)
  if not wl then return fail("目标不在允许目录内") end
  local st = fs.stat(existing)
  if st and st.type == "dir" then return fail("目标是目录，不能作为文件写入") end
  target = existing
end

-- 读 body（ngx 自动缓冲，≤8MB 在内存，大文件落临时文件）
ngx.req.read_body()
local data = ngx.req.get_body_data()
if not data then
  local bodyfile = ngx.req.get_body_file()
  if bodyfile then
    local bf = io.open(bodyfile, "rb")
    if not bf then return fail("读取上传数据失败") end
    data = bf:read("*a"); bf:close()
  else
    data = ""
  end
end

local mode = append and "ab" or "wb"
local f, err = io.open(target, mode)
if not f then return fail("写入失败：" .. tostring(err)) end
local ok, werr = f:write(data)
f:close()
if not ok then return fail("写数据失败：" .. tostring(werr)) end

out({ok=true, path=target, bytes=#data, append=append})

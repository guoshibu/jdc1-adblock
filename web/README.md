# Web 后台菜单入口

本目录提供官改 Web 后台首页 `main.html` 的「去广告」菜单入口补丁。

## 改动说明

在 `/www/PC/main.html` 的顶部导航栏 `<ul class="status-nav">` 内，「路由状态」`<li>` 之后新增一个菜单项：

```html
<li>
    <div class="position Lineheight">
        <a href="/cgi-bin/adblock.cgi" target="main-iframe" id="adblock">去广告</a>
        <div class="line"></div>
    </div>
</li>
```

## 文件

- `main_patched.html` — 已注入「去广告」菜单的完整文件，可直接替换 `/www/PC/main.html`

> 注意：不同固件版本的 `main.html` 结构可能有差异，建议先备份原文件，再对照本补丁手工插入上述 `<li>` 块，而非直接整体覆盖。

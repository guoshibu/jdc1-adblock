# firmware — 官改过渡固件

本目录存放京东云无线宝一代的官改过渡固件，供刷机使用。

## 文件

| 文件 | 大小 | 校验 | 说明 |
|------|------|------|------|
| `jdcloud-1-transitional.zip` | 18,761,643 B | sha256 `7008f4b2353a17e07af3d2d12f1688464989d59c841221c20a21a809a70af61e` | 原始压缩包（含 `JDC4.0.0.r6636_ssh(根目录含有breed文件).bin` + Bootloader(京东云一代4.0原厂uboot).bin） |

## 说明

- 压缩包内的 `JDC4.0.0.r6636_ssh.bin` 基于官方 JDCOS **4.0.0.r6636** 修改：rootfs 内开放 dropbear SSH（`RootPasswordAuth on` + `Port 22` + 预置 host key），根目录塞入 `breed-mt7621-jd-cloud-1.bin`。
- 刷入后版本显示 `4.0.0.r6636`（比原厂 r6645 低一档，属正常）。

## 刷入方式

1. 解压 `jdcloud-1-transitional.zip`，得到 `JDC4.0.0.r6636_ssh.bin`（及 Bootloader、breed 文件）。
2. 按住 reset 键上电，进入原厂 U-Boot 恢复界面（浏览器访问 `192.168.68.1`）。
3. Upload 选择 `JDC4.0.0.r6636_ssh.bin`，等待刷写完成。（这里建议多等5分钟，避免没有写入完成。）
4. 重启后即可 SSH 登录（`root@192.168.68.1`）。默认账号root，密码是你设置的路由器登录密码。

> ⚠️ 刷机有风险。刷前请备份原厂 mtd 分区（尤其 `mtd0` Bootloader 与 `mtd2` Factory/WiFi 校准）。

## 来源

- 原始出处：GitHub 仓库 [`cbywyz/jdcloud-re-sp-01b-flash`](https://github.com/cbywyz/jdcloud-re-sp-01b-flash)（`firmware/jdcloud-1-transitional.zip`）
- 下载方式：jsDelivr 返回错误页，改用 `ghfast.top` 加速源。

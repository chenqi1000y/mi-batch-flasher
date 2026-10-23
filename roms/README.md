# ROM 包说明

本目录存放小米/红米机型的官方 MIUI 卡刷包（recovery 包，供 OrangeFox / TWRP 卡刷使用）。

> ⚠️ **ROM 包体积约 1.9~2.0 GB，不随仓库分发。** 请自行从小米官方渠道下载对应机型的包，并放入本目录后使用。

## 已随附的 ROM 包（红米 Note 5 / whyred）

| ROM | 文件名 | 版本 | 区域 | MD5 |
|-----|--------|------|------|-----|
| 国行版 | `whyred_cn_recovery_V12.0.3.0.PEICNXM.zip` | MIUI 12 / Android 9 | 中国（CN） | `5cb7befde788183319d5316fca59c1a4` |
| 全球版 | `whyred_global_recovery_V12.0.2.0.PEIMIXM.zip` | MIUI 12 / Android 9 | 国际（Global） | `e714180088c0a750259e63f6bd9a1517` |

> 其他机型（红米 Note 7、小米 8 等）请自行下载对应机型的官方卡刷包，放入本目录即可，工具不限制机型。

## 如何获取 ROM 包

### 方式一：小米官方社区 / 官网

1. 访问小米社区（www.xiaomi.cn）或 MIUI 官网
2. 搜索「红米 Note 5」的线刷/卡刷包
3. 选择 **MIUI 12 / Android 9** 版本（这是 whyred 的官方最终版本）

### 方式二：直接下载（需处理 CDN 限速）

小米 CDN（`bigota.d.miui.com`）对裸请求限速约 20~25 KB/s。本仓库提供了 64 线程并发下载脚本：

```bash
# 国行版
bash dl_cn.sh

# 全球版
bash dl_gl.sh
```

> 脚本已处理：UA/Referer 认证、CDN 断线自动重连、MD5 校验。

## 校验完整性（必须做）

下载完成后，务必核对 MD5，否则可能刷入损坏的包导致失败：

```bash
# Windows（PowerShell）
Get-FileHash whyred_cn_recovery_V12.0.3.0.PEICNXM.zip -Algorithm MD5

# Linux / macOS
md5sum whyred_cn_recovery_V12.0.3.0.PEICNXM.zip
```

## 区域选择

| 机型标识（`ro.boot.hwc`） | 应刷包 |
|--------------------------|--------|
| `CN` | 国行版 |
| `GLOBAL` | 全球版 |

> 工具刷机前会验证硬件身份（SoC = SDM636、屏幕 = 1080x2160），请勿刷错区域。

## 注意

- 本仓库 `.gitignore` 已排除 `*.zip`，ROM 包不会被提交到 Git
- ROM 包版权归小米公司所有，仅供设备恢复使用

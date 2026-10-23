# Mi Batch Flasher（小米/红米批量刷机工具）

> 一款面向**非技术操作员**的图形化批量刷机工具，适用于所有刷了 **OrangeFox / TWRP recovery** 的小米、红米机型，把第三方魔改 ROM 批量刷回官方 MIUI。

[中文说明](./刷机说明.md) · [ROM 下载说明](./roms/README.md) · 版本 `v1.0` · 联系作者 `chenqi1000y`

![Build](https://img.shields.io/badge/build-PyInstaller-blue) ![Platform](https://img.shields.io/badge/platform-Windows-lightgrey) ![License](https://img.shields.io/badge/license-MIT-green)

---

## 这是什么？

你有一批（几十到上百台）小米/红米手机，机器上被刷了各种第三方魔改系统（伪装机型、改指纹、塞广告），需要快速、批量地刷回官方小米 MIUI。

手动一台台操作太慢、太容易出错。这个工具把「推包 → 四清 → 刷入 → 自动重启」全流程自动化，支持**多设备并行**、**实时进度**、**失败重试**，普通操作员双击 exe 就能开工。

> **前提条件**：设备必须已刷入 **OrangeFox（或 TWRP）recovery**。工具通过 recovery 执行卡刷，适配所有支持 OrangeFox 的小米/红米机型。

## 核心特性

| 特性 | 说明 |
|------|------|
| 🖱️ 图形界面 | 设备表格 + 实时日志（按设备着色）+ 状态汇总，双击 exe 即用 |
| 🔀 多设备并行 | 每台设备独立线程，支持 1~10 台并发 |
| 📊 实时进度条 | 推包实时百分比 + 全局进度条，不会误以为卡死 |
| ✅ MD5 强校验 | 推包后手机端 MD5 比对，杜绝 USB 传输损坏导致的 error 7 |
| 🔄 失败重试 | 失败设备右键即可重试，无需重新推包 |
| 🧩 分步执行 | 支持单独执行「推包 / 四清 / 刷入」任一步骤或组合 |
| 🔌 刷完即拔 | 刷入开始即判成功，设备自动重启，流水线作业 |

## 目录结构

```
mi-batch-flasher/
├── flash_gui.py              # 核心：图形界面主程序（Python + tkinter）
├── multiflash.py             # 命令行多设备并行版（备用）
├── oneflash.py               # 命令行单台版（备用）
├── flash_gui.spec            # PyInstaller 打包配置
├── 批量刷机GUI.bat            # GUI 启动器（用系统 Python 启动）
├── dl_cn.sh / dl_gl.sh       # 64 线程并发下载脚本（破解小米 CDN 限速）
├── dist/
│   ├── 批量刷机工具.exe        # 打包好的成品（自包含）
│   ├── roms/                  # 卡刷包放这里（.zip）
│   └── tools/                 # adb.exe / fastboot.exe 及 DLL
└── 刷机说明.md                # 中文详细说明
```

## 快速开始

### 方式一：直接运行 exe（推荐给操作员）

1. 把整个 `dist/` 文件夹拷到任意 Windows 电脑
2. 把对应机型的卡刷包（`.zip`）放进 `dist/roms/`（[下载说明](./roms/README.md)）
3. 双击 `dist/批量刷机工具.exe`
4. 手机进入 OrangeFox recovery 后用 USB 连接电脑
5. 勾选执行步骤 → 点「▶ 开始批量刷机」

> 无需安装 Python，无需任何依赖，`dist/` 是自包含的。

### 方式二：源码运行（开发者）

```bash
# 需要 Python 3（带 tkinter），Windows 自带 Python 3.10 即可
python flash_gui.py
```

### 方式三：自动构建（GitHub Actions）

本项目配置了 GitHub Actions，推送 `v*` 标签即可自动打包 Windows exe 并发布 Release：

```bash
git tag v1.0
git push origin v1.0
```

构建产物会自动上传到对应 Release 页面。

## 刷机流程

```
┌─────────┐   ┌────────┐   ┌──────────┐   ┌──────────────┐
│ 1.推包   │ → │ 2.四清  │ → │ 3.一键刷机 │ → │ 4.自动重启进MIUI │
│ MD5校验  │   │ 保留ROM │   │ 写脚本+刷入 │   │ 首次开机10~15分钟 │
└─────────┘   └────────┘   └──────────┘   └──────────────┘
```

- **步骤 1（推包）**：把 ROM 推送到 `/data/media/0/`，并做 **MD5 强校验**，确保传输无损坏
- **步骤 2（四清）**：清空 data/cache/system，但**保留 ROM**（避免误删导致刷机失败）
- **步骤 3（刷机）**：写入 OrangeFox 安装脚本（LF 换行 + 自动重启），等设备真正开始刷入即判成功
- **完成后**：设备自动重启，首次开机 10~15 分钟卡 MIUI logo 属**正常现象**

## 支持的设备

工具通过 OrangeFox/TWRP recovery 卡刷，**理论上适配所有支持 OrangeFox 的小米/红米机型**。核心刷机逻辑不绑定具体机型，只需放入对应机型的官方卡刷包即可。

**已验证机型**：

| 机型 | 代号 | SoC | 说明 |
|------|------|-----|------|
| 红米 Note 5 / Note 5 Pro | `whyred` | 骁龙 636（SDM636） | 3+32G / 4+64G 等配置通用 |

> 💡 其他小米/红米机型（如红米 Note 7、小米 8 等）只要满足「已刷 OrangeFox + 有官方卡刷包」，理论上同样适用。欢迎提交 Issue 反馈更多已验证机型。

## 前置条件

1. 手机已**解锁 bootloader**
2. 手机已刷入 **OrangeFox / TWRP** recovery
3. Windows 电脑已安装 adb 驱动（`dist/tools/` 内含 adb/fastboot）

## 已知问题与排查

| 现象 | 原因 | 解决 |
|------|------|------|
| 多设备只能识别一台 | 无源 USB HUB 供电不足 | 用带独立供电的 HUB，或直插机箱后置口 |
| 推送失败"传输不完整" | 存储空间不足 | 工具会自动清理应用数据腾空间 |
| 刷机报 error 7 | ROM 传输损坏 | 工具已用 MD5 校验自动拦截重推 |
| 重启后不自动安装 | 脚本 LF/CRLF 换行问题 | 已修复，脚本统一 LF 换行 |
| 刷完无法进系统 | data 加密元数据残留 | 进 MI-Recovery「清除所有数据」即可 |

## 免责声明

⚠️ **本工具仅供刷机技术研究和设备维护使用。**

- 刷机存在**变砖风险**，请确认设备已解锁 bootloader 且能进入 recovery
- 使用本工具造成的任何数据丢失或设备损坏，作者不承担责任
- 请确保刷入的 ROM 与设备型号匹配

## 许可

MIT License

## 联系作者

- GitHub：`chenqi1000y`
- 问题反馈 / 功能建议：请在 GitHub Issues 提交

## 支持项目

如果这个工具对你有帮助，欢迎扫码请作者喝杯咖啡。感谢支持！

![微信赞赏码](assets/wechat-donate.jpg)

---

**版本历史**

- `v1.0`（当前）：首个开源版本，包含 GUI 批量刷机、MD5 校验、分步执行、失败重试等完整功能


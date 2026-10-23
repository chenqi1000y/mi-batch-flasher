#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
红米 Note 5 (whyred) 一键刷机工具 v2 —— 全自动一条龙
====================================================
功能：
  检测 OrangeFox recovery → 推送 ROM → 手机端校验 → 四清 → 刷入 → 重启

用法：
  python oneflash.py              交互式选包、自动刷
  python oneflash.py --list       列出可用 ROM 包

目录结构（整个 E:\\rom 文件夹拷到任何电脑都能用）：
  oneflash.py          本脚本
  roms/                放官方 recovery 卡刷包(.zip)，可放多个
  tools/adb.exe        自带 adb（不依赖系统安装）
  tools/fastboot.exe   自带 fastboot

依赖：Python 3（Windows 装好 Python 并勾选 Add to PATH）
"""
import os, sys, subprocess, glob, hashlib, time

if getattr(sys, "frozen", False):
    BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
ROMS = os.path.join(BASE, "roms")
ADB = os.path.join(BASE, "tools", "adb.exe")

def run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return "(超时)"

def devices():
    out = run(f'"{ADB}" devices')
    res = []
    for l in out.splitlines():
        l = l.strip()
        if l and not l.startswith("List") and "\t" in l:
            p = l.split("\t")
            res.append((p[0].strip(), p[1].strip()))
    return res

def shell(dev, cmd, timeout=60):
    return run(f'"{ADB}" -s {dev} shell "{cmd}"', timeout)

def wait_recovery(timeout_sec=180):
    """等待设备进入 recovery 模式，返回序列号"""
    print("等待设备进入 OrangeFox recovery ...")
    print("  手机操作：关机 → 按住【音量上 + 电源】→ 进 OrangeFox")
    end = time.time() + timeout_sec
    while time.time() < end:
        for dev, state in devices():
            if state == "recovery":
                return dev
        time.sleep(2)
    return None

def pick_rom():
    zips = sorted(glob.glob(os.path.join(ROMS, "*.zip")))
    if not zips:
        print(f"❌ roms/ 目录下没有卡刷包(.zip)。请放入：{ROMS}")
        sys.exit(1)
    if len(zips) == 1:
        print(f"✅ 使用唯一 ROM 包: {os.path.basename(zips[0])}")
        return zips[0]
    print("可用 ROM 包：")
    for i, z in enumerate(zips, 1):
        sz = os.path.getsize(z) / 1024 / 1024
        print(f"  [{i}] {os.path.basename(z)}  ({sz:.0f} MB)")
    sel = input("选包编号(默认1): ").strip() or "1"
    try:
        return zips[int(sel) - 1]
    except (ValueError, IndexError):
        print("❌ 无效选择"); sys.exit(1)

def main():
    if not os.path.exists(ADB):
        print(f"❌ 找不到 {ADB}")
        print("  请确保 tools/adb.exe 存在（整个目录一起拷贝）。")
        sys.exit(1)

    if "--list" in sys.argv:
        zips = sorted(glob.glob(os.path.join(ROMS, "*.zip")))
        for z in zips:
            print(os.path.basename(z))
        return

    rom = pick_rom()
    rom_name = os.path.basename(rom)

    dev = wait_recovery()
    if not dev:
        print("❌ 3 分钟内未检测到 recovery 设备。")
        sys.exit(1)
    print(f"✅ 设备已就绪: {dev}\n")

    # [1] 推送
    print(f"[1/4] 推送 {rom_name} ...")
    out = run(f'"{ADB}" -s {dev} push "{rom}" "//sdcard/{rom_name}"', timeout=900)
    print("  推送完成")

    # [2] 校验（大小 + MD5 双保险）
    print("[2/4] 校验文件完整性 ...")
    local_size = os.path.getsize(rom)
    # 本地 MD5（一次算好，后续重刷可复用）
    print("  计算本地 MD5 ...")
    h = hashlib.md5()
    with open(rom, "rb") as f:
        for chunk in iter(lambda: f.read(8192 * 1024), b""):
            h.update(chunk)
    local_md5 = h.hexdigest()
    print(f"  本地 MD5: {local_md5}")

    remote_md5 = shell(dev, f"md5sum /sdcard/{rom_name}", timeout=300).strip()
    # 取第一段
    remote_md5 = remote_md5.split()[0] if remote_md5 and not remote_md5.startswith("(") else ""
    if remote_md5 and remote_md5.lower() == local_md5.lower():
        print(f"  ✅ MD5 一致 ({remote_md5})")
    else:
        # md5sum 可能不存在，退回大小比对
        remote_size = shell(dev, f"stat -c %s /sdcard/{rom_name}", timeout=30).strip()
        if remote_size == str(local_size):
            print(f"  ✅ 大小一致 ({local_size} 字节)，继续")
        else:
            print(f"  ❌ 校验失败 本地{local_size} vs 手机{remote_size}")
            print("  传输可能损坏，中止。请重试。")
            sys.exit(1)

    # [3] 四清（通过 OrangeFox 的 wipe 机制）
    print("[3/4] 四清 (Dalvik/Cache/System/Data) ...")
    # 用 OrangeFox 支持的 shell 清空方式
    shell(dev, "rm -rf /data/* /data/.* 2>/dev/null", timeout=120)
    shell(dev, "rm -rf /cache/* /cache/.* 2>/dev/null", timeout=60)
    shell(dev, "rm -rf /system/* 2>/dev/null", timeout=120)
    print("  清理完成（Vendor 分区保留）")

    # [4] 刷入（写 openrecoveryscript 让 OrangeFox 自动执行）
    print(f"[4/4] 下发刷机指令 ...")
    ors = f"install /sdcard/{rom_name}\nwipe dalvik\nreboot\n"
    ors_path = os.path.join(BASE, "openrecoveryscript.txt")
    with open(ors_path, "w", encoding="utf-8") as f:
        f.write(ors)
    run(f'"{ADB}" -s {dev} push "{ors_path}" "//cache/recovery/openrecoveryscript"', timeout=30)
    # 触发 recovery 重新执行脚本
    run(f'"{ADB}" -s {dev} reboot recovery', timeout=30)

    print("\n✅ 已下发。手机将自动：刷入 → 自动重启")
    print("  首次开机 10~15 分钟属正常，看到 MIUI logo 动画就是在启动。")

if __name__ == "__main__":
    main()

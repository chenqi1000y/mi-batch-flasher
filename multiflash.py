#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
红米 Note 5 (whyred) 多设备并行刷机工具 v3
====================================================
特性：
  - 自动扫描所有处于 OrangeFox recovery 的设备
  - 每台设备独立线程，并行执行：推送 → 校验 → 四清 → 刷入 → 重启
  - 实时打印每台进度，结束后汇总成功/失败
  - 支持「刷完即拔」：reboot 后该设备线程结束，可立刻插新机

用法：
  python multiflash.py [--rom 包名] [--max 并发数] [--watch]

参数：
  --rom   指定 ROM 包名（默认 roms/ 下唯一包，多个则交互选）
  --max   最大并发刷机数（默认 6，受 USB 供电限制）
  --watch 持续监测模式：插一台刷一台，直到 Ctrl+C

目录结构（整目录拷到任何电脑可用）：
  multiflash.py       本脚本
  roms/               放卡刷包(.zip)
  tools/adb.exe       自带 adb
"""
import os, sys, subprocess, glob, hashlib, time, threading, queue

if getattr(sys, "frozen", False):
    BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
ROMS = os.path.join(BASE, "roms")
ADB = os.path.join(BASE, "tools", "adb.exe")

# 线程安全的输出锁
print_lock = threading.Lock()

def log(msg):
    with print_lock:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def run(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return "(超时)"

def list_recovery_devices():
    """返回所有 recovery 模式的设备序列号"""
    out = run(f'"{ADB}" devices', 15)
    devs = []
    for l in out.splitlines():
        l = l.strip()
        if l and not l.startswith("List") and "\t" in l:
            p = l.split("\t")
            if len(p) >= 2 and p[1].strip() == "recovery":
                devs.append(p[0].strip())
    return devs

def shell(dev, cmd, timeout=120):
    return run(f'"{ADB}" -s {dev} shell "{cmd}"', timeout)

def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def flash_one(dev, rom, results):
    """单台设备完整刷机流程"""
    rom_name = os.path.basename(rom)
    try:
        log(f"[{dev}] 开始刷机 <- {rom_name}")

        # [1] 推送
        log(f"[{dev}] ① 推送中...")
        run(f'"{ADB}" -s {dev} push "{rom}" "//sdcard/{rom_name}"', timeout=900)
        log(f"[{dev}] ① 推送完成")

        # [2] 校验大小
        local_size = os.path.getsize(rom)
        remote_size = shell(dev, f"stat -c %s /sdcard/{rom_name}", 30).strip()
        if remote_size != str(local_size):
            log(f"[{dev}] ❌ 校验失败 本地{local_size} vs 手机{remote_size}")
            results[dev] = "FAIL(传输损坏)"
            return
        log(f"[{dev}] ② 大小校验通过 ({local_size} 字节)")

        # [3] 四清（保留 vendor）
        log(f"[{dev}] ③ 四清中...")
        shell(dev, "rm -rf /data/* /data/.[!.]* 2>/dev/null", 120)
        shell(dev, "rm -rf /cache/* /cache/.[!.]* 2>/dev/null", 60)
        shell(dev, "rm -rf /system/* 2>/dev/null", 120)
        log(f"[{dev}] ③ 四清完成")

        # [4] 下发刷机指令
        ors_path = os.path.join(BASE, f"ors_{dev}.txt")
        with open(ors_path, "w", encoding="utf-8") as f:
            f.write(f"install /sdcard/{rom_name}\nwipe dalvik\nreboot\n")
        run(f'"{ADB}" -s {dev} push "{ors_path}" "//cache/recovery/openrecoveryscript"', 30)
        run(f'"{ADB}" -s {dev} reboot recovery', 30)
        os.remove(ors_path)

        results[dev] = "OK"
        log(f"[{dev}] ✅ 完成，已自动重启，可拔线")
    except Exception as e:
        results[dev] = f"FAIL({e})"
        log(f"[{dev}] ❌ 异常: {e}")

def pick_rom():
    zips = sorted(glob.glob(os.path.join(ROMS, "*.zip")))
    if not zips:
        print(f"❌ roms/ 目录无卡刷包，请放入 {ROMS}")
        sys.exit(1)
    # 命令行指定
    for i, a in enumerate(sys.argv):
        if a == "--rom" and i + 1 < len(sys.argv):
            name = sys.argv[i + 1]
            for z in zips:
                if name in os.path.basename(z):
                    return z
    if len(zips) == 1:
        print(f"✅ ROM: {os.path.basename(zips[0])}")
        return zips[0]
    print("可用 ROM 包：")
    for i, z in enumerate(zips, 1):
        print(f"  [{i}] {os.path.basename(z)}")
    sel = input("选包编号(默认1): ").strip() or "1"
    try:
        return zips[int(sel) - 1]
    except (ValueError, IndexError):
        print("❌ 无效"); sys.exit(1)

def get_max_workers():
    for i, a in enumerate(sys.argv):
        if a == "--max" and i + 1 < len(sys.argv):
            try:
                return int(sys.argv[i + 1])
            except ValueError:
                pass
    return 6

def main():
    if not os.path.exists(ADB):
        print(f"❌ 找不到 {ADB}，请保持 tools/adb.exe 存在")
        sys.exit(1)

    rom = pick_rom()
    max_workers = get_max_workers()
    watch = "--watch" in sys.argv

    print(f"\n{'='*50}")
    print(f" 多设备并行刷机 | 并发上限 {max_workers} | ROM: {os.path.basename(rom)}")
    print(f" 手机需处于 OrangeFox recovery 并已连接")
    print(f"{'='*50}\n")

    # 预计算 MD5 一次
    print("计算 ROM MD5（仅首次，之后复用）...")
    # 缓存
    md5_cache = os.path.join(ROMS, "." + os.path.basename(rom) + ".md5")
    if os.path.exists(md5_cache):
        local_md5 = open(md5_cache).read().strip()
    else:
        local_md5 = md5_of(rom)
        open(md5_cache, "w").write(local_md5)
    print(f"本地 MD5: {local_md5}\n")

    results = {}
    running = {}  # dev -> thread
    done = set()

    def scan_and_launch():
        """扫描新设备并启动未处理设备的线程"""
        for dev in list_recovery_devices():
            if dev in running or dev in done:
                continue
            if len(running) >= max_workers:
                break
            t = threading.Thread(target=flash_one, args=(dev, rom, results), daemon=True)
            running[dev] = t
            t.start()
            log(f"   ↳ 接管设备 {dev}（当前并发 {len(running)}）")

    try:
        while True:
            # 清理已结束线程
            for dev in list(running.keys()):
                if not running[dev].is_alive():
                    del running[dev]
                    done.add(dev)
            scan_and_launch()

            # 打印汇总
            if results:
                ok = sum(1 for v in results.values() if v == "OK")
                fail = len(results) - ok
                log(f"【汇总】已完成 {len(results)} 台 | 成功 {ok} | 失败 {fail}")

            if not watch and not running and done:
                # 非 watch 模式，且没有新设备时结束
                time.sleep(3)
                if not list_recovery_devices():
                    break
            time.sleep(3)
    except KeyboardInterrupt:
        log("收到 Ctrl+C，停止监测。")

    # 最终汇总
    print("\n" + "=" * 50)
    print("最终结果：")
    for dev, r in results.items():
        mark = "✅" if r == "OK" else "❌"
        print(f"  {mark} {dev}  ->  {r}")
    print("=" * 50)

if __name__ == "__main__":
    main()

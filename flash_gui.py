#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小米 / 红米系列 多设备并行刷机 GUI 工具（基于 OrangeFox recovery）
====================================================
图形界面版批量刷机工具，适合非技术操作员使用。
适用于所有刷了 OrangeFox / TWRP recovery 的小米、红米机型。

功能：
  - 自动扫描 OrangeFox recovery 设备
  - 多设备并行刷机（推包 + 校验 + 四清 + 刷入 + 重启）
  - 实时日志（按设备着色）
  - 设备状态表格 + 成功/失败汇总
  - 支持「刷完即拔」，流水线作业

运行：python flash_gui.py
依赖：Python 3（带 tkinter），Windows 自带

目录结构：
  flash_gui.py        本程序
  roms/               放卡刷包(.zip)
  tools/adb.exe       自带 adb
"""
import os
import sys
import glob
import time
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# 兼容 PyInstaller 打包：运行时取 exe 所在目录（而非临时解压目录）
if getattr(sys, "frozen", False):
    BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
ROMS = os.path.join(BASE, "roms")
ADB = os.path.join(BASE, "tools", "adb.exe")

# ============ 底层刷机逻辑 ============

def run(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return "(超时)"

def list_recovery_devices():
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

def push_with_progress(dev, rom, remote_path, progress_cb, stop_event):
    """后台执行 adb push，同时轮询手机端文件大小上报进度"""
    rom_name = os.path.basename(rom)
    local_size = os.path.getsize(rom)
    # remote_path 形如 "/data/media/0/xxx.zip"（手机端绝对路径）
    # 手机端轮询用的路径（去掉可能的前导 // 避免 MSYS 转换）
    poll_path = remote_path.lstrip("/")

    # 启动 adb push 后台进程（// 防 MSYS 路径转换）
    proc = subprocess.Popen(
        f'"{ADB}" -s {dev} push "{rom}" "//{poll_path}"',
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    # 轮询手机端已写入大小，计算百分比
    last = 0
    stall = 0
    while proc.poll() is None:
        if stop_event.is_set():
            try:
                proc.terminate()
            except Exception:
                pass
            return False
        try:
            out = shell(dev, f"stat -c %s /{poll_path}", 8).strip()
            if out.isdigit():
                cur = int(out)
                if cur > last:
                    last = cur
                    stall = 0
                    progress_cb(cur, local_size)
                else:
                    stall += 1
                    if stall >= 20:  # 连续 20 次无增长，判定卡死
                        break
        except Exception:
            stall += 1
        time.sleep(0.5)
    rc = proc.wait()
    # 收尾：上报最终进度
    try:
        out = shell(dev, f"stat -c %s /{poll_path}", 8).strip()
        final = int(out) if out.isdigit() else last
    except Exception:
        final = last
    progress_cb(final, local_size)
    return rc == 0 and final == local_size

def wait_install_done(dev, log, status, stop_event):
    """等待设备重启回 recovery，确认 ROM 已开始真正刷入即算成功。
    刷入完成后 recovery 会自动重启进系统（MIUI），电脑无需监控到完成——
    一直监控反而会因设备重启掉线被误判失败。"""
    # 1) 等设备重启后重新枚举为 recovery（期间设备会消失）
    status("等待重启")
    t0 = time.time()
    back = False
    while time.time() - t0 < 240:
        if stop_event.is_set():
            return False
        if dev in list_recovery_devices():
            back = True
            break
        time.sleep(2)
    if not back:
        log("重启后 240 秒未检测到设备回到 recovery", "err")
        return False
    time.sleep(3)  # 等 recovery 日志系统就绪

    # 2) 轮询日志：只要「真正开始写入」就成功；「一开始就报错」则失败
    status("刷入中")
    log("手机正在刷入系统，刷完会自动重启进 MIUI（约 2~3 分钟）...")
    t0 = time.time()
    while time.time() - t0 < 600:
        if stop_event.is_set():
            return False
        out = shell(dev, "tail -n 40 /tmp/recovery.log 2>/dev/null", 10)
        low = out.lower()
        # 安装真正开始刷入的标志（实际写入 system/vendor 分区块）
        started = any(k in low for k in (
            "patching system image", "performing update",
            "writing 1024 blocks", "writing 4096 blocks",
            "blockimg version", "extract succeeded",
        ))
        # 常见失败标志（一开始就失败，说明没刷进去）
        err_keys = [
            "unable to locate", "error installing", "install failed",
            "ended with signal", "error: 7", "error 7",
            "updater process ended", "signature verification failed",
            "this package is for", "failed to verify", "assert failed",
            "e:failed", "e:aborted", "process ended with error",
            "cannot find", "no such file",
        ]
        hit = [k for k in err_keys if k in low]
        # 先判断失败（优先级高于 started，避免误报成功）
        if hit:
            err_lines = [ln for ln in out.splitlines()
                         if any(k in ln.lower() for k in err_keys)]
            for ln in err_lines[-6:]:
                log(f"recovery: {ln.strip()}", "err")
            log(f"安装失败（{hit[0]}）", "err")
            return False
        # 已真正开始刷入 → 成功，直接返回（recovery 会自动重启）
        if started:
            log("已确认 ROM 正在刷入 system 分区", "ok")
            return True
        status(f"等待刷入 {int(time.time() - t0)}s")
        time.sleep(3)
    log("等待刷入超时（600 秒）", "err")
    return False

import hashlib

def _local_md5(path):
    """计算本地文件 MD5（1.9GB 约 3~5 秒）"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def step_push_rom(dev, rom, log, status, prog, stop_event):
    """步骤1：刷 ROM 进去（推包 + MD5 强校验）
    推送到 /data/media/0/（稳定可写路径，避免 /sdcard 挂载点被四清损坏）。
    关键：必须 MD5 校验，不能只比大小——USB 传输可能出现比特翻转，
    大小一致但内容损坏，导致刷机时报 error 7 / Decompression failed。"""
    rom_name = os.path.basename(rom)
    remote = f"/data/media/0/{rom_name}"
    local_size = os.path.getsize(rom)

    # 预计算本地 MD5（每台设备都复用）
    status("计算本地MD5")
    local_md5 = _local_md5(rom)

    # 检查手机端是否已有「完整且正确」的 ROM（大小 + MD5 都一致才跳过）
    status("检查已有ROM")
    existing_size = shell(dev, f"stat -c %s {remote} 2>/dev/null", 15).strip()
    if existing_size == str(local_size):
        # 大小一致，再核 MD5（防止内容损坏）
        md5_out = shell(dev, f"md5sum {remote} 2>/dev/null", 180).strip()
        remote_md5 = md5_out.split()[0] if md5_out else ""
        if remote_md5 == local_md5:
            log(f"手机已有完好 ROM（{rom_name}，MD5 一致），跳过推送", "ok")
            status("已推包 ✓")
            return True
        else:
            log("手机端 ROM 损坏（MD5 不一致），重新推送覆盖...", "err")

    status("推送中 0%")
    log(f"步骤1/3 推送 ROM <- {rom_name}")
    ok_push = push_with_progress(dev, rom, remote, prog, stop_event)
    if stop_event.is_set():
        status("已停止")
        return False
    if not ok_push:
        log("推送失败或传输不完整", "err")
        status("失败:推送")
        return False
    log("推送完成", "ok")

    # MD5 强校验
    status("MD5校验中")
    md5_out = shell(dev, f"md5sum {remote} 2>/dev/null", 180).strip()
    remote_md5 = md5_out.split()[0] if md5_out else ""
    if remote_md5 != local_md5:
        log(f"MD5 校验失败 本地{local_md5} vs 手机{remote_md5}", "err")
        status("失败:传输损坏")
        return False
    log("MD5 校验通过", "ok")
    status("已推包 ✓")
    return True

def step_wipe(dev, rom_name, log, status, stop_event):
    """步骤2：四清（清 data 数据 / cache / system，但保留 /data/media 里的 ROM）
    关键：不能 rm -rf /data/*，否则会把 /data/media（ROM 存放地）一起删掉。
    注意：不能用 shell for/case 循环——嵌套引号经 Windows cmd -> adb 两层转义会失灵，
    保护条件失效导致 ROM 被删（实测踩坑）。改为电脑端枚举、客户端拼删除列表。"""
    status("四清中")
    log("步骤2/3 四清 data(保留ROM)/cache/system ...")
    if stop_event.is_set():
        status("已停止")
        return False
    # 电脑端枚举 /data 下的条目，排除 media 后逐个删除（命令简单，无嵌套引号）
    out = shell(dev, "ls /data", 30)
    entries = [e.strip() for e in out.splitlines() if e.strip()]
    targets = [e for e in entries if e != "media"]
    if targets:
        shell(dev, "rm -rf " + " ".join("/data/" + e for e in targets), 300)
    # 隐藏文件/目录（不含 media，media 非隐藏）
    shell(dev, "rm -rf /data/.[!.]* /data/..?* 2>/dev/null", 60)
    shell(dev, "rm -rf /cache/* /cache/.[!.]* 2>/dev/null", 60)
    shell(dev, "rm -rf /system/* 2>/dev/null", 120)
    # 校验 ROM 仍然在（四清绝不能误删它）
    if rom_name:
        left = shell(dev, f"stat -c %s /data/media/0/{rom_name} 2>/dev/null", 30).strip()
        if not left.isdigit():
            log("四清后 ROM 丢失！请重新执行步骤1推包", "err")
            status("失败:四清误删ROM")
            return False
        log("四清完成（ROM 完好保留）", "ok")
    else:
        log("四清完成（ROM 已保留）", "ok")
    status("已四清 ✓")
    return True

def step_install(dev, rom_name, log, status, stop_event):
    """步骤3：一键刷机（写脚本 + 重启 + 监控安装完成 + 主动重启）"""
    status("刷入中")
    log("步骤3/3 写入安装脚本并重启到 recovery ...")
    # 兜底：确保 media/0 目录存在（防止之前误清导致安装脚本找不到 ROM）
    shell(dev, "mkdir -p /data/media/0 2>/dev/null", 30)
    # 关键：四清会删掉 /cache/recovery 目录，必须先重建，否则脚本推不上去
    shell(dev, "mkdir -p /cache/recovery 2>/dev/null", 30)
    ors_path = os.path.join(BASE, f"ors_{dev}.txt")
    # 关键：必须用 LF 换行（newline="\n"）。Windows 默认会把 \n 写成 \r\n，
    # 导致 recovery 解析 install 命令时路径末尾带上 \r，报 "Unable to locate zip file"。
    with open(ors_path, "w", encoding="utf-8", newline="\n") as f:
        # 脚本末尾带 reboot：刷完 + wipe dalvik 后 recovery 自动重启进系统
        f.write(f"install /data/media/0/{rom_name}\nwipe dalvik\nreboot\n")
    run(f'"{ADB}" -s {dev} push "{ors_path}" "//cache/recovery/openrecoveryscript"', 30)
    # 校验脚本确实写入了（防止静默失败导致重启后不安装）
    check = shell(dev, "cat /cache/recovery/openrecoveryscript 2>/dev/null", 30)
    if "install /data/media/0/" not in check:
        log("安装脚本写入失败（/cache/recovery 不可写），重试一次...", "err")
        shell(dev, "mkdir -p /cache/recovery", 30)
        run(f'"{ADB}" -s {dev} push "{ors_path}" "//cache/recovery/openrecoveryscript"', 30)
        check = shell(dev, "cat /cache/recovery/openrecoveryscript 2>/dev/null", 30)
        if "install /data/media/0/" not in check:
            log("安装脚本写入失败，放弃重启", "err")
            status("失败:脚本写入")
            try:
                os.remove(ors_path)
            except OSError:
                pass
            return False
    log("安装脚本已确认写入", "ok")
    run(f'"{ADB}" -s {dev} reboot recovery', 30)
    try:
        os.remove(ors_path)
    except OSError:
        pass

    if stop_event.is_set():
        status("已停止")
        return False
    if not wait_install_done(dev, log, status, stop_event):
        if stop_event.is_set():
            status("已停止")
        else:
            status("失败:刷入")
        return False

    status("完成 ✓ 可拔线")
    log("刷机已开始，recovery 会自动重启进 MIUI（首次开机较慢属正常）", "ok")
    return True

def flash_one(dev, rom, log_cb, status_cb, progress_cb=None, stop_event=None,
              steps=(1, 2, 3)):
    """单台设备刷机流程，可指定执行哪些步骤（默认全流程 1+2+3）"""
    rom_name = os.path.basename(rom)
    if stop_event is None:
        stop_event = threading.Event()
    def status(st):
        status_cb(dev, st)
    def log(msg, level="info"):
        log_cb(dev, msg, level)
    def prog(cur, total):
        if progress_cb:
            progress_cb(dev, cur, total)

    try:
        if 1 in steps:
            if not step_push_rom(dev, rom, log, status, prog, stop_event):
                return False
        if 2 in steps:
            if not step_wipe(dev, rom_name, log, status, stop_event):
                return False
        if 3 in steps:
            if not step_install(dev, rom_name, log, status, stop_event):
                return False
        return True
    except Exception as e:
        status(f"失败:{e}")
        log(f"异常: {e}", "err")
        return False

# ============ GUI ============

class FlashGUI:
    def __init__(self, root):
        self.root = root
        root.title("小米/红米 批量刷机工具")
        root.geometry("900x680")
        root.minsize(820, 600)

        self.msg_q = queue.Queue()
        self.running = False
        self.stop_event = threading.Event()
        self.workers = {}      # dev -> thread
        self.results = {}      # dev -> (ok, status)
        self.step_tags = {}    # dev -> 已完成的步骤标签
        self.cur_steps = (1, 2, 3)  # 当前批量步骤（默认全流程）
        self.device_rows = {}  # dev -> 表格行 id
        self.dev_color = {}    # dev -> 颜色
        self.palette = ["#2980b9", "#27ae60", "#e67e22", "#8e44ad",
                        "#16a085", "#d35400", "#2c3e50", "#c0392b"]

        self.build_ui()
        self.root.after(100, self.poll_queue)
        self.root.after(1500, self.auto_refresh)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def auto_refresh(self):
        """周期性自动刷新设备状态（仅在非运行或空闲时全量刷新）"""
        try:
            if not self.running:
                self.refresh_devices()
            else:
                # 运行中只刷新：检测新插入设备由 launch_pending 负责，
                # 这里仅做轻量状态核对，避免干扰刷机中的设备
                pass
        except Exception:
            pass
        self.root.after(3000, self.auto_refresh)

    def build_ui(self):
        # ---- 顶部：ROM 选择 + 并发数 ----
        top = ttk.LabelFrame(self.root, text="刷机配置", padding=10)
        top.pack(fill="x", padx=10, pady=8)

        ttk.Label(top, text="ROM 包:").grid(row=0, column=0, sticky="w", padx=5)
        self.rom_var = tk.StringVar()
        self.rom_combo = ttk.Combobox(top, textvariable=self.rom_var, width=55, state="readonly")
        self.rom_combo.grid(row=0, column=1, sticky="w", padx=5)
        self.load_roms()

        ttk.Label(top, text="并发数:").grid(row=0, column=2, sticky="w", padx=(20, 5))
        self.max_var = tk.StringVar(value="6")
        self.max_spin = ttk.Spinbox(top, from_=1, to=10, textvariable=self.max_var, width=5)
        self.max_spin.grid(row=0, column=3, sticky="w", padx=5)

        self.scan_btn = ttk.Button(top, text="重新扫描设备", command=self.refresh_devices)
        self.scan_btn.grid(row=0, column=4, padx=(20, 5))

        # ---- 第二行：执行步骤选择 ----
        step_row = ttk.Frame(top)
        step_row.grid(row=1, column=0, columnspan=5, sticky="w", pady=(8, 0))
        ttk.Label(step_row, text="执行步骤:").pack(side="left", padx=(5, 2))
        self.step1_var = tk.BooleanVar(value=True)
        self.step2_var = tk.BooleanVar(value=True)
        self.step3_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(step_row, text="1 刷ROM(推包+校验)", variable=self.step1_var).pack(side="left", padx=6)
        ttk.Checkbutton(step_row, text="2 四清", variable=self.step2_var).pack(side="left", padx=6)
        ttk.Checkbutton(step_row, text="3 一键刷机", variable=self.step3_var).pack(side="left", padx=6)
        ttk.Label(step_row, text="（不勾选的步骤会跳过）", foreground="#7f8c8d").pack(side="left", padx=6)

        # ---- 中部左：设备表格 ----
        mid = ttk.Frame(self.root)
        mid.pack(fill="both", expand=True, padx=10, pady=5)

        left = ttk.LabelFrame(mid, text="设备列表", padding=5)
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))

        cols = ("序列号", "状态", "进度")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("序列号", width=160, anchor="w")
        self.tree.column("状态", width=170, anchor="w")
        self.tree.column("进度", width=110, anchor="w")
        self.tree.pack(fill="both", expand=True)

        # 垂直滚动条
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")

        # 右键菜单（失败设备可重试）
        self.menu = tk.Menu(self.root, tearoff=0)
        self.tree.bind("<Button-3>", self.on_right_click)
        self.tree.bind("<Button-2>", self.on_right_click)  # 兼容 macOS
        self.tree.bind("<Double-1>", self.on_double_click)

        # ---- 中部右：日志 ----
        right = ttk.LabelFrame(mid, text="实时日志", padding=5)
        right.pack(side="right", fill="both", expand=True)

        self.log_box = scrolledtext.ScrolledText(right, width=55, height=24,
                                                 state="disabled", font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_config("ok", foreground="#1e8449")
        self.log_box.tag_config("err", foreground="#c0392b")
        self.log_box.tag_config("info", foreground="#2c3e50")

        # ---- 底部：按钮 + 汇总 ----
        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=10, pady=8)

        self.start_btn = ttk.Button(bottom, text="▶ 开始批量刷机", command=self.start)
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = ttk.Button(bottom, text="■ 停止", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        self.summary_var = tk.StringVar(value="就绪 | 等待设备")
        ttk.Label(bottom, textvariable=self.summary_var, font=("", 10, "bold")).pack(side="left", padx=20)

        # ---- 全局进度条 + 提示 ----
        prog_frame = ttk.Frame(self.root)
        prog_frame.pack(fill="x", padx=10, pady=(0, 8))

        self.global_prog = ttk.Progressbar(prog_frame, mode="determinate", maximum=100)
        self.global_prog.pack(side="left", fill="x", expand=True)

        self.prog_label = tk.StringVar(value="")
        ttk.Label(prog_frame, textvariable=self.prog_label, width=24).pack(side="right", padx=(8, 0))

        tip = ttk.Label(self.root, text="提示：推送/刷入会实时显示进度；失败设备可右键 → 重试",
                        foreground="#7f8c8d")
        tip.pack(anchor="w", padx=10, pady=(0, 6))

    def load_roms(self):
        zips = sorted(glob.glob(os.path.join(ROMS, "*.zip")))
        names = [os.path.basename(z) for z in zips]
        self.rom_combo["values"] = names
        if names:
            self.rom_combo.current(0)

    def refresh_devices(self):
        """刷新设备列表，保留已刷完的记录"""
        devs = list_recovery_devices()
        current = set(self.tree.get_children())
        existing = {}
        for row in current:
            vals = self.tree.item(row, "values")
            existing[vals[0]] = row
        # 添加新设备
        for dev in devs:
            if dev not in existing:
                self.tree.insert("", "end", values=(dev, "待刷", ""))
                self.log_box_insert(f"[系统] 检测到新设备 {dev}\n", "info")
        # 更新在线但空闲、且非运行中的设备状态（保持"待刷"或恢复为"待刷"）
        busy_prefix = ("推送中", "校验中", "四清中", "刷入中", "等待重启")
        for dev in devs:
            if dev not in self.workers and dev not in self.results:
                row = existing.get(dev)
                if row is not None:
                    cur_val = self.tree.item(row, "values")
                    if not str(cur_val[1]).startswith(busy_prefix):
                        self.tree.item(row, values=(dev, "待刷", cur_val[2]))
        # 标记被拔掉但无结果的设备
        for dev, row in existing.items():
            if dev not in devs and dev not in self.results and dev not in self.workers:
                self.tree.item(row, values=(dev, "已断开", ""))
        if not devs and not self.workers:
            self.summary_var.set("就绪 | 未检测到 recovery 设备")

    def on_double_click(self, event):
        """双击设备行可查看其最近日志（滚动定位）"""
        pass

    def on_right_click(self, event):
        """右键菜单：失败设备可重试"""
        row = self.tree.identify_row(event.y)
        if not row:
            return
        vals = self.tree.item(row, "values")
        if not vals:
            return
        dev = vals[0]
        status = vals[1] if len(vals) > 1 else ""

        self.tree.selection_set(row)

        self.menu.delete(0, "end")
        is_fail = status.startswith("失败") or status == "已断开"
        is_done_ok = status == "完成 ✓" or status.startswith("完成:")
        is_idle = status in ("待刷",)
        is_busy = dev in self.workers and self.workers[dev].is_alive()

        # 一键刷机（全流程）
        if not is_busy:
            self.menu.add_command(label="▶ 一键刷机（全流程）", command=lambda: self.run_device_steps(dev, (1, 2, 3)))

        # 分步执行子菜单
        step_sub = tk.Menu(self.menu, tearoff=0)
        step_sub.add_command(label="① 刷ROM(推包+校验)", command=lambda: self.run_device_steps(dev, (1,)))
        step_sub.add_command(label="② 四清", command=lambda: self.run_device_steps(dev, (2,)))
        step_sub.add_command(label="③ 刷机(安装系统)", command=lambda: self.run_device_steps(dev, (3,)))
        step_sub.add_separator()
        step_sub.add_command(label="①+② 推包并四清", command=lambda: self.run_device_steps(dev, (1, 2)))
        step_sub.add_command(label="②+③ 四清并刷机", command=lambda: self.run_device_steps(dev, (2, 3)))
        self.menu.add_cascade(label="分步执行 ▸", menu=step_sub)

        if is_fail:
            self.menu.add_separator()
            self.menu.add_command(label=f"↻ 重试 {dev}", command=lambda: self.retry_device(dev))
        self.menu.add_separator()
        self.menu.add_command(label="刷新状态", command=self.refresh_devices)
        self.menu.add_command(label="复制序列号", command=lambda: self.copy_serial(dev))
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def copy_serial(self, dev):
        self.root.clipboard_clear()
        self.root.clipboard_append(dev)
        self.log_box_insert(f"[系统] 已复制序列号 {dev}\n", "info")

    def run_device_steps(self, dev, steps):
        """对单个设备执行指定步骤（用于右键分步操作）"""
        if dev in self.workers and self.workers[dev].is_alive():
            messagebox.showinfo("提示", f"{dev} 正在刷机中")
            return
        rom = self.get_rom_path()
        if not rom or not os.path.exists(rom):
            messagebox.showerror("错误", "请先选择 ROM 包")
            return
        # 清除该设备旧结果，允许重新执行
        if dev in self.results:
            del self.results[dev]
        self.update_device_status(dev, "待刷")
        self.log_box_insert(f"[系统] 对 {dev} 执行步骤 {steps}\n", "info")
        # 确保运行状态
        if not self.running:
            self.running = True
            self.stop_event = threading.Event()
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")

        def wrapper():
            ok = flash_one(dev, rom, self.log_cb, self.status_cb,
                           self.progress_cb, self.stop_event, steps=steps)
            st = self.step_done_label(steps) if ok else "失败"
            self.msg_q.put(("done", dev, ok, st))
        t = threading.Thread(target=wrapper, daemon=True)
        self.workers[dev] = t
        t.start()
        self.refresh_summary()

    def retry_device(self, dev):
        """重试失败设备：清除结果记录，按当前勾选步骤重新触发"""
        if dev in self.workers and self.workers[dev].is_alive():
            messagebox.showinfo("提示", f"{dev} 正在刷机中，无需重试")
            return
        steps = self.get_steps()
        if not steps:
            steps = (1, 2, 3)
        self.run_device_steps(dev, steps)

    def log_box_insert(self, text, tag="info"):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text, tag)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def assign_color(self, dev):
        if dev not in self.dev_color:
            self.dev_color[dev] = self.palette[len(self.dev_color) % len(self.palette)]
        return self.dev_color[dev]

    def log_cb(self, dev, msg, level="info"):
        c = self.assign_color(dev)
        self.msg_q.put(("log", dev, msg, level, c))

    def status_cb(self, dev, st):
        self.msg_q.put(("status", dev, st))

    def progress_cb(self, dev, cur, total):
        self.msg_q.put(("progress", dev, cur, total))

    def poll_queue(self):
        """主线程消费队列，更新 UI"""
        try:
            while True:
                item = self.msg_q.get_nowait()
                if item[0] == "log":
                    _, dev, msg, level, color = item
                    self.log_box.tag_config(f"dev_{dev}", foreground=color)
                    tag = "ok" if level == "ok" else ("err" if level == "err" else f"dev_{dev}")
                    self.log_box_insert(f"[{dev}] {msg}\n", tag)
                elif item[0] == "status":
                    _, dev, st = item
                    self.update_device_status(dev, st)
                elif item[0] == "progress":
                    _, dev, cur, total = item
                    pct = int(cur * 100 / total) if total else 0
                    self.update_device_progress(dev, cur, total, pct)
                elif item[0] == "done":
                    _, dev, ok, st = item
                    self.results[dev] = (ok, st)
                    self.update_device_status(dev, st)
                    self.refresh_summary()
                elif item[0] == "worker_end":
                    _, dev = item
                    if dev in self.workers:
                        del self.workers[dev]
                    # 触发新一轮扫描接管新设备
                    self.launch_pending()
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    def update_device_status(self, dev, st):
        for row in self.tree.get_children():
            if self.tree.item(row, "values")[0] == dev:
                cur = self.tree.item(row, "values")
                prog = cur[2] if len(cur) > 2 else ""
                self.tree.item(row, values=(dev, st, prog))
                break
        else:
            self.tree.insert("", "end", values=(dev, st, ""))

    def update_device_progress(self, dev, cur, total, pct):
        """更新单台设备进度列 + 全局进度条"""
        human = self._fmt_size(cur) + " / " + self._fmt_size(total)
        for row in self.tree.get_children():
            if self.tree.item(row, "values")[0] == dev:
                vals = self.tree.item(row, "values")
                st = vals[1]
                # 推送中则把状态同步为百分比
                if st.startswith("推送中"):
                    st = f"推送中 {pct}%"
                self.tree.item(row, values=(dev, st, f"{pct}% {human}"))
                break
        # 全局进度条显示当前最活跃设备的进度
        self.global_prog["value"] = pct
        self.prog_label.set(f"{pct}%")

    def _fmt_size(self, n):
        if n >= 1 << 30:
            return f"{n / (1 << 30):.2f} GB"
        if n >= 1 << 20:
            return f"{n / (1 << 20):.1f} MB"
        if n >= 1 << 10:
            return f"{n / (1 << 10):.0f} KB"
        return f"{n} B"

    def refresh_summary(self):
        if not self.results:
            return
        ok = sum(1 for v in self.results.values() if v[0])
        fail = len(self.results) - ok
        self.summary_var.set(f"已完成 {len(self.results)} 台 | 成功 {ok} | 失败 {fail}")

    def get_rom_path(self):
        name = self.rom_var.get()
        if not name:
            return None
        return os.path.join(ROMS, name)

    def get_steps(self):
        """根据勾选返回要执行的步骤元组"""
        steps = []
        if self.step1_var.get():
            steps.append(1)
        if self.step2_var.get():
            steps.append(2)
        if self.step3_var.get():
            steps.append(3)
        return tuple(steps)

    def step_done_label(self, steps):
        """根据执行的步骤返回完成状态文案"""
        if set(steps) == {1, 2, 3}:
            return "完成 ✓"
        labels = {1: "已推包", 2: "已四清", 3: "已刷入"}
        parts = [labels[s] for s in steps if s in labels]
        return "完成:" + "/".join(parts) + " ✓"

    def start(self):
        if self.running:
            return
        rom = self.get_rom_path()
        if not rom or not os.path.exists(rom):
            messagebox.showerror("错误", "请先在 roms/ 目录放入卡刷包，并选择 ROM")
            return
        steps = self.get_steps()
        if not steps:
            messagebox.showerror("错误", "请至少勾选一个执行步骤")
            return
        try:
            max_w = int(self.max_var.get())
        except ValueError:
            max_w = 6
        self.max_workers = max_w
        self.cur_steps = steps
        self.running = True
        self.stop_event = threading.Event()
        self.results = {}
        self.step_tags = {}
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        step_desc = "+".join(str(s) for s in steps)
        self.log_box_insert(f"===== 开始批量刷机 | ROM: {os.path.basename(rom)} | 步骤 {step_desc} | 并发 {max_w} =====\n", "info")
        self.launch_pending()

    def launch_pending(self):
        if not self.running:
            return
        # 清理已结束的 worker
        for dev in list(self.workers.keys()):
            if not self.workers[dev].is_alive():
                del self.workers[dev]
        # 扫描并启动新设备
        devs = list_recovery_devices()
        for dev in devs:
            if dev in self.workers or dev in self.results:
                continue
            if len(self.workers) >= self.max_workers:
                break
            rom = self.get_rom_path()
            steps = self.cur_steps
            def wrapper(d=dev):
                ok = flash_one(d, rom, self.log_cb, self.status_cb,
                               self.progress_cb, self.stop_event, steps=steps)
                st = self.step_done_label(steps) if ok else "失败"
                self.msg_q.put(("done", d, ok, st))
            t = threading.Thread(target=wrapper, daemon=True)
            self.workers[dev] = t
            t.start()
            self.log_box_insert(f"[系统] 接管设备 {dev}（并发 {len(self.workers)}/{self.max_workers}）\n", "info")

        # 若无设备且无运行中 worker，2 秒后再扫描
        if not self.workers and self.running:
            self.root.after(2000, self.launch_pending)

    def stop(self):
        self.running = False
        if hasattr(self, "stop_event"):
            self.stop_event.set()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.log_box_insert("===== 已停止 =====\n", "err")

    def on_close(self):
        if self.running:
            if not messagebox.askyesno("确认", "刷机进行中，确定退出？"):
                return
        self.running = False
        self.root.destroy()

def main():
    if not os.path.exists(ADB):
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("错误", f"找不到 {ADB}\n请保持 tools/adb.exe 存在")
        root.destroy()
        sys.exit(1)
    root = tk.Tk()
    FlashGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()

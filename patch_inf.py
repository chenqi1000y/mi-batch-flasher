import os, shutil, sys

SRC = r"E:\rom\tools\MiFlash2018\MiFlash2018-5-28-0\Source\ThirdParty\Google\Driver"
DST = r"E:\rom\driver_d00d"

if os.path.isdir(DST):
    shutil.rmtree(DST)
shutil.copytree(SRC, DST)

inf = os.path.join(DST, "android_winusb.inf")
data = open(inf, "rb").read()

LINE = b"%SingleBootLoaderInterface% = USB_Install, USB\\VID_18D1&PID_D00D\r\n"

added = 0
for sec in (b"[Google.NTx86]\r\n", b"[Google.NTamd64]\r\n"):
    if sec in data:
        # 已存在就不重复加
        if b"VID_18D1&PID_D00D" not in data:
            data = data.replace(sec, sec + LINE, 1)
            added += 1

open(inf, "wb").write(data)

# 验证
txt = open(inf, "rb").read().decode("utf-8", "ignore")
cnt = txt.count("VID_18D1&PID_D00D")
print("patched_sections=%d" % added)
print("VID_18D1&PID_D00D_count=%d" % cnt)
print("dst=%s" % DST)
for i, l in enumerate(txt.splitlines()):
    if "D00D" in l:
        print("  line%d: %s" % (i + 1, l.strip()))

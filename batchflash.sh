#!/bin/bash
# ============================================================
#  红米 Note 5 (whyred) 批量线刷脚本
#  用法: bash batchflash.sh <解压后的固件目录> [并发数]
#  原理: 解析官方 flash_all.bat，逐台并发执行 fastboot 刷机
# ============================================================
ROM_DIR="${1:?用法: bash batchflash.sh <固件目录> [并发数，默认4]}"
MAXJOB="${2:-4}"
ROM_DIR="${ROM_DIR%/}"
ROM_DIR_ABS=$(cd "$ROM_DIR" 2>/dev/null && pwd) || { echo "❌ 固件目录不存在: $ROM_DIR"; exit 1; }

WORK=/e/rom/work
LOGS=$WORK/logs
mkdir -p "$LOGS"
DONE=$WORK/done.txt; FAIL=$WORK/fail.txt
touch "$DONE" "$FAIL"
CMDS=$WORK/cmds.txt

BAT="$ROM_DIR_ABS/flash_all.bat"
if [ ! -f "$BAT" ]; then
  echo "❌ 找不到 $BAT —— 固件目录不对，或该包缺少 flash_all.bat"
  exit 1
fi

# ---------- 1. 解析 flash_all.bat 生成命令模板 ----------
export ROM_DIR_ESC="$ROM_DIR_ABS"
grep -iE '^fastboot[[:space:]]' "$BAT" \
  | sed -e 's/%~dp0/'"$ROM_DIR_ABS"'\//g' \
        -e 's/\\/\//g' \
        -e 's/[[:space:]]*2>&1.*//' \
        -e 's/[[:space:]]*||.*//' \
        -e 's/[[:space:]]*|.*//' \
        -e 's/[[:space:]]*$//' \
        -e 's/fastboot[[:space:]]*%\*/fastboot -s __S__/' \
  | grep -v 'oem lock' \
  > "$CMDS"

TOTALCMD=$(wc -l < "$CMDS")
echo "===== 批次配置 ====="
echo "固件目录 : $ROM_DIR_ABS"
echo "命令条数 : $TOTALCMD"
echo "并发上限 : $MAXJOB"
echo "===================="
if [ "$TOTALCMD" -lt 10 ]; then
  echo "⚠️ 解析出的命令太少($TOTALCMD)，请检查 flash_all.bat 格式"
  head -5 "$CMDS"
  exit 1
fi

# ---------- 2. 单台刷机 ----------
flash_one() {
  local S="$1"
  local LOG="$LOGS/${S}.log"
  : > "$LOG"
  echo "[$(date +%H:%M:%S)] >>> 开始 $S" | tee -a "$LOG"

  # 机型校验：product 必须是 whyred
  local PROD
  PROD=$(fastboot -s "$S" getvar product 2>&1 | grep -oE 'whyred[a-z_]*' | head -1)
  if [ -z "$PROD" ]; then
    echo "[$(date +%H:%M:%S)] ❌ $S 机型校验失败，不是 whyred，跳过" | tee -a "$LOG"
    echo "$S 机型不符" >> "$FAIL"
    return 1
  fi
  echo "[$(date +%H:%M:%S)] 机型确认: $PROD" >> "$LOG"

  local n=0 failn=0
  while IFS= read -r tpl; do
    n=$((n+1))
    local CMD="${tpl//__S__/$S}"
    local OUT
    OUT=$(eval "$CMD" 2>&1)
    echo "$OUT" >> "$LOG"
    if echo "$OUT" | grep -qiE 'FAILED|error:|not found'; then
      failn=$((failn+1))
      echo "[$(date +%H:%M:%S)] ⚠️ 第${n}条失败: $(echo "$CMD" | cut -c1-70)" >> "$LOG"
      echo "$OUT" | head -2 >> "$LOG"
    fi
  done < "$CMDS"

  if [ "$failn" -eq 0 ]; then
    echo "$S OK $(date +%H:%M:%S)" >> "$DONE"
    echo "[$(date +%H:%M:%S)] ✅ $S 刷机完成 ($n 条命令全过)"
  else
    echo "$S 失败${failn}条 $(date +%H:%M:%S)" >> "$FAIL"
    echo "[$(date +%H:%M:%S)] ❌ $S 有 $failn 条命令失败，详见 $LOG"
  fi
}

# ---------- 3. 主调度：流式接管新插入的设备 ----------
echo ""
echo "等待设备进入 fastboot（插一台刷一台，Ctrl+C 停止）..."
echo ""

running=0
while :; do
  for S in $(fastboot devices 2>/dev/null | awk '{print $1}'); do
    grep -q "^$S " "$DONE" 2>/dev/null && continue
    grep -q "^$S " "$FAIL" 2>/dev/null && continue
    [ -f "$WORK/run_$S" ] && continue

    if [ "$running" -ge "$MAXJOB" ]; then break; fi

    touch "$WORK/run_$S"
    running=$((running+1))
    (
      flash_one "$S"
      rm -f "$WORK/run_$S"
    ) &
  done
  running=$(ls "$WORK"/run_* 2>/dev/null | wc -l)
  sleep 3
done

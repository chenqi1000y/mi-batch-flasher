#!/bin/bash
# 全球版 recovery 卡刷包 分段并发下载（备用）
URL="https://bigota.d.miui.com/V12.0.2.0.PEIMIXM/miui_HMNote5Global_V12.0.2.0.PEIMIXM_e714180088_9.0.zip"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
TOTAL=2054967854
N=64
DIR=/e/rom/gl_parts
mkdir -p "$DIR"
CHUNK=$(( (TOTAL + N - 1) / N ))
STATUS=/e/rom/gl_status.txt
: > "$STATUS"

worker() {
  i=$1
  S=$(( i * CHUNK )); E=$(( S + CHUNK - 1 ))
  if [ $E -ge $TOTAL ]; then E=$((TOTAL-1)); fi
  NEED=$(( E - S + 1 )); F="$DIR/p$i"; touch "$F"
  stall=0
  while :; do
    HAVE=$(stat -c %s "$F" 2>/dev/null || echo 0)
    if [ "$HAVE" -ge "$NEED" ]; then echo "OK p$i" >> "$STATUS"; return; fi
    ST=$(( S + HAVE ))
    curl -s --max-time 75 --connect-timeout 15 -A "$UA" -H "Referer: https://www.miui.com/" -r "${ST}-${E}" "$URL" >> "$F" 2>/dev/null
    HAVE2=$(stat -c %s "$F" 2>/dev/null || echo 0)
    if [ "$HAVE2" -le "$HAVE" ]; then stall=$((stall+1)); sleep 2; [ $stall -ge 6 ] && { echo "FAIL p$i" >> "$STATUS"; return; }; else stall=0; fi
  done
}

for i in $(seq 0 $((N-1))); do worker "$i" & done
wait
echo "=== 结果 ==="
echo "完成: $(grep -c '^OK' "$STATUS" 2>/dev/null) / 失败: $(grep -c '^FAIL' "$STATUS" 2>/dev/null)"

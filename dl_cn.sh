#!/bin/bash
# 国行版 recovery 卡刷包 分段并发下载
URL="https://bigota.d.miui.com/V12.0.3.0.PEICNXM/miui_HMNote5_V12.0.3.0.PEICNXM_5cb7befde7_9.0.zip"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
TOTAL=1990614560
N=64
DIR=/e/rom/cn_parts
mkdir -p "$DIR"
CHUNK=$(( (TOTAL + N - 1) / N ))
STATUS=/e/rom/cn_status.txt
: > "$STATUS"

worker() {
  i=$1
  S=$(( i * CHUNK ))
  E=$(( S + CHUNK - 1 ))
  if [ $E -ge $TOTAL ]; then E=$((TOTAL-1)); fi
  NEED=$(( E - S + 1 ))
  F="$DIR/p$i"
  touch "$F"
  stall=0
  while :; do
    HAVE=$(stat -c %s "$F" 2>/dev/null || echo 0)
    if [ "$HAVE" -ge "$NEED" ]; then echo "OK p$i" >> "$STATUS"; return; fi
    ST=$(( S + HAVE ))
    curl -s --max-time 75 --connect-timeout 15 \
      -A "$UA" -H "Referer: https://www.miui.com/" \
      -r "${ST}-${E}" "$URL" >> "$F" 2>/dev/null
    HAVE2=$(stat -c %s "$F" 2>/dev/null || echo 0)
    if [ "$HAVE2" -le "$HAVE" ]; then
      stall=$(( stall + 1 ))
      sleep 2
      if [ $stall -ge 6 ]; then echo "FAIL p$i" >> "$STATUS"; return; fi
    else
      stall=0
    fi
  done
}

for i in $(seq 0 $((N-1))); do worker "$i" & done
wait
echo "=== 下载结果 ==="
echo "完成分片: $(grep -c '^OK' "$STATUS" 2>/dev/null)"
echo "失败分片: $(grep -c '^FAIL' "$STATUS" 2>/dev/null)"

#!/bin/bash
# 自适应分段下载：连接被 CDN 掐断后自动重连补齐
URL="https://bigota.d.miui.com/V12.0.2.0.PEIMIXM/whyred_global_images_V12.0.2.0.PEIMIXM_20201224.0000.00_9.0_global_561698251e.tgz"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
TOTAL=2528152566
N=64
DIR=/e/rom/parts64
mkdir -p "$DIR"
CHUNK=$(( (TOTAL + N - 1) / N ))
STATUS=/e/rom/dl_status.txt
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
echo "=== 结果 ==="
grep -c "^OK" "$STATUS" 2>/dev/null | sed 's/^/完成分片: /'
grep "^FAIL" "$STATUS" 2>/dev/null

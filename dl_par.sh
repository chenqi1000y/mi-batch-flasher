#!/bin/bash
# 分段并发下载 whyred 官方固件（支持断点续传）
URL="https://bigota.d.miui.com/V12.0.2.0.PEIMIXM/whyred_global_images_V12.0.2.0.PEIMIXM_20201224.0000.00_9.0_global_561698251e.tgz"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
TOTAL=2528152566
N=64
DIR=/e/rom/parts64
mkdir -p "$DIR"
CHUNK=$(( (TOTAL + N - 1) / N ))

for i in $(seq 0 $((N-1))); do
  S=$(( i * CHUNK ))
  E=$(( S + CHUNK - 1 ))
  if [ $E -ge $TOTAL ]; then E=$((TOTAL-1)); fi
  NEED=$(( E - S + 1 ))
  F="$DIR/p$i"
  HAVE=0
  if [ -f "$F" ]; then HAVE=$(stat -c %s "$F" 2>/dev/null || echo 0); fi
  if [ "$HAVE" -ge "$NEED" ]; then continue; fi
  START=$(( S + HAVE ))
  (
    curl -s --retry 30 --retry-delay 3 --connect-timeout 20 \
      -A "$UA" -H "Referer: https://www.miui.com/" \
      -r "${START}-${E}" "$URL" >> "$F"
  ) &
done
wait
echo "ALL_PARTS_DONE"
ls -l "$DIR" | awk '{s+=$5} END {print "parts合计:", s, "字节"}'

#!/bin/bash
# 尾巴加速：把未完成区间切成 2MB 小块，64 并发补齐
export URL="https://bigota.d.miui.com/V12.0.2.0.PEIMIXM/whyred_global_images_V12.0.2.0.PEIMIXM_20201224.0000.00_9.0_global_561698251e.tgz"
export UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
TOTAL=2528152566
N=64
C=$(( (TOTAL + N - 1) / N ))
BS=2097152   # 2MB
DIR=/e/rom/parts64
SUB=/e/rom/sub
mkdir -p "$SUB"
: > /e/rom/tasks.txt

for i in $(seq 0 $((N-1))); do
  S=$(( i * C ))
  E=$(( S + C - 1 ))
  if [ $E -ge $TOTAL ]; then E=$((TOTAL-1)); fi
  H=$(stat -c %s "$DIR/p$i" 2>/dev/null || echo 0)
  cur=$(( S + H ))
  while [ "$cur" -le "$E" ]; do
    e2=$(( cur + BS - 1 ))
    if [ $e2 -gt $E ]; then e2=$E; fi
    echo "$i $cur $e2" >> /e/rom/tasks.txt
    cur=$(( e2 + 1 ))
  done
done

echo "待下载小块数: $(wc -l < /e/rom/tasks.txt)"

xargs -P 64 -d '\n' -I{} bash -c '
  set -- {}
  i=$1; s=$2; e=$3
  out="/e/rom/sub/p${i}_$(printf "%010d" $s).bin"
  curl -s --max-time 400 --retry 4 --retry-delay 2 --connect-timeout 15 \
    -A "$UA" -H "Referer: https://www.miui.com/" \
    -r ${s}-${e} "$URL" -o "$out"
' < /e/rom/tasks.txt

echo "TAIL_DONE"
ls /e/rom/sub | wc -l

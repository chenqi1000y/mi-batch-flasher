#!/bin/bash
# 等待所有分片补齐 -> 合并 -> MD5 校验
TOTAL=2528152566
N=64
C=$(( (TOTAL + N - 1) / N ))
DIR=/e/rom/parts64
OUT=/e/rom/whyred_global_V12.0.2.0.PEIMIXM.tgz
EXPECT=561698251e93a3b357fe62e2b7cbec64

tries=0
while :; do
  missing=0
  for i in $(seq 0 $((N-1))); do
    S=$(( i * C )); E=$(( S + C - 1 ))
    if [ $E -ge $TOTAL ]; then E=$((TOTAL-1)); fi
    NEED=$(( E - S + 1 ))
    H=$(stat -c %s "$DIR/p$i" 2>/dev/null || echo 0)
    if [ "$H" -lt "$NEED" ]; then missing=$((missing+1)); fi
  done
  if [ "$missing" -eq 0 ]; then break; fi
  tries=$((tries+1))
  if [ $tries -gt 200 ]; then echo "TIMEOUT 仍缺 $missing 片"; exit 1; fi
  sleep 10
done

echo "=== 分片已齐，开始合并 ==="
: > "$OUT"
for i in $(seq 0 $((N-1))); do cat "$DIR/p$i" >> "$OUT"; done

SIZE=$(stat -c %s "$OUT")
echo "合并完成: ${SIZE} 字节 (预期 ${TOTAL})"
echo "=== MD5 校验 ==="
ACT=$(md5sum "$OUT" | awk '{print $1}')
echo "实际: $ACT"
echo "预期: $EXPECT"
if [ "$ACT" = "$EXPECT" ]; then echo "RESULT=MD5_OK"; else echo "RESULT=MD5_MISMATCH"; fi

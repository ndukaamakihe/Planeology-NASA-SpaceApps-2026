#!/usr/bin/env bash
# fetch_ranges URL FILE NPARTS : finish a partial download with parallel HTTP range requests
url="$1"; out="$2"; n="${3:-12}"
total=$(curl -sIL -m 30 "$url" | grep -i '^content-length' | tail -1 | tr -dc '0-9')
have=$(stat -c %s "$out" 2>/dev/null || echo 0)
rest=$((total - have)); chunk=$(( (rest + n - 1) / n ))
echo "total $total have $have parts $n chunk $chunk"
part() {
  i=$1; s=$((have + i * chunk)); e=$((s + chunk - 1)); [ $e -ge $((total - 1)) ] && e=$((total - 1))
  p="$out.part$i"; want=$((e - s + 1))
  for try in $(seq 1 30); do
    got=$(stat -c %s "$p" 2>/dev/null || echo 0)
    [ "$got" -ge "$want" ] && return 0
    curl -sSL --speed-limit 20000 --speed-time 45 -r $((s + got))-$e "$url" >> "$p" || sleep 2
  done
}
for i in $(seq 0 $((n - 1))); do part $i & done; wait
for i in $(seq 0 $((n - 1))); do cat "$out.part$i" >> "$out" && rm "$out.part$i"; done
echo "final $(stat -c %s "$out") of $total"

#!/usr/bin/env bash
# Measures how far the clock of the robot is ahead of (or behind) the clock of this machine.
#
# Usage: clock_offset.sh [user@host] [samples]       (defaults: turtle@turtlebot.local, 5)
#
# It opens one SSH connection (the password is asked once), asks the robot for its time several
# times and takes the time of this machine just before and just after each question. The robot's
# answer belongs to the middle, so   offset = robot - (before + after) / 2   and the error of one
# sample is at most half of the round trip. The median of the samples is reported.
#
# Run it on the PC. A difference under 0.02 s is fine for SLAM; a larger one makes SLAM and RViz
# print "Lookup would require extrapolation into the future" and the map jumps.

set -euo pipefail

HOST=${1:-turtle@turtlebot.local}
SAMPLES=${2:-5}
SOCK=$(mktemp -u /tmp/tb3-clock-XXXXXX)

cleanup() { ssh -S "$SOCK" -O exit "$HOST" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Opening a connection to $HOST (enter the password once) ..."
ssh -fNM -S "$SOCK" "$HOST"

lines=""
for _ in $(seq 1 "$SAMPLES"); do
  t0=$(date +%s.%N)
  robot=$(ssh -S "$SOCK" "$HOST" 'date +%s.%N' | tr -d '\r\n ')
  t1=$(date +%s.%N)
  [[ -n $robot ]] || { echo "No answer from the robot." >&2; exit 1; }
  lines+="$t0 $robot $t1"$'\n'
  sleep 0.5
done

printf '%s' "$lines" | python3 -c '
import statistics, sys
rows = [tuple(float(x) for x in line.split()) for line in sys.stdin if line.strip()]
offsets = [r - (a + b) / 2 for a, r, b in rows]
trips = [b - a for a, r, b in rows]
for n, (o, t) in enumerate(zip(offsets, trips), 1):
    print(f"  sample {n}: robot minus PC {o:+.3f} s   (round trip {t:.3f} s)")
med = statistics.median(offsets)
print(f"Median: robot minus PC = {med:+.3f} s, error about +-{statistics.median(trips) / 2:.3f} s")
side = "ahead of the PC" if med > 0 else "behind the PC"
if abs(med) < 0.02:
    print("OK: the clocks agree.")
elif abs(med) < 0.1:
    print(f"BORDERLINE: the robot clock is {side} by {abs(med):.3f} s. Fine for slow driving, repeat later to see the drift.")
else:
    print(f"TOO LARGE: the robot clock is {side} by {abs(med):.3f} s.")
    print("Find out which machine is off: the PC with  chronyc tracking  and  w32tm /stripchart /computer:pool.ntp.org /samples:3 /dataonly  (Windows),")
    print("the robot with  timedatectl  (see docs/troubleshooting.md, The clocks of the PC and the robot differ).")
'

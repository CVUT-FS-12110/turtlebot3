#!/usr/bin/env bash
# Sanity checks for a TurtleBot3 + ROS 2 Jazzy setup (run on the robot or on the PC).
#
# Usage: ./check.sh [other-host-ip]
#   other-host-ip  optional: ping the other machine (PC from the robot, or robot from the PC)

PEER=${1:-}
FAILS=0

green=$'\e[32m'; yellow=$'\e[33m'; red=$'\e[31m'; reset=$'\e[0m'
ok()   { echo "${green}[ OK ]${reset} $*"; }
warn() { echo "${yellow}[WARN]${reset} $*"; }
fail() { echo "${red}[FAIL]${reset} $*"; FAILS=$((FAILS + 1)); }

# --- Environment ------------------------------------------------------------

echo "Environment"
[[ -n ${ROS_DISTRO:-} ]] && ok "ROS_DISTRO=$ROS_DISTRO" || fail "ROS is not sourced (open a new terminal or: source ~/.bashrc)"
[[ ${ROS_DISTRO:-} == jazzy || -z ${ROS_DISTRO:-} ]] || warn "ROS_DISTRO is $ROS_DISTRO, expected jazzy"
[[ -n ${ROS_DOMAIN_ID:-} ]] && ok "ROS_DOMAIN_ID=$ROS_DOMAIN_ID (must match on PC and robot)" || fail "ROS_DOMAIN_ID is not set"
[[ -n ${TURTLEBOT3_MODEL:-} ]] && ok "TURTLEBOT3_MODEL=$TURTLEBOT3_MODEL" || fail "TURTLEBOT3_MODEL is not set"
if [[ ${RMW_IMPLEMENTATION:-} == rmw_cyclonedds_cpp ]]; then
  ok "RMW_IMPLEMENTATION=rmw_cyclonedds_cpp (must be the same on PC and robot)"
else
  warn "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-<default>}; the other machine must use the same one"
fi

# --- Robot hardware (only when this looks like the Raspberry Pi) ----------------

if grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
  echo; echo "Robot hardware"
  [[ -e /dev/ttyACM0 ]] && ok "OpenCR found at /dev/ttyACM0" || fail "/dev/ttyACM0 missing: OpenCR not connected or not powered (turn its switch on)"
  [[ -e /dev/ttyUSB0 ]] && ok "LiDAR found at /dev/ttyUSB0" || warn "/dev/ttyUSB0 missing: LDS-01 not connected (LDS-02/03 use other ports)"
  id -nG | grep -qw dialout && ok "user is in the dialout group" || fail "user is not in dialout (log out and back in after the installer)"
  if command -v iw >/dev/null; then
    for dev in /sys/class/net/wl*; do
      [[ -e $dev ]] || continue
      iface=${dev##*/}
      ps=$(iw dev "$iface" get power_save 2>/dev/null | awk '{print $NF}')
      [[ $ps == off ]] && ok "Wi-Fi power save is off on $iface" || warn "Wi-Fi power save on $iface is '${ps:-unknown}' (can cause lag over Wi-Fi)"
    done
  fi
  mem_kb=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
  (( mem_kb > 150000 )) && ok "free memory: $((mem_kb / 1024)) MB" || warn "only $((mem_kb / 1024)) MB memory available"
fi

# --- Network ----------------------------------------------------------------

if [[ -n $PEER ]]; then
  echo; echo "Network"
  ping -c 2 -W 2 "$PEER" >/dev/null 2>&1 && ok "ping $PEER" || fail "cannot ping $PEER"
fi

# --- ROS graph ----------------------------------------------------------------

if command -v ros2 >/dev/null; then
  echo; echo "ROS graph (needs bring-up running on the robot)"
  topics=$(timeout 15 ros2 topic list 2>/dev/null || true)
  for t in /scan /odom /imu /battery_state /joint_states; do
    grep -qx "$t" <<< "$topics" && ok "topic $t visible" || warn "topic $t not visible"
  done
fi

echo
(( FAILS == 0 )) && echo "No failures." || { echo "$FAILS check(s) failed."; exit 1; }

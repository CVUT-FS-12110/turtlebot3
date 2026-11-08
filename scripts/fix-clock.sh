#!/usr/bin/env bash
# Keeps the clock of this machine in sync, so the PC and the robot agree on the time.
#
# The PC and the robot stamp their messages with their own clocks. When they differ by more than a few
# hundredths of a second, SLAM and RViz report "Lookup would require extrapolation into the future",
# drop scans, and the map jumps and turns. The WSL2 clock in particular drifts (about 1000 ppm, i.e.
# 0.6 s in 10 minutes) and chrony alone could not correct it there.
#
# Usage: fix-clock.sh [--check] [--dry-run]
#   (no option)  set the clock synchronisation up, then report
#   --check      only report the state, change nothing
#   --dry-run    print the commands instead of running them
#
# WSL2 (the PC):  installs chrony and lets it follow the Windows host clock (/dev/ptp_hyperv) next to
#                 the usual NTP servers.
# Elsewhere (the robot, native Ubuntu): switches on network time synchronisation (timedatectl).
# Safe to run again; what is done already is skipped.

set -euo pipefail

CHECK=0
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=1 ;;
    -n|--dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

IS_WSL=0
grep -qi microsoft /proc/version 2>/dev/null && IS_WSL=1
CHRONY_CONF=/etc/chrony/conf.d/wsl-hyperv.conf

run() {
  echo "   \$ $*"
  [[ $DRY_RUN -eq 1 ]] || bash -c "$*"
}

# report - prints how far the clock is from the reference and whether that is good enough.
report() {
  if command -v chronyc >/dev/null 2>&1 && chronyc tracking >/dev/null 2>&1; then
    chronyc tracking | grep -E '^(Reference ID|System time)' | sed 's/^/   /'
    local offset
    offset=$(chronyc tracking | awk '/^System time/ {print $4}')
    if awk -v o="$offset" 'BEGIN {exit !(o < 0.02)}'; then
      echo "   OK: the clock is within 20 ms of the reference."
    else
      echo "   WARNING: the clock is ${offset} s off. Wait a minute and run: $0 --check"
      return 1
    fi
  elif command -v timedatectl >/dev/null 2>&1; then
    timedatectl 2>/dev/null | grep -E 'System clock synchronized|NTP service' | sed 's/^/   /'
    if [[ $(timedatectl show -p NTPSynchronized --value 2>/dev/null) == yes ]]; then
      echo "   OK: the clock is synchronised over the network."
    else
      echo "   WARNING: the clock is not synchronised yet; it can take a minute after switching it on."
      return 1
    fi
  else
    echo "   Cannot tell: neither chronyc nor timedatectl is available."
    return 1
  fi
}

if [[ $CHECK -eq 1 ]]; then
  report
  exit $?
fi

if [[ $IS_WSL -eq 1 ]]; then
  if [[ ! -d /run/systemd/system ]]; then
    echo "systemd is not running in this WSL, so the clock cannot be kept in sync." >&2
    echo "Add this to /etc/wsl.conf, run 'wsl --shutdown' in Windows and start this script again:" >&2
    printf '   [boot]\n   systemd=true\n' >&2
    exit 1
  fi
  if [[ ! -e /dev/ptp_hyperv ]]; then
    echo "WARNING: /dev/ptp_hyperv is missing (old WSL kernel?). Run 'wsl --update' in Windows." >&2
    echo "chrony will use the NTP servers only, which cannot correct the WSL2 clock well." >&2
    dpkg -s chrony >/dev/null 2>&1 || run "sudo apt-get install -y chrony"
    run "sudo systemctl enable --now chrony"
  elif grep -qs 'ptp_hyperv' "$CHRONY_CONF" && systemctl is-active --quiet chrony; then
    echo "   chrony already follows the Hyper-V clock."
  else
    dpkg -s chrony >/dev/null 2>&1 || run "sudo apt-get install -y chrony"
    run "printf '%s\n' '# Windows host clock via Hyper-V; the WSL2 clock alone drifts by about 1000 ppm.' 'refclock PHC /dev/ptp_hyperv poll 3 dpoll -2 offset 0' | sudo tee $CHRONY_CONF >/dev/null"
    run "sudo systemctl enable chrony && sudo systemctl restart chrony"
    [[ $DRY_RUN -eq 1 ]] || { echo "   Waiting 30 s for chrony to lock on ..."; sleep 30; }
  fi
elif [[ $(timedatectl show -p NTPSynchronized --value 2>/dev/null) == yes ]]; then
  echo "   The clock is already synchronised over the network."
else
  run "sudo timedatectl set-ntp true"
  [[ $DRY_RUN -eq 1 ]] || { echo "   Waiting 20 s for the first synchronisation ..."; sleep 20; }
fi

[[ $DRY_RUN -eq 1 ]] && exit 0
report

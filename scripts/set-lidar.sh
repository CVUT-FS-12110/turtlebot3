#!/usr/bin/env bash
# Switches an already installed robot to another LiDAR, without running the whole installer again.
#
# Usage: set-lidar.sh [--dry-run] <LDS-01|RPLIDAR-A1>
#   --dry-run  print the commands instead of running them
#
# Run it on the ROBOT (Raspberry Pi). It installs the driver package of the new LiDAR if it is
# missing and sets LDS_MODEL in the block that scripts/install.sh keeps in ~/.bashrc.
# Safe to run again; what is done already is skipped.
# (LDS-02 and LDS-03 need their driver built from source: run scripts/install.sh for those.)

set -euo pipefail

ROS_DISTRO_NAME=jazzy
DRY_RUN=0
MODEL=""
for arg in "$@"; do
  case "$arg" in
    -n|--dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    LDS-01|RPLIDAR-A1) MODEL=$arg ;;
    *) echo "Unknown argument: $arg (use LDS-01 or RPLIDAR-A1)" >&2; exit 1 ;;
  esac
done
[[ -n $MODEL ]] || { echo "Usage: set-lidar.sh [--dry-run] <LDS-01|RPLIDAR-A1>" >&2; exit 1; }

run() {
  echo "   \$ $*"
  [[ $DRY_RUN -eq 1 ]] || bash -c "$*"
}

case $MODEL in
  RPLIDAR-A1) PKG=ros-$ROS_DISTRO_NAME-rplidar-ros ;;
  LDS-01)     PKG=ros-$ROS_DISTRO_NAME-hls-lfcd-lds-driver ;;
esac

if dpkg-query -W -f='${Status}' "$PKG" 2>/dev/null | grep -q '^install ok installed'; then
  echo "   $PKG is already installed"
else
  run "sudo apt-get -o DPkg::Lock::Timeout=900 update && sudo apt-get -o DPkg::Lock::Timeout=900 install -y $PKG"
fi

BEGIN_MARK="# >>> turtlebot3 >>>"
END_MARK="# <<< turtlebot3 <<<"
if ! grep -qs "^$BEGIN_MARK\$" ~/.bashrc; then
  echo "~/.bashrc has no installer block; run scripts/install.sh first." >&2
  exit 1
fi
if sed -n "/^$BEGIN_MARK\$/,/^$END_MARK\$/p" ~/.bashrc | grep -q '^export LDS_MODEL='; then
  run "sed -i '/^$BEGIN_MARK\$/,/^$END_MARK\$/ s/^export LDS_MODEL=.*/export LDS_MODEL=$MODEL/' ~/.bashrc"
else
  run "sed -i '/^$END_MARK\$/ i export LDS_MODEL=$MODEL' ~/.bashrc"
fi

echo
echo "LDS_MODEL is now $MODEL. Open a new terminal (or: source ~/.bashrc), then start the bring-up with"
echo "  ros2 launch ~/turtlebot3-setup/robot/launch/bringup.launch.py"
echo "(not turtlebot3_bringup's own robot.launch.py: it does not know the RPLiDAR)."

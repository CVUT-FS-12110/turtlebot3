#!/usr/bin/env bash
# Interactive installer for TurtleBot3 + ROS 2 Jazzy on Ubuntu 24.04.
#
# Roles:
#   pc     - remote PC (native Ubuntu or WSL2): ROS 2 desktop, Gazebo, SLAM, Nav2, simulation
#   robot  - Raspberry Pi on the robot: ROS 2 base, LiDAR driver, bring-up, OpenCR firmware
#
# Usage: ./install.sh [--yes] [--dry-run]
#   --yes      accept all defaults without asking
#   --dry-run  print the commands instead of running them

set -euo pipefail

ROS_DISTRO_NAME=jazzy
ASSUME_YES=0
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    -n|--dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

# --- Helpers ----------------------------------------------------------------

bold=$'\e[1m'; green=$'\e[32m'; yellow=$'\e[33m'; red=$'\e[31m'; reset=$'\e[0m'

step() { echo; echo "${bold}${green}==> $*${reset}"; }
info() { echo "    $*"; }
warn() { echo "${yellow}WARNING: $*${reset}"; }
die()  { echo "${red}ERROR: $*${reset}" >&2; exit 1; }

# Run a shell command string, or only print it in dry-run mode.
run() {
  echo "    ${bold}\$ $*${reset}"
  [[ $DRY_RUN -eq 1 ]] || bash -c "$*"
}

# ask VAR "Question" default
ask() {
  # Locals are prefixed so they do not shadow the caller's variable name.
  local __var=$1 __question=$2 __default=$3 __reply
  if [[ $ASSUME_YES -eq 1 ]]; then
    __reply=$__default
  else
    read -r -p "$__question [$__default]: " __reply
    __reply=${__reply:-$__default}
  fi
  printf -v "$__var" '%s' "$__reply"
}

# choose VAR "Question" default option1 option2 ...
choose() {
  local __var=$1 question=$2 default=$3; shift 3
  local reply
  while true; do
    ask reply "$question ($(IFS=/; echo "$*"))" "$default"
    for opt in "$@"; do
      [[ $reply == "$opt" ]] && { printf -v "$__var" '%s' "$reply"; return; }
    done
    echo "    Please enter one of: $*"
  done
}

# confirm "Question" default(y/n) -> exit status
confirm() {
  local reply
  ask reply "$1 (y/n)" "$2"
  [[ $reply =~ ^[Yy] ]]
}

# ROS setup scripts reference unset variables, so relax nounset while sourcing.
ros_source() {
  set +u
  # shellcheck disable=SC1090
  source "$1"
  set -u
}

# --- Preflight --------------------------------------------------------------

[[ $EUID -ne 0 ]] || die "Run as a normal user, not root (sudo is used where needed)."
command -v sudo >/dev/null || die "sudo is required."

# shellcheck disable=SC1091
. /etc/os-release
if [[ ${VERSION_CODENAME:-} != noble ]]; then
  warn "ROS 2 Jazzy targets Ubuntu 24.04 (noble); this system is ${PRETTY_NAME:-unknown}."
  confirm "Continue anyway?" n || exit 1
fi

IS_WSL=0
grep -qi microsoft /proc/version 2>/dev/null && IS_WSL=1

IS_PI=0
grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null && IS_PI=1

MEM_MB=$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)

# --- Questions --------------------------------------------------------------

echo "${bold}TurtleBot3 + ROS 2 Jazzy installer${reset}"
[[ $DRY_RUN -eq 1 ]] && warn "Dry run: commands are printed, not executed."
info "Detected: ${PRETTY_NAME:-unknown}, ${MEM_MB} MB RAM$([[ $IS_WSL -eq 1 ]] && echo ', WSL2')$([[ $IS_PI -eq 1 ]] && echo ', Raspberry Pi')"
echo

default_role=pc
[[ $IS_PI -eq 1 ]] && default_role=robot

choose ROLE "Install for" "$default_role" pc robot
choose TB3_MODEL "TurtleBot3 model" burger burger waffle waffle_pi
ask DOMAIN_ID "ROS_DOMAIN_ID (must match on PC and robot)" 30
ask WS_DIR "Workspace directory" "$HOME/turtlebot3_ws"
WS_DIR=${WS_DIR/#\~/$HOME}

if [[ $IS_WSL -eq 1 && $WS_DIR == /mnt/* ]]; then
  warn "Workspaces under /mnt are very slow in WSL; a Linux path like ~/turtlebot3_ws is recommended."
fi

DO_SWAP=0; DO_NO_AUTOUPGRADE=0; DO_OPENCR=0; LDS_MODEL=""
if [[ $ROLE == robot ]]; then
  choose LDS_MODEL "LiDAR model" LDS-01 LDS-01 LDS-02 LDS-03
  if [[ $MEM_MB -lt 2048 && ! -f /swapfile ]]; then
    confirm "Less than 2 GB RAM: create a 2 GB swap file (needed for the build)?" y && DO_SWAP=1
  fi
  confirm "Disable automatic apt upgrades (they block apt and use memory on a Pi)?" y && DO_NO_AUTOUPGRADE=1
  confirm "Flash the OpenCR firmware now (OpenCR must be connected over USB)?" n && DO_OPENCR=1
fi

BUILD_ARGS="--symlink-install"
[[ $ROLE == robot || $MEM_MB -lt 2048 ]] && BUILD_ARGS+=" --parallel-workers 1"

echo
echo "${bold}Summary${reset}"
info "Role:            $ROLE"
info "Model:           $TB3_MODEL"
info "ROS_DOMAIN_ID:   $DOMAIN_ID"
info "Workspace:       $WS_DIR"
if [[ $ROLE == robot ]]; then
  info "LiDAR:           $LDS_MODEL"
  info "Swap file:       $([[ $DO_SWAP -eq 1 ]] && echo yes || echo no)"
  info "No auto-upgrade: $([[ $DO_NO_AUTOUPGRADE -eq 1 ]] && echo yes || echo no)"
  info "Flash OpenCR:    $([[ $DO_OPENCR -eq 1 ]] && echo yes || echo no)"
  info "The build can take over an hour on a Raspberry Pi; keep the robot on wall power."
fi
echo
confirm "Start installation?" y || exit 0

# --- Robot system preparation -----------------------------------------------

if [[ $DO_NO_AUTOUPGRADE -eq 1 ]]; then
  step "Disabling automatic apt upgrades"
  run "sudo sed -i 's/\"1\"/\"0\"/' /etc/apt/apt.conf.d/20auto-upgrades"
fi

if [[ $DO_SWAP -eq 1 ]]; then
  step "Creating a 2 GB swap file"
  run "sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile"
  run "grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab"
fi

# --- ROS 2 apt repository ---------------------------------------------------

step "Adding the ROS 2 apt repository"
if dpkg -s ros2-apt-source >/dev/null 2>&1; then
  info "Already configured, skipping."
else
  run "sudo apt-get update && sudo apt-get install -y software-properties-common curl"
  run "sudo add-apt-repository -y universe"
  run 'v=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F tag_name | awk -F\" "{print \$4}") && curl -fL -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${v}/ros2-apt-source_${v}.$(. /etc/os-release && echo $VERSION_CODENAME)_all.deb" && sudo dpkg -i /tmp/ros2-apt-source.deb'
fi
run "sudo apt-get update && sudo apt-get upgrade -y"

# --- Packages ---------------------------------------------------------------

step "Installing ROS 2 $ROS_DISTRO_NAME packages"
if [[ $ROLE == pc ]]; then
  run "sudo apt-get install -y git ros-$ROS_DISTRO_NAME-desktop ros-dev-tools \
    ros-$ROS_DISTRO_NAME-ros-gz \
    ros-$ROS_DISTRO_NAME-cartographer ros-$ROS_DISTRO_NAME-cartographer-ros \
    ros-$ROS_DISTRO_NAME-navigation2 ros-$ROS_DISTRO_NAME-nav2-bringup"
else
  run "sudo apt-get install -y git ros-$ROS_DISTRO_NAME-ros-base ros-dev-tools \
    ros-$ROS_DISTRO_NAME-hls-lfcd-lds-driver ros-$ROS_DISTRO_NAME-turtlebot3-msgs \
    ros-$ROS_DISTRO_NAME-dynamixel-sdk ros-$ROS_DISTRO_NAME-xacro libudev-dev"
fi

# --- Workspace --------------------------------------------------------------

step "Cloning TurtleBot3 sources into $WS_DIR/src"
run "mkdir -p '$WS_DIR/src'"

clone() {
  local repo=$1 dir="$WS_DIR/src/${1##*/}"
  if [[ -d $dir ]]; then
    info "${repo##*/} already present, skipping."
  else
    run "git clone -b $ROS_DISTRO_NAME https://github.com/$repo.git '$dir'"
  fi
}

if [[ $ROLE == pc ]]; then
  clone ROBOTIS-GIT/DynamixelSDK
  clone ROBOTIS-GIT/turtlebot3_msgs
  clone ROBOTIS-GIT/turtlebot3
  clone ROBOTIS-GIT/turtlebot3_simulations
else
  clone ROBOTIS-GIT/turtlebot3
  [[ $LDS_MODEL == LDS-02 ]] && clone ROBOTIS-GIT/ld08_driver
  [[ $LDS_MODEL == LDS-03 ]] && clone ROBOTIS-GIT/coin_d4_driver
  # SLAM and navigation run on the PC; they are too heavy to build on the Pi.
  run "rm -rf '$WS_DIR/src/turtlebot3/turtlebot3_cartographer' '$WS_DIR/src/turtlebot3/turtlebot3_navigation2'"
fi

if [[ $ROLE == pc ]]; then
  step "Installing dependencies with rosdep"
  run "[ -f /etc/ros/rosdep/sources.list.d/20-default.list ] || sudo rosdep init"
  run "rosdep update"
  run "source /opt/ros/$ROS_DISTRO_NAME/setup.bash && rosdep install --from-paths '$WS_DIR/src' --ignore-src -y --rosdistro $ROS_DISTRO_NAME"
fi

step "Building the workspace (colcon build $BUILD_ARGS)"
run "source /opt/ros/$ROS_DISTRO_NAME/setup.bash && cd '$WS_DIR' && colcon build $BUILD_ARGS"

# --- Robot hardware access --------------------------------------------------

if [[ $ROLE == robot ]]; then
  step "Installing udev rules for OpenCR and the LiDAR"
  run "sudo cp '$WS_DIR/src/turtlebot3/turtlebot3_bringup/script/99-turtlebot3-cdc.rules' /etc/udev/rules.d/"
  run "sudo udevadm control --reload-rules && sudo udevadm trigger"
  run "sudo usermod -aG dialout '$USER'"
fi

if [[ $DO_OPENCR -eq 1 ]]; then
  step "Flashing the OpenCR firmware ($TB3_MODEL)"
  run "sudo dpkg --add-architecture armhf && sudo apt-get update && sudo apt-get install -y libc6:armhf"
  run "tmp=\$(mktemp -d) && cd \"\$tmp\" \
    && wget -q https://github.com/ROBOTIS-GIT/OpenCR-Binaries/raw/master/turtlebot3/ROS2/latest/opencr_update.tar.bz2 \
    && tar -xjf opencr_update.tar.bz2 && cd opencr_update \
    && ./update.sh /dev/ttyACM0 $TB3_MODEL.opencr"
  info "Test: hold SW1 to drive forward, SW2 to rotate."
fi

# --- Environment ------------------------------------------------------------

step "Writing environment settings to ~/.bashrc"
BEGIN_MARK="# >>> turtlebot3 >>>"
END_MARK="# <<< turtlebot3 <<<"
ENV_BLOCK="$BEGIN_MARK
source /opt/ros/$ROS_DISTRO_NAME/setup.bash
source $WS_DIR/install/setup.bash
export ROS_DOMAIN_ID=$DOMAIN_ID
export TURTLEBOT3_MODEL=$TB3_MODEL"
[[ -n $LDS_MODEL ]] && ENV_BLOCK+="
export LDS_MODEL=$LDS_MODEL"
ENV_BLOCK+="
$END_MARK"

if [[ -f ~/.bashrc ]] && sed "/^$BEGIN_MARK\$/,/^$END_MARK\$/d" ~/.bashrc | grep -q 'TURTLEBOT3_MODEL\|ROS_DOMAIN_ID'; then
  warn "~/.bashrc already sets TURTLEBOT3_MODEL or ROS_DOMAIN_ID outside the installer block; remove those lines to avoid conflicts."
fi
# Replace a previous installer block, then append the current one.
run "sed -i '/^$BEGIN_MARK\$/,/^$END_MARK\$/d' ~/.bashrc"
if [[ $DRY_RUN -eq 1 ]]; then
  echo "    ${bold}\$ cat >> ~/.bashrc${reset}"
  sed 's/^/      /' <<< "$ENV_BLOCK"
else
  printf '%s\n' "$ENV_BLOCK" >> ~/.bashrc
fi

# --- Done -------------------------------------------------------------------

step "Done"
info "Open a new terminal (or run: source ~/.bashrc), then:"
if [[ $ROLE == pc ]]; then
  info "  ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py"
  info "  ros2 run turtlebot3_teleop teleop_keyboard"
else
  info "  ros2 launch turtlebot3_bringup robot.launch.py"
  info "Log out and back in once so the dialout group membership applies."
fi

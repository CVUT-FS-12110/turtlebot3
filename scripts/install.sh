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

if [[ -t 1 ]]; then
  bold=$'\e[1m'; dim=$'\e[2m'; green=$'\e[32m'; yellow=$'\e[33m'; red=$'\e[31m'; cyan=$'\e[36m'; reset=$'\e[0m'
else
  bold=''; dim=''; green=''; yellow=''; red=''; cyan=''; reset=''
fi

# The plan (step titles) is filled in after the questions; step() walks through it.
PLAN=()
STEP_NO=0
SECONDS=0

hr() { local i; for ((i = 0; i < 64; i++)); do printf '─'; done; echo; }

# step "What happens and why" - title comes from PLAN[STEP_NO].
step() {
  local title=${PLAN[$STEP_NO]:-step}
  STEP_NO=$((STEP_NO + 1))
  echo
  echo "${bold}${green}━━ Step ${STEP_NO}/${#PLAN[@]}: ${title}${reset}"
  [[ -z ${1:-} ]] || fold -s -w 72 <<< "$1" | sed "s/^/   ${cyan}│${reset} /"
}
info() { echo "   $*"; }
ok() {
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "   ${dim}↷ dry run: nothing was changed${reset}"
  else
    echo "   ${green}✔ $*${reset}"
  fi
}
skip() { echo "   ${dim}↷ $*${reset}"; }
warn() { echo "${yellow}⚠ WARNING: $*${reset}"; }
die()  { echo "${red}✘ ERROR: $*${reset}" >&2; exit 1; }

on_error() {
  local code=$? line=$1
  echo
  echo "${red}${bold}✘ Failed${reset}${red} in step ${STEP_NO}/${#PLAN[@]} (${PLAN[$((STEP_NO - 1))]:-start}), script line ${line}, exit code ${code}.${reset}"
  echo "   Fix the problem and run the installer again; parts that are already done are skipped where possible."
}
set -E
trap 'on_error $LINENO' ERR

# Run a shell command string, or only print it in dry-run mode.
run() {
  echo "   ${dim}\$${reset} ${bold}$*${reset}"
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

hr
echo "${bold}  TurtleBot3 + ROS 2 Jazzy installer${reset}"
hr
[[ $DRY_RUN -eq 1 ]] && warn "Dry run: commands are printed, not executed."
info "Detected: ${PRETTY_NAME:-unknown}, ${MEM_MB} MB RAM$([[ $IS_WSL -eq 1 ]] && echo ', WSL2')$([[ $IS_PI -eq 1 ]] && echo ', Raspberry Pi')"
echo
echo "${bold}Questions${reset} ${dim}(press Enter to accept the value in [brackets])${reset}"
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

USE_CYCLONE=0
confirm "Use CycloneDDS (rmw_cyclonedds_cpp, recommended by ROBOTIS; set it on PC and robot alike)?" y && USE_CYCLONE=1

DO_SWAP=0; DO_NO_AUTOUPGRADE=0; DO_OPENCR=0; DO_WIFI_PS=0; LDS_MODEL=""
WLAN_IF=$(ls /sys/class/net 2>/dev/null | grep -m1 '^wl' || true)
if [[ $ROLE == robot ]]; then
  choose LDS_MODEL "LiDAR model" LDS-01 LDS-01 LDS-02 LDS-03
  if [[ $MEM_MB -lt 2048 && ! -f /swapfile ]]; then
    confirm "Less than 2 GB RAM: create a 2 GB swap file (needed for the build)?" y && DO_SWAP=1
  fi
  confirm "Disable automatic apt upgrades (they block apt and use memory on a Pi)?" y && DO_NO_AUTOUPGRADE=1
  if [[ -n $WLAN_IF ]]; then
    confirm "Disable Wi-Fi power saving on $WLAN_IF (avoids lag and dropped topics)?" y && DO_WIFI_PS=1
  fi
  confirm "Flash the OpenCR firmware now (OpenCR must be connected over USB)?" n && DO_OPENCR=1
fi

BUILD_ARGS="--symlink-install"
[[ $ROLE == robot || $MEM_MB -lt 2048 ]] && BUILD_ARGS+=" --parallel-workers 1"

# The steps below run in exactly this order; step() reads the titles from here.
[[ $DO_NO_AUTOUPGRADE -eq 1 ]] && PLAN+=("Disable automatic apt upgrades")
[[ $DO_SWAP -eq 1 ]] && PLAN+=("Create a 2 GB swap file")
[[ $DO_WIFI_PS -eq 1 ]] && PLAN+=("Disable Wi-Fi power saving")
PLAN+=("Add the ROS 2 apt repository")
PLAN+=("Install ROS 2 $ROS_DISTRO_NAME packages")
PLAN+=("Download the TurtleBot3 sources")
[[ $ROLE == pc ]] && PLAN+=("Resolve dependencies with rosdep")
PLAN+=("Build the workspace (colcon)")
[[ $ROLE == robot ]] && PLAN+=("Set up USB access for OpenCR and LiDAR")
[[ $DO_OPENCR -eq 1 ]] && PLAN+=("Flash the OpenCR firmware")
PLAN+=("Write the environment to ~/.bashrc")

echo
hr
echo "${bold}Summary${reset}"
hr
info "Role:            $ROLE"
info "Model:           $TB3_MODEL"
info "ROS_DOMAIN_ID:   $DOMAIN_ID"
info "Workspace:       $WS_DIR"
info "RMW:             $([[ $USE_CYCLONE -eq 1 ]] && echo rmw_cyclonedds_cpp || echo "ROS default")"
if [[ $ROLE == robot ]]; then
  info "LiDAR:           $LDS_MODEL"
fi
echo
echo "${bold}What will happen${reset}"
for i in "${!PLAN[@]}"; do
  info "$((i + 1)). ${PLAN[$i]}"
done
if [[ $ROLE == robot ]]; then
  echo
  warn "The build can take over an hour on a Raspberry Pi. Keep the robot on wall power and run this in tmux/screen so an SSH drop does not stop it."
fi
echo
confirm "Start installation?" y || exit 0

# --- Robot system preparation -----------------------------------------------

if [[ $DO_NO_AUTOUPGRADE -eq 1 ]]; then
  step "Ubuntu checks for updates in the background and holds the apt lock while it does. On a Pi this also eats scarce memory and makes the installer fail with 'could not get lock'. Turning it off means you update manually when you choose."
  run "sudo sed -i 's/\"1\"/\"0\"/' /etc/apt/apt.conf.d/20auto-upgrades"
  ok "Automatic upgrades disabled"
fi

if [[ $DO_SWAP -eq 1 ]]; then
  step "With 1 GB of RAM the compiler runs out of memory while building ROS packages. A swap file on the SD card gives it room (slower, but it finishes)."
  run "sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile"
  run "grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab"
  ok "2 GB swap active and enabled at boot"
fi

if [[ $DO_WIFI_PS -eq 1 ]]; then
  step "Wi-Fi power saving puts the radio to sleep between packets, which shows up as lag and dropped ROS topics. A small systemd unit switches it off on $WLAN_IF at every boot."
  run "sudo apt-get install -y iw"
  run "printf '%s\n' '[Unit]' 'Description=Disable Wi-Fi power saving' 'After=network-online.target' 'Wants=network-online.target' '' '[Service]' 'Type=oneshot' 'ExecStart=/usr/sbin/iw dev $WLAN_IF set power_save off' '' '[Install]' 'WantedBy=multi-user.target' | sudo tee /etc/systemd/system/wifi-powersave-off.service >/dev/null"
  run "sudo systemctl daemon-reload && sudo systemctl enable --now wifi-powersave-off.service"
  ok "Wi-Fi power saving off on $WLAN_IF"
fi

# --- ROS 2 apt repository ---------------------------------------------------

step "ROS 2 is not in Ubuntu's own package lists. This adds the official ROS 2 package source, then refreshes the package lists and updates the system (can take a few minutes)."
if dpkg -s ros2-apt-source >/dev/null 2>&1; then
  skip "ROS 2 apt source already configured"
else
  run "sudo apt-get update && sudo apt-get install -y software-properties-common curl"
  run "sudo add-apt-repository -y universe"
  run 'v=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F tag_name | awk -F\" "{print \$4}") && curl -fL -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${v}/ros2-apt-source_${v}.$(. /etc/os-release && echo $VERSION_CODENAME)_all.deb" && sudo dpkg -i /tmp/ros2-apt-source.deb'
fi
run "sudo apt-get update && sudo apt-get upgrade -y"
ok "ROS 2 apt source ready, system updated"

# --- Packages ---------------------------------------------------------------

if [[ $ROLE == pc ]]; then
  step "Installs ROS 2 with its GUI tools (RViz), Gazebo simulation, Cartographer (SLAM) and Nav2 (navigation). This is the big download of the PC setup."
  run "sudo apt-get install -y git ros-$ROS_DISTRO_NAME-desktop ros-dev-tools \
    ros-$ROS_DISTRO_NAME-ros-gz \
    ros-$ROS_DISTRO_NAME-cartographer ros-$ROS_DISTRO_NAME-cartographer-ros \
    ros-$ROS_DISTRO_NAME-navigation2 ros-$ROS_DISTRO_NAME-nav2-bringup"
else
  step "Installs only the minimum the robot needs: the ROS 2 base system, the LiDAR driver and the OpenCR communication libraries. SLAM, navigation and RViz run on the PC."
  run "sudo apt-get install -y git ros-$ROS_DISTRO_NAME-ros-base ros-dev-tools \
    ros-$ROS_DISTRO_NAME-hls-lfcd-lds-driver ros-$ROS_DISTRO_NAME-turtlebot3-msgs \
    ros-$ROS_DISTRO_NAME-dynamixel-sdk ros-$ROS_DISTRO_NAME-xacro libudev-dev"
fi

if [[ $USE_CYCLONE -eq 1 ]]; then
  info "CycloneDDS: the network layer ROBOTIS recommends; PC and robot must use the same one."
  run "sudo apt-get install -y ros-$ROS_DISTRO_NAME-rmw-cyclonedds-cpp"
fi
ok "ROS 2 packages installed"

# --- Workspace --------------------------------------------------------------

step "Fetches the TurtleBot3 packages (the ROBOTIS 'jazzy' branches) into $WS_DIR/src. These are built in a later step."
run "mkdir -p '$WS_DIR/src'"

clone() {
  local repo=$1 dir="$WS_DIR/src/${1##*/}"
  if [[ -d $dir ]]; then
    skip "${repo##*/} already present"
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
  info "Removing the SLAM and navigation packages: too heavy for the Pi, they run on the PC."
  run "rm -rf '$WS_DIR/src/turtlebot3/turtlebot3_cartographer' '$WS_DIR/src/turtlebot3/turtlebot3_navigation2'"
fi
ok "Sources ready in $WS_DIR/src"

if [[ $ROLE == pc ]]; then
  step "rosdep reads what the packages depend on and installs anything still missing, so the build does not stop halfway."
  run "[ -f /etc/ros/rosdep/sources.list.d/20-default.list ] || sudo rosdep init"
  run "rosdep update"
  run "source /opt/ros/$ROS_DISTRO_NAME/setup.bash && rosdep install --from-paths '$WS_DIR/src' --ignore-src -y --rosdistro $ROS_DISTRO_NAME"
  ok "Dependencies installed"
fi

step "Compiles the TurtleBot3 packages with colcon (build options: $BUILD_ARGS). $([[ $ROLE == robot ]] && echo "On a Raspberry Pi this can take over an hour and the output may look stuck; that is normal." || echo "Takes a few minutes.")"
run "source /opt/ros/$ROS_DISTRO_NAME/setup.bash && cd '$WS_DIR' && colcon build $BUILD_ARGS"
ok "Workspace built"

# --- Robot hardware access --------------------------------------------------

if [[ $ROLE == robot ]]; then
  step "udev rules give the OpenCR and the LiDAR stable device names and let you use them; adding your user to the 'dialout' group allows opening the serial ports without sudo."
  run "sudo cp '$WS_DIR/src/turtlebot3/turtlebot3_bringup/script/99-turtlebot3-cdc.rules' /etc/udev/rules.d/"
  run "sudo udevadm control --reload-rules && sudo udevadm trigger"
  run "sudo usermod -aG dialout '$USER'"
  ok "USB access configured (log out and back in to apply the group)"
fi

if [[ $DO_OPENCR -eq 1 ]]; then
  step "Uploads ROBOTIS' prebuilt firmware for the $TB3_MODEL into the OpenCR board over USB (/dev/ttyACM0). The board must be connected and powered. If it fails, enter recovery mode: hold SW2, press Reset, release Reset, release SW2."
  run "sudo dpkg --add-architecture armhf && sudo apt-get update && sudo apt-get install -y libc6:armhf"
  run "tmp=\$(mktemp -d) && cd \"\$tmp\" \
    && wget -q https://github.com/ROBOTIS-GIT/OpenCR-Binaries/raw/master/turtlebot3/ROS2/latest/opencr_update.tar.bz2 \
    && tar -xjf opencr_update.tar.bz2 && cd opencr_update \
    && ./update.sh /dev/ttyACM0 $TB3_MODEL.opencr"
  ok "Firmware uploaded"
  info "Test without ROS: hold SW1 to drive forward, SW2 to rotate (wheels in the air)."
fi

# --- Environment ------------------------------------------------------------

step "Appends the ROS settings (ROS_DOMAIN_ID, robot model, RMW) to ~/.bashrc inside a marked block, so every new terminal is ready. Running the installer again replaces only that block."
BEGIN_MARK="# >>> turtlebot3 >>>"
END_MARK="# <<< turtlebot3 <<<"
ENV_BLOCK="$BEGIN_MARK
source /opt/ros/$ROS_DISTRO_NAME/setup.bash
source $WS_DIR/install/setup.bash
export ROS_DOMAIN_ID=$DOMAIN_ID
export TURTLEBOT3_MODEL=$TB3_MODEL"
[[ -n $LDS_MODEL ]] && ENV_BLOCK+="
export LDS_MODEL=$LDS_MODEL"
[[ $USE_CYCLONE -eq 1 ]] && ENV_BLOCK+="
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp"
ENV_BLOCK+="
$END_MARK"

if [[ -f ~/.bashrc ]] && sed "/^$BEGIN_MARK\$/,/^$END_MARK\$/d" ~/.bashrc | grep -q 'TURTLEBOT3_MODEL\|ROS_DOMAIN_ID'; then
  warn "~/.bashrc already sets TURTLEBOT3_MODEL or ROS_DOMAIN_ID outside the installer block; remove those lines to avoid conflicts."
fi
# Replace a previous installer block, then append the current one.
run "sed -i '/^$BEGIN_MARK\$/,/^$END_MARK\$/d' ~/.bashrc"
if [[ $DRY_RUN -eq 1 ]]; then
  echo "   ${dim}\$${reset} ${bold}cat >> ~/.bashrc${reset}"
  sed 's/^/      /' <<< "$ENV_BLOCK"
else
  printf '%s\n' "$ENV_BLOCK" >> ~/.bashrc
fi
ok "Environment written to ~/.bashrc"

# --- Done -------------------------------------------------------------------

echo
hr
if [[ $DRY_RUN -eq 1 ]]; then
  echo "${bold}${yellow}Dry run finished${reset}: $STEP_NO steps listed, nothing was installed or changed"
else
  echo "${bold}${green}✔ Installation finished${reset} in $((SECONDS / 60)) min $((SECONDS % 60)) s ($STEP_NO steps)"
fi
hr
echo "${bold}Next${reset}"
info "Open a new terminal (or run: source ~/.bashrc), then:"
if [[ $ROLE == pc ]]; then
  info "  ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py"
  info "  ros2 run turtlebot3_teleop teleop_keyboard"
else
  info "  ros2 launch turtlebot3_bringup robot.launch.py"
  info "Log out and back in once so the dialout group membership applies."
fi
info "Check the setup any time with: $(dirname "$(readlink -f "$0")")/check.sh [other-host-ip]"

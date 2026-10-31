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
#
# On the first question the installer offers to restart itself inside tmux (installs tmux and a
# small ~/.tmux.conf block), so an SSH drop does not stop a long build.

set -euo pipefail

ROS_DISTRO_NAME=jazzy
REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ASSUME_YES=0
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    -n|--dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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

# --- Idempotency helpers: steps check what is already done and skip it ------

APT="sudo apt-get -o DPkg::Lock::Timeout=900"
STAMP_DIR="$HOME/.cache/turtlebot3-installer"
UPGRADE_STAMP="$STAMP_DIR/system-upgraded"

# missing_pkgs pkg... - prints the packages that are not installed yet.
missing_pkgs() {
  local p
  for p in "$@"; do
    dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q '^install ok installed' || echo "$p"
  done
}

# apt_install pkg... - installs only what is missing.
apt_install() {
  local missing
  missing=$(missing_pkgs "$@" | xargs)
  if [[ -z $missing ]]; then
    skip "already installed: $*"
  else
    run "$APT install -y $missing"
  fi
}

# build_current - true when the last successful build used the same options and no source file
# changed since.
build_current() {
  local stamp="$WS_DIR/.installer-build-stamp"
  [[ -f $stamp && $(cat "$stamp") == "$BUILD_ARGS" && -d $WS_DIR/install ]] || return 1
  [[ -z $(find "$WS_DIR/src" -type f -newer "$stamp" -not -path '*/.git/*' -print -quit) ]]
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

# --- tmux -------------------------------------------------------------------
# A long build started over SSH dies when the connection drops. Inside tmux it keeps running and
# you reattach with: tmux attach -t turtlebot3. Asked first, so every later answer is given inside it.

SELF=$(readlink -f "$0")
TMUX_BEGIN="# >>> turtlebot3 >>>"
TMUX_END="# <<< turtlebot3 <<<"
IFS= read -r -d '' TMUX_CONF <<'EOF' || true
# Long scrollback for build and ROS logs, mouse scrolling (hold Shift to select text).
set -g history-limit 50000
set -g mouse on
set -g escape-time 10
set -g focus-events on
set -g default-terminal "screen-256color"
setw -g aggressive-resize on
setw -g mode-keys vi

# Number windows and panes from 1, no gaps when a window closes.
set -g base-index 1
setw -g pane-base-index 1
set -g renumber-windows on

# ROS runs several programs side by side (bringup, teleop, topic echo). Keep the window names you
# give them (Ctrl+b ,) and open new windows and panes in the current directory.
setw -g automatic-rename off
set -g allow-rename off
bind c new-window -c "#{pane_current_path}"
bind | split-window -h -c "#{pane_current_path}"
bind - split-window -v -c "#{pane_current_path}"
bind r source-file ~/.tmux.conf \; display-message "tmux config reloaded"

# Pane borders show what runs in each pane (ros2, python3, ...).
set -g pane-border-status top
set -g pane-border-format " #{pane_index}: #{pane_current_command} "

# Status bar: session, ROS settings, load average (a busy load shows that a build is still alive).
set -g status-interval 5
set -g status-left-length 20
set -g status-right-length 90
set -g status-left "[#S] "
set -g status-right '#(echo "ROS_DOMAIN_ID ${ROS_DOMAIN_ID:-?}, ${TURTLEBOT3_MODEL:-?}") | load #(cut -d" " -f1-3 /proc/loadavg) | #H %H:%M'
EOF
TMUX_BLOCK="$TMUX_BEGIN"$'\n'"$TMUX_CONF""$TMUX_END"

if [[ -n ${TMUX:-} ]]; then
  info "Running inside tmux: an SSH drop will not stop the installer."
elif [[ -t 0 && -t 1 ]]; then
  default_tmux=n
  [[ $IS_PI -eq 1 || -n ${SSH_CONNECTION:-} ]] && default_tmux=y
  if confirm "Run the installer inside tmux, so an SSH drop does not stop a long build (installs tmux and a small config)?" "$default_tmux"; then
    if command -v tmux >/dev/null && tmux has-session -t turtlebot3 2>/dev/null; then
      warn "A tmux session 'turtlebot3' is already running (probably an earlier installer run). Attach with: tmux attach -t turtlebot3"
      exit 0
    fi
    if command -v tmux >/dev/null; then
      skip "tmux already installed"
    else
      run "sudo apt-get -o DPkg::Lock::Timeout=900 update && sudo apt-get -o DPkg::Lock::Timeout=900 install -y tmux"
    fi
    # Replace a previous installer block in ~/.tmux.conf, keep everything else.
    run "touch ~/.tmux.conf && sed -i '/^$TMUX_BEGIN\$/,/^$TMUX_END\$/d' ~/.tmux.conf"
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "   ${dim}\$${reset} ${bold}cat >> ~/.tmux.conf${reset}"
      sed 's/^/      /' <<< "$TMUX_BLOCK"
      skip "dry run: would restart the installer inside the tmux session 'turtlebot3'"
    else
      printf '%s\n' "$TMUX_BLOCK" >> ~/.tmux.conf
      ok "tmux installed and configured (~/.tmux.conf)"
      info "Restarting the installer inside tmux. Detach: Ctrl+b then d. Reattach later: tmux attach -t turtlebot3"
      exec tmux new-session -s turtlebot3 bash -c '"$0" "$@"; code=$?; echo; read -r -p "Installer exited with code $code. Press Enter to close tmux. " _; exit "$code"' "$SELF" "$@"
    fi
  fi
fi
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
    confirm "Less than 2 GB RAM: create a 3 GB swap file (needed for the build)?" y && DO_SWAP=1
  fi
  confirm "Disable automatic apt upgrades (they block apt and use memory on a Pi)?" y && DO_NO_AUTOUPGRADE=1
  if [[ -n $WLAN_IF ]]; then
    confirm "Disable Wi-Fi power saving on $WLAN_IF (avoids lag and dropped topics)?" y && DO_WIFI_PS=1
  fi
  confirm "Flash the OpenCR firmware now (OpenCR must be connected over USB)?" n && DO_OPENCR=1
fi

BUILD_ARGS="--symlink-install"
BUILD_ENV=""
if [[ $ROLE == robot || $MEM_MB -lt 2048 ]]; then
  # One package and one compiler job at a time, an optimized (smaller) build, and a GCC that frees
  # memory sooner. The heaviest package (turtlebot3_node) otherwise needs several hundred MB.
  BUILD_ARGS+=" --parallel-workers 1 --cmake-args -DCMAKE_BUILD_TYPE=Release"
  BUILD_ENV="MAKEFLAGS=-j1 CMAKE_BUILD_PARALLEL_LEVEL=1 CXXFLAGS='--param ggc-min-expand=20 --param ggc-min-heapsize=32768'"
fi

# The steps below run in exactly this order; step() reads the titles from here.
[[ $DO_NO_AUTOUPGRADE -eq 1 ]] && PLAN+=("Disable automatic apt upgrades")
[[ $DO_SWAP -eq 1 ]] && PLAN+=("Create a 3 GB swap file")
[[ $ROLE == robot ]] && PLAN+=("Protect SSH from the out-of-memory killer")
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
  warn "The build can take over an hour on a Raspberry Pi. Keep the robot on wall power."
  [[ -n ${TMUX:-} ]] || warn "Not running in tmux: an SSH drop would stop the build. Restart the installer and answer yes to the tmux question."
fi
echo
confirm "Start installation?" y || exit 0

# --- Robot system preparation -----------------------------------------------

if [[ $DO_NO_AUTOUPGRADE -eq 1 ]]; then
  step "Ubuntu checks for updates in the background and holds the apt lock while it does. On a Pi this also eats scarce memory and makes the installer fail with 'could not get lock'. Turning it off means you update manually when you choose."
  if grep -qs '"1"' /etc/apt/apt.conf.d/20auto-upgrades; then
    run "sudo sed -i 's/\"1\"/\"0\"/' /etc/apt/apt.conf.d/20auto-upgrades"
    ok "Automatic upgrades disabled"
  else
    skip "Automatic upgrades already disabled"
  fi
fi

if [[ $DO_SWAP -eq 1 ]]; then
  step "With 1 GB of RAM the compiler runs out of memory while building ROS packages. A swap file on the SD card gives it room (slower, but it finishes)."
  run "sudo fallocate -l 3G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile"
  run "grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab"
  ok "3 GB swap active and enabled at boot"
fi

if [[ $ROLE == robot ]]; then
  step "When memory runs out, Linux kills a process to recover; without this it can pick sshd and you lose the connection mid-build. Lowering the OOM score of sshd makes the kernel pick the compiler instead."
  OOM_CONF=/etc/systemd/system/ssh.service.d/oom.conf
  if grep -qs '^OOMScoreAdjust=-900' "$OOM_CONF"; then
    skip "sshd is already protected"
  else
    run "sudo mkdir -p /etc/systemd/system/ssh.service.d && printf '[Service]\nOOMScoreAdjust=-900\n' | sudo tee $OOM_CONF >/dev/null"
    run "sudo systemctl daemon-reload && sudo systemctl restart ssh"
    ok "sshd protected from the OOM killer"
  fi
fi

if [[ $DO_WIFI_PS -eq 1 ]]; then
  step "Wi-Fi power saving puts the radio to sleep between packets, which shows up as lag and dropped ROS topics. A small systemd unit switches it off on $WLAN_IF at every boot."
  if systemctl is-enabled wifi-powersave-off.service >/dev/null 2>&1 \
     && grep -qs "dev $WLAN_IF " /etc/systemd/system/wifi-powersave-off.service; then
    skip "Wi-Fi power saving already disabled on $WLAN_IF"
  else
    apt_install iw
    run "printf '%s\n' '[Unit]' 'Description=Disable Wi-Fi power saving' 'After=network-online.target' 'Wants=network-online.target' '' '[Service]' 'Type=oneshot' 'ExecStart=/usr/sbin/iw dev $WLAN_IF set power_save off' '' '[Install]' 'WantedBy=multi-user.target' | sudo tee /etc/systemd/system/wifi-powersave-off.service >/dev/null"
    run "sudo systemctl daemon-reload && sudo systemctl enable --now wifi-powersave-off.service"
    ok "Wi-Fi power saving off on $WLAN_IF"
  fi
fi

# --- ROS 2 apt repository ---------------------------------------------------

step "ROS 2 is not in Ubuntu's own package lists. This adds the official ROS 2 package source, then refreshes the package lists and fully updates the system, so library versions match and the ROS packages install without dependency conflicts (can take a few minutes)."
if dpkg -s ros2-apt-source >/dev/null 2>&1; then
  skip "ROS 2 apt source already configured"
else
  run "rm -f '$UPGRADE_STAMP'"
  run "$APT update && $APT install -y software-properties-common curl"
  run "sudo add-apt-repository -y universe"
  run 'v=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F tag_name | awk -F\" "{print \$4}") && curl -fL -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${v}/ros2-apt-source_${v}.$(. /etc/os-release && echo $VERSION_CODENAME)_all.deb" && sudo dpkg -i /tmp/ros2-apt-source.deb'
fi
# Some images (seen on Ubuntu Server for Raspberry Pi) ship only <release> and <release>-security.
# Without <release>-updates, -dev packages and their libraries come from different pockets and
# installs fail with "unmet dependencies" (e.g. liblz4-dev, libzstd-dev).
UBUNTU_SOURCES=/etc/apt/sources.list.d/ubuntu.sources
if [[ -f $UBUNTU_SOURCES ]] && ! grep -qsE "^[^#]*${VERSION_CODENAME}-updates" /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list; then
  info "The ${VERSION_CODENAME}-updates suite is missing from the apt sources; adding it (otherwise package installs fail)."
  UBUNTU_URI=$(awk '/^URIs:/ {print $2; exit}' "$UBUNTU_SOURCES")
  UBUNTU_COMPONENTS=$(awk '/^Components:/ {sub(/^Components: */, ""); print; exit}' "$UBUNTU_SOURCES")
  run "printf '\nTypes: deb\nURIs: $UBUNTU_URI\nSuites: ${VERSION_CODENAME}-updates\nComponents: $UBUNTU_COMPONENTS\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n' | sudo tee -a $UBUNTU_SOURCES >/dev/null"
  run "rm -f '$UPGRADE_STAMP'"
fi
# full-upgrade (not upgrade): plain upgrade holds packages back and leaves versions inconsistent,
# which later breaks installs with "unmet dependencies" (e.g. liblz4-dev / libzstd-dev).
# A recent successful upgrade (within 24 h) is not repeated when the installer is restarted.
if [[ -n $(find "$UPGRADE_STAMP" -mmin -1440 2>/dev/null) ]]; then
  skip "System was already updated in the last 24 hours"
else
  run "$APT update && $APT full-upgrade -y && $APT install -f -y"
  run "mkdir -p '$STAMP_DIR' && touch '$UPGRADE_STAMP'"
  ok "ROS 2 apt source ready, system updated"
fi

# --- Packages ---------------------------------------------------------------

if [[ $ROLE == pc ]]; then
  step "Installs ROS 2 with its GUI tools (RViz), Gazebo simulation, Cartographer (SLAM) and Nav2 (navigation). This is the big download of the PC setup."
  apt_install git ros-$ROS_DISTRO_NAME-desktop ros-dev-tools \
    ros-$ROS_DISTRO_NAME-ros-gz \
    ros-$ROS_DISTRO_NAME-cartographer ros-$ROS_DISTRO_NAME-cartographer-ros \
    ros-$ROS_DISTRO_NAME-navigation2 ros-$ROS_DISTRO_NAME-nav2-bringup \
    ros-$ROS_DISTRO_NAME-slam-toolbox
else
  step "Installs only the minimum the robot needs: the ROS 2 base system, the LiDAR driver and the OpenCR communication libraries. SLAM, navigation and RViz run on the PC."
  apt_install git ros-$ROS_DISTRO_NAME-ros-base ros-dev-tools \
    ros-$ROS_DISTRO_NAME-hls-lfcd-lds-driver ros-$ROS_DISTRO_NAME-turtlebot3-msgs \
    ros-$ROS_DISTRO_NAME-dynamixel-sdk ros-$ROS_DISTRO_NAME-xacro libudev-dev \
    ros-$ROS_DISTRO_NAME-robot-localization
fi

if [[ $USE_CYCLONE -eq 1 ]]; then
  info "CycloneDDS: the network layer ROBOTIS recommends; PC and robot must use the same one."
  apt_install ros-$ROS_DISTRO_NAME-rmw-cyclonedds-cpp
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
  # Autonomous mapping package from this repository; a link keeps it editable and up to date with git pull.
  if [[ -e "$WS_DIR/src/auto_mapper" ]]; then
    skip "auto_mapper already linked"
  else
    run "ln -s '$REPO_DIR/auto_mapper' '$WS_DIR/src/auto_mapper'"
  fi
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
  if build_current; then
    skip "Workspace already built from the current sources, dependencies were resolved then"
  else
    run "[ -f /etc/ros/rosdep/sources.list.d/20-default.list ] || sudo rosdep init"
    run "rosdep update"
    run "source /opt/ros/$ROS_DISTRO_NAME/setup.bash && rosdep install --from-paths '$WS_DIR/src' --ignore-src -y --rosdistro $ROS_DISTRO_NAME"
    ok "Dependencies installed"
  fi
fi

step "Compiles the TurtleBot3 packages with colcon (build options: $BUILD_ARGS). $([[ $ROLE == robot ]] && echo "On a Raspberry Pi this can take over an hour and the output may look stuck; that is normal." || echo "Takes a few minutes.")"
if build_current; then
  skip "Workspace already built from the current sources"
else
  run "source /opt/ros/$ROS_DISTRO_NAME/setup.bash && cd '$WS_DIR' && $BUILD_ENV nice -n 10 colcon build $BUILD_ARGS"
  run "printf '%s\n' '$BUILD_ARGS' > '$WS_DIR/.installer-build-stamp'"
  ok "Workspace built"
fi

# --- Robot hardware access --------------------------------------------------

if [[ $ROLE == robot ]]; then
  step "udev rules give the OpenCR and the LiDAR stable device names and let you use them; adding your user to the 'dialout' group allows opening the serial ports without sudo."
  UDEV_SRC="$WS_DIR/src/turtlebot3/turtlebot3_bringup/script/99-turtlebot3-cdc.rules"
  if cmp -s "$UDEV_SRC" /etc/udev/rules.d/99-turtlebot3-cdc.rules && id -nG "$USER" | grep -qw dialout; then
    skip "udev rules and dialout group already set up"
  else
    run "sudo cp '$UDEV_SRC' /etc/udev/rules.d/"
    run "sudo udevadm control --reload-rules && sudo udevadm trigger"
    run "sudo usermod -aG dialout '$USER'"
    ok "USB access configured (log out and back in to apply the group)"
  fi
fi

if [[ $DO_OPENCR -eq 1 ]]; then
  step "Uploads ROBOTIS' prebuilt firmware for the $TB3_MODEL into the OpenCR board over USB (/dev/ttyACM0). The board must be connected and powered. If it fails, enter recovery mode: hold SW2, press Reset, release Reset, release SW2."
  if [[ -n $(missing_pkgs libc6:armhf) ]]; then
    run "sudo dpkg --add-architecture armhf && $APT update && $APT install -y libc6:armhf"
  else
    skip "libc6:armhf already installed"
  fi
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
  info "(After a reboot the dialout group applies; without a reboot log out and back in once.)"
fi
info "Check the setup any time with: $(dirname "$(readlink -f "$0")")/check.sh [other-host-ip]"

# A reboot applies a new kernel and libraries from the full upgrade, plus the udev rules and the
# 'dialout' group on the robot. Not needed in WSL.
NEED_REBOOT=0
[[ $ROLE == robot || -f /var/run/reboot-required ]] && NEED_REBOOT=1
[[ $IS_WSL -eq 1 ]] && NEED_REBOOT=0
if [[ $NEED_REBOOT -eq 1 ]]; then
  echo
  info "A reboot is recommended: it applies the system update, the udev rules and the 'dialout' group."
  if [[ $DRY_RUN -eq 1 ]]; then
    skip "dry run: would ask whether to reboot now"
  elif [[ $ASSUME_YES -eq 1 ]]; then
    info "Reboot when ready: sudo reboot"
  elif confirm "Reboot now?" y; then
    info "Rebooting in 5 seconds (Ctrl+C to cancel)..."
    sleep 5
    sudo reboot
  fi
fi

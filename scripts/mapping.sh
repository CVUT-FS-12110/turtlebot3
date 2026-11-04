#!/usr/bin/env bash
# Opens a tmux session on the PC (WSL2) with everything needed to map a room.
# Run it on the PC only; the robot (or Gazebo) must already be running.
#
# Usage: mapping.sh [manual|auto] [--sim] [--gamepad] [--restart] [--no-attach]
#        mapping.sh stop
#   manual      SLAM + RViz + keyboard teleop (default)
#   auto        auto_mapper: SLAM + Nav2 + frontier explorer, plus RViz
#   --sim       use the Gazebo clock (use_sim_time:=true); omit it on the real robot
#   --gamepad   manual mode without the keyboard teleop: drive with the gamepad on the robot
#               (the keyboard teleop publishes zero speed while idle and would fight the gamepad)
#   --restart   kill an existing session and start a new one
#   --no-attach create the session without attaching to it
#   stop        kill the session
#
# Panes:  [launch]  [RViz]  [teleop or hints]  [/scan rate]
# The status bar shows the robot's battery voltage (window "battery" runs robot/battery_status.py).
# Detach with Ctrl+b then d, reattach with: tmux attach -t mapping

set -euo pipefail

SESSION=mapping
REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
WS_DIR=${WS_DIR:-$HOME/turtlebot3_ws}
MODE=manual
SIM=false
ATTACH=1
RESTART=0
GAMEPAD=0

die() { echo "mapping.sh: $*" >&2; exit 1; }

for arg in "$@"; do
  case "$arg" in
    manual|auto) MODE=$arg ;;
    --sim) SIM=true ;;
    --gamepad) GAMEPAD=1 ;;
    --restart) RESTART=1 ;;
    --no-attach) ATTACH=0 ;;
    stop) tmux kill-session -t "$SESSION" 2>/dev/null && echo "Session $SESSION stopped" || echo "No session $SESSION"; exit 0 ;;
    -h|--help) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $arg (try --help)" ;;
  esac
done

command -v tmux >/dev/null || die "tmux is not installed (sudo apt install tmux)"
[[ -f $WS_DIR/install/setup.bash ]] || die "workspace not built: $WS_DIR/install/setup.bash is missing"

attach() {
  if [[ $ATTACH -eq 0 ]]; then echo "Session $SESSION is running: tmux attach -t $SESSION"; return; fi
  if [[ -n ${TMUX:-} ]]; then tmux switch-client -t "$SESSION"; else tmux attach -t "$SESSION"; fi
}

if tmux has-session -t "$SESSION" 2>/dev/null; then
  if [[ $RESTART -eq 1 ]]; then
    tmux kill-session -t "$SESSION"
  else
    echo "Session $SESSION already exists (use --restart to start over)"
    attach
    exit 0
  fi
fi

# The panes are interactive shells, so ~/.bashrc supplies ROS_DOMAIN_ID, RMW_IMPLEMENTATION and so on.
SRC="source $WS_DIR/install/setup.bash"
SLAM_PARAMS='$(ros2 pkg prefix auto_mapper)/share/auto_mapper/config/slam_toolbox.yaml'
# Auto mode runs Nav2, so its own view fits. In manual mode that view has a panel waiting for the Nav2
# servers ("controller_server service not available"), and the cartographer view subscribes to /scan
# as reliable, which the LiDAR (best effort) does not serve. Use our own view from this repository.
if [[ $MODE == auto ]]; then
  RVIZ_CFG='$(ros2 pkg prefix nav2_bringup)/share/nav2_bringup/rviz/nav2_default_view.rviz'
else
  RVIZ_CFG="$REPO_DIR/auto_mapper/config/mapping.rviz"
fi
RVIZ_ARGS=""
[[ $SIM == true ]] && RVIZ_ARGS=" --ros-args -p use_sim_time:=true"

if [[ $MODE == auto ]]; then
  LAUNCH="ros2 launch auto_mapper auto_mapper.launch.py use_sim_time:=$SIM"
else
  LAUNCH="ros2 launch slam_toolbox online_async_launch.py use_sim_time:=$SIM slam_params_file:=$SLAM_PARAMS"
fi

send() { tmux send-keys -t "$1" "$2" C-m; }

P_LAUNCH=$(tmux new-session -d -s "$SESSION" -n mapping -x 200 -y 50 -P -F '#{pane_id}')
P_RVIZ=$(tmux split-window -h -t "$P_LAUNCH" -P -F '#{pane_id}')
P_TELEOP=$(tmux split-window -v -t "$P_RVIZ" -P -F '#{pane_id}')
P_SCAN=$(tmux split-window -v -t "$P_LAUNCH" -P -F '#{pane_id}')
tmux new-window -t "$SESSION:" -n shell
# Battery voltage of the robot in this session's status bar: battery_status.py (the same node as on the Pi)
# subscribes to /battery_state and writes /tmp/tb3_battery, which the status bar shows. It runs in its own window.
tmux new-window -t "$SESSION:" -n battery
tmux send-keys -t "$SESSION:battery" "$SRC; python3 \"$REPO_DIR/robot/battery_status.py\"" C-m
tmux set-option -t "$SESSION" status-right-length 120
tmux set-option -t "$SESSION" status-right "#(cat /tmp/tb3_battery 2>/dev/null) | ROS_DOMAIN_ID ${ROS_DOMAIN_ID:-?} | %H:%M"
tmux set-option -t "$SESSION" status-interval 5
tmux select-window -t "$SESSION:mapping"
tmux set-option -t "$SESSION" mouse on
tmux set-option -t "$SESSION" pane-border-status top
tmux select-layout -t "$SESSION:mapping" tiled

tmux select-pane -t "$P_LAUNCH" -T "$([[ $MODE == auto ]] && echo 'auto_mapper' || echo 'slam_toolbox')"
tmux select-pane -t "$P_RVIZ" -T rviz
if [[ $MODE == auto || $GAMEPAD -eq 1 ]]; then TELEOP_TITLE=hints; else TELEOP_TITLE='teleop (w/x speed, a/d turn, s or space = STOP)'; fi
tmux select-pane -t "$P_TELEOP" -T "$TELEOP_TITLE"
tmux select-pane -t "$P_SCAN" -T "/scan rate"

for pane in "$P_LAUNCH" "$P_RVIZ" "$P_TELEOP" "$P_SCAN"; do send "$pane" "$SRC"; done
tmux send-keys -t "$SESSION:shell" "$SRC" C-m

send "$P_SCAN" "ros2 topic hz /scan"
send "$P_LAUNCH" "$LAUNCH"
send "$P_RVIZ" "sleep 4 && ros2 run rviz2 rviz2 -d \"$RVIZ_CFG\"$RVIZ_ARGS"
if [[ $MODE == auto ]]; then
  send "$P_TELEOP" "clear; echo 'Stop: Ctrl+C in the auto_mapper pane. Save the map by hand:'; echo '  mkdir -p ~/maps && ros2 run nav2_map_server map_saver_cli -f ~/maps/room'"
elif [[ $GAMEPAD -eq 1 ]]; then
  send "$P_TELEOP" "clear; echo 'Gamepad mode: no keyboard teleop here. Drive with the gamepad (hold the enable button);'; echo 'the robot must run: bringup.launch.py gamepad:=true. Save the map by hand:'; echo '  mkdir -p ~/maps && ros2 run nav2_map_server map_saver_cli -f ~/maps/room'"
else
  send "$P_TELEOP" "ros2 run turtlebot3_teleop teleop_keyboard"
  tmux select-pane -t "$P_TELEOP"   # keys go to the teleop pane
fi

attach

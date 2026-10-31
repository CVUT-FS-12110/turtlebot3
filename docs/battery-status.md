# Battery voltage in the tmux status bar

The robot publishes its battery on `/battery_state`. A small node shows the voltage and charge in the tmux status bar on the Raspberry Pi, so you see it while the bring-up runs:

```
Battery: 11.8 V 87 % | ROS_DOMAIN_ID 30, burger | load 0.52 0.40 0.31 | turtle 19:42
```

| Colour | Meaning |
|---|---|
| bold, in the bar's own colours | above the warning voltage |
| yellow box | below `warn_voltage` (default 11.0 V): plan to stop and charge |
| red box, `Battery LOW:` | below `critical_voltage` (default 10.5 V): stop driving, a deeply discharged LiPo is damaged |
| grey box, `Battery: no data (N s)` | no message for 5 s: the bring-up is not running or the OpenCR does not answer |

A healthy battery follows the status bar's colours, so it blends in. The warning boxes set a foreground and a background colour on purpose: the default tmux status bar is green, and text coloured only green on it is invisible.

The limits are my choice for a 3-cell LiPo (11.1 V nominal, 12.6 V full) and are not taken from the OpenCR firmware. Compare them with the point where the board starts to beep and adjust them (below).

## How it works

[`robot/battery_status.py`](../robot/battery_status.py) subscribes to `/battery_state` and writes one line with tmux colour codes to `/tmp/tb3_battery` every 2 s. The tmux status bar reads that file with `#(cat /tmp/tb3_battery)`. This is much lighter than calling `ros2 topic echo` from tmux every few seconds, which starts the whole ROS 2 command line tool each time and loads a Raspberry Pi 3B+ noticeably. The file is removed when the node stops, so an old voltage is never shown.

## ROBOT (Raspberry Pi)

Update the repository ([update steps](../README.md#updating-from-github)):

```bash
git -C ~/turtlebot3-setup pull
```

**1. Start the bring-up with the monitor** instead of the plain `robot.launch.py`:

```bash
export TURTLEBOT3_MODEL=burger
ros2 launch ~/turtlebot3-setup/robot/launch/bringup.launch.py
```

With the EKF odometry, [`bringup_ekf.launch.py`](../robot/launch/bringup_ekf.launch.py) starts the monitor too, see [ekf.md](ekf.md). Never run two bring-ups at once.

**2. Show it in tmux.** New robot installs get this from `scripts/install.sh`. On an existing setup add the status line to `~/.tmux.conf` and reload it:

```bash
cat >> ~/.tmux.conf <<'EOF'
set -g status-right-length 120
set -g status-right '#(cat /tmp/tb3_battery 2>/dev/null) | #(echo "ROS_DOMAIN_ID ${ROS_DOMAIN_ID:-?}, ${TURTLEBOT3_MODEL:-?}") | load #(cut -d" " -f1-3 /proc/loadavg) | #H %H:%M'
EOF
tmux source-file ~/.tmux.conf
```

If you later run the installer again, it writes the same line in its own block; then delete the two lines above from the end of `~/.tmux.conf`. The status bar refreshes every 5 s (`status-interval`).

**3. Change the limits** with launch arguments:

```bash
ros2 launch ~/turtlebot3-setup/robot/launch/bringup.launch.py warn_voltage:=11.3 critical_voltage:=10.8
```

## PC (WSL2)

Nothing to install or run. To read the same value on the PC, use the topic:

```bash
ros2 topic echo /battery_state --once --field voltage
```

## Checks

| Symptom | Action |
|---|---|
| Only ` | ` where the battery should be | The text is there but has the colour of the bar (an old version coloured it green). Update (`git pull`) and restart the bring-up. `tmux show -g status-style` shows the bar colours (default `bg=green,fg=black`). |
| No battery item in the status bar | ROBOT: `cat /tmp/tb3_battery`. If the file is missing, the monitor is not running (use `bringup.launch.py`). If it exists, the `status-right` line is missing from `~/.tmux.conf`. |
| Grey `Battery: no data` | ROBOT: `ros2 topic hz /battery_state`. No messages mean the bring-up or the OpenCR link is down, see [troubleshooting.md](troubleshooting.md). |
| Voltage looks wrong | Compare with a multimeter on the battery connector. The value comes from the OpenCR measurement. |

The formatting is covered by unit tests; run them on a machine with ROS 2 (the node imports `rclpy`):

```bash
cd ~/turtlebot3-setup/robot && python3 -m unittest discover -s test
```

## Status

Tested on the PC with a simulated `/battery_state` (all colours, no-data state, shutdown, tmux rendering). Not yet run on the robot, so the real voltage and percentage values from the OpenCR, and the two limits, still need checking.

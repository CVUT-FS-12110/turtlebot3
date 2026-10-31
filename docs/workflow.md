# What to run where, and how to update

Two machines work together, and every instruction in this repository belongs to one of them:

| | **PC** (Windows 11 + WSL2) | **ROBOT** (Raspberry Pi 3B+, 1 GB RAM) |
|---|---|---|
| Role | SLAM, Nav2, explorer, RViz, teleop, Gazebo | bring-up: motors, OpenCR, LiDAR, optional EKF |
| ROS packages | ROS 2 desktop, Gazebo, Nav2, `slam_toolbox`, `auto_mapper` | ROS 2 base, TurtleBot3 packages, `robot_localization` |
| Builds with `colcon` | `~/turtlebot3_ws` including `auto_mapper` | `~/turtlebot3_ws` with TurtleBot3 packages only (slow, rarely) |
| Scripts from this repo | `scripts/mapping.sh`, `scripts/check.sh` | `robot/launch/bringup_ekf.launch.py`, `scripts/check.sh` |
| Shell | WSL2 terminal | SSH (`ssh turtle@turtlebot.local`), preferably inside tmux |

Both machines need the same `ROS_DOMAIN_ID`, `TURTLEBOT3_MODEL` and `RMW_IMPLEMENTATION` (see [Common settings](../README.md#common-settings)). The installer writes them to `~/.bashrc`.

## Update from GitHub

This repository is cloned to `~/turtlebot3-setup` on **both** machines. Update both, then do only what the changes need.

### PC (WSL2)

```bash
git -C ~/turtlebot3-setup pull
```

`auto_mapper` is linked into the workspace (`~/turtlebot3_ws/src/auto_mapper` → `~/turtlebot3-setup/auto_mapper`) and built with `--symlink-install`. What to do after the pull:

| What changed | PC action |
|---|---|
| Python code or YAML in `auto_mapper/` | nothing, takes effect on the next start |
| New or removed files in `auto_mapper/launch` or `config`, or `setup.py` / `package.xml` | rebuild (below) |
| `scripts/mapping.sh`, docs | nothing |
| `scripts/install.sh` installs new apt packages | `sudo apt install <package>` or run `scripts/install.sh` again (safe, finished steps are skipped) |

```bash
cd ~/turtlebot3_ws && source /opt/ros/jazzy/setup.bash && colcon build --symlink-install --packages-select auto_mapper
source ~/turtlebot3_ws/install/setup.bash
```

Open a new terminal (or `source` again) after a build, otherwise ROS does not see the new files. If the link is missing:

```bash
ln -s ~/turtlebot3-setup/auto_mapper ~/turtlebot3_ws/src/auto_mapper
```

### ROBOT (Pi, over SSH)

```bash
git -C ~/turtlebot3-setup pull
```

Nothing is built on the Pi for this repository: `robot/` contains only a launch file, a config and a script, which run straight from the clone. **Do not build `auto_mapper` or install `slam_toolbox`, Nav2 or RViz on the Pi**; they do not fit in 1 GB of RAM and the SD card. After a pull:

| What changed | ROBOT action |
|---|---|
| `robot/` (EKF launch, config, covariance fixer) | nothing, restart the bring-up |
| `scripts/install.sh` adds a robot package | `sudo apt install <package>`, for example `ros-jazzy-robot-localization` for the EKF |
| `scripts/check.sh`, docs | nothing |

### Both machines

Check that both run the same version:

```bash
git -C ~/turtlebot3-setup log --oneline -1
```

If `git pull` complains about local changes, see them with `git -C ~/turtlebot3-setup status`. To drop them and match GitHub exactly: `git -C ~/turtlebot3-setup fetch && git -C ~/turtlebot3-setup reset --hard origin/master`. Details in [robot-raspberry-pi.md](robot-raspberry-pi.md).

The ROBOTIS sources (`~/turtlebot3_ws/src/turtlebot3`, `turtlebot3_msgs`, ...) are cloned once by the installer and are **not** updated by `git pull` in this repository. Leave them alone unless a fix requires it. On the Pi a rebuild of them takes over an hour (see [robot-raspberry-pi.md](robot-raspberry-pi.md)).

## Daily run order

The robot always starts first.

### 1. ROBOT (Pi, over SSH)

Inside tmux, so an SSH drop does not stop the robot:

```bash
tmux new -A -s robot
export TURTLEBOT3_MODEL=burger
ros2 launch turtlebot3_bringup robot.launch.py
```

Or with the EKF odometry (**instead of**, never together with, the line above; see [ekf.md](ekf.md)):

```bash
ros2 launch ~/turtlebot3-setup/robot/launch/bringup_ekf.launch.py
```

### 2. PC (WSL2)

Check that the robot's data arrive (`/scan` must run at about 5 Hz):

```bash
ros2 daemon stop
ros2 topic hz /scan
```

Then start the mapping, see [auto-mapping.md](auto-mapping.md):

```bash
~/turtlebot3-setup/scripts/mapping.sh          # manual: SLAM + RViz + keyboard teleop
~/turtlebot3-setup/scripts/mapping.sh auto     # autonomous: auto_mapper
~/turtlebot3-setup/scripts/mapping.sh --sim    # Gazebo instead of the robot
```

### 3. Finish

PC: save the map **before** stopping SLAM, then stop the session.

```bash
mkdir -p ~/maps && ros2 run nav2_map_server map_saver_cli -f ~/maps/room
~/turtlebot3-setup/scripts/mapping.sh stop
```

ROBOT: stop the bring-up with `Ctrl+C`, then `sudo shutdown now` before switching the power off.

## Which machine for what

| Task | PC | ROBOT |
|---|---|---|
| `mapping.sh`, SLAM, Nav2, explorer, RViz, teleop, Gazebo | ✅ | ❌ |
| `colcon build --packages-select auto_mapper` | ✅ | ❌ |
| `turtlebot3_bringup` (with or without EKF) | ❌ | ✅ |
| `apt install ros-jazzy-slam-toolbox` | ✅ | ❌ |
| `apt install ros-jazzy-robot-localization` | not needed | ✅ (EKF only) |
| `git pull` of this repository | ✅ | ✅ |
| `scripts/check.sh <other-host-ip>` | ✅ | ✅ |
| `scripts/install.sh` | role `pc` | role `robot` |

Never run two bring-ups at once (normal and EKF): both publish the odometry and the `odom → base_footprint` transform.

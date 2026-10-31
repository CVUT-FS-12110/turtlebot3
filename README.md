# TurtleBot3 Burger – ROS 2 Jazzy setup

Setup notes for running a [TurtleBot3](https://www.turtlebot.com/turtlebot3/) Burger with ROS 2 Jazzy.

## Getting it running, in order

Every step says which machine it is for: **PC** (Windows 11 + WSL2) or **ROBOT** (Raspberry Pi). Do them in this order; each one is checked before the next.

| # | Machine | Step | Guide |
|---|---|---|---|
| 1 | PC | Set up WSL2, install ROS 2 Jazzy, build the TurtleBot3 workspace and try the simulation | [docs/remote-pc-wsl2.md](docs/remote-pc-wsl2.md), installer: [Quick install](#quick-install) |
| 2 | ROBOT | Prepare the SD card and the Raspberry Pi, install ROS 2 and build the workspace | [docs/robot-raspberry-pi.md](docs/robot-raspberry-pi.md) |
| 3 | ROBOT | Flash the ROS 2 firmware to the OpenCR and bring up the robot (motors, LiDAR) | [docs/robot-raspberry-pi.md](docs/robot-raspberry-pi.md), [docs/opencr-firmware.md](docs/opencr-firmware.md) |
| 4 | both | Check that the PC sees the robot's topics (same `ROS_DOMAIN_ID`, CycloneDDS, multicast) | [`scripts/check.sh`](scripts/check.sh), [Common settings](#common-settings) |
| 5 | PC (+ ROBOT) | Drive the robot by hand with the keyboard (PC) or the Evolveo gamepad (plugged into the Pi) | [docs/gamepad.md](docs/gamepad.md), [docs/auto-mapping.md](docs/auto-mapping.md) |
| 6 | PC | Map a room by hand (SLAM + teleop), then let the robot explore on its own | [docs/auto-mapping.md](docs/auto-mapping.md) |
| 7 | ROBOT | Optional: filter the odometry with an EKF for better maps | [docs/ekf.md](docs/ekf.md) |

From the second day on, and for updating both machines from GitHub, use [docs/workflow.md](docs/workflow.md): what to run on the PC, what on the Raspberry Pi, and in which order. When something does not work, see [docs/troubleshooting.md](docs/troubleshooting.md).

## Hardware

| Part | Model |
|---|---|
| Robot | TurtleBot3 Burger |
| Single-board computer | Raspberry Pi 3B+ (1 GB RAM) |
| LiDAR | LDS-01 |
| Motor controller | OpenCR 1.0 |
| Remote PC | Windows 11 + WSL2 (Ubuntu 24.04) |

## Software stack

- ROS 2 **Jazzy Jalisco** on Ubuntu **24.04** (both PC and robot)
- Gazebo **Harmonic** for simulation
- TurtleBot3 packages built from the `jazzy` branches of the ROBOTIS repositories

## Status

| Step | Guide | Status |
|---|---|---|
| Remote PC (WSL2) + simulation | [docs/remote-pc-wsl2.md](docs/remote-pc-wsl2.md) | ✅ working |
| OpenCR firmware (sources, features) | [docs/opencr-firmware.md](docs/opencr-firmware.md) | 📖 overview only |
| Raspberry Pi, OpenCR flashing, bring-up | [docs/robot-raspberry-pi.md](docs/robot-raspberry-pi.md) | ✅ working (bring-up, motors and LiDAR tested on the robot) |
| Gamepad teleop (Evolveo Fighter F1) | [docs/gamepad.md](docs/gamepad.md) | 📝 written, mapping measured, not yet driven |
| Problems and checks | [docs/troubleshooting.md](docs/troubleshooting.md), [`scripts/check.sh`](scripts/check.sh) | 📖 |
| Automatic mapping (`auto_mapper`) | [docs/auto-mapping.md](docs/auto-mapping.md) | 📝 written, frontier logic unit-tested, not yet run in Gazebo or on the robot |
| EKF odometry (`robot/`) | [docs/ekf.md](docs/ekf.md) | 📝 written, not yet run on the robot |
| SLAM and navigation on the real robot | – | ⏳ not done yet |

## Quick install

[`scripts/install.sh`](scripts/install.sh) is an interactive installer for both the remote PC and the robot. It asks for the role, model, `ROS_DOMAIN_ID`, CycloneDDS and (on the robot) LiDAR model, swap, Wi-Fi power saving and OpenCR flashing, shows a summary, then installs ROS 2 Jazzy, builds the TurtleBot3 workspace and writes the environment to `~/.bashrc`. Steps already done (apt source, cloned repositories) are skipped.

```bash
git clone https://github.com/CVUT-FS-12110/turtlebot3.git ~/turtlebot3-setup
~/turtlebot3-setup/scripts/install.sh
```

The first question offers to run the installer inside **tmux** (default yes on a Raspberry Pi or over SSH). It installs tmux, adds a block to `~/.tmux.conf` tuned for ROS 2 (long scrollback, mouse scrolling, vi keys in copy mode, window names that stay, new panes in the current directory, `ROS_DOMAIN_ID`, robot model and load average in the status bar) and restarts itself in a session called `turtlebot3`, so an SSH drop does not stop a long build. Detach with `Ctrl+b` then `d`, and reattach later with `tmux attach -t turtlebot3`.

If `~/turtlebot3-setup` already exists, update it with `git -C ~/turtlebot3-setup pull` and run the installer again.

Add `--yes` to accept all defaults without asking.

The PC role follows the verified [remote PC guide](docs/remote-pc-wsl2.md). The robot role follows the ROBOTIS e-Manual but has not been tested on the robot yet. In WSL, the Windows-side network steps (`.wslconfig`, firewall) still have to be done by hand.

## Updating from GitHub

This repository is cloned to `~/turtlebot3-setup` on both machines. After every change on GitHub, update **both**, then do only what the changes need (details in [docs/workflow.md](docs/workflow.md#update-from-github)).

**PC (WSL2):**

```bash
git -C ~/turtlebot3-setup pull
```

Rebuild `auto_mapper` only if launch or config files were added or removed, or `setup.py` / `package.xml` changed. Edits to its Python code and YAML need no build (`--symlink-install`). Open a new terminal afterwards.

```bash
cd ~/turtlebot3_ws && source /opt/ros/jazzy/setup.bash && colcon build --symlink-install --packages-select auto_mapper
```

**ROBOT (Raspberry Pi, over SSH):**

```bash
git -C ~/turtlebot3-setup pull
```

Nothing is built on the Pi for this repository; `robot/` runs straight from the clone. Restart the bring-up if `robot/` changed. Never build `auto_mapper` or install SLAM/Nav2/RViz there.

If the change adds a package to `scripts/install.sh`, install just that one with `sudo apt install <package>` on the machine it is for, or run the installer again (finished steps are skipped). Check that both machines run the same version with `git -C ~/turtlebot3-setup log --oneline -1`. If `git pull` complains about local changes, see [docs/robot-raspberry-pi.md](docs/robot-raspberry-pi.md).

## Common settings

The PC and the robot must use the same values:

```bash
export ROS_DOMAIN_ID=30
export TURTLEBOT3_MODEL=burger
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
```

Verify the setup (and the link between the machines) with `scripts/check.sh [other-host-ip]`.

## References

- [ROBOTIS TurtleBot3 e-Manual](https://emanual.robotis.com/docs/en/platform/turtlebot3/overview/)
- [OpenCR source code (ROBOTIS-GIT/OpenCR)](https://github.com/ROBOTIS-GIT/OpenCR), [OpenCR 1.0 e-Manual](https://emanual.robotis.com/docs/en/parts/controller/opencr10/)
- [Ubuntu 24.04 (Noble) images](https://cdimage.ubuntu.com/ubuntu/releases/noble/release/) – Raspberry Pi Server image for the robot
- [ROS 2 Jazzy documentation](https://docs.ros.org/en/jazzy/)

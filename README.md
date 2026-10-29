# TurtleBot3 Burger – ROS 2 Jazzy setup

Setup notes for running a [TurtleBot3](https://www.turtlebot.com/turtlebot3/) Burger with ROS 2 Jazzy.

## Where to start

| I want to… | Go to |
|---|---|
| Install everything quickly on the PC or the robot | [Quick install](#quick-install) (`scripts/install.sh`) |
| Set up the Windows 11 PC (WSL2) and try the simulation | [docs/remote-pc-wsl2.md](docs/remote-pc-wsl2.md) |
| Set up the Raspberry Pi, flash the OpenCR and bring up the robot | [docs/robot-raspberry-pi.md](docs/robot-raspberry-pi.md) |
| Find out what the OpenCR firmware does and where its sources are | [docs/opencr-firmware.md](docs/opencr-firmware.md) |
| Drive the robot with the Evolveo Fighter F1 gamepad | [docs/gamepad.md](docs/gamepad.md) |
| Fix a problem (no topics, OpenCR not found, lag over Wi-Fi) | [docs/troubleshooting.md](docs/troubleshooting.md) |
| Check that the setup and the PC–robot link work | [`scripts/check.sh`](scripts/check.sh) – see [Common settings](#common-settings) |

Recommended order: PC and simulation → Raspberry Pi and bring-up → `check.sh` → SLAM and navigation.

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
| Raspberry Pi, OpenCR flashing, bring-up | [docs/robot-raspberry-pi.md](docs/robot-raspberry-pi.md) | 📝 written, not tested on the robot |
| Gamepad teleop (Evolveo Fighter F1) | [docs/gamepad.md](docs/gamepad.md) | 📝 written, mapping measured, not yet driven |
| Problems and checks | [docs/troubleshooting.md](docs/troubleshooting.md), [`scripts/check.sh`](scripts/check.sh) | 📖 |
| SLAM and navigation on the real robot | – | ⏳ not done yet |

## Quick install

[`scripts/install.sh`](scripts/install.sh) is an interactive installer for both the remote PC and the robot. It asks for the role, model, `ROS_DOMAIN_ID`, CycloneDDS and (on the robot) LiDAR model, swap, Wi-Fi power saving and OpenCR flashing, shows a summary, then installs ROS 2 Jazzy, builds the TurtleBot3 workspace and writes the environment to `~/.bashrc`. Steps already done (apt source, cloned repositories) are skipped.

```bash
git clone https://github.com/CVUT-FS-12110/turtlebot3.git ~/turtlebot3-setup
~/turtlebot3-setup/scripts/install.sh
```

Add `--yes` to accept all defaults without asking.

The PC role follows the verified [remote PC guide](docs/remote-pc-wsl2.md). The robot role follows the ROBOTIS e-Manual but has not been tested on the robot yet. In WSL, the Windows-side network steps (`.wslconfig`, firewall) still have to be done by hand.

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

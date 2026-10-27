# TurtleBot3 Burger – ROS 2 Jazzy setup

Setup notes for running a [TurtleBot3](https://www.turtlebot.com/turtlebot3/) Burger with ROS 2 Jazzy.

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
| Raspberry Pi, OpenCR firmware, bring-up | – | ⏳ not done yet |
| SLAM and navigation on the real robot | – | ⏳ not done yet |

## Quick install

[`scripts/install.sh`](scripts/install.sh) is an interactive installer for both the remote PC and the robot. It asks for the role, model, `ROS_DOMAIN_ID` and (on the robot) LiDAR model, swap and OpenCR flashing, shows a summary, then installs ROS 2 Jazzy, builds the TurtleBot3 workspace and writes the environment to `~/.bashrc`. Steps already done (apt source, cloned repositories) are skipped.

```bash
git clone <this-repo-url> ~/turtlebot3-setup
~/turtlebot3-setup/scripts/install.sh            # interactive
~/turtlebot3-setup/scripts/install.sh --dry-run  # only print the commands
~/turtlebot3-setup/scripts/install.sh --yes      # accept all defaults
```

The PC role follows the verified [remote PC guide](docs/remote-pc-wsl2.md). The robot role follows the ROBOTIS e-Manual but has not been tested on the robot yet. In WSL, the Windows-side network steps (`.wslconfig`, firewall) still have to be done by hand.

## Common settings

The PC and the robot must use the same values:

```bash
export ROS_DOMAIN_ID=30
export TURTLEBOT3_MODEL=burger
```

## References

- [ROBOTIS TurtleBot3 e-Manual](https://emanual.robotis.com/docs/en/platform/turtlebot3/overview/)
- [ROS 2 Jazzy documentation](https://docs.ros.org/en/jazzy/)

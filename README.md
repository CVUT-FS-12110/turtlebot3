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

## Common settings

The PC and the robot must use the same values:

```bash
export ROS_DOMAIN_ID=30
export TURTLEBOT3_MODEL=burger
```

## References

- [ROBOTIS TurtleBot3 e-Manual](https://emanual.robotis.com/docs/en/platform/turtlebot3/overview/)
- [ROS 2 Jazzy documentation](https://docs.ros.org/en/jazzy/)

# Automatic map generation

The [`auto_mapper`](../auto_mapper) package lets the robot build a map of a room on its own. It runs on the **PC**; the robot (or Gazebo) only provides `/scan`, `/odom` and TF.

```
/scan, /odom, TF ──► slam_toolbox ──► /map ──► explorer ──► NavigateToPose ──► Nav2 ──► /cmd_vel
                                                  │
                                      no frontier left ──► map_saver_cli ──► ~/maps/auto_map.{yaml,pgm}
```

The `explorer` node looks for **frontiers**: free cells that touch unknown cells. It groups them into clusters, keeps the ones the robot can reach through known free space, and sends the cheapest one (path length minus a bonus for a long frontier) to Nav2. A goal that fails, times out or is reached without clearing the frontier is blacklisted. When no reachable frontier is left for 5 ticks in a row, it saves the map and exits.

## Install

`scripts/install.sh` (PC role) installs `slam_toolbox`, links the package into `~/turtlebot3_ws/src` and builds it. On an existing setup:

```bash
sudo apt install ros-jazzy-slam-toolbox
ln -s ~/turtlebot3-setup/auto_mapper ~/turtlebot3_ws/src/auto_mapper
cd ~/turtlebot3_ws && colcon build --symlink-install --packages-select auto_mapper
source install/setup.bash
```

## Run

In the simulation:

```bash
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py          # terminal 1
ros2 launch auto_mapper auto_mapper.launch.py use_sim_time:=true  # terminal 2
```

Open RViz (`ros2 run rviz2 rviz2`), add `/map` and `/plan` to watch it. On the real robot start the bring-up on the Pi first ([robot-raspberry-pi.md](robot-raspberry-pi.md)) and launch without `use_sim_time`.

The finished map is in `~/maps/auto_map.yaml` and `.pgm`. Stop the exploration early with `Ctrl+C` and save by hand:

```bash
ros2 run nav2_map_server map_saver_cli -f ~/maps/room
```

## Settings

[`config/explorer.yaml`](../auto_mapper/config/explorer.yaml) – the explorer, [`config/slam_toolbox.yaml`](../auto_mapper/config/slam_toolbox.yaml) – SLAM tuned for the LDS-01 (range limited to 3 m, loop closing on). Another file can be passed with `explorer_params:=` and `slam_params:=`.

| Parameter | Default | Meaning |
|---|---|---|
| `min_frontier_size` | 5 | Ignore frontiers shorter than this many cells (5 cm each) |
| `size_weight` | 0.5 | Higher prefers long frontiers over near ones; 0 means always the nearest |
| `blacklist_radius` | 0.5 m | Area around a failed goal that is not tried again |
| `goal_timeout` | 90 s | Time after which a goal is cancelled and blacklisted |
| `finish_after_empty_ticks` | 5 | Ticks without a frontier before the map is saved |

## Tests

The frontier logic has no ROS dependency, so its unit tests run anywhere with numpy:

```bash
cd auto_mapper && python3 -m unittest discover -s test
```

## Status and limits

- The frontier logic is unit-tested. The node, launch file and Nav2 integration are **not yet run** in Gazebo or on the robot, so the first run may need tuning.
- The launch file reuses the Nav2 parameters from `turtlebot3_navigation2` (`$TURTLEBOT3_MODEL.yaml`) and starts only the Nav2 navigation servers, without AMCL and `map_server`.
- On the real robot keep the gamepad ([gamepad.md](gamepad.md)) at hand to take over if the robot gets stuck.
- The explorer treats all known free cells as passable; Nav2 checks clearance and rejects goals too close to walls, which are then blacklisted.

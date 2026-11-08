# Automatic map generation

The [`auto_mapper`](../auto_mapper) package lets the robot build a map of a room on its own. It runs on the **PC**; the robot (or Gazebo) only provides `/scan`, `/odom` and TF.

```
/scan, /odom, TF ──► slam_toolbox ──► /map ──► explorer ──► NavigateToPose ──► Nav2 ──► /cmd_vel
                                                  │
                                      no frontier left ──► map_saver_cli ──► ~/maps/auto_map.{yaml,pgm}
```

The `explorer` node first turns the robot once in place (Nav2 `spin`), so SLAM starts with all the surroundings. Then it looks for **frontiers**: free cells that touch unknown cells. It works on the map reduced to 5 cm cells, so single unknown cells between the rays of a scan do not count. It groups the frontier cells into clusters and keeps the ones the robot can reach through known free space with 15 cm clearance from obstacles (gaps narrower than the robot are skipped). It sends the cheapest one (path length minus a bonus for a long frontier) to Nav2. Cells closer than 0.35 m to the robot are never goals, because Nav2 would report them as reached without moving.

A goal whose surroundings get explored on the way is cancelled and the next one follows at once. A goal that fails, times out or is reached without clearing its frontier is blacklisted, judged 3 s later so that the map has caught up. When no reachable frontier is left for 5 ticks in a row, it clears the blacklist and tries those goals once more. Then it saves the map and exits.

Nav2 rejects goals until all its servers are active; that is not held against the goal, the explorer just tries again 2 s later. If the robot ends up outside the known map (Nav2 cannot plan from there), it turns in place to let SLAM grow the map; after 3 such turns without success it gives up and saves what there is. All times follow the ROS clock, so they also hold in a slow simulation.

The launch file starts Nav2 with the ROBOTIS parameters for the Burger, with two changes. `collision_monitor` only stops the robot after 1 s without a scan instead of 0.2 s; with 0.2 s the scan period plus Wi-Fi jitter stopped the robot hundreds of times in the simulation. The top speed is 0.18 m/s, set with `max_speed:=` (the default 0.3 m/s is above the 0.22 m/s the Burger can do).

## Install

`scripts/install.sh` (PC role) installs `slam_toolbox`, links the package into `~/turtlebot3_ws/src` and builds it. On an existing setup:

```bash
sudo apt install ros-jazzy-slam-toolbox
ln -s ~/turtlebot3-setup/auto_mapper ~/turtlebot3_ws/src/auto_mapper
cd ~/turtlebot3_ws && colcon build --symlink-install --packages-select auto_mapper
source install/setup.bash
```

## One command (tmux)

[`scripts/mapping.sh`](../scripts/mapping.sh) opens a tmux session on the **PC** with the launch, RViz, keyboard teleop and a `/scan` rate monitor in one window. Start the robot first (bring-up on the Pi, see [robot-raspberry-pi.md](robot-raspberry-pi.md)), then:

```bash
~/turtlebot3-setup/scripts/mapping.sh            # manual: SLAM + teleop, drive with the keyboard
~/turtlebot3-setup/scripts/mapping.sh --gamepad  # manual, drive with the gamepad on the robot (no keyboard teleop)
~/turtlebot3-setup/scripts/mapping.sh auto       # autonomous: auto_mapper (SLAM + Nav2 + explorer)
~/turtlebot3-setup/scripts/mapping.sh --sim      # against Gazebo (add use_sim_time)
```

RViz opens with [`auto_mapper/config/mapping.rviz`](../auto_mapper/config/mapping.rviz) in manual mode (map, `/scan`, robot model, TF; the LiDAR is subscribed as best effort, which is how it publishes) and with the Nav2 view in `auto` mode. The Nav2 view is not used by hand, because its panel keeps printing `controller_server service not available` while Nav2 does not run.

The status bar of the session shows the robot's battery voltage ([battery-status.md](battery-status.md#pc-wsl2)); yellow below 11.0 V, red below 10.5 V (stop driving).

With `--gamepad` the pane shows only hints: the keyboard teleop keeps publishing zero speed while idle and would fight the gamepad, which makes the robot jerk ([gamepad.md](gamepad.md#problems)). Start the robot with `bringup.launch.py gamepad:=true`.

Teleop keys work only in the teleop pane: `w`/`x` faster forward/backward, `a`/`d` turn, `s` or space stops. Mouse works in the panes. Detach with `Ctrl+b` then `d`, reattach with `tmux attach -t mapping`, end with `mapping.sh stop`. From Windows one click opens it in a new window: `wt wsl -e ~/turtlebot3-setup/scripts/mapping.sh`.

`slam_toolbox` starts with `use_sim_time:=true` unless told otherwise, so on the real robot the script always passes `use_sim_time:=false` explicitly. When running the SLAM command by hand, do the same, or it waits for a Gazebo clock and builds no map.

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

[`config/explorer.yaml`](../auto_mapper/config/explorer.yaml) – the explorer, [`config/slam_toolbox.yaml`](../auto_mapper/config/slam_toolbox.yaml) – SLAM tuned for the LDS-01 (range limited to 3 m, loop closing on; the RPLiDAR A1M8 reads up to 12 m, so `max_laser_range` can be raised, see [rplidar.md](rplidar.md)). Another file can be passed with `explorer_params:=` and `slam_params:=`.

| Parameter | Default | Meaning |
|---|---|---|
| `analysis_resolution` | 0.05 m | Cell size the map is reduced to before looking for frontiers |
| `min_frontier_size` | 5 | Ignore frontiers shorter than this many cells (5 cm each) |
| `size_weight` | 0.5 | Higher prefers long frontiers over near ones; 0 means always the nearest |
| `clearance` | 0.15 m | Distance from obstacles for paths and goals (Burger radius 0.105 m + margin) |
| `min_goal_distance` | 0.35 m | Nearer frontier cells are no goals |
| `goal_frontier_radius` | 0.25 m | A goal counts as explored when no frontier is left this close to it |
| `blacklist_radius` | 0.5 m | Area around a failed goal that is not tried again |
| `blacklist_retries` | 1 | How often the blacklist is cleared and retried before finishing |
| `initial_spin` | true | Turn 360° before the first goal |
| `max_offmap_spins` | 3 | Turns while outside the map before giving up |
| `goal_timeout` | 90 s | Time after which a goal is cancelled and blacklisted |
| `settle_time` | 3 s | Wait after a goal before judging it (the map updates every 2 s) |
| `finish_after_empty_ticks` | 5 | Ticks without a frontier before the map is saved |

Launch arguments of `auto_mapper.launch.py`: `use_sim_time`, `max_speed` (0.18 m/s), `explorer_params`, `slam_params`.

## Tests

The frontier logic has no ROS dependency, so its unit tests run anywhere with numpy:

```bash
cd auto_mapper && python3 -m unittest discover -s test
```

## Status and limits

- **Gazebo, `turtlebot3_world`:** verified on the PC (WSL2, headless Gazebo, Nav2 1.3.13). The robot explores the whole arena by itself, finishes and saves the map in 5 to 7 minutes. No stop from `collision_monitor`.
- **Gazebo, `turtlebot3_house`:** not usable in WSL2. The world renders so slowly that the LiDAR runs at about 1 Hz, and SLAM stopped adding scans after the first one. The explorer then turned in place; this run is why it now gives up after `max_offmap_spins`. Try it on a PC with a GPU, or skip it.
- **Real robot:** not run yet, see [First test on the robot](#first-test-on-the-robot).
- The launch file reuses the Nav2 parameters from `turtlebot3_navigation2` (`$TURTLEBOT3_MODEL.yaml`, with the changes above). It starts only the Nav2 navigation servers, without AMCL and `map_server`.
- SLAM ignores readings beyond the LiDAR's range, so in a room larger than that no free space is seen and no frontier appears. This does not matter for the RPLiDAR (12 m), but it did for the simulated LDS-01 (3.5 m) in the large house rooms.

## First test on the robot

The robot code does not change for automatic mapping; everything new runs on the PC.

**ROBOT (Pi, over SSH):** the usual bring-up, without the gamepad. Nav2 and the gamepad would both publish `/cmd_vel` and fight each other.

```bash
ros2 launch ~/turtlebot3-setup/robot/launch/bringup.launch.py
```

**PC (WSL2):** switch to the test branch, rebuild once (`package.xml` changed), start the auto mode:

```bash
git -C ~/turtlebot3-setup fetch && git -C ~/turtlebot3-setup checkout feature/auto-mapping
cd ~/turtlebot3_ws && source /opt/ros/jazzy/setup.bash && colcon build --symlink-install --packages-select auto_mapper
~/turtlebot3-setup/scripts/mapping.sh auto
```

Start in a small closed room with nothing the LiDAR cannot see (glass, low edges, stairs). Stay next to the robot. **Stop:** `Ctrl+C` in the `auto_mapper` pane, or switch the robot off. What to watch in the `auto_mapper` pane:

- `Turning around to scan the surroundings`, then `Going to frontier ...`: it works.
- `Nav2 is not accepting goals yet` more than a few times: Nav2 did not start, look for `[ERROR]` above.
- `Robot to stop due to invalid source` from `collision_monitor`: scans arrive too late (Wi-Fi, clock offset, see [troubleshooting.md](troubleshooting.md)).
- The robot oscillates in front of an obstacle: lower the speed with `ros2 launch auto_mapper auto_mapper.launch.py max_speed:=0.12`.

Back on master: `git -C ~/turtlebot3-setup checkout master` and the same `colcon build`.

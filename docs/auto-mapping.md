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

The launch file starts Nav2 with the ROBOTIS parameters for the Burger, with three changes. `collision_monitor` only stops the robot after 1 s without a scan instead of 0.2 s; with 0.2 s the scan period plus Wi-Fi jitter stopped the robot hundreds of times in the simulation. The top speed is 0.18 m/s, set with `max_speed:=` (the default 0.3 m/s is above the 0.22 m/s the Burger can do). The costmaps use the 2.5 cm cells of the SLAM map instead of 5 cm, so RViz shows them as fine as the map; this makes Nav2 handle four times as many cells.

## Geofence

The robot can be kept inside a polygon. By default the explorer **waits for one**: after its first turn it does not send a goal until the geofence is set (`require_geofence: false` explores without). It is drawn on the **PC**, in RViz, in the current map, so it does not matter where the robot started. A rough outline is enough: draw it a little inside the walls, the explorer and Nav2 keep another 15 cm from the edge.

1. Pick the **Publish Point** tool in the RViz toolbar (the fixed frame must stay `map`).
2. Click the vertices one after another. They show as orange spheres and a line. You can click outside the known map.
3. Close the polygon by clicking within 30 cm of the first vertex (at least 3 vertices). It turns red and the explorer starts.

The `explorer` log shows each vertex and `Geofence set: ...`. The polygon is rejected, and drawing starts again, if its edges cross, it is almost empty or **the robot is not inside it**.

What it does:
- The explorer treats the outside as a wall: a frontier outside is no goal, and neither is one that can only be reached through the outside. When nothing is left inside, it saves the map. The map then has unexplored space beyond the fence.
- The explorer also sends the polygon to the Nav2 **keepout filter** (`/keepout_filter_mask`, `/costmap_filter_info`), which the launch file adds to the global and the local costmap. The outside is lethal there, so the planner does not route through it and the controller does not drive into it. The filter does not inflate, so the planner would take the centre of the robot right up to the line with its body across it. The mask therefore also raises the cost inside the edge, from 0 at `keepout_ramp` (30 cm) to nearly inscribed at the line. It stays below the inscribed cost on purpose: a lethal strip along the edge trapped the robot in a test (`No valid trajectories`, it could not drive off). The mask reaches `keepout_extra` (10 m) past the polygon; the costmap is not filtered beyond that.
- The `explorer` keeps running after it saved the map, as long as a geofence is set. Nav2 asks for the latched mask again whenever it resets a costmap (for example in its recovery behaviours), and only this node can send it. Stop it with `Ctrl+C` like the rest.

Change it: `ros2 service call /explorer/clear_geofence std_srvs/srv/Empty` removes it (the running goal is cancelled, the mask is emptied) and the explorer waits for a new one. A polygon known in advance can go into [`explorer.yaml`](../auto_mapper/config/explorer.yaml) as `geofence: [x1, y1, x2, y2, ...]` in the `map` frame; the point `(0, 0)` is where SLAM started, with the x axis along the robot's heading then.

Limits:
- The geofence belongs to the running SLAM. `map` starts where the robot started, so after a restart of SLAM (`--restart`) the polygon is drawn again; it is not matched to an earlier map. A small shift of the map after a loop closure moves the walls, not the polygon, which is why a margin from the edge is kept.
- It only restrains the autonomous mode. The keyboard teleop and the gamepad drive the robot wherever you steer it.
- The keepout filter only marks costmap cells as lethal; nothing stops the robot if it is pushed across the line. Planning from inside a lethal cell may then fail, so the explorer would blacklist its goals. Stop the exploration and move the robot back inside.

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

### Switching between manual and automatic

A running manual session (with or without `--gamepad`) can hand the robot to Nav2 and the explorer and take it back. SLAM keeps running in the `slam_toolbox` pane, so the map built so far is kept both ways. For example, drive through a narrow door by hand and let the robot finish the room on its own:

```bash
~/turtlebot3-setup/scripts/mapping.sh explore   # stops the keyboard teleop, starts Nav2 + explorer in window "explore"
~/turtlebot3-setup/scripts/mapping.sh drive     # stops them (the robot halts) and starts the keyboard teleop again
```

`explore` starts `auto_mapper.launch.py slam:=false`, which uses the running SLAM instead of starting a second one. RViz keeps the manual view; its group **Nav2 and explorer** then shows the global plan (green), the local plan (blue), both costmaps, the robot footprint, the frontier targets (yellow) and the current goal (magenta, topic `/explorer/frontiers`). The explorer begins with its turn in place and explores from the current map. With the gamepad, keep your hands off it while exploring: holding the enable button would fight Nav2.

Switching needs a session started by this version of `mapping.sh`. `mapping.sh auto` does not need it: it runs everything from the start. Switching `manual` ↔ `auto` with `--restart` starts a new SLAM and loses the map.

RViz opens with [`auto_mapper/config/mapping.rviz`](../auto_mapper/config/mapping.rviz) in both modes (map, `/scan`, robot model, TF; the LiDAR is subscribed as best effort, which is how it publishes; the group **Nav2 and explorer** with plans, costmaps, frontiers and the geofence; the **Publish Point** tool for drawing the geofence). The Nav2 default view is not used any more, because its panel keeps printing `controller_server service not available` while Nav2 does not run, and it has neither the geofence nor the Publish Point tool.

The status bar of the session shows the robot's battery voltage ([battery-status.md](battery-status.md#pc-wsl2)); yellow below 11.0 V, red below 10.5 V (stop driving).

With `--gamepad` the pane shows only hints: the keyboard teleop keeps publishing zero speed while idle and would fight the gamepad, which makes the robot jerk ([gamepad.md](gamepad.md#problems)). Start the robot with `bringup.launch.py gamepad:=true`.

Teleop keys work only in the teleop pane: `w`/`x` faster forward/backward, `a`/`d` turn, `s` or space stops. Mouse works in the panes. Detach with `Ctrl+b` then `d`, reattach with `tmux attach -t mapping`, end with `mapping.sh stop`.

`mapping.sh stop` and `--restart` first stop everything with `Ctrl+C` in each pane, then send the robot zero speed (`/cmd_vel`), then kill the session. Neither `turtlebot3_node` nor the OpenCR firmware stops the wheels when commands stop coming. Before this was fixed, the robot kept driving after a restart, still turning at 1 rad/s in the simulation. Never end the session with `tmux kill-session` or by closing the terminal; if you did, stop the robot by hand:

```bash
ros2 topic pub --times 5 -r 10 /cmd_vel geometry_msgs/msg/TwistStamped "{}"
```

Both also work from the session's own `shell` window: the script then finishes in the background (log in `/tmp/mapping_sh_restart.log`) and you attach to the new session with `tmux attach -t mapping`. From Windows one click opens it in a new window: `wt wsl -e ~/turtlebot3-setup/scripts/mapping.sh`.

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
| `map_save_timeout` | 10 s | How long `map_saver_cli` waits for the map (its own default of 2 s failed in 2 of 5 simulation runs) |
| `require_geofence` | true | Wait for a [geofence](#geofence) before the first goal |
| `geofence` | – | Polygon `[x1, y1, x2, y2, ...]` in the `map` frame, instead of drawing it in RViz |
| `geofence_margin` | 0.15 m | Distance from the polygon edge that goals and paths keep |
| `geofence_close_radius` | 0.3 m | A click this close to the first vertex closes the polygon |
| `keepout_ramp` | 0.3 m | Inside the edge, Nav2 costs rise over this distance towards the line |
| `keepout_resolution` | 0.05 m | Cell size of the mask sent to the Nav2 keepout filter |
| `keepout_extra` | 10 m | How far the mask reaches past the polygon |

Launch arguments of `auto_mapper.launch.py`: `use_sim_time`, `max_speed` (0.18 m/s), `slam` (`false` uses a SLAM that already runs), `explorer_params`, `slam_params`.

## Tests

The frontier and geofence logic have no ROS dependency, so their unit tests run anywhere with numpy:

```bash
cd auto_mapper && python3 -m unittest discover -s test
```

## Status and limits

- **Gazebo, `turtlebot3_world`:** verified on the PC (WSL2, headless Gazebo, Nav2 1.3.13). The robot explores the whole arena by itself, finishes and saves the map in 5 to 7 minutes. No stop from `collision_monitor`.
- **Gazebo, `turtlebot3_house`:** not usable in WSL2. The world renders so slowly that the LiDAR runs at about 1 Hz, and SLAM stopped adding scans after the first one. The explorer then turned in place; this run is why it now gives up after `max_offmap_spins`. Try it on a PC with a GPU, or skip it.
- **Geofence:** the polygon geometry and the frontier filtering have unit tests. In Gazebo (`turtlebot3_world`, headless, WSL2) a 2.5 x 3 m fence drawn by clicks was tried in five runs. Every time the robot waited after its turn until the fence was set, then explored only the inside in 2 to 4 minutes, and the global costmap was lethal in every cell outside. A Nav2 goal outside was aborted by the planner while the fence was set and succeeded after `clear_geofence`. The mask changed twice on the way: with a plain outside/inside mask the robot crossed the line by 6 mm and stood with its body across it; with a lethal strip inside the edge it stopped inside the strip and could not leave. With the cost ramp (last run) the nearest it came to the line was 19 cm, with no stuck controller. Not run: a real robot, and other fence shapes and rooms. A goal right next to a pillar did not finish with the fence on or off, so the fence is not the cause.
- **Saving the map:** `map_saver_cli` failed with `Failed to spin map subscription` after its default 2 s in 2 of 5 of these runs, so the explorer now passes `map_save_timeout` (10 s). The run after that saved; one run is no proof that it is gone.
- **Real robot:** not run yet, see [First test on the robot](#first-test-on-the-robot).
- The launch file reuses the Nav2 parameters from `turtlebot3_navigation2` (`$TURTLEBOT3_MODEL.yaml`, with the changes above). It starts only the Nav2 navigation servers, without AMCL and `map_server`.
- SLAM ignores readings beyond the LiDAR's range, so in a room larger than that no free space is seen and no frontier appears. This does not matter for the RPLiDAR (12 m), but it did for the simulated LDS-01 (3.5 m) in the large house rooms.

## First test on the robot

The robot code does not change for automatic mapping; everything new runs on the PC.

**ROBOT (Pi, over SSH):** the usual bring-up (with the EKF, `ekf:=false` without), no gamepad. Nav2 and the gamepad would both publish `/cmd_vel` and fight each other.

```bash
ros2 launch ~/turtlebot3-setup/robot/launch/bringup.launch.py
```

**PC (WSL2):** switch to the test branch, rebuild once (`package.xml` changed), start the auto mode:

```bash
git -C ~/turtlebot3-setup fetch && git -C ~/turtlebot3-setup checkout feature/auto-mapping
cd ~/turtlebot3_ws && source /opt/ros/jazzy/setup.bash && colcon build --symlink-install --packages-select auto_mapper
~/turtlebot3-setup/scripts/mapping.sh auto
```

Start in a small closed room with nothing the LiDAR cannot see (glass, low edges, stairs). Stay next to the robot. **Stop:** `mapping.sh stop` (or `drive` after `explore`), `Ctrl+C` in the `auto_mapper` pane, or switch the robot off. What to watch in the `auto_mapper` pane:

- `Turning around to scan the surroundings`, then `Going to frontier ...`: it works.
- `Nav2 is not accepting goals yet` more than a few times: Nav2 did not start, look for `[ERROR]` above.
- `Robot to stop due to invalid source` from `collision_monitor`: scans arrive too late (Wi-Fi, clock offset, see [troubleshooting.md](troubleshooting.md)).
- The robot oscillates in front of an obstacle: lower the speed with `ros2 launch auto_mapper auto_mapper.launch.py max_speed:=0.12`.

Back on master: `git -C ~/turtlebot3-setup checkout master` and the same `colcon build`.

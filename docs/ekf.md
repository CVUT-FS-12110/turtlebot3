# EKF odometry (robot_localization)

By default the robot has no EKF. `turtlebot3_node` integrates the wheel encoders and takes the heading from the IMU orientation, and publishes the result as `/odom` and the `odom → base_footprint` transform. The EKF in [`robot/`](../robot) replaces that transform with a filtered one built from the wheel speed and the gyro yaw rate.

Expect a modest gain: the heading already comes from the IMU. The EKF mainly smooths the odometry and removes jumps; it does not fix wheel slip. Compare the maps with and without it.

```
/odom (vx) ─┐                                   ┌─► odom → base_footprint (TF)
            ├─► covariance_fixer ─► ekf_node ───┤
/imu (gyro) ┘                                   └─► /odometry/filtered
```

`turtlebot3_node` leaves all covariances at zero, which the EKF would read as perfect measurements, so [`covariance_fixer.py`](../robot/covariance_fixer.py) sets realistic ones first. The EKF only fuses the forward speed from `/odom` and the yaw rate from `/imu`; the pose in `/odom` is not used because it already contains the IMU heading.

## ROBOT (Raspberry Pi)

Install the package (the installer does this for new robot setups) and update the repository:

```bash
sudo apt install ros-jazzy-robot-localization
git -C ~/turtlebot3-setup pull
```

Start this **instead of** the normal bring-up (never both):

```bash
export TURTLEBOT3_MODEL=burger
ros2 launch ~/turtlebot3-setup/robot/launch/bringup_ekf.launch.py
```

The launch file starts `robot.launch.py` with `odometry.publish_tf` switched off in a temporary copy of the installed parameters, so the EKF is the only publisher of `odom → base_footprint`. The Pi needs no build.

## PC (WSL2)

Nothing to install or build. SLAM, RViz and teleop run as before. Check the result:

```bash
ros2 run tf2_ros tf2_echo odom base_footprint
ros2 topic hz /odometry/filtered
ros2 topic info /tf -v | grep -i node
```

`/odometry/filtered` should run at about 30 Hz, and `odom → base_footprint` must come from `ekf_filter_node` only.

## Tuning

| What | Where |
|---|---|
| How much the EKF trusts the wheel speed or the gyro | `odom_vx_variance`, `imu_gyro_variance` of `covariance_fixer` (defaults 4e-4 and 1e-4) |
| Filter rate, fused channels | [`robot/config/ekf.yaml`](../robot/config/ekf.yaml) |

A larger variance means less trust. If the map is rotated or smeared after turns, lower `imu_gyro_variance`; if the robot position jumps, raise `odom_vx_variance`.

## Problems

- **Two sources of `odom → base_footprint`** (the tree flickers, `TF_REPEATED_DATA` warnings): the normal `robot.launch.py` is running too. Stop it and use only `bringup_ekf.launch.py`.
- **`has no "publish_tf: true"`**: the installed `turtlebot3_bringup` parameters changed; check `param/burger.yaml` and adjust `params_without_odom_tf` in the launch file.
- **To go back**: stop the EKF launch and start `ros2 launch turtlebot3_bringup robot.launch.py` as before.

## Status

Written and checked for syntax and loading. It has not been run on the robot yet.

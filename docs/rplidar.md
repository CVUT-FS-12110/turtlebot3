# RPLiDAR A1M8

The robot's LiDAR was changed from the LDS-01 to a Slamtec RPLiDAR A1M8 (12 m range, about 7 scans per second in the mode `rplidar_ros` picks, 8000 readings per second, USB adapter with a CP2102 chip, 115200 baud). The driver is the ROS 2 package `rplidar_ros` (`ros-jazzy-rplidar-ros`), which publishes `/scan` with the frame `base_scan`, so nothing on the PC changes.

> **Partly tested.** On the robot the bring-up starts the driver, and the PC receives `/scan` at about 7.1 Hz and sees all the other topics (`scripts/check.sh`). `scan_stats.py` showed 319 valid rays of 360 per scan (313 to 328) and distances from 0.26 to 7.68 m. In RViz the points sit in the right direction, so the mounting is correct. Not checked yet: a map. Fix this page as soon as something differs on the real hardware.

TurtleBot3's own `robot.launch.py` does not know this model: for an unknown `LDS_MODEL` it silently starts the LDS-01 driver on the same port. That is why the bring-up of this repository must be used; with `LDS_MODEL=RPLIDAR-A1` it starts `rplidar_node` instead ([`robot/launch/lidar_rplidar/hlds_laser.launch.py`](../robot/launch/lidar_rplidar/hlds_laser.launch.py), selected in [`robot/launch/robot_common.py`](../robot/launch/robot_common.py)).

## New robot (installer)

`scripts/install.sh` offers `RPLIDAR-A1` as the LiDAR model (the default for role `robot`), installs `ros-jazzy-rplidar-ros` and writes `export LDS_MODEL=RPLIDAR-A1` to `~/.bashrc`. See [robot-raspberry-pi.md](robot-raspberry-pi.md).

## Robot that is already installed

You do not need the whole installer again. On the **ROBOT**:

```bash
git -C ~/turtlebot3-setup pull
~/turtlebot3-setup/scripts/set-lidar.sh RPLIDAR-A1
```

It installs the package if it is missing and sets `LDS_MODEL` in the installer's block of `~/.bashrc`. Nothing is built. Open a new terminal (or `source ~/.bashrc`), then check the variable and the port:

```bash
echo $LDS_MODEL        # RPLIDAR-A1
ls /dev/ttyUSB*        # /dev/ttyUSB0
```

Running `scripts/install.sh` again gives the same result, but it asks every question again and repeats the clock and apt steps; `set-lidar.sh` is the short way. Going back: `set-lidar.sh LDS-01`. The installer does not install the packages of the other LiDARs on the fly, and `set-lidar.sh` only knows these two.

## Bring-up

```bash
ros2 launch ~/turtlebot3-setup/robot/launch/bringup.launch.py
```

`bringup_ekf.launch.py` does the same with the EKF. Do not use `ros2 launch turtlebot3_bringup robot.launch.py` directly with this LiDAR.

Check on the robot and on the PC:

```bash
ros2 topic hz /scan                    # about 7.1 Hz measured on the PC over Wi-Fi, steady (std dev 5 ms)
python3 ~/turtlebot3-setup/scripts/scan_stats.py
```

`rplidar_node` logs the firmware, the health status and the scan mode at the start. The sensor spins up when the node starts and stops when it ends.

## Things to check on the hardware

- **Mounting:** the sensor's zero angle points along the arrow on its body, and the scan turns counter-clockwise like every ROS scan. Mount it so that the arrow points to the front of the robot, as the TurtleBot3 model expects (frame `base_scan`). If the map is turned or mirrored, the sensor sits rotated or the wrong way round.
- **Power:** the motor and the laser draw more than the LDS-01 did. Use the USB adapter board that came with the sensor in a USB port of the Pi, and check `vcgencmd get_throttled` (`0x0` is fine). Undervoltage shows up as a motor that does not spin up or as a Pi that reboots, see [troubleshooting](troubleshooting.md).
- **Port:** the adapter appears as `/dev/ttyUSB0` (the OpenCR is `/dev/ttyACM0`). `robot.launch.py` fixes the port; with more USB serial devices the names can swap.
- **Range:** the A1M8 reads up to 12 m. [`auto_mapper/config/slam_toolbox.yaml`](../auto_mapper/config/slam_toolbox.yaml) still limits SLAM to 3 m because of the LDS-01. Raise `max_laser_range` (for example to 8) once the scan looks clean.
- **Minimum distance:** nearer than about 0.15 m the sensor reports nothing; that is normal.

## The robust LDS-01 driver

[`lidar-driver.md`](lidar-driver.md) is only for the LDS-01 and is not used with the RPLiDAR. It stays in the repository in case the old sensor comes back.

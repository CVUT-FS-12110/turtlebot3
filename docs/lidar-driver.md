# Robust LDS-01 driver

> **Only for the LDS-01.** The robot now has an RPLiDAR A1M8 ([rplidar.md](rplidar.md)) and this driver is not used with it. It stays in the repository in case the old sensor comes back.

On some robots the serial link of the LDS-01 loses or corrupts about a third of the bytes (measured with [`scripts/lds01_check.py`](../scripts/lds01_check.py): only 34 to 40 of the 60 packets of a revolution arrive, 30 % of the bytes are unusable, on a PC and on the Pi alike). The stock `hlds_laser_publisher` cuts a revolution out of the stream at fixed 42-byte positions, so one lost byte spoils the rest of the revolution. The result is `/scan` at 2.5 Hz instead of 5 Hz with only a few valid readings, and a thin map.

[`robot/lds01_driver.py`](../robot/lds01_driver.py) is a drop-in replacement. It recognises every packet on its own (header, index, plausible speed) and places its six readings by the packet index, so what arrives is kept and only the lost angles stay empty (`0.0`). The protocol is in [`robot/lds01_protocol.py`](../robot/lds01_protocol.py), shared with the check script.

Against a simulated sensor that loses 15 % of the packets and 15 % of the bytes (about what was measured), the same bytes give:

| | scans per second | valid readings per scan |
|---|---|---|
| stock reading from fixed positions | 2.6 | 21 |
| robust driver | 4.0 to 4.5 | about 250 |

It does not repair the link: the gaps in the circle remain and a better cable or adapter is still the real cure. The simulation shows what the driver does with such a stream. On the robot it raised `/scan` from 2.5 to 5.0 scans per second and the valid rays per scan from 3 to 27 to about 190 (169 to 209), and the map has clearly more points.

## ROBOT (Raspberry Pi)

The driver needs pyserial (the installer adds it for new robot setups):

```bash
sudo apt install python3-serial
git -C ~/turtlebot3-setup pull
```

Start the bring-up as before; with the LDS-01 the robust driver is the default:

```bash
export TURTLEBOT3_MODEL=burger
ros2 launch ~/turtlebot3-setup/robot/launch/bringup.launch.py
```

`bringup_ekf.launch.py` does the same. The launch files point `robot.launch.py` at [`robot/launch/lidar/hlds_laser.launch.py`](../robot/launch/lidar/hlds_laser.launch.py) instead of the stock LiDAR launch file. To go back to the stock driver:

```bash
ros2 launch ~/turtlebot3-setup/robot/launch/bringup.launch.py lidar_driver:=stock
```

Other LiDAR models (`LDS_MODEL` other than `LDS-01`) are not touched.

Every 10 s the driver logs how it is doing, for example:

```
[hlds_laser_publisher]: 4.4 scans/s, 41 of 60 packets per scan, 0 revolutions dropped, 19 % of the bytes unusable
```

## PC (WSL2)

Nothing to install; the scan arrives on `/scan` as before. Check the rate and the number of valid readings per scan with [`scripts/scan_stats.py`](../scripts/scan_stats.py):

```bash
ros2 topic hz /scan
python3 ~/turtlebot3-setup/scripts/scan_stats.py
```

Expect 4 to 5 scans per second and well over 100 valid rays per scan in a room with matte walls, instead of 2.5 per second and 3 to 27 rays. Fabric, glass and glossy lacquer return no light and stay empty whatever the driver does ([troubleshooting.md](troubleshooting.md#the-lidar-gives-few-valid-points-or-only-25-scans-per-second)).

## Settings

| Parameter | Default | Meaning |
|---|---|---|
| `port` | `/dev/ttyUSB0` (from `robot.launch.py`) | serial port of the LiDAR |
| `min_packets` | 20 | a revolution with fewer packets is dropped instead of published |
| `frame_id` | `base_scan` (from `robot.launch.py`) | frame of the scan |

The launch files use the defaults. To change a parameter, start the node by hand (with the bring-up stopped):

```bash
python3 ~/turtlebot3-setup/robot/lds01_driver.py --ros-args -p port:=/dev/ttyUSB0 -p min_packets:=30
```

## Tests

The protocol and the scan assembly are plain Python and run anywhere:

```bash
python3 -m unittest discover -s ~/turtlebot3-setup/robot/test
```

The battery test in the same folder needs ROS 2 (`rclpy`), so run all of them on a machine with ROS. Besides the unit tests the driver was run against a fake sensor on a pseudo-terminal in WSL; the check that every reading lands at its angle (9816 readings, none misplaced) is part of that run.

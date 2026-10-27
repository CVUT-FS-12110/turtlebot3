# OpenCR 1.0 – firmware overview

OpenCR is open source (software Apache-2.0, hardware designs published too). This page links the sources and summarizes what the current TurtleBot3 ROS 2 firmware does. It is based on reading the repositories on 2026-10-27, not on running the firmware on the robot.

## Links

| What | Where |
|---|---|
| Firmware, bootloader, Arduino core, libraries | [ROBOTIS-GIT/OpenCR](https://github.com/ROBOTIS-GIT/OpenCR) |
| TurtleBot3 ROS 2 firmware source | [`arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2`](https://github.com/ROBOTIS-GIT/OpenCR/tree/master/arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2) (examples: `turtlebot3_burger`, `turtlebot3_waffle`, `turtlebot3_manipulation`) |
| Prebuilt binaries (used by `scripts/install.sh`) | [OpenCR-Binaries / turtlebot3 / ROS2 / latest](https://github.com/ROBOTIS-GIT/OpenCR-Binaries/tree/master/turtlebot3/ROS2/latest) |
| Hardware (schematics, PCB, BOM) | [ROBOTIS-GIT/OpenCR-Hardware](https://github.com/ROBOTIS-GIT/OpenCR-Hardware) |
| Board documentation | [OpenCR 1.0 e-Manual](https://emanual.robotis.com/docs/en/parts/controller/opencr10/) |
| Flashing guide | [TurtleBot3 OpenCR setup](https://emanual.robotis.com/docs/en/platform/turtlebot3/opencr_setup/) |

## Version status

- The repository is in maintenance mode. The last commit on `master` is release **1.5.3** (August 2023, a CS-10 color sensor library update).
- The newest TurtleBot3 ROS 2 binary is from **January 2023** (commit "release ROS2 OpenCR f/w 0.2.1"). The `latest` folder is presumably 0.2.1; the version is not stated on the e-Manual page.
- There is no Jazzy-specific firmware. The e-Manual uses the same `ROS2/latest` binary for Humble and Jazzy, because the firmware only speaks the DYNAMIXEL protocol 2.0 over USB and the ROS 2 side is handled by `turtlebot3_node` on the Raspberry Pi.
- Releases 1.5.0–1.5.2 fixed the ROS 2 link to the Raspberry Pi (needs DYNAMIXEL2Arduino 0.6.0) and added Foxy/Humble support for the manipulation variant.

## Architecture

The firmware is not a ROS node (no micro-ROS). The OpenCR acts as a **DYNAMIXEL slave over USB CDC** (`/dev/ttyACM0`) with a control table of about 260 bytes. `turtlebot3_node` on the Raspberry Pi reads and writes this table, and publishes the ROS 2 topics itself.

On the OpenCR side, the firmware:

- drives the two wheel motors (DYNAMIXEL protocol 2.0, 1 Mbps on `Serial3`, IDs 1 and 2) from the commanded linear and angular velocity
- reads the IMU and the wheel encoders and updates the table periodically
- measures the battery voltage and percentage
- reports the ROS 2 connection state through LEDs and a heartbeat (`HEARTBEAT_TIMEOUT_MS = 500` in the source)

## Features (control table)

| Area | Content |
|---|---|
| Drive | Left/right motor torque on/off, `cmd_vel` (linear X, angular Z), acceleration profile; present current, velocity and position per wheel; motor connection check by ping |
| IMU | Gyro (3 axes), accelerometer (3 axes), magnetometer fields, orientation quaternion; gyro recalibration on request |
| Power | Battery voltage and percent |
| Inputs | 2 push buttons, 2 bumper inputs (Waffle), illumination sensor, IR and SORNA analog inputs |
| Outputs | 4 user LEDs, a buzzer (sound), 4 GPIO status LEDs showing the motion direction |
| Other | HC-SR04 style sonar on GPIO 1/2, RC-100 remote control (summed with `cmd_vel`), motor test with the on-board buttons, voltage diagnostics |
| Manipulator | Control table entries for 4 joints and the gripper (OpenManipulator-X), used by the `turtlebot3_manipulation` variant |

For the **Burger** with a LDS-01 the relevant parts are the drive, IMU and battery items. The LiDAR is connected to the Raspberry Pi, not to the OpenCR. The bumpers, sonar and manipulator entries stay unused.

## Limitations

- Fixed wheel parameters per model (`Burger`, `Waffle`). Different wheels or a different wheel base need a source edit and a rebuild in the Arduino IDE.
- The OpenCR converts `cmd_vel` to wheel speeds and reports wheel position and velocity. The firmware exposes no pose, so odometry is computed on the Raspberry Pi (not checked in the `turtlebot3_node` source).
- The Arduino IDE board manager does not work on the Raspberry Pi. Compile on the PC, or use the prebuilt binary and `update.sh`.
- The 1.5.x line is old; fixes would have to come from a fork or your own build.

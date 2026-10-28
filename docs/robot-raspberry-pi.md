# Robot setup (Raspberry Pi 3B+ + OpenCR)

> **Not tested on the robot yet.** The steps follow the ROBOTIS e-Manual and the sources of the `jazzy` branches. Fix this page as soon as something differs on the real hardware.

The Pi runs only the bring-up (`turtlebot3_node` for the OpenCR and the LiDAR driver). SLAM, Nav2 and RViz run on the [remote PC](remote-pc-wsl2.md); the 1 GB of RAM would not carry them.

## 1. Prepare the SD card

1. Flash **Ubuntu Server 24.04 (64-bit) for Raspberry Pi** with Raspberry Pi Imager. In the advanced options set the hostname, a user, SSH and the Wi-Fi network.
2. Prefer a **5 GHz** network. The 3B+ supports it, and 2.4 GHz is usually crowded. The network must allow multicast between the PC and the robot (guest and corporate networks often do not).
3. Boot, connect with `ssh <user>@<hostname>.local`, and wait until the first-boot `apt` jobs finish (`cloud-init status --wait`).

Use the server image without a desktop; a desktop eats memory the build and the bring-up need.

## 2. Run the installer

```bash
sudo apt-get install -y git
git clone https://github.com/CVUT-FS-12110/turtlebot3.git ~/turtlebot3-setup
~/turtlebot3-setup/scripts/install.sh --dry-run   # read what it will do first
~/turtlebot3-setup/scripts/install.sh
```

Choose role `robot`. It can create a swap file, disable automatic apt upgrades, install CycloneDDS, disable Wi-Fi power saving, install the udev rules, build the workspace (over an hour on a Pi, keep it on wall power) and flash the OpenCR. Log out and back in afterwards so the `dialout` group applies.

## 3. Flash the OpenCR

The installer does this if you answer yes. Manually:

```bash
sudo dpkg --add-architecture armhf && sudo apt-get update && sudo apt-get install -y libc6:armhf
wget https://github.com/ROBOTIS-GIT/OpenCR-Binaries/raw/master/turtlebot3/ROS2/latest/opencr_update.tar.bz2
tar -xjf opencr_update.tar.bz2 && cd opencr_update
./update.sh /dev/ttyACM0 burger.opencr
```

If the upload fails, enter recovery mode: hold **PUSH SW2**, press **Reset**, release **Reset**, release **SW2** (the STATUS LED blinks), then retry. Details and background: [opencr-firmware.md](opencr-firmware.md).

Test the motors without ROS: with the wheels in the air, hold **SW1** (forward) or **SW2** (rotate) on the OpenCR.

**Gyro calibration:** the firmware calibrates the gyro when it starts. Keep the robot still when you switch it on, otherwise the odometry drifts or the robot slowly turns on its own.

## 4. Bring-up

On the robot:

```bash
ros2 launch turtlebot3_bringup robot.launch.py
```

On the PC (new terminal, same `ROS_DOMAIN_ID`, same `RMW_IMPLEMENTATION`):

```bash
ros2 topic list                                  # /scan /odom /imu /battery_state ...
ros2 run turtlebot3_teleop teleop_keyboard
ros2 launch turtlebot3_cartographer cartographer.launch.py
```

Check everything at once with [`scripts/check.sh`](../scripts/check.sh) (pass the other machine's IP to also test the network):

```bash
~/turtlebot3-setup/scripts/check.sh <pc-ip>
```

## 5. Possible improvements

- **Better odometry:** fuse the IMU and the wheel odometry with `robot_localization` (EKF). The gyro is usually more accurate in turns than the wheels. Not set up here.
- **Battery:** watch the `/battery_state` topic. Stop driving when the voltage drops, a deeply discharged LiPo is damaged.
- **IMU variant:** the OpenCR repository has a branch `add_icm42670p`, so newer boards may carry a different IMU than the MPU9250. If `/imu` stays empty or looks wrong, check the board revision first.
- **Stable device names:** if you add more USB serial devices, `/dev/ttyUSB0` and `/dev/ttyACM0` can swap. Add udev rules with fixed symlinks in that case.

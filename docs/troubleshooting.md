# Troubleshooting

Run [`scripts/check.sh`](../scripts/check.sh) first; it covers most of the items below.

## The PC does not see the robot's topics

1. Same `ROS_DOMAIN_ID` on both machines (`echo $ROS_DOMAIN_ID`).
2. Same `RMW_IMPLEMENTATION` on both (`rmw_cyclonedds_cpp` if you used the installer defaults). Mixed RMWs do not discover each other reliably.
3. The two machines can ping each other: `./scripts/check.sh <other-ip>`.
4. Same subnet and a network that passes multicast. Guest and corporate Wi-Fi often block it.
5. On the WSL2 PC: `networkingMode=mirrored` is set in `.wslconfig` ([guide](remote-pc-wsl2.md#2-configure-networking)) and the Hyper-V firewall rule is applied. With the default NAT mode multicast does not reach WSL.
6. If multicast cannot work at all, configure CycloneDDS with a static peer list through `CYCLONEDDS_URI` on both machines.

## OpenCR

| Symptom | What to do |
|---|---|
| `/dev/ttyACM0` missing | OpenCR power switch off, bad USB cable, or the udev rules are not installed. Check with `ls /dev/ttyACM*` and `dmesg \| tail`. |
| `Permission denied` on the port | The user is not in `dialout`. Log out and back in after the installer. |
| `Failed connection with Devices`, then `RCLError ... context is invalid` | The OpenCR has no ROS 2 firmware (port opens, but the board does not answer). Flash `burger.opencr`, see [robot-raspberry-pi.md](robot-raspberry-pi.md#3-flash-the-opencr). Also check the power switch and battery. |
| Flashing fails | Recovery mode: hold **PUSH SW2**, press **Reset**, release **Reset**, release **SW2**. Make sure `libc6:armhf` is installed. |
| Motors do not move, wheels free | Dynamixel power not enabled, or the battery is empty. Test with **SW1**/**SW2** on the board. |
| Robot turns slowly by itself | The gyro was calibrated while the robot was moving. Restart it and keep it still for the first seconds. |
| `/imu` empty or constant | Check the board revision (see [opencr-firmware.md](opencr-firmware.md)); reflash the firmware. |

## Raspberry Pi

- **Build is killed or the Pi freezes:** out of memory. Make sure the swap file exists (`swapon --show`) and build with one worker and one compiler job: `MAKEFLAGS=-j1 colcon build --symlink-install --parallel-workers 1 --cmake-args -DCMAKE_BUILD_TYPE=Release`. The installer does this itself, creates a 3 GB swap file and lowers the OOM score of `sshd` so a memory shortage does not cut your SSH connection.
- **The Pi freezes during a long build and `journalctl -b -1` shows `blocked for more than 245 seconds` in `mmc_rescan`:** the SD card is too slow for small writes, even if its sequential speed looks fine. Test it and replace it with an A1/A2 card, see [robot-raspberry-pi.md](robot-raspberry-pi.md#10-choose-a-fast-sd-card).
- **`apt` is locked:** automatic upgrades are running. Wait, or disable them (the installer offers it).
- **Topics lag or drop over Wi-Fi:** disable Wi-Fi power saving (`iw dev wlan0 get power_save` should say `off`), move to 5 GHz, and keep the PC on the same access point.
- **`ros2 launch` cannot find the LiDAR:** check `ls /dev/ttyUSB*` and the `LDS_MODEL` variable (`LDS-01` for your robot).

## Remote PC (WSL2)

- **Gazebo crashes or shows a black window:** try `export LIBGL_ALWAYS_SOFTWARE=1`. If that helps, the problem is the GPU driver.
- **Builds are very slow:** the workspace is under `/mnt/c`. Move it into the Linux home directory.

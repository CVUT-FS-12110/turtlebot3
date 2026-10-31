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

## The clocks of the PC and the robot differ

**Symptom:** RViz or SLAM print `Lookup would require extrapolation into the future` or `Message Filter dropping message ... queue is full`, the map is smeared or scans are missing. The PC and the robot stamp their data with their own clocks, and a difference of more than a few hundredths of a second is enough. The WSL2 clock is the usual culprit: it drifts by about 1000 ppm, which is 0.6 s in 10 minutes, and it jumps after Windows sleeps.

**Measure the difference** on the PC with [`scripts/clock_offset.sh`](../scripts/clock_offset.sh). It opens one SSH connection (the password is asked once), asks the robot for its time five times, and prints the offset of every sample and the median:

```bash
~/turtlebot3-setup/scripts/clock_offset.sh
```

The offset is `robot - (PC before + PC after) / 2`; half of the round trip is the error of one sample. Under 0.02 s is fine; a positive value means the robot clock is ahead of the PC. Repeat it after a few minutes and after `wsl --shutdown`: a difference that grows is drift, one that returns after a restart means WSL takes a wrong time from Windows.

**PC (WSL2):** `scripts/install.sh` sets chrony up to follow the Windows host clock (Hyper-V) and NTP. On an existing setup do the same by hand:

```bash
sudo apt install chrony
```
```bash
printf '%s
' 'refclock PHC /dev/ptp_hyperv poll 3 dpoll -2 offset 0' | sudo tee /etc/chrony/conf.d/wsl-hyperv.conf
sudo systemctl enable chrony && sudo systemctl restart chrony
```
Check with `chronyc tracking`: the reference is `PHC0` and `System time` is in milliseconds or less. It needs `systemd=true` under `[boot]` in `/etc/wsl.conf`, and `/dev/ptp_hyperv` must exist (otherwise `wsl --update` in Windows). `chronyc makestep` fails with `500 Failure` here; the clock is corrected by the restart. After Windows sleeps, check `chronyc tracking` before driving.

**ROBOT (Pi):** `timedatectl` must say `System clock synchronized: yes`; if not, `sudo timedatectl set-ntp true` (the Pi has no battery-backed clock and needs a network connection with Internet access after every power-up). The Pi was within 0.03 s of NTP time when measured.

## The LiDAR gives few valid points or only 2.5 scans per second

The LDS-01 cannot be configured (fixed firmware, no gain or power setting), so find out first whether the sensor, the link or the surroundings are at fault. [`scripts/lds01_check.py`](../scripts/lds01_check.py) reads the sensor straight from its serial port, without ROS, and prints per revolution the rotation speed, how many of the 60 packets arrived and how many of the 360 readings are valid:

```
revolution 7: 60/60 packets, 214/360 valid, 300 rpm
```

**ROBOT (Pi):** stop the bring-up first (it holds the port), then:

```bash
sudo apt install python3-serial
python3 ~/turtlebot3-setup/scripts/lds01_check.py /dev/ttyUSB0
```

**PC (Windows):** plug the LiDAR with its USB adapter into the PC. Windows installs the CP2102 driver itself; the COM port is in Device Manager. In PowerShell:

```powershell
py -m pip install pyserial
py scripts\lds01_check.py COM3
```

Reading the result (the summary line at the end gives the means):

| Result | Meaning |
|---|---|
| about 300 rpm, 60 of 60 packets, about 5 revolutions per second | sensor and link are fine; few valid readings then come from the surfaces (fabric, dark or glossy), and a lower rate in ROS comes from the driver or the Pi |
| 300 rpm, but fewer than 60 packets | the link loses data: try another cable, USB port or adapter |
| well below 300 rpm or 0 | the motor does not get enough power or is blocked |
| few valid readings with 60 of 60 packets and a white matte box 0.5 m in front | the sensor or its lens is faulty or dirty |

Run it on both machines in the same place: 5 revolutions per second and 60 of 60 packets on the PC but 2.5 scans per second in `ros2 topic hz /scan` on the Pi points to the Pi side (USB, CPU or driver), not to the LiDAR. Surfaces that return no light: matte fabric, black or glossy lacquer, glass and mirrors; walls and cardboard work.

The last line also counts bytes: a healthy LDS-01 sends about 12600 bytes per second (60 packets of 42 bytes, 5 times a second) and almost none of them are discarded. Clearly fewer bytes mean data lost on the way; many discarded bytes mean corrupted data (cable, adapter, interference). This matters for ROS: the driver cuts a revolution into packets at fixed positions, so a single lost packet spoils the whole revolution and the driver only recovers at the next one. That gives revolutions with a handful of valid points and a scan rate of 2.5 Hz instead of 5 Hz.

The parser is tested on synthetic data. On a real LDS-01 connected to a Windows PC it showed 4.8 revolutions per second and 300 rpm, but only about 40 of the 60 packets per revolution, so a lossy link is not ruled out.

If the link loses data and swapping the cable does not help, use the robust driver that keeps what arrives: [lidar-driver.md](lidar-driver.md).

## Remote PC (WSL2)

- **Gazebo crashes or shows a black window:** try `export LIBGL_ALWAYS_SOFTWARE=1`. If that helps, the problem is the GPU driver.
- **Builds are very slow:** the workspace is under `/mnt/c`. Move it into the Linux home directory.

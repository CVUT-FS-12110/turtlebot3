# Robot setup (Raspberry Pi 3B+ + OpenCR)

> **Not tested on the robot yet.** The steps follow the ROBOTIS e-Manual and the sources of the `jazzy` branches. Fix this page as soon as something differs on the real hardware.

The Pi runs only the bring-up (`turtlebot3_node` for the OpenCR and the LiDAR driver). SLAM, Nav2 and RViz run on the [remote PC](remote-pc-wsl2.md); the 1 GB of RAM would not carry them.

## 1. Prepare the SD card (headless)

The robot runs without a monitor or keyboard. Ubuntu Server has no desktop, so you only need to make sure the Pi joins the Wi-Fi and accepts SSH. The settings are written to the SD card with cloud-init before the first boot.

### 1.1 Write the image

Download `ubuntu-24.04.5-preinstalled-server-arm64+raspi.img.xz` from [cdimage.ubuntu.com](https://cdimage.ubuntu.com/ubuntu/releases/noble/release/) (use the newest 24.04.x there, not the 26.x releases; ROS 2 Jazzy needs 24.04) and write it with Raspberry Pi Imager via **Choose OS → Use custom**.

The online catalogue also lists it under **Other general-purpose OS → Ubuntu → Ubuntu Server 24.04.x LTS (64-bit)**, but with the device set to *Raspberry Pi 3* the entry may be hidden. The device choice is only a list filter: pick *Raspberry Pi 4* or *No filtering* to see it (it is the same 64-bit image for the 3B+).

If the Imager offers OS customisation, you can set the hostname, user, SSH and Wi-Fi there and skip 1.2. If it does not, continue with 1.2.

### 1.2 Configure Wi-Fi, user and SSH

After writing the image, the card shows up in Windows as the **`system-boot`** partition. Edit two files on it before ejecting the card. The examples use the user `turtle` and the hostname `turtlebot`; change them if you like.

`network-config` (replace the whole content; use the 2.4 GHz SSID if the Pi does not see a 5 GHz one):

```yaml
network:
  version: 2
  wifis:
    wlan0:
      dhcp4: true
      optional: true
      regulatory-domain: CZ
      access-points:
        "<ssid>":
          password: "<wifi-password>"
```

`user-data` (replace the whole content; must start with `#cloud-config`):

```yaml
#cloud-config
hostname: turtlebot
manage_etc_hosts: true
ssh_pwauth: true
package_update: true
packages:
  - openssh-server
users:
  - name: turtle
    groups: [sudo, dialout]
    shell: /bin/bash
    sudo: ['ALL=(ALL) NOPASSWD:ALL']
    lock_passwd: false
    plain_text_passwd: "<password>"
runcmd:
  - systemctl enable --now ssh
```

`plain_text_passwd` takes the password as plain text (not a hash; the `passwd` key would need a hash and a plain password there makes login impossible). The password stays readable on the SD card, so use a throwaway one and change it after the first login with `passwd`. For a hash instead, run `openssl passwd -6` and use the output with the `passwd` key.

`ssh_pwauth` only allows password login; it does not start the SSH server. On the tested image the SSH server was **not running after the first boot** (`Connection refused` on port 22 although the Pi answered ping), so `packages` and `runcmd` make sure it is installed and running. This needs a working Wi-Fi at the first boot. If you already booted without it, enable it later from a console (HDMI + keyboard): `sudo systemctl enable --now ssh`, or re-run cloud-init with `sudo cloud-init clean --logs --reboot` (cloud-init reads `user-data` only once per card). Save the files with LF line endings and no tabs.

For key-based login add `ssh_authorized_keys: [<your public key>]` to the user and set `ssh_pwauth: false`.

If you skip this and boot the stock image, the default login is `ubuntu` / `ubuntu` (you must change the password at the first login) on a monitor and keyboard or the Ethernet cable; do not expect SSH to work until you enable it as above.

### 1.3 First boot

1. Insert the card, power the Pi and wait a few minutes. The first boot is slow because cloud-init applies the settings.
2. Connect from the PC:

   ```bash
   ssh turtle@turtlebot.local
   ```

   If `.local` does not resolve, find the IP address in the router's client list.
3. Wait for the first-boot jobs to finish before running `apt`: `cloud-init status --wait`.

If the Pi does not appear on Wi-Fi, connect it with an Ethernet cable for the first boot, log in, and check `/var/log/cloud-init.log` and `sudo netplan apply`. Wi-Fi can also be set later by putting a file like the `network-config` above into `/etc/netplan/` (mode `600`, with `renderer: networkd`).

Not tested on the robot yet. The Wi-Fi should be a **5 GHz** network if possible (the 3B+ supports it, 2.4 GHz is usually crowded), and it must allow multicast between the PC and the robot (guest and corporate networks often do not).

## 2. Run the installer

```bash
sudo apt-get install -y git
git clone https://github.com/CVUT-FS-12110/turtlebot3.git ~/turtlebot3-setup
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

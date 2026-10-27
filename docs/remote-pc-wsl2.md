# Remote PC setup (Windows 11 + WSL2)

Ubuntu 24.04 runs inside WSL2, so no dual boot is needed. GUI apps (RViz, Gazebo) open as normal Windows windows via WSLg.

## 1. Install WSL2 and Ubuntu

In PowerShell **as Administrator**:

```powershell
wsl --install -d Ubuntu-24.04
```

Finish the first-run setup: create a Linux user (lowercase, no diacritics) and a password.

> If WSL prints `Waiting for OOBE command to complete`, the user creation is still pending. Open Ubuntu interactively (`wsl -d Ubuntu-24.04`) and finish it. If it hangs, run `wsl --shutdown` and try again.

## 2. Configure networking

1. Copy [`config/.wslconfig`](../config/.wslconfig) to `C:\Users\<user>\.wslconfig`.
2. Restart WSL and start the distribution once:

   ```powershell
   wsl --shutdown
   wsl -d Ubuntu-24.04 -e true
   ```

3. Allow inbound traffic to WSL (PowerShell **as Administrator**):

   ```powershell
   Set-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -DefaultInboundAction Allow
   ```

   > This fails with `No MSFT_NetFirewallHyperVVMSetting objects found` if no distribution has been installed and started yet. Do steps 1–2 first.

4. Check inside Ubuntu that WSL has the same IP as Windows and that rendering uses the GPU (`D3D12`, not `llvmpipe`):

   ```bash
   ip -4 addr show
   sudo apt update && sudo apt install -y mesa-utils
   glxinfo -B | grep -i renderer
   ```

## 3. Install ROS 2 Jazzy

> Steps 3–5 can be done automatically with [`scripts/install.sh`](../scripts/install.sh) (role `pc`). The manual steps are below.

```bash
sudo apt install -y software-properties-common curl
sudo add-apt-repository -y universe
export ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F "tag_name" | awk -F\" '{print $4}')
curl -L -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo $VERSION_CODENAME)_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb
sudo apt update && sudo apt upgrade -y
sudo apt install -y ros-jazzy-desktop ros-dev-tools
```

Gazebo Harmonic, SLAM and navigation:

```bash
sudo apt install -y ros-jazzy-ros-gz \
  ros-jazzy-cartographer ros-jazzy-cartographer-ros \
  ros-jazzy-navigation2 ros-jazzy-nav2-bringup
```

## 4. Build the TurtleBot3 packages

Keep the workspace in the Linux home directory, not under `/mnt/c` (much slower builds).

```bash
source /opt/ros/jazzy/setup.bash
mkdir -p ~/turtlebot3_ws/src && cd ~/turtlebot3_ws/src
git clone -b jazzy https://github.com/ROBOTIS-GIT/DynamixelSDK.git
git clone -b jazzy https://github.com/ROBOTIS-GIT/turtlebot3_msgs.git
git clone -b jazzy https://github.com/ROBOTIS-GIT/turtlebot3.git
git clone -b jazzy https://github.com/ROBOTIS-GIT/turtlebot3_simulations.git
cd ~/turtlebot3_ws
sudo rosdep init 2>/dev/null; rosdep update
rosdep install --from-paths src --ignore-src -y --rosdistro jazzy
colcon build --symlink-install
```

## 5. Environment

```bash
sudo apt install -y ros-jazzy-rmw-cyclonedds-cpp
cat >> ~/.bashrc << 'EOF'
source /opt/ros/jazzy/setup.bash
source ~/turtlebot3_ws/install/setup.bash
export ROS_DOMAIN_ID=30
export TURTLEBOT3_MODEL=burger
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
EOF
source ~/.bashrc
```

The robot must use the same `ROS_DOMAIN_ID` and `RMW_IMPLEMENTATION`.

## 6. Test in simulation

Run each command in its own terminal. In Windows Terminal, `Alt+Shift+D` splits the window into a new pane; setting **Ubuntu-24.04** as the default profile makes `Ctrl+Shift+T` open Ubuntu tabs.

```bash
# 1. Robot in the Gazebo world
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py

# 2. Keyboard teleop (w/a/s/d/x)
ros2 run turtlebot3_teleop teleop_keyboard

# 3. SLAM
ros2 launch turtlebot3_cartographer cartographer.launch.py use_sim_time:=True

# 4. Save the map
ros2 run nav2_map_server map_saver_cli -f ~/map

# 5. Navigation (stop teleop and SLAM first)
ros2 launch turtlebot3_navigation2 navigation2.launch.py use_sim_time:=True map:=$HOME/map.yaml
```

## Troubleshooting

- **Gazebo crashes or shows a black window:** try `export LIBGL_ALWAYS_SOFTWARE=1`. If that helps, the problem is the GPU driver.
- **PC does not see the robot's topics:** see [troubleshooting.md](troubleshooting.md#the-pc-does-not-see-the-robots-topics) (domain ID, RMW, multicast).

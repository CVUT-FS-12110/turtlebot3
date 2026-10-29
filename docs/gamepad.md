# Gamepad teleop (Evolveo Fighter F1)

Drive the robot with an Evolveo Fighter F1 gamepad and its 2.4 GHz USB receiver, plugged into the Raspberry Pi. The vendor manual is in [manuals/evolveo-fighter-f1-navod.pdf](manuals/evolveo-fighter-f1-navod.pdf) (Czech/Slovak/Polish/Hungarian/English).

## LEDs (from the manual)

| Situation | Indication |
|---|---|
| Power on / off | hold **HOME** 2 s / 5 s |
| Low battery | **LED4** flashes |
| Charging (USB-C connected) | **LED4** flashes |
| Fully charged | **LED4** on |
| Paired in X-input mode | **LED1 + LED2** on |

The pad sleeps 1 minute after losing the link and 5 minutes without activity. Press **HOME** for 2 s to wake it. If it freezes, press the **RESET** button on the underside and pair again. Charge it from a wall adapter or PC, not from the Pi, which has little power to spare.

## Pair in X-input mode

1. Plug the 2.4 GHz receiver into the Pi.
2. Hold **X + HOME** for 2 s. LED1 and LED2 flash, then stay on once paired.
3. Check that the Pi sees an Xbox 360 pad:

```bash
lsusb | grep -i 045e          # 045e:028e  Microsoft Xbox 360 pad
ls /dev/input/js*             # /dev/input/js0
```

Other modes in the manual: **A + HOME** (Android box, LED1) and **TURBO + HOME** (PlayStation 3, LED1-3). In these the receiver may show up as another device, for example `0079:181c` (DragonRise Gamepad), and the button numbering below does not apply. If the receiver shows `0079:181c`, repeat the X + HOME step.

## Find the button and axis mapping

```bash
sudo apt install joystick
jstest /dev/input/js0
```

`jstest` prints one live line. Move one control at a time and note which `Axes` value changes or which `Buttons` entry turns `on`. In ROS the numbers are the same, so you can also check what `joy_node` publishes:

```bash
ros2 run joy joy_node
ros2 topic echo /joy          # axes[] and buttons[] by index
```

### Measured on the robot

The first `jstest` run was made while the receiver showed `0079:181c` (`hid-generic`, DragonRise "Gamepad"), **not** `045e:028e` (X-input). The pad reported 8 axes (X, Y, Z, Rz, Gas, Brake, Hat0X, Hat0Y) and 15 buttons. That is the generic D-input layout, so the Xbox 360 numbering does not apply to it. In X-input mode (LED1 + LED2) the numbering is different, so repeat the measurement after pairing with X + HOME.

| Axis | `jstest` name | Rest | Seen | Probable control |
|---|---|---|---|---|
| 0 | X | 0 | ±32767 | left stick left/right: left = -32767, right = +32767 |
| 1 | Y | 0 | ±32767 | left stick up/down: up = -32767, down = +32767 |
| 2 | Z | 0 | ±32767 | right stick left/right (not named when measured) |
| 3 | Rz | 0 | ±32767 | right stick up/down (not named when measured) |
| 4 | Gas | -32767 | -32767 to +32767 | R2 trigger (moves together with button 9) |
| 5 | Brake | -32767 | -32767 to +32767 | L2 trigger (moves together with button 8) |
| 6 | Hat0X | 0 | -32767 / +32767 | D-pad left/right |
| 7 | Hat0Y | 0 | -32767 / +32767 | D-pad up/down |

Buttons, pressed one by one in the order L1, R1, A, B, X, Y:

| Index | `jstest` name | Control on the pad |
|---|---|---|
| 0 | BtnA | A |
| 1 | BtnB | B |
| 3 | BtnX | X |
| 4 | BtnY | Y |
| 6 | BtnTL | L1 (Xbox LB) |
| 7 | BtnTR | R1 (Xbox RB) |
| 8 | BtnTL2 | L2 (also moves axis 5) |
| 9 | BtnTR2 | R2 (also moves axis 4) |

Not yet pressed: Select, Start, Mode and the stick clicks (10 to 14). Indices 2 (BtnC) and 5 (BtnZ) were never seen and are probably unused. Do not assume the Xbox values (LB = 4, RB = 5): index 4 here is Y.

The left stick was measured on its own (axes 0 and 1), so the drive settings below are based on measured values. These are raw `jstest` signs: up is negative. `joy_node` normally flips them so that up and left are positive in `/joy`, but check this with `ros2 topic echo /joy` before driving.

Use L1 (button 6) as `enable_button`.

## Drive the robot

Start the bring-up first (`ros2 launch turtlebot3_bringup robot.launch.py`), then:

```bash
sudo apt install ros-jazzy-joy ros-jazzy-teleop-twist-joy
ros2 run joy joy_node
ros2 run teleop_twist_joy teleop_node --ros-args \
  -p enable_button:=6 \
  -p axis_linear.x:=1 -p axis_angular.yaw:=0 \
  -p scale_linear.x:=0.2 -p scale_angular.yaw:=1.0
```

- `enable_button:=6` assumes L1 (LB) is index 6 (see the measured table). Confirm it first. The indices in `/joy` can differ from `jstest`, so check with `ros2 topic echo /joy`.
- The robot moves only while you hold `enable_button`. Release it to stop.
- Test with the wheels lifted and watch `ros2 topic echo /cmd_vel` to see whether stick up gives a positive `linear.x` before driving on the floor.
- Burger limits are about 0.22 m/s and 2.84 rad/s, so start slow.
- Set `axis_linear.x`, `axis_angular.yaw` and `enable_button` from your mapping table.
- If `ros2 topic info /cmd_vel` shows `geometry_msgs/msg/TwistStamped`, add `-p publish_stamped_twist:=true`.

## Problems

- **No `js0`:** run `sudo modprobe joydev`, then re-pair the pad.
- **Receiver or lidar drops out, `Undervoltage detected!`:** check `vcgencmd get_throttled` (`0x0` is fine). Without the battery the Pi relies entirely on the OpenCR adapter. See [troubleshooting](troubleshooting.md).

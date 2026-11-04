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

The gamepad runs on the **ROBOT** (the receiver is in the Pi) and publishes `/cmd_vel`, the same topic as the keyboard teleop on the PC. [`robot/launch/gamepad.launch.py`](../robot/launch/gamepad.launch.py) starts `joy_node` and `teleop_twist_joy` with the left stick (axis 1 forward/back, axis 0 turn) and an enable button. The easiest way is to start it together with the bring-up:

```bash
sudo apt install ros-jazzy-joy ros-jazzy-teleop-twist-joy joystick
```
```bash
ros2 launch ~/turtlebot3-setup/robot/launch/bringup.launch.py gamepad:=true
```

(The installer installs the packages on new robots.) `bringup_ekf.launch.py` takes `gamepad:=true` too. To start only the gamepad next to a bring-up that already runs, use `ros2 launch ~/turtlebot3-setup/robot/launch/gamepad.launch.py`.

Arguments (add them to the same command, for example `gamepad:=true enable_button:=4`):

| Argument | Default | Meaning |
|---|---|---|
| `enable_button` | `6` | button held to drive: `6` = L1 in D-input mode (measured, and confirmed driving the robot); `4` = LB in X-input mode (Xbox 360 numbering, not measured on this pad) |
| `scale_linear` | `0.15` | forward speed in m/s at full stick (Burger maximum is about 0.22) |
| `scale_angular` | `1.0` | turning speed in rad/s at full stick (Burger maximum is about 2.84) |
| `stamped` | `true` | `/cmd_vel` as `TwistStamped`, which `turtlebot3_node` expects on the robot; `false` for plain `Twist` |

- The robot moves only while you hold the enable button. Release it to stop.
- **Check once with the wheels in the air** before driving on the floor. Hold the enable button, push the stick up and watch `ros2 topic echo /cmd_vel`: `linear.x` must be positive, and stick left must give a positive `angular.z` (the robot turns left).
- **`/cmd_vel` type:** on the robot `turtlebot3_node` subscribes to `TwistStamped` (checked with `ros2 topic info /cmd_vel -v`), so the default is `stamped:=true`. With the wrong type the robot ignores the commands, and `ros2 topic echo /cmd_vel` fails with "contains more than one type". If you ever see that, publisher and subscriber disagree: set `stamped` to the type shown on the `SUBSCRIPTION` line.
- **Tested on the robot:** with the pad in D-input mode, `bringup.launch.py gamepad:=true` (all defaults) drives the robot while the enable button is held.
- **No reaction:** `ros2 topic echo /joy` shows whether the pad arrives (`buttons[]` changes when you press L1). If the index of L1 differs from `enable_button`, use the one you see.

## Manual mapping with the gamepad

Mapping does not change: it runs on the PC and listens to `/cmd_vel`, whoever publishes it. Start the robot with `gamepad:=true`, then on the **PC**:

```bash
~/turtlebot3-setup/scripts/mapping.sh
```

Drive with the gamepad (hold the enable button) and watch the map grow in RViz. The keyboard teleop pane of `mapping.sh` stays available; it publishes only when you press a key, so the two do not fight, but use one at a time. Drive slowly (the default 0.15 m/s) so SLAM can match the scans; turns are the hard part, so make them gently.

## Problems

- **`ros2 topic echo /joy` stays silent although `/dev/input/js0` exists and `jstest` works:** your user is not in the `input` group. `jstest` reads `js0` (readable by everybody), but `joy_node` uses SDL, which reads `/dev/input/event*` (`root:input`, mode 660). Check with `groups`, then:

  ```bash
  sudo usermod -aG input $USER
  ```

  Log out and back in (or reboot); the installer does this on new robots, and `scripts/check.sh` warns about it.
- **No `js0`:** run `sudo modprobe joydev`, then re-pair the pad.
- **Receiver or lidar drops out, `Undervoltage detected!`:** check `vcgencmd get_throttled` (`0x0` is fine). Without the battery the Pi relies entirely on the OpenCR adapter. See [troubleshooting](troubleshooting.md).

# 采集 CSV 字段说明 · Data dictionary

采集文件存于 sim 主机 `F:\Evtol_TAKEOVER\`，命名 `被试_诱因_模态_时间.csv`，编码 UTF‑8‑SIG（Excel 可直接打开）。
每帧一行（约 18–20 行/秒，随 `CONTROL_HZ`），列顺序 = **6 个采集上下文列**（在最前）+ **76 个 DevKit 字段**（按字母序，与 `/get` 一致）。

The recording CSV lives at `F:\Evtol_TAKEOVER\` on the sim host, named `subject_cause_modality_time.csv`, UTF‑8‑SIG. One row per frame (~18–20 rows/s). Columns = **6 context columns** first, then **76 DevKit fields** (alphabetical, matching `/get`).

> 本机型特有映射 / airframe‑specific mapping：`GENERAL_ENG_THROTTLE_LEVER_POSITION:1` = 前后(fore/aft)，`ELEVATOR_POSITION` = 升降(vertical)，`VELOCITY_BODY_X` 飞行中写入不生效。见 [DESIGN](DESIGN.zh-CN.md)。

---

## A. 采集上下文列 (context columns, CSV 最前 6 列)

| 列 Column | 单位 Unit | 说明 · Description |
|---|---|---|
| `ts_unix` | 秒 s (epoch) | 每帧的 Unix 时间戳(浮点, 毫秒精度)——**首选时间轴**。Per‑frame Unix epoch seconds (ms precision) — primary time axis |
| `ts_local` | 本地时间 | 可读本地时钟 `YYYY-MM-DD HH:MM:SS.mmm`。Human‑readable local wall‑clock |
| `rel_t0_s` | 秒 s | 相对"预警时刻 t0"(=RT 计时起点)的秒数；预警前为空。Seconds since the takeover **alert**(t0); blank before the alert |
| `phase` | — | 试次阶段：`idle`/`waiting`/`alerted`/`triggered`/`takeover`。Trial phase |
| `cause` | — | 当前诱因：`wind_shear`/`ap_fail`/`obstacle`/`blank`/空。Armed cause |
| `modality` | — | HMI 模态：`visual`/`audio`/`multimodal`。HMI modality |

## B. DevKit 字段 (76, 按 CSV/字母序)

| 字段 Field | 单位 Unit | 说明 · Description |
|---|---|---|
| `ABSOLUTE_TIME` | 秒 s | SimConnect 绝对时间(自公元 1 年起)。SimConnect absolute time |
| `ACCELERATION_BODY_X` | ft/s² | 机体横向加速度(右+)。Body lateral acceleration |
| `ACCELERATION_BODY_Y` | ft/s² | 机体垂向加速度(上+)。Body vertical acceleration |
| `ACCELERATION_BODY_Z` | ft/s² | 机体纵向加速度(前+)。Body longitudinal acceleration |
| `AILERON_POSITION` | 位置 ≈−1…1 | 副翼输入位置(滚转杆)。Aileron input position |
| `AILERON_TRIM_PCT` | %/100 | 副翼配平。Aileron trim |
| `AIRSPEED_INDICATED` | 节 kt | 指示空速。Indicated airspeed |
| `AIRSPEED_MACH` | 马赫 | 马赫数。Mach |
| `AIRSPEED_TRUE` | 节 kt | 真空速。True airspeed |
| `AMBIENT_WIND_DIRECTION` | 度 ° | 环境风向。Ambient wind direction |
| `AMBIENT_WIND_VELOCITY` | 节 kt | 环境风速。Ambient wind velocity |
| `ATTITUDE_INDICATOR_BANK_DEGREES` | 度 ° | 姿态仪滚转指示。Attitude indicator bank |
| `ATTITUDE_INDICATOR_PITCH_DEGREES` | 度 ° | 姿态仪俯仰指示。Attitude indicator pitch |
| `BRAKE_LEFT_POSITION` | 位置 0…1 | 左刹车。Left brake |
| `BRAKE_PARKING_POSITION` | 0/1 | 驻车刹车。Parking brake |
| `BRAKE_RIGHT_POSITION` | 位置 0…1 | 右刹车。Right brake |
| `ELEVATOR_POSITION` | 位置 ≈−1…1 | 升降舵输入 —— **本机型=控制升降(垂直)**。Elevator input — **vertical on this airframe** |
| `ELEVATOR_TRIM_POSITION` | 弧度 rad | 升降舵配平偏度。Elevator trim deflection |
| `FLAPS_HANDLE_INDEX` | 数值 | 襟翼手柄档位。Flaps handle index |
| `GEAR_HANDLE_POSITION` | 0/1 | 起落架手柄。Gear handle |
| `GENERAL_ENG_THROTTLE_LEVER_POSITION:1` | % 0–100 | 油门杆 1 —— **本机型=控制前后**(悬停中性≈46)。Throttle lever 1 — **fore/aft on this airframe** |
| `GENERAL_ENG_THROTTLE_LEVER_POSITION:2` | % | 油门杆 2(本机型无效, 常为空)。Throttle lever 2 (inactive here) |
| `GENERAL_ENG_THROTTLE_LEVER_POSITION:3` | % | 油门杆 3(同上)。Throttle lever 3 |
| `GENERAL_ENG_THROTTLE_LEVER_POSITION:4` | % | 油门杆 4(同上)。Throttle lever 4 |
| `GPS_GROUND_SPEED` | 节 kt | GPS 地速。GPS ground speed |
| `GROUND_ALTITUDE` | 英尺 ft | 机下地面标高(MSL)。Terrain elevation below aircraft |
| `GROUND_VELOCITY` | 节 kt | 地速。Ground speed |
| `G_FORCE` | G | 过载。G load |
| `HEADING_INDICATOR` | 度 ° | 航向陀螺指示(会漂)。Gyro heading indicator |
| `HSI_CDI_NEEDLE` | 数值 | HSI 航道偏离指针。HSI course‑deviation needle |
| `LEADING_EDGE_FLAPS_LEFT_PERCENT` | %/100 | 左前缘襟翼。LE flap left |
| `LEADING_EDGE_FLAPS_RIGHT_PERCENT` | %/100 | 右前缘襟翼。LE flap right |
| `LIGHT_BEACON` | 0/1 | 信标灯。Beacon light |
| `LIGHT_CABIN` | 0/1 | 客舱灯。Cabin light |
| `LIGHT_LANDING` | 0/1 | 着陆灯。Landing light |
| `LIGHT_LOGO` | 0/1 | 尾标灯。Logo light |
| `LIGHT_NAV` | 0/1 | 航行灯。Nav light |
| `LIGHT_RECOGNITION` | 0/1 | 识别灯。Recognition light |
| `LIGHT_STROBE` | 0/1 | 频闪灯。Strobe light |
| `LIGHT_TAXI` | 0/1 | 滑行灯。Taxi light |
| `LIGHT_WING` | 0/1 | 翼灯。Wing light |
| `PLANE_ALTITUDE` | 英尺 ft | 海拔高度(MSL)。Altitude MSL |
| `PLANE_ALT_ABOVE_GROUND` | 英尺 ft | 离地高度(AGL)。Altitude above ground |
| `PLANE_BANK_DEGREES` | 度 ° | 滚转角。Bank/roll angle |
| `PLANE_HEADING_DEGREES_GYRO` | 度 ° | 陀螺航向。Gyro heading |
| `PLANE_HEADING_DEGREES_MAGNETIC` | 度 ° | 磁航向。Magnetic heading |
| `PLANE_HEADING_DEGREES_TRUE` | 度 ° | 真航向。True heading |
| `PLANE_IN_PARKING_STATE` | 0/1 | 是否停放状态。In parking state |
| `PLANE_LATITUDE` | 度 ° | 纬度。Latitude |
| `PLANE_LONGITUDE` | 度 ° | 经度。Longitude |
| `PLANE_PITCH_DEGREES` | 度 ° | 俯仰角。Pitch angle |
| `PLANE_TOUCHDOWN_NORMAL_VELOCITY` | ft/min | 触地垂直速度。Touchdown vertical velocity |
| `RECIP_ENG_MANIFOLD_PRESSURE:1` | psi | 1 号发动机进气歧管压力。Engine 1 manifold pressure |
| `RECIP_ENG_MANIFOLD_PRESSURE:2` | psi | 2 号发动机歧管压力。Engine 2 |
| `RECIP_ENG_MANIFOLD_PRESSURE:3` | psi | 3 号发动机歧管压力。Engine 3 |
| `RECIP_ENG_MANIFOLD_PRESSURE:4` | psi | 4 号发动机歧管压力。Engine 4 |
| `ROTATION_VELOCITY_BODY_X` | rad/s | 机体滚转角速度。Body roll rate |
| `ROTATION_VELOCITY_BODY_Y` | rad/s | 机体偏航角速度。Body yaw rate |
| `ROTATION_VELOCITY_BODY_Z` | rad/s | 机体俯仰角速度。Body pitch rate |
| `RUDDER_POSITION` | 位置 ≈−1…1 | 方向舵输入(脚舵)。Rudder input |
| `RUDDER_TRIM_PCT` | %/100 | 方向舵配平。Rudder trim |
| `SIMULATION_RATE` | 倍 | 仿真倍速。Sim rate multiplier |
| `SIM_ON_GROUND` | 0/1 | 是否在地面。On ground |
| `STALL_WARNING` | 0/1 | 失速警告。Stall warning |
| `TRAILING_EDGE_FLAPS_LEFT_PERCENT` | %/100 | 左后缘襟翼。TE flap left |
| `TRAILING_EDGE_FLAPS_RIGHT_PERCENT` | %/100 | 右后缘襟翼。TE flap right |
| `TURN_COORDINATOR_BALL` | 位置 −128…128 | 转弯仪侧滑球(侧滑/侧偏)。Turn‑coordinator ball (slip/skid) |
| `VELOCITY_BODY_X` | ft/s | 机体横向速度(右+)。Body lateral velocity |
| `VELOCITY_BODY_Y` | ft/s | 机体垂向速度(上+)。Body vertical velocity |
| `VELOCITY_BODY_Z` | ft/s | 机体纵向速度(前+)。Body longitudinal velocity |
| `VERTICAL_SPEED` | ft/min | 垂直速度(升降率)。Vertical speed |
| `WATER_RUDDER_HANDLE_POSITION` | %/100 | 水舵手柄。Water‑rudder handle |
| `WING_FLEX_PCT:1` | %/100 | 机翼挠曲 1。Wing flex 1 |
| `WING_FLEX_PCT:2` | %/100 | 机翼挠曲 2。Wing flex 2 |
| `WING_FLEX_PCT:3` | %/100 | 机翼挠曲 3。Wing flex 3 |
| `WING_FLEX_PCT:4` | %/100 | 机翼挠曲 4。Wing flex 4 |

---

**分析常用列 / commonly used columns**：位置轨迹 `PLANE_LATITUDE/LONGITUDE/ALTITUDE`；姿态 `PLANE_PITCH/BANK/HEADING_DEGREES_TRUE`；被试操纵 `AILERON/ELEVATOR/RUDDER_POSITION` + `GENERAL_ENG_THROTTLE_LEVER_POSITION:1`；体轴速度 `VELOCITY_BODY_X/Y/Z`；角速度 `ROTATION_VELOCITY_BODY_*`；过载 `G_FORCE`；触地 `SIM_ON_GROUND` / `PLANE_TOUCHDOWN_NORMAL_VELOCITY`。接管反应时对齐用 `rel_t0_s`。

> 单位说明：舵面"位置"是 MSFS 归一化量(约 −1…1)；油门为百分比(0–100)；`%/100` 指"百分比/100"(即 0…1)。个别单位(如 `GPS_GROUND_SPEED`、`VERTICAL_SPEED`)以 DevKit 返回为准，分析前建议用一段已知机动核对量纲。Units for control "position" are MSFS‑normalized (~−1…1); throttle is percent (0–100); `%/100` means percent‑over‑100 (0…1). A couple of units follow whatever the DevKit returns — sanity‑check against a known maneuver before analysis.

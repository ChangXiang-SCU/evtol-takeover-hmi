# Design & control findings

English · 中文见 [DESIGN.zh-CN.md](DESIGN.zh-CN.md)

This document records how this eVTOL is actually controlled through the MSFS AICtrl DevKit, based on live measurement, and how the flight controllers are built on top of those facts.

## 1. The DevKit interface

The DevKit is a local REST server (`127.0.0.1:5000`):

- `GET /get` → a list of `{name, writable, val}` for **every** exposed variable.
- `PUT /set` `{name, val}` → set one variable.
- `PUT /ap_start` / `PUT /ap_stop` → the DevKit's own autopilot (rotor point‑hold, altitude hold, heading). We mostly avoid it in favour of direct control.

The bundled PDF spec lists only a subset; the **authoritative** truth is `/get`'s per‑field `writable` flag. `dump_fields.py` prints it. Measured: **76 fields, 41 writable**, GET/SET round‑trip **1–2 ms** locally.

## 2. Control mapping (measured on this airframe)

| Input (SimVar) | Effect | Notes |
|---|---|---|
| `GENERAL ENG THROTTLE LEVER POSITION:1` | **fore/aft** | writable & effective. > neutral → forward, < neutral → back. **Does not change altitude.** Terminal ground speed ≈ 5 m/s at throttle ≈ 90. |
| `ELEVATOR POSITION` | **vertical (climb/descend)** | +0.8 → climb ≈ 7.5 ft/s, −0.4 → descend ≈ 3.75 ft/s, −0.85 → ≈ 8–9 ft/s. Roughly **±10 ft/s per unit**. Does not move horizontally. |
| `PLANE HEADING / BANK / PITCH` | attitude | writable and **sticks** — but writing them each frame to "fly" is cheating and causes side‑slip. Used only for the one‑time start teleport. |
| `RUDDER / AILERON POSITION` | yaw / roll | writable (rudder untested as a steering loop — see limitations). |
| `VELOCITY_BODY_X` | (lateral) | **write does NOT stick in flight** — commanded −12 read back ≈ 0. So cross‑track cannot be trimmed with body velocity. |
| collective / cyclic / rotor | — | **not exposed** by the DevKit at all. |

Hover‑neutral throttle drifts between teleports (**≈ 33–58**), because the rotor state after a teleport varies — so controllers read it live and clamp throttle by **absolute** value, not by an offset from neutral.

## 3. Geometry: why "just push the throttle" reaches the pad

At the wind‑shear start the nose heading is **≈ 0.3°**, but the helipad bears **≈ 20°** — the nose is ~19.6° to the *left* of the pad. Independently, the throttle thrust vector sits **≈ 19° to the *right*** of the nose. The two cancel, so the resulting ground track points **at the pad**. From the start, pushing the throttle flies straight to the helipad with **no heading input**. (Earlier attempts that *locked* the heading fought this and produced an apparent 35 % rightward drift.)

## 4. Control philosophy

Fly the aircraft the way a human pilot would: **only pilot inputs** — throttle (fore/aft), elevator (up/down), and (future) rudder for steering. Do **not** write attitude / position / body‑velocity to move the aircraft. The only attitude/position write is the one‑time **teleport to the trial start** (an experiment reset, not a control action).

## 5. Forward cruise — `_fwd_fly.py`

Closed‑loop speed hold: measure forward ground speed from the heading‑projected position derivative (sign is guaranteed), and drive an **absolute‑throttle PI** loop to a target (e.g. 4 m/s). Ramp the target in/out for a smooth start/stop. Result: smooth acceleration to a steady cruise, altitude flat to within ~1 ft, straight track. Throttle is clamped to an absolute ceiling (≈ 96) so a low hover‑neutral doesn't starve it.

## 6. Stepped approach — `_step_land.py` / `_throttle_route_loop`

Alternate **level** segments (throttle forward, elevator neutral) and **descent** segments (elevator down). The crucial detail: keep the throttle **on continuously** across both segment types. Stopping the throttle during descent resets the accelerating throttle response to ~0 each cycle, so short level segments never build speed and the aircraft never makes ground — the working version holds a fixed forward throttle the whole time and only toggles the elevator. Segments are ~5 s; the loop ends ~40 ft above the pad. See the parameter table in [USAGE.md](USAGE.md).

## 7. Vertical landing — `_land.py`

Elevator descent‑rate control with an AGL‑scheduled target sink rate — faster up high, flaring near the ground: −6 ft/s above 30 ft AGL, −3.5 (15–30), −2 (6–15), −1 (< 6). Elevator = feed‑forward `target/11` + a small proportional term on the measured sink rate; hard flare if sink exceeds 12 ft/s. Throttle held neutral so it descends in place. Touchdown detected via `SIM ON GROUND` / AGL.

## 8. Scenarios & triggers (`config.py` → `SCENARIOS`)

The operator arms a cause; `monitor_loop` auto‑triggers when the aircraft is inside the zone **radius** *and* **altitude band (MSL)**, after first being seen outside it. Helipad **ZKMZN**: 23.14125, 113.27712, 168 ft.

| Cause | Trigger centre | Radius | Altitude band | Effect at trigger |
|---|---|---|---|---|
| wind shear | 23.13909, 113.27622 | 50 m | 382–582 ft | inject `VELOCITY_BODY_Y` downdraft + longitudinal speed loss; HMI takeover request |
| AP failure | 23.13961, 113.27799 | 50 m | 260–460 ft | `/ap_stop` + AUTO_STOP (hand to subject); HMI takeover request |
| obstacle | 23.141696, 113.276120 | 60 m | 250–500 ft | HMI alert only; AP continues to pad. Approach targets **mid‑band (≈375 ft)** so it meets the rooftops rather than overflying them |

The wind‑shear downdraft works only with **dense, large** `VELOCITY_BODY_Y` injection (≈ −50 ft/s, high rate); small/sparse values do almost nothing.

## 9. Known limitations / next steps

- **Lateral steering.** With no heading input the aircraft holds track well from the geometrically‑aligned start, but over long legs it can drift. `VELOCITY_BODY_X` can't trim it (write doesn't stick) and force‑writing heading oscillates. The clean fix is a **rudder** cross‑track loop (a real pilot input) — `_rudder_test.py` is the probe for it.
- **Neutral‑throttle drift** after teleports — handled by reading it live + absolute clamping, but worth understanding if precise speeds are needed.
- The MCP‑pushed copy of large binaries (the DevKit PDF, Office docs) is not in this repo.

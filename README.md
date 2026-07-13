# eVTOL Takeover HMI — autonomous flight & takeover on MSFS 2024

> 🇨🇳 中文说明：**[README.zh-CN.md](README.zh-CN.md)**　｜　📖 Detailed docs: **[docs/USAGE.md](docs/USAGE.md)** · **[docs/DESIGN.md](docs/DESIGN.md)** · **[docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md)** (采集 CSV 字段说明)

A research platform for studying **pilot takeover** from an autonomous eVTOL. It is built on **Microsoft Flight Simulator 2024** and its **AICtrl DevKit** REST API. The aircraft flies an autonomous **stepped approach** to a rooftop helipad; at a scripted point a hazard is triggered — **wind shear**, **autopilot failure**, or an **obstacle** — and a **multimodal takeover HMI** (visual / audio / both) asks the human subject to take over, while the system records **reaction time** and full **telemetry**.

Everything is **pure Python standard library** (no `pip install` needed, Python 3.8+) and talks to the DevKit over HTTP.

## Highlights

- **Human-style control, no cheating.** The aircraft is flown with the real pilot inputs only — **throttle** (fore/aft) and **elevator** (up/down) — not by writing attitude/position. See [docs/DESIGN.md](docs/DESIGN.md).
- **Operator panel + subject HMI** in one small HTTP server (`controller/control_panel.py`), served at `:8000/` and `:8000/hmi`.
- **One-click autonomous approach** ("AP on") that flies a smooth stepped descent to the helipad and, if a hazard is armed, routes through its trigger zone so the scenario fires automatically.
- **Three hazard scenarios** with geofenced triggers (radius + altitude band), reaction-time capture on two channels (touchscreen + control deflection), and per-trial CSV telemetry.
- **Remote deploy tooling** (`controller/_ssh_deploy.py`) to push and run the controller on the sim host over SSH.

## Repository layout

```
controller/            Runtime: panel/HMI, DevKit client, config, flight controllers, deploy tools
  control_panel.py     Operator panel + subject HMI + scenario logic + "AP on" stepped approach
  devkit_client.py     Pure-stdlib REST client for the MSFS AICtrl DevKit (Real + Mock)
  config.py            Scenarios, coordinates, trigger zones, tunable parameters
  geo.py               Distance / bearing / move helpers (WGS84)
  _fwd_fly.py          Closed-loop smooth forward cruise (throttle PI on ground speed)
  _step_land.py        Stepped descent to helipad (throttle + elevator staircase)
  _land.py             Vertical landing (elevator descent-rate control)
  _ssh_deploy.py       paramiko deploy / remote-run / panel restart / firewall
  ...                  probes & experiments (throttle_fly.py, dump_fields.py, ...)
场景/ , 3 种场景/        Scenario scripts (helipad / wind-shear / AP-failure / obstacle)
docs/                  USAGE and DESIGN docs (English + 中文)
```

## Quick start

Run on the **sim host** (the Windows PC running MSFS + the DevKit on `127.0.0.1:5000`):

```bat
cd controller
python -X utf8 control_panel.py
```

Then open in a browser (on the sim, or any LAN device):

- Operator panel: `http://<sim-ip>:8000/`
- Subject HMI:    `http://<sim-ip>:8000/hmi`

Pick an HMI modality, optionally **arm** a hazard, and press **自动驾驶：开 (AP on)** to fly the autonomous approach. Full walkthrough in **[docs/USAGE.md](docs/USAGE.md)**.

> Remote option: from a laptop, `python -X utf8 _ssh_deploy.py restart` deploys/starts the panel on the sim over SSH. See [controller/README_部署.md](controller/README_部署.md).

## Key findings (this airframe, measured live)

The DevKit `/get` exposes **76 variables, 41 writable**. On this eVTOL:

- **`GENERAL ENG THROTTLE LEVER POSITION:1` = fore/aft** (writable, effective). Above the hover-neutral value → forward, below → backward; it does **not** change altitude. Terminal ground speed ≈ 5 m/s.
- **`ELEVATOR POSITION` = vertical** (climb/descend), ≈ 10 ft/s per unit — unusual for a fixed-wing convention, correct for this rotorcraft model.
- Collective/cyclic SimVars are **not** exposed; `VELOCITY_BODY_X` writes **do not stick** in flight. Attitude (heading/bank) and control (throttle/elevator/rudder) writes do.
- **Geometry:** at the scenario start the nose points ~0.3° while the helipad bears ~20°; throttle thrust sits ~19° right of the nose, so the two cancel — from the start, **just pushing the throttle tracks straight to the pad** with no heading input.

Details, numbers and the control loop in **[docs/DESIGN.md](docs/DESIGN.md)**.

## Safety & scope

This is **simulation research** software for MSFS. It teleports and commands a simulated aircraft; it is **not** for real flight. Recruitment / participant / questionnaire files that contain personal information are intentionally **excluded** from this repository.

## License

No license has been set yet — all rights reserved by the authors until one is added. Open an issue if you need usage terms.

# Usage

English · 中文见 [USAGE.zh-CN.md](USAGE.zh-CN.md)

## 1. Prerequisites

- **MSFS 2024** running with the eVTOL loaded and **in flight** (an aircraft/flight must be active).
- The **AICtrl DevKit** running on the sim host, serving `http://127.0.0.1:5000` (`/get`, `/set`, `/ap_start`, `/ap_stop`).
- **Python 3.8+** on the sim host. Always launch with UTF‑8: `python -X utf8 …` (the console is otherwise non‑UTF‑8 and Chinese strings break).
- No third‑party packages are needed to run on the sim. `paramiko` is only needed on a laptop that deploys over SSH.

## 2. Run the control panel

On the sim host:

```bat
cd controller
python -X utf8 control_panel.py
```

It prints the DevKit field count (confirming the connection) and serves on port **8000**. Open:

- **Operator panel** — `http://<sim-ip>:8000/`
- **Subject HMI** — `http://<sim-ip>:8000/hmi`

`<sim-ip>` is `127.0.0.1` on the sim itself, or the sim's LAN IP from other devices (a touchscreen, your laptop). To allow LAN access, open the firewall once: `python -X utf8 _ssh_deploy.py openfw` (it also prints the LAN IP).

## 3. Operate a trial

On the **operator panel**:

1. **① Choose HMI modality** — visual (flash + text), audio (beeps), or visual+audio.
2. **② Arm a cause** — wind shear / AP failure / obstacle / blank. This sets the trigger zone and the trial start point.
3. **④ Teleport** — "传送到起点" puts the aircraft at the armed cause's start (≈800 ft), "传送到停机坪" parks it over the helipad.
4. **③ Control** — either let the **subject fly manually** into the trigger zone, or press **自动驾驶：开 (AP on)** to fly the autonomous stepped approach.
5. When the aircraft enters the armed zone (within its radius **and** altitude band) the hazard **auto‑triggers**: the HMI raises the takeover request, wind shear injects a downdraft + speed loss, AP failure clears the autopilot. The obstacle case only raises the HMI alert.
6. **Takeover** is detected on two channels — a tap on the HMI **接管** button, or a **control‑stick deflection** beyond a deadband. The **reaction time** is recorded for each.
7. **↺ 复位 (Reset)** clears the trial for the next run; **⚡ 手动立即触发** forces a trigger; **自动驾驶：关** stops the AP route immediately.

Per‑trial telemetry is written to `controller/logs/tel_<id>.csv`; an event summary to `controller/logs/panel_events.csv`.

## 4. "AP on" — the autonomous stepped approach

Pressing **自动驾驶：开** runs `_throttle_route_loop` (in `control_panel.py`): a **pure throttle + elevator** staircase toward the helipad — level segment (throttle forward, elevator neutral), then descent segment (elevator down), alternating, stopping ~40 ft above the pad. If a cause with a trigger zone is armed and not yet triggered, the route first flies **to that zone at an altitude inside its band**, so the scenario fires; wind shear / AP failure then interrupt the AP (handing control to the subject), while the obstacle case continues to the pad.

Tunables at the top of `_throttle_route_loop`:

| Parameter | Meaning | Default |
|---|---|---|
| `FWD` | fixed level‑segment throttle (speed knob) | `min(neutral+32, 90)` |
| `ELEV_DN` | descent‑segment elevator (sink rate) | `-0.85` (≈ 8–9 ft/s) |
| `ARRIVE` | horizontal arrival radius | `25 m` |
| `HOVER_ALT` | stop height above the pad | pad + `40 ft` |
| obstacle target alt | mid‑band (level with rooftops) | `(alt_min+alt_max)/2` |
| other‑cause target alt | high in band | `alt_max − 20` |
| `HZ` | control‑loop rate | `12 Hz` |

## 5. Standalone flight controllers

These run directly against the DevKit (on the sim, or from a laptop with `set DEVKIT_URL=http://<sim-ip>:5000`) and are useful for tuning:

- `python -X utf8 _fwd_fly.py [target_mps] [cruise_s]` — smooth forward cruise (throttle PI on ground speed).
- `python -X utf8 _step_land.py` — stepped descent to the helipad.
- `python -X utf8 _land.py` — vertical landing (elevator sink‑rate control).
- `python -X utf8 dump_fields.py` — dump every DevKit field + its `writable` flag (saves `fields_dump.txt`).
- `python -X utf8 _goto_start.py` / `_recover.py` — teleport to the start / recover to a safe hover.

## 6. Remote deploy from a laptop

`controller/_ssh_deploy.py` uses **paramiko** (the laptop's native `ssh.exe` was unreliable) with a key at `~/.ssh/sim_evtol` to `flightsimulator@<sim-ip>`:

```bat
python -X utf8 _ssh_deploy.py test        REM connection + DevKit-alive check
python -X utf8 _ssh_deploy.py restart      REM (re)start the panel on the sim
python -X utf8 _ssh_deploy.py openfw       REM open firewall 8000 + print LAN IP
python -X utf8 _ssh_deploy.py put <files>  REM SFTP files to the sim
python -X utf8 _ssh_deploy.py run "<cmd>"  REM run a command on the sim
```

`_probe_remote.py <script.py> [args]` uploads a script and runs it on the sim in one shot.

## 7. Troubleshooting

- **Panel won't open** → the process isn't running. `python -X utf8 _ssh_deploy.py restart`, then re‑open the URL.
- **Chinese text is garbled / a script crashes on start** → you forgot `-X utf8`.
- **Laptop can't reach `sim:5000` / `:8000`** → cross‑subnet + a VPN/TUN proxy (e.g. FlClash) can hijack LAN traffic. Run the controller **on the sim** (`127.0.0.1`), or bypass‑LAN in the proxy. Port 8000 was reachable over Wi‑Fi in testing.
- **No trigger fired** → you must **arm** the cause first, and the flight must cross the zone within its radius **and** altitude band.

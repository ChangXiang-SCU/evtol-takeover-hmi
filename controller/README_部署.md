# eVTOL 接管事件控制器 — 部署说明

纯 Python **标准库**实现，**无需 pip 安装任何东西**。Python 3.8+ 即可（Windows 自带的 `py` 也行）。

## 一、文件清单

| 文件 | 作用 |
| --- | --- |
| `config.py` | **所有可调参数**（坐标、风切变剂量、围栏、阈值…）。带 `TODO` 的是占位值，需替换。 |
| `controller.py` | 主程序：自主飞行→触发→断AP→(风切变扰动)→接管检测→记录。 |
| `devkit_client.py` | DevKit REST 客户端（含 Mock 干跑）。 |
| `event_server.py` | 事件服务器：向 HMI 推接管请求、收触摸屏点击、托管测试 HMI。 |
| `hmi_test.html` | 触摸屏**测试版 HMI**（也是给 HMI 开发者的接口参考实现）。 |
| `geo.py` | 经纬度距离/方位小工具。 |
| `logs/` | 运行后自动生成：逐帧遥测 + 每 trial 事件汇总 CSV。 |

## 二、控制器跑在哪台机器？（重要）

DevKit API 在 MSFS 那台电脑上以 `http://<该机IP>:5000` 提供。控制器是它的客户端，两种放法：

- **方案 A（最省事，推荐）**：**控制器就装在 MSFS 那台电脑上**。`config.py` 里 `DEVKIT_BASE_URL` 保持 `http://127.0.0.1:5000`，没有跨机/防火墙问题。
- **方案 B**：控制器装在同一局域网的另一台机器。把 `DEVKIT_BASE_URL` 改成 `http://<MSFS机器局域网IP>:5000`，并确保 **MSFS 那台机器的防火墙放行 5000 端口**入站。

触摸屏 HMI 只要能用浏览器访问“控制器所在机器”的 `:8000` 即可（同一台或同局域网都行）。

## 三、部署步骤

1. 把整个 `controller/` 文件夹拷到目标机器。
2. 先**干跑**（不连 MSFS，验证链路）：`config.py` 里保持 `USE_MOCK = True`，然后
   ```
   python controller.py
   ```
   控制台应打印：飞向目标→`[t0] 触发`→`[接管·操控] RT`→`[LAND] 触地`，并在 `logs/` 生成 CSV。
3. **测试触摸屏 HMI**：干跑时，用触摸屏（或任意浏览器）打开
   ```
   http://<控制器所在机器的IP>:8000/
   ```
   点“进入监控”（首次交互以启用声音）；触发时会弹“请接管”，点大红“接管”按钮 → 控制台/CSV 记录到触摸屏接管时间。
4. **连真实 MSFS**：
   - 先启动 MSFS 2024 + AICtrl DevKit，加载 eVTOL 停在 ZKMZN。
   - `config.py` 改 `USE_MOCK = False`，`DEVKIT_BASE_URL` 指向 MSFS 机器。
   - 自检连接：`python controller.py --check`（打印一帧飞机状态 = 通了）。
   - 正式跑：`python controller.py`（按 `config.SESSION` 里的 trial 序列）。

## 四、跑之前要替换的占位值（config.py 里带 TODO）

- `TLOF` / `TRIGGER_POINTS`：ZKMZN 停机坪与三个触发点的真实经纬度。
- `LAP_STEPS`：梯形进近各阶梯高度/垂直速度。
- `GEOFENCE_RADIUS_M` / `TRIGGER_LEAD_TIME_S`：触发围栏半径与 L3 提前量（4–5s 或 10s）。
- `WIND_SHEAR`：风切变剂量（下击速度、掉速比例、时长）——**务必在 sim 内标定**后再正式采集。
- `SWAP_LATLNG`：若发现飞反，改 `True`（DevKit 文档经纬度字段疑似写反）。
- `CONTROL_DEADBAND`：操纵面“算作接管”的偏转阈值。
- `SESSION`：按拉丁方排布真实 trial 序列。

## 五、输出数据

- `logs/tel_<trialID>.csv`：逐帧遥测（位置、姿态、垂直速度、G 值、操纵面、机体速度、地速…）。
- `logs/session_events.csv`：每个 trial 一行 —— `t0`、`rt_touch_s`（触摸屏接管RT）、`rt_control_s`（操控接管RT）、`touchdown_g`、`landed` 等。

## 六、常见问题

- `--check` 失败：确认 MSFS+DevKit 在跑；`DEVKIT_BASE_URL` 的 IP/端口对不对；方案 B 下 MSFS 机器防火墙是否放行 5000。
- HMI 连不上：确认浏览器访问的是**控制器所在机器**的 IP:8000；同局域网；控制器已启动。
- HMI 没声音：浏览器策略要求先有一次交互——先点“进入监控”即可。
- 风切变太猛/太轻：调 `config.WIND_SHEAR`，在 sim 内反复标定到合适强度。

## 七、说明

这是可运行的**脚手架/最小闭环**：自主飞行、三类统一断 AP、风切变脚本化速度扰动、双通道接管检测、数据记录、HMI 事件契约都已打通。真实场景坐标与风切变剂量为占位值，需按第四节替换并在 sim 内标定后再正式采集。生理采集(EEG/ECG/EDA/RESP)的 t0 同步打标接口预留在事件广播处，需按你们设备（LSL/并口/串口）接入。

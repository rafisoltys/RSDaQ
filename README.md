# RSDaQ

A clean, functional data-acquisition GUI for **Digilent MCC HATs** on **Raspberry Pi 5**.

![status](https://img.shields.io/badge/status-alpha-orange)

## Supported boards

| HAT     | Function                                           | RSDaQ panel       |
| ------- | -------------------------------------------------- | ----------------- |
| MCC118  | 8-ch analog input, 12-bit, ±10 V, 100 kS/s aggregate (per board) | **Acquire / Spectrum / Trigger captures** |
| MCC134  | 4-ch thermocouple input, 24-bit                    | **Thermocouples** |
| MCC152  | 2-ch analog out (0–5 V) + 8-bit DIO                | **Outputs**       |
| MCC172  | 2-ch IEPE / AC analog input, 24-bit, ±5 V, 51.2 kS/s | **Vibration (MCC172)** |

Up to 8 HATs of any combination can be stacked (addresses 0..7). RSDaQ probes
all 8 SPI addresses on startup and detects the kind at each address.

## Features

- **Auto-discovery + manual override** — *Boards → Scan & configure...* shows every
  detected HAT and lets you force a specific kind at any address.
- **Multi-board MCC118 acquisition** — pick any subset of channels on any subset
  of boards; data is interleaved into a single time-aligned matrix.
- **Real-time scrolling plot** (pyqtgraph), per-channel colours and legend.
- **Live FFT spectrum** with selectable size (256 – 32 k), window (Hann / Hamming
  / Blackman / Rect), linear or log magnitude (dBFS).
- **Software trigger** — level + slope (rising/falling) on any enabled channel,
  configurable pre/post window, modes Free run / Normal / Single. Captures show
  up on the *Trigger captures* tab and a marker is drawn on the live plot.
- **Per-channel calibration** — `V_corrected = gain * V_raw + offset`, persisted
  in JSON at `~/.config/rsdaq/calibration.json`. Applied during acquisition
  (toggleable).
- **Live stats table** — last / min / max / mean / RMS / count per channel.
- **Streaming recorder** — CSV or HDF5 (gzip-compressed, resizable per-channel
  datasets), records while you watch.
- **MCC134 panel** — per-channel TC type (J/K/T/E/R/S/B/N/Disabled), polled
  temperatures + CJC, slow rolling plot.
- **MCC152 panel** — AO sliders (0–5 V), per-bit DIO direction toggles,
  output writes, and live input read-back.
- **MCC172 panel** — per-channel IEPE excitation toggle, AC/DC coupling,
  sensor sensitivity, sigma-delta sample rate (200 Hz – 51.2 kHz), live
  time-domain plot + dBFS spectrum.
- **Simulator backend** auto-engages off the Pi (or via `--simulate`) so the
  whole UI is exercisable on any machine.
- **Hardware safety** — the per-board aggregate-rate label turns red if you
  configure a setup that exceeds the MCC118's 100 kS/s ceiling, and validation
  blocks Start.
- Clean dark theme.

## Install (Raspberry Pi 5)

```bash
git clone https://github.com/rafisoltys/RSDaQ.git
cd RSDaQ
./scripts/install_pi.sh
```

The installer:
1. Installs system packages (build tools, `libhdf5-dev`, libxcb runtime libs).
2. Clones and builds Digilent's [`daqhats`](https://github.com/mccdaq/daqhats) library.
3. Installs the Python requirements into a venv.

After install:
```bash
./scripts/run.sh
```

## Install (development on a non-Pi machine)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m rsdaq                                       # auto: simulated 118+134+152+172
python -m rsdaq --simulate "0:118,1:118"              # two stacked MCC118s, no others
python -m rsdaq --simulate "0:172"                    # MCC172 only
python -m rsdaq --simulate ""                         # no boards
```

You can also force the backend kind:

```bash
python -m rsdaq --backend simulator       # never try real daqhats
python -m rsdaq --backend real            # fail loudly if daqhats missing
```

## Tests

```bash
pip install pytest
pytest -q
```

Tests cover ring buffer, online stats, config validation, calibration apply +
persistence, software-trigger edge cases (rising / falling / normal-rearm /
single / free-run / pre-window cap), board-topology parsing, simulators
(scan / TC / output), and CSV + HDF5 recorders.

## Layout

```
rsdaq/
├── app.py             entry point + Qt bootstrap
├── config.py          AcquisitionConfig + SoftwareTriggerConfig + FFTConfig
├── calibration.py     gain/offset store
├── daq/               backends (real + simulator) + board discovery
│   ├── boards.py
│   ├── mcc118_backend.py
│   ├── mcc134_backend.py
│   ├── mcc152_backend.py
│   ├── mcc172_backend.py
│   └── simulator.py
├── core/              ring buffer, stats, software trigger, worker thread
└── ui/                Qt widgets (control panel, plot, FFT, TC, output, vibration, dialogs)
```

## License

MIT

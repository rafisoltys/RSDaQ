# RSDaQ

A clean, functional data-acquisition GUI for the **Digilent MCC118** HAT on **Raspberry Pi 5**.

![status](https://img.shields.io/badge/status-alpha-orange)

## Features

- 8-channel acquisition from MCC118 (12-bit, ±10 V, up to 100 kS/s aggregate)
- Per-channel enable / colour / live min/max/mean/RMS
- Real-time scrolling plot (pyqtgraph, decoupled from sample rate)
- Configurable sample rate, samples-per-channel, scan mode (finite / continuous)
- Trigger: immediate, software, or external
- Streaming recorder (CSV or HDF5) — records while you watch
- Simulator backend for off-Pi development (auto-detected when `daqhats` is missing)
- Clean dark theme

## Hardware

| Item            | Spec                                              |
| --------------- | ------------------------------------------------- |
| Board           | Digilent / Measurement Computing **MCC 118**      |
| Channels        | 8 single-ended analog inputs                      |
| Resolution      | 12 bits                                           |
| Range           | ±10 V                                             |
| Aggregate rate  | 100 kS/s (shared across enabled channels)         |
| Host            | Raspberry Pi 5 (also works on Pi 4, 3B+, Zero 2W) |

Up to 8 boards can be stacked. RSDaQ currently targets a single board; multi-board support is on the roadmap.

## Install (Raspberry Pi 5)

```bash
git clone https://github.com/rafisoltys/RSDaQ.git
cd RSDaQ
./scripts/install_pi.sh
```

The installer:
1. Installs system packages (`python3-pyside6`, build tools, `libhdf5-dev`).
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
python -m rsdaq
```

Without `daqhats` available, RSDaQ runs the **simulator backend** so the GUI is fully exercisable.

## Layout

See [structure](#) — modules under `rsdaq/`:

- `daq/`     — hardware backends (real MCC118, simulator)
- `core/`    — acquisition worker, ring buffer, online statistics
- `io/`      — streaming CSV / HDF5 recorder
- `ui/`      — Qt widgets

## License

MIT

"""MCC152 (analog out + DIO) panel."""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)

from rsdaq.config import NUM_AO_152, NUM_DIO_152
from rsdaq.daq.backend import OutputBackend


class OutputPanel(QWidget):
    """Operates an open MCC152 (or simulator) at one address."""

    def __init__(self, backend: OutputBackend, address: int, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._address = address
        self._opened = False
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(250)
        self._poll_timer.timeout.connect(self._refresh_dio_inputs)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b>MCC152</b> at address #{self._address}"))
        header.addStretch(1)
        self.connect_btn = QPushButton("Open")
        self.connect_btn.setCheckable(True)
        self.connect_btn.toggled.connect(self._on_open_toggled)
        header.addWidget(self.connect_btn)
        root.addLayout(header)

        # ---- Analog out ----
        ao_group = QGroupBox("Analog out (0 - 5 V)")
        ao_layout = QGridLayout(ao_group)
        self._ao_spins: List[QDoubleSpinBox] = []
        self._ao_sliders: List[QSlider] = []
        for ch in range(NUM_AO_152):
            ao_layout.addWidget(QLabel(f"CH{ch}"), ch, 0)
            spin = QDoubleSpinBox()
            spin.setDecimals(3); spin.setRange(0.0, 5.0); spin.setSingleStep(0.05)
            spin.setSuffix(" V"); spin.setMinimumWidth(110)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 5000)
            spin.valueChanged.connect(lambda v, c=ch: self._on_ao_spin(c, v))
            slider.valueChanged.connect(lambda v, c=ch: self._on_ao_slider(c, v))
            ao_layout.addWidget(spin, ch, 1)
            ao_layout.addWidget(slider, ch, 2)
            self._ao_spins.append(spin)
            self._ao_sliders.append(slider)
        root.addWidget(ao_group)

        # ---- DIO ----
        dio_group = QGroupBox("Digital IO (8 bits)")
        dio_layout = QGridLayout(dio_group)
        dio_layout.addWidget(_h("Bit"), 0, 0)
        dio_layout.addWidget(_h("Direction"), 0, 1)
        dio_layout.addWidget(_h("Output"), 0, 2)
        dio_layout.addWidget(_h("Input read"), 0, 3)
        self._dio_dir: List[QCheckBox] = []
        self._dio_out: List[QCheckBox] = []
        self._dio_in_labels: List[QLabel] = []
        for bit in range(NUM_DIO_152):
            dio_layout.addWidget(QLabel(str(bit)), bit + 1, 0)
            dir_check = QCheckBox("Output")
            dir_check.toggled.connect(lambda checked, b=bit: self._on_dir_changed(b, checked))
            self._dio_dir.append(dir_check)
            dio_layout.addWidget(dir_check, bit + 1, 1)
            out_check = QCheckBox("High")
            out_check.toggled.connect(lambda checked, b=bit: self._on_out_changed(b, checked))
            self._dio_out.append(out_check)
            dio_layout.addWidget(out_check, bit + 1, 2)
            in_lbl = QLabel("--")
            in_lbl.setProperty("role", "value")
            self._dio_in_labels.append(in_lbl)
            dio_layout.addWidget(in_lbl, bit + 1, 3)
        root.addWidget(dio_group)
        root.addStretch(1)
        self._set_enabled(False)

    # ----------------------------------------------------- open / close
    def _on_open_toggled(self, opened: bool) -> None:
        if opened:
            try:
                self._backend.open(self._address)
            except Exception as exc:
                from PySide6.QtWidgets import QMessageBox
                self.connect_btn.setChecked(False)
                QMessageBox.warning(self, "Open failed", str(exc))
                return
            self._opened = True
            self.connect_btn.setText("Close")
            # Push current widget state to hardware.
            for ch in range(NUM_AO_152):
                self._on_ao_spin(ch, self._ao_spins[ch].value())
            for bit in range(NUM_DIO_152):
                self._on_dir_changed(bit, self._dio_dir[bit].isChecked())
                self._on_out_changed(bit, self._dio_out[bit].isChecked())
            self._poll_timer.start()
            self._set_enabled(True)
        else:
            self._poll_timer.stop()
            try:
                self._backend.close()
            finally:
                self._opened = False
                self.connect_btn.setText("Open")
                self._set_enabled(False)

    def _set_enabled(self, on: bool) -> None:
        for w in self._ao_spins + self._ao_sliders + self._dio_dir + self._dio_out:
            w.setEnabled(on)

    # ----------------------------------------------------- AO callbacks
    def _on_ao_spin(self, ch: int, value: float) -> None:
        slider = self._ao_sliders[ch]
        with _block(slider):
            slider.setValue(int(value * 1000))
        if self._opened:
            try:
                self._backend.set_ao(ch, value)
            except Exception:
                pass

    def _on_ao_slider(self, ch: int, value: int) -> None:
        spin = self._ao_spins[ch]
        with _block(spin):
            spin.setValue(value / 1000.0)
        if self._opened:
            try:
                self._backend.set_ao(ch, value / 1000.0)
            except Exception:
                pass

    # ---------------------------------------------------- DIO callbacks
    def _on_dir_changed(self, bit: int, output: bool) -> None:
        self._dio_out[bit].setEnabled(output)
        if self._opened:
            try:
                self._backend.set_dio_direction(bit, output)
            except Exception:
                pass

    def _on_out_changed(self, bit: int, value: bool) -> None:
        if self._opened and self._dio_dir[bit].isChecked():
            try:
                self._backend.set_dio(bit, value)
            except Exception:
                pass

    def _refresh_dio_inputs(self) -> None:
        if not self._opened:
            return
        for bit in range(NUM_DIO_152):
            try:
                v = self._backend.get_dio(bit)
                self._dio_in_labels[bit].setText("HIGH" if v else "low")
            except Exception:
                self._dio_in_labels[bit].setText("?")


def _h(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-weight:600; color:#9ec5fe;")
    return lbl


class _block:
    def __init__(self, widget):
        self._w = widget

    def __enter__(self):
        self._prev = self._w.blockSignals(True)
        return self._w

    def __exit__(self, *_a):
        self._w.blockSignals(self._prev)

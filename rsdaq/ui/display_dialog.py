"""Modal dialog: pick visualisation style + engineering-unit mapping per channel."""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from rsdaq.config import NUM_CHANNELS_118
from rsdaq.daq.boards import BoardInfo, BoardKind
from rsdaq.display import ChannelDisplay, DisplayStore, VizStyle


class DisplayDialog(QDialog):
    """Per-channel visualisation + engineering-unit configuration."""

    HEADERS = [
        "Board", "Channel", "Visualise as", "Use EU",
        "Unit", "Raw min (V)", "Raw max (V)", "EU min", "EU max", "Label",
    ]

    def __init__(self, store: DisplayStore, mcc118_boards: List[BoardInfo],
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Channel display configuration")
        self.resize(940, 520)
        self._store = store
        self._boards = [b for b in mcc118_boards if b.kind is BoardKind.MCC118]
        self._build()
        self._load_into_table()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        info = QLabel(
            "Choose how each channel is visualised on the Acquire tab "
            "(line graph, vertical bar, or radial gauge), and optionally "
            "map raw volts to engineering units.<br>"
            "<i>Example:</i> a 0-5 V pressure transducer rated 0-6 bar "
            "becomes <b>EU on, Unit=bar, Raw 0..5 V, EU 0..6</b>."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        n_rows = len(self._boards) * NUM_CHANNELS_118
        self.table = QTableWidget(n_rows, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        h = self.table.horizontalHeader()
        for i in range(len(self.HEADERS)):
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.HEADERS.index("Label"), QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        # Build per-row editor widgets and remember handles for save.
        self._editors = []
        row = 0
        for board in self._boards:
            for ch in range(NUM_CHANNELS_118):
                self.table.setItem(row, 0, _ro(f"#{board.address}"))
                self.table.setItem(row, 1, _ro(f"CH{ch}"))

                viz = QComboBox()
                for v in VizStyle:
                    viz.addItem(v.value, v.name)

                use_eu = QCheckBox()
                use_eu.setStyleSheet("margin-left: 12px;")

                unit = QLineEdit()
                unit.setPlaceholderText("V")

                raw_min = QDoubleSpinBox()
                raw_min.setRange(-100.0, 100.0); raw_min.setDecimals(4); raw_min.setSingleStep(0.1)
                raw_max = QDoubleSpinBox()
                raw_max.setRange(-100.0, 100.0); raw_max.setDecimals(4); raw_max.setSingleStep(0.1)

                eu_min = QDoubleSpinBox()
                eu_min.setRange(-1e6, 1e6); eu_min.setDecimals(4); eu_min.setSingleStep(0.1)
                eu_max = QDoubleSpinBox()
                eu_max.setRange(-1e6, 1e6); eu_max.setDecimals(4); eu_max.setSingleStep(0.1)

                label_edit = QLineEdit()
                label_edit.setPlaceholderText("e.g. Pressure")

                self.table.setCellWidget(row, 2, viz)
                self.table.setCellWidget(row, 3, use_eu)
                self.table.setCellWidget(row, 4, unit)
                self.table.setCellWidget(row, 5, raw_min)
                self.table.setCellWidget(row, 6, raw_max)
                self.table.setCellWidget(row, 7, eu_min)
                self.table.setCellWidget(row, 8, eu_max)
                self.table.setCellWidget(row, 9, label_edit)

                widgets = (board.address, ch, viz, use_eu, unit,
                           raw_min, raw_max, eu_min, eu_max, label_edit)
                self._editors.append(widgets)
                use_eu.toggled.connect(
                    lambda checked, w=widgets: self._on_eu_toggled(w, checked))
                row += 1

        btn_row = QHBoxLayout()
        self.reset_btn = QPushButton("Reset all to default (Graph / raw V)")
        self.reset_btn.clicked.connect(self._on_reset_all)
        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("Save")
        bb.accepted.connect(self._on_save)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _load_into_table(self) -> None:
        for (addr, ch, viz, use_eu, unit, raw_min, raw_max,
             eu_min, eu_max, label_edit) in self._editors:
            d = self._store.get(addr, ch)
            idx = viz.findData(d.viz_style.name)
            viz.setCurrentIndex(idx if idx >= 0 else 0)
            use_eu.setChecked(d.use_eu)
            unit.setText(d.unit)
            raw_min.setValue(d.raw_min_v); raw_max.setValue(d.raw_max_v)
            eu_min.setValue(d.eu_min); eu_max.setValue(d.eu_max)
            label_edit.setText(d.label)
            self._on_eu_toggled(
                (addr, ch, viz, use_eu, unit, raw_min, raw_max,
                 eu_min, eu_max, label_edit), use_eu.isChecked())

    def _on_eu_toggled(self, widgets, checked: bool) -> None:
        (_a, _c, _v, _u, unit, raw_min, raw_max, eu_min, eu_max, _label) = widgets
        for w in (unit, raw_min, raw_max, eu_min, eu_max):
            w.setEnabled(checked)

    def _on_reset_all(self) -> None:
        for (_addr, _ch, viz, use_eu, unit, raw_min, raw_max,
             eu_min, eu_max, label_edit) in self._editors:
            viz.setCurrentIndex(0)
            use_eu.setChecked(False)
            unit.setText("V")
            raw_min.setValue(0.0); raw_max.setValue(5.0)
            eu_min.setValue(0.0); eu_max.setValue(5.0)
            label_edit.clear()

    def _on_save(self) -> None:
        for (addr, ch, viz, use_eu, unit, raw_min, raw_max,
             eu_min, eu_max, label_edit) in self._editors:
            try:
                style = VizStyle[viz.currentData()]
            except (KeyError, TypeError):
                style = VizStyle.GRAPH
            d = ChannelDisplay(
                viz_style=style,
                use_eu=use_eu.isChecked(),
                unit=unit.text().strip() or "V",
                raw_min_v=float(raw_min.value()),
                raw_max_v=float(raw_max.value()),
                eu_min=float(eu_min.value()),
                eu_max=float(eu_max.value()),
                label=label_edit.text().strip(),
            )
            self._store.set(addr, ch, d)
        try:
            self._store.save()
        except OSError as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Save failed", f"Could not save display config:\n{exc}")
            return
        self.accept()


def _ro(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    it.setTextAlignment(Qt.AlignCenter)
    return it

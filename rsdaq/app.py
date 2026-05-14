"""Application entry point."""
from __future__ import annotations

import argparse
import logging
import sys
from importlib import resources

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

from rsdaq.daq import create_backend
from rsdaq.ui.main_window import MainWindow


def _apply_dark_palette(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#1b1d23"))
    pal.setColor(QPalette.WindowText, QColor("#e6e6e6"))
    pal.setColor(QPalette.Base, QColor("#1f2230"))
    pal.setColor(QPalette.AlternateBase, QColor("#232630"))
    pal.setColor(QPalette.Text, QColor("#e6e6e6"))
    pal.setColor(QPalette.Button, QColor("#2d3140"))
    pal.setColor(QPalette.ButtonText, QColor("#e6e6e6"))
    pal.setColor(QPalette.Highlight, QColor("#3a5fb6"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipBase, QColor("#232630"))
    pal.setColor(QPalette.ToolTipText, QColor("#e6e6e6"))
    app.setPalette(pal)


def _load_stylesheet() -> str:
    try:
        return resources.files("rsdaq.ui").joinpath("style.qss").read_text(encoding="utf-8")
    except Exception:
        return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="rsdaq", description="MCC118 data acquisition")
    parser.add_argument(
        "--backend", choices=["auto", "mcc118", "simulator"], default="auto",
        help="Force a specific DAQ backend (default: auto-detect)")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setApplicationName("RSDaQ")
    app.setOrganizationName("rafisoltys")

    _apply_dark_palette(app)
    qss = _load_stylesheet()
    if qss:
        app.setStyleSheet(qss)

    backend = create_backend(args.backend)
    win = MainWindow(backend=backend)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

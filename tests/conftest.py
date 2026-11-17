import gc
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def app():
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    yield application
    application.closeAllWindows()
    for widget in application.topLevelWidgets():
        widget.deleteLater()
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
    gc.collect()


@pytest.fixture
def tone():
    import numpy as np

    def make(level, seconds=1.0, rate=16000):
        t = np.arange(int(seconds * rate)) / rate
        return (level * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

    return make

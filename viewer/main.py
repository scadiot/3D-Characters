import sys

from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication


def main() -> int:
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)  # avant la création de QApplication

    app = QApplication(sys.argv)
    from viewer.ui.main_window import MainWindow

    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

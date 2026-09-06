import platform
import webbrowser

from aqt import mw
from aqt.qt import *

from util import run_win_install, run_macos_install, run_linux_install

GUIDE = 'https://github.com/asvintheguy/AnkiBrain#install-the-python-study-engine-once'


class InstallDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('AnkiBrain — Set Up Study Engine')
        self.resize(540, 280)
        layout = QVBoxLayout(self)
        text = QLabel('ChatGPT sign-in is built in. To make cards and process documents, AnkiBrain also needs '
                      'a one-time Python environment. You do not need an AnkiBrain account, balance, or AI-provider CLI.\n\n'
                      'Follow the setup guide, then restart Anki. Your sign-in and AI settings are kept. '
                      'Repairing an existing environment replaces it, but does not remove your cards or documents.')
        text.setWordWrap(True)
        layout.addWidget(text)
        guide = QPushButton('Open step-by-step setup guide')
        guide.clicked.connect(lambda: webbrowser.open(GUIDE))
        layout.addWidget(guide)
        system = platform.system()
        installers = {'Windows': ('Windows', run_win_install), 'Darwin': ('macOS', run_macos_install),
                      'Linux': ('Ubuntu/Debian only', run_linux_install)}
        if system in installers:
            label, run = installers[system]
            button = QPushButton(f'Run legacy automatic installer ({label})…')
            def install():
                if QMessageBox.question(self, 'Run setup', 'This opens an installer in a terminal, downloads dependencies, '
                                        'and replaces any existing study-engine environment. Continue?') == QMessageBox.StandardButton.Yes:
                    try:
                        run()
                    except OSError:
                        QMessageBox.warning(self, 'Could not launch installer', 'Use the step-by-step setup guide instead.')
            button.clicked.connect(install)
            layout.addWidget(button)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)


def show_install_dialog():
    mw.installDialog = InstallDialog(mw)
    mw.installDialog.show()

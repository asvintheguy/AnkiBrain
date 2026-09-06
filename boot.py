from aqt import mw


def add_ankibrain_menu():
    mw.ankibrain_menu = mw.form.menubar.addMenu('AnkiBrain')


def load_ankibrain():
    from settings import SettingsManager
    from project_paths import settings_path
    from AnkiBrainModule import AnkiBrain

    mw.settingsManager = SettingsManager(pth=settings_path)
    # One application, including for installations that previously selected SERVER.
    # Show the welcome screen even when the optional Python environment needs setup.
    mw.ankiBrain = AnkiBrain()

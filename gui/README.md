# Music Tools GUI

PySide6 desktop application for Music Tools. Run from the project root:

```
python gui\main.py
```

Or double-click **`Run - Music Tools GUI.cmd`** in the project root.

## Requirements

```
pip install PySide6
```

## Platform compatibility

PySide6 runs on Windows, macOS, and Linux — the GUI works on all three with no code changes. The `Run - Music Tools GUI.cmd` launcher is Windows-only; on Linux/macOS use:

```bash
python gui/main.py
```

## File structure

| File | Purpose |
|---|---|
| `main.py` | Entry point — creates `QApplication` and shows `MainWindow` |
| `main_window.py` | Main window: sidebar, central panel stack, log panel, status bar |
| `settings_panel.py` | Settings form wired to `music_config.json` via `load_config()` |
| `log_panel.py` | Timestamped colour-coded log widget with thread-safe bridge for `QThread` |
| `theme.py` | Dark stylesheet and colour constants |

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 1 | Shell: sidebar navigation, settings panel, log panel | ✅ Complete |
| 2 | Wire in first scripts: Sort CD Tracks, Clean Album Folders, Fix Featuring, Fix Double Spaces | Planned |
| 3 | Remaining tools | Planned |

## Calling a script from the GUI (Phase 2 pattern)

Scripts must always be called from a `QThread`, never the main thread.

```python
from PySide6.QtCore import QThread, Signal, QObject
from sort_cd_tracks.sort_cd_tracks import run_sort_cd_tracks

class SortWorker(QThread):
    finished = Signal(dict)

    def __init__(self, folder, apply, log_cb, progress_cb):
        super().__init__()
        self.folder = folder
        self.apply = apply
        self.log_cb = log_cb
        self.progress_cb = progress_cb

    def run(self):
        result = run_sort_cd_tracks(
            folder=self.folder,
            apply=self.apply,
            log_callback=self.log_cb,
            progress_callback=self.progress_cb,
        )
        self.finished.emit(result)

# In the tool panel:
worker = SortWorker(
    folder=Path("E:/Music"),
    apply=False,
    log_cb=self.log.append_callback(),
    progress_cb=lambda cur, tot, msg: self.progress_bar.setValue(cur),
)
worker.finished.connect(self.on_done)
worker.start()
```

from __future__ import annotations
# import os
# os.environ["QT_QUICK_BACKEND"] = "software"
# os.environ["QT_OPENGL"] = "software"

import csv
import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import (
    QAbstractTableModel,
    QDateTime,
    QModelIndex,
    QObject,
    QRegularExpression,
    QSettings,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import FileRecord, ScanResult, normalize_directory, scan_directory, suggested_export_name
from updater import UpdateChecker, UpdateInfo


APP_TITLE = "本地目录提取工具"
APP_VERSION = "1.0.0"
# GitHub 仓库标识，更新检查会访问 https://api.github.com/repos/{GITHUB_REPO}/releases/latest
GITHUB_REPO = "hkcoo/DirectoryExtractor"
AUTHOR_TEXT = "作者：观山海  ·  QQ：6938070  ·  www.237654.xyz"


def resource_path(file_name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / file_name


class FileTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[FileRecord] = []
        self.hide_extension = False

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else 2

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.records):
            return None
        record = self.records[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            if index.column() == 0:
                return record.full_path
            return record.display_name(self.hide_extension)
        if role == Qt.ItemDataRole.UserRole:
            return record.full_path if index.column() == 0 else record.file_name
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 1:
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ("完整路径", "文件名")[section]
        return super().headerData(section, orientation, role)

    def set_records(self, records: list[FileRecord]) -> None:
        self.beginResetModel()
        self.records = records
        self.endResetModel()

    def clear(self) -> None:
        self.set_records([])

    def set_hide_extension(self, enabled: bool) -> None:
        if self.hide_extension == enabled:
            return
        self.hide_extension = enabled
        if self.records:
            top = self.index(0, 1)
            bottom = self.index(len(self.records) - 1, 1)
            self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.DisplayRole])


class ScanWorker(QObject):
    progress = Signal(int)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, target_path: str, recursive: bool, cancel_event: threading.Event):
        super().__init__()
        self.target_path = target_path
        self.recursive = recursive
        self.cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        try:
            result = scan_directory(
                self.target_path,
                self.recursive,
                cancelled=self.cancel_event.is_set,
                progress=self.progress.emit,
            )
            self.completed.emit(result)
        except Exception as error:  # UI boundary: show every filesystem failure safely
            self.failed.emit(str(error))


LIGHT_STYLE = """
QWidget { color:#1f2937; font-family:"Microsoft YaHei UI"; font-size:13px; }
QMainWindow, QWidget#root { background:#f2f5fa; }
QFrame#header { background:#ffffff; border-bottom:1px solid #e6eaf2; }
QLabel#logo {
  background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #5b8cff, stop:1 #3563e9);
  color:#ffffff; border-radius:12px; font-size:21px; font-weight:700;
}
QLabel#title { font-size:19px; font-weight:700; color:#0f172a; }
QLabel#subtitle, QLabel#muted, QLabel#author { color:#6b7280; font-size:12px; }
QFrame#card { background:#ffffff; border:1px solid #e5e9f2; border-radius:14px; }
QLabel#sectionTitle { font-size:13px; font-weight:600; color:#334155; }
QLabel#emptyIcon { background:#eef3ff; color:#7fa2f5; border-radius:34px; font-size:32px; }
QLineEdit {
  background:#f8fafd; border:1px solid #dbe1ec; border-radius:8px; padding:8px 12px;
  selection-background-color:#3563e9; selection-color:#ffffff;
}
QLineEdit:hover { border-color:#c3cede; }
QLineEdit:focus { border:1px solid #3563e9; background:#ffffff; }
QLineEdit:disabled { background:#f1f3f8; color:#9aa3b2; }
QPushButton {
  background:#ffffff; border:1px solid #dce2ec; border-radius:8px;
  padding:8px 14px; font-weight:600; color:#33415c;
}
QPushButton:hover { background:#f4f7ff; border-color:#b9cbfa; color:#2b5bd7; }
QPushButton:pressed { background:#e8eeff; }
QPushButton:disabled { background:#f4f6fa; color:#a7b0bf; border-color:#e6eaf0; }
QPushButton#primary {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #4f82ff, stop:1 #3363e8);
  border:1px solid #2f5bdd; color:#ffffff;
}
QPushButton#primary:hover { background:#3f74f7; border-color:#2f5bdd; color:#ffffff; }
QPushButton#primary:pressed { background:#2f5bdd; }
QPushButton#primary:disabled { background:#c7d4f5; border-color:#c7d4f5; color:#f2f5ff; }
QPushButton#danger { color:#d92d20; }
QPushButton#danger:hover { background:#fef2f1; border-color:#f2b8b3; color:#b42318; }
QPushButton#danger:pressed { background:#fde8e6; }
QToolButton {
  background:transparent; border:1px solid #dce2ec; border-radius:19px;
  color:#6b7280; font-size:15px; padding:0;
}
QToolButton:hover { background:#eef3ff; border-color:#b9cbfa; color:#2b5bd7; }
QCheckBox { spacing:8px; color:#475467; }
QTableView {
  background:#ffffff; alternate-background-color:#fafbfe; border:0;
  gridline-color:transparent; selection-background-color:#e8f0ff; selection-color:#1f2937;
}
QTableView::item { padding:6px 8px; border:0; }
QTableView::item:selected { background:#e8f0ff; }
QHeaderView::section {
  background:#f7f9fc; color:#667085; border:0; border-bottom:1px solid #e6eaf2;
  padding:10px 10px; font-weight:600; font-size:12px;
}
QTableCornerButton::section { background:#f7f9fc; border:0; }
QProgressBar { background:#e8ecf4; border:0; border-radius:3px; height:6px; text-align:center; }
QProgressBar::chunk { border-radius:3px; background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #4f82ff, stop:1 #3363e8); }
QScrollBar:vertical { background:transparent; width:10px; margin:4px 3px; }
QScrollBar::handle:vertical { background:#ccd5e3; min-height:32px; border-radius:5px; }
QScrollBar::handle:vertical:hover { background:#b3c0d4; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QScrollBar:horizontal { background:transparent; height:10px; margin:3px 4px; }
QScrollBar::handle:horizontal { background:#ccd5e3; min-width:32px; border-radius:5px; }
QScrollBar::handle:horizontal:hover { background:#b3c0d4; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background:transparent; }
QToolTip { background:#111827; color:#f9fafb; border:0; padding:6px 8px; border-radius:6px; }
"""


DARK_STYLE = """
QWidget { color:#e5eaf2; font-family:"Microsoft YaHei UI"; font-size:13px; }
QMainWindow, QWidget#root { background:#0f1420; }
QFrame#header { background:#151c2c; border-bottom:1px solid #252f43; }
QLabel#logo {
  background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #6a92ff, stop:1 #4066e6);
  color:#ffffff; border-radius:12px; font-size:21px; font-weight:700;
}
QLabel#title { font-size:19px; font-weight:700; color:#f2f5fb; }
QLabel#subtitle, QLabel#muted, QLabel#author { color:#8e9bb3; font-size:12px; }
QFrame#card { background:#161e2e; border:1px solid #252f43; border-radius:14px; }
QLabel#sectionTitle { font-size:13px; font-weight:600; color:#cbd5e6; }
QLabel#emptyIcon { background:#1d2740; color:#6b8ce0; border-radius:34px; font-size:32px; }
QLineEdit {
  background:#101724; border:1px solid #303c52; border-radius:8px; padding:8px 12px;
  selection-background-color:#4066e6; selection-color:#ffffff;
}
QLineEdit:hover { border-color:#3d4a63; }
QLineEdit:focus { border:1px solid #6d8df0; background:#131c2c; }
QLineEdit:disabled { background:#131a27; color:#5f6b80; }
QPushButton {
  background:#1e2739; border:1px solid #303c52; border-radius:8px;
  padding:8px 14px; font-weight:600; color:#cfd8e8;
}
QPushButton:hover { background:#24304a; border-color:#4a5d80; color:#ffffff; }
QPushButton:pressed { background:#182033; }
QPushButton:disabled { background:#192233; color:#5f6b80; border-color:#242e40; }
QPushButton#primary {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #5b83ff, stop:1 #3f66e8);
  border:1px solid #3a5ada; color:#ffffff;
}
QPushButton#primary:hover { background:#6d90ff; border-color:#3a5ada; color:#ffffff; }
QPushButton#primary:pressed { background:#3a5ada; }
QPushButton#primary:disabled { background:#2a3550; border-color:#2a3550; color:#6d7c9e; }
QPushButton#danger { color:#ff7b86; }
QPushButton#danger:hover { background:#33202a; border-color:#7a3a44; color:#ff9aa3; }
QPushButton#danger:pressed { background:#291a22; }
QToolButton {
  background:transparent; border:1px solid #303c52; border-radius:19px;
  color:#8e9bb3; font-size:15px; padding:0;
}
QToolButton:hover { background:#22304c; border-color:#4a5d80; color:#cfe0ff; }
QCheckBox { spacing:8px; color:#a8b4c8; }
QTableView {
  background:#161e2e; alternate-background-color:#192233; border:0;
  gridline-color:transparent; selection-background-color:#26406f; selection-color:#ffffff;
}
QTableView::item { padding:6px 8px; border:0; }
QTableView::item:selected { background:#26406f; }
QHeaderView::section {
  background:#1b2436; color:#9aa6b8; border:0; border-bottom:1px solid #2b3546;
  padding:10px 10px; font-weight:600; font-size:12px;
}
QTableCornerButton::section { background:#1b2436; border:0; }
QProgressBar { background:#232d40; border:0; border-radius:3px; height:6px; text-align:center; }
QProgressBar::chunk { border-radius:3px; background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6d90ff, stop:1 #3f66e8); }
QScrollBar:vertical { background:transparent; width:10px; margin:4px 3px; }
QScrollBar::handle:vertical { background:#3a465e; min-height:32px; border-radius:5px; }
QScrollBar::handle:vertical:hover { background:#4a5a76; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QScrollBar:horizontal { background:transparent; height:10px; margin:3px 4px; }
QScrollBar::handle:horizontal { background:#3a465e; min-width:32px; border-radius:5px; }
QScrollBar::handle:horizontal:hover { background:#4a5a76; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background:transparent; }
QToolTip { background:#e5eaf2; color:#111827; border:0; padding:6px 8px; border-radius:6px; }
"""


def dark_palette() -> QPalette:
    """深色调色板：让复选框、下拉框等原生控件在深色主题下正确着色。"""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#0f1420"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#e5eaf2"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#101724"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#192233"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#e5eaf2"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#1e2739"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#cfd8e8"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#26406f"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#e5eaf2"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#111827"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#5f6b80"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#5f6b80"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#5f6b80"))
    return palette


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings("hkcoo", "DirectoryExtractor")
        self.model = FileTableModel()
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.scan_thread: QThread | None = None
        self.scan_worker: ScanWorker | None = None
        self.scan_name = ""
        self.cancel_event = threading.Event()
        self.is_scanning = False
        self.close_after_scan = False
        self.dark_mode = self.settings.value("darkMode", False, bool)
        self.update_thread: QThread | None = None
        self.update_worker: UpdateChecker | None = None
        self._update_manual = False

        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION}  QQ:6938070")
        self.resize(1180, 760)
        self.setMinimumSize(880, 600)
        icon_path = resource_path("zm_icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setAcceptDrops(True)
        self._build_ui()
        self._create_shortcuts()
        self._apply_theme()
        self._restore_settings()
        # 启动后延迟做一次后台更新检查（按 QSettings 限频，避免频繁刷 GitHub API）
        self._schedule_update_check()

    def _schedule_update_check(self) -> None:
        last = self.settings.value("lastUpdateCheck", "", str)
        last_time = QDateTime.fromString(last, Qt.DateFormat.ISODate) if last else QDateTime()
        if last_time.isValid() and last_time.addDays(1) > QDateTime.currentDateTime():
            return
        QTimer.singleShot(3000, self.check_for_updates)

    def _button(self, text: str, slot, name="") -> QPushButton:
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(slot)
        if name:
            button.setObjectName(name)
        return button

    def _build_ui(self) -> None:
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = QFrame(objectName="header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 17, 24, 17)
        logo = QLabel("目", objectName="logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(44, 44)
        titles = QVBoxLayout()
        title = QLabel(APP_TITLE, objectName="title")
        subtitle = QLabel("快速整理文件路径与名称，让目录清单一目了然", objectName="subtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        self.theme_button = QToolButton()
        self.theme_button.setToolTip("切换深色/浅色主题")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.setFixedSize(38, 38)
        self.theme_button.clicked.connect(self.toggle_theme)
        self.update_button = self._button("检查更新", self.check_update_manual)
        self.update_button.setFixedSize(92, 38)
        header_layout.addWidget(logo)
        header_layout.addLayout(titles)
        header_layout.addStretch()
        header_layout.addWidget(self.update_button)
        header_layout.addWidget(self.theme_button)
        root_layout.addWidget(header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 18)
        content_layout.setSpacing(14)

        path_card = QFrame(objectName="card")
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(16, 14, 16, 16)
        path_layout.setSpacing(10)
        path_layout.addWidget(QLabel("目标目录", objectName="sectionTitle"))
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(os.getcwd())
        self.path_edit.setPlaceholderText("输入目录路径，或将文件夹拖放到窗口")
        self.path_edit.returnPressed.connect(lambda: self.start_scan(False))
        self.browse_button = self._button("浏览目录", self.browse_directory)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(self.browse_button)
        path_layout.addLayout(path_row)
        content_layout.addWidget(path_card)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.current_button = self._button("扫描当前目录", lambda: self.start_scan(False), "primary")
        self.recursive_button = self._button("递归扫描", lambda: self.start_scan(True))
        self.cancel_button = self._button("停止", self.cancel_scan, "danger")
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.current_button)
        actions.addWidget(self.recursive_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索路径或文件名…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(280)
        self.search_edit.textChanged.connect(self.filter_results)
        actions.addWidget(self.search_edit)
        self.hide_extension = QCheckBox("隐藏扩展名")
        self.hide_extension.toggled.connect(self.model.set_hide_extension)
        actions.addWidget(self.hide_extension)
        content_layout.addLayout(actions)

        result_card = QFrame(objectName="card")
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(1, 1, 1, 1)
        result_layout.setSpacing(0)
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 10, 14, 10)
        toolbar_layout.setSpacing(7)
        self.result_title = QLabel("扫描结果", objectName="sectionTitle")
        self.visible_count = QLabel("0 个文件", objectName="muted")
        toolbar_layout.addWidget(self.result_title)
        toolbar_layout.addWidget(self.visible_count)
        toolbar_layout.addStretch()
        for button in (
            self._button("复制文件名", self.copy_names),
            self._button("复制完整路径", self.copy_paths),
            self._button("导出 TXT", self.export_txt),
            self._button("导出 CSV", self.export_csv),
        ):
            toolbar_layout.addWidget(button)
        self.clear_button = self._button("清空", self.clear_results, "danger")
        toolbar_layout.addWidget(self.clear_button)
        result_layout.addWidget(toolbar)

        self.result_stack = QStackedWidget()
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.addStretch()
        empty_icon = QLabel("◎")
        empty_icon.setObjectName("emptyIcon")
        empty_icon.setFont(QFont("Microsoft YaHei UI", 32))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setFixedSize(68, 68)
        empty_title = QLabel("尚无扫描结果")
        empty_title.setObjectName("sectionTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint = QLabel("选择目标目录，然后开始扫描", objectName="muted")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_row = QHBoxLayout()
        empty_row.addStretch()
        empty_row.addWidget(empty_icon)
        empty_row.addStretch()
        empty_layout.addLayout(empty_row)
        empty_layout.addWidget(empty_title)
        empty_layout.addSpacing(6)
        empty_layout.addWidget(empty_hint)
        empty_layout.addStretch()

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header_view.resizeSection(1, 280)
        self.table.doubleClicked.connect(self.open_location)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.result_stack.addWidget(empty)
        self.result_stack.addWidget(self.table)
        result_layout.addWidget(self.result_stack, 1)
        content_layout.addWidget(result_card, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel("就绪", objectName="muted")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.progress.hide()
        author = QLabel(AUTHOR_TEXT, objectName="author")
        footer.addWidget(self.status_label)
        footer.addWidget(self.progress, 1)
        footer.addWidget(author)
        content_layout.addLayout(footer)
        root_layout.addWidget(content, 1)
        self.statusBar().hide()

    def _create_shortcuts(self) -> None:
        copy_action = QAction(self)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self.copy_paths)
        self.addAction(copy_action)
        focus_search = QAction(self)
        focus_search.setShortcut(QKeySequence.StandardKey.Find)
        focus_search.triggered.connect(self.search_edit.setFocus)
        self.addAction(focus_search)

    def _restore_settings(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        previous_path = self.settings.value("lastPath", "", str)
        if previous_path and os.path.isdir(previous_path):
            self.path_edit.setText(previous_path)

    @Slot()
    def toggle_theme(self) -> None:
        self.dark_mode = not self.dark_mode
        self._apply_theme()

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(DARK_STYLE if self.dark_mode else LIGHT_STYLE)
            if self.dark_mode:
                app.setPalette(dark_palette())
            else:
                app.setPalette(app.style().standardPalette())
        self.theme_button.setText("☀" if self.dark_mode else "☾")

    def check_update_manual(self) -> None:
        """菜单/按钮触发的手动检查（无更新也会给提示）。"""
        self.check_for_updates(manual=True)

    def check_for_updates(self, manual: bool = False) -> None:
        """在后台线程检查 GitHub 最新版本。"""
        if self.update_thread is not None and self.update_thread.isRunning():
            return
        self._update_manual = manual
        thread = QThread(self)
        worker = UpdateChecker(GITHUB_REPO, APP_VERSION)
        worker.moveToThread(thread)
        queued = Qt.ConnectionType.QueuedConnection
        thread.started.connect(worker.run, queued)
        # 必须用 QueuedConnection 回主线程：否则 _on_update_result 会在子线程里弹窗，
        # 重蹈之前跨线程操作 GUI 崩溃的覆辙。信号直接连主窗口自己的方法，不用 lambda 传参。
        worker.finished.connect(self._on_update_result, queued)
        worker.finished.connect(thread.quit, queued)
        worker.finished.connect(worker.deleteLater, queued)
        thread.finished.connect(thread.deleteLater, queued)
        self.update_thread = thread
        self.update_worker = worker
        thread.start()

    @Slot(object)
    def _on_update_result(self, info: UpdateInfo) -> None:
        manual = self._update_manual
        self.settings.setValue(
            "lastUpdateCheck", QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate)
        )
        if info.error:
            if manual:
                QMessageBox.warning(
                    self, "检查更新失败", f"无法连接更新服务器：\n{info.error}"
                )
            return
        if info.has_update:
            body = info.body or "（未提供更新说明）"
            message = QMessageBox(self)
            message.setWindowTitle(f"发现新版本 v{info.latest}")
            message.setIcon(QMessageBox.Icon.Information)
            message.setText(
                f"当前版本 v{info.current}，已有新版本 v{info.latest} 可用。"
            )
            message.setInformativeText("是否前往 GitHub 下载最新版本？")
            message.setDetailedText(body)
            message.setStandardButtons(
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
            )
            message.button(QMessageBox.StandardButton.Ok).setText("前往下载")
            message.button(QMessageBox.StandardButton.Cancel).setText("稍后")
            if (
                message.exec() == QMessageBox.StandardButton.Ok
                and info.html_url
            ):
                QDesktopServices.openUrl(QUrl(info.html_url))
        elif manual:
            QMessageBox.information(
                self, "已是最新", f"当前已是最新版本 v{info.current}。"
            )

    @Slot()
    def browse_directory(self) -> None:
        start = self.path_edit.text().strip() or os.getcwd()
        selected = QFileDialog.getExistingDirectory(self, "选择目标目录", start)
        if selected:
            self.path_edit.setText(os.path.normpath(selected))
            self._set_status("已选择目录，可以开始扫描")

    def start_scan(self, recursive: bool) -> None:
        if self.is_scanning:
            return
        try:
            target_path = normalize_directory(self.path_edit.text())
        except (ValueError, NotADirectoryError) as error:
            QMessageBox.warning(self, "目录无效", str(error))
            self.path_edit.setFocus()
            return

        self.clear_results(update_status=False)
        self.path_edit.setText(target_path)
        self.cancel_event.clear()
        self.is_scanning = True
        self._set_scanning_controls(True)
        self.progress.setRange(0, 0)
        self.progress.show()
        scan_name = "递归扫描" if recursive else "当前目录扫描"
        self._set_status(f"正在进行{scan_name}…")
        self.visible_count.setText("正在扫描…")
        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION} - 正在扫描…")

        thread = QThread(self)
        worker = ScanWorker(target_path, recursive, self.cancel_event)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # 跨线程信号必须显式指定 QueuedConnection：PySide6 自动推断连接类型时，
        # 对“lambda”或“子类覆盖基类 @Slot 方法”等情况会退化成直接连接，
        # 导致槽函数在子线程里操作 GUI，触发访问违例崩溃。
        # 同时槽函数只连接主窗口自己的方法，不再用 lambda 传参。
        queued = Qt.ConnectionType.QueuedConnection
        worker.progress.connect(self._scan_progress, queued)
        worker.completed.connect(self._scan_completed, queued)
        worker.failed.connect(self._scan_failed, queued)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._release_scan_objects)
        self.scan_name = scan_name
        self.scan_thread = thread
        self.scan_worker = worker
        thread.start()

    @Slot(int)
    def _scan_progress(self, count: int) -> None:
        self.visible_count.setText(f"已发现 {count:,} 个")
        self._set_status(f"正在扫描… 已发现 {count:,} 个文件")

    @Slot(object)
    def _scan_completed(self, result: ScanResult) -> None:
        self.model.set_records(result.records)
        self.result_stack.setCurrentIndex(1 if result.records else 0)
        self.is_scanning = False
        self._set_scanning_controls(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.hide()
        self._update_visible_count()
        count = len(result.records)
        scan_name = self.scan_name
        if result.cancelled:
            message = f"扫描已停止，保留已找到的 {count:,} 个文件"
        else:
            message = f"{scan_name}完成，共找到 {count:,} 个文件"
        if result.skipped:
            message += f"，跳过 {result.skipped:,} 个无法访问的项目"
        self._set_status(message)
        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION}  QQ:6938070 - {count:,} 个文件")

    @Slot(str)
    def _scan_failed(self, message: str) -> None:
        self.is_scanning = False
        self._set_scanning_controls(False)
        self.progress.hide()
        self._set_status("扫描失败")
        QMessageBox.critical(self, "扫描错误", message)

    @Slot()
    def _release_scan_objects(self) -> None:
        self.scan_thread = None
        self.scan_worker = None
        if self.close_after_scan:
            self.close_after_scan = False
            self.close()

    @Slot()
    def cancel_scan(self) -> None:
        if not self.is_scanning:
            return
        self.cancel_event.set()
        self.cancel_button.setEnabled(False)
        self._set_status("正在停止扫描，请稍候…")

    def _set_scanning_controls(self, scanning: bool) -> None:
        self.current_button.setEnabled(not scanning)
        self.recursive_button.setEnabled(not scanning)
        self.browse_button.setEnabled(not scanning)
        self.path_edit.setEnabled(not scanning)
        self.cancel_button.setEnabled(scanning)

    @Slot(str)
    def filter_results(self, text: str) -> None:
        expression = QRegularExpression(QRegularExpression.escape(text.strip()))
        expression.setPatternOptions(QRegularExpression.PatternOption.CaseInsensitiveOption)
        self.proxy.setFilterRegularExpression(expression)
        self._update_visible_count()

    def _update_visible_count(self) -> None:
        shown = self.proxy.rowCount()
        total = self.model.rowCount()
        if self.search_edit.text().strip() and shown != total:
            self.visible_count.setText(f"显示 {shown:,} / {total:,} 个文件")
        else:
            self.visible_count.setText(f"{total:,} 个文件")

    def _selection_changed(self) -> None:
        selected = len(self.table.selectionModel().selectedRows())
        if selected:
            self._set_status(f"已选择 {selected:,} 个文件")

    def _selected_source_rows(self) -> list[int]:
        selected = self.table.selectionModel().selectedRows()
        if selected:
            return sorted({self.proxy.mapToSource(index).row() for index in selected})
        return [self.proxy.mapToSource(self.proxy.index(row, 0)).row() for row in range(self.proxy.rowCount())]

    def _selected_records(self) -> list[FileRecord]:
        return [self.model.records[row] for row in self._selected_source_rows()]

    def _copy(self, values: list[str], label: str) -> None:
        if not values:
            self._set_status(f"没有可复制的{label}")
            return
        QApplication.clipboard().setText("\n".join(values))
        self._set_status(f"已复制 {len(values):,} 个{label}")

    @Slot()
    def copy_names(self) -> None:
        values = [item.display_name(self.hide_extension.isChecked()) for item in self._selected_records()]
        self._copy(values, "文件名")

    @Slot()
    def copy_paths(self) -> None:
        self._copy([item.full_path for item in self._selected_records()], "完整路径")

    @Slot(QModelIndex)
    def open_location(self, proxy_index: QModelIndex) -> None:
        source_index = self.proxy.mapToSource(proxy_index)
        if not source_index.isValid():
            return
        path = self.model.records[source_index.row()].full_path
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
            self._set_status("已打开文件所在目录")
        except OSError as error:
            QMessageBox.critical(self, "打开失败", str(error))

    def _save_path(self, title: str, suffix: str) -> str:
        default_name = suggested_export_name(self.path_edit.text(), suffix)
        default_path = os.path.join(self.path_edit.text(), default_name)
        file_filter = "文本文件 (*.txt)" if suffix == "txt" else "CSV 文件 (*.csv)"
        path, _ = QFileDialog.getSaveFileName(self, title, default_path, file_filter)
        return path

    @Slot()
    def export_txt(self) -> None:
        records = self._selected_records()
        if not records:
            QMessageBox.information(self, "提示", "当前没有可导出的扫描结果。")
            return
        path = self._save_path("导出 TXT 文件", "txt")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as output:
                for record in records:
                    output.write(record.display_name(self.hide_extension.isChecked()) + "\n")
            self._set_status(f"已导出 {len(records):,} 条记录到 {path}")
        except OSError as error:
            QMessageBox.critical(self, "导出失败", str(error))

    @Slot()
    def export_csv(self) -> None:
        records = self._selected_records()
        if not records:
            QMessageBox.information(self, "提示", "当前没有可导出的扫描结果。")
            return
        path = self._save_path("导出 CSV 文件", "csv")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(["完整路径", "文件名"])
                writer.writerows(
                    (record.full_path, record.display_name(self.hide_extension.isChecked()))
                    for record in records
                )
            self._set_status(f"已导出 {len(records):,} 条记录到 {path}")
        except OSError as error:
            QMessageBox.critical(self, "导出失败", str(error))

    def clear_results(self, update_status: bool = True) -> None:
        if self.is_scanning:
            return
        self.search_edit.clear()
        self.model.clear()
        self.result_stack.setCurrentIndex(0)
        self._update_visible_count()
        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION}  QQ:6938070")
        if update_status:
            self._set_status("已清空扫描结果")

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile() and os.path.isdir(urls[0].toLocalFile()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        folder = event.mimeData().urls()[0].toLocalFile()
        self.path_edit.setText(os.path.normpath(folder))
        self._set_status("已接收拖放目录，可以开始扫描")
        event.acceptProposedAction()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.is_scanning:
            answer = QMessageBox.question(
                self,
                "确认退出",
                "当前正在扫描目录，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.cancel_event.set()
            self.close_after_scan = True
            self._set_scanning_controls(True)
            self.cancel_button.setEnabled(False)
            self._set_status("正在安全结束扫描，完成后将自动退出…")
            event.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("lastPath", self.path_edit.text())
        self.settings.setValue("darkMode", self.dark_mode)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName("hkcoo")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

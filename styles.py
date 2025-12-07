###############################################################################
# СТИЛИ VS Code Dark+
###############################################################################
class Styles:
    def __init__(self):
        # VS Code Dark+ точные цвета
        # Editor background: #1e1e1e
        # Sidebar background: #252526
        # Activity bar: #333333
        # Borders: #474747
        # Text: #cccccc / #d4d4d4
        # Accent: #007acc / #0e639c
        # Selection: #264f78
        # Hover: #2a2d2e
        # Input background: #3c3c3c

        self.dark_qss = """
        /* Основной виджет */
        QWidget { 
            background: #252526; 
            color: #cccccc; 
            font-family: 'Segoe UI', sans-serif; 
            font-size: 13px; 
        }

        /* Кнопки */
        QPushButton { 
            background: #0e639c;
            color: #ffffff; 
            border: 1px solid #1177bb; 
            padding: 6px 14px; 
            font-weight: normal; 
            font-size: 13px;
            min-height: 20px;
        }
        QPushButton:hover { 
            background: #1177bb;
            border: 1px solid #1177bb;
        }
        QPushButton:pressed { 
            background: #0d5689;
            border: 1px solid #0d5689;
        }
        QPushButton:disabled {
            background: #3c3c3c;
            color: #808080;
            border: 1px solid #474747;
        }

        /* Метки */
        QLabel { 
            color: #cccccc; 
            font-size: 13px; 
            background: transparent;
            border: none;
        }

        /* Поля ввода */
        QTextEdit, QPlainTextEdit { 
            background: #1e1e1e; 
            color: #d4d4d4; 
            border: 1px solid #474747; 
            padding: 6px; 
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 13px; 
            selection-background-color: #264f78;
            selection-color: #ffffff;
        }
        QTextEdit:focus, QPlainTextEdit:focus { 
            border: 1px solid #007acc; 
        }

        QLineEdit {
            background: #3c3c3c; 
            color: #cccccc; 
            border: 1px solid #474747; 
            padding: 4px 8px; 
            font-size: 13px; 
            selection-background-color: #264f78;
            selection-color: #ffffff;
        }
        QLineEdit:focus { 
            border: 1px solid #007acc;
            background: #3c3c3c;
        }

        /* Выпадающие списки */
        QComboBox { 
            background: #3c3c3c; 
            color: #cccccc; 
            border: 1px solid #474747; 
            padding: 4px 8px; 
            padding-right: 28px;
            font-size: 13px;
            min-height: 20px;
        }
        QComboBox:hover {
            border: 1px solid #007acc;
        }
        QComboBox:focus {
            border: 1px solid #007acc;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: 1px solid #474747;
            background: #3c3c3c;
        }
        QComboBox::drop-down:hover {
            background: #505050;
        }
        QComboBox::down-arrow {
            width: 0;
            height: 0;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid #cccccc;
        }
        QComboBox QAbstractItemView {
            background: #252526;
            border: 1px solid #474747;
            selection-background-color: #094771;
            selection-color: #ffffff;
            outline: none;
            padding: 2px;
        }
        QComboBox QAbstractItemView::item {
            padding: 4px 8px;
            min-height: 22px;
        }
        QComboBox QAbstractItemView::item:hover {
            background: #2a2d2e;
        }

        /* Счетчики */
        QSpinBox { 
            background: #3c3c3c; 
            color: #cccccc; 
            border: 1px solid #474747;
            padding: 4px 8px;
            padding-right: 20px;
            font-size: 13px;
            min-height: 20px;
        }
        QSpinBox:focus {
            border: 1px solid #007acc;
        }
        QSpinBox::up-button {
            subcontrol-origin: border;
            subcontrol-position: top right;
            background: #3c3c3c;
            border-left: 1px solid #474747;
            border-bottom: 1px solid #474747;
            width: 18px;
        }
        QSpinBox::down-button {
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            background: #3c3c3c;
            border-left: 1px solid #474747;
            width: 18px;
        }
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {
            background: #505050;
        }
        QSpinBox::up-arrow {
            width: 0;
            height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-bottom: 4px solid #cccccc;
        }
        QSpinBox::down-arrow {
            width: 0;
            height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 4px solid #cccccc;
        }

        /* Чекбоксы */
        QCheckBox { 
            color: #cccccc; 
            font-size: 13px;
            spacing: 8px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #6b6b6b;
            background: transparent;
        }
        QCheckBox::indicator:hover {
            border: 1px solid #007acc;
        }
        QCheckBox::indicator:checked {
            background: #007acc;
            border: 1px solid #007acc;
        }
        QCheckBox::indicator:checked:hover {
            background: #1177bb;
            border: 1px solid #1177bb;
        }

        /* Чекбоксы внутри таблиц QTableWidget и QTableView */
        QTableWidget::indicator, QTableView::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #6b6b6b;
            background: transparent;
        }
        QTableWidget::indicator:hover, QTableView::indicator:hover {
            border: 1px solid #007acc;
        }
        QTableWidget::indicator:checked, QTableView::indicator:checked {
            background: #007acc;
            border: 1px solid #007acc;
        }
        QTableWidget::indicator:checked:hover, QTableView::indicator:checked:hover {
            background: #1177bb;
            border: 1px solid #1177bb;
        }
        
        
        
        QTableWidget::indicator:checked:hover {
            background: #1177bb;
            border: 1px solid #1177bb;
        }

        /* Таблицы */
        QTableWidget, QTableView {
            background: #1e1e1e;
            color: #cccccc;
            border: 1px solid #474747;
            gridline-color: #474747;
            selection-background-color: #094771;
            selection-color: #ffffff;
            alternate-background-color: #252526;
        }
        QTableWidget::item, QTableView::item {
            padding: 4px 8px;
            border-bottom: 1px solid #2d2d2d;
        }
        QTableWidget::item:selected, QTableView::item:selected {
            background: #094771;
        }
        QTableWidget::item:hover, QTableView::item:hover {
            background: #2a2d2e;
        }

        /* Списки */
        QListWidget, QListView { 
            background: #1e1e1e; 
            color: #cccccc; 
            border: 1px solid #474747;
            font-size: 13px;
            outline: none;
        }
        QListWidget::item, QListView::item {
            padding: 6px 8px;
            border-bottom: 1px solid #2d2d2d;
        }
        QListWidget::item:selected, QListView::item:selected {
            background: #094771;
            color: #ffffff;
        }
        QListWidget::item:hover, QListView::item:hover {
            background: #2a2d2e;
        }

        /* Заголовки таблиц */
        QHeaderView::section { 
            background: #252526; 
            color: #cccccc; 
            font-weight: normal; 
            border: none;
            border-right: 1px solid #474747;
            border-bottom: 1px solid #474747;
            font-size: 13px; 
            padding: 6px 8px;
        }
        QHeaderView::section:hover {
            background: #2a2d2e;
        }

        /* Группы */
        QGroupBox { 
            border: 1px solid #474747; 
            margin-top: 10px; 
            font-size: 13px;
            padding-top: 14px;
        }
        QGroupBox::title { 
            subcontrol-origin: margin; 
            subcontrol-position: top left; 
            padding: 2px 8px; 
            color: #cccccc; 
            background: #252526;
        }

        /* Вертикальный скроллбар */
        QScrollBar:vertical { 
            background: #1e1e1e; 
            width: 14px; 
            margin: 0;
            border: none;
        }
        QScrollBar::handle:vertical { 
            background: #5a5a5a; 
            min-height: 30px; 
            margin: 0 3px;
        }
        QScrollBar::handle:vertical:hover { 
            background: #787878;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { 
            background: none; 
            height: 0;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }

        /* Горизонтальный скроллбар */
        QScrollBar:horizontal { 
            background: #1e1e1e; 
            height: 14px; 
            margin: 0;
            border: none;
        }
        QScrollBar::handle:horizontal { 
            background: #5a5a5a; 
            min-width: 30px; 
            margin: 3px 0;
        }
        QScrollBar::handle:horizontal:hover { 
            background: #787878;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { 
            background: none; 
            width: 0;
        }
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
            background: none;
        }

        /* Вкладки */
        QTabWidget::pane {
            border: 1px solid #474747;
            background: #1e1e1e;
            top: -1px;
        }
        QTabBar::tab {
            background: #2d2d2d;
            color: #969696;
            padding: 8px 16px;
            border: 1px solid #474747;
            border-bottom: none;
            margin-right: -1px;
        }
        QTabBar::tab:selected {
            background: #1e1e1e;
            color: #ffffff;
            border-top: 1px solid #007acc;
        }
        QTabBar::tab:hover:!selected {
            background: #383838;
            color: #cccccc;
        }

        /* Подсказки */
        QToolTip {
            background: #252526;
            color: #cccccc;
            border: 1px solid #474747;
            padding: 4px 8px;
            font-size: 12px;
        }

        /* Прогресс-бар */
        QProgressBar {
            background: #3c3c3c;
            border: 1px solid #474747;
            text-align: center;
            color: #cccccc;
            height: 18px;
        }
        QProgressBar::chunk {
            background: #007acc;
        }

        /* Меню */
        QMenuBar {
            background: #333333;
            color: #cccccc;
            border-bottom: 1px solid #474747;
        }
        QMenuBar::item {
            padding: 4px 10px;
            background: transparent;
        }
        QMenuBar::item:selected {
            background: #094771;
        }
        QMenu {
            background: #252526;
            color: #cccccc;
            border: 1px solid #474747;
        }
        QMenu::item {
            padding: 6px 30px 6px 20px;
        }
        QMenu::item:selected {
            background: #094771;
        }
        QMenu::separator {
            height: 1px;
            background: #474747;
            margin: 4px 10px;
        }

        /* Statusbar */
        QStatusBar {
            background: #007acc;
            color: #ffffff;
            border: none;
        }
        QStatusBar::item {
            border: none;
        }

        /* Splitter */
        QSplitter::handle {
            background: #474747;
        }
        QSplitter::handle:horizontal {
            width: 1px;
        }
        QSplitter::handle:vertical {
            height: 1px;
        }

        /* Tree View */
        QTreeView, QTreeWidget {
            background: #252526;
            color: #cccccc;
            border: 1px solid #474747;
            outline: none;
        }
        QTreeView::item, QTreeWidget::item {
            padding: 4px 0;
        }
        QTreeView::item:selected, QTreeWidget::item:selected {
            background: #094771;
        }
        QTreeView::item:hover, QTreeWidget::item:hover {
            background: #2a2d2e;
        }
        QTreeView::branch:has-children:closed {
            image: none;
            border-image: none;
        }
        QTreeView::branch:has-children:open {
            image: none;
            border-image: none;
        }

        /* Dialog buttons */
        QDialogButtonBox QPushButton {
            min-width: 80px;
        }

        /* Message Box */
        QMessageBox {
            background: #252526;
        }
        QMessageBox QLabel {
            color: #cccccc;
        }
        """

        # Светлая тема (VS Code Light+)
        self.light_qss = """
        QWidget { 
            background: #f3f3f3; 
            color: #333333; 
            font-family: 'Segoe UI', sans-serif; 
            font-size: 13px; 
        }

        QPushButton { 
            background: #007acc;
            color: #ffffff; 
            border: 1px solid #006bb3; 
            padding: 6px 14px;
        }
        QPushButton:hover { 
            background: #0062a3;
        }
        QPushButton:pressed { 
            background: #005491;
        }
        QPushButton:disabled {
            background: #cccccc;
            color: #888888;
            border: 1px solid #bbbbbb;
        }

        QLabel { 
            color: #333333; 
            background: transparent;
        }

        QTextEdit, QPlainTextEdit { 
            background: #ffffff; 
            color: #333333; 
            border: 1px solid #cecece; 
            padding: 6px;
            selection-background-color: #add6ff;
        }
        QTextEdit:focus, QPlainTextEdit:focus { 
            border: 1px solid #007acc; 
        }

        QLineEdit {
            background: #ffffff; 
            color: #333333; 
            border: 1px solid #cecece; 
            padding: 4px 8px;
        }
        QLineEdit:focus { 
            border: 1px solid #007acc;
        }

        QComboBox { 
            background: #ffffff; 
            color: #333333; 
            border: 1px solid #cecece; 
            padding: 4px 8px;
        }
        QComboBox:hover, QComboBox:focus {
            border: 1px solid #007acc;
        }
        QComboBox::drop-down {
            border-left: 1px solid #cecece;
            background: #ffffff;
            width: 24px;
        }
        QComboBox::down-arrow {
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid #333333;
        }
        QComboBox QAbstractItemView {
            background: #ffffff;
            border: 1px solid #cecece;
            selection-background-color: #0060c0;
            selection-color: #ffffff;
        }

        QSpinBox { 
            background: #ffffff; 
            color: #333333; 
            border: 1px solid #cecece;
            padding: 4px 8px;
        }
        QSpinBox:focus {
            border: 1px solid #007acc;
        }
        QSpinBox::up-button, QSpinBox::down-button {
            background: #ffffff;
            border-left: 1px solid #cecece;
        }
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {
            background: #e8e8e8;
        }

        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #919191;
            background: #ffffff;
        }
        QCheckBox::indicator:hover {
            border: 1px solid #007acc;
        }
        QCheckBox::indicator:checked {
            background: #007acc;
            border: 1px solid #007acc;
        }

        QTableWidget, QTableView {
            background: #ffffff;
            color: #333333;
            border: 1px solid #cecece;
            gridline-color: #e5e5e5;
            selection-background-color: #0060c0;
            selection-color: #ffffff;
        }

        QListWidget, QListView { 
            background: #ffffff; 
            color: #333333; 
            border: 1px solid #cecece;
        }
        QListWidget::item:selected {
            background: #0060c0;
            color: #ffffff;
        }
        QListWidget::item:hover {
            background: #e8e8e8;
        }

        QHeaderView::section { 
            background: #f3f3f3; 
            color: #333333; 
            border: none;
            border-right: 1px solid #cecece;
            border-bottom: 1px solid #cecece;
            padding: 6px 8px;
        }

        QGroupBox { 
            border: 1px solid #cecece;
            margin-top: 10px;
            padding-top: 14px;
        }
        QGroupBox::title { 
            color: #333333;
            background: #f3f3f3;
            padding: 2px 8px;
        }

        QScrollBar:vertical { 
            background: #f3f3f3; 
            width: 14px;
        }
        QScrollBar::handle:vertical { 
            background: #c1c1c1; 
            min-height: 30px;
            margin: 0 3px;
        }
        QScrollBar::handle:vertical:hover { 
            background: #929292;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { 
            height: 0;
        }

        QScrollBar:horizontal { 
            background: #f3f3f3; 
            height: 14px;
        }
        QScrollBar::handle:horizontal { 
            background: #c1c1c1; 
            min-width: 30px;
            margin: 3px 0;
        }
        QScrollBar::handle:horizontal:hover { 
            background: #929292;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { 
            width: 0;
        }

        QTabWidget::pane {
            border: 1px solid #cecece;
            background: #ffffff;
        }
        QTabBar::tab {
            background: #ececec;
            color: #333333;
            padding: 8px 16px;
            border: 1px solid #cecece;
            border-bottom: none;
        }
        QTabBar::tab:selected {
            background: #ffffff;
            border-top: 1px solid #007acc;
        }
        QTabBar::tab:hover:!selected {
            background: #e0e0e0;
        }

        QToolTip {
            background: #f3f3f3;
            color: #333333;
            border: 1px solid #cecece;
            padding: 4px 8px;
        }

        QProgressBar {
            background: #e4e4e4;
            border: 1px solid #cecece;
            text-align: center;
        }
        QProgressBar::chunk {
            background: #007acc;
        }

        QMenuBar {
            background: #f3f3f3;
            color: #333333;
            border-bottom: 1px solid #cecece;
        }
        QMenuBar::item:selected {
            background: #0060c0;
            color: #ffffff;
        }
        QMenu {
            background: #f3f3f3;
            color: #333333;
            border: 1px solid #cecece;
        }
        QMenu::item:selected {
            background: #0060c0;
            color: #ffffff;
        }
        QMenu::separator {
            height: 1px;
            background: #cecece;
            margin: 4px 10px;
        }

        QStatusBar {
            background: #007acc;
            color: #ffffff;
        }

        QTreeView, QTreeWidget {
            background: #ffffff;
            color: #333333;
            border: 1px solid #cecece;
        }
        QTreeView::item:selected {
            background: #0060c0;
            color: #ffffff;
        }
        QTreeView::item:hover {
            background: #e8e8e8;
        }

        QMessageBox {
            background: #f3f3f3;
        }
        """

    def get_light(self) -> str:
        return self.light_qss

    def get_dark(self) -> str:
        return self.dark_qss
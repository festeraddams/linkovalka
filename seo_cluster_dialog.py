"""
seo_cluster_dialog.py — GUI диалог для SEO кластерной перелинковки

Интегрируется в main.py как замена/дополнение к существующей перелинковке.

Использование в main.py:
```python
from seo_cluster_dialog import SEOClusterDialog

# В методе on_cluster_linking:
dialog = SEOClusterDialog(self.generator.directory, parent=self)
dialog.exec()
```
"""

import os
import random
from urllib.parse import urlparse
from typing import Dict, List, Optional, Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QGroupBox, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QMessageBox, QTabWidget, QWidget, QSplitter, QFrame,
    QAbstractItemView, QFileDialog
)
from PyQt6.QtGui import QColor, QFont

# Импортируем основной модуль
from seo_cluster_linker import (
    SEOClusterLinker, AnchorMorpher, CoverageAnalyzer,
    Cluster, Link, Page, LinkInserter
)
from graph_dialog import GraphDialog


# Импортируем стили
from styles import Styles

from seo_visual_editor import VisualEditorWidget

# Импортируем словарь ключевых слов
try:
    from pills import KEYWORDS
except ImportError:
    KEYWORDS = {}


# ═══════════════════════════════════════════════════════════════════════════════
# WORKER THREADS
# ═══════════════════════════════════════════════════════════════════════════════
class ScanWorker(QThread):
    """Поток для сканирования директории."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, linker: SEOClusterLinker):
        super().__init__()
        self.linker = linker

    def run(self):
        try:
            self.progress.emit("Сканирование директории...")
            clusters = self.linker.build_clusters()
            self.finished.emit(clusters)
        except Exception as e:
            self.error.emit(str(e))


class LinkWorker(QThread):
    """Поток для вставки ссылок (без пересоздания)."""
    progress = pyqtSignal(str)
    link_created = pyqtSignal(str, str, str)  # source, target, anchor
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, linker: SEOClusterLinker, use_existing: bool = True):
        super().__init__()
        self.linker = linker
        self.use_existing = use_existing

    def run(self):
        try:
            # Используем УЖЕ СУЩЕСТВУЮЩИЕ ссылки из all_links
            links = getattr(self.linker, "all_links", [])

            if not links:
                self.error.emit("Нет ссылок для вставки. Сначала нажмите 'Предпросмотр'.")
                return

            self.progress.emit(f"Вставка {len(links)} ссылок...")

            # Отправляем информацию о каждой ссылке
            for link in links:
                self.link_created.emit(
                    link.source.domain,
                    link.target.domain,
                    link.anchor[:50]
                )

            # Вставляем ссылки
            self.progress.emit("Вставка ссылок в HTML...")
            stats = self.linker.insert_all_links()

            self.finished.emit(stats)

        except Exception as e:
            self.error.emit(str(e))

class LinkingExamplesDialog(QDialog):
    """Диалог с наглядными примерами схем перелинковки."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📊 Примеры схем перелинковки")
        self.setMinimumSize(950, 750)
        self._init_ui()
        self._apply_styles()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        header = QLabel("🔗 Схемы перелинковки PBN")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #61afef;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        tabs = QTabWidget()
        tabs.addTab(self._create_cluster_tab(), "🔷 Кластерная")
        tabs.addTab(self._create_pyramid_tab(), "🔺 Пирамидальная")
        tabs.addTab(self._create_mesh_tab(), "🔶 Сетевая")
        tabs.addTab(self._create_hub_spoke_tab(), "⭐ Hub & Spoke")
        layout.addWidget(tabs)

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _create_cluster_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        scheme = QTextEdit()
        scheme.setReadOnly(True)
        scheme.setFont(QFont("Consolas", 10))
        scheme.setPlainText("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    КЛАСТЕРНАЯ СХЕМА (рекомендуется для PBN)                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║   ПРИНЦИП: Равномерное распределение ссылочного веса между всеми страницами  ║
║                                                                              ║
║   ┌─────────────┐       ┌─────────────┐       ┌─────────────┐               ║
║   │   ДОМЕН A   │       │   ДОМЕН B   │       │   ДОМЕН C   │               ║
║   │ ┌─────────┐ │       │ ┌─────────┐ │       │ ┌─────────┐ │               ║
║   │ │ Page 1  │◄├───────┼►│ Page 1  │◄├───────┼►│ Page 1  │ │               ║
║   │ │    ↕    │ │       │ │    ↕    │ │       │ │    ↕    │ │               ║
║   │ │ Page 2  │◄├───────┼►│ Page 2  │◄├───────┼►│ Page 2  │ │               ║
║   │ └─────────┘ │       │ └─────────┘ │       │ └─────────┘ │               ║
║   └──────┬──────┘       └──────┬──────┘       └──────┬──────┘               ║
║          │                     │                     │                       ║
║          └─────────────────────┴─────────────────────┘                       ║
║                         Cross-site связи                                     ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ✅ ВНУТРЕННЯЯ: Все страницы домена связаны между собой (A↔B)               ║
║  ✅ CROSS-SITE: Каждая страница получает N входящих с ДРУГИХ доменов         ║
║  ✅ БАЛАНСИРОВКА: Приоритет страницам с минимумом входящих ссылок            ║
║  ✅ ОХВАТ 100%: Гарантия что все страницы получат ссылки                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  📋 РЕКОМЕНДУЕМЫЕ НАСТРОЙКИ:                                                 ║
║     • Cross-site ссылок: 2-3                                                 ║
║     • Мин. длина текста: 50-100 символов                                     ║
║     • Гарантировать охват: ВКЛ                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
        layout.addWidget(scheme)
        return widget

    def _create_pyramid_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        scheme = QTextEdit()
        scheme.setReadOnly(True)
        scheme.setFont(QFont("Consolas", 10))
        scheme.setPlainText("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    ПИРАМИДАЛЬНАЯ СХЕМА (концентрация веса)                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║   ПРИНЦИП: Передача ссылочного веса снизу вверх к топовым страницам          ║
║                                                                              ║
║                              ┌─────────┐                                     ║
║                              │  TOP 1  │  ◄── Level 1 (получает макс. вес)   ║
║                              └────┬────┘                                     ║
║                     ┌─────────────┼─────────────┐                            ║
║                     ▼             ▼             ▼                            ║
║                ┌─────────┐  ┌─────────┐  ┌─────────┐                         ║
║                │  MID 1  │  │  MID 2  │  │  MID 3  │  ◄── Level 2            ║
║                └────┬────┘  └────┬────┘  └────┬────┘                         ║
║          ┌──────────┼───────────┼───────────┼──────────┐                     ║
║          ▼          ▼           ▼           ▼          ▼                     ║
║     ┌─────────┐┌─────────┐┌─────────┐┌─────────┐┌─────────┐                  ║
║     │ BASE 1  ││ BASE 2  ││ BASE 3  ││ BASE 4  ││ BASE 5  │ ◄── Level 3     ║
║     └─────────┘└─────────┘└─────────┘└─────────┘└─────────┘                  ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  🔺 Level 3 (база) → ссылаются на Level 2                                    ║
║  🔺 Level 2 (середина) → ссылаются на Level 1                                ║
║  🔺 Level 1 (топ) → связаны между собой cross-site                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  📋 КОГДА ИСПОЛЬЗОВАТЬ:                                                      ║
║     • Когда есть "money pages" которые нужно продвигать                      ║
║     • Для концентрации PageRank на целевых страницах                         ║
║     • Топ-страницы определяются автоматически (первые в списке)              ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
        layout.addWidget(scheme)
        return widget

    def _create_mesh_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        scheme = QTextEdit()
        scheme.setReadOnly(True)
        scheme.setFont(QFont("Consolas", 10))
        scheme.setPlainText("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    СЕТЕВАЯ СХЕМА (mesh — все со всеми)                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║   ПРИНЦИП: Каждая страница ссылается на % других (с ограничением плотности)  ║
║                                                                              ║
║              density = 0.3 → каждая страница ссылается на 30% других         ║
║                                                                              ║
║        ┌──────────────────────────────────────────────────────┐              ║
║        │                                                      │              ║
║        │    ┌───────►┌───────►┌───────►┌─────────┐           │              ║
║        │    │        │        │        │         ▼           │              ║
║     ┌──┴──┐ │ ┌────┐ │ ┌────┐ │ ┌────┐ │ ┌────┐  ┌──┴──┐     │              ║
║     │ P1  │◄┴─│ P2 │◄┴─│ P3 │◄┴─│ P4 │◄┴─│ P5 │──│ P6  │     │              ║
║     └──┬──┘   └─┬──┘   └─┬──┘   └─┬──┘   └─┬──┘  └─────┘     │              ║
║        │        │        │        │        │                  │              ║
║        └────────┴────────┴────────┴────────┴──────────────────┘              ║
║                                                                              ║
║                    МАКСИМУМ 5 ссылок на страницу                             ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  🔶 Приоритет cross-site (сначала ссылки на другие домены)                   ║
║  🔶 Остаток добирается внутренними ссылками                                  ║
║  🔶 Жёсткий лимит: не более 5 исходящих на страницу                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  📋 КОГДА ИСПОЛЬЗОВАТЬ:                                                      ║
║     • Для максимального "склеивания" сети                                    ║
║     • Когда все страницы равнозначны по важности                             ║
║     ⚠️ Осторожно: может выглядеть неестественно для Google                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
        layout.addWidget(scheme)
        return widget

    def _create_hub_spoke_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        scheme = QTextEdit()
        scheme.setReadOnly(True)
        scheme.setFont(QFont("Consolas", 10))
        scheme.setPlainText("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    HUB & SPOKE (звёздная топология)                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║   ПРИНЦИП: Центральные хабы получают ссылки от всех сателлитов               ║
║                                                                              ║
║                         ┌───────────────────────────┐                        ║
║                         │    САТЕЛЛИТЫ (Spokes)     │                        ║
║                         │ ┌───┐ ┌───┐ ┌───┐ ┌───┐  │                        ║
║                         │ │S1 │ │S2 │ │S3 │ │S4 │  │                        ║
║                         │ └─┬─┘ └─┬─┘ └─┬─┘ └─┬─┘  │                        ║
║                         └───┼─────┼─────┼─────┼────┘                        ║
║                             │     │     │     │                              ║
║                             ▼     ▼     ▼     ▼                              ║
║                         ┌─────────────────────────┐                          ║
║                         │     ╔═══════════╗       │                          ║
║                         │     ║    HUB    ║       │  ◄── Центральная         ║
║                         │     ║  (домен)  ║       │      страница            ║
║                         │     ╚═════╤═════╝       │                          ║
║                         └───────────┼─────────────┘                          ║
║                                     │                                        ║
║                                     ▼ (25% обратных ссылок)                  ║
║                               S1, S3 (выборочно)                             ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ⭐ ВСЕ сателлиты ссылаются на хабы (только cross-site)                      ║
║  ⭐ Хабы отдают обратные ссылки на ~25% спутников                            ║
║  ⭐ Внутренняя перелинковка сохраняется                                      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ⚠️ ПРОБЛЕМА: Сейчас HUB выбирается АВТОМАТИЧЕСКИ                           ║
║     Берётся ПЕРВАЯ страница каждого домена (по алфавиту файлов).             ║
║     Ручной выбор HUB пока не реализован!                                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  📋 КОГДА ИСПОЛЬЗОВАТЬ:                                                      ║
║     • Для продвижения конкретных "денежных" страниц                          ║
║     • Когда есть явные лидеры в сети PBN                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
        layout.addWidget(scheme)
        return widget

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QTabWidget::pane {
                border: 1px solid #3c3c3c;
                background-color: #252526;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #d4d4d4;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #61afef;
                border-bottom: 2px solid #61afef;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #98c379;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 8px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 8px 24px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN DIALOG
# ═══════════════════════════════════════════════════════════════════════════════
class SEOClusterDialog(QDialog):
    """
    Главный диалог для SEO кластерной перелинковки.

    Возможности:
    - Сканирование директории и построение кластеров
    - Выбор схемы перелинковки
    - Настройка параметров
    - Предпросмотр ссылок
    - Генерация и вставка
    - Отчёт об охвате
    """

    SCHEMES = {
        'cluster': 'Кластерная (рекомендуется)',
        'pyramid': 'Пирамидальная',
        'mesh': 'Сетевая',
        'hub_spoke': 'Hub & Spoke',
    }

    def __init__(self, base_directory: str, parent=None):
        super().__init__(parent)
        self.base_dir = base_directory
        self.linker: Optional[SEOClusterLinker] = None
        self.clusters: Dict[str, Cluster] = {}

        self.setWindowTitle("🔗 SEO Кластерная Перелинковка")
        self.setMinimumSize(1400, 900)

        self._init_ui()
        self._apply_styles()

        # Автоматически начинаем сканирование
        if base_directory and os.path.isdir(base_directory):
            self._on_scan()

    def _init_ui(self):
        """Инициализация интерфейса."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # === Заголовок ===
        header = QLabel("🔗 SEO Кластерная Перелинковка")
        header.setObjectName("header")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header)

        # === Директория ===
        dir_layout = QHBoxLayout()
        self.dir_label = QLabel(f"📁 Директория: {self.base_dir}")
        dir_layout.addWidget(self.dir_label)
        dir_layout.addStretch()

        self.scan_btn = QPushButton("🔍 Сканировать")
        self.scan_btn.clicked.connect(self._on_scan)
        dir_layout.addWidget(self.scan_btn)
        main_layout.addLayout(dir_layout)

        # === Основной контент (вкладки) ===
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Вкладка 1: Кластеры
        self._create_clusters_tab()

        # Вкладка 2: Настройки
        self._create_settings_tab()

        # Вкладка 3: Превью ссылок
        self._create_preview_tab()

        # Вкладка 4: Отчёт
        self._create_report_tab()

        # Вкладка 5: Визуальный редактор
        self._create_visual_editor_tab()

        # === Прогресс ===
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # === Кнопки действий ===
        btn_layout = QHBoxLayout()

        self.preview_btn = QPushButton("👁 Предпросмотр")
        self.preview_btn.clicked.connect(self._on_preview)
        self.preview_btn.setEnabled(False)
        btn_layout.addWidget(self.preview_btn)

        btn_layout.addStretch()

        self.export_btn = QPushButton("📤 Экспорт JSON")
        self.export_btn.clicked.connect(self._on_export)
        self.export_btn.setEnabled(False)
        btn_layout.addWidget(self.export_btn)

        self.generate_btn = QPushButton("🚀 Генерировать и вставить ссылки")
        self.generate_btn.setObjectName("generate_btn")
        self.generate_btn.clicked.connect(self._on_generate)
        self.generate_btn.setEnabled(False)
        btn_layout.addWidget(self.generate_btn)

        main_layout.addLayout(btn_layout)

    def _create_clusters_tab(self):
        """Вкладка с информацией о кластерах."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Таблица кластеров
        self.clusters_table = QTableWidget()
        self.clusters_table.setColumnCount(5)
        self.clusters_table.setHorizontalHeaderLabels([
            "Препарат", "Страниц", "Доменов", "Синонимы", "Статус"
        ])
        self.clusters_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.clusters_table.horizontalHeader().setStretchLastSection(True)
        self.clusters_table.setColumnWidth(0, 150)
        self.clusters_table.setColumnWidth(1, 100)
        self.clusters_table.setColumnWidth(2, 100)
        self.clusters_table.setColumnWidth(3, 300)
        layout.addWidget(self.clusters_table)

        # Информация о выбранном кластере
        info_group = QGroupBox("Информация о кластере")
        info_layout = QVBoxLayout(info_group)

        self.cluster_info = QTextEdit()
        self.cluster_info.setReadOnly(True)
        self.cluster_info.setMaximumHeight(150)
        info_layout.addWidget(self.cluster_info)

        layout.addWidget(info_group)

        self.tabs.addTab(widget, "📊 Кластеры")

        # Обработчик выбора
        self.clusters_table.itemSelectionChanged.connect(self._on_cluster_selected)

    def _create_settings_tab(self):
        """Вкладка настроек."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Выбор кластера
        cluster_group = QGroupBox("Выбор кластера")
        cluster_layout = QHBoxLayout(cluster_group)

        cluster_layout.addWidget(QLabel("Препарат:"))
        self.topic_combo = QComboBox()
        self.topic_combo.setMinimumWidth(200)
        cluster_layout.addWidget(self.topic_combo)
        cluster_layout.addStretch()

        layout.addWidget(cluster_group)

        # Схема перелинковки
        scheme_group = QGroupBox("Схема перелинковки")
        scheme_layout = QVBoxLayout(scheme_group)

        scheme_row = QHBoxLayout()
        scheme_row.addWidget(QLabel("Схема:"))
        self.scheme_combo = QComboBox()
        for key, name in self.SCHEMES.items():
            self.scheme_combo.addItem(name, key)
        self.scheme_combo.setMinimumWidth(300)
        scheme_row.addWidget(self.scheme_combo)
        scheme_row.addStretch()
        scheme_layout.addLayout(scheme_row)

        # Описание схем
        scheme_desc = QLabel(
            "<b>Кластерная</b> — внутри сайта A↔B + между сайтами равномерно (рекомендуется для PBN)<br>"
            "<b>Пирамидальная</b> — концентрация веса на топ-страницах<br>"
            "<b>Сетевая</b> — все со всеми с ограничением плотности<br>"
            "<b>Hub & Spoke</b> — центральные хабы + сателлиты"
        )
        scheme_desc.setWordWrap(True)
        scheme_layout.addWidget(scheme_desc)

        # Кнопка примеров
        self.examples_btn = QPushButton("📊 Примеры перелинковки")
        self.examples_btn.setMaximumWidth(220)
        self.examples_btn.clicked.connect(self._show_linking_examples)
        scheme_layout.addWidget(self.examples_btn)

        layout.addWidget(scheme_group)

        # Параметры
        params_group = QGroupBox("Параметры")
        params_layout = QVBoxLayout(params_group)

        # Внешние ссылки
        ext_row = QHBoxLayout()
        ext_row.addWidget(QLabel("Cross-site ссылок на страницу:"))
        self.external_links_spin = QSpinBox()
        self.external_links_spin.setRange(1, 10)
        self.external_links_spin.setValue(2)
        ext_row.addWidget(self.external_links_spin)
        ext_row.addStretch()
        params_layout.addLayout(ext_row)

        ext_help = QLabel("Сколько входящих ссылок с других доменов получит каждая страница")
        ext_help.setStyleSheet("color: #999999; font-size: 10px;")
        ext_help.setWordWrap(True)
        params_layout.addWidget(ext_help)


        # Минимальная длина текста
        min_len_row = QHBoxLayout()
        min_len_row.addWidget(QLabel("Мин. длина текста для вставки:"))
        self.min_len_spin = QSpinBox()
        self.min_len_spin.setRange(20, 200)
        self.min_len_spin.setValue(50)
        min_len_row.addWidget(self.min_len_spin)
        min_len_row.addStretch()
        params_layout.addLayout(min_len_row)

        min_len_help = QLabel("Минимальное кол-во символов в блоке текста для вставки")
        min_len_help.setStyleSheet("color: #999999; font-size: 10px;")
        min_len_help.setWordWrap(True)
        params_layout.addWidget(min_len_help)


        # Опции
        self.ensure_coverage_cb = QCheckBox("Гарантировать полный охват (все страницы получат ссылки)")
        self.ensure_coverage_cb.setChecked(True)
        params_layout.addWidget(self.ensure_coverage_cb)

        layout.addWidget(params_group)
        layout.addStretch()

        self.tabs.addTab(widget, "⚙️ Настройки")

    def _on_open_visual_graph(self):
        """
        Открывает граф из Visual Linker в отдельном окне (GraphDialog).
        """
        if not hasattr(self, "visual_editor") or self.visual_editor is None:
            QMessageBox.warning(self, "Visual Linker", "Визуальный редактор не инициализирован")
            return

        nodes, edges = self.visual_editor.export_for_graph_dialog()
        if not nodes:
            QMessageBox.information(self, "Visual Linker", "Нет данных для отображения графа")
            return

        dlg = GraphDialog(nodes, edges, self)
        dlg.exec()

    def _create_preview_tab(self):
        """Вкладка предпросмотра ссылок."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Таблица ссылок - добавляем столбец Title
        self.links_table = QTableWidget()
        self.links_table.setColumnCount(6)
        self.links_table.setHorizontalHeaderLabels([
            "Источник (домен)", "Title источника", "Цель (домен)", "Тип", "Анкор", "Статус"
        ])
        self.links_table.horizontalHeader().setStretchLastSection(True)
        self.links_table.setColumnWidth(0, 180)
        self.links_table.setColumnWidth(1, 250)
        self.links_table.setColumnWidth(2, 180)
        self.links_table.setColumnWidth(3, 80)
        self.links_table.setColumnWidth(4, 280)

        # Делаем столбец "Анкор" редактируемым
        self.links_table.itemChanged.connect(self._on_anchor_edited)

        self.links_table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        layout.addWidget(self.links_table)

        # Кнопки управления анкорами
        btn_layout = QHBoxLayout()

        self.regenerate_anchors_btn = QPushButton("🔄 Пересобрать анкоры")
        self.regenerate_anchors_btn.clicked.connect(self._on_regenerate_anchors)
        btn_layout.addWidget(self.regenerate_anchors_btn)

        self.titles_to_anchors_btn = QPushButton("📋 Title → Анкор (internal)")
        self.titles_to_anchors_btn.clicked.connect(self._on_titles_to_anchors)
        btn_layout.addWidget(self.titles_to_anchors_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Статистика
        stats_layout = QHBoxLayout()
        self.links_stats_label = QLabel("")
        stats_layout.addWidget(self.links_stats_label)
        stats_layout.addStretch()
        layout.addLayout(stats_layout)

        self.tabs.addTab(widget, "👁 Предпросмотр")

    def _on_anchor_edited(self, item: QTableWidgetItem):
        """Синхронизирует изменённый анкор с объектом Link."""
        if item.column() != 4:  # Только столбец "Анкор"
            return

        row = item.row()
        links = getattr(self.linker, "all_links", [])

        if 0 <= row < len(links):
            new_anchor = item.text().strip()
            if new_anchor:
                links[row].anchor = new_anchor

    def _on_cell_double_clicked(self, row: int, column: int):
        """Двойной клик по ячейке Title — копирует в буфер обмена."""
        if column != 1:  # Только столбец "Title источника"
            return

        item = self.links_table.item(row, column)
        if item:
            from PyQt6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            # Берём полный title из tooltip (там без обрезки)
            full_title = item.toolTip() or item.text()
            clipboard.setText(full_title)

    def _on_regenerate_anchors(self):
        """Пересобирает анкоры для всех ссылок."""
        links = getattr(self.linker, "all_links", [])
        if not links:
            return

        from seo_cluster_linker import AnchorMorpher

        # Собираем уникальные топики
        topics = set()
        for link in links:
            if link.source.topic:
                topics.add(link.source.topic)

        # Создаём морферы для каждого топика
        morphers = {}
        for topic in topics:
            synonyms = self.linker.cluster_builder._get_synonyms(topic) if self.linker else []
            morphers[topic] = AnchorMorpher(topic, synonyms)

        # Блокируем сигналы
        self.links_table.blockSignals(True)

        for row, link in enumerate(links):
            topic = link.source.topic or list(topics)[0] if topics else "drug"
            morpher = morphers.get(topic)

            if morpher:
                # 60% commercial, 40% longtail
                category = random.choices(
                    ['commercial', 'longtail'],
                    weights=[60, 40],
                    k=1
                )[0]
                new_anchor = morpher.get_anchor(category=category)
                link.anchor = new_anchor

                # Обновляем таблицу
                anchor_item = self.links_table.item(row, 4)
                if anchor_item:
                    anchor_item.setText(new_anchor)

        self.links_table.blockSignals(False)

    def _on_titles_to_anchors(self):
        """Копирует Title в Анкор для internal ссылок (lowercase)."""
        links = getattr(self.linker, "all_links", [])
        if not links:
            return

        self.links_table.blockSignals(True)

        for row, link in enumerate(links):
            if link.link_type == 'internal':
                title = link.source.title or ""
                # Преобразуем в lowercase
                new_anchor = title.lower().strip()

                if new_anchor:
                    link.anchor = new_anchor

                    # Обновляем таблицу
                    anchor_item = self.links_table.item(row, 4)
                    if anchor_item:
                        anchor_item.setText(new_anchor)

        self.links_table.blockSignals(False)

    def _create_report_tab(self):
        """Вкладка отчёта."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        layout.addWidget(self.report_text)

        self.tabs.addTab(widget, "📋 Отчёт")

    def _create_visual_editor_tab(self):
        """
        Вкладка "Визуальный редактор" с графом фактических и планируемых ссылок.
        """
        self.visual_editor = VisualEditorWidget(self.base_dir, parent=self)
        self.visual_editor.applyPlannedLinks.connect(self._on_visual_editor_apply_links)
        self.tabs.addTab(self.visual_editor, "🧠 Визуальный редактор")

    def _on_visual_editor_apply_links(self, links: list):
        """Обработчик сигнала от VisualEditorWidget.applyPlannedLinks.

        links: список словарей вида:
            {
                "source_path": "C:/.../domain/page.html",
                "source_url": "https://domain/page/",
                "target_url": "https://target-domain/target-page/",
                "anchor": "anchor text"
            }
        """
        if not links:
            QMessageBox.information(self, "Visual Linker", "Нет ссылок для вставки")
            return

        # Создаём объекты Page/Link минимально необходимыми для вставки
        link_objects: List[Link] = []
        for item in links:
            source_path = item.get("source_path") or ""
            source_url = item.get("source_url") or ""
            target_url = item.get("target_url") or ""
            anchor = (item.get("anchor") or "").strip()

            if not source_path or not source_url or not target_url or not anchor:
                continue

            src_domain = urlparse(source_url).netloc or os.path.basename(os.path.dirname(source_path))
            tgt_domain = urlparse(target_url).netloc or src_domain

            src_page = Page(
                url=source_url,
                domain=src_domain,
                file_path=source_path,
                title=os.path.basename(source_path),
                topic="",
                incoming_links=0,
                outgoing_links=0,
            )
            tgt_page = Page(
                url=target_url,
                domain=tgt_domain,
                file_path="",
                title="",
                topic="",
                incoming_links=0,
                outgoing_links=0,
            )

            link_type = "internal" if tgt_domain == src_domain else "cross-site"
            link_objects.append(Link(
                source=src_page,
                target=tgt_page,
                anchor=anchor,
                link_type=link_type,
            ))

        if not link_objects:
            QMessageBox.warning(self, "Visual Linker", "Не удалось подготовить ссылки для вставки")
            return

        inserter = LinkInserter()
        stats = inserter.insert_links(link_objects)

        ok = stats.get("success", 0)
        failed = stats.get("failed", 0)
        skipped = stats.get("skipped", 0)

        msg = (
            f"Вставка ссылок из Visual Linker завершена.\n\n"
            f"Успешно: {ok}\n"
            f"Пропущено: {skipped}\n"
            f"Ошибок: {failed}"
        )
        QMessageBox.information(self, "Visual Linker", msg)

    def _apply_styles(self):
        """Применяет стили из styles.py."""
        styles = Styles()
        self.setStyleSheet(styles.get_dark())

        # Дополнительные стили для специфичных элементов этого диалога
        extra_styles = """
            QLabel#header {
                font-size: 20px;
                font-weight: bold;
                color: #007acc;
                padding: 10px;
                border: none;
            }
            
            QPushButton#generate_btn {
                background: #2d8d46;
                border: 1px solid #3ca55a;
                font-weight: bold;
                padding: 10px 20px;
            }
            
            QPushButton#generate_btn:hover {
                background: #3ca55a;
                border: 1px solid #4dc56a;
            }
            
            QPushButton#generate_btn:disabled {
                background: #3c3c3c;
                border: 1px solid #474747;
                color: #808080;
            }
        """
        self.setStyleSheet(styles.get_dark() + extra_styles)

    # ═══════════════════════════════════════════════════════════════════════════
    # EVENT HANDLERS
    # ═══════════════════════════════════════════════════════════════════════════

    def _on_scan(self):
        """Сканирование директории."""
        if not self.base_dir or not os.path.isdir(self.base_dir):
            QMessageBox.warning(self, "Ошибка", "Директория не найдена!")
            return

        self.scan_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate

        # Создаём linker
        self.linker = SEOClusterLinker(
            base_directory=self.base_dir,
            keywords_map=KEYWORDS,
            min_text_length=self.min_len_spin.value()
        )

        # Запускаем сканирование в потоке
        self.scan_worker = ScanWorker(self.linker)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_error)
        self.scan_worker.start()

    def _on_scan_progress(self, msg: str):
        """Прогресс сканирования."""
        self.cluster_info.append(msg)

    def _on_scan_finished(self, clusters: dict):
        """Сканирование завершено."""
        self.clusters = clusters
        self.scan_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        # Заполняем таблицу кластеров
        self.clusters_table.setRowCount(0)
        self.topic_combo.clear()
        self.topic_combo.addItem("ВСЕ КЛАСТЕРЫ", "ALL")

        for topic, cluster in clusters.items():
            row = self.clusters_table.rowCount()
            self.clusters_table.insertRow(row)

            # Препарат
            self.clusters_table.setItem(row, 0, QTableWidgetItem(topic.capitalize()))

            # Страниц
            self.clusters_table.setItem(row, 1, QTableWidgetItem(str(len(cluster.pages))))

            # Доменов
            self.clusters_table.setItem(row, 2, QTableWidgetItem(str(len(cluster.domains))))

            # Синонимы
            synonyms = [k for k, v in KEYWORDS.items() if v == topic and k != topic]
            self.clusters_table.setItem(row, 3, QTableWidgetItem(", ".join(synonyms)))

            # Статус
            status = "✅ Готов" if len(cluster.pages) >= 2 else "⚠️ Мало страниц"
            item = QTableWidgetItem(status)
            if "⚠️" in status:
                item.setForeground(QColor("#e8ab02"))
            else:
                item.setForeground(QColor("#3ca55a"))
            self.clusters_table.setItem(row, 4, item)

            # Добавляем в комбобокс
            self.topic_combo.addItem(f"{topic.capitalize()} ({len(cluster.pages)} стр.)", topic)

        # Активируем кнопки
        if clusters:
            self.preview_btn.setEnabled(True)
            self.generate_btn.setEnabled(True)
            self.export_btn.setEnabled(True)

        self.cluster_info.append(f"\n✅ Найдено {len(clusters)} кластеров!")

    def _on_cluster_selected(self):
        """Выбран кластер в таблице."""
        selected = self.clusters_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        topic = self.clusters_table.item(row, 0).text().lower()

        if topic not in self.clusters:
            return

        cluster = self.clusters[topic]

        info_lines = [
            f"<b>Препарат:</b> {topic.upper()}",
            f"<b>Страниц:</b> {len(cluster.pages)}",
            f"<b>Доменов:</b> {len(cluster.domains)}",
            "",
            "<b>Домены:</b>"
        ]

        for domain, pages in cluster.pages_by_domain.items():
            info_lines.append(f"  • {domain}: {len(pages)} страниц")

        self.cluster_info.setHtml("<br>".join(info_lines))

    def _on_preview(self):
        """Предпросмотр ссылок."""
        if not self.linker:
            return

        topic = self.topic_combo.currentData()
        scheme = self.scheme_combo.currentData()

        # Создаём ссылки (без вставки)
        params = {
            'external_links_per_page': self.external_links_spin.value(),
            'ensure_full_coverage': self.ensure_coverage_cb.isChecked()
        }

        links = self.linker.create_links(
            topic=topic if topic != 'ALL' else None,
            scheme=scheme,
            **params
        )

        # Блокируем сигнал чтобы не срабатывал _on_anchor_edited при заполнении
        self.links_table.blockSignals(True)
        self.links_table.setRowCount(0)

        for link in links:
            row = self.links_table.rowCount()
            self.links_table.insertRow(row)

            # Источник (домен) - read-only
            source_item = QTableWidgetItem(link.source.domain)
            source_item.setFlags(source_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.links_table.setItem(row, 0, source_item)

            # Title источника - read-only
            title_item = QTableWidgetItem(link.source.title[:60] if link.source.title else "")
            title_item.setFlags(title_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            title_item.setToolTip(link.source.title)  # Полный title в tooltip
            self.links_table.setItem(row, 1, title_item)

            # Цель (домен) - read-only
            target_item = QTableWidgetItem(link.target.domain)
            target_item.setFlags(target_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.links_table.setItem(row, 2, target_item)

            # Тип - read-only
            type_item = QTableWidgetItem(link.link_type)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if link.link_type == 'internal':
                type_item.setForeground(QColor("#007acc"))
            else:
                type_item.setForeground(QColor("#3ca55a"))
            self.links_table.setItem(row, 3, type_item)

            # Анкор - РЕДАКТИРУЕМЫЙ
            anchor_item = QTableWidgetItem(link.anchor)
            self.links_table.setItem(row, 4, anchor_item)

            # Статус - read-only
            status_item = QTableWidgetItem("📝 План")
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.links_table.setItem(row, 5, status_item)

        self.links_table.blockSignals(False)

        # Статистика
        internal = sum(1 for l in links if l.link_type == 'internal')
        cross = sum(1 for l in links if l.link_type == 'cross-site')

        self.links_stats_label.setText(
            f"📊 Всего: {len(links)} ссылок | Внутренних: {internal} | Cross-site: {cross}"
        )

        # Переключаемся на вкладку превью
        self.tabs.setCurrentIndex(2)

        # Генерируем отчёт
        self._generate_report()

    def _on_generate(self):
        """Вставка ссылок (использует уже созданные в предпросмотре)."""
        if not self.linker:
            return

        # Проверяем что ссылки уже созданы через предпросмотр
        links = getattr(self.linker, "all_links", [])
        if not links:
            QMessageBox.warning(
                self, "Ошибка",
                "Сначала нажмите 'Предпросмотр' чтобы создать ссылки."
            )
            return

        # Подтверждение
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Вставить {len(links)} ссылок в HTML-файлы?\n\n"
            "Будут использованы анкоры из таблицы предпросмотра.\n"
            "Рекомендуется сделать резервную копию перед продолжением.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.generate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        # Запускаем вставку БЕЗ пересоздания ссылок
        self.link_worker = LinkWorker(self.linker, use_existing=True)
        self.link_worker.progress.connect(self._on_link_progress)
        self.link_worker.link_created.connect(self._on_link_created)
        self.link_worker.finished.connect(self._on_generate_finished)
        self.link_worker.error.connect(self._on_error)
        self.link_worker.start()

    def _on_link_progress(self, msg: str):
        """Прогресс создания ссылок."""
        self.report_text.append(msg)

    def _on_link_created(self, source: str, target: str, anchor: str):
        """Создана ссылка."""
        pass  # Можно добавить обновление UI

    def _on_generate_finished(self, stats: dict):
        """Генерация завершена."""
        self.generate_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        # Берём фактический список ссылок, по которым работал инсертер
        links = getattr(self.linker, "all_links", [])

        row_count = self.links_table.rowCount()
        for row in range(row_count):
            status_item = self.links_table.item(row, 5)
            if status_item is None:
                status_item = QTableWidgetItem()

            link_obj = links[row] if 0 <= row < len(links) else None
            inserted = bool(getattr(link_obj, "inserted", False)) if link_obj is not None else False
            context = getattr(link_obj, "context", "") if link_obj is not None else ""

            if inserted:
                status_item.setText("✅ Вставлено")
                status_item.setForeground(QColor("#3ca55a"))
                status_item.setToolTip("Ссылка успешно вставлена в HTML")
            else:
                status_item.setText("❌ Ошибка")
                status_item.setForeground(QColor("#e06c75"))
                if context:
                    status_item.setToolTip(context)
                else:
                    status_item.setToolTip("Не удалось вставить ссылку в текстовый блок")

            self.links_table.setItem(row, 4, status_item)

        # Генерируем финальный отчёт
        self._generate_report()

        QMessageBox.information(
            self, "Готово",
            f"✅ Перелинковка завершена!\n\n"
            f"Успешно: {stats.get('success', 0)}\n"
            f"Ошибок: {stats.get('failed', 0)}\n"
            f"Пропущено: {stats.get('skipped', 0)}"
        )


    def _on_export(self):
        """Экспорт в JSON."""
        if not self.linker:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить JSON",
            "links_export.json",
            "JSON Files (*.json)"
        )

        if path:
            self.linker.export_links_json(path)
            QMessageBox.information(self, "Экспорт", f"Сохранено в {path}")

    def _on_error(self, error: str):
        """Обработка ошибок."""
        self.scan_btn.setEnabled(True)
        self.generate_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Ошибка", error)

    def _generate_report(self):
        """Генерирует текстовый отчёт."""
        if not self.linker:
            return

        report_lines = []
        analyses = self.linker.get_coverage_analysis()

        for topic, analysis in analyses.items():
            report_lines.append("=" * 70)
            report_lines.append(f"  {topic.upper()}")
            report_lines.append("=" * 70)
            report_lines.append("")
            report_lines.append(f"📊 Страниц: {analysis['total_pages']}")
            report_lines.append(f"📊 Ссылок: {analysis['total_links']}")
            report_lines.append(f"   • Внутренних: {analysis['internal_links']}")
            report_lines.append(f"   • Cross-site: {analysis['cross_site_links']}")
            report_lines.append("")
            report_lines.append(f"📈 Coverage Score: {analysis['coverage_score']:.1f}%")
            report_lines.append(f"📈 Среднее входящих: {analysis['avg_incoming']:.1f}")
            report_lines.append(f"📈 Среднее исходящих: {analysis['avg_outgoing']:.1f}")
            report_lines.append("")

            if analysis['orphan_pages']:
                report_lines.append(f"⚠️ Страницы без входящих ({analysis['pages_without_incoming']}):")
                for url in analysis['orphan_pages'][:5]:
                    report_lines.append(f"   • {url}")
            else:
                report_lines.append("✅ Все страницы имеют входящие ссылки")

            report_lines.append("")
            report_lines.append("📁 Домены:")
            for domain, count in analysis['pages_per_domain'].items():
                report_lines.append(f"   {domain}: {count} страниц")

            report_lines.append("")

        self.report_text.setPlainText("\n".join(report_lines))
        self.tabs.setCurrentIndex(3)

    def _on_apply_visual_links(self, links_data: list):
        """
        Вставляет ТОЛЬКО те ссылки, которые заданы во вкладке Visual Linker.
        Не трогает существующую кластерную перелинковку.
        """
        if not self.linker or not self.linker.clusters:
            QMessageBox.warning(
                self,
                "Visual Linker",
                "Сначала выполните сканирование кластеров"
            )
            return

        # Быстрая карта URL -> Page
        def _norm(u: str) -> str:
            return (u or "").strip().rstrip("/").lower()

        url_to_page: dict[str, Page] = {}
        for cluster in self.linker.clusters.values():
            for page in cluster.pages:
                url_to_page[_norm(page.url)] = page

        custom_links: list[Link] = []

        for item in links_data:
            source_url = item.get("source_url", "")
            target_url = item.get("target_url", "")
            anchor = (item.get("anchor") or "").strip()
            if not source_url or not target_url or not anchor:
                continue

            src_page = url_to_page.get(_norm(source_url))
            tgt_page = url_to_page.get(_norm(target_url))

            # Работать только с теми, кто реально есть в кластерах
            if not src_page or not tgt_page:
                continue

            link = Link(
                source=src_page,
                target=tgt_page,
                anchor=anchor,
                link_type="cross-site"
            )
            custom_links.append(link)

        if not custom_links:
            QMessageBox.information(
                self,
                "Visual Linker",
                "Не найдено ни одной валидной связи для вставки"
            )
            return

        # Вставляем только эти ссылки через уже настроенный LinkInserter
        inserter = self.linker.link_inserter
        stats = inserter.insert_links(custom_links)

        QMessageBox.information(
            self,
            "Visual Linker",
            f"Вставка связей Visual Linker завершена\n\n"
            f"Успешно: {stats.get('success', 0)}\n"
            f"Ошибок: {stats.get('failed', 0)}\n"
            f"Пропущено: {stats.get('skipped', 0)}"
        )

    def _show_linking_examples(self):
        """Показывает наглядные примеры схем перелинковки."""
        dialog = LinkingExamplesDialog(self)
        dialog.exec()
# ═══════════════════════════════════════════════════════════════════════════════
# ИНТЕГРАЦИЯ В MAIN.PY
# ═══════════════════════════════════════════════════════════════════════════════
"""
Добавьте в main.py:

1. Импорт:
   from seo_cluster_dialog import SEOClusterDialog

2. Кнопку в интерфейсе:
   self.cluster_link_btn = QPushButton("🔗 Кластерная перелинковка")
   self.cluster_link_btn.clicked.connect(self.on_cluster_linking)
   
3. Метод:
   def on_cluster_linking(self):
       if not self.generator or not self.generator.directory:
           QMessageBox.warning(self, "Ошибка", "Сначала выберите директорию!")
           return
       
       dialog = SEOClusterDialog(self.generator.directory, parent=self)
       dialog.exec()
"""


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Тестовый запуск
    dialog = SEOClusterDialog("/tmp/test", None)
    dialog.show()

    sys.exit(app.exec())
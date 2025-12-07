import math
import os
import subprocess
import re
import logging
import random
import chardet
import requests
from datetime import datetime
from typing import List, Dict, Set, Tuple
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup, Comment
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QRectF, QPointF
from PyQt6.QtGui import QMovie, QPainter, QColor, QFont, QPen, QBrush, QPainterPath, QRadialGradient
from PyQt6.QtWidgets import (
    QLabel, QTextEdit, QFileDialog, QListWidget, QDialog, QDialogButtonBox, QLineEdit, QSpinBox, QCheckBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox,
    QApplication, QStyledItemDelegate, QAbstractButton
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from graph_dialog import GraphDialog
from stage2 import SecondStageLinkDialog
from matrix_splash import MatrixSplashScreen, SpinnerOverlay
from seo_cluster_dialog import SEOClusterDialog
from pbn_analyzer import PbnAnalyzerDialog
from google_indexer import GoogleIndexerDialog


from pills import KEYWORDS
keywords = KEYWORDS

from styles import Styles


class NoCacheCheckerThread(QThread):
    progress = pyqtSignal(int, str, str, str, str, bool)  # row, url, title, status, pill, ok
    def __init__(self, links, tablet_map):
        super().__init__()
        self.links = links
        self.tablet_map = tablet_map
    def run(self):
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}
        for i, url in enumerate(self.links):
            url_clean = url.split("/?nocache")[0]
            pill = self.tablet_map.get(url_clean, "")
            try:
                r = requests.get(url, headers=headers, timeout=10)
                http_status = r.status_code
                status_text = f"{http_status} OK" if r.ok else f"{http_status} {r.reason.upper()}"
                if r.ok:
                    soup = BeautifulSoup(r.text, "html.parser")
                    title = (soup.title.string or "").strip()
                    all_synonyms = set([pill])
                    for k, v in keywords.items():
                        if v == pill:
                            all_synonyms.add(k)
                    ok = any(syn.lower() in title.lower() for syn in all_synonyms)
                else:
                    title, ok = status_text, False
            except Exception as e:
                status_text = "ERROR"
                title = str(e)
                ok = False
            self.progress.emit(i, url, title, status_text, pill, ok)

class PrintCheckThread(QThread):
    # row, url, title, status, matched
    progress = pyqtSignal(int, str, str, str, bool)

    def __init__(self, links, parent=None):
        super().__init__(parent)
        self.links = links
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/129.0.0.0 Safari/537.36"
            ),
            "Referer": "https://google.com/",
        }

        # тут твои ключевые слова
        keywords = ("11", "11drugs.com", "online", "drug", "pharm", "pills", "tablet", "Medicines", "pharmacy", "prescription")

        for i, url in enumerate(self.links):
            if self._stop_requested:
                break

            url_clean = url  # НИЧЕГО не режем

            try:
                r = requests.get(url_clean, headers=headers, timeout=10)
                status_code = r.status_code
                reason = r.reason or ""
                status_text = f"{status_code} {reason}".strip()

                if r.ok:
                    soup = BeautifulSoup(r.text, "html.parser")
                    title_tag = soup.find("title")
                    title = (title_tag.text or "").strip() if title_tag else ""
                else:
                    title = ""
            except Exception as e:
                status_text = "ERROR"
                title = str(e)

            lower = (title or "").lower()
            matched = any(word in lower for word in keywords)

            self.progress.emit(i, url_clean, title, status_text, matched)



class GiveMeUrlsWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, generator):
        super().__init__()
        self.generator = generator

    def run(self):
        try:
            import shutil
            import tempfile
            import os
            import sys
            tracker_key = getattr(self.generator, 'tracker_key', None)
            folder = self.generator.directory

            orig_path = os.path.abspath("url_from_folder.py")
            pills_path = os.path.abspath("pills.py")  # путь к pills.py

            temp_filename = ""
            output = ""
            temp_dir = None

            try:
                # Создаем временную директорию для всех файлов
                temp_dir = tempfile.mkdtemp(prefix="giveurls_")

                # Копируем url_from_folder.py во временную директорию
                temp_url_script = os.path.join(temp_dir, "url_from_folder.py")
                with open(orig_path, "r", encoding="utf-8") as f_in, open(temp_url_script, "w",
                                                                          encoding="utf-8") as f_out:
                    for line in f_in:
                        if "trackerKey" in line and line.strip().startswith('"trackerKey":'):
                            f_out.write(f'            "trackerKey": "{tracker_key}",\n')
                        elif "trackerKey" in line and line.strip().startswith('#"trackerKey":'):
                            f_out.write(f'            "trackerKey": "{tracker_key}",\n')
                        else:
                            f_out.write(line)

                # Копируем pills.py в ту же папку
                temp_pills = os.path.join(temp_dir, "pills.py")
                shutil.copyfile(pills_path, temp_pills)

                # Запускаем subprocess в temp_dir с sys.path
                project_dir = os.path.dirname(os.path.abspath(__file__))
                log_dir = os.path.join(project_dir, "logs")

                res = subprocess.run(
                    [sys.executable, temp_url_script, folder, log_dir],  # <-- передаем log_dir ТРЕТЬИМ аргументом
                    capture_output=True, encoding="utf-8", timeout=1800,
                    cwd=temp_dir
                )
                output = res.stdout.strip()
                if res.stderr:
                    output += "\n\n[stderr]\n" + res.stderr

            except Exception as e:
                output = f"Ошибка запуска скрипта url_from_folder.py: {e}"

            finally:
                # Удаляем временную директорию со всеми файлами
                try:
                    if temp_dir and os.path.isdir(temp_dir):
                        shutil.rmtree(temp_dir)
                except Exception:
                    pass

            self.finished.emit(output)
        except Exception as e:
            self.error.emit(str(e))


class AnalyzePagesWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, generator):
        super().__init__()
        self.generator = generator

    def run(self):
        try:
            res = self.generator.analyze_pages()
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))

class ReplaceTxtWorker(QThread):
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.directory = directory

    def run(self):
        try:
            from content_replacer import ReplaceFromTxtDialog
            diag = ReplaceFromTxtDialog(content_dir=self.directory)
            diag.exec()
        except Exception as e:
            self.error.emit(str(e))
        self.finished.emit()

###############################################################################
# ЛОГИРОВАНИЕ
###############################################################################
class DomainFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        self.last_domain = None
    def format(self, record):
        formatted_record = super().format(record)
        if hasattr(record, 'domain') and record.domain != self.last_domain:
            self.last_domain = record.domain
            return f"\n{'=' * 50}\nПереход к домену: {record.domain}\n{'=' * 50}\n{formatted_record}"
        return formatted_record

def setup_logging(filename):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.handlers:
        logger.handlers.clear()
    formatter = DomainFormatter('%(asctime)s - %(levelname)s - %(message)s')
    fh = logging.FileHandler(filename, encoding='utf-8')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger

log_filename = os.path.join("logs", f"link_generator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
os.makedirs(os.path.dirname(log_filename), exist_ok=True)
logger = setup_logging(log_filename)




class NoCacheTableDialog(QDialog):
    def __init__(self, links, tablet_map, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NOCACHE ПРОВЕРКА")
        self.setMinimumSize(1200, 750)
        vbox = QVBoxLayout(self)
        self.tbl = QTableWidget(len(links), 4)
        self.tbl.setHorizontalHeaderLabels(["URL", "TITLE", "STATUS", "PILL"])
        for i, url in enumerate(links):
            self.tbl.setItem(i, 0, QTableWidgetItem(url))
            self.tbl.setItem(i, 1, QTableWidgetItem("…"))
            self.tbl.setItem(i, 2, QTableWidgetItem("…"))
            self.tbl.setItem(i, 3, QTableWidgetItem(tablet_map.get(url.split("/?nocache")[0], "")))
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        vbox.addWidget(self.tbl)
        self.setLayout(vbox)
        self.status_lbl = QLabel("Идёт онлайн-проверка Googlebot…")
        vbox.addWidget(self.status_lbl)
        self.thread = NoCacheCheckerThread(links, tablet_map)
        self.thread.progress.connect(self.update_row)
        self.thread.start()

    def update_row(self, i, url, title, status, pill, ok):
        self.tbl.setItem(i, 1, QTableWidgetItem(title))
        self.tbl.setItem(i, 2, QTableWidgetItem(status))
        self.tbl.setItem(i, 3, QTableWidgetItem(pill))
        # Цвет всей строки
        color = Qt.GlobalColor.green if status.startswith("200") and ok else Qt.GlobalColor.red
        for col in range(self.tbl.columnCount()):
            item = self.tbl.item(i, col)
            if item:
                item.setForeground(color)
        self.tbl.scrollToItem(self.tbl.item(i, 0))

class PrintCheckTableDialog(QDialog):
    def __init__(self, links, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Проверка принтов")
        self.setMinimumSize(1200, 750)

        self.matched_titles: List[str] = []
        self.worker = None

        vbox = QVBoxLayout(self)

        # --- Верхняя панель кнопок ---
        btn_layout = QHBoxLayout()

        self.btn_remove_nocache = QPushButton("УБРАТЬ ?nocache")
        self.btn_remove_nocache.setFixedWidth(160)
        self.btn_remove_nocache.clicked.connect(self.remove_nocache)
        btn_layout.addWidget(self.btn_remove_nocache)

        self.btn_add_nocache = QPushButton("УСТАНОВИТЬ ?nocache")
        self.btn_add_nocache.setFixedWidth(180)
        self.btn_add_nocache.clicked.connect(self.add_nocache)
        btn_layout.addWidget(self.btn_add_nocache)

        # СТАРТ / СТОП
        self.btn_start = QPushButton("СТАРТ")
        self.btn_start.setFixedWidth(100)
        self.btn_start.setStyleSheet("background-color: #1e7e34; color: #ffffff;")
        self.btn_start.clicked.connect(self.start_checks)
        btn_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("СТОП")
        self.btn_stop.setFixedWidth(100)
        self.btn_stop.setStyleSheet("background-color: #c82333; color: #ffffff;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_checks)
        btn_layout.addWidget(self.btn_stop)

        btn_layout.addStretch(1)
        vbox.addLayout(btn_layout)

        # --- Таблица ---
        self.tbl = QTableWidget(len(links), 4, self)
        self.tbl.setHorizontalHeaderLabels(["#", "URL", "TITLE", "STATUS"])

        header = self.tbl.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        vbox.addWidget(self.tbl)

        for i, url in enumerate(links):
            # номер
            num_item = QTableWidgetItem(str(i + 1))
            num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl.setItem(i, 0, num_item)

            # URL как есть
            url_item = QTableWidgetItem(url)
            url_item.setFlags(url_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl.setItem(i, 1, url_item)

            # заглушки
            title_item = QTableWidgetItem("…")
            title_item.setFlags(title_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl.setItem(i, 2, title_item)

            status_item = QTableWidgetItem("…")
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl.setItem(i, 3, status_item)

    # --- nocache кнопки ---

    def remove_nocache(self):
        rows = self.tbl.rowCount()
        for i in range(rows):
            item = self.tbl.item(i, 1)
            if not item:
                continue
            url = item.text()

            if "/?nocache" in url:
                url = url.replace("/?nocache", "")
            if "?nocache" in url:
                url = url.replace("?nocache", "")

            item.setText(url)

    def add_nocache(self):
        rows = self.tbl.rowCount()
        for i in range(rows):
            item = self.tbl.item(i, 1)
            if not item:
                continue

            url = item.text()

            # уже есть — пропускаем
            if "/?nocache" in url or "?nocache" in url:
                continue

            # всегда добавляем строго через "/?nocache"
            if url.endswith("/"):
                url = url + "?nocache"
            else:
                url = url + "/?nocache"

            item.setText(url)

    # --- старт / стоп ---

    def start_checks(self):
        # уже идёт — не дёргаем
        if self.worker is not None and self.worker.isRunning():
            return

        # собираем актуальные URL из таблицы
        links = []
        rows = self.tbl.rowCount()
        for i in range(rows):
            item = self.tbl.item(i, 1)
            links.append(item.text().strip() if item else "")

            # одновременно сбрасываем результат
            title_item = self.tbl.item(i, 2)
            if title_item:
                title_item.setText("…")
                font = title_item.font()
                font.setBold(False)
                title_item.setFont(font)
                title_item.setForeground(QBrush(Qt.GlobalColor.white))

            status_item = self.tbl.item(i, 3)
            if status_item:
                status_item.setText("…")
                status_item.setForeground(QBrush(Qt.GlobalColor.white))

        self.matched_titles.clear()

        self.worker = PrintCheckThread(links, self)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_worker_finished)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.worker.start()

    def stop_checks(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()

    def on_worker_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    # --- обновление строк таблицы из потока ---

    def on_progress(self, row: int, url: str, title: str, status: str, matched: bool):
        if row < 0 or row >= self.tbl.rowCount():
            return

        # URL
        url_item = self.tbl.item(row, 1)
        if url_item is None:
            url_item = QTableWidgetItem()
            url_item.setFlags(url_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl.setItem(row, 1, url_item)
        url_item.setText(url)

        # TITLE
        title_item = self.tbl.item(row, 2)
        if title_item is None:
            title_item = QTableWidgetItem()
            title_item.setFlags(title_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl.setItem(row, 2, title_item)
        title_item.setText(title)

        # STATUS
        status_item = self.tbl.item(row, 3)
        if status_item is None:
            status_item = QTableWidgetItem()
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl.setItem(row, 3, status_item)
        status_item.setText(status)

        # Подсветка совпадений: (11, online, drug, pharm) — зелёный bold
        if matched:
            self.matched_titles.append(title)
            font = title_item.font()
            font.setBold(True)
            title_item.setFont(font)
            title_item.setForeground(QColor("#00FF00"))

        self.tbl.scrollToItem(self.tbl.item(row, 0))




###############################################################################
# ГЛОБАЛЬНЫЕ
###############################################################################
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0'
]




###############################################################################
# HELP
###############################################################################
from help import help_html


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Справка / Help")
        self.setMinimumSize(900, 700)  # увеличил для удобства просмотра

        # Используем QWebEngineView вместо QTextBrowser
        layout = QVBoxLayout()
        web_view = QWebEngineView()
        web_view.setHtml(help_html)

        layout.addWidget(web_view)
        self.setLayout(layout)


###############################################################################
# 1-й этап: АНКОРЫ
###############################################################################
class AnchorDialog(QDialog):
    def __init__(self, kw_set, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройка анкоров (1-й этап)")
        self.setMinimumWidth(600)
        layout = QVBoxLayout()
        self.keyword_list = QListWidget()
        self.keyword_list.addItems(sorted(kw_set))
        layout.addWidget(QLabel("Выберите ключевое слово для редактирования анкоров:"))
        layout.addWidget(self.keyword_list)

        add_layout = QHBoxLayout()
        self.anchor_input = QLineEdit()
        self.add_anchor_btn = QPushButton("Добавить анкор")
        add_layout.addWidget(self.anchor_input)
        add_layout.addWidget(self.add_anchor_btn)
        layout.addWidget(QLabel("Добавить новый анкор:"))
        layout.addLayout(add_layout)

        self.anchor_list = QListWidget()
        layout.addWidget(QLabel("Текущие анкоры:"))
        layout.addWidget(self.anchor_list)

        rm_layout = QHBoxLayout()
        self.remove_selected_btn = QPushButton("Удалить выбранный анкор")
        self.clear_all_btn = QPushButton("Очистить все анкоры для слова")
        rm_layout.addWidget(self.remove_selected_btn)
        rm_layout.addWidget(self.clear_all_btn)
        layout.addLayout(rm_layout)

        self.load_defaults_btn = QPushButton("Загрузить анкоры по умолчанию")
        layout.addWidget(self.load_defaults_btn)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(btn_box)

        self.setLayout(layout)

        self.keyword_list.currentItemChanged.connect(self.load_anchors_for_keyword)
        self.add_anchor_btn.clicked.connect(self.add_anchor)
        self.remove_selected_btn.clicked.connect(self.remove_selected_anchor)
        self.clear_all_btn.clicked.connect(self.clear_all_anchors)
        self.load_defaults_btn.clicked.connect(self.load_default_anchors)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

        self.anchors_dict = {}
        self.load_default_anchors()

    def load_default_anchors(self):
        default_templates = [
            "buy cheap {keyword} online",
            "order {keyword} pills without prescription",
            "purchase {keyword} safely",
            "best price on {keyword} tablets",
            "{keyword} tablets for sale",
            "buy {keyword} online pharmacy",
            "cheap {keyword} medication",
            "buy {keyword} without RX",
            "where to buy {keyword} online",
            "order generic {keyword} pills",
            "{keyword} pills discreet shipping",
            "secure online purchase of {keyword}",
            "{keyword} tablets online no prescription",
            "best place to buy {keyword} online",
            "{keyword} affordable prices",
            "{keyword} online order fast delivery",
            "trusted pharmacy for {keyword}",
            "how to buy {keyword} online",
            "{keyword} medication online safely",
            "{keyword} pills from reliable pharmacy",
            "discounted {keyword} tablets online",
            "order {keyword} medication discreetly",
            "{keyword} without prescription cheap",
            "reliable supplier of {keyword} online",
            "{keyword} tablets purchase safely",
            "safe and fast {keyword} pills",
            "low-cost {keyword} tablets",
            "genuine {keyword} available online",
            "{keyword} pills online overnight",
            "trusted source for {keyword} medication"
        ]

        new_d = {}
        for k in keywords:
            new_d[k] = {tpl.format(keyword=k) for tpl in default_templates}
        self.anchors_dict = new_d
        self.load_anchors_for_keyword()

    def add_anchor(self):
        kw_item = self.keyword_list.currentItem()
        if not kw_item:
            return
        kw = kw_item.text()
        text_ = self.anchor_input.text().strip()
        if not text_:
            return
        if kw not in self.anchors_dict:
            self.anchors_dict[kw] = set()
        self.anchors_dict[kw].add(text_)
        self.load_anchors_for_keyword()
        self.anchor_input.clear()

    def remove_selected_anchor(self):
        kw_item = self.keyword_list.currentItem()
        if not kw_item:
            return
        kw = kw_item.text()
        sel = self.anchor_list.currentItem()
        if not sel:
            return
        val = sel.text()
        if kw in self.anchors_dict and val in self.anchors_dict[kw]:
            self.anchors_dict[kw].remove(val)
        self.load_anchors_for_keyword()

    def clear_all_anchors(self):
        kw_item = self.keyword_list.currentItem()
        if not kw_item:
            return
        kw = kw_item.text()
        if kw in self.anchors_dict:
            self.anchors_dict[kw].clear()
        self.load_anchors_for_keyword()

    def load_anchors_for_keyword(self):
        self.anchor_list.clear()
        kw_item = self.keyword_list.currentItem()
        if not kw_item:
            return
        kw = kw_item.text()
        if kw in self.anchors_dict:
            ls = sorted(self.anchors_dict[kw])
            self.anchor_list.addItems(ls)

###############################################################################
# Диалог главной (star-схемы)
###############################################################################
class MainPageChoiceDialog(QDialog):
    def __init__(self, pages: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор главной страницы")
        self.setMinimumWidth(700)
        self.main_url = None

        layout = QVBoxLayout()
        self.list_widget = QListWidget()
        for p in pages:
            self.list_widget.addItem(p)
        layout.addWidget(QLabel("Выберите главный URL (для star-схемы):"))
        layout.addWidget(self.list_widget)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(btn_box)
        self.setLayout(layout)

        btn_box.accepted.connect(self.ok_clicked)
        btn_box.rejected.connect(self.reject)

    def ok_clicked(self):
        sel = self.list_widget.currentItem()
        if sel:
            self.main_url = sel.text()
        self.accept()

####################
# LinkScheme
####################
class LinkScheme:
    def __init__(self, scheme_name: str):
        self.scheme = scheme_name
        self.main_url = None

    def set_main_url(self, main_url: str):
        self.main_url = main_url

    def build_links(self, pages: List[str]) -> List[Tuple[str, str]]:
        if len(pages) < 2:
            return []
        if self.scheme == "chain":
            result = []
            for i in range(len(pages) - 1):
                result.append((pages[i], pages[i + 1]))
            return result
        elif self.scheme == "star-to-one":
            if self.main_url and (self.main_url in pages):
                center = self.main_url
            else:
                center = pages[0]
            return [(p, center) for p in pages if p != center]
        elif self.scheme == "star-from-one":
            if self.main_url and (self.main_url in pages):
                center = self.main_url
            else:
                center = pages[0]
            return [(center, p) for p in pages if p != center]
        elif self.scheme == "random":
            result = []
            for i in range(len(pages)):
                A = pages[i]
                B_candidates = [x for x in pages if x != A]
                if not B_candidates:
                    continue
                B = random.choice(B_candidates)
                result.append((A, B))
            return result
        return []

###############################################################################
# LinkGenerator
###############################################################################
class LinkGenerator:
    def __init__(self, directory: str):
        self.directory = directory
        self.pages_by_domain: Dict[str, Dict[str, str]] = {}
        self.relevant_pages: Dict[str, List[str]] = {}
        self.page_topics: Dict[str, str] = {}
        self.anchors: Dict[str, Set[str]] = {}
        self.scheme_name = "chain"
        self.main_url_overrides: Dict[str, str] = {}
        self._gather_pages()
        self.min_text_node_length = 40
        self.allow_fallback_insertion = False

    def set_link_scheme(self, scheme: str):
        self.scheme_name = scheme

    def set_main_url_for_topic(self, topic, url):
        self.main_url_overrides[topic] = url

    def _gather_pages(self):
        if not os.path.isdir(self.directory):
            return

        for domain in os.listdir(self.directory):
            domain_path = os.path.join(self.directory, domain)
            if os.path.isdir(domain_path):
                self.pages_by_domain[domain] = {}
                logger.info(f"\n{'=' * 50}\nОбработка домена: {domain}\n{'=' * 50}", extra={'domain': domain})

                for root, dirs, files in os.walk(domain_path):
                    for file in files:
                        if file.endswith('.html'):
                            full_file_path = os.path.join(root, file)
                            relative_path = os.path.relpath(full_file_path, domain_path).replace('\\', '/')
                            url_path = relative_path[:-5]  # удаляем '.html'
                            url = f"https://{domain}/{url_path}/"
                            self.pages_by_domain[domain][relative_path] = url
                            logger.info(f"Найдена страница: {url}")

    def _read_file(self, filepath: str) -> str:
        with open(filepath, "rb") as f:
            raw_data = f.read()
        det = chardet.detect(raw_data)
        enc = det.get('encoding') or 'utf-8'
        return raw_data.decode(enc, errors='replace')

    # def analyze_pages(self) -> Dict[str, List[str]]:
    #     self.relevant_pages = {}
    #     self.page_topics = {}
    #     for dom, mapping in self.pages_by_domain.items():
    #         for rel_file, url in mapping.items():
    #             fullp = os.path.join(self.directory, dom, rel_file)
    #             try:
    #                 content = self._read_file(fullp)
    #                 soup = BeautifulSoup(content, 'html.parser')
    #                 if not soup.title or not soup.title.string:
    #                     continue
    #                 title_ = soup.title.string.lower()
    #                 found_topic = None
    #                 for kw_ in keywords:
    #                     pat = re.compile(r'\b' + re.escape(kw_.lower()) + r'\b')
    #                     if pat.search(title_):
    #                         found_topic = kw_
    #                         break
    #                 if found_topic:
    #                     if found_topic not in self.relevant_pages:
    #                         self.relevant_pages[found_topic] = []
    #                     self.relevant_pages[found_topic].append(url)
    #                     self.page_topics[url] = found_topic
    #             except:
    #                 pass
    #     return self.relevant_pages

    def analyze_pages(self) -> Dict[str, List[str]]:
        self.relevant_pages = {}
        self.page_topics = {}

        # Готовим словарь всех синонимов таблеток
        synonym_to_main_keyword = {}
        for key, val in keywords.items():
            synonym_to_main_keyword[key] = val
            synonym_to_main_keyword[val] = val

        for dom, mapping in self.pages_by_domain.items():
            for rel_file, url in mapping.items():
                fullp = os.path.join(self.directory, dom, rel_file)
                try:
                    content = self._read_file(fullp)
                    soup = BeautifulSoup(content, 'html.parser')
                    if not soup.title or not soup.title.string:
                        continue
                    title_ = soup.title.string.lower()
                    found_topic = None

                    # Проверяем наличие любого синонима в тайтле
                    for synonym, main_keyword in synonym_to_main_keyword.items():
                        if re.search(r'\b' + re.escape(synonym.lower()) + r'\b', title_):
                            found_topic = main_keyword
                            break

                    if found_topic:
                        if found_topic not in self.relevant_pages:
                            self.relevant_pages[found_topic] = []
                        self.relevant_pages[found_topic].append(url)
                        self.page_topics[url] = found_topic
                except:
                    pass
        return self.relevant_pages



    def set_anchors(self, anchor_dict: Dict[str, Set[str]]):
        self.anchors = anchor_dict

    def _build_links_plan(self) -> List[Tuple[str, str, str]]:
        plan = []
        for topic, pages in self.relevant_pages.items():
            if len(pages) < 2:
                continue
            scheme = LinkScheme(self.scheme_name)
            if topic in self.main_url_overrides:
                scheme.set_main_url(self.main_url_overrides[topic])
            sub = scheme.build_links(pages)
            for (A, B) in sub:
                plan.append((A, B, topic))
        return plan

    def _is_forbidden_parent(self, tag) -> bool:
        forbidden_tags = {
            'script', 'style', 'meta', 'head', 'link', 'button', 'code', 'pre',
            'nav', 'footer', 'header', 'menu', 'aside'
        }
        while tag:
            if tag.name and tag.name.lower() in forbidden_tags:
                return True
            cls = tag.get('class') or []
            if isinstance(cls, str):
                cls = [cls]
            allc = " ".join(cls).lower()
            if any(x in allc for x in
                   ["header", "footer", "menu", "nav", "aside", "script", "bsa", "applugin", "display-none"]):
                return True
            my_id = tag.get('id', '').lower()
            if any(x in my_id for x in ["header", "footer", "menu", "nav", "aside", "script", "bsa", "applugin"]):
                return True
            st = tag.get('style', '').lower()
            if 'display' in st and 'none' in st:
                return True
            tag = tag.parent
        return False

    def _is_in_a_tag(self, node) -> bool:
        return node.find_parent('a') is not None

    def _is_inside_content_area(self, node) -> bool:
        return True  # Упрощенно считаем, что везде можно

    def _find_text_nodes_for_insertion(self, soup) -> list:
        text_nodes = []
        all_texts = soup.find_all(string=lambda s: not isinstance(s, Comment))
        for tnode in all_texts:
            stripped = tnode.strip()
            if len(stripped) < self.min_text_node_length:
                continue
            if self._is_forbidden_parent(tnode.parent):
                continue
            if self._is_in_a_tag(tnode):
                continue
            if not self._is_inside_content_area(tnode):
                continue
            text_nodes.append(tnode)
        return text_nodes

    def _fallback_insert(self, soup, content: str):
        body = soup.find('body')
        if not body:
            soup.append(BeautifulSoup(content, 'html.parser'))
        else:
            body.append(BeautifulSoup(content, 'html.parser'))

    def generate_links(self, max_links_per_page: int):
        # Создаём план перелинковки (URL откуда, куда и какой топик)
        plan = self._build_links_plan()
        logger.info(f"Схема: {self.scheme_name}. Всего пар ссылок для вставки: {len(plan)}")

        # Карта URL на их файлы для удобного доступа
        url_map = {u: (dom, rf) for dom, mapping in self.pages_by_domain.items() for rf, u in mapping.items()}

        # Счётчик вставленных ссылок по каждому файлу
        inserted_count: Dict[str, int] = {}

        # Множество для предотвращения вставки одинаковых пар URL
        already_inserted_pairs = set()

        # Начинаем перебор плана перелинковки
        for (urlA, urlB, topic) in plan:
            # Проверка на уже вставленную пару URL
            if (urlA, urlB) in already_inserted_pairs:
                logger.info(f"Пара {urlA} -> {urlB} уже была вставлена, пропускаем.")
                continue

            # Получаем случайный анкор для текущего топика
            anchor = random.choice(list(self.anchors.get(topic, [])))

            # Проверка, что URL-A существует
            if urlA not in url_map:
                logger.error(f"URL {urlA} не найден в url_map, пропускаем.")
                continue

            # Получаем путь к файлу для URL-A
            domA, rel_fileA = url_map[urlA]
            file_path = os.path.join(self.directory, domA, rel_fileA)

            # Проверка, что файл физически существует
            if not os.path.isfile(file_path):
                logger.error(f"Файл {file_path} не существует, пропускаем.")
                continue

            # Проверка, не превышено ли количество ссылок на страницу
            if inserted_count.get(file_path, 0) >= max_links_per_page:
                logger.info(f"В файл {file_path} уже вставлено максимум ссылок ({max_links_per_page}).")
                continue

            # Читаем содержимое файла с автоматическим определением кодировки
            try:
                with open(file_path, 'rb') as f:
                    raw_data = f.read()
                encoding = chardet.detect(raw_data).get('encoding') or 'utf-8'
                html_text = raw_data.decode(encoding, errors='replace')
            except Exception as e:
                logger.error(f"Ошибка чтения файла {file_path}: {e}")
                continue

            # Парсим HTML-контент
            soup = BeautifulSoup(html_text, 'html.parser')
            # Получаем текстовые узлы для вставки ссылок
            text_nodes = self._find_text_nodes_for_insertion(soup)
            random.shuffle(text_nodes)

            inserted = False  # Флаг успешной вставки ссылки

            # Перебираем текстовые узлы для вставки
            for node in text_nodes:
                # Проверка на максимальное количество ссылок
                if inserted_count.get(file_path, 0) >= max_links_per_page:
                    break

                # Проверка наличия анкора в текущем узле, чтобы избежать дублей
                if anchor.lower() in node.lower():
                    continue

                # Разбиваем текстовый узел на слова и пробелы
                tokens = re.split(r'(\s+)', str(node))
                if len(tokens) <= 1:
                    continue  # Если нет подходящих слов для вставки, пропускаем узел

                # Выбираем случайное место вставки ссылки
                idx = random.randint(0, len(tokens) - 1)

                # Создаём тег <a> безопасным способом без повторного парсинга HTML
                link_tag = soup.new_tag('a', href=urlB)
                link_tag.string = anchor

                # Аккуратно вставляем новый тег прямо в список элементов узла
                new_frag = []
                for i, token in enumerate(tokens):
                    if i == idx:
                        new_frag.append(link_tag)
                    new_frag.append(token)

                # Заменяем оригинальный текстовый узел новым фрагментом с ссылкой
                node.replace_with(*new_frag)

                inserted = True
                inserted_count[file_path] = inserted_count.get(file_path, 0) + 1
                already_inserted_pairs.add((urlA, urlB))  # Запоминаем вставленную пару ссылок

                # Логирование контекста вставки
                left_context = tokens[idx - 1] if idx > 0 else ""
                right_context = tokens[idx + 1] if idx < len(tokens) - 1 else ""
                logger.info(
                    f"[1-й этап] Вставлена ссылка:\n"
                    f"Файл: {file_path}\n"
                    f"Анкор: {anchor}\n"
                    f"Ссылка: {urlA} -> {urlB}\n"
                    f"Контекст: {left_context} <<<{anchor}>>> {right_context}"
                )
                break  # После вставки ссылки завершаем цикл по узлам страницы

            # Фоллбек-вставка, если не удалось вставить ссылку в текстовые узлы
            if (not inserted) and self.allow_fallback_insertion and inserted_count.get(file_path,
                                                                                       0) < max_links_per_page:
                fallback_html = f"<p><a href='{urlB}'>{anchor}</a></p>"
                self._fallback_insert(soup, fallback_html)
                inserted_count[file_path] = inserted_count.get(file_path, 0) + 1
                already_inserted_pairs.add((urlA, urlB))
                logger.info(f"[1-й этап] Выполнена фоллбек-вставка в файл {file_path}")

            # Сохраняем изменения обратно в файл после вставки
            if inserted or self.allow_fallback_insertion:
                try:
                    with open(file_path, "w", encoding="utf-8", errors="replace") as f:
                        f.write(str(soup))
                except Exception as e:
                    logger.error(f"Ошибка записи файла {file_path}: {e}")

        logger.info("Генерация ссылок (1-й этап) успешно завершена!")

###############################################################################
# Главное окно (GUI)
###############################################################################
class LinkGeneratorGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Генератор ссылок + Контент (SEO)")
        self.setGeometry(100, 100, 1200, 800)

        self.generator = None
        # Обратите внимание: здесь упоминается self.lm_studio,
        # но в данном файле класс LMStudioConnector вынесен во 2-й файл
        self.lm_studio = None

        main_layout = QVBoxLayout(self)

        help_btn = QPushButton("HELP")
        help_btn.clicked.connect(self.on_help)
        main_layout.addWidget(help_btn, alignment=Qt.AlignmentFlag.AlignRight)

        dir_layout = QHBoxLayout()
        self.dir_label = QLabel("Выбранная директория: нет")
        self.browse_btn = QPushButton("Обзор")
        self.browse_btn.clicked.connect(self.on_browse_dir)
        dir_layout.addWidget(self.dir_label)
        dir_layout.addWidget(self.browse_btn)
        main_layout.addLayout(dir_layout)

        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Выбор model_id для LM Studio:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(300)
        # Пустой при старте — заполнится при нажатии "Обновить"
        self.model_combo.addItem("-- Нажмите 'Обновить модели' --")
        model_layout.addWidget(self.model_combo)

        self.refresh_models_btn = QPushButton("Обновить модели")
        self.refresh_models_btn.clicked.connect(self.on_refresh_models)
        model_layout.addWidget(self.refresh_models_btn)

        self.load_model_btn = QPushButton("Подключиться к LM Studio")
        self.load_model_btn.clicked.connect(self.on_connect_lm_studio)
        model_layout.addWidget(self.load_model_btn)
        main_layout.addLayout(model_layout)

        top_h = QHBoxLayout()
        self.grabber_btn = QPushButton("Граббер")
        self.grabber_btn.clicked.connect(self.on_grabber)

        self.second_stage_btn = QPushButton("Внешние ссылки (2-й этап)")
        self.second_stage_btn.clicked.connect(self.on_second_stage)

        # После строки с self.second_stage_btn:
        self.cluster_link_btn = QPushButton("🔗 Кластерная перелинковка (SEO)")
        self.cluster_link_btn.clicked.connect(self.on_cluster_linking)

        top_h.addWidget(self.cluster_link_btn)

        self.content_btn = QPushButton("Контент (SEO) LM Studio")
        self.content_btn.clicked.connect(self.on_content)

        top_h.addWidget(self.grabber_btn)
        top_h.addWidget(self.second_stage_btn)
        top_h.addWidget(self.content_btn)
        main_layout.addLayout(top_h)

        an_h = QHBoxLayout()
        self.analyze_btn = QPushButton("Анализ страниц (1-й этап)")
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.clicked.connect(self.on_analyze)

        self.anchor_btn = QPushButton("Настройка анкоров (1-й этап)")
        self.anchor_btn.setEnabled(False)
        self.anchor_btn.clicked.connect(self.on_anchor)

        self.replace_txt_btn = QPushButton("Замена контента из txt и TITLE")
        self.replace_txt_btn.setEnabled(False)
        self.replace_txt_btn.clicked.connect(self.on_replace_from_txt)
        an_h.addWidget(self.replace_txt_btn)

        self.graph_btn = QPushButton("Графики")
        self.graph_btn.clicked.connect(self.show_graph_dialog)
        top_h.addWidget(self.graph_btn)

        self.give_urls_btn = QPushButton("MY FUCKING URL's")
        self.give_urls_btn.clicked.connect(self.on_give_me_urls)
        top_h.addWidget(self.give_urls_btn)

        # Кнопка Google Indexer
        self.indexer_btn = QPushButton("Google Indexing 🚀")
        self.indexer_btn.setStyleSheet("""
                    QPushButton { background-color: #1a7f37; color: white; font-weight: bold; }
                    QPushButton:hover { background-color: #2ea043; }
                """)
        self.indexer_btn.clicked.connect(self.on_google_indexer)
        top_h.addWidget(self.indexer_btn)

        # --- НАЧАЛО ВСТАВКИ ---
        self.pbn_analyze_btn = QPushButton("📊 PBN Analyzer (Fat Pages)")
        self.pbn_analyze_btn.clicked.connect(self.on_pbn_analyze)
        self.pbn_analyze_btn.setStyleSheet(
            "background-color: #4a3b69; color: white; font-weight: bold;")  # Выделим цветом
        top_h.addWidget(self.pbn_analyze_btn)
        # --- КОНЕЦ ВСТАВКИ ---

        an_h.addWidget(self.analyze_btn)
        an_h.addWidget(self.anchor_btn)
        main_layout.addLayout(an_h)

        sc_h = QHBoxLayout()
        sc_h.addWidget(QLabel("Схема перелинковки:"))
        self.scheme_combo = QComboBox()
        self.scheme_combo.addItems(["chain", "star-to-one", "star-from-one", "random"])
        sc_h.addWidget(self.scheme_combo)
        main_layout.addLayout(sc_h)

        param_h = QHBoxLayout()
        left_v = QVBoxLayout()
        self.min_len_spin = QSpinBox()
        self.min_len_spin.setRange(1, 2000)
        self.min_len_spin.setValue(40)
        left_v.addWidget(QLabel("Min text node length (1-й этап):"))
        left_v.addWidget(self.min_len_spin)
        right_v = QVBoxLayout()
        self.fallback_check = QCheckBox("Фолбэк вставка (1-й этап)")
        right_v.addWidget(self.fallback_check)
        param_h.addLayout(left_v)
        param_h.addLayout(right_v)
        main_layout.addLayout(param_h)

        self.result_view = QTextEdit()
        self.result_view.setReadOnly(True)
        main_layout.addWidget(QLabel("Результаты анализа (1-й этап):"))
        main_layout.addWidget(self.result_view)

        gen_h = QHBoxLayout()
        self.max_links_spin = QSpinBox()
        self.max_links_spin.setRange(1, 10)
        self.max_links_spin.setValue(3)
        self.gen_btn = QPushButton("Генерировать (1-й этап)")
        self.gen_btn.setEnabled(False)
        self.gen_btn.clicked.connect(self.on_generate_links)
        gen_h.addWidget(QLabel("Макс ссылок на стр. (1-й этап):"))
        gen_h.addWidget(self.max_links_spin)
        gen_h.addWidget(self.gen_btn)
        main_layout.addLayout(gen_h)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        main_layout.addWidget(QLabel("Лог:"))
        main_layout.addWidget(self.log_edit)

        self.setLayout(main_layout)
        self.spinner = SpinnerOverlay(self)
        self.spinner.hide()

        self.default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template_grab")
        if os.path.isdir(self.default_dir) and not self.generator:
            self.generator = LinkGenerator(self.default_dir)
            self.dir_label.setText(f"Выбранная директория: {self.default_dir}")
            self.analyze_btn.setEnabled(True)
            self.replace_txt_btn.setEnabled(True)
        ####################
        ##### GRAPHICS #####
        ####################

    def show_graph_dialog(self):
        if not self.generator:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите директорию с HTML!")
            return

        self.generator.analyze_pages()

        nodes = []
        edges = []

        url_to_node = {}

        for tablet in self.generator.relevant_pages.keys():
            nodes.append({
                "id": f"tablet-{tablet}",
                "label": tablet,
                "group": "tablet",
                "size": 30,
                "color": "#FFA500"
            })

        for tablet, urls in self.generator.relevant_pages.items():
            for url in urls:
                node_id = url.rstrip('/')
                url_to_node[url.rstrip('/')] = node_id
                nodes.append({
                    "id": node_id,
                    "label": urlparse(url).netloc.replace('www.', ''),
                    "url": url,
                    "group": "page",
                    "size": 15,
                    "color": "#87CEFA"
                })
                edges.append({
                    "from": f"tablet-{tablet}",
                    "to": node_id,
                    "arrows": "to",
                    "color": {"color": "#CCCCCC"},
                    "label": ""
                })

        actual_links = self._get_actual_links_from_html()

        for url_from, links_to in actual_links.items():
            for url_to, anchor in links_to:
                node_from = url_to_node.get(url_from.rstrip('/'))
                node_to = url_to_node.get(url_to.rstrip('/'))
                if node_from and node_to:
                    edges.append({
                        "from": node_from,
                        "to": node_to,
                        "arrows": "to",
                        "label": anchor,
                        "font": {"size": 10, "align": "middle"},
                        "color": {"color": "#AAAAAA"},
                    })

        dlg = GraphDialog(nodes, edges, self)
        dlg.exec()




    def _simplify_url(self, url):
        parsed = urlparse(url.lower().rstrip('/'))
        netloc = parsed.netloc.replace('www.', '')
        simplified = f"{netloc}{parsed.path}".rstrip('/')
        return simplified

    def _get_actual_links_from_html(self):
        actual_links = {}

        logging.info("===== Запуск подробного поиска перелинковки =====")

        # Создаем словарь синонимов таблеток
        all_synonyms = {}
        for key, synonym in keywords.items():
            all_synonyms.setdefault(synonym, set()).update([key.lower(), synonym.lower()])

        url_map = {
            self._simplify_url(u.rstrip('/')): u.rstrip('/')
            for dom, mapping in self.generator.pages_by_domain.items()
            for rf, u in mapping.items()
        }

        simplified_urls_set = set(url_map.keys())

        full_url_to_filepath = {
            u.rstrip('/'): os.path.join(self.generator.directory, dom, rel_file)
            for dom, mapping in self.generator.pages_by_domain.items()
            for rel_file, u in mapping.items()
        }

        # Составляем карту: URL → таблетка
        url_to_tablet = {}
        for dom, mapping in self.generator.pages_by_domain.items():
            for rel_file, url in mapping.items():
                file_path = os.path.join(self.generator.directory, dom, rel_file)
                if not os.path.isfile(file_path):
                    continue

                try:
                    with open(file_path, 'rb') as f:
                        raw_data = f.read()
                    encoding = chardet.detect(raw_data).get('encoding') or 'utf-8'
                    html_text = raw_data.decode(encoding, errors='replace')
                    soup = BeautifulSoup(html_text, 'html.parser')

                    title = soup.title.string.lower() if soup.title and soup.title.string else ''
                    for synonym, syn_set in all_synonyms.items():
                        if any(s in title for s in syn_set):
                            url_to_tablet[url.rstrip('/')] = synonym
                            break
                except:
                    continue

        # Анализируем ссылки
        for current_simple_url, current_full_url in url_map.items():
            file_path = full_url_to_filepath.get(current_full_url)
            logging.info(f"Обрабатываем URL: {current_full_url}")
            logging.info(f"Путь к файлу: {file_path}")

            if not file_path or current_full_url not in url_to_tablet:
                continue

            current_tablet_synonym = url_to_tablet[current_full_url]
            current_synonyms = all_synonyms[current_tablet_synonym]

            links_in_page = []

            try:
                with open(file_path, 'rb') as f:
                    raw_data = f.read()

                encoding = chardet.detect(raw_data).get('encoding') or 'utf-8'
                html_text = raw_data.decode(encoding, errors='replace')
                soup = BeautifulSoup(html_text, 'html.parser')

                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href'].strip()
                    anchor = a_tag.text.strip().lower()

                    absolute_href = urljoin(current_full_url + '/', href).rstrip('/')
                    simplified_href = self._simplify_url(absolute_href)

                    if simplified_href in simplified_urls_set and simplified_href != current_simple_url:
                        target_full_url = url_map[simplified_href]

                        if target_full_url in url_to_tablet:
                            target_tablet_synonym = url_to_tablet[target_full_url]

                            # СТРОГАЯ ПРОВЕРКА НА АНКОРЫ (должны содержать название таблеток)
                            if current_tablet_synonym == target_tablet_synonym:
                                if any(s in anchor for s in current_synonyms):
                                    links_in_page.append((target_full_url, anchor))
                                    logging.info(
                                        f"✅ Совпадение: {current_full_url} → {target_full_url} (анкор: '{anchor}')"
                                    )

                if links_in_page:
                    normalized_current_url = current_full_url.rstrip('/')
                    normalized_links = [(link.rstrip('/'), anchor) for link, anchor in links_in_page]
                    actual_links[normalized_current_url] = normalized_links
                    logging.info(f"📌 Страница {current_full_url} содержит {len(links_in_page)} перелинковок.")
                else:
                    logging.info(f"⚠️ Страница {current_full_url} не содержит подходящих ссылок.")

            except Exception as e:
                logging.error(f"Ошибка обработки файла {file_path}: {e}")

        logging.info("===== Завершение поиска перелинковки =====")
        logging.info(f"Всего страниц с перелинковкой: {len(actual_links)}")

        return actual_links

    def on_help(self):
        dlg = HelpDialog(self)
        dlg.exec()

    def on_browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Выберите директорию с HTML")
        if not d:
            return
        self.generator = LinkGenerator(d)
        self.dir_label.setText(f"Выбрана директория: {d}")
        self.analyze_btn.setEnabled(True)
        self.replace_txt_btn.setEnabled(True)
        self.update_log_view()

    def on_replace_from_txt(self):
        if not self.generator:
            QMessageBox.warning(self, "Ошибка", "Не выбрана директория!")
            return

        from content_replacer import ReplaceFromTxtDialog
        diag = ReplaceFromTxtDialog(content_dir=self.generator.directory, parent=self)
        diag.setModal(True)  # делаем модальным
        diag.raise_()  # выводим на передний план
        diag.activateWindow()  # даём фокус
        diag.exec()  # запускаем

    def on_connect_lm_studio(self):
        """
        Подключение к LM Studio.
        """
        from lm_studio_connector import LMStudioConnector
        chosen_model = self.model_combo.currentText()

        # Проверка, что выбрана реальная модель
        if not chosen_model or chosen_model.startswith("--"):
            QMessageBox.warning(self, "Ошибка",
                                "Сначала нажмите 'Обновить модели' и выберите модель из списка!")
            return

        try:
            self.lm_studio = LMStudioConnector(model_name=chosen_model, host="http://127.0.0.1:1234")
            QMessageBox.information(self, "OK", f"Подключились к LM Studio\nМодель: {chosen_model}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка подключения", f"Не удалось подключиться:\n{e}")
            self.lm_studio = None

    def fetch_lm_studio_models(self) -> list:
        """
        Получает список доступных моделей из LM Studio API.
        Возвращает список model_id или пустой список при ошибке.
        """
        import requests
        try:
            resp = requests.get("http://127.0.0.1:1234/v1/models", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            return [m.get("id", "") for m in models if m.get("id")]
        except Exception as e:
            logger.warning(f"Не удалось получить модели из LM Studio: {e}")
            return []

    def on_refresh_models(self):
        """
        Обновляет список моделей в ComboBox, запрашивая их из LM Studio.
        """
        models = self.fetch_lm_studio_models()
        self.model_combo.clear()
        if models:
            for m in models:
                self.model_combo.addItem(m)
            QMessageBox.information(self, "OK", f"Найдено моделей: {len(models)}")
        else:
            self.model_combo.addItem("-- LM Studio недоступен или нет моделей --")
            QMessageBox.warning(self, "Ошибка",
                                "Не удалось получить список моделей.\n"
                                "Проверьте, что LM Studio запущен на http://127.0.0.1:1234")

    def on_grabber(self):
        from grabber import UrlGrabberDialog  # новый файл
        dlg = UrlGrabberDialog(self)
        dlg.exec()

    def on_second_stage(self):
        try:
            if not self.generator:
                QMessageBox.warning(self, "Ошибка", "Сначала выберите директорию с HTML!")
                return
            dlg = SecondStageLinkDialog(self.generator.directory, self)
            dlg.exec()
        except Exception as e:
            logger.error(f"SecondStage error: {e}")
            QMessageBox.critical(self, "Ошибка", f"SecondStage: {e}")

    def on_content(self):
        if not self.lm_studio:
            QMessageBox.warning(self, "Ошибка", "Сначала подключитесь к LM Studio!")
            return
        if not self.generator:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите директорию с HTML!")
            return
        try:
            from content_generator import ContentRewriteDialog, PromptManager
            diag = ContentRewriteDialog(
                self.lm_studio,
                PromptManager(),
                content_dir=self.generator.directory,  # вот тут передаём текущую директорию
                parent=self
            )
            diag.exec()
        except Exception as e:
            logger.error(f"ContentRewriteDialog error: {e}")
            QMessageBox.critical(self, "Ошибка", f"Content: {e}")

    def on_analyze(self):
        if not self.generator:
            QMessageBox.warning(self, "Ошибка", "Не выбрана директория!")
            return

        self.spinner.setGeometry(self.rect())
        self.spinner.show()
        QApplication.processEvents()

        def on_finish(res):
            txt = "Результаты анализа (1-й этап):\n"
            for kw, arr in res.items():
                txt += f"{kw}: {len(arr)}\n"
            self.result_view.setText(txt)
            self.anchor_btn.setEnabled(True)
            self.update_log_view()
            self.spinner.hide()

        def on_error(msg):
            logger.error(f"Analyze error: {msg}")
            QMessageBox.critical(self, "Ошибка", "Analyze error")
            self.spinner.hide()

        self.worker = AnalyzePagesWorker(self.generator)
        self.worker.finished.connect(on_finish)
        self.worker.error.connect(on_error)
        self.worker.start()

    def on_anchor(self):
        if not self.generator:
            return
        try:
            dlg = AnchorDialog(set(keywords.keys()), self)
            if dlg.exec():
                self.generator.set_anchors(dlg.anchors_dict)
                self.gen_btn.setEnabled(True)
            self.update_log_view()
        except Exception as e:
            logger.error(f"Anchor error: {e}")
            QMessageBox.critical(self, "Ошибка", f"Anchor: {e}")

    def on_generate_links(self):
        if not self.generator:
            QMessageBox.warning(self, "Ошибка", "Нет генератора (1-й этап)!")
            return
        try:
            self.spinner.setGeometry(self.rect())
            self.spinner.show()
            QApplication.processEvents()
            scheme = self.scheme_combo.currentText()
            self.generator.set_link_scheme(scheme)
            if scheme in ["star-to-one", "star-from-one"]:
                for t, arr in self.generator.relevant_pages.items():
                    if len(arr) < 2:
                        continue
                    mp_dlg = MainPageChoiceDialog(arr, self)
                    mp_dlg.setWindowTitle(f"Главная страница для {t}")
                    if mp_dlg.exec():
                        if mp_dlg.main_url:
                            self.generator.set_main_url_for_topic(t, mp_dlg.main_url)

            self.generator.min_text_node_length = self.min_len_spin.value()
            self.generator.allow_fallback_insertion = self.fallback_check.isChecked()
            mx = self.max_links_spin.value()
            self.generator.generate_links(mx)
            self.update_log_view()
            QMessageBox.information(self, "OK", "Ссылки (1-й этап) сгенерированы!")
        except Exception as e:
            logger.error(f"Gen links error: {e}")
            QMessageBox.critical(self, "Ошибка", f"Gen links: {e}")
        finally:
            self.spinner.hide()

    def on_give_me_urls(self):
        if not self.generator:
            QMessageBox.warning(self, "Ошибка", "Не выбрана директория!")
            return

        # 2. Спросить у пользователя trackerKey (это оставляем тут!)
        tracker_dialog = QDialog(self)
        tracker_dialog.setWindowTitle("Выберите проект (trackerKey)")
        vbox = QVBoxLayout()
        label = QLabel("Для какого проекта формировать JSON?")
        vbox.addWidget(label)
        combo = QComboBox()
        combo.addItem("WPEAUDIT.COM")
        combo.addItem("WPDEBUG.ONLINE")
        vbox.addWidget(combo)
        ok_btn = QPushButton("OK")
        vbox.addWidget(ok_btn, alignment=Qt.AlignmentFlag.AlignRight)
        tracker_dialog.setLayout(vbox)

        chosen_tracker = {}

        def accept_tracker():
            sel = combo.currentText()
            if sel == "WPEAUDIT.COM":
                chosen_tracker['key'] = "brhgxppnjymh4qh91w5bvqnj7ycfmpds"
            elif sel == "WPDEBUG.ONLINE":
                chosen_tracker['key'] = "zwn9f3kPWgpyjzVC"
            tracker_dialog.accept()

        ok_btn.clicked.connect(accept_tracker)
        if not tracker_dialog.exec():
            return

        tracker_key = chosen_tracker.get('key')
        if not tracker_key:
            return

        self.spinner.setGeometry(self.rect())
        self.spinner.show()
        QApplication.processEvents()

        def on_finish(output):
            # Найди HTML-блок из вывода (ты печатаешь final_html в url_from_folder.py)
            # Обычно html начинается с <html> и заканчивается </html>
            # Получаем только HTML часть между разделителями
            html_result = output
            if "===START_HTML===" in output and "===END_HTML===" in output:
                html_result = output.split("===START_HTML===")[1].split("===END_HTML===")[0].strip()

            # НОКАШ и ТАБЛЕТКИ разбирай по plain-тексту (output, а не html_result)
            def extract_nocache_links(text):
                links = []
                in_block = False
                for line in text.splitlines():
                    if "ALL NO-CACHE LINKS" in line:
                        in_block = True
                        continue
                    # конец блока — если новая секция или полностью пустая строка (но пустые строки между ссылками бывают!)
                    if in_block and line.strip().startswith("ALL KEITARO JSON"):
                        break
                    # главное: брать только строки, содержащие и http, и "/?nocache"
                    if in_block and line.strip().startswith("http") and "/?nocache" in line:
                        links.append(line.strip())
                return links

            def extract_url_tablet_map(text):
                pairs = {}
                in_block = False
                for line in text.splitlines():
                    if "ALL FOUND URLS" in line:
                        in_block = True
                        continue
                    if in_block and (line.strip().startswith("---") or not line.strip()):
                        if pairs:
                            break
                        continue
                    if in_block and " - " in line:
                        url, pill = line.strip().split(" - ", 1)
                        url_base = url.strip().rstrip("/")
                        pairs[url_base] = pill.strip()
                return pairs

            nocache_links = extract_nocache_links(output)
            url_tablet_map = extract_url_tablet_map(output)

            dlg = UrlsResultDialog(html_result, nocache_links, url_tablet_map, self)
            dlg.exec()
            self.spinner.hide()

        def on_error(msg):
            QMessageBox.critical(self, "Ошибка", f"GiveMeUrls: {msg}")
            self.spinner.hide()

        self.generator.tracker_key = tracker_key
        self.worker = GiveMeUrlsWorker(self.generator)
        self.worker.tracker_key = tracker_key  # передаём выбранный ключ
        self.worker.finished.connect(on_finish)
        self.worker.error.connect(on_error)
        self.worker.start()

    def update_log_view(self):
        try:
            with open(log_filename, 'r', encoding='utf-8') as f:
                text = f.read()
            self.log_edit.setText(text)
            self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
        except:
            pass

    def on_cluster_linking(self):
        dialog = SEOClusterDialog(self.generator.directory, parent=self)
        dialog.exec()

    def on_pbn_analyze(self):
        """Запуск PBN анализатора (Метод 4)"""
        if not self.generator:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите директорию с HTML!")
            return

        # Передаем путь к папке из текущего генератора
        dlg = PbnAnalyzerDialog(self.generator.directory, self)
        dlg.exec()

    def on_google_indexer(self):
        """Открывает окно профессионального индексатора"""
        try:
            dlg = GoogleIndexerDialog(self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось запустить индексатор:\n{e}")

class UrlsResultDialog(QDialog):
    def __init__(self, html_text, nocache_links=None, tablet_map=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Результаты: give me urls")
        self.setMinimumWidth(1100)
        self.setMinimumHeight(780)
        self.setStyleSheet("""
            QDialog { background: #23272e; color: #e4e6eb; }
            QPushButton { background: #222e3c; color: #e4e6eb; border: 1.3px solid #30353b; border-radius: 6px; padding: 8px 18px; font-weight: 500; }
            QPushButton:hover { background: #2e3d4e; }
        """)

        layout = QVBoxLayout(self)
        # Заменяем QTextBrowser на QWebEngineView
        self.browser = QWebEngineView(self)
        self.browser.setHtml(html_text)
        layout.addWidget(self.browser)

        # --- Кнопки ---
        hbox = QHBoxLayout()
        self.copy_btn = QPushButton("Копировать всё")
        self.copy_btn.clicked.connect(self.copy_all)
        hbox.addWidget(self.copy_btn)

        self.nocache_btn = QPushButton("СНОУКЕШИТЬ ВСЕ")
        self.nocache_btn.clicked.connect(lambda: self.run_nocache_check(nocache_links, tablet_map))
        hbox.addWidget(self.nocache_btn)

        self.prints_btn = QPushButton("ПРОВЕРИТЬ ПРИНТЫ")
        self.prints_btn.clicked.connect(lambda: self.run_prints_check(nocache_links))
        hbox.addWidget(self.prints_btn)

        hbox.addStretch(1)
        layout.addLayout(hbox)

        self.setLayout(layout)

    def run_prints_check(self, nocache_links):
        if not nocache_links:
            QMessageBox.warning(self, "Нет данных", "Нет ссылок для проверки.")
            return

        dlg = PrintCheckTableDialog(nocache_links, self)
        dlg.exec()


    def run_nocache_check(self, nocache_links, tablet_map):
        if not nocache_links:
            QMessageBox.warning(self, "Нет данных", "Нет ссылок для проверки.")
            return
        dlg = NoCacheTableDialog(nocache_links, tablet_map, self)
        dlg.exec()

    def copy_all(self):
        # Получить ВЕСЬ видимый текст из QWebEngineView:
        self.browser.page().toPlainText(self._set_clipboard)

    def _set_clipboard(self, text):
        QApplication.clipboard().setText(text)

    # show_nocache_table оставляю без изменений (не зависит от рендера результата)
    def show_nocache_table(self, results):
        dlg = QDialog(self)
        dlg.setWindowTitle("NOCACHE ПРОВЕРКА")
        dlg.setMinimumSize(1100, 700)
        vbox = QVBoxLayout(dlg)
        tbl = QTableWidget(len(results), 4)
        tbl.setHorizontalHeaderLabels(["URL", "TITLE", "STATUS", "TABLET"])
        for i, (url, title, status, pill) in enumerate(results):
            tbl.setItem(i, 0, QTableWidgetItem(url))
            tbl.setItem(i, 1, QTableWidgetItem(title))
            item = QTableWidgetItem(status)
            if status == "OK":
                item.setForeground(Qt.GlobalColor.green)
            else:
                item.setForeground(Qt.GlobalColor.red)
            tbl.setItem(i, 2, item)
            tbl.setItem(i, 3, QTableWidgetItem(pill))
        tbl.resizeColumnsToContents()
        vbox.addWidget(tbl)
        dlg.setLayout(vbox)
        dlg.exec()
        self.nocache_btn.setEnabled(True)


###############################################################################
# main()
###############################################################################
def main():
    try:
        import sys
        app = QApplication(sys.argv)
        styles = Styles()
        app.setStyleSheet(styles.get_dark())
        logger.info("Запуск программы")

        global main_window
        main_window = None

        def show_main():
            global main_window
            main_window = LinkGeneratorGUI()
            main_window.show()
            qr = main_window.frameGeometry()
            cp = app.primaryScreen().availableGeometry().center()
            qr.moveCenter(cp)
            main_window.move(qr.topLeft())

        splash = MatrixSplashScreen(msec=2000)
        splash.set_on_finish(show_main)
        splash.show()

        rc = app.exec()
        logger.info("Программа завершена")
        sys.exit(rc)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        QMessageBox.critical(None, "Критическая ошибка", f"Ошибка:\n{e}")
        raise


if __name__ == "__main__":
    main()

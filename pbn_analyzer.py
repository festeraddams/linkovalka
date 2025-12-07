"""
PBN Analyzer — Advanced Donor Page Evaluator
Features:
- WP REST API parsing (posts, pages, categories)
- Google Index Check with CAPTCHA handling
- Response time, SSL, Last Modified, Robots.txt analysis
- Visual scoring with color coding
"""
import csv
import re
import time
from datetime import datetime
from urllib.parse import urlparse, urljoin
from styles import Styles
import requests
import urllib3
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QAbstractTableModel, QUrl, QTimer
from PyQt6.QtGui import QDesktopServices, QFont, QColor, QBrush, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTableView, QPushButton, QHBoxLayout,
    QLabel, QHeaderView, QFileDialog, QMessageBox, QTextEdit,
    QSplitter, QTabWidget, QWidget, QCheckBox, QProgressBar,
    QLineEdit, QGroupBox, QGridLayout, QApplication
)
from bs4 import BeautifulSoup
from grabber import UrlGrabberDialog

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# =============================================================================
# DATA STRUCTURE
# =============================================================================
class PbnPageData:
    """Структура данных для страницы-донора"""

    def __init__(self, domain, post_type, url, title, word_count, obl):
        self.checked = False
        self.domain = domain
        self.post_type = post_type  # post, page, category
        self.url = url
        self.title = title
        self.word_count = word_count
        self.obl = obl  # Outbound Links
        self.inlinks = 0
        self.score = 0.0
        # Новые поля
        self.index_status = None  # None=не проверено, True=в индексе, False=не в индексе
        self.last_modified = None  # Дата последнего изменения
        self.response_time = 0.0  # Время ответа в секундах
        self.has_ssl = True
        self.robots_blocked = False  # Закрыт ли в robots.txt


# =============================================================================
# TABLE MODEL
# =============================================================================
class PbnTableModel(QAbstractTableModel):
    """Модель таблицы с поддержкой индексации и расширенных метрик"""

    def __init__(self, data=None):
        super().__init__()
        self._data = data or []
        self._headers = [
            "✔", "Type", "📌URL", "👉Title", "Words",
            "OBL", "Inlinks", "🎯Score", "📊Index", "⏱ms", "🔒SSL"
        ]
        self._tooltips = {
            "✔": "Отметьте для отправки в Граббер",
            "Type": "POST / PAGE / CATEGORY",
            "Words": "Кол-во слов. Больше = лучше.",
            "OBL": "Внешние ссылки. Меньше = лучше.",
            "Inlinks": "Внутренние ссылки на эту статью.",
            "🎯Score": "Рейтинг качества донора.",
            "📊Index": "Статус индексации Google (кликните ПКМ для проверки)",
            "⏱ms": "Время ответа сервера (мс)",
            "🔒SSL": "HTTPS сертификат"
        }

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self._headers)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = super().flags(index)
        if index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        return flags

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        item = self._data[index.row()]
        col = index.column()

        # Чекбоксы в 0-й колонке
        if role == Qt.ItemDataRole.CheckStateRole and col == 0:
            return Qt.CheckState.Checked if item.checked else Qt.CheckState.Unchecked

        # Шрифт для URL (подчёркнутый)
        if role == Qt.ItemDataRole.FontRole:
            if col == 2:
                font = QFont()
                font.setUnderline(True)
                return font
            # Жирный для проиндексированных
            if col == 8 and item.index_status is True:
                font = QFont()
                font.setBold(True)
                return font

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 1:
                return item.post_type.upper()
            if col == 2:
                return item.url
            if col == 3:
                return item.title
            if col == 4:
                return str(item.word_count)
            if col == 5:
                return str(item.obl)
            if col == 6:
                return str(item.inlinks)
            if col == 7:
                return f"{item.score:.2f}"
            if col == 8:
                if item.index_status is None:
                    return "—"
                return "✅ YES" if item.index_status else "❌ NO"
            if col == 9:
                return f"{int(item.response_time * 1000)}" if item.response_time > 0 else "—"
            if col == 10:
                if item.robots_blocked:
                    return "🚫BLOCKED"
                return "✓" if item.has_ssl else "✗"

        if role == Qt.ItemDataRole.ForegroundRole:
            # URL — cyan
            if col == 2:
                return QBrush(QColor("#00bcd4"))
            # Score coloring
            if col == 7:
                if item.score > 15:
                    return QBrush(QColor("#4caf50"))
                if item.score < 0:
                    return QBrush(QColor("#f44336"))
            # OBL — красный если много
            if col == 5 and item.obl > 3:
                return QBrush(QColor("#ff5722"))
            # Type coloring
            if col == 1:
                if item.post_type == 'post':
                    return QBrush(QColor("#00bcd4"))
                elif item.post_type == 'page':
                    return QBrush(QColor("#ffeb3b"))
                else:  # category
                    return QBrush(QColor("#9c27b0"))
            # Index status coloring
            if col == 8:
                if item.index_status is True:
                    return QBrush(QColor("#4caf50"))  # Зелёный
                elif item.index_status is False:
                    return QBrush(QColor("#f44336"))  # Красный
            # SSL
            if col == 10:
                if item.robots_blocked:
                    return QBrush(QColor("#ff5722"))
                return QBrush(QColor("#4caf50")) if item.has_ssl else QBrush(QColor("#f44336"))
            # Response time — если медленно (>2s)
            if col == 9 and item.response_time > 2.0:
                return QBrush(QColor("#ff9800"))

        # Background для всей строки если в индексе
        if role == Qt.ItemDataRole.BackgroundRole:
            if item.index_status is True:
                return QBrush(QColor(76, 175, 80, 30))  # Лёгкий зелёный фон
            elif item.index_status is False:
                return QBrush(QColor(244, 67, 54, 20))  # Лёгкий красный фон

        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            item = self._data[index.row()]
            item.checked = (value == Qt.CheckState.Checked.value)
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            name = self._headers[section]
            if role == Qt.ItemDataRole.DisplayRole:
                return name
            if role == Qt.ItemDataRole.ToolTipRole:
                return self._tooltips.get(name, name)
        return None

    def sort(self, column, order):
        self.layoutAboutToBeChanged.emit()
        reverse = (order == Qt.SortOrder.DescendingOrder)

        key_map = {
            1: lambda x: x.post_type,
            2: lambda x: x.url,
            3: lambda x: x.title,
            4: lambda x: x.word_count,
            5: lambda x: x.obl,
            6: lambda x: x.inlinks,
            7: lambda x: x.score,
            8: lambda x: (0 if x.index_status is None else (1 if x.index_status else 2)),
            9: lambda x: x.response_time,
            10: lambda x: (0 if x.robots_blocked else (1 if x.has_ssl else 2))
        }
        key_func = key_map.get(column, lambda x: x.score)
        self._data.sort(key=key_func, reverse=reverse)
        self.layoutChanged.emit()

    def update_item(self, row):
        """Обновить отображение конкретной строки"""
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right)

    def get_data(self):
        return self._data


# =============================================================================
# API WORKER — Загрузка данных с WP REST API
# =============================================================================
class PbnApiWorker(QThread):
    """Загружает данные с WordPress REST API"""
    finished = pyqtSignal(dict, dict)
    progress = pyqtSignal(str)

    def __init__(self, domains, fetch_posts=True, fetch_pages=True, fetch_categories=False):
        super().__init__()
        self.domains = domains
        self.fetch_posts = fetch_posts
        self.fetch_pages = fetch_pages
        self.fetch_categories = fetch_categories
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def _fetch_json(self, domain, endpoint, max_pages=3):
        """Универсальный метод получения JSON из WP API"""
        results = []
        page = 1
        base_url = f"https://{domain}/wp-json/wp/v2/{endpoint}"

        while page <= max_pages:
            if self._stop_flag:
                break
            try:
                url = f"{base_url}?per_page=100&page={page}"
                start_time = time.time()
                r = requests.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=15,
                    verify=False
                )
                response_time = time.time() - start_time

                if r.status_code != 200:
                    break

                data = r.json()
                if not data or not isinstance(data, list):
                    break

                # Добавляем время ответа к каждому элементу
                for item in data:
                    item['_response_time'] = response_time
                    item['_has_ssl'] = base_url.startswith('https')

                results.extend(data)
                if len(data) < 100:
                    break
                page += 1
            except Exception as e:
                print(f"API Error [{domain}/{endpoint}]: {e}")
                break
        return results

    def _clean_url(self, url):
        return url.strip().rstrip('/')

    def _check_robots_txt(self, domain):
        """Проверяем robots.txt на наличие Disallow: /"""
        try:
            r = requests.get(
                f"https://{domain}/robots.txt",
                headers={"User-Agent": self.user_agent},
                timeout=5,
                verify=False
            )
            if r.status_code == 200:
                content = r.text.lower()
                # Грубая проверка на полную блокировку
                if 'disallow: /' in content and 'disallow: /wp-' not in content:
                    # Может быть Disallow: / для всех
                    lines = content.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line == 'disallow: /':
                            return True
        except:
            pass
        return False

    def run(self):
        final_results_by_domain = {}
        stats = {'posts': 0, 'pages': 0, 'categories': 0}

        total_domains = len(self.domains)

        for i, domain in enumerate(self.domains):
            if self._stop_flag:
                break

            domain = domain.strip().replace("http://", "").replace("https://", "").strip("/")
            if not domain:
                continue

            self.progress.emit(f"[{i + 1}/{total_domains}] Анализ: {domain}...")

            domain_pages_data = []
            internal_links_graph = []
            url_to_page_map = {}

            try:
                # Проверяем robots.txt
                robots_blocked = self._check_robots_txt(domain)

                # 1. Posts
                if self.fetch_posts:
                    posts = self._fetch_json(domain, "posts")
                    self._process_items(
                        domain, "post", posts, domain_pages_data,
                        internal_links_graph, url_to_page_map, stats, robots_blocked
                    )

                # 2. Pages
                if self.fetch_pages:
                    pages = self._fetch_json(domain, "pages")
                    self._process_items(
                        domain, "page", pages, domain_pages_data,
                        internal_links_graph, url_to_page_map, stats, robots_blocked
                    )

                # 3. Categories
                if self.fetch_categories:
                    categories = self._fetch_json(domain, "categories")
                    self._process_categories(
                        domain, categories, domain_pages_data, stats, robots_blocked
                    )

                # 4. Расчёт Inlinks
                for src, target in internal_links_graph:
                    if target in url_to_page_map and src != target:
                        url_to_page_map[target].inlinks += 1

                # 5. Расчёт Score
                for p in domain_pages_data:
                    score = (p.word_count / 1000.0) + (p.inlinks * 3.0) - (p.obl * 5.0)
                    # Бонус за SSL
                    if p.has_ssl:
                        score += 1.0
                    # Штраф за robots блокировку
                    if p.robots_blocked:
                        score -= 10.0
                    # Штраф за медленный ответ
                    if p.response_time > 3.0:
                        score -= 2.0
                    p.score = round(score, 2)

                # Сортировка
                domain_pages_data.sort(key=lambda x: x.score, reverse=True)

                if domain_pages_data:
                    final_results_by_domain[domain] = domain_pages_data

            except Exception as e:
                print(f"Error processing {domain}: {e}")
                continue

        self.finished.emit(final_results_by_domain, stats)

    def _process_items(self, domain, p_type, items, data_list, graph, mapper, stats, robots_blocked):
        """Обработка постов/страниц"""
        for item in items:
            try:
                url = item.get('link', '')
                title_data = item.get('title', {})
                title = title_data.get('rendered', 'No Title') if isinstance(title_data, dict) else str(title_data)
                content = item.get('content', {}).get('rendered', '')

                if not url:
                    continue

                stats[p_type + 's'] += 1

                # Парсим контент
                soup = BeautifulSoup(content, 'html.parser')
                text = soup.get_text(separator=' ', strip=True)
                word_count = len(text.split())

                # Считаем внешние ссылки
                obl = 0
                links = soup.find_all('a', href=True)
                for link in links:
                    href = link['href'].strip()
                    if not href or href.startswith('#'):
                        continue
                    abs_href = urljoin(url, href)

                    ph = urlparse(abs_href)
                    pb = urlparse(url)

                    if ph.netloc and ph.netloc.replace('www.', '') != pb.netloc.replace('www.', ''):
                        obl += 1
                    else:
                        graph.append((self._clean_url(url), self._clean_url(abs_href)))

                # Создаём объект
                obj = PbnPageData(domain, p_type, url, title, word_count, obl)
                obj.response_time = item.get('_response_time', 0)
                obj.has_ssl = item.get('_has_ssl', True)
                obj.robots_blocked = robots_blocked

                # Last Modified
                modified = item.get('modified', item.get('date', ''))
                if modified:
                    try:
                        obj.last_modified = datetime.fromisoformat(modified.replace('Z', '+00:00'))
                    except:
                        pass

                data_list.append(obj)
                mapper[self._clean_url(url)] = obj
            except Exception as e:
                print(f"Item processing error: {e}")
                pass

    def _process_categories(self, domain, categories, data_list, stats, robots_blocked):
        """Обработка категорий"""
        for cat in categories:
            try:
                url = cat.get('link', '')
                name = cat.get('name', 'No Name')
                description = cat.get('description', '')
                count = cat.get('count', 0)

                if not url or count == 0:
                    continue

                stats['categories'] += 1

                # Для категорий word_count = длина описания
                word_count = len(description.split()) if description else 0

                obj = PbnPageData(domain, "category", url, name, word_count, 0)
                obj.has_ssl = url.startswith('https')
                obj.robots_blocked = robots_blocked
                obj.inlinks = count  # Используем count как inlinks

                data_list.append(obj)
            except:
                pass


# =============================================================================
# INDEX CHECK WORKER — Проверка индексации Google
# =============================================================================
class IndexCheckWorker(QThread):
    """Проверяет индексацию URL в Google"""
    progress = pyqtSignal(int, int, str)  # current, total, status
    item_checked = pyqtSignal(int, bool)  # row, is_indexed
    captcha_required = pyqtSignal(str, str)  # captcha_url, page_html
    finished = pyqtSignal()

    def __init__(self, items_with_rows):
        """items_with_rows: список кортежей (row_index, PbnPageData)"""
        super().__init__()
        self.items = items_with_rows
        self._stop_flag = False
        self._captcha_response = None
        self._waiting_captcha = False
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })

    def stop(self):
        self._stop_flag = True

    def set_captcha_response(self, response):
        """Установить ответ на капчу"""
        self._captcha_response = response
        self._waiting_captcha = False

    def _check_google_index(self, url):
        """
        Проверяет, есть ли URL в индексе Google.
        Возвращает: True (в индексе), False (не в индексе), 'captcha' (требуется капча)
        """
        search_url = f"https://www.google.com/search?q=site:{url}&num=1"

        try:
            r = self.session.get(search_url, timeout=15, verify=False)
            html = r.text.lower()

            # Проверка на капчу
            if 'captcha' in html or 'unusual traffic' in html or '/sorry/' in r.url:
                return 'captcha', r.text

            # Проверяем результаты
            # Google показывает "did not match any documents" если ничего не найдено
            if 'did not match any documents' in html:
                return False, None

            # Проверяем наличие результатов
            # Ищем ссылку на сайт в результатах
            domain = urlparse(url).netloc.replace('www.', '')
            if domain in html:
                return True, None

            # Альтернативная проверка — ищем div с результатами
            if 'class="g"' in html or 'data-hveid' in html:
                # Есть какие-то результаты
                soup = BeautifulSoup(r.text, 'html.parser')
                results = soup.find_all('div', class_='g')
                for res in results:
                    links = res.find_all('a', href=True)
                    for link in links:
                        href = link.get('href', '')
                        if domain in href:
                            return True, None
                return False, None

            # По умолчанию считаем что не в индексе если не нашли явных признаков
            return False, None

        except Exception as e:
            print(f"Google check error: {e}")
            return None, None

    def run(self):
        total = len(self.items)

        for i, (row, item) in enumerate(self.items):
            if self._stop_flag:
                break

            self.progress.emit(i + 1, total, f"Проверка: {item.url[:50]}...")

            result, html = self._check_google_index(item.url)

            if result == 'captcha':
                # Запрашиваем решение капчи
                self.captcha_required.emit(item.url, html)
                self._waiting_captcha = True

                # Ждём ответа на капчу (максимум 120 сек)
                wait_time = 0
                while self._waiting_captcha and wait_time < 120:
                    time.sleep(0.5)
                    wait_time += 0.5
                    if self._stop_flag:
                        break

                # После капчи пробуем снова
                if self._captcha_response:
                    result, _ = self._check_google_index(item.url)
                    self._captcha_response = None

            if result is not None and result != 'captcha':
                item.index_status = result
                self.item_checked.emit(row, result)

            # Задержка между запросами чтобы не забанили
            time.sleep(2.0)

        self.finished.emit()


# =============================================================================
# CAPTCHA DIALOG — Окно для ввода капчи
# =============================================================================
class CaptchaDialog(QDialog):
    """Диалог для отображения и решения капчи Google"""

    def __init__(self, url, html_content, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🤖 Google CAPTCHA Required")
        self.setMinimumSize(500, 400)
        self.response = None

        layout = QVBoxLayout(self)

        # Информация
        info = QLabel(f"Google требует подтверждение для:\n{url}")
        info.setWordWrap(True)
        info.setStyleSheet("color: #ff9800; font-weight: bold; padding: 10px;")
        layout.addWidget(info)

        # Инструкция
        instruction = QLabel(
            "Откройте ссылку ниже в браузере, пройдите капчу, "
            "затем нажмите 'Готово'.\n\n"
            "Или скопируйте URL и вставьте в браузер вручную."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        # URL для копирования
        url_box = QGroupBox("URL для проверки в браузере:")
        url_layout = QVBoxLayout(url_box)

        self.url_edit = QLineEdit(f"https://www.google.com/search?q=site:{url}")
        self.url_edit.setReadOnly(True)
        self.url_edit.setStyleSheet("background: #1e1e1e; color: #00bcd4; padding: 8px;")
        url_layout.addWidget(self.url_edit)

        copy_btn = QPushButton("📋 Копировать URL")
        copy_btn.clicked.connect(self._copy_url)
        url_layout.addWidget(copy_btn)

        open_btn = QPushButton("🌐 Открыть в браузере")
        open_btn.clicked.connect(self._open_browser)
        url_layout.addWidget(open_btn)

        layout.addWidget(url_box)

        # Кнопки
        btn_layout = QHBoxLayout()

        done_btn = QPushButton("✅ Готово (капча пройдена)")
        done_btn.setStyleSheet("background: #4caf50; font-weight: bold; padding: 10px;")
        done_btn.clicked.connect(self._on_done)

        skip_btn = QPushButton("⏭ Пропустить")
        skip_btn.clicked.connect(self._on_skip)

        cancel_btn = QPushButton("❌ Отмена (остановить)")
        cancel_btn.setStyleSheet("background: #f44336;")
        cancel_btn.clicked.connect(self._on_cancel)

        btn_layout.addWidget(done_btn)
        btn_layout.addWidget(skip_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _copy_url(self):
        QApplication.clipboard().setText(self.url_edit.text())
        QMessageBox.information(self, "OK", "URL скопирован!")

    def _open_browser(self):
        QDesktopServices.openUrl(QUrl(self.url_edit.text()))

    def _on_done(self):
        self.response = "done"
        self.accept()

    def _on_skip(self):
        self.response = "skip"
        self.accept()

    def _on_cancel(self):
        self.response = "cancel"
        self.reject()


# =============================================================================
# MAIN DIALOG — Основное окно анализатора
# =============================================================================
class PbnAnalyzerDialog(QDialog):
    """Главное окно PBN Analyzer"""

    def __init__(self, ignored_dir=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔍 PBN Multi-Tab Analyzer")
        self.resize(1400, 900)

        # Применяем глобальный стиль
        self.styles = Styles()
        self.setStyleSheet(self.styles.get_dark())

        self.worker = None
        self.index_worker = None
        self.results_cache = {}
        self.table_models = {}  # domain -> model

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ===== TOP SECTION: Ввод доменов и настройки =====
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # Левая часть — ввод доменов
        input_group = QGroupBox("📋 Домены")
        input_layout = QVBoxLayout(input_group)

        self.domains_edit = QTextEdit()
        self.domains_edit.setPlaceholderText("site1.com\nsite2.com\nsite3.com")
        self.domains_edit.setMaximumHeight(120)
        input_layout.addWidget(self.domains_edit)

        load_btn = QPushButton("📂 Загрузить .txt")
        load_btn.clicked.connect(self._load_txt)
        input_layout.addWidget(load_btn)

        top_layout.addWidget(input_group, stretch=2)

        # Правая часть — настройки фильтров
        settings_group = QGroupBox("⚙️ Настройки")
        settings_layout = QGridLayout(settings_group)

        # Чекбоксы типов контента
        self.cb_posts = QCheckBox("📝 Posts")
        self.cb_posts.setChecked(True)
        self.cb_pages = QCheckBox("📄 Pages")
        self.cb_pages.setChecked(True)
        self.cb_categories = QCheckBox("📁 Categories")
        self.cb_categories.setChecked(False)

        settings_layout.addWidget(self.cb_posts, 0, 0)
        settings_layout.addWidget(self.cb_pages, 0, 1)
        settings_layout.addWidget(self.cb_categories, 0, 2)

        # Кнопка запуска
        self.btn_run = QPushButton("🚀 АНАЛИЗ")
        self.btn_run.setStyleSheet(
            "background-color: #2ea043; color: white; "
            "font-weight: bold; padding: 12px; font-size: 14px;"
        )
        self.btn_run.clicked.connect(self._start_analysis)
        settings_layout.addWidget(self.btn_run, 1, 0, 1, 2)

        self.btn_stop = QPushButton("⏹ СТОП")
        self.btn_stop.setStyleSheet("background-color: #d32f2f; padding: 12px;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_analysis)
        settings_layout.addWidget(self.btn_stop, 1, 2)

        top_layout.addWidget(settings_group, stretch=1)
        layout.addWidget(top_widget)

        # ===== STATS & FORMULA =====
        stats_layout = QHBoxLayout()

        self.stats_lbl = QLabel("Ожидание...")
        self.stats_lbl.setStyleSheet(
            "font-weight: bold; color: #61afef; font-size: 14px; padding: 5px;"
        )
        stats_layout.addWidget(self.stats_lbl)

        stats_layout.addStretch()

        formula_text = "Score = (Words/1000) + (Inlinks×3) - (OBL×5) + SSL - Robots"
        self.formula_lbl = QLabel(formula_text)
        self.formula_lbl.setToolTip("Формула расчёта качества донора")
        self.formula_lbl.setStyleSheet("""
            QLabel { color: #61afef; font-weight: bold; font-size: 13px; padding: 5px; }
            QLabel:hover { color: #ffffff; }
        """)
        stats_layout.addWidget(self.formula_lbl)

        layout.addLayout(stats_layout)

        # ===== PROGRESS BAR =====
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar { 
                background: #1e1e1e; 
                border: 1px solid #474747; 
                text-align: center;
                color: #ffffff;
            }
            QProgressBar::chunk { background: #007acc; }
        """)
        layout.addWidget(self.progress_bar)

        # ===== TABS =====
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, stretch=4)

        # ===== BOTTOM BUTTONS =====
        btn_layout = QHBoxLayout()

        self.btn_check_index = QPushButton("🔎 Проверить индекс (выбранные)")
        self.btn_check_index.setEnabled(False)
        self.btn_check_index.setStyleSheet(
            "background-color: #0288d1; color: white; font-weight: bold; padding: 8px;"
        )
        self.btn_check_index.clicked.connect(self._check_index_selected)

        self.btn_check_all_index = QPushButton("🔎 Проверить ВСЕ")
        self.btn_check_all_index.setEnabled(False)
        self.btn_check_all_index.clicked.connect(self._check_index_all)

        self.btn_grab = QPushButton("📥 Отправить в Граббер")
        self.btn_grab.setEnabled(False)
        self.btn_grab.setStyleSheet(
            "background-color: #6a4a9c; color: white; font-weight: bold; padding: 8px;"
        )
        self.btn_grab.clicked.connect(self._send_to_grabber)

        self.btn_export = QPushButton("💾 Сохранить CSV")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_csv)

        btn_layout.addWidget(self.btn_check_index)
        btn_layout.addWidget(self.btn_check_all_index)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_grab)
        btn_layout.addWidget(self.btn_export)
        layout.addLayout(btn_layout)

    def _load_txt(self):
        f, _ = QFileDialog.getOpenFileName(self, "Файл", "", "*.txt")
        if f:
            with open(f, "r", encoding="utf-8") as file:
                self.domains_edit.setText(file.read())

    def _start_analysis(self):
        raw = self.domains_edit.toPlainText()
        domains = [d.strip() for d in raw.splitlines() if d.strip()]
        if not domains:
            QMessageBox.warning(self, "Ошибка", "Введите хотя бы один домен!")
            return

        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.tabs.clear()
        self.results_cache = {}
        self.table_models = {}
        self.stats_lbl.setText("Запуск воркера...")

        self.worker = PbnApiWorker(
            domains,
            fetch_posts=self.cb_posts.isChecked(),
            fetch_pages=self.cb_pages.isChecked(),
            fetch_categories=self.cb_categories.isChecked()
        )
        self.worker.progress.connect(self.stats_lbl.setText)
        self.worker.finished.connect(self._on_analysis_finished)
        self.worker.start()

    def _stop_analysis(self):
        if self.worker:
            self.worker.stop()
        if self.index_worker:
            self.index_worker.stop()
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.stats_lbl.setText("Остановлено.")

    def _on_analysis_finished(self, results, stats):
        self.results_cache = results

        info_text = (
            f"ГОТОВО. | Posts: {stats['posts']} | "
            f"Pages: {stats['pages']} | Categories: {stats['categories']}"
        )
        self.stats_lbl.setText(info_text)

        if not results:
            QMessageBox.warning(
                self, "Пусто",
                "Ничего не найдено. Проверьте домены или доступность WP JSON API."
            )
            self.btn_run.setEnabled(True)
            self.btn_stop.setEnabled(False)
            return

        # Создаём вкладки
        for domain, data_list in results.items():
            self._create_tab(domain, data_list)

        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_export.setEnabled(True)
        self.btn_grab.setEnabled(True)
        self.btn_check_index.setEnabled(True)
        self.btn_check_all_index.setEnabled(True)

    def _create_tab(self, domain, data_list):
        """Создаёт вкладку с таблицей для домена"""
        tab = QWidget()
        vbox = QVBoxLayout(tab)
        vbox.setContentsMargins(2, 2, 2, 2)

        table = QTableView()
        model = PbnTableModel(data_list)
        self.table_models[domain] = model

        table.setModel(model)
        table.setSortingEnabled(True)
        table.setWordWrap(False)
        table.setAlternatingRowColors(True)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        table.doubleClicked.connect(self._on_table_double_click)

        # Настройка колонок
        h = table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # Checkbox
        table.setColumnWidth(0, 40)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Type
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # URL
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Title
        for c in range(4, 11):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        vbox.addWidget(table)

        # Краткое имя вкладки
        short_name = domain.replace("https://", "").replace("www.", "")
        count = len(data_list)
        self.tabs.addTab(tab, f"{short_name} ({count})")

    def _on_table_double_click(self, index):
        """Открывает URL при двойном клике"""
        url = index.siblingAtColumn(2).data()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _get_current_model_and_items(self):
        """Возвращает модель и данные текущей вкладки"""
        idx = self.tabs.currentIndex()
        if idx < 0:
            return None, None

        tab = self.tabs.widget(idx)
        table = tab.findChild(QTableView)
        if table:
            model = table.model()
            return model, model.get_data() if hasattr(model, 'get_data') else None
        return None, None

    def _check_index_selected(self):
        """Проверяет индекс только для выбранных (отмеченных) страниц"""
        items_to_check = []

        for domain, model in self.table_models.items():
            data = model.get_data()
            for i, item in enumerate(data):
                if item.checked and item.index_status is None:
                    items_to_check.append((i, item))

        if not items_to_check:
            QMessageBox.information(
                self, "Инфо",
                "Отметьте страницы галочками для проверки индексации."
            )
            return

        self._start_index_check(items_to_check)

    def _check_index_all(self):
        """Проверяет индекс для ВСЕХ непроверенных страниц текущей вкладки"""
        model, data = self._get_current_model_and_items()
        if not data:
            return

        items_to_check = []
        for i, item in enumerate(data):
            if item.index_status is None:
                items_to_check.append((i, item))

        if not items_to_check:
            QMessageBox.information(self, "Инфо", "Все страницы уже проверены!")
            return

        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Проверить индексацию для {len(items_to_check)} страниц?\n"
            "Это может занять время и вызвать капчу Google.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._start_index_check(items_to_check)

    def _start_index_check(self, items):
        """Запускает воркер проверки индексации"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(items))
        self.progress_bar.setValue(0)

        self.btn_check_index.setEnabled(False)
        self.btn_check_all_index.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self.index_worker = IndexCheckWorker(items)
        self.index_worker.progress.connect(self._on_index_progress)
        self.index_worker.item_checked.connect(self._on_item_indexed)
        self.index_worker.captcha_required.connect(self._on_captcha_required)
        self.index_worker.finished.connect(self._on_index_finished)
        self.index_worker.start()

    def _on_index_progress(self, current, total, status):
        self.progress_bar.setValue(current)
        self.stats_lbl.setText(f"Index Check: {current}/{total} — {status}")

    def _on_item_indexed(self, row, is_indexed):
        """Обновляет модель когда элемент проверен"""
        model, _ = self._get_current_model_and_items()
        if model:
            model.update_item(row)

    def _on_captcha_required(self, url, html):
        """Показывает диалог капчи"""
        dlg = CaptchaDialog(url, html, self)
        dlg.exec()

        if dlg.response == "cancel":
            if self.index_worker:
                self.index_worker.stop()
        elif dlg.response == "done":
            if self.index_worker:
                self.index_worker.set_captcha_response("solved")
        else:
            if self.index_worker:
                self.index_worker.set_captcha_response(None)

    def _on_index_finished(self):
        self.progress_bar.setVisible(False)
        self.btn_check_index.setEnabled(True)
        self.btn_check_all_index.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.stats_lbl.setText("Проверка индексации завершена.")

    def _send_to_grabber(self):
        """Собирает отмеченные ссылки и открывает Граббер"""
        if not self.results_cache:
            return

        collected_urls = []
        for domain, items in self.results_cache.items():
            for item in items:
                if item.checked:
                    collected_urls.append(item.url)

        if not collected_urls:
            QMessageBox.warning(
                self, "Ничего не выбрано",
                "Отметьте галочками страницы для отправки в граббер."
            )
            return

        try:
            dlg = UrlGrabberDialog(self)
            dlg.url_edit.setPlainText("\n".join(collected_urls))
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть Граббер: {e}")

    def _export_csv(self):
        """Экспорт всех данных в CSV"""
        if not self.results_cache:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить", "pbn_report.csv", "CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow([
                    "Domain", "Type", "URL", "Title", "Words",
                    "OBL", "Inlinks", "Score", "Indexed", "Response_ms", "SSL"
                ])

                for domain, items in self.results_cache.items():
                    for item in items:
                        index_str = ""
                        if item.index_status is True:
                            index_str = "YES"
                        elif item.index_status is False:
                            index_str = "NO"

                        writer.writerow([
                            domain,
                            item.post_type.upper(),
                            item.url,
                            item.title,
                            item.word_count,
                            item.obl,
                            item.inlinks,
                            str(item.score).replace('.', ','),
                            index_str,
                            int(item.response_time * 1000),
                            "YES" if item.has_ssl else "NO"
                        ])

            QMessageBox.information(self, "OK", f"Сохранено: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def closeEvent(self, event):
        """Останавливаем воркеры при закрытии"""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
        if self.index_worker and self.index_worker.isRunning():
            self.index_worker.stop()
            self.index_worker.wait(2000)
        event.accept()
"""
URL Grabber — 4 метода на выбор:
1. Requests + Selenium cookies (быстро, но не всегда работает)
2. Selenium view-source (надёжно, но форматирование может отличаться)
3. Chrome + PyAutoGUI (реальный браузер)
4. Firefox + PyAutoGUI (реальный браузер, лучшее форматирование)
"""
import os
import time
import subprocess
import pyperclip
import pyautogui
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QFileDialog, QMessageBox, QPlainTextEdit, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QWidget, QComboBox, QSpinBox,
    QGroupBox, QRadioButton, QButtonGroup
)

import requests
import urllib3

from matrix_splash import SpinnerOverlay
from styles import Styles

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# PyAutoGUI настройки
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


# ============================================================================
# SAVE FUNCTION
# ============================================================================

def _save_page(url: str, html_content, base_folder: str = "template_grab") -> bool:
    """Сохранение HTML в файл"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        path = parsed.path.strip("/")

        if not path:
            path = "index"
        elif path.endswith("/"):
            path = path[:-1]

        path = path.replace("?", "_").replace("&", "_").replace("=", "_")

        dir_ = os.path.join(base_folder, domain)
        if "/" in path:
            subdir = os.path.dirname(path)
            dir_ = os.path.join(dir_, subdir)
            filename = os.path.basename(path)
        else:
            filename = path

        file_path = os.path.join(dir_, f"{filename}.html")
        os.makedirs(dir_, exist_ok=True)

        # Сохраняем
        if isinstance(html_content, bytes):
            # Байты (requests / API) пишем как есть — без трогания переносов строк
            with open(file_path, "wb") as f:
                f.write(html_content)
        else:
            # Нормализация переводов строк от браузера / буфера обмена:
            #   \r\n и \r приводим к \n, а при записи фиксируем newline="\n"
            text = html_content.replace("\r\n", "\n").replace("\r", "\n")
            with open(file_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)

        # footer.php
        footer_dir = os.path.join(base_folder, domain)
        footer_path = os.path.join(footer_dir, "footer.php")
        if not os.path.exists(footer_path):
            os.makedirs(footer_dir, exist_ok=True)
            with open(footer_path, "w", encoding="utf-8") as f:
                f.write("<!-- wp_footer -->")

        return True
    except Exception as e:
        print(f"Save error: {e}")
        return False


# ============================================================================
# METHOD 1: REQUESTS + SELENIUM COOKIES
# ============================================================================

def _grab_requests_with_selenium_cookies(url: str, headless: bool = True) -> tuple:
    """
    1. Selenium открывает страницу (обход Cloudflare)
    2. Берём cookies
    3. requests с cookies получает RAW HTML
    """
    try:
        import undetected_chromedriver as uc
    except ImportError:
        return False, "undetected-chromedriver not installed"

    driver = None
    try:
        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1920,1080")

        driver = uc.Chrome(options=options, use_subprocess=True)
        driver.set_page_load_timeout(60)

        driver.get(url)
        time.sleep(3)

        cookies = driver.get_cookies()
        user_agent = driver.execute_script("return navigator.userAgent;")

        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=cookie.get('domain', '').lstrip('.')
            )

        parsed = urlparse(url)
        headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'identity',
            'Referer': f"{parsed.scheme}://{parsed.netloc}/",
        }

        resp = session.get(url, headers=headers, timeout=30, verify=False)

        if resp.status_code == 200 and len(resp.content) > 500:
            return True, resp.content

        return False, f"HTTP {resp.status_code}"

    except Exception as e:
        return False, str(e)[:100]
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


# ============================================================================
# METHOD 2: SELENIUM VIEW-SOURCE
# ============================================================================

def _grab_selenium_view_source(url: str, headless: bool = False) -> tuple:
    """
    Selenium открывает view-source:URL напрямую
    """
    try:
        import undetected_chromedriver as uc
    except ImportError:
        return False, "undetected-chromedriver not installed"

    driver = None
    try:
        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1920,1080")

        driver = uc.Chrome(options=options, use_subprocess=True)
        driver.set_page_load_timeout(60)

        # Сначала обычная страница для cookies
        driver.get(url)
        time.sleep(3)

        # Теперь view-source
        driver.get(f"view-source:{url}")
        time.sleep(2)

        # Получаем из <pre> или body
        try:
            pre = driver.find_element("tag name", "pre")
            html_content = pre.text
        except:
            html_content = driver.find_element("tag name", "body").text

        if html_content and len(html_content) > 100:
            return True, html_content

        return False, "Empty response"

    except Exception as e:
        return False, str(e)[:100]
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


# ============================================================================
# METHOD 3: CHROME + PYAUTOGUI
# ============================================================================

def _grab_chrome_pyautogui(url: str, wait_load: float = 4.0) -> tuple:
    """
    Chrome + PyAutoGUI:
    1. Открываем URL
    2. Ctrl+U → View Source
    3. Ctrl+A, Ctrl+C
    """
    try:
        pyperclip.copy('')

        # Открываем Chrome
        subprocess.Popen(
            ['cmd', '/c', 'start', 'chrome', '--new-window', url],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        time.sleep(wait_load)

        # Ctrl+U — View Source
        pyautogui.hotkey('ctrl', 'u')
        time.sleep(2.0)

        # Ctrl+A — выделить
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.3)

        # Ctrl+C — копировать
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.5)

        html_content = pyperclip.paste()

        # Закрываем вкладки
        pyautogui.hotkey('ctrl', 'w')
        time.sleep(0.2)
        pyautogui.hotkey('ctrl', 'w')
        time.sleep(0.2)

        if html_content and len(html_content) > 100:
            return True, html_content

        return False, "Empty clipboard"

    except Exception as e:
        return False, str(e)


# ============================================================================
# METHOD 4: FIREFOX + PYAUTOGUI (с исправлением)
# ============================================================================

def _grab_firefox_pyautogui(url: str, wait_load: float = 5.0) -> tuple:
    """
    Firefox + PyAutoGUI:
    1. Открываем view-source:URL напрямую (обход JS блокировки)
    2. Ждём загрузки
    3. Кликаем в контент (чтобы фокус не был на адресной строке!)
    4. Ctrl+A, Ctrl+C
    """
    try:
        pyperclip.copy('')

        view_source_url = f"view-source:{url}"

        # Открываем Firefox с view-source напрямую
        subprocess.Popen(
            ['cmd', '/c', 'start', 'firefox', '-private-window', view_source_url],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Ждём загрузки (увеличено!)
        time.sleep(wait_load)

        # ВАЖНО: Кликаем в центр экрана чтобы фокус был на контенте, а не на адресной строке
        screen_width, screen_height = pyautogui.size()
        pyautogui.click(screen_width // 2, screen_height // 2)
        time.sleep(0.3)

        # Ctrl+A — выделить всё
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.3)

        # Ctrl+C — копировать
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.5)

        html_content = pyperclip.paste()

        # Закрываем окно
        pyautogui.hotkey('alt', 'F4')
        time.sleep(0.3)

        # Проверяем что это не поисковый запрос Google
        if html_content and len(html_content) > 100:
            # Если начинается с <!DOCTYPE или <html — это HTML
            stripped = html_content.strip().lower()
            if stripped.startswith('<!doctype') or stripped.startswith('<html') or stripped.startswith('<?xml'):
                return True, html_content
            # Если содержит HTML теги — тоже ок
            if '<head>' in html_content.lower() or '<body>' in html_content.lower():
                return True, html_content

        return False, "Empty or invalid content"

    except Exception as e:
        return False, str(e)


# ============================================================================
# UNIVERSAL GRAB FUNCTION
# ============================================================================

def grab_url(url: str, method: str = "firefox", wait_time: float = 5.0, headless: bool = True) -> tuple:
    """
    Универсальная функция граббинга
    method: "requests", "selenium", "chrome", "firefox"
    """
    if method == "requests":
        return _grab_requests_with_selenium_cookies(url, headless)
    elif method == "selenium":
        return _grab_selenium_view_source(url, headless)
    elif method == "chrome":
        return _grab_chrome_pyautogui(url, wait_time)
    elif method == "firefox":
        return _grab_firefox_pyautogui(url, wait_time)
    else:
        return False, f"Unknown method: {method}"


# ============================================================================
# WORKERS
# ============================================================================

class GrabberWorker(QThread):
    """Универсальный воркер для граббинга"""
    progress = pyqtSignal(str, bool)
    finished_signal = pyqtSignal()
    progress_count = pyqtSignal(int, int)

    def __init__(self, urls: list, method: str = "firefox", wait_time: float = 5.0, headless: bool = True):
        super().__init__()
        self.urls = urls
        self.method = method
        self.wait_time = wait_time
        self.headless = headless
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def run(self):
        total = len(self.urls)
        completed = 0

        for url in self.urls:
            if self._stop_flag:
                break

            completed += 1
            self.progress_count.emit(completed, total)

            try:
                success, data = grab_url(url, self.method, self.wait_time, self.headless)

                if success:
                    if _save_page(url, data):
                        self.progress.emit(f"<span style='color:#89d185'>✔</span> {url}", True)
                    else:
                        self.progress.emit(f"<span style='color:#f14c4c'>✗</span> {url} — save error", False)
                else:
                    error_msg = data[:60] if isinstance(data, str) else str(data)[:60]
                    self.progress.emit(f"<span style='color:#f14c4c'>✗</span> {url} — {error_msg}", False)

            except Exception as e:
                self.progress.emit(f"<span style='color:#f14c4c'>✗</span> {url} — {str(e)[:50]}", False)

            # Пауза между URL для PyAutoGUI методов
            if not self._stop_flag and self.method in ("chrome", "firefox"):
                time.sleep(1.0)

        self.finished_signal.emit()


# ============================================================================
# REST API GRABBER
# ============================================================================

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


class RestApiGrabberWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict, dict)
    progress_domain = pyqtSignal(int, int)
    partial_result = pyqtSignal(dict, dict)

    def __init__(self, domains: list):
        super().__init__()
        self.domains = domains
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        posts_by_domain = {}
        pages_by_domain = {}
        total = len(self.domains)

        session = requests.Session()
        session.headers.update(API_HEADERS)

        for idx, domain in enumerate(self.domains, 1):
            if self._stop:
                break

            self.progress_domain.emit(idx, total)
            self.progress.emit(f"<span style='color:#569cd6'>→</span> {domain}")

            base_url = f"https://{domain}"
            posts = self._fetch_all(session, f"{base_url}/wp-json/wp/v2/posts", domain)
            pages = self._fetch_all(session, f"{base_url}/wp-json/wp/v2/pages", domain)

            if posts:
                posts_by_domain[domain] = posts
                self.progress.emit(f"  Posts: {len(posts)}")
            if pages:
                pages_by_domain[domain] = pages
                self.progress.emit(f"  Pages: {len(pages)}")

            self.partial_result.emit(posts_by_domain, pages_by_domain)

        self.finished.emit(posts_by_domain, pages_by_domain)

    def _fetch_all(self, session, api_url, domain, per_page=100):
        items = []
        page = 1

        while not self._stop:
            try:
                r = session.get(api_url, params={"per_page": per_page, "page": page}, timeout=30, verify=False)
                if r.status_code != 200:
                    break

                data = r.json()
                if not data:
                    break

                for item in data:
                    items.append({
                        "id": item.get("id"),
                        "title": item.get("title", {}).get("rendered", "No title"),
                        "link": item.get("link", ""),
                        "slug": item.get("slug", ""),
                        "domain": domain,
                    })

                total_pages = int(r.headers.get("X-WP-TotalPages", 1))
                if page >= total_pages:
                    break
                page += 1
            except:
                break

        return items


# ============================================================================
# GUI
# ============================================================================

class UrlGrabberDialog(QDialog):
    """Основной диалог граббера с 4 методами"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌐 URL Grabber (4 метода)")
        self.setMinimumSize(1000, 800)
        self.setStyleSheet(Styles().get_dark())
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # === Выбор метода ===
        method_group = QGroupBox("Метод граббинга")
        method_layout = QVBoxLayout(method_group)

        self.method_buttons = QButtonGroup(self)

        # Метод 1: Requests
        self.rb_requests = QRadioButton(
            "🚀 Requests + Selenium cookies (быстро, но форматирование может отличаться)"
        )
        self.method_buttons.addButton(self.rb_requests, 0)
        method_layout.addWidget(self.rb_requests)

        # Метод 2: Selenium
        self.rb_selenium = QRadioButton(
            "🤖 Selenium view-source (надёжно, но форматирование браузера)"
        )
        self.method_buttons.addButton(self.rb_selenium, 1)
        method_layout.addWidget(self.rb_selenium)

        # Метод 3: Chrome
        self.rb_chrome = QRadioButton(
            "🌐 Chrome + PyAutoGUI (реальный браузер, Ctrl+U)"
        )
        self.method_buttons.addButton(self.rb_chrome, 2)
        method_layout.addWidget(self.rb_chrome)

        # Метод 4: Firefox (по умолчанию)
        self.rb_firefox = QRadioButton(
            "🦊 Firefox + PyAutoGUI (рекомендуется — лучшее форматирование, обход блокировок)"
        )
        self.rb_firefox.setChecked(True)
        self.method_buttons.addButton(self.rb_firefox, 3)
        method_layout.addWidget(self.rb_firefox)

        layout.addWidget(method_group)

        # === Настройки ===
        settings_layout = QHBoxLayout()

        wait_label = QLabel("Ожидание загрузки (сек):")
        wait_label.setStyleSheet("color: #969696;")
        settings_layout.addWidget(wait_label)

        self.wait_spin = QSpinBox()
        self.wait_spin.setRange(1, 30)
        self.wait_spin.setValue(5)
        self.wait_spin.setToolTip("Время ожидания загрузки страницы (для PyAutoGUI методов)")
        settings_layout.addWidget(self.wait_spin)

        settings_layout.addSpacing(20)

        self.headless_check = QRadioButton("Headless (для Requests/Selenium)")
        self.headless_check.setChecked(True)
        settings_layout.addWidget(self.headless_check)

        settings_layout.addStretch()
        layout.addLayout(settings_layout)

        # === Предупреждение PyAutoGUI ===
        pyautogui_warning = QLabel(
            "⚠️ <b>PyAutoGUI методы:</b> Не трогайте мышь/клавиатуру! "
            "Аварийный стоп: мышь в левый верхний угол экрана."
        )
        pyautogui_warning.setStyleSheet(
            "color: #dcdcaa; font-size: 11px; padding: 6px; "
            "background: #3d3d1e; border: 1px solid #6d6d3e;"
        )
        pyautogui_warning.setWordWrap(True)
        layout.addWidget(pyautogui_warning)

        # === URL Input ===
        input_layout = QHBoxLayout()
        input_layout.setSpacing(12)

        self.url_edit = QPlainTextEdit()
        self.url_edit.setPlaceholderText(
            "Введите URL (по одному на строку)\n"
            "https://example.com/page1\n"
            "https://example.com/page2"
        )
        input_layout.addWidget(self.url_edit, 3)

        # Кнопки справа
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)

        browse_btn = QPushButton("📂 Открыть файл")
        browse_btn.clicked.connect(self._load_urls_from_file)
        btn_layout.addWidget(browse_btn)

        btn_layout.addSpacing(10)

        grab_btn = QPushButton("⬇ СКАЧАТЬ")
        grab_btn.setStyleSheet(
            "background: #2d8d46; border: 1px solid #3ca55a; "
            "font-weight: bold; padding: 12px;"
        )
        grab_btn.clicked.connect(self._start_grab)
        btn_layout.addWidget(grab_btn)

        self.stop_btn = QPushButton("⏹ Стоп")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("background: #c42b1c; border: 1px solid #e81123;")
        self.stop_btn.clicked.connect(self._stop_grab)
        btn_layout.addWidget(self.stop_btn)

        btn_layout.addSpacing(20)

        wp_btn = QPushButton("🔍 WP REST API")
        wp_btn.clicked.connect(self._open_wp_dialog)
        btn_layout.addWidget(wp_btn)

        btn_layout.addStretch()

        input_layout.addLayout(btn_layout)
        layout.addLayout(input_layout)

        # === Progress ===
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_label = QLabel("Готов")
        progress_layout.addWidget(self.progress_bar, 1)
        progress_layout.addWidget(self.progress_label)
        layout.addLayout(progress_layout)

        # === Log ===
        log_label = QLabel("Лог:")
        log_label.setStyleSheet("color: #969696; font-size: 11px;")
        layout.addWidget(log_label)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)

        self.spinner = SpinnerOverlay(self)
        self.spinner.hide()
        self.worker = None

    def _get_method(self) -> str:
        """Получить выбранный метод"""
        if self.rb_requests.isChecked():
            return "requests"
        elif self.rb_selenium.isChecked():
            return "selenium"
        elif self.rb_chrome.isChecked():
            return "chrome"
        else:
            return "firefox"

    def _load_urls_from_file(self):
        file_, _ = QFileDialog.getOpenFileName(self, "Выбрать файл", "", "Text files (*.txt);;All (*)")
        if file_:
            try:
                with open(file_, "r", encoding="utf-8") as f:
                    self.url_edit.setPlainText(f.read())
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))

    def _start_grab(self):
        urls = [u.strip() for u in self.url_edit.toPlainText().splitlines() if u.strip()]
        if not urls:
            QMessageBox.warning(self, "Внимание", "Введите URL!")
            return

        urls = list(dict.fromkeys(urls))
        method = self._get_method()

        # Предупреждение для PyAutoGUI методов
        if method in ("chrome", "firefox"):
            reply = QMessageBox.warning(
                self,
                f"{'🌐 Chrome' if method == 'chrome' else '🦊 Firefox'} Grabber",
                f"Скачать {len(urls)} страниц через {method.upper()}?\n\n"
                "⚠️ НЕ ДВИГАЙТЕ мышь и НЕ НАЖИМАЙТЕ клавиши!\n\n"
                "🛑 Аварийный стоп: мышь в левый верхний угол\n\n"
                "Продолжить?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.log_view.clear()
        method_names = {
            "requests": "Requests + Cookies",
            "selenium": "Selenium",
            "chrome": "Chrome PyAutoGUI",
            "firefox": "Firefox PyAutoGUI"
        }
        self._log(f"<span style='color:#569cd6'>→</span> Запуск ({len(urls)} URL), метод: {method_names[method]}")

        os.makedirs("template_grab", exist_ok=True)

        self.spinner.setGeometry(self.rect())
        self.spinner.show()
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)

        self.worker = GrabberWorker(
            urls,
            method=method,
            wait_time=float(self.wait_spin.value()),
            headless=self.headless_check.isChecked()
        )
        self.worker.progress.connect(self._log)
        self.worker.progress_count.connect(self._update_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _stop_grab(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self._log("<span style='color:#f14c4c'>⏹ Остановлено</span>")

    def _update_progress(self, current, total):
        if total > 0:
            pct = int(current / total * 100)
            self.progress_bar.setValue(pct)
            self.progress_label.setText(f"{current}/{total}")

    def _on_finished(self):
        self.spinner.hide()
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(100)
        self.progress_label.setText("Готово")
        self._log("<span style='color:#89d185'>✔ Загрузка завершена!</span>")
        QMessageBox.information(self, "Готово", "Загрузка завершена!\nФайлы в папке template_grab/")

    def _open_wp_dialog(self):
        dlg = WPMapGrabberDialog(self)
        dlg.exec()

    def _log(self, text, success=True):
        self.log_view.append(text)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.spinner.isVisible():
            self.spinner.setGeometry(self.rect())


class WPMapGrabberDialog(QDialog):
    """Диалог для WP REST API"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔍 WP REST API Grabber")
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(Styles().get_dark())
        self._init_ui()
        self._posts_by_domain = {}
        self._pages_by_domain = {}

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # === Метод для скачивания ===
        method_layout = QHBoxLayout()
        method_label = QLabel("Метод скачивания:")
        method_label.setStyleSheet("color: #969696;")
        method_layout.addWidget(method_label)

        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "🦊 Firefox + PyAutoGUI",
            "🌐 Chrome + PyAutoGUI",
            "🤖 Selenium view-source",
            "🚀 Requests + Cookies"
        ])
        method_layout.addWidget(self.method_combo)
        method_layout.addStretch()
        layout.addLayout(method_layout)

        top_layout = QHBoxLayout()

        self.domain_edit = QPlainTextEdit()
        self.domain_edit.setPlaceholderText("Введите домены WordPress\nexample.com")
        self.domain_edit.setMaximumHeight(120)
        top_layout.addWidget(self.domain_edit, 3)

        btn_layout = QVBoxLayout()
        scan_btn = QPushButton("🔍 Сканировать")
        scan_btn.setStyleSheet("background: #2d8d46;")
        scan_btn.clicked.connect(self._start_scan)

        self.stop_btn = QPushButton("⏹ Стоп")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("background: #c42b1c;")
        self.stop_btn.clicked.connect(self._stop_scan)

        btn_layout.addWidget(scan_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addStretch()
        top_layout.addLayout(btn_layout)
        layout.addLayout(top_layout)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.tabs = QTabWidget()

        # Posts
        posts_widget = QWidget()
        posts_layout = QVBoxLayout(posts_widget)
        self.tbl_posts = self._create_table()
        posts_layout.addWidget(self.tbl_posts)

        posts_btns = QHBoxLayout()
        sel_all = QPushButton("✅ Выбрать все")
        sel_all.clicked.connect(lambda: self._select_all(self.tbl_posts, True))
        desel_all = QPushButton("❌ Снять все")
        desel_all.clicked.connect(lambda: self._select_all(self.tbl_posts, False))
        posts_btns.addWidget(sel_all)
        posts_btns.addWidget(desel_all)
        posts_btns.addStretch()
        posts_layout.addLayout(posts_btns)
        self.tabs.addTab(posts_widget, "📝 Posts")

        # Pages
        pages_widget = QWidget()
        pages_layout = QVBoxLayout(pages_widget)
        self.tbl_pages = self._create_table()
        pages_layout.addWidget(self.tbl_pages)

        pages_btns = QHBoxLayout()
        sel_all_p = QPushButton("✅ Выбрать все")
        sel_all_p.clicked.connect(lambda: self._select_all(self.tbl_pages, True))
        desel_all_p = QPushButton("❌ Снять все")
        desel_all_p.clicked.connect(lambda: self._select_all(self.tbl_pages, False))
        pages_btns.addWidget(sel_all_p)
        pages_btns.addWidget(desel_all_p)
        pages_btns.addStretch()
        pages_layout.addLayout(pages_btns)
        self.tabs.addTab(pages_widget, "📄 Pages")

        layout.addWidget(self.tabs, 1)

        download_layout = QHBoxLayout()
        download_btn = QPushButton("⬇ Скачать выбранные")
        download_btn.setStyleSheet("background: #2d8d46; padding: 10px 20px; font-weight: bold;")
        download_btn.clicked.connect(self._download_selected)
        download_layout.addStretch()
        download_layout.addWidget(download_btn)
        download_layout.addStretch()
        layout.addLayout(download_layout)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        layout.addWidget(self.log)

        self.spinner = SpinnerOverlay(self)
        self.spinner.hide()
        self.worker = None

    def _create_table(self):
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["ID", "✓", "URL", "Title", "Domain"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table.setAlternatingRowColors(True)
        return table

    def _get_method(self) -> str:
        idx = self.method_combo.currentIndex()
        return ["firefox", "chrome", "selenium", "requests"][idx]

    def _start_scan(self):
        domains = [
            d.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
            for d in self.domain_edit.toPlainText().splitlines() if d.strip()
        ]
        if not domains:
            QMessageBox.warning(self, "Внимание", "Введите домены!")
            return

        self.spinner.setGeometry(self.rect())
        self.spinner.show()
        self.stop_btn.setEnabled(True)
        self.log.clear()
        self.tbl_posts.setRowCount(0)
        self.tbl_pages.setRowCount(0)

        self.worker = RestApiGrabberWorker(domains)
        self.worker.progress.connect(self._log)
        self.worker.finished.connect(self._on_scan_finished)
        self.worker.progress_domain.connect(self._update_progress)
        self.worker.partial_result.connect(self._on_partial_result)
        self.worker.start()

    def _stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()

    def _update_progress(self, current, total):
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))

    def _on_partial_result(self, posts, pages):
        self._posts_by_domain = posts
        self._pages_by_domain = pages
        self._fill_table(self.tbl_posts, posts)
        self._fill_table(self.tbl_pages, pages)

    def _on_scan_finished(self, posts, pages):
        self.spinner.hide()
        self.stop_btn.setEnabled(False)
        self._posts_by_domain = posts
        self._pages_by_domain = pages
        self._fill_table(self.tbl_posts, posts)
        self._fill_table(self.tbl_pages, pages)
        self.progress_bar.setValue(100)
        self._log("<span style='color:#89d185'>✔ Готово</span>")

    def _fill_table(self, table, data_by_domain):
        table.setRowCount(0)
        row = 0
        for domain, items in data_by_domain.items():
            table.insertRow(row)
            h = QTableWidgetItem(f"→ {domain} ({len(items)})")
            h.setFlags(Qt.ItemFlag.ItemIsEnabled)
            table.setItem(row, 2, h)
            table.setSpan(row, 2, 1, 3)
            row += 1

            for item in items:
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem(str(item.get("id", ""))))
                chk = QTableWidgetItem()
                chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk.setCheckState(Qt.CheckState.Unchecked)
                table.setItem(row, 1, chk)
                table.setItem(row, 2, QTableWidgetItem(item.get("link", "")))
                table.setItem(row, 3, QTableWidgetItem(item.get("title", "")))
                table.setItem(row, 4, QTableWidgetItem(domain))
                row += 1

    def _select_all(self, table, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(table.rowCount()):
            item = table.item(row, 1)
            if item and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(state)

    def _download_selected(self):
        urls = []
        for table in [self.tbl_posts, self.tbl_pages]:
            for row in range(table.rowCount()):
                chk = table.item(row, 1)
                url_item = table.item(row, 2)
                if chk and url_item and chk.checkState() == Qt.CheckState.Checked:
                    url = url_item.text()
                    if url and not url.startswith("→"):
                        urls.append(url)

        urls = list(dict.fromkeys(urls))
        if not urls:
            QMessageBox.warning(self, "Внимание", "Выберите URL!")
            return

        method = self._get_method()

        if method in ("chrome", "firefox"):
            reply = QMessageBox.warning(
                self, "Grabber",
                f"Скачать {len(urls)} страниц методом {method.upper()}?\n\n"
                "Не трогайте мышь и клавиатуру!",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._log(f"<span style='color:#569cd6'>⬇</span> Загрузка {len(urls)} страниц ({method})...")
        self.spinner.setGeometry(self.rect())
        self.spinner.show()

        self.worker = GrabberWorker(urls, method=method, wait_time=5.0, headless=True)
        self.worker.progress.connect(self._log)
        self.worker.finished_signal.connect(self._on_download_finished)
        self.worker.start()

    def _on_download_finished(self):
        self.spinner.hide()
        self._log("<span style='color:#89d185'>✔ Готово!</span>")
        QMessageBox.information(self, "Готово", "Файлы в папке template_grab/")

    def _log(self, text):
        self.log.append(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.spinner.isVisible():
            self.spinner.setGeometry(self.rect())
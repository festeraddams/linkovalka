import json
import os
import time
import csv
import shutil
from datetime import datetime, timedelta

# Библиотеки Google
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import BatchHttpRequest
except ImportError:
    pass

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QFileDialog, QMessageBox, QLineEdit, QProgressBar, QComboBox,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QTreeWidget, QTreeWidgetItem, QInputDialog, QCheckBox, QApplication, QTextBrowser
)
from PyQt6.QtGui import QColor, QBrush, QFont
# Ваши стили
from styles import Styles


# ============================================================================
# 1. СТАРЫЙ ДОБРЫЙ WORKER (ОТПРАВКА В ИНДЕКС) - ИСПРАВЛЕННЫЙ
# ============================================================================
class IndexingWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal()

    def __init__(self, json_key_path, urls, request_type="URL_UPDATED"):
        super().__init__()
        self.json_key_path = json_key_path
        self.urls = urls
        self.request_type = request_type
        self.is_running = True

    def run(self):
        # Для индексации нужен scope "indexing", а не "webmasters"
        SCOPES = ["https://www.googleapis.com/auth/indexing"]
        try:
            self.log_signal.emit("🔄 Подключение к Indexing API...")
            credentials = service_account.Credentials.from_service_account_file(
                self.json_key_path, scopes=SCOPES
            )
            service = build("indexing", "v3", credentials=credentials)

            # Используем Batch для массовой отправки (до 100 за раз технически, но будем слать по одной для надежности или группировать)
            # В данном примере шлем через batch, чтобы работали коллбэки

            batch = service.new_batch_http_request(callback=self._batch_callback)
            total = len(self.urls)

            # Лимит batch запроса у Google - 1000, но лучше отправлять частями, если их много.
            # Здесь простая реализация: добавляем все в один batch (если до 1000 ссылок).

            count_in_batch = 0

            for i, url in enumerate(self.urls):
                if not self.is_running: break

                # Формируем тело запроса
                body = {
                    "url": url.strip(),
                    "type": self.request_type
                }

                # Добавляем в очередь
                batch.add(service.urlNotifications().publish(body=body), request_id=url.strip())
                count_in_batch += 1

                # Обновляем прогресс (визуально, реальная отправка будет при execute)
                self.progress_signal.emit(i + 1, total)

            if count_in_batch > 0 and self.is_running:
                self.log_signal.emit(f"📤 Отправка {count_in_batch} URL в Google...")
                batch.execute()  # Блокирующий вызов, ждем ответов

        except Exception as e:
            self.log_signal.emit(f"❌ Critical Error: {e}")

        self.finished_signal.emit()

    def _batch_callback(self, request_id, response, exception):
        if not self.is_running:
            return

        if exception is None:
            # Успех
            self.log_signal.emit(f"<span style='color:#89d185'>[200 OK]</span> {request_id}")
        else:
            # Ошибка
            error_reason = "Unknown"
            status = "Error"

            if hasattr(exception, 'resp'):
                status = str(exception.resp.status)
                try:
                    content = json.loads(exception.content)
                    error_reason = content.get('error', {}).get('message', 'No msg')
                except:
                    error_reason = str(exception)
            else:
                error_reason = str(exception)

            color = "#f14c4c"  # Red
            if "429" in status:
                error_reason = "Quota Exceeded (Лимит исчерпан)"
                color = "#e5c07b"  # Yellow
            elif "403" in status:
                error_reason = "Forbidden (Нет прав / Нет Owner)"

            self.log_signal.emit(
                f"<span style='color:{color}'>[{status}]</span> {request_id} — {error_reason}")

    def stop(self):
        self.is_running = False


# ============================================================================
# 2. НОВЫЙ WORKER (ПРОВЕРКА СНИППЕТОВ)
# ============================================================================
class SnippetCheckerWorker(QThread):
    result_signal = pyqtSignal(str, str, str)  # URL, Title, Status
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal()
    log_signal = pyqtSignal(str)

    def __init__(self, api_key, cx_id, urls):
        super().__init__()
        self.api_key = api_key
        self.cx_id = cx_id
        self.urls = urls
        self.is_running = True

    def run(self):
        try:
            self.log_signal.emit("🔄 Подключение к Custom Search API...")
            service = build("customsearch", "v1", developerKey=self.api_key)

            total = len(self.urls)

            for i, url in enumerate(self.urls):
                if not self.is_running: break

                try:
                    # Запрос вида site:URL
                    res = service.cse().list(q=f"site:{url}", cx=self.cx_id).execute()
                    items = res.get('items', [])

                    if items:
                        # Если нашли — берем первый результат
                        title = items[0].get('title', 'No Title')
                        snippet = items[0].get('snippet', '')
                        self.result_signal.emit(url, title, "INDEXED")
                        self.log_signal.emit(f"<span style='color:#89d185'>[FOUND]</span> {url}")
                    else:
                        self.result_signal.emit(url, "—", "NOT IN INDEX")
                        self.log_signal.emit(f"<span style='color:#e5c07b'>[MISSING]</span> {url}")

                except Exception as e:
                    err = str(e)
                    if "429" in err:
                        self.log_signal.emit(
                            "<span style='color:red'>Лимит запросов API исчерпан (100/день бесплатно).</span>")
                        self.result_signal.emit(url, "Error 429", "QUOTA LIMIT")
                        break
                    else:
                        self.result_signal.emit(url, "Error", "ERROR")
                        self.log_signal.emit(f"<span style='color:red'>[Error]</span> {url}: {err}")

                self.progress_signal.emit(i + 1, total)
                time.sleep(0.2)  # Небольшая пауза, чтобы Гугл не банил

        except Exception as e:
            self.log_signal.emit(f"Critical Error: {e}")

        self.finished_signal.emit()

    def stop(self):
        self.is_running = False


# ============================================================================
# 3. WORKER: GSC KEYWORDS (Mini Ahrefs) - ФИНАЛЬНАЯ ЛОГИКА
# ============================================================================
class GscKeywordsWorker(QThread):
    """
    Получает ключевые слова, сравнивает с историей.
    NEW (Зеленые) - только если реально не было в истории.
    ACTIVE (Обычные) - если были в истории.
    LOST (Красные) - если были, но исчезли из выдачи.
    """
    data_signal = pyqtSignal(dict)
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal()

    def __init__(self, json_key_path, urls, country_code, history_file="rank_history.json"):
        super().__init__()
        self.json_key_path = json_key_path
        self.urls = urls
        self.country = country_code
        self.history_file = history_file
        self.is_running = True

    def run(self):
        SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
        try:
            self.log_signal.emit("🔄 Подключение к Search Console API...")
            credentials = service_account.Credentials.from_service_account_file(
                self.json_key_path, scopes=SCOPES
            )
            service = build("webmasters", "v3", credentials=credentials)

            site_list_resp = service.sites().list().execute()
            verified_sites = [s['siteUrl'] for s in site_list_resp.get('siteEntry', [])]

            if not verified_sites:
                self.log_signal.emit("<span style='color:red'>Нет прав Owner ни на один сайт!</span>")
                self.finished_signal.emit()
                return

            # БЭКАП ПЕРЕД ЗАПУСКОМ
            self._create_backup()

            history = self._load_history()
            history_map = {k.rstrip('/'): k for k in history.keys()}

            today_str = datetime.now().strftime("%Y-%m-%d")
            end_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

            total = len(self.urls)
            final_data = {}

            for i, url in enumerate(self.urls):
                if not self.is_running: break

                original_url = url.strip()
                clean_url = original_url.rstrip('/')

                matching_site = None
                for site in verified_sites:
                    if site in original_url or (site.startswith("sc-domain:") and site[10:] in original_url):
                        matching_site = site
                        break

                if not matching_site:
                    self.log_signal.emit(f"⚠️ Не найден Owner-сайт для: {original_url}")
                    continue

                # Подготовка истории
                history_key = history_map.get(clean_url, original_url)
                if history_key not in history: history[history_key] = {}
                url_history = history[history_key]

                try:
                    request = {
                        "startDate": start_date, "endDate": end_date,
                        "dimensions": ["query"],
                        "dimensionFilterGroups": [{
                            "filters": [
                                {"dimension": "page", "operator": "equals", "expression": original_url},
                                {"dimension": "country", "operator": "equals", "expression": self.country}
                            ]
                        }],
                        "rowLimit": 50
                    }
                    response = service.searchanalytics().query(siteUrl=matching_site, body=request).execute()
                    rows = response.get('rows', [])

                    current_keys_set = set()
                    url_keywords_data = []

                    # 1. ОБРАБОТКА ТЕКУЩИХ КЛЮЧЕЙ
                    for row in rows:
                        kw = row['keys'][0]
                        pos = round(row['position'], 1)
                        clicks = row['clicks']
                        imp = row['impressions']
                        current_keys_set.add(kw)

                        status = "ACTIVE"
                        diff = 0.0

                        if kw not in url_history:
                            # --- НОВЫЙ КЛЮЧ ---
                            status = "NEW"
                            url_history[kw] = {
                                'first_seen': today_str,
                                'day_start_pos': pos,  # Старт дня = текущая
                                'last_pos': pos,
                                'last_seen': today_str
                            }
                        else:
                            # --- КЛЮЧ БЫЛ В ИСТОРИИ ---
                            prev_data = url_history[kw]

                            # Конвертация старого формата (если есть)
                            if isinstance(prev_data, (int, float)):
                                prev_data = {'first_seen': "2000-01-01", 'last_pos': prev_data, 'last_seen': today_str}

                            last_seen_date = prev_data.get('last_seen', '')

                            # === ЛОГИКА СОХРАНЕНИЯ "Change" ===
                            # Если дата изменилась (первый запуск сегодня), фиксируем "Старт дня"
                            if last_seen_date != today_str:
                                prev_data['day_start_pos'] = prev_data.get('last_pos', pos)
                                prev_data['last_seen'] = today_str  # Обновляем дату посещения

                            # Если поля day_start_pos нет в базе (для старых записей), создаем его
                            if 'day_start_pos' not in prev_data:
                                prev_data['day_start_pos'] = prev_data.get('last_pos', pos)

                            # Считаем разницу: СТАРТ ДНЯ (утро) минус ТЕКУЩАЯ
                            day_start = prev_data['day_start_pos']
                            diff = day_start - pos

                            # Всегда обновляем "last_pos" на самое свежее значение (чтобы завтра оно стало стартом)
                            prev_data['last_pos'] = pos

                            # Статус
                            if prev_data.get('first_seen') == today_str:
                                status = "NEW"
                            else:
                                status = "ACTIVE"

                            url_history[kw] = prev_data

                        url_keywords_data.append({
                            'kw': kw, 'pos': pos, 'diff': diff,
                            'clicks': clicks, 'imp': imp, 'status': status
                        })

                    # 2. ИЩЕМ ПРОПАВШИЕ (LOST)
                    for hist_kw, hist_val in url_history.items():
                        if hist_kw not in current_keys_set:
                            last_p = hist_val if isinstance(hist_val, (int, float)) else hist_val.get('last_pos', 0)
                            url_keywords_data.append({
                                'kw': hist_kw, 'pos': last_p, 'diff': 0,
                                'clicks': 0, 'imp': 0, 'status': "LOST"
                            })

                    def sort_key(item):
                        prio = 1
                        if item['status'] == "NEW":
                            prio = 0
                        elif item['status'] == "LOST":
                            prio = 2
                        return (prio, item['pos'])

                    url_keywords_data.sort(key=sort_key)
                    final_data[original_url] = url_keywords_data

                    self.log_signal.emit(f"✅ {original_url}: {len(url_keywords_data)} keys")

                except Exception as e:
                    self.log_signal.emit(f"❌ Ошибка GSC для {original_url}: {e}")

                self.progress_signal.emit(i + 1, total)
                time.sleep(0.2)

            self._save_history(history)
            self.data_signal.emit(final_data)

        except Exception as e:
            self.log_signal.emit(f"Critical Worker Error: {e}")
        self.finished_signal.emit()

    def _create_backup(self):
        """Создает копию rank_history.json в папку backups с текущей датой"""
        if os.path.exists(self.history_file):
            try:
                # Создаем папку, если нет
                backup_dir = "backups"
                if not os.path.exists(backup_dir):
                    os.makedirs(backup_dir)

                # Имя файла: rank_history_2023-10-05_12-30.json
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
                backup_name = f"rank_history_{timestamp}.json"
                backup_path = os.path.join(backup_dir, backup_name)

                shutil.copy2(self.history_file, backup_path)
                self.log_signal.emit(f"📦 Бэкап создан: {backup_name}")
            except Exception as e:
                self.log_signal.emit(f"⚠️ Ошибка бэкапа: {e}")

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_history(self, data):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except:
            pass

    def stop(self):
        self.is_running = False


# ============================================================================
# СПРАВКА (СТАРАЯ + НОВАЯ)
# ============================================================================
class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Справка по Google Indexing API")
        self.resize(800, 700)
        self.styles = Styles()
        self.setStyleSheet(self.styles.get_dark())

        layout = QVBoxLayout(self)

        text_edit = QTextBrowser()
        text_edit.setOpenExternalLinks(True)
        text_edit.setHtml("""
        <h2 style="color: #61afef;">🚀 Полная инструкция по настройке</h2>
        <p style="color: #ccc;">Следуйте этим шагам, чтобы получить <b>JSON-ключ</b> и настроить права доступа. Это делается один раз.</p>

        <hr style="background-color: #444; height: 1px; border: none;">

        <h3 style="color: #98c379;">Шаг 1. Установка библиотек</h3>
        <p>Чтобы программа могла общаться с Google, нужно установить библиотеки. Откройте терминал (в PyCharm вкладка <b>Terminal</b> внизу) и введите:</p>
        <code style="background-color: #2b2b2b; padding: 10px; color: #e5c07b; display: block; margin: 5px 0;">pip install google-api-python-client google-auth</code>

        <hr style="background-color: #444; height: 1px; border: none;">

        <h3 style="color: #61afef;">Шаг 2. Создание проекта и Бота (Google Cloud)</h3>
        <p>Самый сложный этап. Делайте по пунктам:</p>
        <ol style="margin-left: -20px;">
            <li>Зайдите в <a href="https://console.cloud.google.com/" style="color: #61afef;">Google Cloud Console</a>.</li>
            <li><b>Создайте проект:</b> В левом верхнем углу (рядом с лого Google Cloud) нажмите на кнопку <b>Select a project</b>. Откроется окно и в нем уже будет 1 project с названием <b>No organization</b>, забейте на эту хуйню, сверху справа этого окошка будет <b>NEW PROJECT</b>. Дайте имя (например, <i>SeoIndexer</i>) и нажмите <b>CREATE</b>.</li>
            <li><b>Включите API:</b> 
                <ul>
                    <li>Убедитесь, что выбран ваш новый проект (сверху) там где раньше было <b>Select a project</b>.</li>
                    <li>В строке поиска (вверху по центру) введите <b>Web Search Indexing API</b>.</li>
                    <li>Выберите карточку с таким названием и нажмите синюю кнопку <b>ENABLE</b> (Включить).</li>
                </ul>
            </li>
            <li><b>Создайте Сервисный Аккаунт (Бота):</b>
                <ul>
                    <li>Нажмите на меню "Гамбургер" (три полоски слева) -> <b>IAM & Admin</b> -> <b>Service Accounts</b>.</li>
                    <li>Нажмите <b>+ CREATE SERVICE ACCOUNT</b>.</li>
                    <li>Придумайте имя (например, <i>indexer-bot</i>). Нажмите <b>CREATE AND CONTINUE</b>.</li>
                    <li>Permissions (optional) - открывайте свиток <b>Select a role</b> выбирайте слева Basic справа Owner затем <b>DONE</b></li>
                </ul>
            </li>
            <li><b>Получите Ключ:</b>
                <ul>
                    <li>В списке аккаунтов найдите созданного бота. Справа нажмите на три точки -> <b>Manage keys</b>.</li>
                    <li>Нажмите <b>ADD KEY</b> -> <b>Create new key</b>.</li>
                    <li>Выберите тип <b>JSON</b> и нажмите <b>CREATE</b>. Файл скачается на компьютер.</li>
                </ul>
            </li>
        </ol>

        <hr style="background-color: #444; height: 1px; border: none;">

        <h3 style="color: #e06c75;">Шаг 3. Связка с сайтом (Search Console)</h3>
        <p><b>⚠️ КРИТИЧЕСКИ ВАЖНО:</b> Бот не сможет отправлять ссылки, если вы не сделаете его Владельцем сайта.</p>
        <ol style="margin-left: -20px;">
            <li>Откройте скачанный JSON-файл любым текстовым редактором.</li>
            <li>Найдите строчку <b>client_email</b> и скопируйте email (вида: <i>bot-name@project-id.iam.gserviceaccount.com</i>).</li>
            <li>Перейдите в <a href="https://search.google.com/search-console" style="color: #61afef;">Google Search Console</a> и выберите нужный сайт.</li>
            <li>В меню слева внизу нажмите <b>Settings (Настройки)</b>.</li>
            <li>Выберите пункт <b>Users and permissions (Пользователи и разрешения)</b>.</li>
            <li>Нажмите синюю кнопку <b>Add User (Добавить пользователя)</b>.</li>
            <li>Вставьте email бота.</li>
            <li><b>ВАЖНО:</b> В поле Permission (Разрешение) выберите <b>OWNER (Владелец)</b>.</li>
            <li>Нажмите Add (Добавить).</li>
        </ol>
        <p><i>Повторите Шаг 3 для каждого сайта, который вы хотите индексировать этим ключом.</i></p>

        <hr style="background-color: #444; height: 1px; border: none;">

        <h3 style="color: #c678dd;">Лимиты и Квоты</h3>
        <p><b>200 запросов в сутки</b> — это лимит на один Проект (JSON-файл).</p>
        <p><b>Как обойти?</b></p>
        <ul>
            <li>Создайте еще один Проект в Google Cloud (повторите Шаг 2).</li>
            <li>Получите для него новый JSON-файл.</li>
            <li>В программе просто выберите новый файл ключа, когда лимит первого исчерпан.</li>
        </ul>
        
        
        
        <br><br>
        <hr style="background-color: #444; height: 1px; border: none;">
        <hr style="background-color: #444; height: 1px; border: none;">
        <br><br>



        <h2 style="color: #c678dd;">🔍 Инструкция: CHECKER (Проверка заголовков)</h2>
        <p>Для проверки сниппетов нужны <b>API Key</b> и <b>Search Engine ID</b>.</p>

        <hr style="background-color: #444; height: 1px; border: none;">

        <ol style="margin-left: -20px;">
            <li><b>API Key:</b>
                <ul>
                    <li>В Google Cloud Console включите <b>Custom Search API</b>.</li>
                    <li>В меню <b>APIs & Services -> Credentials</b> нажмите <b>+ Create Credentials -> API Key</b>.</li>
                </ul>
            </li>
            <li><b>Search Engine ID (CX):</b>
                <ul>
                    <li>Зайдите на <a href="https://programmablesearchengine.google.com/" style="color: #c678dd;">Programmable Search Engine</a>.</li>
                    <li>Нажмите кнопку <b>Add (Добавить)</b>.</li>
                    <li><b>Название:</b> Напишите любое имя.</li>
                    <li><b>Что искать? (Важно):</b> Переключите галочку на <b>"Поиск во всем интернете"</b> (второй пункт, см. скриншот).</li>
                    <li>Поставьте галочку "Я не робот" и нажмите кнопку <b>Создать</b>.</li>
                    <li>На следующем экране вы увидите код. Скопируйте <b>CX</b> (например: <code>012345...</code>).</li>
                </ul>
            </li>
        </ol>
        <p style="color: orange;">Бесплатный лимит проверки: 100 запросов в день.</p>
        """)

        layout.addWidget(text_edit)

        close_btn = QPushButton("Понятно")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet("background-color: #0e639c; color: white; font-weight: bold; padding: 8px;")
        layout.addWidget(close_btn)


# ============================================================================
# ГЛАВНОЕ ОКНО С ВКЛАДКАМИ
# ============================================================================
class GoogleIndexerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Google SEO Toolset (Indexer + Checker)")
        self.resize(1400, 900)

        self.styles = Styles()
        self.setStyleSheet(self.styles.get_dark())

        self.settings = QSettings("SamsaSoft", "GoogleIndexer")
        self.groups_file = "url_groups.json"
        self.cache_file = "gsc_full_cache.json"

        main_layout = QVBoxLayout(self)

        # ВКЛАДКИ
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Вкладка 1: Твой старый добрый Индексатор
        self.tab_indexer = QWidget()
        self.init_indexer_tab()
        self.tabs.addTab(self.tab_indexer, "🚀 Indexer (Send)")

        # Вкладка 2: Новый Чекер
        self.tab_checker = QWidget()
        self.init_checker_tab()
        self.tabs.addTab(self.tab_checker, "🔍 Checker (Snippets)")

        # Вкладка 3: GSC Keywords
        self.tab_gsc = QWidget()
        self.init_gsc_tab()
        self.tabs.addTab(self.tab_gsc, "📈 GSC Positions (Mini Ahrefs)")

    # ------------------------------------------------------------------------
    # ЛОГИКА ВКЛАДКИ 1 (ТВОЙ СТАРЫЙ КОД)
    # ------------------------------------------------------------------------
    def init_indexer_tab(self):
        layout = QVBoxLayout(self.tab_indexer)
        layout.setSpacing(12)

        # 1. Верхняя панель (Ключ + INFO)
        top_box = QHBoxLayout()

        key_layout = QVBoxLayout()
        key_layout.setSpacing(2)
        key_lbl = QLabel("Service Account Key (JSON):")
        key_lbl.setStyleSheet("color: #aaa; font-size: 11px;")

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("C:/path/to/service_account.json")
        saved_key = self.settings.value("json_key_path", "")
        self.key_input.setText(saved_key)

        key_layout.addWidget(key_lbl)
        key_layout.addWidget(self.key_input)

        # Кнопки выбора файла и справки
        btns_layout = QVBoxLayout()

        browse_btn = QPushButton("📂")
        browse_btn.setToolTip("Выбрать файл ключа")
        browse_btn.setFixedSize(50, 25)
        browse_btn.clicked.connect(self.browse_key)

        info_btn = QPushButton("💡 INFO")
        info_btn.setToolTip("Инструкция по настройке")
        info_btn.setFixedSize(100, 25)
        info_btn.setStyleSheet("background-color: #9a7ecc; color: white; font-weight: bold; font-size: 11px;")
        info_btn.clicked.connect(self.show_info)

        btns_row = QHBoxLayout()
        btns_row.addWidget(browse_btn)
        btns_row.addWidget(info_btn)

        top_box.addLayout(key_layout)
        top_box.addLayout(btns_layout)
        top_box.addLayout(btns_row)

        layout.addLayout(top_box)

        # 2. Тип запроса
        type_layout = QHBoxLayout()
        type_lbl = QLabel("Request Type:")
        self.type_combo = QComboBox()
        self.type_combo.addItems(["URL_UPDATED (Update/Add)", "URL_DELETED (Remove)"])
        type_layout.addWidget(type_lbl)
        type_layout.addWidget(self.type_combo)
        type_layout.addStretch()
        layout.addLayout(type_layout)

        # 3. Поле ввода
        layout.addWidget(QLabel("URLs List (One per line):"))
        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText("https://example.com/post-1/\nhttps://example.com/post-2/")
        layout.addWidget(self.url_input)

        # 4. Кнопки
        btn_box = QHBoxLayout()
        self.start_btn = QPushButton("🚀 START BATCH INDEXING")
        self.start_btn.setStyleSheet("""
            QPushButton { background-color: #2ea043; color: white; font-weight: bold; padding: 10px; font-size: 14px;}
            QPushButton:hover { background-color: #3fb950; }
        """)
        self.start_btn.clicked.connect(self.start_indexing)

        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("background-color: #d73a49; color: white;")
        self.stop_btn.clicked.connect(self.stop_worker)

        btn_box.addWidget(self.start_btn, stretch=2)
        btn_box.addWidget(self.stop_btn, stretch=1)
        layout.addLayout(btn_box)

        # 5. Прогресс и Лог
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.progress_bar)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: Consolas; font-size: 12px; background: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(self.log_view)

    # ------------------------------------------------------------------------
    # ЛОГИКА ВКЛАДКИ 2 (НОВЫЙ ЧЕКЕР)
    # ------------------------------------------------------------------------
    def init_checker_tab(self):
        layout = QVBoxLayout(self.tab_checker)

        # Настройки API
        params_layout = QHBoxLayout()

        # API Key
        v1 = QVBoxLayout()
        v1.addWidget(QLabel("Google API Key:"))
        self.chk_api_input = QLineEdit()
        self.chk_api_input.setPlaceholderText("AIzaSy...")
        self.chk_api_input.setText(self.settings.value("chk_api_key", ""))
        v1.addWidget(self.chk_api_input)

        # CX ID
        v2 = QVBoxLayout()
        v2.addWidget(QLabel("Search Engine ID (CX):"))
        self.chk_cx_input = QLineEdit()
        self.chk_cx_input.setPlaceholderText("012345...")
        self.chk_cx_input.setText(self.settings.value("chk_cx_id", ""))
        v2.addWidget(self.chk_cx_input)

        params_layout.addLayout(v1)
        params_layout.addLayout(v2)
        layout.addLayout(params_layout)

        # URLS
        layout.addWidget(QLabel("Check URLs:"))
        self.chk_url_input = QTextEdit()
        self.chk_url_input.setPlaceholderText("https://site.com/page1")
        layout.addWidget(self.chk_url_input)

        # Buttons
        btn_box = QHBoxLayout()
        self.chk_start_btn = QPushButton("CHECK SNIPPETS")
        self.chk_start_btn.setStyleSheet("background-color: #0e639c; color: white; font-weight: bold; padding: 8px;")
        self.chk_start_btn.clicked.connect(self.start_checking)

        self.chk_stop_btn = QPushButton("STOP")
        self.chk_stop_btn.setEnabled(False)
        self.chk_stop_btn.setStyleSheet("background-color: #d73a49; color: white;")
        self.chk_stop_btn.clicked.connect(self.stop_checking)

        btn_box.addWidget(self.chk_start_btn)
        btn_box.addWidget(self.chk_stop_btn)
        layout.addLayout(btn_box)

        # Table Results
        self.chk_table = QTableWidget(0, 3)
        self.chk_table.setHorizontalHeaderLabels(["Status", "URL", "Google Title"])
        self.chk_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.chk_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.chk_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.chk_table)

        # Progress
        self.chk_progress = QProgressBar()
        self.chk_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.chk_progress)

    # ------------------------------------------------------------------------
    # МЕТОДЫ (ОБЩИЕ И ДЛЯ КАЖДОЙ ВКЛАДКИ)
    # ------------------------------------------------------------------------
    def browse_key(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select JSON Key", "", "JSON Files (*.json)")
        if fname:
            self.key_input.setText(fname)
            self.settings.setValue("json_key_path", fname)

    def show_info(self):
        dlg = HelpDialog(self)
        dlg.exec()

    # --- Indexer Logic ---
    def start_indexing(self):
        json_path = self.key_input.text().strip()
        raw_urls = self.url_input.toPlainText()

        if not json_path or not os.path.exists(json_path):
            QMessageBox.warning(self, "Key Error", "Please select a valid JSON Service Account key file.")
            return

        urls = [u.strip() for u in raw_urls.splitlines() if u.strip().startswith("http")]
        if not urls:
            QMessageBox.warning(self, "URL Error", "URL list is empty.")
            return

        try:
            import google.oauth2
            import googleapiclient
        except ImportError:
            QMessageBox.critical(self, "Library Error", "Libraries not found!")
            return

        self.settings.setValue("json_key_path", json_path)

        self.log_view.clear()
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.key_input.setEnabled(False)
        self.url_input.setEnabled(False)

        req_type = "URL_UPDATED"
        if "DELETED" in self.type_combo.currentText():
            req_type = "URL_DELETED"

        self.worker = IndexingWorker(json_path, urls, req_type)
        self.worker.log_signal.connect(self.append_log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.on_finished_indexer)
        self.worker.start()

    def stop_worker(self):
        if hasattr(self, 'worker'):
            self.worker.stop()
            self.append_log("<br><span style='color:orange'>⚠️ Stopping...</span>")
            self.stop_btn.setEnabled(False)

    def append_log(self, text):
        self.log_view.append(text)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        percent = int((current / total) * 100)
        self.progress_bar.setFormat(f"{current}/{total} ({percent}%)")

    def on_finished_indexer(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.key_input.setEnabled(True)
        self.url_input.setEnabled(True)

    # --- Checker Logic ---
    def start_checking(self):
        api = self.chk_api_input.text().strip()
        cx = self.chk_cx_input.text().strip()

        # Получаем ссылки и фильтруем пустые строки
        raw_text = self.chk_url_input.toPlainText()
        urls = [u.strip() for u in raw_text.splitlines() if u.strip().startswith("http")]

        # Сохраняем настройки сразу, чтобы не терялись
        if api: self.settings.setValue("chk_api_key", api)
        if cx: self.settings.setValue("chk_cx_id", cx)

        if not api or not cx:
            QMessageBox.warning(self, "Error", "Пожалуйста, введите API Key и Search Engine ID (CX).")
            return

        if not urls:
            QMessageBox.warning(self, "Error", "Список URL пуст. Введите ссылки (одна на строку).")
            return

        self.chk_table.setRowCount(0)
        self.chk_progress.setValue(0)
        self.chk_start_btn.setEnabled(False)
        self.chk_stop_btn.setEnabled(True)

        self.chk_worker = SnippetCheckerWorker(api, cx, urls)
        self.chk_worker.result_signal.connect(self.add_check_result)
        self.chk_worker.progress_signal.connect(
            lambda c, t: (self.chk_progress.setMaximum(t), self.chk_progress.setValue(c)))
        self.chk_worker.finished_signal.connect(
            lambda: (self.chk_start_btn.setEnabled(True), self.chk_stop_btn.setEnabled(False)))
        self.chk_worker.log_signal.connect(lambda s: print(s))
        self.chk_worker.start()

    def stop_checking(self):
        if hasattr(self, 'chk_worker'): self.chk_worker.stop()

    def add_check_result(self, url, title, status):
        row = self.chk_table.rowCount()
        self.chk_table.insertRow(row)

        it_status = QTableWidgetItem(status)
        if status == "INDEXED":
            it_status.setForeground(QBrush(QColor("#89d185")))  # Green
        elif status == "NOT IN INDEX":
            it_status.setForeground(QBrush(QColor("#e5c07b")))  # Yellow
        else:
            it_status.setForeground(QBrush(QColor("#f14c4c")))  # Red

        self.chk_table.setItem(row, 0, it_status)
        self.chk_table.setItem(row, 1, QTableWidgetItem(url))
        self.chk_table.setItem(row, 2, QTableWidgetItem(title))

    # ------------------------------------------------------------------
    # TAB 3: GSC KEYWORDS (MINI AHREFS)
    # ------------------------------------------------------------------
    def init_gsc_tab(self):
        l = QVBoxLayout(self.tab_gsc)

        # 1. Настройки API
        h = QHBoxLayout()
        v1 = QVBoxLayout();
        v1.setSpacing(2)
        v1.addWidget(QLabel("JSON Key:"))
        self.gsc_key = QLineEdit(self.settings.value("json_key_path", ""))
        v1.addWidget(self.gsc_key)
        h.addLayout(v1, stretch=2)

        v2 = QVBoxLayout();
        v2.setSpacing(2)
        v2.addWidget(QLabel("Локация:"))
        self.gsc_country = QComboBox()
        self.gsc_country.addItem("USA 🇺🇸", "USA")
        self.gsc_country.addItem("UK 🇬🇧", "GBR")
        self.gsc_country.addItem("Canada 🇨🇦", "CAN")
        self.gsc_country.addItem("Germany 🇩🇪", "DEU")
        self.gsc_country.addItem("France 🇫🇷", "FRA")
        self.gsc_country.addItem("Ukraine 🇺🇦", "UKR")
        self.gsc_country.addItem("Russia 🇷🇺", "RUS")
        v2.addWidget(self.gsc_country)
        h.addLayout(v2, stretch=1)
        l.addLayout(h)

        # 2. Группы + CSV
        group_box = QHBoxLayout()

        # Выбор группы
        self.group_combo = QComboBox()
        self.group_combo.setMinimumWidth(180)
        self.group_combo.currentIndexChanged.connect(self.load_group_urls)

        # Кнопки управления (убрал setFixedWidth и сделал их шире)
        btn_add = QPushButton("✚ GROUP")
        btn_add.setFixedWidth(95)
        btn_add.setToolTip("Создать новую группу")
        btn_add.setStyleSheet("""
                    QPushButton {
                        background-color: #6f42c1; 
                        color: white; 
                        font-weight: bold;
                        border: none;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #5a379c; 
                    }
                """)
        btn_add.clicked.connect(self.create_group)

        btn_del = QPushButton("✘")
        btn_del.setFixedWidth(40)
        btn_del.setToolTip("Удалить выбранную группу")
        btn_del.setStyleSheet("""
                    QPushButton {
                        background-color: #c42b1c; 
                        color: white; 
                        font-weight: bold;
                        font-size: 14px;
                        border: none;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #a32417; 
                    }
                """)
        btn_del.clicked.connect(self.delete_group)

        btn_save = QPushButton("✔ SAVE")
        btn_save.setFixedWidth(80)
        btn_save.setToolTip("Сохранить список URL")
        btn_save.setStyleSheet("""
                    QPushButton {
                        background-color: #66aa70; 
                        color: white; 
                        font-weight: bold;
                        border: none;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #4a8050; 
                    }
                """)
        btn_save.clicked.connect(self.save_urls_to_group)

        # Кнопка CSV
        btn_csv = QPushButton("📉 EXPORT CSV")
        btn_csv.setFixedWidth(130)
        btn_csv.setToolTip("Экспорт текущих данных в CSV")
        btn_csv.setStyleSheet("""
                    QPushButton {
                        background-color: #d19a66; 
                        color: white; 
                        font-weight: bold;
                        border: none;
                        font-shadow: 1px 1px 2px black;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #a5754a;
                        box-shadow: 1px 1px 6px 3px white; 
                    }
                """)
        btn_csv.clicked.connect(self.export_group_csv)

        group_box.addWidget(QLabel("Группа:"))
        group_box.addWidget(self.group_combo)
        group_box.addWidget(btn_add)
        group_box.addWidget(btn_del)
        group_box.addWidget(btn_save)
        group_box.addStretch()
        group_box.addWidget(btn_csv)
        l.addLayout(group_box)

        # 3. Фильтры
        filter_box = QHBoxLayout()
        self.chk_all = QCheckBox("Все");
        self.chk_all.setChecked(True)
        self.chk_active = QCheckBox("Активные");
        self.chk_active.setChecked(True)
        self.chk_new = QCheckBox("Новые (Green)");
        self.chk_new.setChecked(True)
        self.chk_lost = QCheckBox("Пропавшие (Red)");
        self.chk_lost.setChecked(True)

        for chk in [self.chk_all, self.chk_active, self.chk_new, self.chk_lost]:
            chk.stateChanged.connect(self.apply_filters)

        filter_box.addWidget(QLabel("Фильтр:"))
        filter_box.addWidget(self.chk_all)
        filter_box.addWidget(self.chk_active)
        filter_box.addWidget(self.chk_new)
        filter_box.addWidget(self.chk_lost)
        filter_box.addStretch()
        l.addLayout(filter_box)

        l.addWidget(QLabel("Список URL:"))
        self.gsc_urls = QTextEdit()
        self.gsc_urls.setMaximumHeight(100)  # Увеличил высоту поля ссылок (было 60)
        l.addWidget(self.gsc_urls)

        b_run = QPushButton("📊 ПРОВЕРИТЬ ПОЗИЦИИ");
        b_run.clicked.connect(self.run_gsc)
        b_run.setStyleSheet("background: #9a7ecc; color: white; font-weight: bold; padding: 8px;")
        l.addWidget(b_run)

        # 4. Дерево
        self.gsc_tree = QTreeWidget()
        self.gsc_tree.setHeaderLabels(["Keyword / URL", "Position", "Change", "Clicks", "Impr"])
        self.gsc_tree.setColumnWidth(0, 400)  # Чуть шире колонка ключей
        self.gsc_tree.setSortingEnabled(True)
        self.gsc_tree.setAlternatingRowColors(True)
        self.gsc_tree.itemDoubleClicked.connect(self.copy_tree_item)
        l.addWidget(self.gsc_tree, stretch=3)

        self.gsc_prog = QProgressBar();
        self.gsc_prog.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(self.gsc_prog)
        self.gsc_log = QLabel("Ready")
        l.addWidget(self.gsc_log)

        self.refresh_groups_combo()
        self.current_data_cache = {}

    def run_gsc(self):
        key = self.gsc_key.text()
        urls = [x.strip() for x in self.gsc_urls.toPlainText().splitlines() if x.strip().startswith('http')]
        country = self.gsc_country.currentData()

        if not key or not urls: return
        self.gsc_tree.clear()
        self.gsc_log.setText("Starting analysis...")

        self.worker3 = GscKeywordsWorker(key, urls, country)
        self.worker3.data_signal.connect(self.fill_gsc_tree)
        self.worker3.log_signal.connect(self.gsc_log.setText)
        self.worker3.progress_signal.connect(lambda c, t: (self.gsc_prog.setMaximum(t), self.gsc_prog.setValue(c)))
        self.worker3.start()

    def fill_gsc_tree(self, data, save_to_cache=True):
        # ВСЕГДА обновляем кэш памяти, чтобы фильтры работали с актуальными данными
        self.current_data_cache = data

        if save_to_cache:
            # Сохраняем на диск только когда пришли новые данные от Гугла
            try:
                full_cache = {}
                if os.path.exists(self.cache_file):
                    with open(self.cache_file, 'r', encoding='utf-8') as f: full_cache = json.load(f)
                full_cache.update(data)
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(full_cache, f, indent=2, ensure_ascii=False)
            except:
                pass

        self.gsc_tree.clear()
        self.gsc_tree.setSortingEnabled(False)  # Отключаем на время вставки

        font_bold = QFont();
        font_bold.setBold(True)

        show_active = self.chk_active.isChecked()
        show_new = self.chk_new.isChecked()
        show_lost = self.chk_lost.isChecked()
        if not self.chk_all.isChecked():
            # Если "Все" выключено, смотрим только на конкретные
            pass
        else:
            # Если "Все" включено - показываем всё (можно упростить логику по желанию)
            show_active = show_new = show_lost = True

        for url, keywords in data.items():
            parent = QTreeWidgetItem(self.gsc_tree)
            parent.setText(0, url)
            parent.setFont(0, font_bold)
            parent.setForeground(0, QBrush(QColor("#61afef")))

            visible_count = 0

            if not keywords:
                # ... (код для пустых)
                continue

            for k in keywords:
                status = k.get('status', 'ACTIVE')

                # Фильтрация
                if status == 'ACTIVE' and not show_active: continue
                if status == 'NEW' and not show_new: continue
                if status == 'LOST' and not show_lost: continue

                child = QTreeWidgetItem(parent)
                child.setText(0, k['kw'])

                # Сортировка чисел (через setData чтобы сортировалось как число, а не текст)
                child.setData(1, Qt.ItemDataRole.DisplayRole, float(k['pos']))

                # Раскраска
                if status == 'NEW':
                    child.setForeground(0, QBrush(QColor("#89d185")))  # Зеленый текст
                    child.setFont(0, font_bold)
                    child.setToolTip(0, "Новый ключ (появился сегодня)")
                elif status == 'LOST':
                    child.setForeground(0, QBrush(QColor("#f14c4c")))  # Красный текст
                    child.setFont(0, font_bold)
                    child.setToolTip(0, "Ключ пропал из выдачи (Top 50)")
                    # Для пропавших позиция может быть старой, можно сделать серым
                    child.setForeground(1, QBrush(QColor("gray")))

                # Стрелочки (Change)
                diff = k.get('diff', 0)
                if diff > 0:
                    child.setText(2, f"▲ +{diff:.1f}")
                    child.setForeground(2, QBrush(QColor("#89d185")))
                elif diff < 0:
                    child.setText(2, f"▼ {diff:.1f}")
                    child.setForeground(2, QBrush(QColor("#f14c4c")))
                else:
                    child.setText(2, "●")
                    child.setForeground(2, QBrush(QColor("#555")))

                child.setText(3, str(k.get('clicks', 0)))
                child.setText(4, str(k.get('imp', 0)))
                visible_count += 1

            parent.setText(1, f"{visible_count}")
            parent.setExpanded(True)

        self.gsc_tree.setSortingEnabled(True)  # Включаем обратно
        if save_to_cache: self.gsc_log.setText("Данные обновлены.")

    # ------------------------------------------------------------------
    # ЛОГИКА ГРУПП (Сохранение/Загрузка)
    # ------------------------------------------------------------------
    def get_all_groups(self):
        if os.path.exists(self.groups_file):
            try:
                with open(self.groups_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_all_groups(self, data):
        try:
            with open(self.groups_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить группы: {e}")

    def refresh_groups_combo(self):
        groups = self.get_all_groups()
        current = self.group_combo.currentText()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        if groups:
            self.group_combo.addItems(sorted(groups.keys()))
            if current in groups:
                self.group_combo.setCurrentText(current)
        else:
            self.group_combo.addItem("-- Нет групп --")
        self.group_combo.blockSignals(False)
        self.load_group_urls()  # Загружаем URL для текущей

    def create_group(self):
        name, ok = QInputDialog.getText(self, "Новая группа", "Введите название группы:")
        if ok and name:
            groups = self.get_all_groups()
            if name in groups:
                QMessageBox.warning(self, "Ошибка", "Группа с таким именем уже есть!")
                return
            groups[name] = []  # Создаем пустую
            self.save_all_groups(groups)
            self.refresh_groups_combo()
            self.group_combo.setCurrentText(name)

    def delete_group(self):
        name = self.group_combo.currentText()
        if name == "-- Нет групп --": return

        reply = QMessageBox.question(self, "Удаление", f"Удалить группу '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            groups = self.get_all_groups()
            if name in groups:
                del groups[name]
                self.save_all_groups(groups)
                self.refresh_groups_combo()

    def save_urls_to_group(self):
        name = self.group_combo.currentText()
        if name == "-- Нет групп --":
            QMessageBox.warning(self, "Ошибка", "Сначала создайте группу!")
            return

        # Берем текст из поля, чистим
        urls = [u.strip() for u in self.gsc_urls.toPlainText().splitlines() if u.strip()]

        groups = self.get_all_groups()
        groups[name] = urls
        self.save_all_groups(groups)

        # Визуальный эффект (мигание кнопки или лог)
        self.gsc_log.setText(f"✅ Группа '{name}' сохранена ({len(urls)} ссылок)")

    def load_group_urls(self):
        name = self.group_combo.currentText()
        groups = self.get_all_groups()

        self.gsc_tree.clear()  # Очищаем таблицу перед загрузкой

        if name in groups:
            urls = groups[name]
            self.gsc_urls.setPlainText("\n".join(urls))

            # --- НОВАЯ ЛОГИКА: Попытка загрузить из кэша ---
            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, 'r', encoding='utf-8') as f:
                        full_cache = json.load(f)

                    # Отбираем данные только для URL из этой группы
                    group_data = {}
                    for url in urls:
                        url = url.strip()
                        if url in full_cache:
                            group_data[url] = full_cache[url]

                    # Если нашли данные - отображаем (save_to_cache=False, чтобы не перезаписывать)
                    if group_data:
                        self.current_data_cache = group_data
                        self.fill_gsc_tree(group_data, save_to_cache=False)
                        self.gsc_log.setText(f"Загружены сохраненные данные для группы '{name}'")
                    else:
                        self.gsc_log.setText("Нет сохраненных данных. Нажмите 'ПРОВЕРИТЬ ПОЗИЦИИ'.")

                except Exception as e:
                    self.gsc_log.setText(f"Ошибка кэша: {e}")
        else:
            self.gsc_urls.clear()

    def apply_filters(self):
        # Просто перерисовываем дерево из кэша памяти
        if self.current_data_cache:
            self.fill_gsc_tree(self.current_data_cache, save_to_cache=False)

    def export_group_csv(self):
        if not self.current_data_cache:
            QMessageBox.warning(self, "Ошибка",
                                "Нет данных для экспорта. Сначала проверьте позиции или выберите группу.")
            return

        name = self.group_combo.currentText()
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", f"GSC_{name}.csv", "CSV (*.csv)")

        if path:
            try:
                with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f, delimiter=';')
                    writer.writerow(["URL", "Keyword", "Position", "Change", "Clicks", "Impressions", "Status"])

                    for url, keywords in self.current_data_cache.items():
                        for k in keywords:
                            writer.writerow([
                                url,
                                k['kw'],
                                str(k['pos']).replace('.', ','),
                                str(k.get('diff', 0)).replace('.', ','),
                                k.get('clicks', 0),
                                k.get('imp', 0),
                                k.get('status', 'ACTIVE')
                            ])
                QMessageBox.information(self, "Успех", f"Файл сохранен:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить CSV: {e}")

    def copy_tree_item(self, item, column):
        """Копирует текст ячейки в буфер обмена при двойном клике"""
        text = item.text(column)
        if text:
            QApplication.clipboard().setText(text)
            # Пишем в лог, чтобы было видно, что сработало
            self.gsc_log.setText(f"📋 Скопировано: {text}")
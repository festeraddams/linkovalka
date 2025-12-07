# content_replacer.py
"""
Диалог для пакетной замены контента из txt-файлов.
Использует единый движок content_engine.py
Включает мощный модуль для замены Meta-тегов (Title, OG, Twitter, JSON-LD).
"""

import os
import chardet
import re
import json  # Добавлено для работы с JSON-LD
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QTextEdit, QFileDialog,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHBoxLayout, QMessageBox,
    QProgressDialog, QComboBox
)
from PyQt6.QtCore import Qt
from bs4 import BeautifulSoup

# Единый движок замены контента
# Предполагается, что файл content_engine.py находится рядом
from content_engine import universal_replace_content, analyze_page_structure

# Список таблеток/синонимов
# Предполагается, что файл url_from_folder.py находится рядом
from url_from_folder import KEYWORDS as URL_KEYWORDS


class ReplaceFromTxtDialog(QDialog):
    """
    Диалог для пакетной замены контента на HTML-страницах
    по заранее подготовленным txt/html-фрагментам.
    """

    def __init__(self, content_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Замена контента из txt файлов")
        self.setMinimumSize(1400, 900)
        self.content_dir = content_dir

        # Папка для текстов замены (рядом со скриптом)
        self.texts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "text_for_replace")
        if not os.path.isdir(self.texts_dir):
            os.makedirs(self.texts_dir, exist_ok=True)

        self._init_ui()
        self.populate_file_table()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # ─── Таблица файлов ───
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(6)
        self.file_table.setHorizontalHeaderLabels([
            "✓", "HTML Файл", "Title", "Description", "Контент (txt)", "Путь"
        ])
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.file_table.setColumnWidth(0, 40)
        self.file_table.setColumnWidth(1, 350)
        self.file_table.setColumnWidth(2, 250)
        self.file_table.setColumnWidth(3, 250)
        self.file_table.setColumnWidth(4, 200)
        self.file_table.setColumnWidth(5, 250)

        main_layout.addWidget(QLabel("Список HTML-страниц:"))
        main_layout.addWidget(self.file_table)

        # ─── Счётчик страниц ───
        self.pages_count_label = QLabel("")
        main_layout.addWidget(self.pages_count_label)

        # ─── Инфо ───
        info_lbl = QLabel(
            "<i>Выберите txt-файл с контентом для каждой HTML-страницы.<br>"
            "После замены txt-файл будет переименован в used_*.txt</i>"
        )
        main_layout.addWidget(info_lbl)

        # ─── Кнопки ───
        btn_layout = QHBoxLayout()

        self.auto_select_btn = QPushButton("🔍 Автоподбор файлов")
        self.auto_select_btn.clicked.connect(self.on_auto_select_files)
        btn_layout.addWidget(self.auto_select_btn)

        self.analyze_btn = QPushButton("📊 Анализ структуры")
        self.analyze_btn.clicked.connect(self.on_analyze_structure)
        btn_layout.addWidget(self.analyze_btn)

        btn_layout.addStretch()

        self.replace_btn = QPushButton("🔄 Заменить контент")
        self.replace_btn.setStyleSheet("""
            QPushButton {
                background: #28a745;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover { background: #2ea44f; }
        """)
        self.replace_btn.clicked.connect(self.on_replace_content)
        btn_layout.addWidget(self.replace_btn)

        self.batch_meta_btn = QPushButton("📝 Пакетно заменить Title/Desc")
        self.batch_meta_btn.clicked.connect(self.on_batch_meta_update)
        btn_layout.addWidget(self.batch_meta_btn)

        main_layout.addLayout(btn_layout)

        # ─── Лог ───
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(200)
        main_layout.addWidget(QLabel("Лог:"))
        main_layout.addWidget(self.log_edit)

    def get_available_texts(self, exclude_set=None):
        """Возвращает список доступных txt-файлов."""
        exclude_set = exclude_set or set()
        files = []
        if os.path.isdir(self.texts_dir):
            for f in os.listdir(self.texts_dir):
                if f.endswith('.txt') and not f.startswith('used_'):
                    if f.lower() not in exclude_set:
                        files.append(f)
        return sorted(files)

    def populate_file_table(self):
        """Заполняет таблицу HTML-файлами."""
        self.file_table.setRowCount(0)

        if not self.content_dir or not os.path.isdir(self.content_dir):
            return

        row = 0
        for root, dirs, files in os.walk(self.content_dir):
            for fname in files:
                if not fname.endswith('.html'):
                    continue

                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, self.content_dir)

                # Читаем title и description
                title, desc = self._extract_meta(full_path)

                self.file_table.insertRow(row)

                # Чекбокс
                chk = QTableWidgetItem()
                chk.setCheckState(Qt.CheckState.Unchecked)
                chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                self.file_table.setItem(row, 0, chk)

                # HTML файл
                self.file_table.setItem(row, 1, QTableWidgetItem(rel_path))

                # Title
                self.file_table.setItem(row, 2, QTableWidgetItem(title[:100] if title else ""))

                # Description
                self.file_table.setItem(row, 3, QTableWidgetItem(desc[:150] if desc else ""))

                # ComboBox для выбора txt-файла
                combo = QComboBox()
                combo.addItem("— Выбрать файл —")
                for txt_file in self.get_available_texts():
                    combo.addItem(txt_file)
                combo.currentIndexChanged.connect(lambda idx, r=row: self.on_select_text_file(r, idx))
                self.file_table.setCellWidget(row, 4, combo)

                # Путь к txt (скрытый)
                self.file_table.setItem(row, 5, QTableWidgetItem(""))

                row += 1

        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.pages_count_label.setText(f"<b>Всего HTML-страниц:</b> {row}")
        self.update_all_combos()

    def _extract_meta(self, filepath: str):
        """Извлекает title и description из HTML."""
        try:
            with open(filepath, 'rb') as f:
                raw = f.read()
            enc = chardet.detect(raw).get('encoding') or 'utf-8'
            html_content = raw.decode(enc, errors='replace')

            soup = BeautifulSoup(html_content, 'html.parser')

            title = ""
            if soup.title:
                title = soup.title.get_text(strip=True)

            desc = ""
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                desc = meta_desc.get('content', '')

            return title, desc
        except Exception:
            return "", ""

    def update_all_combos(self):
        """Обновляет все ComboBox, скрывая уже выбранные файлы."""
        # Собираем уже выбранные файлы
        selected_files = set()
        for i in range(self.file_table.rowCount()):
            path_item = self.file_table.item(i, 5)
            if path_item and path_item.text():
                selected_files.add(os.path.basename(path_item.text()).lower())

        # Обновляем каждый комбобокс
        for i in range(self.file_table.rowCount()):
            combo = self.file_table.cellWidget(i, 4)
            if not combo:
                continue

            current = combo.currentText()

            combo.blockSignals(True)
            combo.clear()
            combo.addItem("— Выбрать файл —")

            for txt_file in self.get_available_texts():
                # Показываем файл если он не выбран ИЛИ это текущий выбор
                if txt_file.lower() not in selected_files or txt_file == current:
                    combo.addItem(txt_file)

            # Восстанавливаем выбор
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)

            combo.blockSignals(False)

    def on_select_text_file(self, row, idx):
        """Обработчик выбора txt-файла."""
        combo = self.file_table.cellWidget(row, 4)
        fname = combo.currentText()

        if not fname or fname.startswith("—"):
            self.file_table.item(row, 5).setText("")
            self.file_table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
            self.update_all_combos()
            return

        # Проверяем дубликаты
        for other_row in range(self.file_table.rowCount()):
            if other_row != row:
                other_combo = self.file_table.cellWidget(other_row, 4)
                if other_combo and other_combo.currentText() == fname:
                    QMessageBox.warning(
                        self, "Ошибка",
                        f"Файл '{fname}' уже выбран для другой страницы!"
                    )
                    combo.blockSignals(True)
                    combo.setCurrentIndex(0)
                    combo.blockSignals(False)
                    self.file_table.item(row, 5).setText("")
                    self.file_table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
                    self.update_all_combos()
                    return

        # Устанавливаем путь и отмечаем
        full_path = os.path.join(self.texts_dir, fname)
        self.file_table.item(row, 5).setText(full_path)
        self.file_table.item(row, 0).setCheckState(Qt.CheckState.Checked)

        # Визуальное выделение
        for c in range(self.file_table.columnCount()):
            item = self.file_table.item(row, c)
            if item:
                item.setForeground(Qt.GlobalColor.blue)

        self.update_all_combos()

    def on_analyze_structure(self):
        """Анализирует структуру выбранных страниц."""
        selected = []
        for i in range(self.file_table.rowCount()):
            if self.file_table.item(i, 0).checkState() == Qt.CheckState.Checked:
                selected.append((i, self.file_table.item(i, 1).text()))

        if not selected:
            QMessageBox.warning(self, "Внимание", "Выберите страницы для анализа!")
            return

        self.log_edit.clear()
        self.log_edit.append("=== АНАЛИЗ СТРУКТУРЫ СТРАНИЦ ===\n")

        for row, rel_path in selected[:10]:
            full_path = os.path.join(self.content_dir, rel_path)
            try:
                with open(full_path, 'rb') as f:
                    raw = f.read()
                enc = chardet.detect(raw).get('encoding') or 'utf-8'
                html_content = raw.decode(enc, errors='replace')

                analysis = analyze_page_structure(html_content)

                self.log_edit.append(f"📄 {rel_path}")
                self.log_edit.append(
                    f"   Контейнер: {'✅ ' + str(analysis['container_selector']) if analysis['container_found'] else '❌ Не найден'}")
                self.log_edit.append(f"   H1: {'✅' if analysis['h1_found'] else '❌ Не найден'}")
                self.log_edit.append(f"   Сохраняемых элементов: {analysis['preserved_count']}")
                self.log_edit.append("")

            except Exception as e:
                self.log_edit.append(f"❌ {rel_path}: {e}\n")

    def on_replace_content(self):
        """Заменяет контент на выбранных страницах."""
        selected = []
        for i in range(self.file_table.rowCount()):
            chk = self.file_table.item(i, 0)
            path_item = self.file_table.item(i, 5)
            if chk.checkState() == Qt.CheckState.Checked and path_item and path_item.text().strip():
                html_rel = self.file_table.item(i, 1).text()
                txt_path = path_item.text().strip()
                selected.append((i, html_rel, txt_path))

        if not selected:
            QMessageBox.warning(self, "Внимание", "Не выбрано ни одной строки с контентом!")
            return

        self.log_edit.clear()
        self.log_edit.append(f"Начинаю замену контента для {len(selected)} страниц...\n")

        success_count = 0
        error_count = 0

        for i, html_rel, txt_path in selected:
            html_full = os.path.join(self.content_dir, html_rel)

            try:
                # Читаем HTML
                with open(html_full, "rb") as f:
                    raw = f.read()
                enc = chardet.detect(raw).get("encoding") or "utf-8"
                old_html = raw.decode(enc, errors="replace")

                # Читаем новый контент
                with open(txt_path, "r", encoding="utf-8", errors="replace") as t:
                    new_content = t.read()

                # Меняем через единый движок
                new_html = universal_replace_content(old_html, new_content)

                # Сохраняем без лишних пустых строк:
                # нормализуем \r\n / \r -> \n и фиксируем newline="\n"
                normalized_html = new_html.replace("\r\n", "\n").replace("\r", "\n")
                with open(html_full, "w", encoding=enc, errors="replace", newline="\n") as f:
                    f.write(normalized_html)

                # Переименовываем txt в used_
                dir_, base = os.path.split(txt_path)
                used_name = os.path.join(dir_, "used_" + base)
                os.rename(txt_path, used_name)

                self.log_edit.append(f"✅ {html_rel}")

                # Визуальная отметка
                self.file_table.item(i, 5).setText("")
                self.file_table.item(i, 0).setCheckState(Qt.CheckState.Unchecked)
                for c in range(self.file_table.columnCount()):
                    item = self.file_table.item(i, c)
                    if item:
                        item.setForeground(Qt.GlobalColor.darkGreen)

                success_count += 1

            except ValueError as ve:
                self.log_edit.append(f"⚠️ {html_rel}: {ve}")
                for c in range(self.file_table.columnCount()):
                    item = self.file_table.item(i, c)
                    if item:
                        item.setForeground(Qt.GlobalColor.darkYellow)
                error_count += 1

            except Exception as e:
                self.log_edit.append(f"❌ {html_rel}: {e}")
                for c in range(self.file_table.columnCount()):
                    item = self.file_table.item(i, c)
                    if item:
                        item.setForeground(Qt.GlobalColor.red)
                error_count += 1

        self.log_edit.append(f"\n{'=' * 50}")
        self.log_edit.append(f"✅ Успешно: {success_count}")
        self.log_edit.append(f"❌ Ошибок: {error_count}")

        self.update_all_combos()
        QMessageBox.information(self, "Готово", f"Замена завершена!\nУспешно: {success_count}\nОшибок: {error_count}")

    def on_auto_select_files(self):
        """Автоматический подбор txt-файлов по ключевым словам."""
        keywords = list({
            *map(str.lower, URL_KEYWORDS.keys()),
            *map(str.lower, URL_KEYWORDS.values())
        })

        # Занятые файлы
        busy = {
            os.path.basename(self.file_table.item(r, 5).text()).lower()
            for r in range(self.file_table.rowCount())
            if self.file_table.item(r, 5).text().strip()
        }

        # Свободные файлы
        free_files = [f for f in self.get_available_texts() if f.lower() not in busy]

        matched = 0
        for row in range(self.file_table.rowCount()):
            if self.file_table.item(row, 5).text().strip():
                continue

            title_lc = self.file_table.item(row, 2).text().lower()
            match_file = None

            for kw in keywords:
                if kw in title_lc:
                    for fname in free_files:
                        if kw in fname.lower():
                            match_file = fname
                            break
                if match_file:
                    break

            if match_file:
                combo = self.file_table.cellWidget(row, 4)
                if combo:
                    combo.blockSignals(True)
                    idx = combo.findText(match_file)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    combo.blockSignals(False)

                full_path = os.path.join(self.texts_dir, match_file)
                self.file_table.item(row, 5).setText(full_path)
                self.file_table.item(row, 0).setCheckState(Qt.CheckState.Checked)

                for c in range(self.file_table.columnCount()):
                    item = self.file_table.item(row, c)
                    if item:
                        item.setForeground(Qt.GlobalColor.blue)

                free_files.remove(match_file)
                matched += 1

        self.update_all_combos()
        QMessageBox.information(self, "Автоподбор", f"Подобрано файлов: {matched}")

    def on_batch_meta_update(self):
        """Пакетное обновление Title/Description."""
        dlg = BatchMetaUpdateDialog(self.content_dir, self)
        dlg.exec()


# ─────────────────────────────────────────────────────────────────────────────
# ДИАЛОГ ПАКЕТНОГО ОБНОВЛЕНИЯ META (ОБНОВЛЕННАЯ ЛОГИКА)
# ─────────────────────────────────────────────────────────────────────────────
class BatchMetaUpdateDialog(QDialog):
    """Диалог для пакетной замены title/description (Deep Regex Replace)."""

    def __init__(self, content_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Пакетное обновление Title/Description (Full)")
        self.setMinimumSize(800, 600)
        self.content_dir = content_dir

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Формат файла: каждая строка = title|description\n"
            "Скрипт обновит: Title, Description, OG:Tags, Twitter Cards, JSON-LD"
        ))

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("New Title 1|New description 1\nNew Title 2|New description 2")
        layout.addWidget(self.text_edit)

        btn_row = QHBoxLayout()

        load_btn = QPushButton("Загрузить из файла")
        load_btn.clicked.connect(self._load_from_file)
        btn_row.addWidget(load_btn)

        btn_row.addStretch()

        apply_btn = QPushButton("Применить")
        apply_btn.clicked.connect(self._apply)
        btn_row.addWidget(apply_btn)

        layout.addLayout(btn_row)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        layout.addWidget(self.log)

    def _load_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать файл", "", "Text Files (*.txt)")
        if path:
            with open(path, 'r', encoding='utf-8') as f:
                self.text_edit.setText(f.read())

    def _apply(self):
        """Применяет изменения, используя REGEX (как в старом файле)."""
        lines = self.text_edit.toPlainText().strip().split('\n')
        lines = [l.strip() for l in lines if l.strip()]

        if not lines:
            QMessageBox.warning(self, "Ошибка", "Введите данные!")
            return

        # Собираем HTML-файлы
        html_files = []
        for root, dirs, files in os.walk(self.content_dir):
            for f in sorted(files):
                if f.endswith('.html'):
                    html_files.append(os.path.join(root, f))

        if len(lines) < len(html_files):
            QMessageBox.warning(
                self, "Внимание",
                f"Строк ({len(lines)}) меньше чем файлов ({len(html_files)})!"
            )

        self.log.clear()

        # Прогресс бар, так как операции могут быть долгими
        progress = QProgressDialog("Применяем обновления...", "Отмена", 0, len(html_files), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        updated_count = 0

        for i, html_path in enumerate(html_files):
            progress.setValue(i)
            if progress.wasCanceled():
                break

            if i >= len(lines):
                break

            line = lines[i]
            if '|' not in line:
                self.log.append(f"⚠️ Строка {i + 1}: нет разделителя |")
                continue

            # Разделяем title и desc
            title, desc = line.split('|', 1)
            title = title.strip()
            desc = desc.strip()

            try:
                # 1. Читаем файл с автоопределением кодировки (чтобы не сломать)
                with open(html_path, 'rb') as f:
                    raw = f.read()
                enc = chardet.detect(raw).get('encoding') or 'utf-8'
                content = raw.decode(enc, errors='replace')

                # 2. Применяем регулярные выражения (Логика из content_replacer_old.py)

                # Title
                content = replace_title(content, title)

                # OpenGraph Title
                content = replace_og_title(content, title)

                # JSON-LD Name
                content = replace_json_field_preserving_format(content, "name", title)

                # Meta Description (name="description") + OpenGraph Description (og:description)
                content, replaced_name = replace_meta_desc(content, "name", "description", desc)
                content, replaced_og = replace_meta_desc(content, "property", "og:description", desc)

                # JSON-LD Description
                content = replace_json_field_preserving_format(content, "description", desc)

                # Twitter Cards
                content = replace_twitter_title(content, title)
                content = replace_twitter_description(content, desc)

                # Если meta description не найден, добавляем его принудительно после title
                if not replaced_name:
                    pat_title = re.compile(r"<title[^>]*>.*?</title>", re.IGNORECASE | re.DOTALL)
                    m_title = pat_title.search(content)
                    if m_title:
                        pos = m_title.end()
                        content = (
                                content[:pos]
                                + f'\n    <meta name="description" content="{desc}">'
                                + content[pos:]
                        )

                # 3. Сохраняем файл обратно
                with open(html_path, 'w', encoding=enc, errors='replace') as f:
                    f.write(content)

                self.log.append(f"✅ {os.path.basename(html_path)}")
                updated_count += 1

            except Exception as e:
                self.log.append(f"❌ {os.path.basename(html_path)}: {e}")

        progress.setValue(len(html_files))
        QMessageBox.information(self, "Готово", f"Обновление завершено!\nОбновлено файлов: {updated_count}")


# ─────────────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (ИЗ STAROGO FILE) ДЛЯ РАБОТЫ С REGEX И JSON
# ─────────────────────────────────────────────────────────────────────────────

def replace_title(content: str, new_val: str) -> str:
    pat = re.compile(r'(<title>)(.*?)(</title>)', re.IGNORECASE | re.DOTALL)
    mm = pat.search(content)
    if mm:
        return pat.sub(lambda m: m.group(1) + new_val + m.group(3), content, 1)
    else:
        pat_head = re.compile(r"<head[^>]*>", re.IGNORECASE)
        mh = pat_head.search(content)
        if mh:
            pos = mh.end()
            return content[:pos] + f"\n<title>{new_val}</title>" + content[pos:]
    return content


def replace_og_title(content: str, new_val: str) -> str:
    pat = re.compile(
        r'(<meta\s+property=["\']og:title["\']\s+content=["\'])(.*?)(["\'])',
        re.IGNORECASE | re.DOTALL
    )
    return pat.sub(lambda m: m.group(1) + new_val + m.group(3), content)


def replace_meta_desc(content: str, attr: str, value: str, new_val: str):
    pat = re.compile(
        rf'(<meta\s+{attr}=["\']{value}["\']\s+content=["\'])(.*?)(["\'])',
        re.IGNORECASE | re.DOTALL
    )
    mm = pat.search(content)
    if mm:
        new_html = pat.sub(lambda m: m.group(1) + new_val + m.group(3), content, 1)
        return new_html, True
    return content, False


def replace_twitter_title(content: str, new_val: str):
    pat = re.compile(
        r'(<meta\s+name=["\']twitter:title["\']\s+content=["\'])(.*?)(["\'])',
        re.IGNORECASE | re.DOTALL
    )
    return pat.sub(lambda m: m.group(1) + new_val + m.group(3), content)


def replace_twitter_description(content: str, new_val: str):
    pat = re.compile(
        r'(<meta\s+name=["\']twitter:description["\']\s+content=["\'])(.*?)(["\'])',
        re.IGNORECASE | re.DOTALL
    )
    return pat.sub(lambda m: m.group(1) + new_val + m.group(3), content)


def replace_json_field_preserving_format(original_text, field_name, new_value):
    pattern_script = re.compile(
        r'(<script[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
        re.IGNORECASE | re.DOTALL
    )
    match_script = pattern_script.search(original_text)
    if not match_script:
        return original_text

    json_body = match_script.group(2)
    # Пытаемся распарсить, чтобы убедиться что это валидный JSON
    try:
        data = json.loads(json_body)
    except:
        return original_text

    # Рекурсивная проверка наличия поля
    def has_field(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if k == field_name:
                    return True
                if isinstance(v, (dict, list)):
                    if has_field(v):
                        return True
        elif isinstance(d, list):
            for x in d:
                if has_field(x):
                    return True
        return False

    if not has_field(data):
        return original_text

    # Замена через Regex внутри найденного блока скрипта, чтобы сохранить отступы
    field_esc = re.escape(field_name)
    pattern_field = re.compile(
        rf'(["\']){field_esc}\1(\s*:\s*)(["\'])(.*?)\3',
        re.IGNORECASE | re.DOTALL
    )
    replaced_text, count = pattern_field.subn(
        lambda m: (
                f'{m.group(1)}{field_name}{m.group(1)}'
                + m.group(2)
                + m.group(3)
                + new_value
                + m.group(3)
        ),
        json_body
    )
    if count == 0:
        return original_text

    def replacer_script(m):
        return m.group(1) + replaced_text + m.group(3)

    return pattern_script.sub(replacer_script, original_text, 1)
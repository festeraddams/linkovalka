"""
content_generator.py – v3.1 (Unified Engine + Per-Article Randomization)
• Генерация SEO-контента через LM Studio.
• РАНДОМ ПРОМПТА ДЛЯ КАЖДОЙ СТАТЬИ (не один на пакет!)
• Использует единый движок content_engine.py для замены контента.
"""

from __future__ import annotations
import os
import json
import chardet
import logging
import random
from pathlib import Path
from typing import Dict, List, Tuple

from lxml import etree, html
try:
    import cssselect
except ImportError:
    cssselect = None

from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QTextEdit, QMessageBox,
    QLineEdit, QSpinBox, QComboBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHBoxLayout, QCheckBox, QPlainTextEdit,
)

# Единый движок замены контента
from content_engine import (
    replace_content, smart_replace_content, analyze_page_structure,
    detect_page_type_from_html, PageType
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s content_generator | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


class PromptManager:
    def __init__(self, json_path="assets/prompts.json"):
        self.json_path = json_path
        self.prompts_data = {}
        self.load_prompts()

    def load_prompts(self):
        if os.path.exists(self.json_path):
            with open(self.json_path, "r", encoding="utf-8") as f:
                self.prompts_data = json.load(f)
        else:
            self.prompts_data = {"new_prompt": []}

    def get_prompts(self, key: str):
        return self.prompts_data.get(key, [])


class BatchGenThread(QThread):
    """
    Поток для пакетной генерации.
    ВАЖНО: если random_mode=True, выбирает НОВЫЙ промпт для КАЖДОЙ статьи!
    """
    finishedOne = pyqtSignal(int, str)
    finishedAll = pyqtSignal()

    def __init__(self, rows_info, prompts_list, chosen_prompt_idx, random_mode,
                 global_keywords, density, lm_studio, content_dir, parent=None):
        super().__init__(parent)
        self.rows_info = rows_info
        self.prompts_list = prompts_list          # Весь список промптов
        self.chosen_prompt_idx = chosen_prompt_idx # Выбранный индекс (если не рандом)
        self.random_mode = random_mode            # Флаг рандома
        self.global_keywords = global_keywords
        self.density = density
        self.lm_studio = lm_studio
        self.content_dir = content_dir

    def run(self):
        for (row, file_, title_, desc_, local_kw) in self.rows_info:
            try:
                path = Path(self.content_dir, file_)

                # ---- ВЫБОР ПРОМПТА (для каждой статьи!) ----
                if self.random_mode and len(self.prompts_list) > 1:
                    # РАНДОМ для каждой статьи!
                    prompt_template = random.choice(self.prompts_list)
                    log.info(f"[RANDOM] Выбран промпт #{self.prompts_list.index(prompt_template)+1} для {file_}")
                else:
                    prompt_template = self.prompts_list[self.chosen_prompt_idx]

                # ---- ПОДСТАНОВКА ПЕРЕМЕННЫХ ----
                keys = [*self.global_keywords,
                        *[k.strip() for k in local_kw.split(",") if k.strip()]]

                prompt = (prompt_template
                          .replace("{title}", title_)
                          .replace("{description}", desc_)
                          .replace("{keywords}", ", ".join(keys) if keys else "extract from title")
                          .replace("{density}", f"{self.density}%"))

                # ---- ГЕНЕРАЦИЯ ----
                gen = self.lm_studio.generate_text(prompt)
                if gen.startswith("<e>"):
                    self.finishedOne.emit(row, f"[LM ERROR] {gen}")
                    continue

                # ---- ЧТЕНИЕ HTML ----
                raw = path.read_bytes()
                enc = chardet.detect(raw).get("encoding") or "utf-8"
                old_html = raw.decode(enc, "replace")

                # ---- ЗАМЕНА (единый движок) ----
                try:
                    new_html = smart_replace_content(old_html, gen)
                except ValueError as ve:
                    self.finishedOne.emit(row, f"[STRUCTURE ERROR] {file_}: {ve}")
                    continue
                except Exception as e:
                    self.finishedOne.emit(row, f"[REPLACE ERROR] {file_}: {e}")
                    continue

                # ---- НОРМАЛИЗАЦИЯ КОДИРОВКИ ----
                # LM Studio генерирует UTF-8 с Unicode-символами (умные кавычки, тире)
                # Всегда записываем в UTF-8 и обновляем meta charset
                normalized_html = new_html.replace("\r\n", "\n").replace("\r", "\n")

                # Обновляем meta charset на UTF-8 если он другой
                import re
                normalized_html = re.sub(
                    r'<meta\s+charset=["\']?[^"\'>\s]+["\']?\s*/?>',
                    '<meta charset="UTF-8">',
                    normalized_html,
                    flags=re.IGNORECASE
                )
                normalized_html = re.sub(
                    r'<meta\s+http-equiv=["\']?Content-Type["\']?\s+content=["\']?[^"\']+["\']?\s*/?>',
                    '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">',
                    normalized_html,
                    flags=re.IGNORECASE
                )

                # ---- ЗАПИСЬ (всегда UTF-8) ----
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(normalized_html)

                self.finishedOne.emit(row, f"[OK] {file_}")


            except Exception as e:
                self.finishedOne.emit(row, f"[FAIL] {file_}: {e}")

        self.finishedAll.emit()


class ContentRewriteDialog(QDialog):
    """
    Диалог для пакетной генерации SEO-контента через LM Studio.
    """

    def __init__(self, lm_studio, prompt_mgr: PromptManager, content_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Генерация SEO-контента (LM Studio)")
        self.setMinimumSize(1400, 900)

        self.lm_studio = lm_studio
        self.prompt_mgr = prompt_mgr
        self.content_dir = content_dir
        self.batch_thread = None

        self._init_ui()
        self._populate_file_table()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # ─── Промпты ───
        prompt_row = QHBoxLayout()
        prompt_row.addWidget(QLabel("Промпт:"))
        self.prompt_combo = QComboBox()
        self.prompt_combo.setMinimumWidth(500)
        self.update_prompt_combo()
        prompt_row.addWidget(self.prompt_combo)

        self.random_cb = QCheckBox("🎲 Рандом промпт (для каждой статьи!)")
        self.random_cb.setToolTip(
            "Если включено — для КАЖДОЙ статьи будет выбран случайный промпт.\n"
            "Это создаёт разнообразие в структуре и стиле статей."
        )
        self.random_cb.setStyleSheet("QCheckBox { color: #ffa500; font-weight: bold; }")
        prompt_row.addWidget(self.random_cb)
        prompt_row.addStretch()
        layout.addLayout(prompt_row)

        # ─── Инфо о промптах ───
        prompts_info = QLabel("")
        self._update_prompts_info(prompts_info)
        prompts_info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(prompts_info)
        self.prompts_info_label = prompts_info

        # ─── Ключевые слова ───
        kw_row = QHBoxLayout()
        kw_row.addWidget(QLabel("Глобальные ключевые слова:"))
        self.kw_edit = QLineEdit()
        self.kw_edit.setPlaceholderText("Оставьте пустым — ключи возьмутся из Title каждой страницы")
        kw_row.addWidget(self.kw_edit)
        layout.addLayout(kw_row)

        # ─── Плотность ───
        density_row = QHBoxLayout()
        density_row.addWidget(QLabel("Плотность ключевых слов (%):"))
        self.density_spin = QSpinBox()
        self.density_spin.setRange(1, 10)
        self.density_spin.setValue(3)
        density_row.addWidget(self.density_spin)
        density_row.addStretch()
        layout.addLayout(density_row)

        # ─── Таблица файлов ───
        layout.addWidget(QLabel("Файлы для обработки:"))
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(6)
        self.file_table.setHorizontalHeaderLabels([
            "✓", "Файл", "Title", "Description", "Local KW", "Статус"
        ])
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_table.setColumnWidth(0, 40)
        self.file_table.setColumnWidth(1, 350)
        self.file_table.setColumnWidth(2, 250)
        self.file_table.setColumnWidth(3, 250)
        self.file_table.setColumnWidth(4, 150)
        self.file_table.setColumnWidth(5, 150)
        layout.addWidget(self.file_table)

        # ─── Кнопки ───
        btn_row = QHBoxLayout()

        self.select_all_btn = QPushButton("Выбрать все")
        self.select_all_btn.clicked.connect(self._select_all)
        btn_row.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Снять все")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        btn_row.addWidget(self.deselect_all_btn)

        btn_row.addStretch()

        self.analyze_btn = QPushButton("Анализ структуры")
        self.analyze_btn.clicked.connect(self._analyze_selected)
        btn_row.addWidget(self.analyze_btn)

        self.generate_btn = QPushButton("🚀 Генерировать контент")
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background: #28a745;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover { background: #2ea44f; }
        """)
        self.generate_btn.clicked.connect(self.start_batch_generation)
        btn_row.addWidget(self.generate_btn)

        layout.addLayout(btn_row)

        # ─── Лог ───
        layout.addWidget(QLabel("Лог:"))
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(200)
        layout.addWidget(self.log_edit)

    def _update_prompts_info(self, label):
        prompts = self.prompt_mgr.get_prompts("new_prompt")
        styles = []
        style_names = ["Patient-Focused", "Clinical Deep-Dive", "Myth-Busting",
                       "How-To Guide", "Comparative", "Q&A Interview"]
        for i, name in enumerate(style_names[:len(prompts)]):
            styles.append(f"#{i+1}: {name}")
        if styles:
            label.setText(f"Доступно {len(prompts)} стилей: " + ", ".join(styles))

    def _populate_file_table(self):
        """Заполняет таблицу HTML-файлами из директории."""
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

                title, desc = self._extract_meta(full_path)

                self.file_table.insertRow(row)

                chk = QTableWidgetItem()
                chk.setCheckState(Qt.CheckState.Unchecked)
                chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                self.file_table.setItem(row, 0, chk)

                self.file_table.setItem(row, 1, QTableWidgetItem(rel_path))
                self.file_table.setItem(row, 2, QTableWidgetItem(title[:100] if title else ""))
                self.file_table.setItem(row, 3, QTableWidgetItem(desc[:150] if desc else ""))
                self.file_table.setItem(row, 4, QTableWidgetItem(""))
                self.file_table.setItem(row, 5, QTableWidgetItem("—"))

                row += 1

        self.file_table.horizontalHeader().setStretchLastSection(True)

    def _extract_meta(self, filepath: str) -> Tuple[str, str]:
        """Извлекает title и description из HTML-файла."""
        try:
            with open(filepath, 'rb') as f:
                raw = f.read()
            enc = chardet.detect(raw).get('encoding') or 'utf-8'
            html_content = raw.decode(enc, errors='replace')

            from bs4 import BeautifulSoup
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

    def update_prompt_combo(self):
        self.prompt_combo.clear()
        arr = self.prompt_mgr.get_prompts("new_prompt")
        if not arr:
            self.prompt_combo.addItem("— Нет промптов в prompts.json —")
        else:
            style_names = ["Patient-Focused", "Clinical Deep-Dive", "Myth-Busting",
                           "How-To Guide", "Comparative", "Q&A Interview"]
            for i, pr in enumerate(arr):
                name = style_names[i] if i < len(style_names) else f"Style {i+1}"
                preview = pr[:60].replace('\n', ' ')
                self.prompt_combo.addItem(f"#{i+1} [{name}]: {preview}…")

    def _select_all(self):
        for i in range(self.file_table.rowCount()):
            self.file_table.item(i, 0).setCheckState(Qt.CheckState.Checked)

    def _deselect_all(self):
        for i in range(self.file_table.rowCount()):
            self.file_table.item(i, 0).setCheckState(Qt.CheckState.Unchecked)

    def _analyze_selected(self):
        """Анализирует структуру выбранных файлов."""
        selected = []
        for i in range(self.file_table.rowCount()):
            if self.file_table.item(i, 0).checkState() == Qt.CheckState.Checked:
                selected.append((i, self.file_table.item(i, 1).text()))

        if not selected:
            QMessageBox.warning(self, "Внимание", "Выберите хотя бы один файл!")
            return

        self.log_edit.clear()
        self.log_edit.append("=== АНАЛИЗ СТРУКТУРЫ СТРАНИЦ (v4.0) ===\n")

        for row, rel_path in selected[:10]:  # Увеличил до 10
            full_path = os.path.join(self.content_dir, rel_path)
            try:
                with open(full_path, 'rb') as f:
                    raw = f.read()
                enc = chardet.detect(raw).get('encoding') or 'utf-8'
                html_content = raw.decode(enc, errors='replace')

                analysis = analyze_page_structure(html_content)

                # Иконка типа страницы
                type_icons = {
                    'POST': '📝',
                    'PAGE': '📄',
                    'CATEGORY': '📁',
                    'ARCHIVE': '📚',
                    'UNKNOWN': '❓'
                }
                type_icon = type_icons.get(analysis['page_type'], '❓')

                self.log_edit.append(f"{type_icon} {rel_path}")
                self.log_edit.append(f"   Тип: {analysis['page_type']}")
                self.log_edit.append(f"   Контейнер: {'✅ ' + str(analysis['container_selector']) if analysis['container_found'] else '❌ Не найден'}")
                self.log_edit.append(f"   H1: {'✅ ' + (analysis['h1_text'][:50] + '...' if analysis['h1_text'] else 'пусто') if analysis['h1_found'] else '❌ Не найден'}")

                # Для категорий показываем количество articles
                if analysis['page_type'] in ('CATEGORY', 'ARCHIVE'):
                    self.log_edit.append(f"   Articles в листинге: {analysis['articles_count']}")

                self.log_edit.append("")

            except Exception as e:
                self.log_edit.append(f"❌ {rel_path}: {e}\n")

    def start_batch_generation(self):
        """Запускает пакетную генерацию контента."""
        if not self.lm_studio:
            QMessageBox.warning(self, "Ошибка", "LM Studio не подключен!")
            return

        selected = []
        for i in range(self.file_table.rowCount()):
            if self.file_table.item(i, 0).checkState() == Qt.CheckState.Checked:
                selected.append((
                    i,
                    self.file_table.item(i, 1).text(),
                    self.file_table.item(i, 2).text(),
                    self.file_table.item(i, 3).text(),
                    self.file_table.item(i, 4).text(),
                ))

        if not selected:
            QMessageBox.warning(self, "Внимание", "Не выбрано ни одной строки!")
            return

        prompts = self.prompt_mgr.get_prompts("new_prompt")
        if not prompts:
            QMessageBox.warning(self, "Ошибка", "Нет промптов в prompts.json!")
            return

        # Определяем режим
        random_mode = self.random_cb.isChecked()
        chosen_idx = self.prompt_combo.currentIndex()

        if not random_mode and (chosen_idx < 0 or chosen_idx >= len(prompts)):
            QMessageBox.warning(self, "Ошибка", "Выберите промпт!")
            return

        global_kw = [k.strip() for k in self.kw_edit.text().split(",") if k.strip()]

        self.log_edit.clear()
        if random_mode:
            self.log_edit.append(f"🎲 РАНДОМ РЕЖИМ: каждая статья получит случайный стиль из {len(prompts)} вариантов\n")
        else:
            self.log_edit.append(f"📝 Фиксированный промпт #{chosen_idx+1}\n")
        self.log_edit.append(f"Запуск генерации для {len(selected)} файлов...\n")

        self.generate_btn.setEnabled(False)

        # ПЕРЕДАЁМ ВЕСЬ СПИСОК ПРОМПТОВ + режим рандома
        self.batch_thread = BatchGenThread(
            rows_info=selected,
            prompts_list=prompts,           # Весь список!
            chosen_prompt_idx=chosen_idx,
            random_mode=random_mode,        # Флаг рандома
            global_keywords=global_kw,
            density=self.density_spin.value(),
            lm_studio=self.lm_studio,
            content_dir=self.content_dir,
        )
        self.batch_thread.finishedOne.connect(self._on_one_finished)
        self.batch_thread.finishedAll.connect(self._on_all_finished)
        self.batch_thread.start()

    def _on_one_finished(self, row: int, msg: str):
        self.log_edit.append(msg)

        status_item = self.file_table.item(row, 5)
        if "[OK]" in msg:
            status_item.setText("✅ OK")
            for col in range(self.file_table.columnCount()):
                item = self.file_table.item(row, col)
                if item:
                    item.setForeground(Qt.GlobalColor.darkGreen)
        else:
            status_item.setText("❌ Error")
            for col in range(self.file_table.columnCount()):
                item = self.file_table.item(row, col)
                if item:
                    item.setForeground(Qt.GlobalColor.red)

        self.file_table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

    def _on_all_finished(self):
        self.log_edit.append("\n✅ Пакетная генерация завершена!")
        self.generate_btn.setEnabled(True)
        QMessageBox.information(self, "Готово", "Генерация контента завершена!")


if __name__ == "__main__":
    print("Импортируйте ContentRewriteDialog из content_generator в своём GUI.")
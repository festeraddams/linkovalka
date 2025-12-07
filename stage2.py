import os
import random
import re
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QFileDialog,
                            QMessageBox, QPlainTextEdit, QCheckBox, QSpinBox, QGroupBox)
from bs4 import BeautifulSoup, Comment

class SecondStageLinkDialog(QDialog):
    def __init__(self, base_dir, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.setWindowTitle("Внешние ссылки (2-й этап)")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(800)

        layout = QVBoxLayout()

        anchor_layout = QHBoxLayout()
        self.anchor_input = QPlainTextEdit()
        self.anchor_input.setPlaceholderText(
            "Вставьте готовые <a href=\"...\">Anchor</a> или ПРОИЗВОЛЬНЫЙ HTML, по одному на строке"
        )
        anchor_layout.addWidget(self.anchor_input)
        anchor_btns = QVBoxLayout()
        self.browse_button = QPushButton("Открыть файл с <a>")
        self.browse_button.clicked.connect(self.browse_anchor_file)
        anchor_btns.addWidget(self.browse_button)
        anchor_btns.addStretch()
        anchor_layout.addLayout(anchor_btns)
        layout.addLayout(anchor_layout)

        # --- Группа "Режим вставки" ---
        mode_group = QGroupBox("Режим вставки")
        mode_vbox = QVBoxLayout()
        self.allow_arbitrary_html_checkbox = QCheckBox("Разрешить произвольный HTML (не только <a>)")
        mode_vbox.addWidget(self.allow_arbitrary_html_checkbox)

        info_html = """
        <span style="font-size:13px;">
            <b>• Если <span style='color:#32aaff;'>ВКЛ</span></b> — вставляет HTML-блок <b>после</b> &lt;p&gt;, &lt;div&gt;, &lt;section&gt;, &lt;article&gt;.<br>
            <b>• Если <span style='color:#fca311;'>ВЫКЛ</span></b> — вставляет анкор <b>внутрь</b> текста абзаца &lt;p&gt;.<br>
            <b>Fallback:</b> если не найден ни один подходящий блок — вставка всегда в конец основного контейнера.
        </span>
        """
        info_label = QLabel(info_html)
        info_label.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #232e3a, stop:1 #253347);
            color: #d6eaff;
            border-radius: 7px;
            padding: 10px 15px;
            margin-bottom:8px;
            font-size:13px;
        """)
        info_label.setWordWrap(True)
        mode_vbox.addWidget(info_label)
        mode_group.setLayout(mode_vbox)
        layout.addWidget(mode_group)

        # --- Группа "Опции" ---
        options_group = QGroupBox("Опции")
        options_vbox = QVBoxLayout()
        self.allow_fallback_checkbox = QCheckBox("Фаллбек-вставка, если нет подходящих блоков")
        self.allow_fallback_checkbox.setChecked(True)
        options_vbox.addWidget(self.allow_fallback_checkbox)
        min_len_layout = QHBoxLayout()
        self.min_len_label = QLabel("Мин. длина текста абзаца/блока (20) симв.:")
        self.min_len_spin = QSpinBox()
        self.min_len_spin.setRange(1, 2000)
        self.min_len_spin.setValue(20)
        min_len_layout.addWidget(self.min_len_label)
        min_len_layout.addWidget(self.min_len_spin)
        options_vbox.addLayout(min_len_layout)
        options_group.setLayout(options_vbox)
        layout.addWidget(options_group)

        '''
        options_layout = QHBoxLayout()
        self.max_links_spin = QSpinBox()
        self.max_links_spin.setRange(1, 50)
        self.max_links_spin.setValue(1)
        self.sequential_checkbox = QCheckBox("Вставлять по порядку (иначе — рандом)")
        self.cycle_checkbox = QCheckBox("Повторять анкоры по кругу")
        self.cycle_checkbox.setChecked(True)
        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("Максимум ссылок на страницу:"))
        left_box.addWidget(self.max_links_spin)
        right_box = QVBoxLayout()
        right_box.addWidget(self.sequential_checkbox)
        right_box.addWidget(self.cycle_checkbox)
        options_layout.addLayout(left_box)
        options_layout.addLayout(right_box)
        layout.addLayout(options_layout)
        '''
        #Новый блок по ссылкам
        options_layout = QHBoxLayout()

        self.min_links_spin = QSpinBox()
        self.min_links_spin.setRange(1, 50)
        self.min_links_spin.setValue(1)

        self.max_links_spin = QSpinBox()
        self.max_links_spin.setRange(1, 50)
        self.max_links_spin.setValue(3)

        def update_min_max():
            min_val = self.min_links_spin.value()
            max_val = self.max_links_spin.value()
            if max_val < min_val:
                self.max_links_spin.setValue(min_val)

        self.min_links_spin.valueChanged.connect(update_min_max)
        self.max_links_spin.valueChanged.connect(update_min_max)

        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("Минимум ссылок на страницу:"))
        left_box.addWidget(self.min_links_spin)
        left_box.addWidget(QLabel("Максимум ссылок на страницу:"))
        left_box.addWidget(self.max_links_spin)



        links_box = QVBoxLayout()
        links_box.addWidget(QLabel("Минимум ссылок на страницу:"))
        links_box.addWidget(self.min_links_spin)
        links_box.addWidget(QLabel("Максимум ссылок на страницу:"))
        links_box.addWidget(self.max_links_spin)

        self.sequential_checkbox = QCheckBox("Вставлять по порядку (иначе — рандом)")
        self.cycle_checkbox = QCheckBox("Повторять анкоры по кругу")
        self.cycle_checkbox.setChecked(True)

        right_box = QVBoxLayout()
        right_box.addWidget(self.sequential_checkbox)
        right_box.addWidget(self.cycle_checkbox)

        options_layout.addLayout(links_box)
        options_layout.addLayout(right_box)
        layout.addLayout(options_layout)

        # === ВСТАВЬ СЮДА! ===
        fail_html = """
        <span style="font-size:12px; color:#e36464;">
            <b>Когда ссылка <u>НЕ будет вставлена</u>:</b><br>
            • Если после первого &lt;h1&gt; в главном контенте <b>нет ни одного абзаца &lt;p&gt; с длиной текста не меньше</b> значения выше (по умолчанию 20 символов).<br>
            • Если все такие &lt;p&gt; или их родители имеют класс/ID с "sidebar", "menu", "footer", "login", "captcha", "error".<br>
            • Если все такие &lt;p&gt; содержат только ссылки или слишком короткий текст.<br>
            • Если не включён <b>фаллбек</b>, и не найдено ни одного подходящего места.
        </span>
        """
        fail_label = QLabel(fail_html)
        fail_label.setWordWrap(True)
        layout.addWidget(fail_label)
        # === КОНЕЦ вставки ===



        btn_layout = QHBoxLayout()
        self.analyze_button = QPushButton("Анализ страниц")
        self.generate_button = QPushButton("Генерировать (2-й этап)")
        btn_layout.addWidget(self.analyze_button)
        btn_layout.addWidget(self.generate_button)
        layout.addLayout(btn_layout)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(QLabel("Лог (2-й этап):"))
        layout.addWidget(self.log_view)
        self.setLayout(layout)

        self.analyzed_pages = []
        self.anchors = []
        self.curr_index = 0

        self.analyze_button.clicked.connect(self.analyze_pages)
        self.generate_button.clicked.connect(self.generate_links)
        self.anchor_input.textChanged.connect(self.sync_anchors)

    def browse_anchor_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите файл с HTML-ссылками", "", "Text Files (*.txt)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.anchor_input.setPlainText(f.read())
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))

    def sync_anchors(self):
        lines = self.anchor_input.toPlainText().split('\n')
        anchors = [l.strip() for l in lines if l.strip()]
        self.anchors = anchors

    def analyze_pages(self):
        self.analyzed_pages = []
        self.log_view.clear()
        base_dir = self.base_dir
        if not os.path.exists(base_dir):
            self.log_view.append(f"Папка {base_dir} не найдена!")
            return
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                if file.endswith(".html"):
                    fullp = os.path.join(root, file)
                    rel = os.path.relpath(fullp, base_dir)
                    self.analyzed_pages.append(rel)
                    self.log_view.append(f"Найдена страница: {rel}")
        self.log_view.append(f"\nВсего найдено страниц: {len(self.analyzed_pages)}")
        self.sync_anchors()
        self.log_view.append(f"Загружено строк (2-й этап): {len(self.anchors)}")

    def get_next_anchor(self):
        if not self.anchors:
            return None
        if not self.sequential_checkbox.isChecked():
            return random.choice(self.anchors)
        if self.curr_index >= len(self.anchors):
            if self.cycle_checkbox.isChecked():
                self.curr_index = 0
            else:
                return None
        a = self.anchors[self.curr_index]
        self.curr_index += 1
        return a

    def _is_forbidden_parent(self, tag):
        forbidden = {
            'footer', 'nav', 'aside', 'header', 'form', 'button', 'input',
            'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'th', 'td', 'script',
            'style', 'code', 'meta', 'head', 'link', 'title'
        }
        while tag:
            if tag.name in forbidden:
                return True
            id_class = (tag.get('id', '') + ' ' + ' '.join(
                tag.get('class', []) if tag.has_attr('class') else '')).lower()
            if any(x in id_class for x in ['login', 'form', 'error', 'sidebar', 'menu', 'captcha']):
                return True
            tag = tag.parent
        return False

    def _find_main_container(self, soup):
        for name, attrs in [
            ('div', {'class': lambda v: v and any(x in v for x in ['entry-content', 'content-area', 'post-content', 'article-content', 'site-content'])}),
            ('main', {}),
            ('article', {}),
        ]:
            el = soup.find(name, attrs=attrs)
            if el:
                return el
        return soup.find('body') or soup

    def _is_in_a_tag(self, node):
        return node.find_parent('a') is not None

    def _find_main_article(self, soup):
        # Сначала ищем <main> с нормальным id/class
        main = soup.find('main', id=lambda x: x is None or 'content' in x)
        if not main:
            # Пробуем найти основную колонку/контент
            main = soup.find('div', class_=lambda x: x and 'content-column' in x)
        if not main:
            main = soup.find('article', class_=lambda x: x and ('post' in x or 'listing-item' in x))
        if not main:
            # Если не нашли — fallback: entry-content без off-canvas/side/footer в родителях
            all_content = soup.find_all('div', class_=lambda x: x and 'entry-content' in x)
            for cont in all_content:
                # Проверяем родителей
                p = cont
                bad = False
                while p:
                    p_class = ' '.join(p.get('class', []) if p.has_attr('class') else [])
                    if any(y in p_class for y in ('sidebar', 'off-canvas', 'footer', 'header')):
                        bad = True
                        break
                    p = p.parent if hasattr(p, 'parent') else None
                if not bad:
                    main = cont
                    break
        if not main:
            # Абсолютный fallback — <body>
            main = soup.body
        return main

    def _find_content_blocks(self, soup):
        # Ищет только внутри главного контейнера с контентом
        main = (
                soup.find('div', class_=lambda x: x and 'entry-content' in x)
                or soup.find('div', class_=lambda x: x and 'content-area' in x)
                or soup.find('main')
                or soup.find('article')
                or soup.body
        )
        if not main:
            return []
        candidates = []
        min_len = self.min_len_spin.value()
        for tag in main.find_all(['p', 'div', 'section', 'article'], recursive=True):
            txt = tag.get_text(strip=True)
            if len(txt) < min_len:
                continue
            # Не трогать явные футеры, меню, и т.д.
            if tag.name in ('footer', 'nav', 'header', 'aside'):
                continue
            # Не брать, если тег или класс/id содержит login/menu/footer/sidebar и т.д.
            id_class = (tag.get('id', '') + ' ' + ' '.join(
                tag.get('class', []) if tag.has_attr('class') else '')).lower()
            if any(x in id_class for x in ['login', 'form', 'error', 'sidebar', 'menu', 'captcha', 'footer', 'nav']):
                continue
            candidates.append(tag)
        return candidates

    def _insert_after_h1(self, soup, anchor_html):
        # Вставляет HTML после первого <h1> внутри главного контейнера (entry-content, main, ...)
        main = (
                soup.find('div', class_=lambda x: x and 'entry-content' in x)
                or soup.find('div', class_=lambda x: x and 'content-area' in x)
                or soup.find('main')
                or soup.find('article')
                or soup.body
        )
        if not main:
            return False, None
        h1 = main.find('h1')
        # Проверяем, что этот h1 не в sidebar/footer/nav и т.д.
        if h1 and not self._is_forbidden_parent(h1):
            new_block = BeautifulSoup(anchor_html, 'html.parser')
            h1.insert_after(new_block)
            context = (h1.get_text(strip=True)[:40] or "") + " ... [AFTER <h1>]"
            return True, context
        return False, None

    def _insert_anchor_into_text(self, node, anchor_html):
        # Вставляем ссылку между словами
        text = str(node)
        words = re.split(r'(\s+)', text)
        if len(words) < 3:
            return False, "", ""
        idx = random.randint(1, len(words) - 2)
        words.insert(idx, f' {anchor_html} ')
        new_html = ''.join(words)
        frag = BeautifulSoup(new_html, 'html.parser')
        node.replace_with(frag)
        context = ''.join(words[max(0, idx - 4):idx + 5])
        return True, context, node

    def generate_links(self):
        if not self.analyzed_pages:
            QMessageBox.warning(self, "Ошибка", "Сначала проанализируйте страницы!")
            return
        if not self.anchors:
            QMessageBox.warning(self, "Ошибка", "Добавьте <a> ссылки или HTML!")
            return

        self.curr_index = 0
        base_dir = self.base_dir
        total_inserted = 0
        processed_pages = 0
        min_text_len = self.min_len_spin.value()
        fallback_on = self.allow_fallback_checkbox.isChecked()
        html_mode = self.allow_arbitrary_html_checkbox.isChecked()

        # --- новые значения из спинбоксов ---
        min_links = self.min_links_spin.value()
        max_links = self.max_links_spin.value()

        for rel_path in self.analyzed_pages:
            file_path = os.path.join(base_dir, rel_path)
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    html_text = f.read()
            except Exception as e:
                self.log_view.append(f"<span style='color:red'>Ошибка чтения {file_path}: {e}</span>")
                continue

            soup = BeautifulSoup(html_text, 'html.parser')
            success = False
            inserted_count = 0  # сколько реально вставлено ссылок
            inserted_info = ''

            # --- сколько ссылок вставлять на эту страницу ---
            num_links = random.randint(min_links, max_links)

            if html_mode:
                # --- Режим ПРОИЗВОЛЬНОГО HTML: вставка после блока ---
                candidates = []
                for tag in soup.find_all(['p', 'div', 'section', 'article']):
                    txt = tag.get_text(strip=True)
                    if len(txt) < min_text_len:
                        continue
                    if self._is_forbidden_parent(tag):
                        continue
                    candidates.append(tag)
                if candidates:
                    for _ in range(num_links):
                        anchor_html = self.get_next_anchor()
                        if not anchor_html:
                            break
                        tag = random.choice(candidates)
                        new_block = BeautifulSoup(anchor_html, 'html.parser')
                        tag.insert_after(new_block)
                        inserted_count += 1
                    if inserted_count > 0:
                        success = True
                        short_txt = tag.get_text(strip=True)
                        context = short_txt[:70] + ("..." if len(short_txt) > 70 else "")
                        inserted_info = f"<b>ПОСЛЕ</b> <b>&lt;{tag.name}&gt;</b>: <span style='color:#c1dfff;'>{context}</span>"
                else:
                    # fallback
                    if fallback_on and self.anchors:
                        for _ in range(num_links):
                            anchor_html = self.get_next_anchor()
                            if not anchor_html:
                                break
                            container = self._find_main_container(soup)
                            if container:
                                new_block = BeautifulSoup(anchor_html, 'html.parser')
                                container.append(new_block)
                                inserted_count += 1
                        if inserted_count > 0:
                            success = True
                            inserted_info = "<b>ФОЛЛБЕК</b> — аппенд в конец основного контейнера"

            else:
                min_text_len = self.min_len_spin.value()
                main = self._find_main_article(soup)
                first_h1 = main.find('h1') if main else None
                p_candidates = []
                if main and first_h1:
                    # Перебираем только потомков main после первого h1!
                    started = False
                    for el in main.descendants:
                        if el == first_h1:
                            started = True
                            continue
                        if not started:
                            continue
                        if getattr(el, "name", None) == "p":
                            txt = el.get_text(strip=True)
                            if len(txt) < min_text_len:
                                continue
                            id_class = (el.get('id', '') + ' ' + ' '.join(
                                el.get('class', []) if el.has_attr('class') else '')).lower()
                            if any(x in id_class for x in
                                   ['login', 'form', 'error', 'sidebar', 'menu', 'captcha', 'footer', 'nav']):
                                continue
                            for tnode in el.find_all(string=lambda s: not isinstance(s, Comment)):
                                if len(tnode.strip()) < min_text_len:
                                    continue
                                if self._is_in_a_tag(tnode):
                                    continue
                                p_candidates.append((el, tnode))

                # Считаем кандидатов один раз перед вставкой
                p_candidates = []
                main = self._find_main_article(soup)
                first_h1 = main.find('h1') if main else None
                if main and first_h1:
                    started = False
                    for el in main.descendants:
                        if el == first_h1:
                            started = True
                            continue
                        if not started:
                            continue
                        if getattr(el, "name", None) == "p":
                            txt = el.get_text(strip=True)
                            if len(txt) < min_text_len:
                                continue
                            id_class = (el.get('id', '') + ' ' + ' '.join(
                                el.get('class', []) if el.has_attr('class') else '')).lower()
                            if any(x in id_class for x in
                                   ['login', 'form', 'error', 'sidebar', 'menu', 'captcha', 'footer', 'nav']):
                                continue
                            for tnode in el.find_all(string=lambda s: not isinstance(s, Comment)):
                                if len(tnode.strip()) < min_text_len:
                                    continue
                                if self._is_in_a_tag(tnode):
                                    continue
                                p_candidates.append((el, tnode))

                    # Перемешиваем кандидатов (для рандома)
                    random.shuffle(p_candidates)
                    num_actual = min(num_links, len(p_candidates))
                    for i in range(num_actual):
                        anchor_html = self.get_next_anchor()
                        if not anchor_html:
                            break
                        tag, node = p_candidates[i]
                        ok, context, oldstr = self._insert_anchor_into_text(node, anchor_html)
                        if ok:
                            inserted_count += 1
                            success = True
                            context_disp = context.replace(anchor_html,
                                                           f"<span style='color:#fca311;background:#22303c;'>{anchor_html}</span>")
                            inserted_info = f"<b>ВНУТРЬ</b> <b>&lt;p&gt;</b>: ...{context_disp}..."


                else:
                    # fallback
                    if fallback_on and self.anchors:
                        for _ in range(num_links):
                            anchor_html = self.get_next_anchor()
                            if not anchor_html:
                                break
                            container = self._find_main_container(soup)
                            if container:
                                new_block = BeautifulSoup(anchor_html, 'html.parser')
                                container.append(new_block)
                                inserted_count += 1
                        if inserted_count > 0:
                            success = True
                            inserted_info = "<b>ФОЛЛБЕК</b> — аппенд в конец основного контейнера"

            if success and inserted_count > 0:
                try:
                    with open(file_path, 'w', encoding='utf-8', errors='replace') as f:
                        f.write(str(soup))
                    self.log_view.append(
                        f"<span style='color:green;'>Вставлено {inserted_count} ссылок на страницу</span><br><span style='color:blue'>{file_path}</span>")
                    total_inserted += inserted_count
                except Exception as e:
                    self.log_view.append(f"<span style='color:red;'>Ошибка записи {file_path}: {e}</span>")
            else:
                self.log_view.append(
                    f"<span style='color:orange;'>НЕ ВСТАВЛЕНО — нет подходящих блоков</span><br><span style='color:blue'>{file_path}</span>")

            processed_pages += 1

        summ = f"Готово! Обработано {processed_pages} страниц, всего вставлено {total_inserted} ссылок (2-й этап)."
        self.log_view.append(f"<b>{summ}</b>")
        QMessageBox.information(self, "Завершено", summ)


from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import chardet
from urllib.parse import urlparse

from lxml import html

from PyQt6.QtCore import Qt, QObject, pyqtSignal, pyqtSlot, QUrl
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QMessageBox, QDialog,
    QLineEdit, QTextEdit, QDialogButtonBox, QListWidget, QListWidgetItem
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

from seo_cluster_linker import AnchorMorpher

try:
    from pills import KEYWORDS
except ImportError:
    KEYWORDS = {}

logger = logging.getLogger("seo_visual_editor")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | seo_visual_editor | %(message)s",
        datefmt="%H:%M:%S"
    ))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


@dataclass
class VisualPage:
    id: str
    url: str
    file_path: str
    title: str
    domain: str


@dataclass
class PillarNode:
    id: str
    url: str
    label: str
    anchors: List[str]


class VisualEditorBridge(QObject):
    linkCreated = pyqtSignal(str, str)

    @pyqtSlot(str, str)
    def createLink(self, source_id: str, target_id: str):
        if not source_id or not target_id or source_id == target_id:
            return
        self.linkCreated.emit(source_id, target_id)


class AddPillarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить Pillar-страницу")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        url_label = QLabel("URL Pillar-страницы:")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/pillar-page/")
        layout.addWidget(url_label)
        layout.addWidget(self.url_edit)

        kw_label = QLabel("Список анкоров (по одному на строку):")
        self.kw_edit = QTextEdit()
        self.kw_edit.setPlaceholderText(
            "buy modafinil online\n"
            "modafinil dosage guide\n"
            "best place to buy modafinil"
        )
        layout.addWidget(kw_label)
        layout.addWidget(self.kw_edit)

        info = QLabel(
            "Эта страница может не существовать в HTML.\n"
            "На графе она появится как отдельный Pillar-узел."
        )
        info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> Tuple[str, List[str]]:
        url = self.url_edit.text().strip()
        raw = self.kw_edit.toPlainText()
        anchors = [line.strip() for line in raw.splitlines() if line.strip()]
        return url, anchors


class AnchorSelectionDialog(QDialog):
    def __init__(self, suggestions: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор анкора")
        self.setMinimumWidth(480)

        self._selected_anchor: Optional[str] = None

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Выберите или отредактируйте анкор:"))

        self.list_widget = QListWidget()
        for s in suggestions:
            item = QListWidgetItem(s)
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Свободный ввод анкора")
        layout.addWidget(self.edit)

        hint = QLabel(
            "• Двойной клик по варианту — сразу выбрать.\n"
            "• Или выберите строку, при необходимости отредактируйте ниже и нажмите OK."
        )
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        self._selected_anchor = item.text().strip()
        if self._selected_anchor:
            self.accept()

    def _on_accept(self):
        text = self.edit.text().strip()
        if text:
            self._selected_anchor = text
        else:
            current = self.list_widget.currentItem()
            self._selected_anchor = current.text().strip() if current else ""
        if not self._selected_anchor:
            QMessageBox.warning(self, "Ошибка", "Анкор не может быть пустым")
            return
        self.accept()

    @property
    def selected_anchor(self) -> Optional[str]:
        return self._selected_anchor


class VisualEditorWidget(QWidget):
    applyPlannedLinks = pyqtSignal(list)
    def __init__(self, base_directory: str, parent=None):
        super().__init__(parent)
        self.base_dir = base_directory

        self.pages_by_id: Dict[str, VisualPage] = {}
        self.page_id_by_url: Dict[str, str] = {}
        self.pillars: Dict[str, PillarNode] = {}
        self.existing_edges: List[Dict[str, str]] = []
        self.planned_edges: List[Dict[str, str]] = []

        self._next_page_id = 1
        self._next_pillar_id = 1

        self._web_ready = False

        self._init_ui()
        self._init_webview()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(8, 4, 8, 4)

        self.add_pillar_btn = QPushButton("➕ Добавить Pillar-страницу")
        self.add_pillar_btn.clicked.connect(self._on_add_pillar)
        top_bar.addWidget(self.add_pillar_btn)

        self.reload_btn = QPushButton("🔄 Пересканировать")
        self.reload_btn.clicked.connect(self.reload_graph)
        top_bar.addWidget(self.reload_btn)

        # Кнопка: вставить только связи из Visual Linker
        self.apply_btn = QPushButton("💾 Вставить связи Visual Linker")
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        top_bar.addWidget(self.apply_btn)

        # Открыть граф в отдельном окне (на весь экран)
        self.open_window_btn = QPushButton("🔍 Отдельное окно")
        self.open_window_btn.clicked.connect(self._on_open_window)
        top_bar.addWidget(self.open_window_btn)



        top_bar.addStretch()

        self.stats_label = QLabel("Страниц: 0 • Ссылок: 0")
        self.stats_label.setStyleSheet("color: #aaa; font-size: 11px;")
        top_bar.addWidget(self.stats_label)

        layout.addLayout(top_bar)

        self.view = QWebEngineView()
        layout.addWidget(self.view)

    def _on_open_window(self):
        """
        Открывает текущий граф Visual Linker в отдельном окне (QDialog).
        """
        if not self.pages_by_id and not self.pillars:
            QMessageBox.information(self, "Visual Linker", "Нет данных для отображения графа")
            return

        nodes = self._build_nodes_payload()

        dlg = VisualGraphDialog(
            nodes=nodes,
            existing_edges=list(self.existing_edges),
            planned_edges=list(self.planned_edges),
            parent=self.window()
        )
        # НЕМОДАЛЬНОЕ окно, чтобы можно было работать с остальным интерфейсом
        dlg.setModal(False)
        dlg.show()

    def _init_webview(self):
        self.bridge = VisualEditorBridge()
        self.bridge.linkCreated.connect(self._on_link_created)

        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, "templates", "visual_linker_template.html")

        if not os.path.exists(template_path):
            QMessageBox.critical(
                self, "Ошибка",
                f"HTML-шаблон Visual Linker не найден:\n{template_path}"
            )
            return

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html_source = f.read()
        except Exception as e:
            QMessageBox.critical(
                self, "Ошибка",
                f"Не удалось прочитать HTML-шаблон:\n{e}"
            )
            return

        base_url = QUrl.fromLocalFile(script_dir + os.sep)
        self.view.loadFinished.connect(self._on_load_finished)
        self.view.setHtml(html_source, base_url)

    def _on_load_finished(self, ok: bool):
        self._web_ready = ok
        if ok:
            self.reload_graph()
        else:
            logger.error("Не удалось загрузить HTML для визуального редактора")

    def _run_js(self, script: str):
        if not self._web_ready:
            return
        self.view.page().runJavaScript(script)

    def reload_graph(self):
        if not os.path.isdir(self.base_dir):
            QMessageBox.warning(self, "Ошибка", f"Директория не найдена:\n{self.base_dir}")
            return

        logger.info(f"VisualEditor: пересканирование директории {self.base_dir}")

        self.pages_by_id.clear()
        self.page_id_by_url.clear()
        self.existing_edges.clear()
        # pillars и planned_edges не трогаем — это "план"

        self._next_page_id = 1

        self._scan_pages()
        self._scan_existing_links()
        self._update_stats_label()

        payload = {
            "nodes": self._build_nodes_payload(),
            "existingEdges": self.existing_edges,
            "plannedEdges": self.planned_edges,
        }
        js = f"window.initVisualGraph({json.dumps(payload)});"
        self._run_js(js)

    def _scan_pages(self):
        base = self.base_dir

        for domain in os.listdir(base):
            domain_path = os.path.join(base, domain)
            if not os.path.isdir(domain_path):
                continue

            for root, _, files in os.walk(domain_path):
                for fname in files:
                    if not fname.endswith(".html"):
                        continue

                    full_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(full_path, domain_path).replace("\\", "/")

                    url_path = rel_path.replace(".html", "")
                    url = f"https://{domain}/{url_path}/"

                    page_id = f"p{self._next_page_id}"
                    self._next_page_id += 1

                    title = self._extract_title(full_path)
                    vp = VisualPage(
                        id=page_id,
                        url=url,
                        file_path=full_path,
                        title=title or url,
                        domain=domain,
                    )
                    self.pages_by_id[page_id] = vp
                    self.page_id_by_url[self._normalize_url(url)] = page_id

        logger.info(f"VisualEditor: найдено страниц: {len(self.pages_by_id)}")

    def _extract_title(self, file_path: str) -> str:
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
            enc = chardet.detect(raw).get("encoding") or "utf-8"
            text = raw.decode(enc, errors="replace")
            doc = html.fromstring(text)
            titles = doc.xpath("//title/text()")
            return titles[0].strip() if titles else ""
        except Exception as e:
            logger.warning(f"Не удалось прочитать title из {file_path}: {e}")
            return ""

    def _scan_existing_links(self):
        for page in self.pages_by_id.values():
            try:
                with open(page.file_path, "rb") as f:
                    raw = f.read()
                enc = chardet.detect(raw).get("encoding") or "utf-8"
                text = raw.decode(enc, errors="replace")
                doc = html.fromstring(text)
            except Exception as e:
                logger.warning(f"Не удалось распарсить {page.file_path}: {e}")
                continue

            anchors = doc.xpath("//a[@href]")
            for a in anchors:
                href = a.get("href") or ""
                target_url = self._resolve_href(page, href)
                if not target_url:
                    continue

                norm = self._normalize_url(target_url)
                target_id = self.page_id_by_url.get(norm)
                if not target_id or target_id == page.id:
                    continue

                self.existing_edges.append({
                    "source": page.id,
                    "target": target_id,
                    "type": "existing",
                })

        logger.info(f"VisualEditor: найдено существующих ссылок: {len(self.existing_edges)}")

    @staticmethod
    def _normalize_url(url: str) -> str:
        try:
            p = urlparse(url)
            scheme = p.scheme or "https"
            netloc = (p.netloc or "").lower()
            path = p.path or "/"

            if path.endswith(".html"):
                path = path[:-5]
            if path.endswith("/"):
                path = path[:-1]
            if not path.startswith("/"):
                path = "/" + path

            return f"{scheme}://{netloc}{path}"
        except Exception:
            return url

    def _resolve_href(self, page: VisualPage, href: str) -> Optional[str]:
        href = href.strip()
        if not href:
            return None
        if href.startswith("#"):
            return None
        if href.startswith("mailto:") or href.startswith("tel:") or href.startswith("javascript:"):
            return None

        if href.startswith("http://") or href.startswith("https://"):
            return href

        p = urlparse(page.url)
        base = f"{p.scheme}://{p.netloc}"

        if href.startswith("/"):
            path = href
        else:
            path = "/" + href

        return base + path

    def _build_nodes_payload(self) -> List[Dict]:
        nodes: List[Dict] = []

        for page in self.pages_by_id.values():
            nodes.append({
                "id": page.id,
                "url": page.url,
                "label": page.title or page.url,
                "group": "page",
                "isPillar": False,
            })

        for pillar in self.pillars.values():
            nodes.append({
                "id": pillar.id,
                "url": pillar.url,
                "label": pillar.label,
                "group": "pillar",
                "isPillar": True,
            })

        return nodes

    def _update_stats_label(self):
        pages_count = len(self.pages_by_id)
        existing_count = len(self.existing_edges)
        planned_count = len(self.planned_edges)
        self.stats_label.setText(
            f"Страниц: {pages_count} • Существующих ссылок: {existing_count} • Новых (план): {planned_count}"
        )

    def _on_add_pillar(self):
        dlg = AddPillarDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        url, anchors = dlg.get_data()
        if not url:
            QMessageBox.warning(self, "Ошибка", "URL не может быть пустым")
            return
        if not anchors:
            QMessageBox.warning(self, "Ошибка", "Нужно задать хотя бы один анкор")
            return

        node_id = f"pillar_{self._next_pillar_id}"
        self._next_pillar_id += 1

        label = url
        pillar = PillarNode(id=node_id, url=url, label=label, anchors=anchors)
        self.pillars[node_id] = pillar

        node_payload = {
            "id": pillar.id,
            "url": pillar.url,
            "label": pillar.label,
            "group": "pillar",
            "isPillar": True,
        }

        js = f"window.addPillarNode({json.dumps(node_payload)});"
        self._run_js(js)
        self._update_stats_label()

    def _on_link_created(self, source_id: str, target_id: str):
        logger.info(f"VisualEditor: запрос на создание ссылки {source_id} → {target_id}")

        anchor_suggestions: List[str] = []

        if target_id in self.pillars:
            pillar = self.pillars[target_id]
            anchor_suggestions = pillar.anchors
        else:
            target_page = self.pages_by_id.get(target_id)
            if not target_page:
                QMessageBox.warning(self, "Ошибка", "Не удалось найти целевую страницу в карте")
                return

            topic = self._detect_topic_by_title(target_page.title)
            synonyms = self._get_synonyms_for_topic(topic)
            morpher = AnchorMorpher(topic, synonyms)

            categories = ["commercial", "longtail", "branded", "informational", "contextual", "cta"]
            for cat in categories:
                anchor_suggestions.append(morpher.get_anchor(category=cat))

            anchor_suggestions = list(dict.fromkeys(anchor_suggestions))

        if not anchor_suggestions:
            anchor_suggestions = ["learn more", "read more", "click here"]

        dlg = AnchorSelectionDialog(anchor_suggestions, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        anchor = dlg.selected_anchor
        if not anchor:
            return

        edge = {
            "source": source_id,
            "target": target_id,
            "type": "planned",
            "anchor": anchor,
        }
        self.planned_edges.append(edge)

        js = f"window.addPlannedLink({json.dumps(edge)});"
        self._run_js(js)
        self._update_stats_label()
    def _export_planned_links(self) -> list:
        """
        Отдаёт список планируемых ссылок в виде:
        [
            {
                "source_path": "C:/.../domain/page.html",
                "source_url": "https://domain/page/",
                "target_url": "https://target-domain/target-page/",
                "anchor": "anchor text"
            },
            ...
        ]
        """
        result = []

        # Быстрая карта id -> url / path
        for edge in self.planned_edges:
            source_id = edge.get("source")
            target_id = edge.get("target")
            anchor = edge.get("anchor", "").strip()
            if not source_id or not target_id or not anchor:
                continue

            # Донора мы вставляем только из реальных страниц (а не из pillar-узлов)
            page = self.pages_by_id.get(source_id)
            if not page:
                continue

            # Цель может быть реальной страницей или Pillar-узлом
            if target_id in self.pages_by_id:
                target_url = self.pages_by_id[target_id].url
            elif target_id in self.pillars:
                target_url = self.pillars[target_id].url
            else:
                continue

            result.append({
                "source_path": page.file_path,
                "source_url": page.url,
                "target_url": target_url,
                "anchor": anchor,
            })

        return result

    def export_for_graph_dialog(self) -> tuple[list, list]:
        """
        Готовит данные в формате, который ожидает GraphDialog / graph_template.html.
        nodes: [{"id": "...", "label": "...", "url": "...", "group": "page/pillar", "size": int, "color": "#RRGGBB"}, ...]
        edges: [{"from": id, "to": id, "arrows": "to", "label": anchor, "color": {"color": "#xxxxxx"}}, ...]
        """
        nodes = []
        edges = []

        # Узлы-страницы
        for page in self.pages_by_id.values():
            node_id = page.url.rstrip('/')
            nodes.append({
                "id": node_id,
                "label": page.domain,
                "url": page.url,
                "group": "page",
                "size": 15,
                "color": "#87CEFA"
            })

        # Узлы-Pillar
        for pillar in self.pillars.values():
            node_id = pillar.url.rstrip('/')
            nodes.append({
                "id": node_id,
                "label": pillar.label,
                "url": pillar.url,
                "group": "pillar",
                "size": 22,
                "color": "#f97316"
            })

        # Карта id (внутренний) -> id (графовый)
        id_to_graph = {}
        for page in self.pages_by_id.values():
            id_to_graph[page.id] = page.url.rstrip('/')

        for pillar in self.pillars.values():
            id_to_graph[pillar.id] = pillar.url.rstrip('/')

        # Существующие ссылки (серые)
        for e in self.existing_edges:
            src = id_to_graph.get(e.get("source"))
            tgt = id_to_graph.get(e.get("target"))
            if not src or not tgt:
                continue

            edges.append({
                "from": src,
                "to": tgt,
                "arrows": "to",
                "label": "",
                "color": {"color": "#888888"}
            })

        # Новые планируемые (зелёные, с подписью анкора)
        for e in self.planned_edges:
            src = id_to_graph.get(e.get("source"))
            tgt = id_to_graph.get(e.get("target"))
            if not src or not tgt:
                continue

            edges.append({
                "from": src,
                "to": tgt,
                "arrows": "to",
                "label": e.get("anchor", ""),
                "color": {"color": "#22c55e"}
            })

        return nodes, edges

    def _on_apply_clicked(self):
        """Отправить наружу планируемые связи для вставки в HTML."""
        links = self._export_planned_links()
        if not links:
            QMessageBox.information(
                self,
                "Visual Linker",
                "Нет планируемых ссылок для вставки"
            )
            return

        # Отдаём список словарей в SEOClusterDialog
        self.applyPlannedLinks.emit(links)

    def _detect_topic_by_title(self, title: str) -> str:
        if not title:
            return "drug"

        title_lower = title.lower()
        found_topic = None

        for synonym, main_keyword in KEYWORDS.items():
            if not synonym:
                continue
            if synonym.lower() in title_lower:
                found_topic = main_keyword
                break

        if found_topic:
            return found_topic

        parts = [p for p in title.split() if p.isalpha()]
        return parts[0].lower() if parts else "drug"

    def _get_synonyms_for_topic(self, topic: str) -> List[str]:
        if not topic:
            return []
        synonyms = []
        for synonym, main in KEYWORDS.items():
            if main == topic:
                synonyms.append(synonym)
        if topic not in synonyms:
            synonyms.append(topic)
        return synonyms


class VisualGraphDialog(QDialog):
    """
    Отдельное окно с графом Visual Linker.
    Только просмотр (создание связей остаётся во вкладке).
    """
    def __init__(self, nodes: List[Dict], existing_edges: List[Dict], planned_edges: List[Dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Visual Linker — отдельное окно")
        self.resize(1400, 900)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.view = QWebEngineView()
        layout.addWidget(self.view)

        # Простейший WebChannel (мост не используется, но JS его ждёт)
        self.channel = QWebChannel(self.view.page())
        self.bridge = QObject()
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, "templates", "visual_linker_template.html")

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html_source = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать HTML-шаблон Visual Linker:\n{e}")
            return

        base_url = QUrl.fromLocalFile(script_dir + os.sep)

        # После загрузки HTML передаём данные графа
        def on_loaded(ok: bool):
            if not ok:
                return
            payload = {
                "nodes": nodes,
                "existingEdges": existing_edges,
                "plannedEdges": planned_edges,
            }
            js = f"window.initVisualGraph({json.dumps(payload)});"
            self.view.page().runJavaScript(js)

        self.view.loadFinished.connect(on_loaded)
        self.view.setHtml(html_source, base_url)

import os
import json
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QMessageBox
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl

class GraphDialog(QDialog):
    def __init__(self, nodes, edges, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Граф обратных ссылок")
        self.setMinimumSize(1200, 800)

        layout = QVBoxLayout()
        self.browser = QWebEngineView()

        # Получаем абсолютный путь до файла шаблона, относительно текущего файла
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, 'templates', 'graph_template.html')

        # Проверяем существование файла
        if not os.path.exists(template_path):
            QMessageBox.critical(self, "Ошибка", f"Файл шаблона не найден:\n{template_path}")
            self.close()
            return

        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                html = f.read()

            html = html.replace('NODES_DATA', json.dumps(nodes))
            html = html.replace('EDGES_DATA', json.dumps(edges))

            self.browser.setHtml(html, baseUrl=QUrl.fromLocalFile(script_dir + '/'))
            layout.addWidget(self.browser)
            self.setLayout(layout)

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка загрузки шаблона:\n{e}")
            self.close()

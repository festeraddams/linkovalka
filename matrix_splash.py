import random
import math

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QLinearGradient, QRadialGradient, QPen, QBrush
from PyQt6.QtWidgets import QWidget, QApplication, QGraphicsOpacityEffect


class MatrixRainColumn:
    """Класс для одной колонки дождя"""

    def __init__(self, x, rows, speed=1.0):
        self.x = x
        self.rows = rows
        self.speed = speed
        self.y = random.randint(-rows, 0)
        self.chars = []
        self.trail_length = random.randint(8, 15)
        self.regenerate_chars()

    def regenerate_chars(self):
        chars_pool = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
        self.chars = [random.choice(chars_pool) for _ in range(self.trail_length)]

    def update(self):
        self.y += self.speed
        if self.y > self.rows + self.trail_length:
            self.y = random.randint(-self.trail_length * 2, -self.trail_length)
            self.speed = random.uniform(0.3, 1.5)
            self.trail_length = random.randint(8, 15)
            self.regenerate_chars()

        # Иногда меняем символы
        if random.random() < 0.1:
            idx = random.randint(0, len(self.chars) - 1)
            chars_pool = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
            self.chars[idx] = random.choice(chars_pool)


class MatrixSplashScreen(QWidget):
    def __init__(self, msec=3000):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(1000, 600)

        # Параметры дождя
        self.col_width = 20
        self.row_height = 25
        self.cols = self.width() // self.col_width
        self.rows = self.height() // self.row_height

        # Создаем колонки дождя
        self.rain_columns = [
            MatrixRainColumn(i, self.rows, random.uniform(0.3, 1.5))
            for i in range(self.cols)
        ]

        # Шрифты
        self.font_matrix = QFont("Consolas", 16, QFont.Weight.Bold)
        self.font_title = QFont("Consolas", 72, QFont.Weight.ExtraBold)
        self.font_subtitle = QFont("Consolas", 20, QFont.Weight.Bold)

        # Анимация появления текста
        self._title_opacity = 0.0
        self._subtitle_opacity = 0.0
        self._pulse = 0.0

        # Таймеры
        self.rain_timer = QTimer(self)
        self.rain_timer.timeout.connect(self.updateRain)
        self.rain_timer.start(40)  # 25 FPS

        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self.updatePulse)
        self.pulse_timer.start(30)

        # Анимация появления заголовка
        QTimer.singleShot(200, self.animateTitleIn)
        QTimer.singleShot(800, self.animateSubtitleIn)

        # Завершение
        QTimer.singleShot(msec, self.finishSplash)

        # Центрируем окно
        desktop = QApplication.primaryScreen().availableGeometry()
        self.move(desktop.center() - self.rect().center())

        self._on_finish = None

    def set_on_finish(self, func):
        self._on_finish = func

    def finishSplash(self):
        self.close()
        if self._on_finish:
            self._on_finish()

    def updateRain(self):
        for col in self.rain_columns:
            col.update()
        self.update()

    def updatePulse(self):
        self._pulse = (self._pulse + 0.05) % (2 * math.pi)
        self.update()

    def animateTitleIn(self):
        self.anim_title = QPropertyAnimation(self, b"title_opacity")
        self.anim_title.setDuration(800)
        self.anim_title.setStartValue(0.0)
        self.anim_title.setEndValue(1.0)
        self.anim_title.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim_title.start()

    def animateSubtitleIn(self):
        self.anim_subtitle = QPropertyAnimation(self, b"subtitle_opacity")
        self.anim_subtitle.setDuration(600)
        self.anim_subtitle.setStartValue(0.0)
        self.anim_subtitle.setEndValue(1.0)
        self.anim_subtitle.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim_subtitle.start()

    @pyqtProperty(float)
    def title_opacity(self):
        return self._title_opacity

    @title_opacity.setter
    def title_opacity(self, value):
        self._title_opacity = value
        self.update()

    @pyqtProperty(float)
    def subtitle_opacity(self):
        return self._subtitle_opacity

    @subtitle_opacity.setter
    def subtitle_opacity(self, value):
        self._subtitle_opacity = value
        self.update()

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        qp.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Темный полупрозрачный фон
        qp.fillRect(self.rect(), QColor(0, 0, 0, 220))

        # Рисуем Matrix дождь
        qp.setFont(self.font_matrix)
        for col in self.rain_columns:
            x_pos = col.x * self.col_width + 10

            for i in range(col.trail_length):
                y_pos_idx = int(col.y - i)

                if 0 <= y_pos_idx < self.rows:
                    y_pos = y_pos_idx * self.row_height + 20

                    # Яркость уменьшается от головы к хвосту
                    if i == 0:
                        # Голова - яркий белый с зеленоватым оттенком
                        color = QColor(220, 255, 220)
                        alpha = 255
                    elif i < 3:
                        # Ближайшие символы - яркий зеленый
                        color = QColor(0, 255, 100)
                        alpha = int(255 * (1 - i / 5))
                    else:
                        # Хвост - темный зеленый
                        brightness = int(180 * (1 - i / col.trail_length))
                        color = QColor(0, brightness, int(brightness * 0.5))
                        alpha = int(200 * (1 - i / col.trail_length))

                    color.setAlpha(alpha)
                    qp.setPen(color)

                    if i < len(col.chars):
                        qp.drawText(x_pos, y_pos, col.chars[i])

        # Рисуем главный заголовок с эффектами
        if self._title_opacity > 0:
            main_text = "DARK SEO"
            qp.setFont(self.font_title)
            fm_main = qp.fontMetrics()
            main_width = fm_main.horizontalAdvance(main_text)
            main_height = fm_main.height()
            x_main = (self.width() - main_width) // 2
            y_main = self.height() // 2 - 20

            # Эффект свечения (несколько слоев)
            glow_intensity = 0.3 + 0.2 * math.sin(self._pulse)
            for offset in [8, 6, 4, 2]:
                glow_color = QColor(0, 255, 70)
                glow_color.setAlpha(int(30 * glow_intensity * self._title_opacity / (offset / 2)))
                qp.setPen(QPen(glow_color, offset))
                qp.drawText(x_main, y_main, main_text)

            # Темная обводка для контраста
            for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2), (-2, 0), (2, 0), (0, -2), (0, 2)]:
                shadow = QColor(0, 0, 0)
                shadow.setAlpha(int(200 * self._title_opacity))
                qp.setPen(shadow)
                qp.drawText(x_main + dx, y_main + dy, main_text)

            # Основной текст с градиентом
            gradient = QLinearGradient(x_main, y_main - main_height // 2, x_main, y_main + main_height // 2)

            # Пульсирующий эффект
            pulse_brightness = int(220 + 35 * math.sin(self._pulse))

            gradient.setColorAt(0, QColor(pulse_brightness, 255, pulse_brightness))
            gradient.setColorAt(0.5, QColor(0, 255, 100))
            gradient.setColorAt(1, QColor(0, 200, 50))

            pen = QPen(gradient, 1)
            color_main = QColor(0, 255, 100)
            color_main.setAlpha(int(255 * self._title_opacity))
            pen.setColor(color_main)
            qp.setPen(pen)
            qp.drawText(x_main, y_main, main_text)

        # Рисуем подзаголовок
        if self._subtitle_opacity > 0:
            sub_text = "BY UNCLE FESTER"
            qp.setFont(self.font_subtitle)
            fm_sub = qp.fontMetrics()
            sub_width = fm_sub.horizontalAdvance(sub_text)
            sub_height = fm_sub.height()
            x_sub = (self.width() - sub_width) // 2
            y_sub = self.height() // 2 + 60

            # Обводка
            for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
                shadow = QColor(0, 0, 0)
                shadow.setAlpha(int(180 * self._subtitle_opacity))
                qp.setPen(shadow)
                qp.drawText(x_sub + dx, y_sub + dy, sub_text)

            # Основной текст с легким свечением
            glow = QColor(255, 255, 255)
            glow.setAlpha(int(100 * self._subtitle_opacity))
            qp.setPen(QPen(glow, 3))
            qp.drawText(x_sub, y_sub, sub_text)

            color_sub = QColor(230, 230, 230)
            color_sub.setAlpha(int(255 * self._subtitle_opacity))
            qp.setPen(color_sub)
            qp.drawText(x_sub, y_sub, sub_text)

        # Рамка по краям экрана
        border_color = QColor(0, 200, 70)
        border_color.setAlpha(100)
        qp.setPen(QPen(border_color, 2))
        qp.drawRect(5, 5, self.width() - 10, self.height() - 10)

###############################################################################
class SpinnerOverlay(QWidget):
    """Оверлей загрузки с Matrix-эффектом"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Параметры матричного дождя
        self.col_width = 20
        self.row_height = 25
        self.cols = 100
        self.rows = 40
        self.rain_columns = []

        # Параметры спиннера
        self.spinner_angle = 0
        self.pulse = 0.0
        self.dots_phase = 0.0

        # Шрифты
        self.font_matrix = QFont("Consolas", 16, QFont.Weight.Bold)
        self.font_loading = QFont("Consolas", 14, QFont.Weight.Bold)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_animation)
        self.timer.start(40)

        self._initialized = False

    def showEvent(self, event):
        super().showEvent(event)
        self._init_rain()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._init_rain()

    def _init_rain(self):
        if self.width() < 10 or self.height() < 10:
            return

        self.cols = self.width() // self.col_width
        self.rows = self.height() // self.row_height

        chars_pool = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"

        self.rain_columns = []
        for i in range(self.cols):
            col = {
                'x': i,
                'y': random.randint(-self.rows, 0),
                'speed': random.uniform(0.3, 1.5),
                'trail_length': random.randint(8, 15),
                'chars': [random.choice(chars_pool) for _ in range(15)]
            }
            self.rain_columns.append(col)

        self._initialized = True

    def _update_animation(self):
        chars_pool = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"

        # Обновляем дождь
        for col in self.rain_columns:
            col['y'] += col['speed']

            if col['y'] > self.rows + col['trail_length']:
                col['y'] = random.randint(-col['trail_length'] * 2, -col['trail_length'])
                col['speed'] = random.uniform(0.3, 1.5)
                col['trail_length'] = random.randint(8, 15)
                col['chars'] = [random.choice(chars_pool) for _ in range(col['trail_length'])]

            # Иногда меняем символы
            if random.random() < 0.1 and col['chars']:
                idx = random.randint(0, len(col['chars']) - 1)
                col['chars'][idx] = random.choice(chars_pool)

        # Обновляем спиннер
        self.spinner_angle = (self.spinner_angle + 5) % 360
        self.pulse = (self.pulse + 0.08) % (2 * math.pi)
        self.dots_phase = (self.dots_phase + 0.12) % (2 * math.pi)

        self.update()

    def paintEvent(self, event):
        if not self._initialized:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Тёмный полупрозрачный фон
        painter.fillRect(self.rect(), QColor(0, 0, 0, 200))

        # Матричный дождь
        painter.setFont(self.font_matrix)
        for col in self.rain_columns:
            x_pos = col['x'] * self.col_width + 10

            for i in range(col['trail_length']):
                y_pos_idx = int(col['y'] - i)

                if 0 <= y_pos_idx < self.rows:
                    y_pos = y_pos_idx * self.row_height + 20

                    if i == 0:
                        # Голова - яркий белый с зеленоватым оттенком
                        color = QColor(220, 255, 220)
                        alpha = 255
                    elif i < 3:
                        # Ближайшие символы - яркий зеленый
                        color = QColor(0, 255, 100)
                        alpha = int(255 * (1 - i / 5))
                    else:
                        # Хвост - темный зеленый
                        brightness = int(180 * (1 - i / col['trail_length']))
                        color = QColor(0, brightness, int(brightness * 0.5))
                        alpha = int(200 * (1 - i / col['trail_length']))

                    color.setAlpha(alpha)
                    painter.setPen(color)

                    if i < len(col['chars']):
                        painter.drawText(x_pos, y_pos, col['chars'][i])

        # Центр экрана
        cx = self.width() // 2
        cy = self.height() // 2

        # Рисуем спиннер
        self._draw_spinner(painter, cx, cy)

        # Текст загрузки
        self._draw_loading_text(painter, cx, cy)

    def _draw_spinner(self, painter, cx, cy):
        """Современный круговой спиннер"""

        # Пульсация размера
        pulse_scale = 1.0 + 0.05 * math.sin(self.pulse)

        # Внешнее кольцо - вращающаяся дуга
        outer_radius = 45 * pulse_scale
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.spinner_angle)

        # Градиентная дуга
        for i in range(20):
            t = i / 20
            alpha = int(255 * (1 - t))
            color = QColor(0, 255, 100, alpha)
            pen = QPen(color, 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)

            start_angle = int(i * 5 * 16)
            span_angle = int(6 * 16)
            rect = QRectF(-outer_radius, -outer_radius, outer_radius * 2, outer_radius * 2)
            painter.drawArc(rect, start_angle, span_angle)

        painter.restore()

        # Среднее кольцо - вращается в другую сторону
        middle_radius = 32 * pulse_scale
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self.spinner_angle * 1.3)

        for i in range(15):
            t = i / 15
            alpha = int(200 * (1 - t))
            color = QColor(0, 200, 80, alpha)
            pen = QPen(color, 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)

            start_angle = int(i * 8 * 16)
            span_angle = int(10 * 16)
            rect = QRectF(-middle_radius, -middle_radius, middle_radius * 2, middle_radius * 2)
            painter.drawArc(rect, start_angle, span_angle)

        painter.restore()

        # Внутреннее кольцо из точек
        inner_radius = 20 * pulse_scale
        num_dots = 8
        for i in range(num_dots):
            angle = math.radians(i * (360 / num_dots) + self.spinner_angle * 0.5)

            x = cx + inner_radius * math.cos(angle)
            y = cy + inner_radius * math.sin(angle)

            # Пульсация каждой точки со сдвигом фазы
            phase = (i / num_dots) * 2 * math.pi + self.dots_phase
            dot_alpha = int(100 + 155 * abs(math.sin(phase)))
            dot_scale = 0.5 + 0.5 * abs(math.sin(phase))

            color = QColor(0, 255, 120, dot_alpha)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)

            dot_radius = 4 * dot_scale
            painter.drawEllipse(QPointF(x, y), dot_radius, dot_radius)

        # Центральное свечение
        glow_radius = 12 * pulse_scale
        gradient = QRadialGradient(cx, cy, glow_radius)
        brightness = int(200 + 55 * math.sin(self.pulse))
        gradient.setColorAt(0, QColor(brightness, 255, brightness, 180))
        gradient.setColorAt(0.6, QColor(0, 200, 100, 80))
        gradient.setColorAt(1, QColor(0, 100, 50, 0))

        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), glow_radius, glow_radius)

    def _draw_loading_text(self, painter, cx, cy):
        """Текст Loading с эффектами"""
        painter.setFont(self.font_loading)
        text = "Loading..."

        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(text)
        text_x = cx - text_width // 2
        text_y = cy + 80

        # Тень
        painter.setPen(QColor(0, 0, 0, 180))
        painter.drawText(text_x + 2, text_y + 2, text)

        # Свечение
        glow_alpha = int(80 + 40 * math.sin(self.pulse))
        painter.setPen(QPen(QColor(0, 255, 100, glow_alpha), 3))
        painter.drawText(text_x, text_y, text)

        # Основной текст
        text_alpha = int(200 + 55 * math.sin(self.pulse))
        painter.setPen(QColor(220, 255, 220, text_alpha))
        painter.drawText(text_x, text_y, text)
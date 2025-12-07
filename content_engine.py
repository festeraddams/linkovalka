"""
content_engine.py — Единый модуль замены контента v4.0

КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ v4.0:
- Поддержка POST, PAGE, CATEGORY, ARCHIVE страниц
- Автоопределение типа страницы по body-классам и структуре
- Для категорий: удаление листинга постов, вставка контента
- НЕ трогает <head> вообще — работает только с <body>
- Сохраняет оригинальный порядок атрибутов
- Не ломает void-теги (<meta>, <link>, <br>, <img>)
- Использует lxml для парсинга (более надёжный)

Принципы:
1. HEAD остаётся НЕТРОНУТЫМ
2. Автодетект типа страницы (POST/PAGE/CATEGORY/ARCHIVE)
3. Для POST/PAGE: заменяется контент внутри контейнера статьи
4. Для CATEGORY/ARCHIVE: удаляется листинг, вставляется контент
5. Сохраняются wrapper-div'ы и их CSS-классы
6. H1 обрабатывается отдельно
"""

import re
import logging
from enum import Enum, auto
from typing import Optional, List, Dict, Tuple, Any
from lxml import etree, html
from lxml.html import HtmlElement, tostring, fragment_fromstring
from copy import deepcopy


# ─────────────────────────────────────────────────────────────────────────────
# PAGE TYPE ENUM
# ─────────────────────────────────────────────────────────────────────────────
class PageType(Enum):
    """Тип WordPress страницы."""
    POST = auto()      # Одиночная запись (single post)
    PAGE = auto()      # Статическая страница
    CATEGORY = auto()  # Архив категории
    ARCHIVE = auto()   # Другие архивы (tag, author, date)
    UNKNOWN = auto()   # Не удалось определить

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# ─────────────────────────────────────────────────────────────────────────────
# СЕЛЕКТОРЫ КОНТЕЙНЕРОВ (XPath, от узких к широким)
# ─────────────────────────────────────────────────────────────────────────────
CONTENT_XPATHS: Tuple[str, ...] = (
    # === 1. Page Builders (самые точные) ===
    # Elementor
    "//div[contains(@class, 'elementor-widget-theme-post-content')]//div[contains(@class, 'elementor-widget-container')]",
    "//div[contains(@class, 'elementor-widget-text-editor')]//div[contains(@class, 'elementor-widget-container')]",
    "//div[contains(@class, 'elementor-text-editor')]",
    # Divi
    "//div[contains(@class, 'et_pb_post_content')]",
    "//div[contains(@class, 'et_pb_text_inner')]",
    "//div[contains(@class, 'et_pb_module_inner')]",
    # WPBakery
    "//div[contains(@class, 'wpb_text_column')]//div[contains(@class, 'wpb_wrapper')]",
    "//div[contains(@class, 'wpb_content_element')]//div[contains(@class, 'wpb_wrapper')]",
    # Beaver Builder
    "//div[contains(@class, 'fl-post-content')]",
    "//div[contains(@class, 'fl-module-content')]",
    "//div[contains(@class, 'fl-rich-text')]",
    # Bricks
    "//div[contains(@class, 'brxe-post-content')]",
    "//div[contains(@class, 'brxe-text-basic')]",
    "//div[contains(@class, 'brxe-text')]",
    # Oxygen
    "//div[contains(@class, 'ct-text-block')]",
    "//div[contains(@class, 'oxy-post-content')]",
    "//div[contains(@class, 'ct-content-block')]",
    # Gutenberg
    "//div[contains(@class, 'wp-block-post-content')]",
    # Thrive
    "//div[contains(@class, 'thrv_text_element')]",
    "//div[contains(@class, 'tve_shortcode_rendered')]",
    # Brizy
    "//div[contains(@class, 'brz-rich-text')]",
    "//div[contains(@class, 'brz-text')]",
    # SeedProd
    "//div[contains(@class, 'seedprod-text')]",

    # === 2. Специфичные темы ===
    # Flavor / flavor variations
    "//div[contains(@class, 'single-content')]",
    "//div[contains(@class, 'w-post-elm') and contains(@class, 'post_content')]",
    "//div[contains(@class, 'uk-margin-medium-top') and @property='text']",
    "//div[@property='text']",
    "//div[contains(@class, 'l-section-h')]//div[contains(@class, 'w-post-elm')]",
    # Astra
    "//div[contains(@class, 'ast-post-content')]",
    "//div[contains(@class, 'ast-article-post')]//div[contains(@class, 'entry-content')]",
    # GeneratePress
    "//div[contains(@class, 'inside-article')]//div[contains(@class, 'entry-content')]",
    # OceanWP
    "//div[contains(@class, 'oceanwp-post-content')]",
    # flavor theme ct- classes
    "//div[contains(@class, 'ct-page-content')]",
    "//div[contains(@class, 'ct-container-content')]",
    "//div[contains(@class, 'ct-inner-content')]",
    # Magazine themes
    "//div[contains(@class, 'td-post-content')]",
    "//div[contains(@class, 'jeg_post_content')]",
    "//div[contains(@class, 'tdb-block-inner')]",
    # flavor theme vc
    "//div[contains(@class, 'vc_row')]//div[contains(@class, 'wpb_wrapper')]",

    # === 3. WooCommerce ===
    "//div[contains(@class, 'woocommerce-product-details__short-description')]",
    "//div[@id='tab-description']",
    "//div[contains(@class, 'woocommerce-Tabs-panel--description')]",
    "//div[contains(@class, 'product-short-description')]",

    # === 4. Стандарты WordPress ===
    "//div[contains(@class, 'entry-content')]",
    "//div[contains(@class, 'post-content')]",
    "//div[contains(@class, 'single-post-content')]",
    "//div[contains(@class, 'article-content')]",
    "//div[contains(@class, 'the-content')]",
    "//div[contains(@class, 'page-content')]",
    "//div[contains(@class, 'blog-single-content')]",
    "//div[contains(@class, 'post-body')]",
    "//div[contains(@class, 'content-inner')]",
    "//div[contains(@class, 'singular-content')]",

    # === 5. Schema.org ===
    "//*[@itemprop='articleBody']",
    "//*[@itemprop='text']",
    "//*[@itemprop='description']",

    # === 6. Fallback (широкие) ===
    "//div[contains(@class, 'content-area')]//div[contains(@class, 'entry-content')]",
    "//div[contains(@class, 'content-container')]",
    "//div[contains(@class, 'content-wrapper')]",
    "//div[@id='primary']//div[contains(@class, 'content')]",
    "//div[@id='content']",
    "//div[@role='main']",
    "//article//div[contains(@class, 'content')]",
    "//article",
    "//div[contains(@class, 'hentry')]",

    # === 7. HTML5 (крайний случай) ===
    "//main//article",
    "//article[not(contains(@class, 'sidebar'))]",
    "//main[not(contains(@class, 'sidebar'))]",
)

# ─────────────────────────────────────────────────────────────────────────────
# СЕЛЕКТОРЫ ДЛЯ КАТЕГОРИЙ/АРХИВОВ (листинги постов)
# ─────────────────────────────────────────────────────────────────────────────
CATEGORY_LISTING_XPATHS: Tuple[str, ...] = (
    # === Publisher / flavor themes ===
    "//div[contains(@class, 'listing-grid')]",
    "//div[contains(@class, 'listing-blog')]",
    "//div[contains(@class, 'listing') and contains(@class, 'clearfix')]",

    # === JNews / flavor themes ===
    "//div[contains(@class, 'jeg_posts')]",
    "//div[contains(@class, 'jeg_postblock')]",
    "//div[contains(@class, 'jnews_posts')]",

    # === flavor theme Flavor Flavor ===
    "//div[contains(@class, 'posts-listing')]",
    "//div[contains(@class, 'post-listing')]",
    "//div[contains(@class, 'blog-listing')]",

    # === flavor theme flavor flavor flavor ===
    "//div[contains(@class, 'td-ss-main-content')]",
    "//div[contains(@class, 'td_module_wrap')]",
    "//div[contains(@class, 'tdb-block-inner')]//div[contains(@class, 'td-module')]/..",

    # === Flavor flavor flavor ===
    "//div[contains(@class, 'elementor-posts-container')]",
    "//div[contains(@class, 'elementor-posts')]",
    "//div[contains(@class, 'elementor-loop-container')]",

    # === flavor flavor flavor ===
    "//div[contains(@class, 'et_pb_blog_grid')]",
    "//div[contains(@class, 'et_pb_posts')]",

    # === flavor flavor flavor ===
    "//div[contains(@class, 'theme-flavor-container')]//div[contains(@class, 'posts')]",
    "//div[contains(@class, 'ast-archive-post')]/..",
    "//div[contains(@class, 'flavor')]//div[contains(@class, 'posts')]",

    # === flavor Standard ===
    "//div[contains(@class, 'archive-posts')]",
    "//div[contains(@class, 'blog-posts')]",
    "//div[contains(@class, 'posts-wrapper')]",
    "//div[contains(@class, 'post-list')]",
    "//div[contains(@class, 'category-posts')]",

    # === flavor flavor flavor (содержит articles) ===
    "//div[.//article[contains(@class, 'listing-item')]]",
    "//div[.//article[contains(@class, 'post-item')]]",
    "//div[.//article[contains(@class, 'type-post')]]",
    "//section[.//article[contains(@class, 'type-post')]]",

    # === flavor Fallback ===
    "//main//div[count(.//article) >= 2]",
    "//div[@id='content']//div[count(.//article) >= 2]",
    "//div[contains(@class, 'content')]//div[count(.//article) >= 2]",
)

# XPath для поиска H1 в категориях/архивах
CATEGORY_HEADER_XPATHS: Tuple[str, ...] = (
    # === Publisher / flavor themes ===
    "//section[contains(@class, 'archive-title')]//h1",
    "//section[contains(@class, 'category-title')]//h1",
    "//div[contains(@class, 'archive-title')]//h1",
    "//div[contains(@class, 'category-title')]//h1",

    # === flavor Standard ===
    "//h1[contains(@class, 'page-heading')]",
    "//h1[contains(@class, 'page-title')]",
    "//h1[contains(@class, 'archive-title')]",
    "//h1[contains(@class, 'category-title')]",
    "//h1[contains(@class, 'term-title')]",

    # === JNews ===
    "//div[contains(@class, 'jeg_cat_header')]//h1",
    "//div[contains(@class, 'jeg_archive_header')]//h1",

    # === flavor flavor ===
    "//header[contains(@class, 'page-header')]//h1",
    "//header[contains(@class, 'archive-header')]//h1",
    "//div[contains(@class, 'page-header')]//h1",

    # === Elementor ===
    "//div[contains(@class, 'elementor-widget-archive-title')]//h1",
    "//h1[contains(@class, 'elementor-heading-title')]",

    # === Fallback ===
    "//h1",
)

# XPath для поиска H1
HEADER_XPATHS: Tuple[str, ...] = (
    # Именно этот класс отвечает за динамический заголовок в твоей теме
    "//div[contains(@class, 'elementor-widget-theme-post-title')]//h1",
    "//div[contains(@class, 'elementor-widget-page-title')]//h1",
    "//*[@data-widget_type='theme-post-title.default']//h1",

    # Баннеры тем
    "//section[contains(@class, 'page-title')]//h1",
    "//div[contains(@class, 'page-header')]//h1",
    "//header[contains(@class, 'entry-header')]//h1",
    "//div[contains(@class, 'entry-header')]//h1",
    "//div[contains(@class, 'post-header')]//h1",

    # Elementor
    "//h1[contains(@class, 'elementor-heading-title')]",
    "//div[contains(@class, 'elementor-widget-heading')]//h1",

    # Специфичные
    "//h1[contains(@class, 'entry-title')]",
    "//h1[contains(@class, 'post-title')]",
    "//h1[contains(@class, 'page-title')]",
    "//h1[@id='post_title']",

    # Глобальный fallback
    "//h1",
)

# Элементы темы которые НЕ трогаем
PRESERVE_CLASSES = frozenset([
    'share', 'social', 'author', 'meta', 'date', 'category',
    'tags', 'tag', 'navigation', 'breadcrumb', 'related',
    'comment', 'comments', 'ads', 'advertisement', 'banner',
    'widget', 'sidebar', 'menu', 'nav', 'footer', 'header',
    'signup', 'subscribe', 'newsletter', 'cta',
    'rating', 'review', 'schema', 'structured-data',
])

# Элементы которые НЕ трогаем в категориях (дополнительно)
CATEGORY_PRESERVE_CLASSES = frozenset([
    'pagination', 'paging', 'page-numbers', 'nav-links',
    'pre-title', 'term-badges', 'term-description',
    'archive-description', 'category-description',
])

# Void-элементы HTML5 (самозакрывающиеся)
VOID_ELEMENTS = frozenset([
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
    'link', 'meta', 'param', 'source', 'track', 'wbr'
])


# ─────────────────────────────────────────────────────────────────────────────
# ОСНОВНОЙ КЛАСС
# ─────────────────────────────────────────────────────────────────────────────
class ContentEngine:
    """
    Движок замены контента v4.0.

    Поддерживает:
    - POST/PAGE: стандартная замена контента в контейнере статьи
    - CATEGORY/ARCHIVE: удаление листинга постов, вставка контента

    КРИТИЧНО: Не трогает <head>, работает только с <body>.
    """

    def __init__(self, html_content: str):
        self.original_html = html_content
        self.doc = None
        self.body = None
        self.container = None
        self.h1_element = None

        # v4.0: Новые атрибуты для категорий
        self.page_type: PageType = PageType.UNKNOWN
        self.listing_container = None  # Контейнер листинга для категорий

        # Сохраняем head отдельно
        self._head_html = self._extract_head(html_content)
        self._doctype = self._extract_doctype(html_content)

        # Парсим только для работы с body
        self._parse_html(html_content)

    def _extract_doctype(self, html_content: str) -> str:
        """Извлекает DOCTYPE как есть."""
        match = re.match(r'(<!DOCTYPE[^>]*>)', html_content, re.IGNORECASE)
        return match.group(1) if match else '<!DOCTYPE html>'

    def _extract_head(self, html_content: str) -> str:
        """
        Извлекает <head>...</head> как СЫРУЮ СТРОКУ.
        Это гарантирует что мы его не изменим.
        """
        # Ищем head с учётом возможных атрибутов
        match = re.search(
            r'(<head[^>]*>.*?</head>)',
            html_content,
            re.IGNORECASE | re.DOTALL
        )
        if match:
            return match.group(1)
        return '<head></head>'

    def _parse_html(self, html_content: str):
        """Парсит HTML через lxml."""
        try:
            # Используем lxml.html для парсинга
            self.doc = html.fromstring(html_content)

            # Находим body
            body_list = self.doc.xpath('//body')
            if body_list:
                self.body = body_list[0]
            else:
                self.body = self.doc

        except Exception as e:
            logger.error(f"Ошибка парсинга HTML: {e}")
            raise ValueError(f"Не удалось распарсить HTML: {e}")

    def detect_page_type(self) -> PageType:
        """
        Определяет тип WordPress страницы по body-классам и структуре.

        Returns:
            PageType: POST, PAGE, CATEGORY, ARCHIVE или UNKNOWN
        """
        if self.body is None:
            return PageType.UNKNOWN

        # Получаем классы body
        body_classes = (self.body.get('class') or '').lower()

        # === 1. Проверка по body-классам (самый надёжный способ) ===

        # CATEGORY / ARCHIVE
        category_indicators = [
            'category', 'archive', 'tag', 'tax-', 'taxonomy-',
            'author', 'date', 'search-results', 'post-type-archive'
        ]
        for indicator in category_indicators:
            if indicator in body_classes:
                # Различаем category и archive
                if 'category' in body_classes:
                    self.page_type = PageType.CATEGORY
                else:
                    self.page_type = PageType.ARCHIVE
                logger.debug(f"Тип страницы по body-классам: {self.page_type.name}")
                return self.page_type

        # SINGLE POST
        post_indicators = ['single-post', 'single-format', 'postid-']
        for indicator in post_indicators:
            if indicator in body_classes:
                self.page_type = PageType.POST
                logger.debug(f"Тип страницы: POST (по body-классам)")
                return self.page_type

        # PAGE
        page_indicators = ['page-template', 'page-id-', 'page ']  # 'page ' с пробелом
        for indicator in page_indicators:
            if indicator in body_classes:
                self.page_type = PageType.PAGE
                logger.debug(f"Тип страницы: PAGE (по body-классам)")
                return self.page_type

        # === 2. Проверка по структуре (fallback) ===

        # Ищем характерные элементы категорий
        category_structure_xpaths = [
            "//section[contains(@class, 'archive-title')]",
            "//section[contains(@class, 'category-title')]",
            "//div[contains(@class, 'archive-title')]",
            "//h1[contains(@class, 'page-heading')]",
            "//div[contains(@class, 'listing-grid')]",
            "//div[contains(@class, 'jeg_posts')]",
        ]

        for xpath in category_structure_xpaths:
            try:
                if self.body.xpath(xpath):
                    self.page_type = PageType.CATEGORY
                    logger.debug(f"Тип страницы: CATEGORY (по структуре: {xpath})")
                    return self.page_type
            except Exception:
                continue

        # Проверяем количество article элементов (признак листинга)
        articles = self.body.xpath('//article[contains(@class, "listing-item") or contains(@class, "type-post")]')
        if len(articles) >= 2:
            self.page_type = PageType.CATEGORY
            logger.debug(f"Тип страницы: CATEGORY (найдено {len(articles)} article-элементов)")
            return self.page_type

        # Проверяем наличие одного article с контентом (признак поста)
        single_article = self.body.xpath('//article[.//div[contains(@class, "entry-content") or contains(@class, "post-content")]]')
        if single_article:
            self.page_type = PageType.POST
            logger.debug(f"Тип страницы: POST (по структуре article)")
            return self.page_type

        # Не удалось определить — пробуем как POST (обратная совместимость)
        self.page_type = PageType.UNKNOWN
        logger.warning("Не удалось определить тип страницы, будет использован режим POST")
        return self.page_type

    def find_content_container(self) -> Optional[HtmlElement]:
        """Находит контейнер статьи по XPath."""
        if self.body is None:
            return None

        for xpath in CONTENT_XPATHS:
            try:
                results = self.body.xpath(xpath)
                if results:
                    container = results[0]
                    if self._is_valid_container(container):
                        logger.debug(f"Контейнер найден: {xpath}")
                        self.container = container
                        return container
            except Exception as e:
                logger.debug(f"XPath error {xpath}: {e}")
                continue

        # Fallback: поиск по плотности текста
        container = self._find_by_text_density()
        if container is not None:
            self.container = container
            return container

        logger.warning("Контейнер контента не найден!")
        return None

    def _is_valid_container(self, elem: HtmlElement) -> bool:
        """Проверяет валидность контейнера."""
        if elem is None:
            return False

        # Должно быть минимум 2 параграфа
        p_tags = elem.xpath('.//p')
        if len(p_tags) < 2:
            return False

        # Проверяем что это не sidebar/menu
        classes = (elem.get('class') or '').lower()
        elem_id = (elem.get('id') or '').lower()
        combined = classes + ' ' + elem_id

        #bad_indicators = ['sidebar', 'menu', 'footer', 'header', 'comment', 'widget', 'nav']
        bad_indicators = ['sidebar', 'menu', 'footer', 'header', 'comment', 'nav']
        for bad in bad_indicators:
            if bad in combined:
                return False

        return True

    def _find_by_text_density(self) -> Optional[HtmlElement]:
        """Находит контейнер по плотности текста."""
        if self.body is None:
            return None

        candidates = []

        for elem in self.body.xpath('.//div | .//article | .//section | .//main'):
            classes = (elem.get('class') or '').lower()
            elem_id = (elem.get('id') or '').lower()
            combined = classes + ' ' + elem_id

            # Пропускаем плохие контейнеры
            if any(bad in combined for bad in PRESERVE_CLASSES):
                continue

            p_tags = elem.xpath('.//p')
            if len(p_tags) >= 2:
                text_len = sum(len(p.text_content() or '') for p in p_tags)
                if text_len > 300:
                    # Глубина вложенности как штраф
                    depth = len(list(elem.iterancestors()))
                    score = text_len / (depth + 1)
                    candidates.append((elem, score))

        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # МЕТОДЫ ДЛЯ КАТЕГОРИЙ/АРХИВОВ (v4.0)
    # ─────────────────────────────────────────────────────────────────────────

    def find_listing_container(self) -> Optional[HtmlElement]:
        """
        Находит контейнер листинга постов для категорий/архивов.

        Returns:
            HtmlElement контейнера или None
        """
        if self.body is None:
            return None

        # Пробуем XPath селекторы
        for xpath in CATEGORY_LISTING_XPATHS:
            try:
                results = self.body.xpath(xpath)
                if results:
                    container = results[0]
                    # Проверяем что это действительно листинг (есть articles)
                    articles = container.xpath('.//article | ./article')
                    if articles or 'listing' in (container.get('class') or '').lower():
                        logger.debug(f"Листинг категории найден: {xpath}")
                        self.listing_container = container
                        return container
            except Exception as e:
                logger.debug(f"XPath error {xpath}: {e}")
                continue

        # Fallback: ищем div с максимальным количеством article
        best_container = None
        max_articles = 0

        for elem in self.body.xpath('.//div | .//section | .//main'):
            classes = (elem.get('class') or '').lower()
            elem_id = (elem.get('id') or '').lower()
            combined = classes + ' ' + elem_id

            # Пропускаем sidebar, footer и т.д.
            if any(bad in combined for bad in PRESERVE_CLASSES):
                continue

            # Считаем article внутри
            articles = elem.xpath('./article | .//article')
            if len(articles) > max_articles:
                max_articles = len(articles)
                best_container = elem

        if best_container is not None and max_articles >= 2:
            logger.debug(f"Листинг найден по количеству articles: {max_articles}")
            self.listing_container = best_container
            return best_container

        logger.warning("Контейнер листинга категории не найден!")
        return None

    def find_category_h1(self) -> Optional[HtmlElement]:
        """
        Находит H1 заголовок категории/архива.

        Returns:
            HtmlElement H1 или None
        """
        if self.body is None:
            return None

        # Сначала пробуем специфичные селекторы для категорий
        for xpath in CATEGORY_HEADER_XPATHS:
            try:
                results = self.body.xpath(xpath)
                if results:
                    self.h1_element = results[0]
                    logger.debug(f"H1 категории найден: {xpath}")
                    return self.h1_element
            except Exception:
                continue

        # Fallback на обычные селекторы
        return self.find_h1()

    def _clear_listing_container(self, container: HtmlElement):
        """
        Очищает контейнер листинга, удаляя все article и сохраняя структурные элементы.

        Args:
            container: Контейнер листинга для очистки
        """
        to_remove = []

        for child in list(container):
            # Проверяем классы
            classes = (child.get('class') or '').lower()
            elem_id = (child.get('id') or '').lower()
            combined = classes + ' ' + elem_id

            # Удаляем article элементы
            if child.tag == 'article':
                to_remove.append(child)
                continue

            # Удаляем div'ы с listing-item, type-post и т.д.
            listing_indicators = [
                'listing-item', 'post-item', 'type-post', 'hentry',
                'jeg_post', 'td_module', 'elementor-post'
            ]
            if any(ind in combined for ind in listing_indicators):
                to_remove.append(child)
                continue

            # Сохраняем pagination, description и другие элементы
            preserve_indicators = list(CATEGORY_PRESERVE_CLASSES) + list(PRESERVE_CLASSES)
            if any(ind in combined for ind in preserve_indicators):
                continue

            # Если это пустой div или div только с articles — удаляем
            if child.tag == 'div':
                sub_articles = child.xpath('.//article')
                other_content = child.xpath('.//*[not(self::article)]')
                if sub_articles and not other_content:
                    to_remove.append(child)

        for elem in to_remove:
            container.remove(elem)

        # Очищаем текст между элементами
        container.text = None
        for child in container:
            child.tail = None

        logger.debug(f"Удалено {len(to_remove)} элементов из листинга категории")

    def _replace_category_content(self, new_html: str) -> str:
        """
        Заменяет контент на странице категории/архива.

        Алгоритм:
        1. Находит H1 категории и обновляет текст
        2. Находит контейнер листинга
        3. Удаляет все article/post элементы из листинга
        4. Вставляет новый контент в контейнер листинга

        Args:
            new_html: Новый HTML контент (h1 + p + h2 + ul + etc.)

        Returns:
            Полный HTML с заменённым контентом
        """
        # 1. Находим контейнер листинга
        if self.listing_container is None:
            self.find_listing_container()

        if self.listing_container is None:
            raise ValueError(
                "Контейнер листинга категории не найден. "
                "Страница имеет нестандартную структуру."
            )

        # 2. Парсим новый контент
        new_elements = self._parse_new_content(new_html)

        # 3. Извлекаем H1 из нового контента
        new_h1_text = None
        new_h1_element = None
        new_elements_filtered = []

        for elem in new_elements:
            if elem.tag == 'h1' and new_h1_text is None:
                new_h1_text = elem.text_content()
                new_h1_element = elem
            else:
                new_elements_filtered.append(elem)

        # 4. Заменяем/вставляем H1
        if new_h1_text:
            self.find_category_h1()
            if self.h1_element is not None:
                self.replace_h1_text(new_h1_text)
            elif new_h1_element is not None:
                # H1 нет в шаблоне — вставляем перед листингом
                parent = self.listing_container.getparent()
                if parent is not None:
                    idx = list(parent).index(self.listing_container)
                    parent.insert(idx, deepcopy(new_h1_element))

        # 5. Очищаем листинг от articles
        self._clear_listing_container(self.listing_container)

        # 6. Создаём wrapper для нового контента (сохраняем стили темы)
        content_wrapper = etree.Element('div')
        content_wrapper.set('class', 'category-content-replaced entry-content')

        # 7. Вставляем новый контент в wrapper
        for elem in new_elements_filtered:
            elem_copy = deepcopy(elem)
            content_wrapper.append(elem_copy)

        # 8. Вставляем wrapper в контейнер листинга
        # Вставляем в начало, перед pagination если есть
        if len(self.listing_container) > 0:
            self.listing_container.insert(0, content_wrapper)
        else:
            self.listing_container.append(content_wrapper)

        # 9. Гарантируем один H1
        self._ensure_single_h1()

        # 10. Собираем результат
        return self._build_final_html()

    def find_h1(self) -> Optional[HtmlElement]:
        """Находит H1 заголовок."""
        if self.body is None:
            return None

        for xpath in HEADER_XPATHS:
            try:
                results = self.body.xpath(xpath)
                if results:
                    self.h1_element = results[0]
                    logger.debug(f"H1 найден: {xpath}")
                    return self.h1_element
            except Exception:
                continue

        logger.warning("H1 не найден")
        return None

    def replace_h1_text(self, new_text: str) -> bool:
        """Заменяет текст H1, сохраняя структуру и атрибуты."""
        if self.h1_element is None:
            self.find_h1()

        if self.h1_element is None:
            return False

        # Ищем вложенный span/a
        inner = self.h1_element.xpath('.//span | .//a')
        if inner:
            # Очищаем и вставляем текст во внутренний элемент
            inner[0].text = new_text
            # Удаляем tail и children после текста
            for child in list(inner[0]):
                inner[0].remove(child)
        else:
            # Очищаем h1 и вставляем текст
            self.h1_element.text = new_text
            for child in list(self.h1_element):
                self.h1_element.remove(child)

        logger.debug(f"H1 заменён на: {new_text[:50]}...")
        return True

    def _is_preserve_element(self, elem: HtmlElement) -> bool:
        """Проверяет, является ли элемент theme-элементом (не трогать)."""
        if elem is None:
            return False

        classes = (elem.get('class') or '').lower()
        elem_id = (elem.get('id') or '').lower()
        combined = classes + ' ' + elem_id

        # Проверяем по классам
        for indicator in PRESERVE_CLASSES:
            if indicator in combined:
                return True

        # Проверяем тег
        if elem.tag in ['aside', 'nav', 'footer', 'header', 'form']:
            return True

        return False

    def _clear_container(self, container: HtmlElement):
        """Очищает контейнер, сохраняя theme-элементы."""
        to_remove = []

        for child in list(container):
            # Не трогаем theme-элементы
            if self._is_preserve_element(child):
                continue
            # Не трогаем H1 (обрабатывается отдельно)
            if child.tag == 'h1':
                continue
            to_remove.append(child)

        for elem in to_remove:
            container.remove(elem)

        # Очищаем текст между элементами
        container.text = None
        for child in container:
            child.tail = None

        logger.debug(f"Удалено {len(to_remove)} элементов из контейнера")

    def _parse_new_content(self, new_html: str) -> List[HtmlElement]:
        """Парсит новый контент в список элементов."""
        elements = []

        # Оборачиваем в div для парсинга
        wrapped = f"<div>{new_html}</div>"

        try:
            fragment = html.fromstring(wrapped)

            # Извлекаем детей
            for child in fragment:
                if isinstance(child, HtmlElement):
                    elements.append(child)

        except Exception as e:
            logger.error(f"Ошибка парсинга нового контента: {e}")

        return elements

    def replace_content(self, new_html: str) -> str:
        """
        ГЛАВНЫЙ МЕТОД замены контента v4.0.

        Автоматически определяет тип страницы и применяет соответствующий алгоритм:
        - POST/PAGE: стандартная замена в контейнере статьи
        - CATEGORY/ARCHIVE: удаление листинга, вставка контента

        Возвращает полный HTML с:
        - Оригинальным DOCTYPE
        - Оригинальным <head> (НЕ ИЗМЕНЁН!)
        - Изменённым <body>
        """
        # 0. Определяем тип страницы
        if self.page_type == PageType.UNKNOWN:
            self.detect_page_type()

        # Для CATEGORY/ARCHIVE используем специальный метод
        if self.page_type in (PageType.CATEGORY, PageType.ARCHIVE):
            logger.info(f"Режим замены: {self.page_type.name}")
            return self._replace_category_content(new_html)

        # Для POST/PAGE/UNKNOWN используем стандартный алгоритм
        logger.info(f"Режим замены: POST/PAGE (тип: {self.page_type.name})")
        return self._replace_post_content(new_html)

    def _replace_post_content(self, new_html: str) -> str:
        """
        Заменяет контент на странице POST/PAGE (оригинальный алгоритм).

        Args:
            new_html: Новый HTML контент

        Returns:
            Полный HTML с заменённым контентом
        """
        # 1. Находим контейнер
        if self.container is None:
            self.find_content_container()

        if self.container is None:
            raise ValueError(
                "Контейнер контента не найден. "
                "Страница имеет нестандартную структуру."
            )

        # 2. Парсим новый контент
        new_elements = self._parse_new_content(new_html)

        # 3. Извлекаем H1 из нового контента
        new_h1_text = None
        new_h1_element = None
        new_elements_filtered = []

        for elem in new_elements:
            if elem.tag == 'h1' and new_h1_text is None:
                # Первый H1 запоминаем отдельно
                new_h1_text = elem.text_content()
                new_h1_element = elem
            else:
                new_elements_filtered.append(elem)

        # 4. Заменяем/вставляем H1
        if new_h1_text:
            self.find_h1()
            if self.h1_element is not None:
                # В шаблоне уже есть H1 — меняем только текст
                self.replace_h1_text(new_h1_text)
            elif new_h1_element is not None:
                # В шаблоне H1 нет — вставляем H1 из нового контента в начало контейнера
                new_elements_filtered.insert(0, new_h1_element)

        # 5. Находим wrapper внутри контейнера
        target = self._find_wrapper() or self.container

        # 6. Очищаем старый контент
        self._clear_container(target)

        # 7. Вставляем новый контент
        for i, elem in enumerate(new_elements_filtered):
            # Делаем глубокую копию
            elem_copy = deepcopy(elem)
            target.append(elem_copy)

        # 8. Гарантируем один H1
        self._ensure_single_h1()

        # 9. Собираем результат
        return self._build_final_html()

    def _find_wrapper(self) -> Optional[HtmlElement]:
        """Находит внутренний wrapper-div."""
        if self.container is None:
            return None

        # Ищем div с большинством параграфов
        all_p = self.container.xpath('.//p')
        if len(all_p) < 2:
            return None

        for child in self.container:
            if not isinstance(child, HtmlElement):
                continue
            if child.tag != 'div':
                continue

            # Пропускаем theme-элементы
            if self._is_preserve_element(child):
                continue

            child_p = child.xpath('.//p')
            if len(child_p) >= len(all_p) * 0.7:
                logger.debug(f"Wrapper найден: class={child.get('class')}")
                return child

        return None

    def _ensure_single_h1(self):
        """Гарантирует один H1 на странице."""
        if self.body is None:
            return

        all_h1 = self.body.xpath('.//h1')

        if len(all_h1) <= 1:
            return

        # Оставляем первый, остальные делаем h2
        for h1 in all_h1[1:]:
            h1.tag = 'h2'
            logger.debug(f"Лишний H1 преобразован в H2")

    def _build_final_html(self) -> str:
        """
        Собирает финальный HTML.
        КРИТИЧНО: Использует ОРИГИНАЛЬНЫЙ head!
        """
        # Получаем body как строку
        body_html = tostring(
            self.body,
            encoding='unicode',
            method='html'
        )

        # Собираем полный HTML
        result = f"""{self._doctype}
        <html>
        {self._head_html}
        {body_html}
        </html>"""

        # Нормализуем переводы строк, чтобы дальше при записи файла
        # не появлялись пустые строки между каждой строкой
        result = result.replace("\r\n", "\n").replace("\r", "\n")

        return result


# ─────────────────────────────────────────────────────────────────────────────
# ПУБЛИЧНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────────────────────────────────────

def replace_content(old_html: str, new_html: str) -> str:
    """
    Основная функция замены контента.

    Args:
        old_html: Исходный HTML страницы
        new_html: Новый контент (h1 + p + h2 + ul + etc.)

    Returns:
        Полный HTML с заменённым контентом и НЕТРОНУТЫМ head
    """
    engine = ContentEngine(old_html)
    return engine.replace_content(new_html)


def detect_page_type_from_html(html_content: str) -> PageType:
    """
    Определяет тип WordPress страницы.

    Args:
        html_content: HTML страницы

    Returns:
        PageType: POST, PAGE, CATEGORY, ARCHIVE или UNKNOWN
    """
    engine = ContentEngine(html_content)
    return engine.detect_page_type()


def smart_replace_content(old_html: str, new_html: str) -> str:
    """Алиас для совместимости."""
    return replace_content(old_html, new_html)


def universal_replace_content(old_html: str, new_html: str, force_full_replace: bool = False) -> str:
    """Алиас для совместимости с content_replacer.py"""
    return replace_content(old_html, new_html)


def analyze_page_structure(html_content: str) -> Dict[str, Any]:
    """
    Анализирует структуру страницы для отладки.

    v4.0: Добавлена информация о типе страницы и листинге категорий.
    """
    engine = ContentEngine(html_content)

    # Определяем тип страницы
    page_type = engine.detect_page_type()

    # Для категорий ищем листинг, для остальных — контейнер контента
    if page_type in (PageType.CATEGORY, PageType.ARCHIVE):
        engine.find_listing_container()
        engine.find_category_h1()
        container = engine.listing_container
    else:
        engine.find_content_container()
        engine.find_h1()
        container = engine.container

    container_info = None
    if container is not None:
        classes = container.get('class', '')
        tag = container.tag
        container_info = f"{tag}.{classes}" if classes else tag

    h1_text = None
    if engine.h1_element is not None:
        h1_text = engine.h1_element.text_content()[:100]

    # Подсчёт articles для категорий
    articles_count = 0
    if page_type in (PageType.CATEGORY, PageType.ARCHIVE) and container is not None:
        articles_count = len(container.xpath('.//article'))

    return {
        'page_type': page_type.name,
        'container_found': container is not None,
        'container_selector': container_info,
        'h1_found': engine.h1_element is not None,
        'h1_text': h1_text,
        'head_preserved': bool(engine._head_html),
        'articles_count': articles_count,  # Для категорий
    }


# ─────────────────────────────────────────────────────────────────────────────
# ТЕСТ
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8"/>
    <meta name="description" content="Test description here"/>
    <link rel="stylesheet" href="/style.css"/>
    <title>Test Page</title>
</head>
<body>
    <header><nav>Menu</nav></header>
    <main>
        <article>
            <div class="entry-content">
                <h1 class="entry-title">Old Title Here</h1>
                <p class="intro">Old paragraph one.</p>
                <p>Old paragraph two.</p>
                <h2>Old Section</h2>
                <ul><li>Old item</li></ul>
                <div class="share-buttons">Share</div>
            </div>
        </article>
    </main>
    <footer>Footer</footer>
</body>
</html>'''

    new_content = '''<h1>New Amazing Title</h1>
<p>This is brand new first paragraph.</p>
<p>Second new paragraph here.</p>
<h2>New Section Heading</h2>
<ul>
    <li>New item 1</li>
    <li>New item 2</li>
</ul>'''

    print("=" * 60)
    print("ТЕСТ CONTENT_ENGINE")
    print("=" * 60)

    result = replace_content(test_html, new_content)
    print(result)

    print("\n" + "=" * 60)
    print("ПРОВЕРКА HEAD:")
    print("=" * 60)

    # Проверяем что meta не изменились
    if 'name="description" content="Test description here"' in result:
        print("✅ Порядок атрибутов meta сохранён")
    else:
        print("❌ Порядок атрибутов meta изменился")

    if '</meta>' not in result:
        print("✅ Нет лишних </meta>")
    else:
        print("❌ Есть лишние </meta>")

    if '</link>' not in result:
        print("✅ Нет лишних </link>")
    else:
        print("❌ Есть лишние </link>")

    print("\n" + "=" * 60)
    print("АНАЛИЗ СТРУКТУРЫ:")
    print("=" * 60)
    print(analyze_page_structure(test_html))

    # ─────────────────────────────────────────────────────────────────────────
    # ТЕСТ КАТЕГОРИИ
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ТЕСТ КАТЕГОРИИ")
    print("=" * 60)

    category_html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8"/>
    <title>Category: Health</title>
</head>
<body class="archive category category-health">
    <header><nav>Menu</nav></header>
    <main>
        <section class="archive-title category-title">
            <h1 class="page-heading">Health &amp; Wellness</h1>
        </section>
        <div class="listing listing-grid clearfix">
            <article class="listing-item listing-item-grid type-post">
                <h2 class="title"><a href="/post1/">Post 1 Title</a></h2>
                <div class="post-summary">Summary of post 1...</div>
            </article>
            <article class="listing-item listing-item-grid type-post">
                <h2 class="title"><a href="/post2/">Post 2 Title</a></h2>
                <div class="post-summary">Summary of post 2...</div>
            </article>
            <article class="listing-item listing-item-grid type-post">
                <h2 class="title"><a href="/post3/">Post 3 Title</a></h2>
                <div class="post-summary">Summary of post 3...</div>
            </article>
            <div class="pagination">
                <a href="/page/2/">Next</a>
            </div>
        </div>
    </main>
    <footer>Footer</footer>
</body>
</html>'''

    new_category_content = '''<h1>Complete Guide to Health & Wellness</h1>
<p>Welcome to our comprehensive guide about health and wellness topics.</p>
<p>This page covers everything you need to know about maintaining a healthy lifestyle.</p>
<h2>Key Topics</h2>
<ul>
    <li>Nutrition and Diet</li>
    <li>Exercise and Fitness</li>
    <li>Mental Health</li>
</ul>
<p>Read on to learn more about each of these important areas.</p>'''

    print("Анализ категории:")
    analysis = analyze_page_structure(category_html)
    print(f"  Тип страницы: {analysis['page_type']}")
    print(f"  Контейнер: {analysis['container_selector']}")
    print(f"  H1: {analysis['h1_text']}")
    print(f"  Articles: {analysis['articles_count']}")

    print("\nЗамена контента категории:")
    try:
        result_category = replace_content(category_html, new_category_content)

        # Проверки
        if 'Complete Guide to Health' in result_category:
            print("✅ Новый H1 вставлен")
        else:
            print("❌ Новый H1 не найден")

        if 'listing-item' not in result_category:
            print("✅ Articles удалены")
        else:
            print("❌ Articles остались")

        if 'category-content-replaced' in result_category:
            print("✅ Wrapper контента создан")
        else:
            print("❌ Wrapper не создан")

        if 'pagination' in result_category:
            print("✅ Pagination сохранён")
        else:
            print("❌ Pagination удалён")

        print("\nРезультат (фрагмент body):")
        # Показываем только body
        import re
        body_match = re.search(r'<body[^>]*>.*</body>', result_category, re.DOTALL)
        if body_match:
            print(body_match.group()[:1500] + "...")

    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
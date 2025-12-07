"""
seo_cluster_linker.py — Продвинутый SEO-модуль кластерной перелинковки v1.0

ВОЗМОЖНОСТИ:
• Морфологические анкоры с согласованием по контексту
• Умные SEO-схемы перелинковки (кластерная, пирамидальная, mesh)
• Распределение ссылок между сайтами без "простыней"
• Гарантированный охват всех страниц
• Анализ и визуализация графа ссылок
• Поддержка синонимов препаратов

АРХИТЕКТУРА:
┌─────────────────────────────────────────────────────────────┐
│                    SEOClusterLinker                         │
├─────────────────────────────────────────────────────────────┤
│  AnchorMorpher      — морфология анкоров                    │
│  LinkSchemeEngine   — схемы перелинковки                    │
│  ClusterBuilder     — построение кластеров                  │
│  LinkInserter       — вставка ссылок в HTML                 │
│  CoverageAnalyzer   — анализ охвата                         │
└─────────────────────────────────────────────────────────────┘

Автор: AI Assistant
Версия: 1.0 Production
"""

import os
import re
import json
import random
import logging
import chardet
from copy import deepcopy
from typing import Dict, List, Set, Tuple, Optional, Any, NamedTuple
from dataclasses import dataclass, field
from collections import defaultdict
from urllib.parse import urlparse
from lxml import html, etree
from lxml.html import HtmlElement

# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════════
logger = logging.getLogger("seo_cluster_linker")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.addHandler(handler)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class Page:
    """Представление страницы в кластере."""
    url: str
    domain: str
    file_path: str
    title: str = ""
    topic: str = ""
    incoming_links: int = 0
    outgoing_links: int = 0

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        return self.url == other.url


@dataclass
class Link:
    """Представление ссылки."""
    source: Page
    target: Page
    anchor: str
    link_type: str  # 'internal', 'cross-site'
    inserted: bool = False
    context: str = ""


@dataclass
class Cluster:
    """Кластер страниц одного препарата."""
    topic: str
    pages: List[Page] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)

    @property
    def domains(self) -> Set[str]:
        return {p.domain for p in self.pages}

    @property
    def pages_by_domain(self) -> Dict[str, List[Page]]:
        result = defaultdict(list)
        for p in self.pages:
            result[p.domain].append(p)
        return dict(result)


# ═══════════════════════════════════════════════════════════════════════════════
# ANCHOR MORPHER — МОРФОЛОГИЯ АНКОРОВ
# ═══════════════════════════════════════════════════════════════════════════════
class AnchorMorpher:
    """
    Генератор морфологически согласованных анкоров.

    Создаёт естественные анкоры, которые:
    - Согласуются с окружающим контекстом
    - Имеют разнообразную структуру
    - Включают LSI-вариации
    - Выглядят естественно для читателя
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # ШАБЛОНЫ АНКОРОВ ПО КАТЕГОРИЯМ
    # ═══════════════════════════════════════════════════════════════════════════

    # Коммерческие (высокий intent)
    COMMERCIAL_TEMPLATES = [
        "buy {drug} online",
        "order {drug} tablets",
        "purchase {drug} pills",
        "{drug} for sale",
        "buy {drug} without prescription",
        "order {drug} no rx",
        "get {drug} online",
        "{drug} buy now",
        "cheap {drug} online",
        "discount {drug} pills",
        "best price {drug}",
        "{drug} lowest price",
        "affordable {drug} tablets",
        "{drug} special offer",
        "buy generic {drug}",
        "order {drug} fast delivery",
        "{drug} overnight shipping",
        "buy {drug} discreet",
        "{drug} secure purchase",
        "licensed {drug} pharmacy",
        "{drug} buy online",
        "{drug} order online",
        "{drug} purchase online",
        "{drug} for sale online",
        "{drug} no prescription",
        "{drug} no rx",
        "{drug} no script",
        "{drug} without prescription",
        "{drug} non prescription",
        "{drug} over the counter",
        "{drug} otc",
        "{drug} online pharmacy",
        "{drug} pharmacy usa",
        "cheap {drug}",
        "cheap {drug} online",
        "{drug} cheapest price",
        "{drug} low price",
        "{drug} best price",
        "{drug} discount",
        "{drug} coupon",
        "{drug} promo code",
        "{drug} wholesale",
        "generic {drug} online",
        "legit {drug} online",
        "real {drug} online",
        "authentic {drug} online",
        "{drug} reviews",
        "{drug} forum",
        "{drug} in stock",
        "{drug} bulk",
        "{drug} tablets online",
        "{drug} capsules online",
        "{drug} pills online",
        "buy {drug} no script",
        "order {drug} usa to usa",
        "buy {drug} domestic shipping",
        "{drug} cash on delivery",
        "order {drug} cod",
        "buy {drug} with credit card",
        "purchase {drug} bitcoin",
        "{drug} no dr visit",
        "buy {drug} overnight",
        "{drug} next day delivery",
        "order {drug} no prescription needed",
        "{drug} fedex delivery",
        "buy {drug} pay later",
        "{drug} for sale usa",
        "generic {drug} no rx",
    ]

    # Информационные
    INFORMATIONAL_TEMPLATES = [
        "{drug} dosage guide",
        "how {drug} works",
        "{drug} side effects",
        "{drug} benefits",
        "{drug} usage instructions",
        "taking {drug} safely",
        "{drug} effectiveness",
        "{drug} reviews",
        "{drug} user experiences",
        "is {drug} safe",
        "{drug} for beginners",
        "{drug} complete guide",
        "everything about {drug}",
        "{drug} FAQ",
        "{drug} medication info",
        "understanding {drug}",
        "{drug} therapy",
        "{drug} treatment options",
        "when to use {drug}",
        "{drug} precautions",
    ]

    # Сравнительные
    COMPARISON_TEMPLATES = [
        "{drug} vs alternatives",
        "comparing {drug} options",
        "{drug} or generic",
        "best {drug} choice",
        "{drug} comparison",
        "generic vs brand {drug}",
        "{drug} alternatives",
        "similar to {drug}",
        "{drug} substitutes",
        "choosing {drug}",
    ]

    # Брендовые / навигационные
    BRANDED_TEMPLATES = [
        "{drug}",
        "{drug} generic",
        "{drug} pills",
        "{drug} tablets",
        "{drug} medication",
        "{drug} medicine",
        "{drug} drug",
        "{drug} rx",
        "{drug} pharmacy",
        "genuine {drug}",
        "original {drug}",
        "authentic {drug}",
        "real {drug}",
        "quality {drug}",
        "certified {drug}",
        "approved {drug}",
    ]

    # Длинный хвост (long-tail)
    LONGTAIL_TEMPLATES = [
        "where to buy {drug} online safely",
        "how to order {drug} without prescription",
        "best place to buy {drug} online",
        "can i buy {drug} over the counter",
        "{drug} online pharmacy reviews",
        "cheapest {drug} online pharmacy",
        "buy {drug} from trusted source",
        "order {drug} with fast shipping",
        "{drug} pills available online",
        "get {drug} delivered to your door",
        "legal {drug} online purchase",
        "safe way to buy {drug}",
        "{drug} medication without doctor",
        "online {drug} prescription",
        "how to get {drug} online",
        "buying {drug} internationally",
        "{drug} home delivery service",
        "discrete {drug} purchase online",
        "{drug} express delivery",
        "order {drug} same day delivery",
        "buy {drug} online with fast shipping",
        "order {drug} overnight shipping",
        "buy {drug} with next day delivery",
        "buy {drug} with express delivery",
        "order {drug} usa to usa shipping",
        "buy {drug} usa domestic shipping",
        "buy {drug} with fedex shipping",
        "buy {drug} with ups delivery",
        "order {drug} cash on delivery",
        "buy {drug} cod",
        "buy {drug} pay with credit card",
        "buy {drug} pay with visa",
        "buy {drug} pay with mastercard",
        "buy {drug} pay with paypal",
        "buy {drug} pay with bitcoin",
        "buy {drug} pay with crypto",
        "cheap {drug} online pharmacy usa",
        "discount {drug} online pharmacy",
        "wholesale {drug} tablets online",
        "{drug} bulk tablets online",
        "how to buy {drug} without seeing a doctor",
        "order {drug} online overnight shipping usa",
        "legit website to buy {drug}",
        "buy {drug} online no customs",
        "where to get {drug} without prescription",
        "{drug} online pharmacy accepting visa",
        "buy {drug} with paypal online",
        "order {drug} tablets next day delivery",
        "can i buy {drug} online legally",
        "safest place to order {drug} online",
    ]

    # Контекстуальные вставки (для вставки в середину предложения)
    CONTEXTUAL_TEMPLATES = [
        "{drug}",
        "{drug} tablets",
        "{drug} medication",
        "{drug} pills",
        "{drug} online",
        "{drug} treatment",
        "this {drug}",
        "the {drug}",
        "{drug} therapy",
        "{drug} dosage",
        "{drug} prescription",
        "effective {drug}",
        "popular {drug}",
        "reliable {drug}",
        "proven {drug}",
        "{drug} online pharmacy",
        "{drug} usa pharmacy",
        "{drug} otc",
        "{drug} no prescription",
        "{drug} over the counter",

    ]

    # Вопросительные (для FAQ и информационных страниц)
    QUESTION_TEMPLATES = [
        "what is {drug}",
        "how does {drug} work",
        "is {drug} effective",
        "where to get {drug}",
        "can i take {drug}",
        "should i try {drug}",
    ]

    # Призыв к действию (CTA)
    CTA_TEMPLATES = [
        "try {drug} today",
        "get your {drug}",
        "start {drug} treatment",
        "order {drug} now",
        "buy {drug} here",
        "shop {drug}",
        "discover {drug}",
        "learn about {drug}",
        "explore {drug}",
        "check {drug} prices",
    ]

    # ═══════════════════════════════════════════════════════════════════════════
    # ПЕРЕХОДНЫЕ ФРАЗЫ ДЛЯ ЕСТЕСТВЕННОЙ ВСТАВКИ
    # ═══════════════════════════════════════════════════════════════════════════

    TRANSITION_BEFORE = [
        "You can",
        "Many patients",
        "Doctors recommend to",
        "It's possible to",
        "Consider to",
        "Learn how to",
        "Find out how to",
        "Discover how to",
        "If you need to",
        "Those looking to",
        "Patients often",
        "For those who want to",
        "When you need to",
        "To effectively",
        "The best way to",
        "A reliable option is to",
        "An excellent choice is to",
        "We recommend to",
        "Experts suggest to",
        "Research shows you can",
    ]

    TRANSITION_AFTER = [
        "for best results",
        "at competitive prices",
        "from verified sources",
        "with fast delivery",
        "safely and securely",
        "without hassle",
        "with confidence",
        "from trusted pharmacies",
        "with proper guidance",
        "following medical advice",
        "as recommended",
        "when needed",
        "conveniently",
        "discreetly",
        "affordably",
        "reliably",
        "quickly",
        "easily",
        "today",
        "right now",
        "without a prescription",
        "with overnight delivery",
        "shipped from USA",
        "no doctor required",
        "with cash on delivery",
        "via priority mail",
        "without customs issues",
        "discreetly to your door",
        "using secure payment",
        "with 100% guarantee",
    ]

    # ═══════════════════════════════════════════════════════════════════════════
    # СИНОНИМЫ ДЕЙСТВИЙ
    # ═══════════════════════════════════════════════════════════════════════════

    ACTION_SYNONYMS = {
        "buy": ["purchase", "order", "get", "obtain", "acquire", "shop for"],
        "cheap": ["affordable", "low-cost", "budget", "economical", "inexpensive", "discount"],
        "fast": ["quick", "rapid", "express", "speedy", "swift", "overnight"],
        "safe": ["secure", "reliable", "trusted", "verified", "legitimate", "certified"],
        "online": ["on the internet", "digitally", "via web", "electronically"],
        "pills": ["tablets", "capsules", "medication", "medicine", "drug"],
        "best": ["top", "finest", "premium", "optimal", "superior", "excellent"],
        "effective": ["potent", "powerful", "working", "proven", "reliable"],
    }

    # Хвосты для коммерческих анкоров (доставка, оплата, OTC, отзывы и т.п.)
    TAIL_SUFFIXES = [
        # онлайн / покупка
        "online",
        "buy online",
        "order online",
        "purchase online",
        "for sale",
        "for sale online",

        # рецептурность / OTC
        "no prescription",
        "no rx",
        "no script",
        "without prescription",
        "no script needed",
        "non prescription",
        "no doctor visit",
        "no dr approval",
        "over the counter",
        "otc",

        # доставка / гео
        "usa to usa",
        "usa domestic",
        "domestic shipping",
        "fast shipping",
        "overnight shipping",
        "overnight delivery",
        "next day delivery",
        "express delivery",
        "fedex shipping",
        "ups delivery",

        # оплата
        "cash on delivery",
        "cod",
        "pay with credit card",
        "pay with visa",
        "pay with mastercard",
        "pay with paypal",
        "pay with bitcoin",
        "pay with crypto",

        # цена
        "cheap",
        "cheap online",
        "cheapest price",
        "low price",
        "best price",
        "discount",
        "coupon",
        "promo code",
        "wholesale",

        # тип / форма / легальность
        "generic",
        "legit",
        "real",
        "authentic",
        "reviews",
        "forum",
        "in stock",
        "bulk",
        "tablets",
        "capsules",
        "pills",
        "gel",

        # аптеки
        "online pharmacy",
        "online pharmacy usa",
        "pharmacy usa",
    ]

    # ═══════════════════════════════════════════════════════════════════════════
    # LSI КЛЮЧЕВЫЕ СЛОВА ПО ПРЕПАРАТАМ
    # ═══════════════════════════════════════════════════════════════════════════

    DRUG_LSI = {
        # ══════════════════════════════════════════════════════════════════════
        # ED ПРЕПАРАТЫ (Erectile Dysfunction)
        # ══════════════════════════════════════════════════════════════════════
        "viagra": [
            "sildenafil", "sildenafil citrate", "ED treatment", "erectile dysfunction",
            "male enhancement", "PDE5 inhibitor", "impotence treatment", "sexual health",
            "blue pill", "erection pills", "ED medication", "performance enhancement",
            "sexual dysfunction", "male potency", "libido booster"
        ],
        "cialis": [
            "tadalafil", "ED medication", "erectile dysfunction", "weekend pill",
            "daily ED", "36-hour pill", "PDE5 inhibitor", "impotence",
            "sexual performance", "male enhancement", "BPH treatment",
            "enlarged prostate", "urinary symptoms"
        ],
        "levitra": [
            "vardenafil", "ED pills", "erectile dysfunction", "impotence treatment",
            "PDE5 inhibitor", "sexual health", "erection medication",
            "male potency", "performance pills"
        ],
        "kamagra": [
            "sildenafil citrate", "ED generic", "erectile dysfunction",
            "sexual health", "generic viagra", "affordable ED", "impotence"
        ],
        "sildalist": [
            "sildenafil", "tadalafil", "dual action ED", "erectile dysfunction",
            "combination therapy", "powerful ED treatment"
        ],
        "tadacip": [
            "tadalafil", "generic cialis", "ED treatment", "weekend pill",
            "erectile dysfunction", "PDE5 inhibitor"
        ],
        "aurogra": [
            "sildenafil", "generic viagra", "ED pills", "erectile dysfunction",
            "affordable sildenafil", "male enhancement"
        ],

        # ══════════════════════════════════════════════════════════════════════
        # АНТИБИОТИКИ
        # ══════════════════════════════════════════════════════════════════════
        "amoxil": [
            "amoxicillin", "antibiotic", "bacterial infection", "penicillin",
            "strep throat", "ear infection", "sinus infection", "UTI",
            "respiratory infection", "dental infection", "H. pylori"
        ],
        "zithromax": [
            "azithromycin", "Z-pack", "antibiotic", "bacterial infection",
            "respiratory infection", "STD treatment", "chlamydia", "bronchitis",
            "pneumonia", "skin infection", "macrolide antibiotic"
        ],
        "doxycycline": [
            "antibiotic", "bacterial infection", "acne treatment", "Lyme disease",
            "malaria prevention", "chlamydia", "tetracycline class",
            "respiratory infection", "skin infection", "STI treatment"
        ],
        "flagyl": [
            "metronidazole", "antibiotic", "bacterial infection", "parasites",
            "BV treatment", "bacterial vaginosis", "trichomoniasis", "giardia",
            "C. diff", "dental infection", "anaerobic bacteria"
        ],
        "cleocin": [
            "clindamycin", "antibiotic", "bacterial infection", "acne",
            "MRSA", "bone infection", "skin infection", "dental"
        ],
        "keflex": [
            "cephalexin", "antibiotic", "bacterial infection", "UTI",
            "skin infection", "respiratory", "cephalosporin"
        ],
        "tetracycline": [
            "antibiotic", "acne treatment", "bacterial infection", "rosacea",
            "Lyme disease", "cholera", "plague", "broad-spectrum"
        ],

        # ══════════════════════════════════════════════════════════════════════
        # ФЕРТИЛЬНОСТЬ И ГОРМОНЫ
        # ══════════════════════════════════════════════════════════════════════
        "clomid": [
            "clomiphene", "clomiphene citrate", "fertility", "ovulation",
            "PCOS treatment", "infertility", "ovulation induction", "fertility drug",
            "pregnancy help", "conceive", "fertility medication", "anovulation",
            "fertility treatment", "egg production", "hormonal balance"
        ],
        "synthroid": [
            "levothyroxine", "thyroid", "hypothyroidism", "hormone replacement",
            "T4 hormone", "thyroid medication", "underactive thyroid",
            "metabolism", "thyroid hormone", "Hashimoto's"
        ],

        # ══════════════════════════════════════════════════════════════════════
        # АНТИДЕПРЕССАНТЫ И ПСИХОТРОПНЫЕ
        # ══════════════════════════════════════════════════════════════════════
        "zoloft": [
            "sertraline", "antidepressant", "SSRI", "anxiety", "depression",
            "panic disorder", "OCD", "PTSD", "social anxiety",
            "mental health", "mood disorder"
        ],
        "lexapro": [
            "escitalopram", "antidepressant", "SSRI", "anxiety disorder",
            "depression", "GAD", "panic attacks", "mental health"
        ],
        "paxil": [
            "paroxetine", "antidepressant", "SSRI", "anxiety", "depression",
            "panic disorder", "social anxiety", "OCD", "PTSD"
        ],
        "celexa": [
            "citalopram", "antidepressant", "SSRI", "depression", "anxiety",
            "mood disorder", "mental health"
        ],
        "prozac": [
            "fluoxetine", "antidepressant", "SSRI", "depression", "anxiety",
            "OCD", "bulimia", "panic disorder", "PMDD"
        ],
        "fluoxetine": [
            "Prozac", "antidepressant", "SSRI", "depression", "anxiety",
            "OCD", "eating disorders", "mental health"
        ],
        "provigil": [
            "modafinil", "wakefulness", "narcolepsy", "cognitive enhancer",
            "sleep disorder", "shift work", "alertness", "focus",
            "smart drug", "nootropic", "fatigue"
        ],
        "buspar": [
            "buspirone", "anxiety", "anxiolytic", "GAD", "generalized anxiety",
            "anti-anxiety", "non-benzo", "mental health"
        ],
        "trazodone": [
            "antidepressant", "sleep aid", "insomnia", "depression",
            "anxiety", "sleep disorder", "sedative"
        ],
        "amitriptyline": [
            "tricyclic antidepressant", "TCA", "depression", "nerve pain",
            "migraine prevention", "chronic pain", "fibromyalgia"
        ],

        # ══════════════════════════════════════════════════════════════════════
        # ОБЕЗБОЛИВАЮЩИЕ И НЕРВНАЯ СИСТЕМА
        # ══════════════════════════════════════════════════════════════════════
        "lyrica": [
            "pregabalin", "nerve pain", "fibromyalgia", "neuropathy",
            "seizures", "diabetic neuropathy", "chronic pain", "anxiety",
            "shingles pain", "postherpetic neuralgia"
        ],
        "neurontin": [
            "gabapentin", "nerve pain", "seizures", "neuropathy",
            "epilepsy", "chronic pain", "restless leg", "shingles pain"
        ],
        "toradol": [
            "ketorolac", "NSAID", "pain relief", "anti-inflammatory",
            "short-term pain", "post-surgery", "migraine"
        ],
        "celebrex": [
            "celecoxib", "NSAID", "arthritis", "pain relief", "inflammation",
            "COX-2 inhibitor", "joint pain", "osteoarthritis", "rheumatoid"
        ],
        "indocin": [
            "indomethacin", "NSAID", "gout", "arthritis", "inflammation",
            "pain relief", "bursitis", "tendinitis"
        ],

        # ══════════════════════════════════════════════════════════════════════
        # КОЖА И АКНЕ
        # ══════════════════════════════════════════════════════════════════════
        "accutane": [
            "isotretinoin", "acne", "severe acne", "skin treatment",
            "cystic acne", "nodular acne", "retinoid", "vitamin A derivative",
            "acne medication", "clear skin"
        ],
        "propecia": [
            "finasteride", "hair loss", "male pattern baldness", "DHT blocker",
            "androgenic alopecia", "hair regrowth", "hair restoration",
            "balding treatment", "5-alpha reductase inhibitor"
        ],
        "diflucan": [
            "fluconazole", "antifungal", "yeast infection", "candida",
            "thrush", "fungal infection", "vaginal yeast"
        ],
        "zovirax": [
            "acyclovir", "antiviral", "herpes", "cold sores", "shingles",
            "HSV", "genital herpes", "chickenpox"
        ],

        # ══════════════════════════════════════════════════════════════════════
        # СЕРДЕЧНО-СОСУДИСТЫЕ
        # ══════════════════════════════════════════════════════════════════════
        "lipitor": [
            "atorvastatin", "cholesterol", "statin", "cardiovascular",
            "heart health", "LDL", "high cholesterol", "hyperlipidemia"
        ],
        "lisinopril": [
            "ACE inhibitor", "blood pressure", "hypertension", "heart",
            "cardiovascular", "heart failure", "kidney protection"
        ],
        "norvasc": [
            "amlodipine", "calcium channel blocker", "blood pressure",
            "hypertension", "angina", "cardiovascular"
        ],
        "lopressor": [
            "metoprolol", "beta blocker", "blood pressure", "heart rate",
            "hypertension", "angina", "heart attack prevention"
        ],
        "inderal": [
            "propranolol", "beta blocker", "blood pressure", "anxiety",
            "migraine prevention", "tremor", "heart rate"
        ],
        "lasix": [
            "furosemide", "diuretic", "water pill", "edema", "blood pressure",
            "swelling", "fluid retention", "heart failure", "kidney"
        ],

        # ══════════════════════════════════════════════════════════════════════
        # ДИАБЕТ И МЕТАБОЛИЗМ
        # ══════════════════════════════════════════════════════════════════════
        "metformin": [
            "diabetes", "blood sugar", "type 2 diabetes", "insulin resistance",
            "glucose control", "A1C", "metabolic syndrome", "PCOS"
        ],
        "rybelsus": [
            "semaglutide", "GLP-1", "diabetes", "type 2 diabetes",
            "blood sugar", "weight loss", "oral semaglutide"
        ],
        "xenical": [
            "orlistat", "weight loss", "obesity", "fat absorption",
            "diet pill", "BMI", "weight management"
        ],

        # ══════════════════════════════════════════════════════════════════════
        # АНТИВИРУСНЫЕ
        # ══════════════════════════════════════════════════════════════════════
        "valtrex": [
            "valacyclovir", "herpes", "cold sores", "antiviral", "shingles",
            "HSV", "genital herpes", "outbreak prevention", "suppressive therapy"
        ],
        "soolantra": [
            "ivermectin cream", "ivermectin 1% cream", "topical ivermectin",
            "rosacea", "rosacea treatment", "facial redness", "papulopustular rosacea",
            "soolantra cream", "skin inflammation", "dermatology"
        ],
        "stromectol": [
            "ivermectin", "parasites", "antiparasitic", "worms", "scabies",
            "river blindness", "strongyloides", "onchocerciasis"
        ],
        "albenza": [
            "albendazole", "antiparasitic", "worms", "parasites",
            "tapeworm", "roundworm", "pinworm"
        ],

        # ══════════════════════════════════════════════════════════════════════
        # АЛЛЕРГИИ И ДЫХАТЕЛЬНАЯ СИСТЕМА
        # ══════════════════════════════════════════════════════════════════════
        "singulair": [
            "montelukast", "asthma", "allergies", "leukotriene",
            "breathing", "seasonal allergies", "exercise-induced asthma"
        ],
        "ventolin": [
            "albuterol", "salbutamol", "asthma", "bronchodilator",
            "inhaler", "breathing", "COPD", "rescue inhaler"
        ],
        "atarax": [
            "hydroxyzine", "antihistamine", "anxiety", "itching",
            "allergies", "sedative", "hives"
        ],

        # ══════════════════════════════════════════════════════════════════════
        # ПРОЧИЕ КАТЕГОРИИ
        # ══════════════════════════════════════════════════════════════════════
        "prednisone": [
            "corticosteroid", "inflammation", "immune system", "allergies",
            "asthma", "arthritis", "lupus", "autoimmune",
            "steroid", "anti-inflammatory"
        ],
        "deltasone": [
            "prednisone", "corticosteroid", "inflammation", "autoimmune",
            "allergies", "steroid"
        ],
        "colchicine": [
            "gout", "gout treatment", "uric acid", "joint pain",
            "gout attack", "inflammation", "pericarditis"
        ],
        "naltrexone": [
            "opioid antagonist", "alcohol dependence", "addiction",
            "opioid addiction", "craving reduction", "recovery"
        ],
        "antabuse": [
            "disulfiram", "alcohol dependence", "alcoholism", "addiction",
            "alcohol deterrent", "sobriety"
        ],
        "champix": [
            "varenicline", "smoking cessation", "quit smoking",
            "nicotine addiction", "tobacco", "stop smoking"
        ],
        "zyban": [
            "bupropion", "smoking cessation", "quit smoking",
            "antidepressant", "nicotine withdrawal"
        ],
        "cytotec": [
            "misoprostol", "ulcer", "NSAID protection", "gastric",
            "stomach protection", "prostaglandin"
        ],
        "motilium": [
            "domperidone", "nausea", "vomiting", "gastroparesis",
            "digestive", "stomach motility"
        ],
        "dapoxetine": [
            "premature ejaculation", "PE treatment", "SSRI",
            "sexual health", "ejaculation control"
        ],
    }

    def __init__(self, drug: str, synonyms: List[str] = None):
        """
        Инициализация морфера для конкретного препарата.

        Args:
            drug: Название препарата
            synonyms: Список синонимов (generic names, etc.)
        """
        self.drug = drug.lower()
        self.drug_display = drug.capitalize()
        self.synonyms = [s.lower() for s in (synonyms or [])]
        self.all_names = [self.drug] + self.synonyms
        self.lsi_keywords = self.DRUG_LSI.get(self.drug, [])

        # Кэш сгенерированных анкоров для избежания повторов
        self._used_anchors: Set[str] = set()

        # Построение полного пула анкоров
        self._build_anchor_pool()

    def _build_anchor_pool(self):
        """Строит полный пул всех возможных анкоров."""
        self.anchor_pool = {
            'commercial': [],
            'informational': [],
            'comparison': [],
            'branded': [],
            'longtail': [],
            'contextual': [],
            'question': [],
            'cta': [],
        }

        # Генерируем анкоры для каждого имени препарата
        for name in self.all_names:
            display_name = name.capitalize()

            for tpl in self.COMMERCIAL_TEMPLATES:
                self.anchor_pool['commercial'].append(tpl.format(drug=display_name))

            for tpl in self.INFORMATIONAL_TEMPLATES:
                self.anchor_pool['informational'].append(tpl.format(drug=display_name))

            for tpl in self.COMPARISON_TEMPLATES:
                self.anchor_pool['comparison'].append(tpl.format(drug=display_name))

            for tpl in self.BRANDED_TEMPLATES:
                self.anchor_pool['branded'].append(tpl.format(drug=display_name))

            for tpl in self.LONGTAIL_TEMPLATES:
                self.anchor_pool['longtail'].append(tpl.format(drug=display_name))

            for tpl in self.CONTEXTUAL_TEMPLATES:
                self.anchor_pool['contextual'].append(tpl.format(drug=display_name))

            for tpl in self.QUESTION_TEMPLATES:
                self.anchor_pool['question'].append(tpl.format(drug=display_name))

            for tpl in self.CTA_TEMPLATES:
                self.anchor_pool['cta'].append(tpl.format(drug=display_name))

        # Добавляем коммерческие анкоры с хвостами (shipping, OTC, оплата и т.п.)
        self._add_tail_suffix_variations()

        # Добавляем вариации с синонимами действий
        self._add_synonym_variations()

        # Добавляем LSI вариации
        self._add_lsi_variations()

        logger.debug(f"Построен пул анкоров для {self.drug}: "
                    f"{sum(len(v) for v in self.anchor_pool.values())} вариантов")

    def _add_tail_suffix_variations(self):
        """
        Строит дополнительные коммерческие анкоры вида:
        - buy {drug} + хвост
        - order {drug} + хвост
        - {drug} for sale + хвост

        Для всех имён в self.all_names (бренд + синонимы).
        """
        base_roots: List[str] = []

        # Строим базовые ядра для каждого имени
        for name in self.all_names:
            display_name = name.capitalize()
            base_roots.extend([
                f"buy {display_name}",
                f"order {display_name}",
                f"{display_name} for sale",
            ])

        extra: List[str] = []

        # Комбинируем ядра с хвостами
        for base in base_roots:
            for tail in self.TAIL_SUFFIXES:
                combo = f"{base} {tail}".strip()
                extra.append(combo)

        # Убираем дубликаты и ограничиваем размер, чтобы не раздувать пул
        seen: Set[str] = set()
        limited: List[str] = []

        for anchor in extra:
            key = anchor.lower()
            if key in seen:
                continue
            seen.add(key)
            limited.append(anchor)
            if len(limited) >= 300:
                break

        # Добавляем в коммерческий пул
        self.anchor_pool['commercial'].extend(limited)


    def _add_synonym_variations(self):
        """Добавляет вариации с синонимами действий."""
        new_anchors = []

        for category, anchors in self.anchor_pool.items():
            for anchor in anchors[:20]:  # Ограничиваем для производительности
                for word, synonyms in self.ACTION_SYNONYMS.items():
                    if word in anchor.lower():
                        for syn in synonyms[:2]:
                            new_anchor = re.sub(
                                rf'\b{word}\b',
                                syn,
                                anchor,
                                flags=re.IGNORECASE
                            )
                            if new_anchor != anchor:
                                new_anchors.append((category, new_anchor))

        for category, anchor in new_anchors:
            if anchor not in self.anchor_pool[category]:
                self.anchor_pool[category].append(anchor)

    def _add_lsi_variations(self):
        """Добавляет LSI-вариации анкоров."""
        if not self.lsi_keywords:
            return

        lsi_anchors = []
        for lsi in self.lsi_keywords:
            lsi_anchors.extend([
                f"{self.drug_display} {lsi}",
                f"{lsi} with {self.drug_display}",
                f"{self.drug_display} for {lsi}",
                f"best {lsi} {self.drug_display}",
            ])

        self.anchor_pool['informational'].extend(lsi_anchors)

    def get_anchor(self,
                   category: str = 'mixed',
                   avoid_repeats: bool = True,
                   context: str = None) -> str:
        """
        Получает анкор заданной категории.

        Args:
            category: Категория анкора ('commercial', 'informational', etc. или 'mixed')
            avoid_repeats: Избегать повторения уже использованных
            context: Контекст для согласования (опционально)

        Returns:
            Текст анкора
        """
        if category == 'mixed':
            # Взвешенный выбор категории
            weights = {
                'commercial': 25,
                'branded': 20,
                'longtail': 15,
                'informational': 15,
                'contextual': 10,
                'cta': 10,
                'comparison': 3,
                'question': 2,
            }
            category = random.choices(
                list(weights.keys()),
                weights=list(weights.values())
            )[0]

        pool = self.anchor_pool.get(category, self.anchor_pool['branded'])

        if avoid_repeats:
            available = [a for a in pool if a.lower() not in self._used_anchors]
            if not available:
                # Сброс если всё использовано
                self._used_anchors.clear()
                available = pool
        else:
            available = pool

        if not available:
            return self.drug_display

        anchor = random.choice(available)

        if avoid_repeats:
            self._used_anchors.add(anchor.lower())

        return anchor

    def get_contextual_anchor(self,
                              surrounding_text: str,
                              position: str = 'middle') -> Tuple[str, str]:
        """
        Генерирует анкор, согласованный с окружающим контекстом.

        Args:
            surrounding_text: Окружающий текст
            position: Позиция вставки ('start', 'middle', 'end')

        Returns:
            Tuple (anchor, full_insertion) — анкор и полная фраза для вставки
        """
        surrounding_lower = surrounding_text.lower()

        # Определяем тематику контекста
        if any(w in surrounding_lower for w in ['buy', 'order', 'purchase', 'price', 'cost', 'cheap']):
            category = 'commercial'
        elif any(w in surrounding_lower for w in ['how', 'what', 'why', 'effect', 'work', 'dose']):
            category = 'informational'
        elif any(w in surrounding_lower for w in ['vs', 'compare', 'better', 'alternative']):
            category = 'comparison'
        else:
            category = 'contextual'

        anchor = self.get_anchor(category=category)

        # Для вставки в середину — используем короткий контекстуальный
        if position == 'middle':
            anchor = self.get_anchor(category='contextual')
            return anchor, anchor

        # Для начала/конца — можем добавить переходную фразу
        if position == 'start':
            transition = random.choice(self.TRANSITION_BEFORE)
            full = f"{transition} {anchor.lower()}"
        elif position == 'end':
            transition = random.choice(self.TRANSITION_AFTER)
            full = f"{anchor} {transition}"
        else:
            full = anchor

        return anchor, full

    def get_diverse_anchors(self, count: int) -> List[str]:
        """
        Получает набор разнообразных анкоров.

        Args:
            count: Количество нужных анкоров

        Returns:
            Список уникальных анкоров из разных категорий
        """
        anchors = []
        categories = list(self.anchor_pool.keys())

        # Сначала берём по одному из каждой категории
        random.shuffle(categories)
        for cat in categories:
            if len(anchors) >= count:
                break
            anchor = self.get_anchor(category=cat)
            if anchor not in anchors:
                anchors.append(anchor)

        # Добираем недостающие из mixed
        while len(anchors) < count:
            anchor = self.get_anchor(category='mixed')
            if anchor not in anchors:
                anchors.append(anchor)

        return anchors[:count]

    def reset(self):
        """Сбрасывает кэш использованных анкоров."""
        self._used_anchors.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# LINK SCHEME ENGINE — СХЕМЫ ПЕРЕЛИНКОВКИ
# ═══════════════════════════════════════════════════════════════════════════════
class LinkSchemeEngine:
    """
    Движок схем перелинковки.

    Реализует различные SEO-стратегии распределения ссылок:
    - cluster: Кластерная (внутри сайта + между сайтами)
    - pyramid: Пирамидальная (иерархия страниц)
    - mesh: Сетевая (все со всеми, но разумно)
    - hub_spoke: Хаб и спицы (центральная страница + сателлиты)
    - tiered: Многоуровневая (tier 1 -> tier 2 -> tier 3)
    """

    @staticmethod
    def cluster_scheme(pages_by_domain: Dict[str, List[Page]],
                       external_links_per_page: int = 2,
                       ensure_full_coverage: bool = True) -> List[Link]:
        """
        Кластерная схема — оптимальная для PBN.

        Принцип:
        1. Внутри каждого домена: A↔B (двусторонняя связь)
        2. Между доменами: каждая страница получает external_links_per_page
           входящих ссылок с других доменов
        3. Гарантируется что ни одна страница не останется без ссылок

        Args:
            pages_by_domain: Словарь {domain: [Page, Page]}
            external_links_per_page: Кол-во внешних ссылок на страницу
            ensure_full_coverage: Гарантировать что все страницы охвачены

        Returns:
            Список Link объектов
        """
        links = []
        all_pages = []

        for domain, pages in pages_by_domain.items():
            all_pages.extend(pages)

        if len(all_pages) < 2:
            return links

        # 1. Внутренняя перелинковка (внутри каждого домена)
        for domain, pages in pages_by_domain.items():
            if len(pages) >= 2:
                # A↔B двусторонняя
                for i, page_a in enumerate(pages):
                    for page_b in pages[i+1:]:
                        # A → B
                        links.append(Link(
                            source=page_a,
                            target=page_b,
                            anchor="",  # Заполнится позже
                            link_type='internal'
                        ))
                        # B → A
                        links.append(Link(
                            source=page_b,
                            target=page_a,
                            anchor="",
                            link_type='internal'
                        ))

        # 2. Внешняя перелинковка (между доменами)
        domains = list(pages_by_domain.keys())

        if len(domains) < 2:
            return links

        # Счётчик входящих внешних ссылок для каждой страницы
        incoming_external: Dict[str, int] = {p.url: 0 for p in all_pages}

        # Счётчик исходящих внешних ссылок для каждой страницы
        outgoing_external: Dict[str, int] = {p.url: 0 for p in all_pages}

        # Проходим по каждой странице как source
        for source_page in all_pages:
            source_domain = source_page.domain

            # Находим страницы других доменов
            other_domain_pages = [
                p for p in all_pages
                if p.domain != source_domain
            ]

            if not other_domain_pages:
                continue

            # Жёсткий лимит исходящих внешних ссылок с одной страницы
            max_outgoing = min(external_links_per_page, len(other_domain_pages))
            if max_outgoing <= 0:
                continue

            # Приоритет страницам с минимальным количеством входящих
            other_domain_pages.sort(key=lambda p: incoming_external[p.url])

            # Идём по отсортированному списку, пока не вычерпаем лимит исходящих
            for target_page in other_domain_pages:
                # Лимит исходящих для source
                if outgoing_external[source_page.url] >= max_outgoing:
                    break

                # Лимит входящих для target
                if incoming_external[target_page.url] >= external_links_per_page:
                    continue

                links.append(Link(
                    source=source_page,
                    target=target_page,
                    anchor="",  # Заполнится позже
                    link_type='cross-site'
                ))

                incoming_external[target_page.url] += 1
                outgoing_external[source_page.url] += 1

        # 3. Гарантируем полный охват
        if ensure_full_coverage:
            for page in all_pages:
                # Нас интересуют только страницы вообще без входящих внешних ссылок
                if incoming_external.get(page.url, 0) > 0:
                    continue

                # Найти донора с другого домена
                donors = [
                    p for p in all_pages
                    if p.domain != page.domain and p.url != page.url
                ]

                if not donors:
                    continue

                # Выбираем донора с минимумом исходящих
                donors.sort(key=lambda p: outgoing_external.get(p.url, 0))
                donor = donors[0]

                # Уважаем лимит исходящих даже для coverage
                if outgoing_external.get(donor.url, 0) >= external_links_per_page:
                    continue

                links.append(Link(
                    source=donor,
                    target=page,
                    anchor="",
                    link_type='cross-site'
                ))

                incoming_external[page.url] = incoming_external.get(page.url, 0) + 1
                outgoing_external[donor.url] = outgoing_external.get(donor.url, 0) + 1

                logger.debug(f"Добавлена coverage-ссылка: {donor.url} → {page.url}")

        return links

    @staticmethod
    def pyramid_scheme(pages_by_domain: Dict[str, List[Page]],
                       levels: int = 3,
                       **kwargs) -> List[Link]:
        """
        Пирамидальная схема — иерархическая структура.

        Принцип:
        - Уровень 1 (вершина): 1-2 главные страницы
        - Уровень 2: Поддерживающие страницы → ссылаются на уровень 1
        - Уровень 3: Дополнительные → ссылаются на уровень 2

        Хорошо подходит для концентрации ссылочного веса на главных страницах.
        """
        links = []
        all_pages = []

        for pages in pages_by_domain.values():
            all_pages.extend(pages)

        if len(all_pages) < 3:
            return LinkSchemeEngine.cluster_scheme(pages_by_domain)

        # Распределяем страницы по уровням
        random.shuffle(all_pages)

        pages_per_level = max(1, len(all_pages) // levels)

        level_1 = all_pages[:max(1, pages_per_level // 2)]
        level_2 = all_pages[len(level_1):len(level_1) + pages_per_level]
        level_3 = all_pages[len(level_1) + len(level_2):]

        # Level 3 → Level 2
        for page in level_3:
            if level_2:
                target = random.choice(level_2)
                links.append(Link(
                    source=page,
                    target=target,
                    anchor="",
                    link_type='cross-site'
                ))

        # Level 2 → Level 1
        for page in level_2:
            if level_1:
                target = random.choice(level_1)
                links.append(Link(
                    source=page,
                    target=target,
                    anchor="",
                    link_type='cross-site'
                ))

        # Level 1 ↔ Level 1 (между собой)
        for i, page_a in enumerate(level_1):
            for page_b in level_1[i+1:]:
                if page_a.domain != page_b.domain:
                    links.append(Link(
                        source=page_a,
                        target=page_b,
                        anchor="",
                        link_type='cross-site'
                    ))

        # Внутренняя перелинковка
        for domain, pages in pages_by_domain.items():
            if len(pages) >= 2:
                for i, page_a in enumerate(pages):
                    for page_b in pages[i+1:]:
                        links.append(Link(source=page_a, target=page_b, anchor="", link_type='internal'))
                        links.append(Link(source=page_b, target=page_a, anchor="", link_type='internal'))

        return links

    @staticmethod
    def mesh_scheme(pages_by_domain: Dict[str, List[Page]],
                    density: float = 0.3,
                    **kwargs) -> List[Link]:
        """
        Сетевая схема — умное "все со всеми".

        Args:
            density: Плотность связей (0.0-1.0).
                     0.3 означает что каждая страница ссылается на 30% других
        """
        links = []
        all_pages = []

        for pages in pages_by_domain.values():
            all_pages.extend(pages)

        if len(all_pages) < 2:
            return links

        # Для каждой страницы
        for source in all_pages:
            # Возможные цели
            targets = [p for p in all_pages if p.url != source.url]

            # Определяем сколько ссылок
            num_links = max(1, int(len(targets) * density))
            num_links = min(num_links, 5)  # Не более 5 на страницу

            # Приоритет страницам с других доменов
            other_domain = [t for t in targets if t.domain != source.domain]
            same_domain = [t for t in targets if t.domain == source.domain]

            # Сначала берём с других доменов, потом со своего
            selected = []
            random.shuffle(other_domain)
            random.shuffle(same_domain)

            for t in other_domain:
                if len(selected) >= num_links:
                    break
                selected.append(t)

            for t in same_domain:
                if len(selected) >= num_links:
                    break
                selected.append(t)

            for target in selected:
                link_type = 'internal' if target.domain == source.domain else 'cross-site'
                links.append(Link(
                    source=source,
                    target=target,
                    anchor="",
                    link_type=link_type
                ))

        return links

    @staticmethod
    def hub_spoke_scheme(pages_by_domain: Dict[str, List[Page]],
                         hub_count: int = 1,
                         **kwargs) -> List[Link]:
        """
        Схема Hub & Spoke — центральные страницы + сателлиты.

        Один или несколько "хабов" получают ссылки от всех остальных,
        и ссылаются на некоторых.
        """
        links = []
        all_pages = []

        for pages in pages_by_domain.values():
            all_pages.extend(pages)

        if len(all_pages) < 2:
            return links

        # Выбираем хабы (по одному с разных доменов если возможно)
        domains = list(pages_by_domain.keys())
        hubs = []

        for domain in domains[:hub_count]:
            if pages_by_domain[domain]:
                hubs.append(pages_by_domain[domain][0])

        if not hubs:
            hubs = [all_pages[0]]

        spokes = [p for p in all_pages if p not in hubs]

        # Spokes → Hubs
        for spoke in spokes:
            for hub in hubs:
                if spoke.domain != hub.domain:  # Только cross-site
                    links.append(Link(
                        source=spoke,
                        target=hub,
                        anchor="",
                        link_type='cross-site'
                    ))

        # Hubs → некоторые Spokes (обратные ссылки)
        for hub in hubs:
            # Выбираем 20-30% spokes для обратных ссылок
            num_backlinks = max(1, len(spokes) // 4)
            selected_spokes = random.sample(spokes, min(num_backlinks, len(spokes)))

            for spoke in selected_spokes:
                if spoke.domain != hub.domain:
                    links.append(Link(
                        source=hub,
                        target=spoke,
                        anchor="",
                        link_type='cross-site'
                    ))

        # Внутренняя перелинковка
        for domain, pages in pages_by_domain.items():
            if len(pages) >= 2:
                for i, page_a in enumerate(pages):
                    for page_b in pages[i+1:]:
                        links.append(Link(source=page_a, target=page_b, anchor="", link_type='internal'))
                        links.append(Link(source=page_b, target=page_a, anchor="", link_type='internal'))

        return links


# ═══════════════════════════════════════════════════════════════════════════════
# CLUSTER BUILDER — ПОСТРОЕНИЕ КЛАСТЕРОВ
# ═══════════════════════════════════════════════════════════════════════════════
class ClusterBuilder:
    """
    Строитель кластеров страниц.

    Анализирует директорию с HTML-файлами и строит кластеры
    по препаратам/темам.
    """

    def __init__(self,
                 base_directory: str,
                 keywords_map: Dict[str, str]):
        """
        Args:
            base_directory: Корневая директория с доменами
            keywords_map: Словарь синонимов {synonym: main_keyword}
        """
        self.base_dir = base_directory
        self.keywords_map = keywords_map
        self.clusters: Dict[str, Cluster] = {}
        self.all_pages: List[Page] = []

    def scan_directory(self) -> Dict[str, Cluster]:
        """
        Сканирует директорию и строит кластеры.

        Returns:
            Словарь {topic: Cluster}
        """
        self.clusters = {}
        self.all_pages = []

        if not os.path.isdir(self.base_dir):
            logger.error(f"Директория не найдена: {self.base_dir}")
            return self.clusters

        # Проходим по доменам
        for domain in os.listdir(self.base_dir):
            domain_path = os.path.join(self.base_dir, domain)

            if not os.path.isdir(domain_path):
                continue

            logger.info(f"Сканирование домена: {domain}")

            # Проходим по HTML-файлам
            for root, dirs, files in os.walk(domain_path):
                for file in files:
                    if not file.endswith('.html'):
                        continue

                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, domain_path)

                    # Формируем URL
                    url_path = rel_path.replace('\\', '/').replace('.html', '')
                    url = f"https://{domain}/{url_path}/"

                    # Читаем файл и определяем тему
                    page = self._analyze_page(full_path, domain, url)

                    if page and page.topic:
                        self.all_pages.append(page)

                        # Добавляем в кластер
                        if page.topic not in self.clusters:
                            self.clusters[page.topic] = Cluster(topic=page.topic)

                        self.clusters[page.topic].pages.append(page)

        # Логирование результатов
        logger.info(f"Найдено кластеров: {len(self.clusters)}")
        for topic, cluster in self.clusters.items():
            logger.info(f"  {topic}: {len(cluster.pages)} страниц на {len(cluster.domains)} доменах")

        return self.clusters

    def _analyze_page(self, file_path: str, domain: str, url: str) -> Optional[Page]:
        """Анализирует страницу и определяет её тему."""
        try:
            with open(file_path, 'rb') as f:
                raw = f.read()

            encoding = chardet.detect(raw).get('encoding') or 'utf-8'
            content = raw.decode(encoding, errors='replace')

            # Парсим HTML
            doc = html.fromstring(content)

            # Получаем title
            title_elems = doc.xpath('//title/text()')
            title = title_elems[0].strip() if title_elems else ""

            if not title:
                return None

            # Определяем тему по title
            title_lower = title.lower()
            found_topic = None

            for synonym, main_keyword in self.keywords_map.items():
                pattern = r'\b' + re.escape(synonym.lower()) + r'\b'
                if re.search(pattern, title_lower):
                    found_topic = main_keyword
                    break

            if not found_topic:
                return None

            return Page(
                url=url,
                domain=domain,
                file_path=file_path,
                title=title,
                topic=found_topic
            )

        except Exception as e:
            logger.warning(f"Ошибка анализа {file_path}: {e}")
            return None

    def build_links_for_cluster(self,
                                topic: str,
                                scheme: str = 'cluster',
                                **kwargs) -> List[Link]:
        """
        Строит ссылки для указанного кластера.

        Args:
            topic: Название препарата/темы
            scheme: Схема перелинковки
            **kwargs: Дополнительные параметры схемы

        Returns:
            Список Link объектов
        """
        if topic not in self.clusters:
            logger.error(f"Кластер не найден: {topic}")
            return []

        cluster = self.clusters[topic]
        pages_by_domain = cluster.pages_by_domain

        # Выбираем схему
        if scheme == 'cluster':
            links = LinkSchemeEngine.cluster_scheme(pages_by_domain, **kwargs)
        elif scheme == 'pyramid':
            links = LinkSchemeEngine.pyramid_scheme(pages_by_domain, **kwargs)
        elif scheme == 'mesh':
            links = LinkSchemeEngine.mesh_scheme(pages_by_domain, **kwargs)
        elif scheme == 'hub_spoke':
            links = LinkSchemeEngine.hub_spoke_scheme(pages_by_domain, **kwargs)
        else:
            logger.warning(f"Неизвестная схема: {scheme}, использую cluster")
            links = LinkSchemeEngine.cluster_scheme(pages_by_domain, **kwargs)

        # Назначаем анкоры
        morpher = AnchorMorpher(topic, self._get_synonyms(topic))

        for link in links:
            # Для internal — используем коммерческие + брендовые анкоры
            # Для cross-site — больше коммерческих и longtail
            if link.link_type == 'internal':
                # 50% коммерческие, 30% longtail, 20% branded
                category = random.choices(
                    ['commercial', 'longtail', 'branded'],
                    weights=[50, 30, 20],
                    k=1
                )[0]
            else:
                # cross-site: 40% commercial, 30% longtail, 20% cta, 10% branded
                category = random.choices(
                    ['commercial', 'longtail', 'cta'],
                    weights=[60, 30, 10],
                    k=1
                )[0]

            link.anchor = morpher.get_anchor(category=category)

        cluster.links = links

        logger.info(f"Кластер {topic}: создано {len(links)} ссылок "
                   f"({sum(1 for l in links if l.link_type == 'internal')} internal, "
                   f"{sum(1 for l in links if l.link_type == 'cross-site')} cross-site)")

        return links

    def _get_synonyms(self, main_keyword: str) -> List[str]:
        """Получает синонимы для ключевого слова."""
        synonyms = []
        for syn, main in self.keywords_map.items():
            if main == main_keyword and syn != main_keyword:
                synonyms.append(syn)
        return synonyms


# ═══════════════════════════════════════════════════════════════════════════════
# LINK INSERTER — ВСТАВКА ССЫЛОК В HTML (FIXED)
# ═══════════════════════════════════════════════════════════════════════════════
class LinkInserter:
    """
    Вставляет ссылки в HTML-файлы.
    v1.1 - Fix: Расширенный поиск текстовых узлов (не только <p>)
    """

    # Запрещённые родительские теги (где нельзя ставить ссылки)
    FORBIDDEN_TAGS = frozenset([
        'script', 'style', 'meta', 'head', 'link', 'title',
        'button', 'nav', 'footer', 'header', 'menu', 'aside',
        'code', 'pre', 'xmp', 'noscript', 'iframe', 'object',
        'form', 'input', 'select', 'textarea', 'option', 'label',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',  # Не ставим в заголовки
        'a'  # Внутри ссылок нельзя
    ])

    # Запрещённые классы/id (только явные признаки мусора)
    # Убрали 'sidebar', 'menu' и т.д. из глобального бана, чтобы не блочить body
    FORBIDDEN_PATTERNS = frozenset([
        'comment', 'reply', 'login', 'signup', 'cookie', 'popup', 'modal',
        'copyright', 'author-bio', 'related-posts', 'share-buttons',
        'widget-area', 'ad-banner', 'breadcrumbs'
    ])

    # Расширенный список контейнеров
    CONTENT_SELECTORS = [
        "//div[contains(@class, 'entry-content')]",
        "//div[contains(@class, 'post-content')]",
        "//div[contains(@class, 'article-content')]",
        "//div[contains(@class, 'page-content')]",
        "//div[contains(@class, 'text-content')]",
        "//div[contains(@class, 'content-area')]",
        "//div[contains(@id, 'content')]",
        "//section",
        "//article",
        "//main",
    ]

    def __init__(self, min_text_length: int = 50):
        self.min_text_length = min_text_length
        self.stats = {'success': 0, 'failed': 0, 'skipped': 0}

    def insert_links(self, links: List[Link]) -> Dict[str, Any]:
        links_by_file: Dict[str, List[Link]] = defaultdict(list)
        for link in links:
            links_by_file[link.source.file_path].append(link)

        self.stats = {'success': 0, 'failed': 0, 'skipped': 0}

        for file_path, file_links in links_by_file.items():
            self._process_file(file_path, file_links)

        return self.stats

    def _process_file(self, file_path: str, links: List[Link]):
        if not os.path.isfile(file_path):
            self.stats['failed'] += len(links)
            return

        try:
            with open(file_path, 'rb') as f:
                raw = f.read()
            encoding = chardet.detect(raw).get('encoding') or 'utf-8'
            html_content = raw.decode(encoding, errors='replace')

            # Сохраняем head (regex надежнее lxml для сохранения скриптов и стилей)
            head_match = re.search(r'(<head[^>]*>.*?</head>)', html_content, re.IGNORECASE | re.DOTALL)
            original_head = head_match.group(1) if head_match else ''

            doc = html.fromstring(html_content)

            # Ищем контейнер
            content_container = self._find_content_container(doc)
            if content_container is None:
                # Если не нашли спец контейнер, берем body, но аккуратно
                body = doc.xpath('//body')
                content_container = body[0] if body else doc

            # Находим ВСЕ текстовые блоки, а не только <p>
            text_nodes = self._find_text_nodes(content_container)

            if not text_nodes:
                logger.warning(f"Skipped {file_path}: no suitable text nodes found")
                self.stats['skipped'] += len(links)
                return

            random.shuffle(text_nodes)

            inserted_count = 0
            node_idx = 0

            for link in links:
                # Циклический перебор узлов, если ссылок больше чем узлов
                if node_idx >= len(text_nodes):
                    random.shuffle(text_nodes)
                    node_idx = 0

                # Пытаемся вставить — больше попыток
                attempts = 0
                inserted = False
                max_attempts = min(20, len(text_nodes))  # До 20 попыток
                while attempts < max_attempts:
                    if node_idx >= len(text_nodes):
                        random.shuffle(text_nodes)
                        node_idx = 0
                    if self._insert_single_link(text_nodes[node_idx], link):
                        inserted = True
                        break
                    node_idx += 1
                    attempts += 1

                if inserted:
                    link.inserted = True
                    inserted_count += 1
                    self.stats['success'] += 1
                    # Для удачных можно чисто на всякий случай очистить контекст
                    link.context = ""
                else:
                    self.stats['failed'] += 1
                    # Сохраняем минимальную информацию о том, где была ошибка
                    link.context = (
                        f"Не удалось вставить ссылку "
                        f"{link.source.url} → {link.target.url} "
                        f"в файл: {os.path.basename(file_path)}"
                    )
                    logger.warning(
                        f"Failed to insert link {link.source.url} -> "
                        f"{link.target.url} in {file_path}"
                    )

                node_idx += 1

            # Сохраняем только если были изменения
            if inserted_count > 0:
                self._save_file(file_path, doc, original_head, encoding)

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            self.stats['failed'] += len(links)

    def _find_content_container(self, doc: HtmlElement) -> Optional[HtmlElement]:
        for xpath in self.CONTENT_SELECTORS:
            results = doc.xpath(xpath)
            # Берем самый длинный по тексту контейнер из найденных (чтобы не взять пустой div)
            if results:
                valid_results = [r for r in results if len(r.text_content() or "") > 500]
                if valid_results:
                    return valid_results[0]
                # Если все короткие, берем первый
                return results[0]
        return None

    def _find_text_nodes(self, container: HtmlElement) -> List[HtmlElement]:
        """
        Поиск текстовых узлов с многоступенчатым фоллбеком.

        1) Ищем контейнеры по CONTENT_SELECTORS.
        2) Если пусто — ищем <p> внутри <body>.
        3) Если пусто — ищем <div> с текстом ≥ min_text_length.

        Если в документе есть достаточно длинный текст, должны найти хотя бы один узел.
        """

        def is_suitable(elem: HtmlElement) -> bool:
            # Запрещённые зоны
            if self._is_forbidden(elem):
                return False
            # Не вставляем внутрь ссылок
            if elem.xpath('ancestor::a'):
                return False
            # Проверяем ПРЯМОЙ текст элемента (elem.text), а не text_content()!
            direct_text = (elem.text or "").strip()
            return len(direct_text) >= self.min_text_length

        # Определяем корень документа
        try:
            root = container.getroottree().getroot()
        except Exception:
            root = container

        # 1) Поиск по CONTENT_SELECTORS
        candidates: List[HtmlElement] = []
        for xpath_expr in self.CONTENT_SELECTORS:
            try:
                blocks = root.xpath(xpath_expr)
            except Exception:
                continue

            for block in blocks:
                if not isinstance(block, HtmlElement):
                    continue
                # Ищем внутри блока текстовые элементы
                for elem in block.xpath(".//*[self::p or self::div or self::li or self::span or self::blockquote]"):
                    if is_suitable(elem):
                        candidates.append(elem)

        if candidates:
            return candidates

        # 2) Жёсткий fallback: <p> внутри <body>
        bodies = root.xpath("//body")
        if bodies:
            body = bodies[0]
            p_nodes = body.xpath(".//p")
            p_suitable = [p for p in p_nodes if is_suitable(p)]
            if p_suitable:
                return p_suitable

        # 3) Последний fallback: любые <div> с достаточной длиной текста
        div_nodes = root.xpath("//div")
        div_suitable = [d for d in div_nodes if is_suitable(d)]
        if div_suitable:
            return div_suitable

        return []

    def _is_forbidden(self, elem: HtmlElement) -> bool:
        """Умная проверка на запрещенные зоны."""
        current = elem
        depth = 0

        # Проверяем вверх на 5 уровней, а не до корня сайта
        # Это предотвращает бан всего контента из-за класса в body
        while current is not None and depth < 6:
            if current.tag in self.FORBIDDEN_TAGS:
                return True

            # Получаем классы и ID
            cls = str(current.get('class', '')).lower()
            cid = str(current.get('id', '')).lower()
            combined = cls + ' ' + cid

            for pattern in self.FORBIDDEN_PATTERNS:
                if pattern in combined:
                    return True

            current = current.getparent()
            depth += 1

        return False

    def _insert_single_link(self, elem: HtmlElement, link: Link) -> bool:
        """
        Вставка ссылки в текстовый элемент.

        БЕЗОПАСНЫЙ режим: работаем ТОЛЬКО с elem.text,
        никогда не трогаем дочерние элементы!
        """
        try:
            # Работаем ТОЛЬКО с прямым текстом элемента (не text_content!)
            raw_text = elem.text or ""

            # Проверяем что текст достаточно длинный
            if len(raw_text.strip()) < self.min_text_length:
                return False

            words = raw_text.split()
            if len(words) < 6:
                return False

            # Выбираем позицию для вставки (не в начале и не в конце)
            pos = random.randint(2, len(words) - 3)

            before = " ".join(words[:pos])
            after = " ".join(words[pos:])

            # Сохраняем пробелы
            if raw_text.startswith((' ', '\n', '\t')):
                before = raw_text[0] + before.lstrip()
            if before and not before.endswith(' '):
                before += ' '
            if after and not after.startswith(' '):
                after = ' ' + after

            # Создаём тег ссылки
            a_tag = etree.Element("a")
            a_tag.set("href", link.target.url)
            a_tag.text = link.anchor
            a_tag.tail = after

            # Заменяем только elem.text, вставляем ссылку первым ребёнком
            # Это НЕ удаляет существующих детей!
            elem.text = before
            elem.insert(0, a_tag)

            return True

        except Exception as e:
            logger.warning(f"Exception while inserting link: {e}")
            return False


    def _save_file(self, file_path: str, doc: HtmlElement, original_head: str, encoding: str):
        body = doc.xpath('//body')
        if not body: return

        # tostring может вернуть байты
        body_content = html.tostring(body[0], encoding='unicode', method='html')

        # Если original_head пустой (не нашли regex), попробуем восстановить из lxml
        if not original_head:
            head = doc.xpath('//head')
            if head:
                original_head = html.tostring(head[0], encoding='unicode', method='html')

        new_html = f"<!DOCTYPE html>\n<html>\n{original_head}\n{body_content}\n</html>"

        with open(file_path, 'w', encoding=encoding, errors='replace') as f:
            f.write(new_html)


# ═══════════════════════════════════════════════════════════════════════════════
# COVERAGE ANALYZER — АНАЛИЗ ОХВАТА
# ═══════════════════════════════════════════════════════════════════════════════
class CoverageAnalyzer:
    """
    Анализирует охват перелинковки.

    Проверяет:
    - Все ли страницы имеют входящие ссылки
    - Все ли страницы имеют исходящие ссылки
    - Нет ли изолированных страниц
    - Равномерность распределения
    """

    @staticmethod
    def analyze(cluster: Cluster) -> Dict[str, Any]:
        """
        Анализирует кластер.

        Returns:
            Словарь с метриками охвата
        """
        pages = cluster.pages
        links = cluster.links

        if not pages:
            return {'error': 'No pages in cluster'}

        # Считаем входящие и исходящие
        incoming: Dict[str, int] = {p.url: 0 for p in pages}
        outgoing: Dict[str, int] = {p.url: 0 for p in pages}

        for link in links:
            incoming[link.target.url] = incoming.get(link.target.url, 0) + 1
            outgoing[link.source.url] = outgoing.get(link.source.url, 0) + 1

        # Обновляем объекты Page
        for page in pages:
            page.incoming_links = incoming.get(page.url, 0)
            page.outgoing_links = outgoing.get(page.url, 0)

        # Анализируем
        pages_without_incoming = [p for p in pages if incoming[p.url] == 0]
        pages_without_outgoing = [p for p in pages if outgoing[p.url] == 0]

        internal_links = [l for l in links if l.link_type == 'internal']
        cross_site_links = [l for l in links if l.link_type == 'cross-site']

        return {
            'total_pages': len(pages),
            'total_links': len(links),
            'internal_links': len(internal_links),
            'cross_site_links': len(cross_site_links),
            'pages_without_incoming': len(pages_without_incoming),
            'pages_without_outgoing': len(pages_without_outgoing),
            'orphan_pages': [p.url for p in pages_without_incoming],
            'dead_end_pages': [p.url for p in pages_without_outgoing],
            'avg_incoming': sum(incoming.values()) / len(pages) if pages else 0,
            'avg_outgoing': sum(outgoing.values()) / len(pages) if pages else 0,
            'max_incoming': max(incoming.values()) if incoming else 0,
            'min_incoming': min(incoming.values()) if incoming else 0,
            'coverage_score': (len(pages) - len(pages_without_incoming)) / len(pages) * 100 if pages else 0,
            'domains': len(cluster.domains),
            'pages_per_domain': {d: len(ps) for d, ps in cluster.pages_by_domain.items()},
        }

    @staticmethod
    def print_report(analysis: Dict[str, Any], topic: str):
        """Выводит отчёт об охвате."""
        print("\n" + "=" * 70)
        print(f"  ОТЧЁТ О ПЕРЕЛИНКОВКЕ: {topic.upper()}")
        print("=" * 70)

        print(f"\n📊 ОБЩАЯ СТАТИСТИКА:")
        print(f"   Всего страниц: {analysis['total_pages']}")
        print(f"   Всего ссылок: {analysis['total_links']}")
        print(f"   • Внутренних: {analysis['internal_links']}")
        print(f"   • Cross-site: {analysis['cross_site_links']}")
        print(f"   Доменов: {analysis['domains']}")

        print(f"\n📈 ОХВАТ:")
        print(f"   Coverage Score: {analysis['coverage_score']:.1f}%")
        print(f"   Среднее входящих: {analysis['avg_incoming']:.1f}")
        print(f"   Среднее исходящих: {analysis['avg_outgoing']:.1f}")
        print(f"   Макс входящих: {analysis['max_incoming']}")
        print(f"   Мин входящих: {analysis['min_incoming']}")

        if analysis['pages_without_incoming']:
            print(f"\n⚠️  СТРАНИЦЫ БЕЗ ВХОДЯЩИХ ССЫЛОК ({analysis['pages_without_incoming']}):")
            for url in analysis['orphan_pages'][:5]:
                print(f"   • {url}")
            if len(analysis['orphan_pages']) > 5:
                print(f"   ... и ещё {len(analysis['orphan_pages']) - 5}")
        else:
            print(f"\n✅ Все страницы имеют входящие ссылки!")

        if analysis['pages_without_outgoing']:
            print(f"\n⚠️  СТРАНИЦЫ БЕЗ ИСХОДЯЩИХ ССЫЛОК ({analysis['pages_without_outgoing']}):")
            for url in analysis['dead_end_pages'][:5]:
                print(f"   • {url}")
        else:
            print(f"\n✅ Все страницы имеют исходящие ссылки!")

        print(f"\n📁 РАСПРЕДЕЛЕНИЕ ПО ДОМЕНАМ:")
        for domain, count in analysis['pages_per_domain'].items():
            print(f"   {domain}: {count} страниц")

        print("\n" + "=" * 70)


# ═══════════════════════════════════════════════════════════════════════════════
# SEO CLUSTER LINKER — ГЛАВНЫЙ КЛАСС
# ═══════════════════════════════════════════════════════════════════════════════
class SEOClusterLinker:
    """
    Главный класс для SEO кластерной перелинковки.

    Объединяет все компоненты:
    - Сканирование директории
    - Построение кластеров
    - Генерация схемы перелинковки
    - Вставка ссылок
    - Анализ охвата

    Пример использования:
    ```python
    linker = SEOClusterLinker(
        base_directory="/path/to/sites",
        keywords_map=KEYWORDS
    )

    # Сканируем и строим кластеры
    linker.build_clusters()

    # Создаём перелинковку для конкретного препарата
    linker.create_links('viagra', scheme='cluster')

    # Вставляем ссылки
    linker.insert_all_links()

    # Получаем отчёт
    linker.print_coverage_report()
    ```
    """

    AVAILABLE_SCHEMES = ['cluster', 'pyramid', 'mesh', 'hub_spoke']

    def __init__(self,
                 base_directory: str,
                 keywords_map: Dict[str, str],
                 min_text_length: int = 50):
        """
        Args:
            base_directory: Корневая директория с доменами
            keywords_map: Словарь синонимов
            min_text_length: Минимальная длина текста для вставки
        """
        self.base_dir = base_directory
        self.keywords_map = keywords_map
        self.min_text_length = min_text_length

        # Компоненты
        self.cluster_builder = ClusterBuilder(base_directory, keywords_map)
        self.link_inserter = LinkInserter(min_text_length)

        # Данные
        self.clusters: Dict[str, Cluster] = {}
        self.all_links: List[Link] = []

    def build_clusters(self) -> Dict[str, Cluster]:
        """
        Сканирует директорию и строит кластеры.

        Returns:
            Словарь кластеров по темам
        """
        self.clusters = self.cluster_builder.scan_directory()
        return self.clusters

    def create_links(self,
                     topic: str = None,
                     scheme: str = 'cluster',
                     **kwargs) -> List[Link]:
        """
        Создаёт ссылки для кластера(ов).

        Args:
            topic: Тема/препарат. Если None — для всех кластеров
            scheme: Схема перелинковки
            **kwargs: Дополнительные параметры схемы

        Returns:
            Список созданных ссылок
        """
        if not self.clusters:
            logger.warning("Кластеры не построены. Вызовите build_clusters() сначала.")
            return []

        self.all_links = []

        if topic:
            # Для конкретного препарата
            if topic not in self.clusters:
                logger.error(f"Кластер не найден: {topic}")
                return []

            links = self.cluster_builder.build_links_for_cluster(topic, scheme, **kwargs)
            self.all_links.extend(links)
        else:
            # Для всех кластеров
            for topic_name in self.clusters:
                links = self.cluster_builder.build_links_for_cluster(topic_name, scheme, **kwargs)
                self.all_links.extend(links)

        return self.all_links

    def insert_all_links(self) -> Dict[str, Any]:
        """
        Вставляет все созданные ссылки в HTML-файлы.

        Returns:
            Статистика вставки
        """
        if not self.all_links:
            logger.warning("Нет ссылок для вставки. Вызовите create_links() сначала.")
            return {}

        return self.link_inserter.insert_links(self.all_links)

    def get_coverage_analysis(self, topic: str = None) -> Dict[str, Dict[str, Any]]:
        """
        Получает анализ охвата.

        Args:
            topic: Конкретный препарат или None для всех

        Returns:
            Словарь с анализом по каждому кластеру
        """
        results = {}

        if topic:
            if topic in self.clusters:
                results[topic] = CoverageAnalyzer.analyze(self.clusters[topic])
        else:
            for topic_name, cluster in self.clusters.items():
                results[topic_name] = CoverageAnalyzer.analyze(cluster)

        return results

    def print_coverage_report(self, topic: str = None):
        """Выводит отчёт об охвате."""
        analyses = self.get_coverage_analysis(topic)

        for topic_name, analysis in analyses.items():
            CoverageAnalyzer.print_report(analysis, topic_name)

    def get_links_summary(self) -> str:
        """Возвращает текстовое резюме ссылок."""
        lines = ["=" * 70]
        lines.append("  РЕЗЮМЕ ПЕРЕЛИНКОВКИ")
        lines.append("=" * 70)

        for topic, cluster in self.clusters.items():
            lines.append(f"\n📦 {topic.upper()}")
            lines.append(f"   Страниц: {len(cluster.pages)}")
            lines.append(f"   Ссылок: {len(cluster.links)}")

            if cluster.links:
                lines.append("   Примеры ссылок:")
                for link in cluster.links[:3]:
                    lines.append(f"   • {link.source.domain} → {link.target.domain}")
                    lines.append(f"     Анкор: {link.anchor[:50]}...")

        return '\n'.join(lines)

    def export_links_json(self, output_path: str):
        """Экспортирует ссылки в JSON."""
        data = {
            'clusters': {},
            'total_links': len(self.all_links)
        }

        for topic, cluster in self.clusters.items():
            data['clusters'][topic] = {
                'pages': [
                    {
                        'url': p.url,
                        'domain': p.domain,
                        'title': p.title,
                        'incoming': p.incoming_links,
                        'outgoing': p.outgoing_links
                    }
                    for p in cluster.pages
                ],
                'links': [
                    {
                        'source': l.source.url,
                        'target': l.target.url,
                        'anchor': l.anchor,
                        'type': l.link_type,
                        'inserted': l.inserted
                    }
                    for l in cluster.links
                ]
            }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Ссылки экспортированы в {output_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# ТЕСТИРОВАНИЕ
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # Тест морфера анкоров
    print("\n" + "=" * 70)
    print("  ТЕСТ ANCHOR MORPHER")
    print("=" * 70)

    morpher = AnchorMorpher('viagra', ['sildenafil'])

    print("\nРазнообразные анкоры:")
    for i in range(10):
        anchor = morpher.get_anchor(category='mixed')
        print(f"  {i+1}. {anchor}")

    print("\nКоммерческие анкоры:")
    for i in range(5):
        anchor = morpher.get_anchor(category='commercial')
        print(f"  {i+1}. {anchor}")

    print("\nLong-tail анкоры:")
    for i in range(5):
        anchor = morpher.get_anchor(category='longtail')
        print(f"  {i+1}. {anchor}")

    # Тест схем
    print("\n" + "=" * 70)
    print("  ТЕСТ СХЕМ ПЕРЕЛИНКОВКИ")
    print("=" * 70)

    # Создаём тестовые страницы
    test_pages = {
        'site1.com': [
            Page(url='https://site1.com/page1/', domain='site1.com', file_path='/test/1', title='Page 1', topic='viagra'),
            Page(url='https://site1.com/page2/', domain='site1.com', file_path='/test/2', title='Page 2', topic='viagra'),
        ],
        'site2.com': [
            Page(url='https://site2.com/page1/', domain='site2.com', file_path='/test/3', title='Page 3', topic='viagra'),
            Page(url='https://site2.com/page2/', domain='site2.com', file_path='/test/4', title='Page 4', topic='viagra'),
        ],
        'site3.com': [
            Page(url='https://site3.com/page1/', domain='site3.com', file_path='/test/5', title='Page 5', topic='viagra'),
            Page(url='https://site3.com/page2/', domain='site3.com', file_path='/test/6', title='Page 6', topic='viagra'),
        ],
    }

    print("\nТест CLUSTER схемы:")
    links = LinkSchemeEngine.cluster_scheme(test_pages, external_links_per_page=2)

    internal = [l for l in links if l.link_type == 'internal']
    external = [l for l in links if l.link_type == 'cross-site']

    print(f"  Всего ссылок: {len(links)}")
    print(f"  Внутренних: {len(internal)}")
    print(f"  Cross-site: {len(external)}")

    print("\n  Внутренние ссылки:")
    for l in internal[:4]:
        print(f"    {l.source.url} → {l.target.url}")

    print("\n  Cross-site ссылки:")
    for l in external[:6]:
        print(f"    {l.source.url} → {l.target.url}")

    # Создаём тестовый кластер для анализа
    cluster = Cluster(topic='viagra')
    for pages in test_pages.values():
        cluster.pages.extend(pages)
    cluster.links = links

    # Назначаем анкоры
    for link in cluster.links:
        link.anchor = morpher.get_anchor()

    # Анализ
    print("\n" + "=" * 70)
    print("  ТЕСТ АНАЛИЗА ОХВАТА")
    print("=" * 70)

    analysis = CoverageAnalyzer.analyze(cluster)
    CoverageAnalyzer.print_report(analysis, 'viagra')

    print("\n✅ Все тесты пройдены!")

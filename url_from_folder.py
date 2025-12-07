import os
import json
import sys
import datetime
import chardet
import re
import hashlib
from bs4 import BeautifulSoup

from pills import KEYWORDS


def detect_language(title_text):
    text = " " + title_text.lower() + " "
    lang_patterns = {
        'fr': [" le ", " la ", " les ", " de ", " du ", " des ", " et ", " ou ",
               "actualité", "actualités", "santé"],
        'it': [" il ", " lo ", " la ", " gli ", " un ", " uno ", " una ", " con ", " per ",
               " che ", " di ", " del ", " della ", " delle ", " degli ", " e ",
               " attualità", " comuni", " sicilia", " salute", " itinerari",
               " informazione", " periodico", " salento"],
        'es': [" el ", " la ", " los ", " las ", " un ", " una ", " unos ", " unas ",
               " con ", " que ", " de ", " del ", " en ", " y ",
               " farmacias", " salud", " actualidad", " educación", " guardia",
               " categoria", " categorías", " puentegenil", " genil"]
    }
    lang_scores = {'fr': 0, 'it': 0, 'es': 0}
    for lang in lang_patterns:
        for pattern in lang_patterns[lang]:
            lang_scores[lang] += text.count(pattern)
    sorted_langs = sorted(lang_scores.items(), key=lambda x: x[1], reverse=True)
    if sorted_langs[0][1] > 0 and sorted_langs[0][1] > sorted_langs[1][1]:
        return sorted_langs[0][0]
    else:
        return None


def generate_md5(text):
    """Генерирует MD5 хеш для текста"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def open_with_detected_encoding(filepath):
    with open(filepath, 'rb') as file:
        rawdata = file.read()
        detected_encoding = chardet.detect(rawdata)['encoding']
        if detected_encoding is None:
            detected_encoding = 'utf-8'
    return rawdata.decode(detected_encoding, errors='ignore')


def check_title_keywords(filepath, keywords_map):
    try:
        html_content = open_with_detected_encoding(filepath)
        soup = BeautifulSoup(html_content, 'html.parser')
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text().strip()
            lower_title = title_text.lower()
            for k in keywords_map:
                if k.lower() in lower_title:
                    pill = keywords_map[k]
                    if pill in ['viagra', 'cialis']:
                        lang = detect_language(title_text)
                        if lang in ['fr', 'it', 'es']:
                            pill = f"{pill}_{lang}"
                    return pill
    except Exception as e:
        print(f"Ошибка чтения файла {filepath}: {e}")
    return None


def format_json_pretty(json_obj):
    text = json.dumps(json_obj, indent=4, ensure_ascii=False)
    keys = ['tracker', 'trackerKey', 'pages', 'kloak']
    for k in keys:
        text = re.sub(rf'"{k}":', f'<b style="color:#f4df8b;">"{k}"</b>:', text)
    return text


def main():
    if len(sys.argv) < 2:
        print("Использование: python url_from_folder_html.py <путь_к_wpeaudit.com>")
        sys.exit(1)

    root_folder = sys.argv[1]
    results_by_domain = {}

    try:
        domains = sorted(os.listdir(root_folder))
    except FileNotFoundError:
        print(f"Папка '{root_folder}' не найдена.")
        sys.exit(1)

    for domain_dir in domains:
        domain_path = os.path.join(root_folder, domain_dir)
        if not os.path.isdir(domain_path):
            continue
        if domain_dir.startswith('.'):
            continue

        domain_results = []
        for root, dirs, files in os.walk(domain_path):
            for file in files:
                if file.endswith('.html'):
                    full_html_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_html_path, start=domain_path)
                    if rel_path.endswith('.html'):
                        rel_path = rel_path[:-5]
                    rel_path = "/" + rel_path.replace("\\", "/")
                    pill = check_title_keywords(full_html_path, KEYWORDS) or "yes"
                    domain_results.append((rel_path, pill))
        if domain_results:
            results_by_domain[domain_dir] = domain_results

    output_lines = []
    output_lines.append("--------------------------------------------------")
    output_lines.append("DOMAINS")
    output_lines.append("--------------------------------------------------")
    output_lines.append("")
    all_domains = sorted(set(results_by_domain.keys()))
    for dom in all_domains:
        output_lines.append(f"https://{dom}/")
    output_lines.append("")
    output_lines.append("")

    output_lines.append("--------------------------------------------------")
    output_lines.append("ALL FOUND URLS (domain + path + tablet)")
    output_lines.append("--------------------------------------------------")
    output_lines.append("")
    for dom, pairs in results_by_domain.items():
        for (path, pill) in pairs:
            full_link = f"https://{dom}{path}"
            output_lines.append(f"{full_link} - {pill}")
    output_lines.append("")
    output_lines.append("")

    output_lines.append("--------------------------------------------------")
    output_lines.append("ALL NO-CACHE LINKS")
    output_lines.append("--------------------------------------------------")
    output_lines.append("")
    for dom, pairs in results_by_domain.items():
        for (path, _) in pairs:
            full_link = f"https://{dom}{path}/?nocache"
            output_lines.append(full_link)
    output_lines.append("")
    output_lines.append("")

    output_lines.append("--------------------------------------------------")
    output_lines.append("ALL KEITARO JSON (splitted by domain)")
    output_lines.append("--------------------------------------------------")
    output_lines.append("")
    for dom, pairs in results_by_domain.items():
        pages_dict = {}
        kloak_dict = {}
        for (path, pill) in pairs:
            pages_dict[path] = pill
            kloak_dict[path] = "yes"
        keitaro_obj = {
            "tracker": "https://a4a0ccb560f3b5ebc2836a07ec121e90.com/",
            "trackerKey": "{tracker_key}",
            "pages": pages_dict,
            "kloak": kloak_dict
        }
        output_lines.append(f"------ KEITARO for {dom} ------")
        output_lines.append("")
        output_lines.append(json.dumps(keitaro_obj, indent=4, ensure_ascii=False))
        output_lines.append("")
        output_lines.append("==========================")
        output_lines.append("")

    html_lines = []
    html_lines.append('<div style="background:#1a68d7;color:#fff;font-size:22px;font-weight:bold;'
                      'border-radius:11px;'
                      'padding:15px 32px;margin-top:16px;margin-bottom:13px;'
                      'letter-spacing:1.7px;box-shadow:0 2px 9px #131d30cc;">DOMAINS :</div>')

    html_lines.append('<div style="margin:10px 0 20px 24px;">')
    for dom in all_domains:
        html_lines.append(f'<div style="margin:2px 0 2px 0;color:#357a3b;">https://{dom}/</div>')
    html_lines.append('</div>')

    html_lines.append('<div style="background:#1a68d7;color:#fff;font-size:22px;font-weight:bold;'
                      'border-radius:11px;'
                      'padding:15px 32px;margin-top:16px;margin-bottom:13px;'
                      'letter-spacing:1.7px;box-shadow:0 2px 9px #131d30cc;">ALL FOUND URLS (domain + path + tablet)</div>')
    html_lines.append('<div style="margin:10px 0 20px 24px;">')
    for dom, pairs in results_by_domain.items():
        for (path, pill) in pairs:
            url = f"https://{dom}{path}"
            html_lines.append(
                f'<div style="margin:2px 0 2px 0;color:#1a68d7;">{url} <span style="color:#228922;">- {pill}</span></div>')
    html_lines.append('</div>')

    html_lines.append('<div style="background:#1a68d7;color:#fff;font-size:22px;font-weight:bold;'
                      'border-radius:11px;'
                      'padding:15px 32px;margin-top:16px;margin-bottom:13px;'
                      'letter-spacing:1.7px;box-shadow:0 2px 9px #131d30cc;">ALL NO-CACHE LINKS</div>')
    html_lines.append('<div style="margin:10px 0 20px 24px;">')
    for dom, pairs in results_by_domain.items():
        for (path, _) in pairs:
            url = f"https://{dom}{path}/?nocache"
            html_lines.append(f'<div style="margin:2px 0 2px 0;color:#673ab7;">{url}</div>')
    html_lines.append('</div>')

    html_lines.append('<div style="background:#1a68d7;color:#fff;font-size:22px;font-weight:bold;'
                      'border-radius:11px;'
                      'padding:15px 32px;margin-top:16px;margin-bottom:13px;'
                      'letter-spacing:1.7px;box-shadow:0 2px 9px #131d30cc;">ALL KEITARO JSON (splitted by domain)</div>')

    for dom, pairs in results_by_domain.items():
        pages_dict = {}
        kloak_dict = {}
        for (path, pill) in pairs:
            pages_dict[path] = pill
            kloak_dict[path] = "yes"
        keitaro_obj = {
            "tracker": "https://a4a0ccb560f3b5ebc2836a07ec121e90.com/",
            "trackerKey": "{tracker_key}",
            "pages": pages_dict,
            "kloak": kloak_dict
        }
        js_pretty = format_json_pretty(keitaro_obj)

        html_lines.append(
            f'''
            <div class="keitaro-block">
                <div class="keitaro-title">
                    <b><span class="keitaro-label">KEITARO for </span>
                    <span class="keitaro-domain">{dom}</span></b>
                </div>
                <pre class="keitaro-json" id="json-{dom}" ondblclick="window.getSelection().selectAllChildren(this);">{js_pretty}</pre>
            </div>
            '''
        )

    # Собираем ВСЕ уникальные таблетки из всех доменов
    all_unique_pills = set()
    for dom, pairs in results_by_domain.items():
        for (_, pill) in pairs:
            all_unique_pills.add(pill)

    # Сортируем таблетки
    all_unique_pills = sorted(all_unique_pills)

    # Добавляем ОДИН общий блок MD5 Pills в конце
    html_lines.append(
        f'''
        <div class="md5-pills-block">
            <div class="md5-pills-title">
                <b><span class="md5-pills-label">MD5 Pills </span>
                <span class="md5-pills-domain">ALL PROJECT</span></b>
            </div>
            <div class="md5-pills-container">
        '''
    )

    for pill in all_unique_pills:
        pill_md5 = generate_md5(pill.lower())  # MD5 из lowercase версии
        html_lines.append(
            f'''
            <div class="pill-item">
                <div class="pill-name">{pill}</div>
                <div class="pill-md5" ondblclick="navigator.clipboard.writeText(this.textContent).then(() => {{
                    this.style.background = '#2d5f2f';
                    setTimeout(() => {{ this.style.background = '#1e3a5f'; }}, 300);
                }});" title="Двойной клик для копирования">{pill_md5}</div>
            </div>
            '''
        )

    html_lines.append('</div></div>')

    final_output = "\n".join(output_lines)
    final_html = (
            "<html><head><meta charset='utf-8'><style>"
            "body {font-family:Segoe UI,Arial,sans-serif;color:#e4e6eb;background:#23272e;}"
            "div {font-size:15px;}"
            ".keitaro-block { margin:32px 0 36px 0; }"
            ".keitaro-title { margin-top:16px;margin-bottom:2px; }"
            ".keitaro-label { color:#b53f3f; font-size:17px; }"
            ".keitaro-domain {"
            "  display:inline-block;"
            "  background:#b53f3f;"
            "  color:#fff;"
            "  padding:5px 10px;"
            "  margin-left:5px;"
            "  border-radius:8px;"
            "  border:2px solid #454c57;"
            "  font-size:16px;"
            "  font-weight:900;"
            "  letter-spacing:1.5px;"
            "  box-shadow:0 2px 10px #191b21b3;"
            "  transition:background 0.18s,box-shadow 0.18s;"
            "  cursor:default;"
            "  vertical-align:middle;"
            "}"
            ".keitaro-domain:hover {"
            "  background:#b53f3f;"
            "  box-shadow:0 4px 20px #a7363680, 0 1px 4px #16171ad0;"
            "}"
            ".keitaro-json {"
            "  background:#252c33;"
            "  border:2.2px solid #454c57;"
            "  border-radius:11px;"
            "  box-shadow:0 2px 12px #0005;"
            "  color:#e4e6eb;"
            "  font-size:15.5px;"
            "  padding:22px 32px;"
            "  margin:14px 0 36px 0;"
            "  transition:box-shadow 0.14s;"
            "  font-family:Consolas,monospace,monaco;"
            "}"
            ".keitaro-json:active {"
            "  box-shadow:0 2px 24px #a7363680;"
            "}"
            ".md5-pills-block { margin:24px 0 48px 0; }"
            ".md5-pills-title { margin-top:16px;margin-bottom:12px; }"
            ".md5-pills-label { color:#2e7d32; font-size:17px; }"
            ".md5-pills-domain {"
            "  display:inline-block;"
            "  background:#2e7d32;"
            "  color:#fff;"
            "  padding:5px 10px;"
            "  margin-left:5px;"
            "  border-radius:8px;"
            "  border:2px solid #454c57;"
            "  font-size:16px;"
            "  font-weight:900;"
            "  letter-spacing:1.5px;"
            "  box-shadow:0 2px 10px #191b21b3;"
            "  transition:background 0.18s,box-shadow 0.18s;"
            "  cursor:default;"
            "  vertical-align:middle;"
            "}"
            ".md5-pills-domain:hover {"
            "  background:#2e7d32;"
            "  box-shadow:0 4px 20px #2e7d3280, 0 1px 4px #16171ad0;"
            "}"
            ".md5-pills-container {"
            "  background:#252c33;"
            "  border:2.2px solid #454c57;"
            "  border-radius:11px;"
            "  box-shadow:0 2px 12px #0005;"
            "  padding:16px;"
            "  display:grid;"
            "  grid-template-columns:repeat(auto-fill, minmax(450px, 1fr));"
            "  gap:12px;"
            "}"
            ".pill-item {"
            "  background:#2a3139;"
            "  border:1.5px solid #3a424d;"
            "  border-radius:8px;"
            "  padding:12px 16px;"
            "  display:flex;"
            "  flex-direction:column;"
            "  gap:8px;"
            "  transition:all 0.2s;"
            "}"
            ".pill-item:hover {"
            "  border-color:#4a5a6d;"
            "  box-shadow:0 2px 8px #0003;"
            "}"
            ".pill-name {"
            "  color:#66bb6a;"
            "  font-weight:700;"
            "  font-size:16px;"
            "  letter-spacing:0.5px;"
            "  text-transform:uppercase;"
            "}"
            ".pill-md5 {"
            "  background:#1e3a5f;"
            "  color:#90caf9;"
            "  font-family:Consolas,monospace,monaco;"
            "  font-size:14px;"
            "  padding:8px 12px;"
            "  border-radius:6px;"
            "  cursor:pointer;"
            "  user-select:all;"
            "  transition:all 0.2s;"
            "  border:1px solid #2a4a6f;"
            "}"
            ".pill-md5:hover {"
            "  background:#244a7f;"
            "  border-color:#3a5a8f;"
            "  box-shadow:0 2px 6px #0004;"
            "}"
            ".pill-md5:active {"
            "  transform:scale(0.98);"
            "}"
            "</style></head><body>"
            + "\n".join(html_lines) +
            "</body></html>"
    )

    print("===START_HTML===")
    print(final_html)
    print("===END_HTML===")
    print(final_output)

    if len(sys.argv) > 2:
        log_dir = sys.argv[2]
    else:
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "take_you_links.log")

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n----- RUN AT {timestamp} -----\n")
        f.write(final_output)
        f.write("\n\n----- END OF RUN -----\n\n")


if __name__ == "__main__":
    main()
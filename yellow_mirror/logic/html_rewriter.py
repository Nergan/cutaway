from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
from .url_utils import is_safe_url


def replace_urls_in_html(html: str, base_url: str, proxy_base_url: str) -> str:
    """
    Заменяет все ссылки в HTML на прокси-ссылки.
    proxy_base_url — абсолютный URL прокси-эндпоинта (например, http://localhost:8000/api/).
    """
    soup = BeautifulSoup(html, 'lxml')

    # Замена ссылок в тегах
    for tag, attr in [('a', 'href'), ('link', 'href'), ('script', 'src'),
                      ('img', 'src'), ('iframe', 'src'), ('form', 'action')]:
        for element in soup.find_all(tag, **{attr: True}):
            original = element[attr]
            if original and not original.startswith('#') and not original.startswith('data:'):
                absolute = urljoin(base_url, original)
                if is_safe_url(absolute):
                    element[attr] = f"{proxy_base_url}?target={quote(absolute, safe='')}"

    # Замена URL в стилях (url(...))
    for element in soup.find_all(style=True):
        style = element['style']
        new_style = []
        for part in style.split('url('):
            if part and ')' in part:
                before, rest = part.split(')', 1)
                url_candidate = before.strip('\'" ')
                absolute = urljoin(base_url, url_candidate)
                if is_safe_url(absolute):
                    new_style.append(f"url({proxy_base_url}?target={quote(absolute, safe='')}){rest}")
                else:
                    new_style.append(f'url({before}){rest}')
            else:
                new_style.append(part)
        element['style'] = ''.join(new_style)

    # Убедимся, что есть body и head
    if not soup.body:
        if not soup.html:
            soup.append(soup.new_tag('html'))
        soup.html.append(soup.new_tag('body'))

    if not soup.head:
        head = soup.new_tag('head')
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)

    # Добавляем CSS для панели
    css_links = '''
<link rel="stylesheet" href="/yellow_mirror/static/styles/base.css">
<link rel="stylesheet" href="/yellow_mirror/static/styles/panel.css">
<link rel="stylesheet" href="/yellow_mirror/static/styles/responsive.css">
'''
    soup.head.append(BeautifulSoup(css_links, 'html.parser'))

    # Добавляем HTML панели
    panel_html = '''
<div class="panel-container">
    <div class="expanded-panel" id="expandedPanel">
        <input type="text" id="url-input" placeholder="paste web link" />
        <button id="load-site-btn" aria-label="Загрузить сайт">
            <img src="/yellow_mirror/static/favicon.png" alt="Globe" width="24" height="24">
        </button>
    </div>
    <div class="minimized-bar" id="minimizedBar"></div>
</div>
'''
    soup.body.append(BeautifulSoup(panel_html, 'html.parser'))

    # Добавляем скрипты Yellow Mirror
    scripts = '''
<script src="/yellow_mirror/scripts/core.js"></script>
<script src="/yellow_mirror/scripts/browser.js"></script>
<script src="/yellow_mirror/scripts/history.js"></script>
<script src="/yellow_mirror/scripts/dom.js"></script>
<script src="/yellow_mirror/scripts/background.js"></script>
<script src="/yellow_mirror/scripts/panel.js"></script>
<script src="/yellow_mirror/scripts/navigation.js"></script>
<script src="/yellow_mirror/scripts/init.js"></script>
'''
    soup.body.append(BeautifulSoup(scripts, 'html.parser'))

    return str(soup)
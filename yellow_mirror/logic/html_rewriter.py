from urllib.parse import urljoin, urlparse, urlunparse, quote
from bs4 import BeautifulSoup
from .url_utils import is_safe_url

# HTML-код панели (без iframe и видео)
PANEL_HTML = '''
<div class="panel-container" id="panel-container">
    <div class="expanded-panel" id="expandedPanel">
        <input type="text" id="url-input" placeholder="paste web link" />
        <button id="load-site-btn" aria-label="Загрузить сайт">
            <img src="/yellow_mirror/static/favicon.png" alt="Globe" width="24" height="24">
        </button>
    </div>
    <div class="minimized-bar" id="minimizedBar"></div>
</div>
'''

# Подключаемые ресурсы (стили и скрипты)
RESOURCES = '''
<link rel="stylesheet" href="/yellow_mirror/static/styles/base.css">
<link rel="stylesheet" href="/yellow_mirror/static/styles/panel.css">
<link rel="stylesheet" href="/yellow_mirror/static/styles/responsive.css">
<script src="/yellow_mirror/scripts/core.js"></script>
<script src="/yellow_mirror/scripts/browser.js"></script>
<script src="/yellow_mirror/scripts/dom.js"></script>
<script src="/yellow_mirror/scripts/panel.js"></script>
<script src="/yellow_mirror/scripts/background.js"></script>
<script src="/yellow_mirror/scripts/init.js"></script>
'''


def replace_urls_in_html(html: str, base_url: str, proxy_base_url: str) -> str:
    """
    Заменяет ссылки на прокси и вставляет панель управления.
    proxy_base_url — абсолютный URL прокси-эндпоинта (например, http://localhost:8000/api/).
    """
    soup = BeautifulSoup(html, 'lxml')

    # 1. Переписываем ссылки в тегах
    for tag, attr in [('a', 'href'), ('link', 'href'), ('script', 'src'),
                      ('img', 'src'), ('iframe', 'src'), ('form', 'action')]:
        for element in soup.find_all(tag, **{attr: True}):
            original = element[attr]
            if original and not original.startswith('#') and not original.startswith('data:'):
                absolute = urljoin(base_url, original)
                if is_safe_url(absolute):
                    # Разделяем URL на часть до фрагмента и фрагмент
                    parsed = urlparse(absolute)
                    # Убираем фрагмент из основного URL, он будет добавлен после прокси
                    base_without_frag = urlunparse(parsed._replace(fragment=''))
                    fragment = parsed.fragment
                    proxy_url = f"{proxy_base_url}?target={quote(base_without_frag, safe='')}"
                    if fragment:
                        proxy_url += f"#{fragment}"
                    element[attr] = proxy_url

    # 2. Переписываем URL в style-атрибутах
    for element in soup.find_all(style=True):
        style = element['style']
        new_style = []
        for part in style.split('url('):
            if part and ')' in part:
                before, rest = part.split(')', 1)
                url_candidate = before.strip('\'" ')
                absolute = urljoin(base_url, url_candidate)
                if is_safe_url(absolute):
                    parsed = urlparse(absolute)
                    base_without_frag = urlunparse(parsed._replace(fragment=''))
                    fragment = parsed.fragment
                    proxy_url = f"{proxy_base_url}?target={quote(base_without_frag, safe='')}"
                    if fragment:
                        proxy_url += f"#{fragment}"
                    new_style.append(f"url({proxy_url}){rest}")
                else:
                    new_style.append(f'url({before}){rest}')
            else:
                new_style.append(part)
        element['style'] = ''.join(new_style)

    # 3. Вставляем панель и ресурсы в <body>
    if not soup.body:
        if not soup.html:
            soup.append(soup.new_tag('html'))
        soup.html.append(soup.new_tag('body'))

    # Вставляем панель сразу после открывающего тега body
    panel_soup = BeautifulSoup(PANEL_HTML, 'lxml')
    for child in reversed(panel_soup.body.contents):
        soup.body.insert(0, child)

    # Добавляем ресурсы (стили и скрипты) в <head> или в конец body? Лучше в head.
    head = soup.head
    if not head:
        head = soup.new_tag('head')
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.append(head)
    resources_soup = BeautifulSoup(RESOURCES, 'lxml')
    for child in resources_soup.head.contents:
        head.append(child)

    return str(soup)
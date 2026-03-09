from urllib.parse import urljoin, quote, urlparse, urlunparse
from bs4 import BeautifulSoup
from .url_utils import is_safe_url


def replace_urls_in_html(html: str, base_url: str, proxy_base_url: str) -> str:
    """
    Заменяет все ссылки в HTML на прокси-ссылки.
    proxy_base_url — абсолютный URL прокси-эндпоинта (например, http://localhost:8000/yellow-mirror/api/).
    """
    soup = BeautifulSoup(html, 'lxml')

    for tag, attr in [('a', 'href'), ('link', 'href'), ('script', 'src'),
                      ('img', 'src'), ('iframe', 'src'), ('form', 'action')]:
        for element in soup.find_all(tag, **{attr: True}):
            original = element[attr]
            if original and not original.startswith('#') and not original.startswith('data:'):
                absolute = urljoin(base_url, original)
                if is_safe_url(absolute):
                    # Разделяем URL на часть без фрагмента и сам фрагмент
                    parsed = urlparse(absolute)
                    # Собираем URL без фрагмента
                    url_without_fragment = urlunparse(parsed._replace(fragment=''))
                    quoted_target = quote(url_without_fragment, safe='')
                    new_url = f"{proxy_base_url}?target={quoted_target}"
                    if parsed.fragment:
                        new_url += "#" + parsed.fragment
                    element[attr] = new_url

    for element in soup.find_all(style=True):
        style = element['style']
        new_style = []
        for part in style.split('url('):
            if part and ')' in part:
                before, rest = part.split(')', 1)
                url_candidate = before.strip('\'" ')
                absolute = urljoin(base_url, url_candidate)
                if is_safe_url(absolute):
                    # Аналогично обрабатываем фрагменты в CSS (редко, но возможно)
                    parsed = urlparse(absolute)
                    url_without_fragment = urlunparse(parsed._replace(fragment=''))
                    quoted_target = quote(url_without_fragment, safe='')
                    new_url = f"{proxy_base_url}?target={quoted_target}"
                    if parsed.fragment:
                        new_url += "#" + parsed.fragment
                    new_style.append(f"url({new_url}){rest}")
                else:
                    new_style.append(f'url({before}){rest}')
            else:
                new_style.append(part)
        element['style'] = ''.join(new_style)

    if not soup.body:
        if not soup.html:
            soup.append(soup.new_tag('html'))
        soup.html.append(soup.new_tag('body'))

    # Добавляем скрипт для отслеживания навигации внутри iframe (без изменений)
    script_tag = soup.new_tag('script')
    script_tag.string = '''
    (function() {
        var lastUrl = location.href;
        setInterval(function() {
            if (location.href !== lastUrl) {
                lastUrl = location.href;
                window.top.postMessage({ type: 'iframe-navigation', url: lastUrl }, '*');
            }
        }, 300);
        window.top.postMessage({ type: 'iframe-navigation', url: lastUrl }, '*');
    })();
    '''
    soup.body.append(script_tag)

    return str(soup)
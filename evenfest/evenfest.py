import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / 'templates')

# В монолите корень уже в sys.path, при standalone-запуске из папки плагина — нет.
sys.path.append(str(BASE_DIR.parent))
from shared_mongo import get_client

db = get_client()['evenfest']
config_collection = db['config']


async def get_config():
    """Загружает конфигурацию (меню и контент) из MongoDB."""
    config = await config_collection.find_one({'_id': 'main'})
    if config is None:
        # Если документа нет – возвращаем пустые структуры
        return {'menu': [], 'content': {}}
    return config


_TITLE = re.compile(r"\{%\s*block title\s*%\}(.*?)\{%\s*endblock\s*%\}", re.DOTALL)
_HEADING = re.compile(r"<h2[^>]*>(.*?)</h2>", re.DOTALL | re.IGNORECASE)
_LEAD = re.compile(r'<p class="text-muted">(.*?)</p>', re.DOTALL | re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_PAGE_NAME = re.compile(r"^[a-z0-9-]+$")


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items() if key != "_id"}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _page_names() -> list[str]:
    names = []
    for path in sorted((BASE_DIR / "templates").glob("*.html")):
        if path.stem == "base":
            continue
        names.append(path.stem)
    return names


def _page_shell(name: str) -> dict:
    template = (BASE_DIR / "templates" / f"{name}.html").read_text(encoding="utf-8")
    title = _TITLE.search(template)
    heading = _HEADING.search(template)
    lead = _LEAD.search(template)

    def text_of(match) -> str:
        if not match:
            return ""
        return _TAGS.sub("", match.group(1)).strip()

    return {
        "id": name,
        "title": text_of(title),
        "heading": text_of(heading),
        "lead": text_of(lead),
        "href": f"/evenfest/{name}",
    }


@router.get("/api")
async def api_index():
    config = await get_config()
    return {
        "pages": "/evenfest/api/pages",
        "menu": _plain(config.get("menu", [])),
    }


@router.get("/api/pages")
async def list_pages():
    config = await get_config()
    content = config.get("content") or {}
    pages = []
    for name in _page_names():
        page = _page_shell(name)
        page["has_content"] = bool(str(content.get(name) or "").strip())
        pages.append(page)
    return {"menu": _plain(config.get("menu", [])), "pages": pages}


@router.get("/api/pages/{page_name}")
async def read_page(page_name: str):
    if not _PAGE_NAME.fullmatch(page_name) or page_name not in _page_names():
        raise HTTPException(status_code=404, detail="Page not found")
    config = await get_config()
    content = config.get("content") or {}
    stored = content.get(page_name) or ""
    if not isinstance(stored, str):
        stored = str(stored)
    page = _page_shell(page_name)
    page["content"] = stored
    page["menu"] = _plain(config.get("menu", []))
    return page


@router.get('/', response_class=HTMLResponse, name='evenfest_root')
@router.get('/{page_name:path}', response_class=HTMLResponse, name='evenfest_page')
async def evenpage(request: Request, page_name: str = ''):
    root_path = request.scope.get('root_path', '').rstrip('/')

    # Корневой URL → перенаправляем на страницу новостей
    if not page_name or request.url.path.rstrip('/') == root_path:
        return RedirectResponse(url=request.url_for('evenfest_page', page_name='news'))

    segments = page_name.strip('/').split('/')
    first_segment = segments[0] if segments else ''

    # Проверяем существование шаблона для первого сегмента
    template_path = BASE_DIR / 'templates' / f'{first_segment}.html'
    if not template_path.exists():
        # Если шаблона нет – редирект на новости
        return RedirectResponse(url=request.url_for('evenfest_page', page_name='news'))

    # Если в пути больше одного сегмента – редиректим на первый (нормализация)
    if len(segments) > 1:
        return RedirectResponse(url=request.url_for('evenfest_page', page_name=first_segment))

    # Получаем данные из MongoDB
    config = await get_config()
    menu = config.get('menu', [])
    page_content = config.get('content', {}).get(first_segment, '')

    return templates.TemplateResponse(
        request,
        f'{first_segment}.html',
        {
            'menu': menu,
            'page_content': page_content,
        }
    )
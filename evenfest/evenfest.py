from pathlib import Path
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / 'templates')


def load_data() -> dict:
    file_path = BASE_DIR / 'content.json'
    if file_path.exists():
        with open(file_path, encoding='utf-8') as f:
            return json.load(f)
    raise Exception(f'{file_path} not found')


def get_menu_pages() -> list[str]:
    """Возвращает список допустимых имён страниц из меню."""
    data = load_data()
    return [item['url'] for item in data.get('menu', [])]


@router.get('/', response_class=HTMLResponse, name='evenfest_root')
@router.get('/{page_name:path}', response_class=HTMLResponse, name='evenfest_page')
async def evenpage(request: Request, page_name: str = ''):
    root_path = request.scope.get('root_path', '').rstrip('/')
    
    # Если запрошен корень (пустой page_name или только root_path)
    if not page_name or request.url.path.rstrip('/') == root_path:
        return RedirectResponse(url=request.url_for('evenfest_page', page_name='news'))
    
    # Разбиваем путь на сегменты
    segments = page_name.strip('/').split('/')
    first_segment = segments[0] if segments else ''
    
    # Проверяем, существует ли шаблон для первого сегмента
    template_path = BASE_DIR / 'templates' / f'{first_segment}.html'
    if template_path.exists():
        # Если первый сегмент валиден, но есть дополнительные сегменты, редиректим на него
        if len(segments) > 1:
            return RedirectResponse(url=request.url_for('evenfest_page', page_name=first_segment))
        # Иначе отображаем страницу первого сегмента (нормальный случай)
    else:
        # Первый сегмент не существует — редирект на новости
        return RedirectResponse(url=request.url_for('evenfest_page', page_name='news'))
    
    # Загружаем данные для отображения страницы (первый сегмент валиден)
    data = load_data()
    return templates.TemplateResponse(
        f'{first_segment}.html',
        {
            'request': request,
            'menu': data.get('menu', []),
            'page_content': data.get('content', {}).get(first_segment, ''),
        }
    )
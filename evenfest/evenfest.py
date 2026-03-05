import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient

router = APIRouter()
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / 'templates')

# Подключение к MongoDB (аналогично другим микросервисам)
MONGO_URL = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
db = client['evenfest']
config_collection = db['config']


async def get_config():
    """Загружает конфигурацию (меню и контент) из MongoDB."""
    config = await config_collection.find_one({'_id': 'main'})
    if config is None:
        # Если документа нет – возвращаем пустые структуры
        return {'menu': [], 'content': {}}
    return config


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
        f'{first_segment}.html',
        {
            'request': request,
            'menu': menu,
            'page_content': page_content,
        }
    )
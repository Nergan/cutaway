from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from json import load
from os.path import exists
from pathlib import Path

router = APIRouter()
templates = Jinja2Templates(directory='evenfest/templates')


def load_data(path: str) -> dict:
    file_path = Path(path)
    if file_path.exists():
        with open(file_path, encoding='utf-8') as f:
            return load(f)
    raise Exception(f'{path} not found')


@router.get('/evenfest', response_class=HTMLResponse)
@router.get('/evenfest/{page_name}', response_class=HTMLResponse)
async def evenpage(request: Request, page_name: str = 'news'):
    if request.url.path.rstrip('/') == '/evenfest':
        return RedirectResponse(url='/evenfest/news')

    if not exists(f'evenfest/templates/{page_name}.html'):
        raise HTTPException(status_code=404, detail='Страница не найдена')

    data = load_data('evenfest/content.json')
    return templates.TemplateResponse(
        f'{page_name}.html',
        {
            'request': request,
            'menu': data.get('menu', []),
            'page_content': data.get('content', {}).get(page_name, '')
        }
    )
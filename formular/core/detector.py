import magic
import re
import zipfile
from io import BytesIO

MIME_MAP = {
    'application/pdf': 'pdf',
    'text/html': 'html',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/msword': 'doc',
    'application/vnd.ms-office': 'doc',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
    'application/vnd.ms-powerpoint': 'pptx',
    'application/rtf': 'rtf',
    'text/rtf': 'rtf',
    'application/vnd.oasis.opendocument.text': 'odt',
    'application/epub+zip': 'epub',
    'image/vnd.djvu': 'djvu',
    'image/x-djvu': 'djvu',
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'image/svg+xml': 'svg',
    'image/gif': 'gif',
    'audio/mpeg': 'mp3',
    'audio/x-wav': 'wav',
    'audio/wav': 'wav',
    'video/mp4': 'mp4',
    'video/webm': 'webm',
    'text/csv': 'csv',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
    'application/zip': 'zip',
    'application/x-zip-compressed': 'zip',
    'application/x-zip': 'zip',
    'multipart/x-zip': 'zip',
    'application/x-rar': 'rar',
    'application/vnd.rar': 'rar',
    'application/x-7z-compressed': '7z',
    'application/x-tar': 'tar',
    'application/gzip': 'gz',
    'application/json': 'json',
    'text/yaml': 'yaml',
    'application/x-yaml': 'yaml',
    'application/toml': 'toml',
    'text/toml': 'toml',
    'application/xml': 'xml',
    'text/xml': 'xml'
}

ALLOWED_CONVERSIONS = {
    'docx': ['pdf', 'html', 'txt', 'md'],
    'doc': ['pdf', 'html', 'txt', 'md'],
    'pptx': ['pdf', 'html', 'txt', 'md', 'xml'],
    'pdf': ['html', 'txt', 'md'],
    'html': ['pdf', 'md', 'txt', 'xml'],
    'md': ['pdf', 'html', 'txt'],
    'txt': ['pdf', 'html', 'md', 'json', 'yaml', 'toml', 'xml'],
    'rtf': ['pdf', 'html', 'txt', 'md'],
    'odt': ['pdf', 'html', 'txt', 'md'],
    'epub': ['pdf', 'html', 'txt', 'md'],
    'djvu': ['pdf', 'html', 'txt', 'md'],
    'json': ['yaml', 'toml', 'xml', 'md', 'txt', 'html', 'pdf'],
    'yaml': ['json', 'toml', 'xml', 'md', 'txt', 'html', 'pdf'],
    'toml': ['json', 'yaml', 'xml', 'md', 'txt', 'html', 'pdf'],
    'xml': ['json', 'yaml', 'toml', 'md', 'txt', 'html', 'pdf'],
    'jpg': ['jpg', 'png', 'webp', 'pdf'],
    'png': ['png', 'jpg', 'webp', 'pdf'],
    'webp': ['webp', 'jpg', 'png', 'pdf'],
    'svg': ['png', 'jpg', 'pdf'],
    'gif': ['gif', 'mp4', 'png'],
    'mp3': ['mp3', 'wav'],
    'wav': ['wav', 'mp3'],
    'mp4': ['mp4', 'webm', 'gif', 'mp3'],
    'webm': ['webm', 'mp4', 'gif', 'mp3'],
    'csv': ['pdf'],
    'xlsx': ['csv', 'pdf'],
    'zip': ['7z', 'tar', 'gz'],
    'rar': ['zip', '7z', 'tar', 'gz'],
    '7z': ['zip', 'tar', 'gz'],
    'tar': ['zip', '7z', 'gz'],
    'gz': ['zip', '7z', 'tar']
}

def detect_file_format(file_bytes: bytes, filename: str) -> str:
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    mime = magic.from_buffer(file_bytes[:4096], mime=True)

    if file_bytes.startswith(b'AT&T') and b'DJVU' in file_bytes[:100]:
        return 'djvu'

    if mime in ['application/zip', 'application/x-zip-compressed', 'application/octet-stream'] or ext == 'zip' or file_bytes.startswith(b'PK\x03\x04'):
        if file_bytes.startswith(b'PK\x03\x04'):
            try:
                with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
                    namelist = zf.namelist()
                    if 'word/document.xml' in namelist: return 'docx'
                    if 'xl/workbook.xml' in namelist: return 'xlsx'
                    if 'ppt/presentation.xml' in namelist: return 'pptx'
                    if 'mimetype' in namelist:
                        mime_content = zf.read('mimetype').decode('utf-8', errors='ignore').strip()
                        if 'application/epub+zip' in mime_content: return 'epub'
                        if 'application/vnd.oasis.opendocument.text' in mime_content: return 'odt'
            except Exception:
                pass
        
        if file_bytes.startswith(b'PK\x03\x04') or ext == 'zip':
            return 'zip'

    text_extensions = {'txt', 'py', 'js', 'json', 'yaml', 'yml', 'toml', 'xml', 'csv', 'md', 'html', 'css', 'log', 'sh', 'bat', 'ini', 'cfg'}
    if mime.startswith('text/') or 'script' in mime or mime == 'application/x-python' or ext in text_extensions:
        if ext in ['md', 'csv', 'html', 'json', 'yaml', 'yml', 'toml', 'xml']:
            return 'yaml' if ext == 'yml' else ext
        if ext in text_extensions: return 'txt'
        
        text_content = file_bytes[:2048].decode('utf-8', errors='ignore')
        if not ext:
            if re.search(r'(^#{1,6}\s.+|^>\s.+|\*\*.+\*\*|\[.+\]\(.+\))', text_content, re.MULTILINE): return 'md'
            if ',' in text_content.split('\n')[0] and '\n' in text_content: return 'csv'
            if '<html>' in text_content.lower() or '<!doctype html>' in text_content.lower(): return 'html'
            if text_content.strip().startswith('{') or text_content.strip().startswith('['): return 'json'
            if text_content.strip().startswith('<?xml') or text_content.strip().startswith('<'): return 'xml'
        
        return 'txt'

    if mime in MIME_MAP: return MIME_MAP[mime]

    fallback_map = {
        'rar': 'rar', '7z': '7z', 'tar': 'tar', 'gz': 'gz',
        'pdf': 'pdf', 'rtf': 'rtf', 'odt': 'odt', 'epub': 'epub', 'djvu': 'djvu',
        'jpg': 'jpg', 'jpeg': 'jpg', 'png': 'png', 'webp': 'webp', 'svg': 'svg', 'gif': 'gif',
        'mp3': 'mp3', 'wav': 'wav', 'mp4': 'mp4', 'webm': 'webm', 'xlsx': 'xlsx', 'docx': 'docx', 'doc': 'doc', 'pptx': 'pptx',
        'json': 'json', 'yaml': 'yaml', 'yml': 'yaml', 'toml': 'toml', 'xml': 'xml'
    }
    if ext in fallback_map: return fallback_map[ext]

    return 'unknown'

def get_allowed_targets(detected_format: str) -> list:
    return ALLOWED_CONVERSIONS.get(detected_format, [])
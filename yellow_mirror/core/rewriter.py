import re
from bs4 import BeautifulSoup

def rewrite_html(html: str, target_url: str) -> str:
    soup = BeautifulSoup(html, 'lxml')
    
    if not soup.head:
        head = soup.new_tag("head")
        if soup.body:
            soup.body.insert_before(head)
        else:
            soup.append(head)

    # Base tag for relative links
    base_tag = soup.new_tag("base", href=f"/yellow-mirror/proxy/{target_url}")
    soup.head.insert(0, base_tag)
    
    # Injector script
    script_tag = soup.new_tag("script", src="/yellow_mirror/scripts/inject.js")
    soup.head.insert(1, script_tag)
    
    # 1. KILL SUBRESOURCE INTEGRITY (Fixes Twitch modules)
    for tag in soup.find_all(True):
        if 'integrity' in tag.attrs:
            del tag['integrity']
        if 'nonce' in tag.attrs:
            del tag['nonce']
            
    # 2. FIX IMAGES (Forces fallback to standard src)
    for tag in soup.find_all(['img', 'source']):
        if tag.has_attr('srcset'):
            del tag['srcset']

    # 3. DESTROY CSP META TAGS
    for meta in soup.find_all('meta', attrs={'http-equiv': lambda x: x and x.lower() == 'content-security-policy'}):
        meta.decompose()
    
    # Rewrite absolute links
    for tag, attr in[('a', 'href'), ('link', 'href'), ('script', 'src'), ('img', 'src'), ('iframe', 'src'), ('form', 'action')]:
        for el in soup.find_all(tag, **{attr: True}):
            val = el.get(attr, "")
            if val.startswith(("http://", "https://")):
                el[attr] = f"/yellow-mirror/proxy/{val}"
                
    return str(soup)
from bs4 import BeautifulSoup

def rewrite_html(html: str, target_url: str) -> str:
    soup = BeautifulSoup(html, 'lxml')
    
    if not soup.head:
        head = soup.new_tag("head")
        if soup.body:
            soup.body.insert_before(head)
        else:
            soup.append(head)

    # Automatically resolves relative links within the iframe
    base_tag = soup.new_tag("base", href=f"/yellow-mirror/proxy/{target_url}")
    soup.head.insert(0, base_tag)
    
    # Inject DOM intercepter for history tracking
    script_tag = soup.new_tag("script", src="/yellow_mirror/scripts/inject.js")
    soup.head.insert(1, script_tag)
    
    # Explicitly rewrite existing absolute links
    for tag, attr in[('a', 'href'), ('link', 'href'), ('script', 'src'), ('img', 'src'), ('iframe', 'src'), ('form', 'action')]:
        for el in soup.find_all(tag, **{attr: True}):
            val = el.get(attr, "")
            if val.startswith("http://") or val.startswith("https://"):
                el[attr] = f"/yellow-mirror/proxy/{val}"
                
    return str(soup)
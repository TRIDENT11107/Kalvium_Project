import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

def extract_page_text(url, limit=5000):
    """Fetch readable text from public HTTP(S) pages when the host permits it."""
    if urlparse(url).scheme not in ("http","https"):
        return ""
    try:
        response=requests.get(url,headers={"User-Agent":"AILessonStudioResearch/1.0"},timeout=8)
        response.raise_for_status()
        content_type=response.headers.get("Content-Type","")
        if "text/html" not in content_type: return ""
        soup=BeautifulSoup(response.text,"html.parser")
        for node in soup(["script","style","nav","footer","header","noscript"]): node.decompose()
        return " ".join(soup.get_text(" ",strip=True).split())[:limit]
    except requests.RequestException:
        return ""

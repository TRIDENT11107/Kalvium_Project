"""Provider-backed research collection with a common, honest source shape."""
from __future__ import annotations

import time
from urllib.parse import urlsplit, urlunsplit

import requests

from config import (
    CROSSREF_MAILTO,
    GOOGLE_BOOKS_API_KEY,
    OPENALEX_MAILTO,
    TAVILY_API_KEY,
    WEB_LIMIT,
    BOOK_LIMIT,
    YOUTUBE_API_KEY,
    YOUTUBE_LIMIT,
)
from modules.web_research import extract_page_text


def _request(method, url, *, params=None, json=None, headers=None, timeout=20, attempts=3):
    last = None
    for attempt in range(attempts):
        try:
            request_fn = requests.get if method.upper() == "GET" else requests.post
            response = request_fn(url, params=params, json=json, headers=headers,
                                  timeout=timeout)
            status_code = getattr(response, "status_code", 200)
            if status_code == 429 or (isinstance(status_code, int) and status_code >= 500):
                response.raise_for_status()
            response.raise_for_status()
            return response
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(0.25 * (2 ** attempt))
    raise last


def _source(provider, source_type, title, url="", description="", **metadata):
    return {
        "provider": provider,
        "type": source_type,
        "title": title or "Untitled source",
        "url": url or "",
        "description": description or "",
        "content_available": bool(description),
        "metadata_only": not bool(description),
        **metadata,
    }


def _canonical(url):
    if not url:
        return ""
    parsed = urlsplit(url.strip())
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(),
                       parsed.path.rstrip("/"), "", ""))


def web_search(query):
    if not TAVILY_API_KEY:
        return [], "Tavily API key not configured"
    try:
        response = _request("POST", "https://api.tavily.com/search",
                            json={"api_key": TAVILY_API_KEY, "query": query,
                                  "search_depth": "advanced", "max_results": WEB_LIMIT,
                                  "include_answer": False}, timeout=25)
        items = []
        for item in response.json().get("results", []):
            if item.get("title") and item.get("url"):
                items.append(_source("tavily", "Website", item["title"], item["url"],
                                     item.get("content", ""), relevance=item.get("score"),
                                     published=item.get("published_date"),
                                     retrieval_metadata={"search_depth": "advanced"}))
        return items, None
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [], "Tavily search failed: " + str(exc)


def books_search(query):
    params = {"q": query, "maxResults": BOOK_LIMIT, "printType": "books"}
    if GOOGLE_BOOKS_API_KEY:
        params["key"] = GOOGLE_BOOKS_API_KEY
    try:
        response = _request("GET", "https://www.googleapis.com/books/v1/volumes",
                            params=params, timeout=20)
        items = []
        for item in response.json().get("items", []):
            info = item.get("volumeInfo", {})
            identifiers = {x.get("type"): x.get("identifier")
                           for x in info.get("industryIdentifiers", [])}
            items.append(_source("google_books", "Book", info.get("title"),
                                 info.get("infoLink") or item.get("selfLink", ""),
                                 info.get("description", ""),
                                 authors=info.get("authors", []),
                                 publisher=info.get("publisher"),
                                 published=info.get("publishedDate"),
                                 isbn=identifiers.get("ISBN_13") or identifiers.get("ISBN_10"),
                                 isbn_10=identifiers.get("ISBN_10"),
                                 isbn_13=identifiers.get("ISBN_13")))
        return items, None
    except requests.RequestException as exc:
        return [], "Google Books search failed: " + str(exc)


def openalex_search(query):
    try:
        params = {"search": query, "per-page": 5}
        if OPENALEX_MAILTO:
            params["mailto"] = OPENALEX_MAILTO
        response = _request("GET", "https://api.openalex.org/works",
                            params=params, timeout=20)
        items = []
        for work in response.json().get("results", []):
            primary = work.get("primary_location") or {}
            source = primary.get("source") or {}
            doi = work.get("doi") or ""
            items.append(_source("openalex", "Scholarly publication",
                                 work.get("title"), primary.get("landing_page_url") or doi,
                                 "",
                                 authors=[a.get("author", {}).get("display_name")
                                          for a in work.get("authorships", [])],
                                 published=work.get("publication_date"),
                                 doi=doi, journal=source.get("display_name"),
                                 citation_count=work.get("cited_by_count", 0),
                                 open_access=(work.get("open_access") or {}).get("is_oa"),
                                 source_metadata={"openalex_id": work.get("id")}))
        return items, None
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [], "OpenAlex search failed: " + str(exc)


def crossref_search(query):
    try:
        params = {"query.bibliographic": query, "rows": 5}
        if CROSSREF_MAILTO:
            params["mailto"] = CROSSREF_MAILTO
        response = _request("GET", "https://api.crossref.org/works",
                            params=params, timeout=20)
        items = []
        for work in response.json().get("message", {}).get("items", []):
            doi = work.get("DOI")
            if not doi:
                continue
            authors = [" ".join(filter(None, (a.get("given"), a.get("family"))))
                       for a in work.get("author", [])]
            items.append(_source("crossref", "Scholarly publication",
                                 (work.get("title") or ["Untitled"])[0],
                                 "https://doi.org/" + doi,
                                 (work.get("abstract") or "").replace("<jats:p>", "").replace("</jats:p>", ""),
                                 authors=authors,
                                 published=(work.get("published-print") or
                                            work.get("published-online") or {}).get("date-parts", [[None]])[0][0],
                                 doi=doi, journal=(work.get("container-title") or [None])[0],
                                 citation_count=work.get("is-referenced-by-count", 0),
                                 open_access=work.get("link") is not None))
        return items, None
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [], "Crossref search failed: " + str(exc)


def youtube_search(query):
    if not YOUTUBE_API_KEY:
        return [], "YouTube Data API key not configured"
    try:
        response = _request("GET", "https://www.googleapis.com/youtube/v3/search",
                            params={"part": "snippet", "type": "video",
                                    "maxResults": YOUTUBE_LIMIT, "q": query,
                                    "key": YOUTUBE_API_KEY}, timeout=20)
        ids = [x.get("id", {}).get("videoId") for x in response.json().get("items", [])]
        durations = {}
        if ids:
            detail = _request("GET", "https://www.googleapis.com/youtube/v3/videos",
                              params={"part": "contentDetails", "id": ",".join(ids),
                                      "key": YOUTUBE_API_KEY}, timeout=20)
            durations = {x["id"]: x.get("contentDetails", {}).get("duration")
                         for x in detail.json().get("items", []) if isinstance(x.get("id"), str)}
        items = []
        for item in response.json().get("items", []):
            video_id = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            if video_id:
                items.append(_source("youtube", "YouTube", snippet.get("title"),
                                     "https://www.youtube.com/watch?v=" + video_id,
                                     snippet.get("description", ""),
                                     channel=snippet.get("channelTitle"),
                                     published=snippet.get("publishedAt"),
                                     duration=durations.get(video_id),
                                     video_id=video_id))
        return items, None
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [], "YouTube search failed: " + str(exc)


def _deduplicate(items):
    seen = set()
    result = []
    for item in items:
        keys = [("doi", str(item.get("doi", "")).lower()),
                ("isbn", str(item.get("isbn", "")).replace("-", "")),
                ("url", _canonical(item.get("url", "")))]
        key = next((name + ":" + value for name, value in keys if value), None)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(item)
    return result


def collect_research(title, objective):
    query = title + ": " + objective + " educational explanation"
    providers = [("web", web_search), ("books", books_search),
                 ("openalex", openalex_search), ("crossref", crossref_search),
                 ("youtube", youtube_search)]
    results, errors = {}, {}
    for name, provider in providers:
        items, error = provider(query)
        results[name] = _deduplicate(items)
        if error:
            errors[name] = error
    for page in results["web"]:
        extracted = extract_page_text(page["url"])
        if extracted:
            page["content_available"] = True
            page["metadata_only"] = False
            page["description"] = (page["description"] + " " + extracted).strip()[:6000]
            page["retrieval_metadata"] = {"content_extracted": True}
    results["errors"] = errors
    results["all"] = _deduplicate(sum((results[k] for k, _ in providers), []))
    results["available_providers"] = [name for name, _ in providers if results[name]]
    results["partial"] = bool(errors) and bool(results["all"])
    return results

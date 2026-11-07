from unittest.mock import Mock

import requests

from modules import research_engine


def response(payload, status=200):
    result=Mock()
    result.status_code=status
    result.json.return_value=payload
    result.raise_for_status.side_effect=requests.HTTPError() if status>=400 else None
    return result


def test_provider_normalization_and_metadata(monkeypatch):
    def get(url, **kwargs):
        if "books" in url:
            return response({"items":[{"volumeInfo":{"title":"Book","authors":["Author"],"infoLink":"https://book.test","industryIdentifiers":[{"type":"ISBN_13","identifier":"123"}]}}]})
        if "openalex" in url:
            return response({"results":[{"title":"Paper","doi":"https://doi.org/10/x","authorships":[]}]})
        if "crossref" in url:
            return response({"message":{"items":[{"DOI":"10/x","title":["Paper"]}]}})
        return response({"items":[{"id":{"videoId":"v1"},"snippet":{"title":"Video","description":"Description"}}]})

    monkeypatch.setattr(research_engine.requests,"get",get)
    monkeypatch.setattr(research_engine,"GOOGLE_BOOKS_API_KEY","")
    monkeypatch.setattr(research_engine,"YOUTUBE_API_KEY","key")
    books,error=research_engine.books_search("topic")
    openalex,error2=research_engine.openalex_search("topic")
    crossref,error3=research_engine.crossref_search("topic")
    assert books[0]["isbn_13"]=="123" and books[0]["metadata_only"] is True
    assert openalex[0]["description"]=="" and openalex[0]["content_available"] is False
    assert crossref[0]["doi"]=="10/x" and error is error2 is error3 is None


def test_provider_auth_timeout_and_malformed_results_are_reported(monkeypatch):
    monkeypatch.setattr(research_engine,"TAVILY_API_KEY","key")
    monkeypatch.setattr(research_engine.requests,"post",Mock(side_effect=requests.Timeout()))
    items,error=research_engine.web_search("topic")
    assert items==[] and "Tavily search failed" in error
    monkeypatch.setattr(research_engine.requests,"post",Mock(return_value=response({},200)))
    items,error=research_engine.web_search("topic")
    assert items==[] and error is None
    malformed=response([],200)
    monkeypatch.setattr(research_engine.requests,"post",Mock(return_value=malformed))
    items,error=research_engine.web_search("topic")
    assert items==[] and "failed" in error


def test_research_deduplicates_urls_and_records_partial_results(monkeypatch):
    monkeypatch.setattr(research_engine,"web_search",lambda query:([{"url":"https://x.test/","title":"A","type":"Website"}],None))
    monkeypatch.setattr(research_engine,"books_search",lambda query:([{"url":"https://x.test","title":"Duplicate","type":"Book"}],None))
    monkeypatch.setattr(research_engine,"openalex_search",lambda query:([],"OpenAlex unavailable"))
    monkeypatch.setattr(research_engine,"crossref_search",lambda query:([],"Crossref unavailable"))
    monkeypatch.setattr(research_engine,"youtube_search",lambda query:([],"YouTube unavailable"))
    monkeypatch.setattr(research_engine,"extract_page_text",lambda url:"")
    result=research_engine.collect_research("Title","Objective")
    assert len(result["all"])==1
    assert result["partial"] is True
    assert set(result["errors"])=={"openalex","crossref","youtube"}

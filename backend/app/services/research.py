from modules.research_engine import collect_research, web_search, books_search, youtube_search

class WebResearchService:
    def search(self, query: str): return web_search(query)
class BooksResearchService:
    def search(self, query: str): return books_search(query)
class YouTubeResearchService:
    def search(self, query: str): return youtube_search(query)
class ResearchService:
    """Coordinates the existing provider integrations and normalized result collection."""
    def collect(self, title: str, objective: str) -> dict:
        return collect_research(title, objective)

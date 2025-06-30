import requests
import time
from typing import List, Optional, Dict, Any
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from loguru import logger
from .base_collector import BaseCollector, PaperMetadata


class GoogleScholarCollector(BaseCollector):
    """
    Google Scholar collector using web scraping.
    
    WARNING: This scraper should be used respectfully:
    - Implement proper rate limiting (recommended: 1 request per 10-30 seconds)
    - Use random user agents and delays
    - Consider using a proxy service for production
    - Be aware that Google may block scrapers
    
    For production use, consider:
    - SerpAPI (paid service for Google Scholar)
    - Scholarly library with proxy rotation
    - Academic API alternatives
    """
    
    def __init__(self, rate_limit: float = 0.1, use_serpapi: bool = False, serpapi_key: Optional[str] = None):
        # Very conservative rate limiting for Google Scholar (1 request per 10 seconds)
        super().__init__(rate_limit=rate_limit)
        self.base_url = "https://scholar.google.com"
        self.use_serpapi = use_serpapi
        self.serpapi_key = serpapi_key
        self.session = requests.Session()
        
        # Rotate user agents to appear more human-like
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        ]
        
        self.headers = {
            'User-Agent': self.user_agents[0],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
    
    def search_papers(
        self, 
        query: str, 
        max_results: int = 20,  # Keep small to avoid being blocked
        year_start: int = 2010,
        year_end: int = 2024
    ) -> List[PaperMetadata]:
        """
        Search Google Scholar for papers.
        
        Note: Google Scholar is very aggressive about blocking scrapers.
        For production use, consider SerpAPI or other academic APIs.
        """
        if self.use_serpapi and self.serpapi_key:
            return self._search_with_serpapi(query, max_results, year_start, year_end)
        else:
            return self._search_with_scraping(query, max_results, year_start, year_end)
    
    def _search_with_serpapi(
        self, 
        query: str, 
        max_results: int,
        year_start: int,
        year_end: int
    ) -> List[PaperMetadata]:
        """Use SerpAPI for reliable Google Scholar access (paid service)."""
        try:
            url = "https://serpapi.com/search.json"
            params = {
                'engine': 'google_scholar',
                'q': query,
                'api_key': self.serpapi_key,
                'num': min(max_results, 20),  # SerpAPI limit
                'as_ylo': year_start,
                'as_yhi': year_end,
                'as_sdt': '0,5'  # Include patents and citations
            }
            
            response = self._make_request_with_retry(
                requests.get, url, params=params, timeout=30
            )
            data = response.json()
            
            papers = []
            for result in data.get('organic_results', []):
                paper = self._parse_serpapi_result(result)
                if paper:
                    papers.append(paper)
            
            logger.info(f"Google Scholar (SerpAPI): Found {len(papers)} papers for query: {query}")
            return papers[:max_results]
            
        except Exception as e:
            logger.error(f"SerpAPI Google Scholar search failed: {e}")
            return []
    
    def _search_with_scraping(
        self, 
        query: str, 
        max_results: int,
        year_start: int,
        year_end: int
    ) -> List[PaperMetadata]:
        """
        Scrape Google Scholar directly (high risk of being blocked).
        
        WARNING: This method is fragile and may break frequently.
        Use only for testing or with proper proxy rotation.
        """
        try:
            # Construct search URL with year filter
            search_query = f"{query} after:{year_start} before:{year_end}"
            url = f"{self.base_url}/scholar?q={quote_plus(search_query)}&hl=en&as_sdt=0,5"
            
            papers = []
            start = 0
            results_per_page = 10
            
            while len(papers) < max_results and start < 100:  # Limit to 10 pages max
                page_url = f"{url}&start={start}"
                
                try:
                    response = self._make_request_with_retry(
                        self.session.get, page_url, headers=self.headers, timeout=30
                    )
                    
                    if response.status_code == 429:
                        logger.warning("Google Scholar rate limiting detected. Stopping collection.")
                        break
                    
                    soup = BeautifulSoup(response.content, 'html.parser')
                    results = soup.find_all('div', {'class': 'gs_r gs_or gs_scl'})
                    
                    if not results:
                        logger.warning("No more results found or blocked by Google Scholar")
                        break
                    
                    for result in results:
                        if len(papers) >= max_results:
                            break
                        
                        paper = self._parse_scholar_result(result)
                        if paper:
                            papers.append(paper)
                    
                    start += results_per_page
                    
                    # Extra delay between pages to avoid blocking
                    time.sleep(10)
                    
                except Exception as e:
                    logger.error(f"Error parsing Google Scholar page: {e}")
                    break
            
            logger.info(f"Google Scholar (scraping): Found {len(papers)} papers for query: {query}")
            return papers
            
        except Exception as e:
            logger.error(f"Google Scholar search failed: {e}")
            return []
    
    def _parse_serpapi_result(self, result: Dict[str, Any]) -> Optional[PaperMetadata]:
        """Parse a result from SerpAPI."""
        try:
            title = result.get('title', '').strip()
            if not title:
                return None
            
            # Extract authors
            authors = []
            if 'publication_info' in result:
                pub_info = result['publication_info'].get('authors', [])
                authors = [author.get('name', '') for author in pub_info if author.get('name')]
            
            # Extract year
            year = None
            if 'publication_info' in result and 'summary' in result['publication_info']:
                summary = result['publication_info']['summary']
                # Try to extract year from summary
                import re
                year_match = re.search(r'\b(19|20)\d{2}\b', summary)
                if year_match:
                    year = int(year_match.group())
            
            # Extract citation count
            citation_count = None
            if 'inline_links' in result:
                cited_by = result['inline_links'].get('cited_by', {})
                if 'total' in cited_by:
                    citation_count = cited_by['total']
            
            paper = PaperMetadata(
                title=title,
                authors=authors,
                abstract=result.get('snippet', ''),
                year=year,
                journal=None,  # Would need additional parsing
                citation_count=citation_count,
                pdf_url=result.get('resources', [{}])[0].get('link') if result.get('resources') else None,
                source='google_scholar',
                metadata={
                    'scholar_url': result.get('link'),
                    'result_id': result.get('result_id'),
                    'publication_info': result.get('publication_info')
                }
            )
            
            return paper
            
        except Exception as e:
            logger.error(f"Error parsing SerpAPI result: {e}")
            return None
    
    def _parse_scholar_result(self, result) -> Optional[PaperMetadata]:
        """Parse a single Google Scholar search result."""
        try:
            # Extract title
            title_elem = result.find('h3', {'class': 'gs_rt'})
            if not title_elem:
                return None
            
            title = title_elem.get_text().strip()
            title = title.replace('[PDF]', '').replace('[HTML]', '').strip()
            
            # Extract authors and publication info
            authors = []
            journal = None
            year = None
            
            auth_elem = result.find('div', {'class': 'gs_a'})
            if auth_elem:
                auth_text = auth_elem.get_text()
                # Parse "Author1, Author2 - Journal, Year - Publisher"
                parts = auth_text.split(' - ')
                if len(parts) >= 1:
                    authors_text = parts[0]
                    authors = [auth.strip() for auth in authors_text.split(',')]
                
                if len(parts) >= 2:
                    pub_info = parts[1]
                    # Extract year
                    import re
                    year_match = re.search(r'\b(19|20)\d{2}\b', pub_info)
                    if year_match:
                        year = int(year_match.group())
                    
                    # Extract journal (everything before year)
                    if year_match:
                        journal = pub_info[:year_match.start()].strip().rstrip(',')
            
            # Extract abstract/snippet
            abstract = ""
            snippet_elem = result.find('span', {'class': 'gs_rs'})
            if snippet_elem:
                abstract = snippet_elem.get_text().strip()
            
            # Extract citation count
            citation_count = None
            cited_elem = result.find('a', string=lambda text: text and 'Cited by' in text)
            if cited_elem:
                import re
                cite_text = cited_elem.get_text()
                cite_match = re.search(r'Cited by (\d+)', cite_text)
                if cite_match:
                    citation_count = int(cite_match.group(1))
            
            # Extract PDF URL if available
            pdf_url = None
            pdf_links = result.find_all('a', href=True)
            for link in pdf_links:
                href = link.get('href', '')
                if href.endswith('.pdf') or 'pdf' in href.lower():
                    pdf_url = href
                    break
            
            paper = PaperMetadata(
                title=title,
                authors=authors,
                abstract=abstract,
                year=year,
                journal=journal,
                citation_count=citation_count,
                pdf_url=pdf_url,
                source='google_scholar',
                metadata={
                    'raw_auth_text': auth_elem.get_text() if auth_elem else None
                }
            )
            
            return paper
            
        except Exception as e:
            logger.error(f"Error parsing Google Scholar result: {e}")
            return None
    
    def get_paper_details(self, paper_id: str) -> Optional[PaperMetadata]:
        """
        Get detailed information about a specific paper.
        Google Scholar doesn't have a direct paper details API.
        """
        logger.warning("Google Scholar doesn't support direct paper detail lookup")
        return None


# Example usage and testing
if __name__ == "__main__":
    # Test with conservative settings
    collector = GoogleScholarCollector(rate_limit=0.03)  # 1 request per 30 seconds
    
    # Test search
    papers = collector.search_papers(
        query="resistance training progressive overload",
        max_results=5,
        year_start=2020,
        year_end=2024
    )
    
    print(f"Found {len(papers)} papers")
    for paper in papers:
        print(f"- {paper.title}")
        print(f"  Authors: {', '.join(paper.authors[:3])}...")
        print(f"  Year: {paper.year}")
        print(f"  Citations: {paper.citation_count}")
        print()
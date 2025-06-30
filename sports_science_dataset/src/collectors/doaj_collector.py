import requests
from typing import List, Optional, Dict, Any
from loguru import logger
from .base_collector import BaseCollector, PaperMetadata


class DOAJCollector(BaseCollector):
    """
    DOAJ (Directory of Open Access Journals) collector.
    
    DOAJ provides access to high-quality, open access, peer-reviewed journals.
    Perfect for sports science as many sports journals are open access.
    
    API Documentation: https://doaj.org/api/docs
    Rate Limit: No strict limits mentioned, but we'll be conservative
    """
    
    def __init__(self, rate_limit: float = 2.0):
        super().__init__(rate_limit=rate_limit)
        self.base_url = "https://doaj.org/api/search"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'SportsScience-DatasetBuilder/1.0 (Academic Research)',
            'Accept': 'application/json'
        })
    
    def search_papers(
        self, 
        query: str, 
        max_results: int = 100,
        year_start: int = 2010,
        year_end: int = 2024
    ) -> List[PaperMetadata]:
        """Search DOAJ for open access papers."""
        try:
            papers = []
            page_size = 50  # DOAJ max page size
            page = 1
            
            while len(papers) < max_results:
                params = {
                    'q': self._build_query(query, year_start, year_end),
                    'pageSize': min(page_size, max_results - len(papers)),
                    'page': page,
                    'sort': 'score:desc'
                }
                
                response = self._make_request_with_retry(
                    self.session.get, 
                    f"{self.base_url}/articles", 
                    params=params,
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.error(f"DOAJ API error: {response.status_code}")
                    break
                
                data = response.json()
                results = data.get('results', [])
                
                if not results:
                    break
                
                for result in results:
                    paper = self._parse_doaj_result(result)
                    if paper:
                        papers.append(paper)
                
                # Check if we've got all available results
                total = data.get('total', 0)
                if len(papers) >= total or len(results) < page_size:
                    break
                
                page += 1
            
            logger.info(f"DOAJ: Found {len(papers)} papers for query: {query}")
            return papers[:max_results]
            
        except Exception as e:
            logger.error(f"DOAJ search failed: {e}")
            return []
    
    def _build_query(self, query: str, year_start: int, year_end: int) -> str:
        """Build DOAJ search query with filters."""
        # DOAJ uses Elasticsearch query syntax
        base_query = f'bibjson.title:"{query}" OR bibjson.abstract:"{query}"'
        
        # Add year filter
        year_filter = f'bibjson.year:[{year_start} TO {year_end}]'
        
        # Combine with AND
        full_query = f'({base_query}) AND {year_filter}'
        
        return full_query
    
    def _parse_doaj_result(self, result: Dict[str, Any]) -> Optional[PaperMetadata]:
        """Parse a DOAJ search result."""
        try:
            bibjson = result.get('bibjson', {})
            
            title = bibjson.get('title', '').strip()
            if not title:
                return None
            
            # Extract authors
            authors = []
            author_list = bibjson.get('author', [])
            for author in author_list:
                name = author.get('name', '').strip()
                if name:
                    authors.append(name)
            
            # Extract journal information
            journal_info = bibjson.get('journal', {})
            journal = journal_info.get('title', '')
            
            # Extract year
            year = None
            year_str = bibjson.get('year')
            if year_str:
                try:
                    year = int(year_str)
                except (ValueError, TypeError):
                    pass
            
            # Extract abstract
            abstract = bibjson.get('abstract', '').strip()
            
            # Extract DOI
            doi = None
            identifiers = bibjson.get('identifier', [])
            for identifier in identifiers:
                if identifier.get('type') == 'doi':
                    doi = identifier.get('id')
                    break
            
            # Extract PDF URL
            pdf_url = None
            links = bibjson.get('link', [])
            for link in links:
                if link.get('type') == 'fulltext' and 'pdf' in link.get('content_type', '').lower():
                    pdf_url = link.get('url')
                    break
            
            # If no PDF link found, try the first fulltext link
            if not pdf_url:
                for link in links:
                    if link.get('type') == 'fulltext':
                        pdf_url = link.get('url')
                        break
            
            # Extract keywords for metadata
            keywords = bibjson.get('keywords', [])
            subject = bibjson.get('subject', [])
            
            paper = PaperMetadata(
                title=title,
                authors=authors,
                abstract=abstract,
                year=year,
                journal=journal,
                doi=doi,
                pdf_url=pdf_url,
                source='doaj',
                metadata={
                    'doaj_id': result.get('id'),
                    'keywords': keywords,
                    'subject': subject,
                    'journal_info': journal_info,
                    'language': bibjson.get('language'),
                    'license': bibjson.get('license'),
                    'created_date': result.get('created_date'),
                    'last_updated': result.get('last_updated')
                }
            )
            
            return paper
            
        except Exception as e:
            logger.error(f"Error parsing DOAJ result: {e}")
            return None
    
    def get_paper_details(self, paper_id: str) -> Optional[PaperMetadata]:
        """Get detailed information about a specific paper by DOAJ ID."""
        try:
            url = f"https://doaj.org/api/articles/{paper_id}"
            
            response = self._make_request_with_retry(
                self.session.get, url, timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return self._parse_doaj_result(result)
            else:
                logger.error(f"DOAJ paper details failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting DOAJ paper details: {e}")
            return None
    
    def search_journals(self, subject: str = "sports") -> List[Dict[str, Any]]:
        """Search for relevant journals in DOAJ."""
        try:
            params = {
                'q': f'bibjson.subject.term:"{subject}"',
                'pageSize': 50,
                'sort': 'score:desc'
            }
            
            response = self._make_request_with_retry(
                self.session.get,
                f"{self.base_url}/journals",
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                journals = []
                
                for result in data.get('results', []):
                    bibjson = result.get('bibjson', {})
                    journal_info = {
                        'title': bibjson.get('title'),
                        'publisher': bibjson.get('publisher'),
                        'subjects': [subj.get('term') for subj in bibjson.get('subject', [])],
                        'language': bibjson.get('language'),
                        'license': bibjson.get('license'),
                        'homepage': bibjson.get('link', [{}])[0].get('url') if bibjson.get('link') else None
                    }
                    journals.append(journal_info)
                
                logger.info(f"DOAJ: Found {len(journals)} journals for subject: {subject}")
                return journals
            
            return []
            
        except Exception as e:
            logger.error(f"DOAJ journal search failed: {e}")
            return []


# Example usage
if __name__ == "__main__":
    collector = DOAJCollector()
    
    # Test search
    papers = collector.search_papers(
        query="resistance training",
        max_results=10,
        year_start=2020,
        year_end=2024
    )
    
    print(f"Found {len(papers)} papers")
    for paper in papers:
        print(f"- {paper.title}")
        print(f"  Journal: {paper.journal}")
        print(f"  Year: {paper.year}")
        print(f"  Authors: {', '.join(paper.authors[:2])}...")
        print(f"  DOI: {paper.doi}")
        print(f"  PDF: {'Yes' if paper.pdf_url else 'No'}")
        print()
    
    # Test journal search
    print("\nRelevant journals:")
    journals = collector.search_journals("sports")
    for journal in journals[:5]:
        print(f"- {journal['title']} ({journal['publisher']})")
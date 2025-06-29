from typing import List, Dict, Any, Optional
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from loguru import logger
from .base_collector import BaseCollector, PaperMetadata

class ArxivCollector(BaseCollector):
    def __init__(self, rate_limit: float = 0.17):  # 10 requests per minute
        super().__init__(rate_limit=rate_limit)
        self.base_url = "http://export.arxiv.org/api/query"
        self.source = "arxiv"
    
    def search_papers(
        self, 
        query: str, 
        max_results: int = 100,
        year_start: int = 2010,
        year_end: int = 2024
    ) -> List[PaperMetadata]:
        try:
            papers = []
            start = 0
            batch_size = min(50, max_results)  # arXiv recommends max 50 per request
            
            while len(papers) < max_results:
                current_batch_size = min(batch_size, max_results - len(papers))
                
                # Build search parameters
                search_query = self._build_arxiv_query(query, year_start, year_end)
                params = {
                    "search_query": search_query,
                    "start": start,
                    "max_results": current_batch_size,
                    "sortBy": "relevance",
                    "sortOrder": "descending"
                }
                
                logger.info(f"Searching arXiv: {query} (start: {start})")
                
                response = self._make_request_with_retry(
                    requests.get,
                    self.base_url,
                    params=params
                )
                
                if response.status_code != 200:
                    logger.error(f"arXiv API error: {response.status_code} - {response.text}")
                    break
                
                # Parse XML response
                batch_papers = self._parse_arxiv_response(response.text)
                
                if not batch_papers:
                    break
                
                for paper in batch_papers:
                    if paper and self._filter_by_year(paper, year_start, year_end):
                        paper.source = self.source
                        papers.append(paper)
                
                start += current_batch_size
                
                # If we got fewer papers than requested, we've reached the end
                if len(batch_papers) < current_batch_size:
                    break
            
            logger.info(f"Found {len(papers)} papers from arXiv for query: {query}")
            return papers[:max_results]
        
        except Exception as e:
            logger.error(f"Error searching arXiv: {e}")
            return []
    
    def _build_arxiv_query(self, query: str, year_start: int, year_end: int) -> str:
        # Convert natural language query to arXiv search format
        # Focus on relevant categories for sports science
        categories = [
            "q-bio",  # Quantitative Biology
            "stat",   # Statistics
            "cs.LG",  # Machine Learning
            "cs.AI",  # Artificial Intelligence
            "math.ST" # Statistics Theory
        ]
        
        # Build category filter
        category_filter = " OR ".join([f"cat:{cat}" for cat in categories])
        
        # Combine query with categories and date range
        # Note: arXiv uses submittedDate format YYYYMMDD
        date_filter = f"submittedDate:[{year_start}0101 TO {year_end}1231]"
        
        return f"({query}) AND ({category_filter}) AND {date_filter}"
    
    def _parse_arxiv_response(self, xml_content: str) -> List[PaperMetadata]:
        papers = []
        
        try:
            root = ET.fromstring(xml_content)
            
            # Define namespaces
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            entries = root.findall('atom:entry', namespaces)
            
            for entry in entries:
                paper = self._parse_arxiv_entry(entry, namespaces)
                if paper:
                    papers.append(paper)
        
        except ET.ParseError as e:
            logger.error(f"Error parsing arXiv XML response: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing arXiv response: {e}")
        
        return papers
    
    def _parse_arxiv_entry(self, entry: ET.Element, namespaces: Dict[str, str]) -> Optional[PaperMetadata]:
        try:
            # Extract title
            title_elem = entry.find('atom:title', namespaces)
            title = title_elem.text.strip() if title_elem is not None else ""
            if not title:
                return None
            
            # Extract authors
            authors = []
            author_elems = entry.findall('atom:author', namespaces)
            for author_elem in author_elems:
                name_elem = author_elem.find('atom:name', namespaces)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text.strip())
            
            # Extract abstract
            summary_elem = entry.find('atom:summary', namespaces)
            abstract = summary_elem.text.strip() if summary_elem is not None else ""
            
            # Extract arXiv ID
            id_elem = entry.find('atom:id', namespaces)
            arxiv_url = id_elem.text if id_elem is not None else ""
            arxiv_id = arxiv_url.split('/')[-1] if arxiv_url else ""
            
            # Extract publication date
            published_elem = entry.find('atom:published', namespaces)
            year = None
            if published_elem is not None:
                try:
                    pub_date = datetime.fromisoformat(published_elem.text.replace('Z', '+00:00'))
                    year = pub_date.year
                except ValueError:
                    pass
            
            # Extract categories
            categories = []
            category_elems = entry.findall('atom:category', namespaces)
            for cat_elem in category_elems:
                term = cat_elem.get('term')
                if term:
                    categories.append(term)
            
            # Extract PDF URL
            pdf_url = None
            link_elems = entry.findall('atom:link', namespaces)
            for link_elem in link_elems:
                if link_elem.get('type') == 'application/pdf':
                    pdf_url = link_elem.get('href')
                    break
            
            # Extract DOI if available
            doi = None
            arxiv_doi_elem = entry.find('arxiv:doi', namespaces)
            if arxiv_doi_elem is not None:
                doi = arxiv_doi_elem.text.strip()
            
            # Build metadata
            metadata = {
                "arxiv_url": arxiv_url,
                "categories": categories,
                "primary_category": categories[0] if categories else None,
                "updated": entry.find('atom:updated', namespaces).text if entry.find('atom:updated', namespaces) is not None else None
            }
            
            return PaperMetadata(
                title=title,
                authors=authors,
                abstract=abstract,
                year=year,
                arxiv_id=arxiv_id,
                doi=doi,
                pdf_url=pdf_url,
                source=self.source,
                metadata=metadata
            )
        
        except Exception as e:
            logger.error(f"Error parsing arXiv entry: {e}")
            return None
    
    def _filter_by_year(self, paper: PaperMetadata, year_start: int, year_end: int) -> bool:
        if not paper.year:
            return True  # Include papers without year information
        return year_start <= paper.year <= year_end
    
    def get_paper_details(self, arxiv_id: str) -> Optional[PaperMetadata]:
        try:
            params = {
                "id_list": arxiv_id,
                "max_results": 1
            }
            
            response = self._make_request_with_retry(
                requests.get,
                self.base_url,
                params=params
            )
            
            if response.status_code != 200:
                logger.error(f"arXiv API error for ID {arxiv_id}: {response.status_code}")
                return None
            
            papers = self._parse_arxiv_response(response.text)
            
            if papers:
                paper = papers[0]
                paper.source = self.source
                return paper
            
            return None
        
        except Exception as e:
            logger.error(f"Error fetching arXiv paper details for ID {arxiv_id}: {e}")
            return None
    
    def get_papers_by_category(
        self, 
        category: str, 
        max_results: int = 50,
        year_start: int = 2010,
        year_end: int = 2024
    ) -> List[PaperMetadata]:
        """Get papers from a specific arXiv category"""
        try:
            date_filter = f"submittedDate:[{year_start}0101 TO {year_end}1231]"
            search_query = f"cat:{category} AND {date_filter}"
            
            params = {
                "search_query": search_query,
                "start": 0,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending"
            }
            
            logger.info(f"Searching arXiv category: {category}")
            
            response = self._make_request_with_retry(
                requests.get,
                self.base_url,
                params=params
            )
            
            if response.status_code != 200:
                logger.error(f"arXiv API error for category {category}: {response.status_code}")
                return []
            
            papers = self._parse_arxiv_response(response.text)
            
            for paper in papers:
                paper.source = self.source
            
            return papers
        
        except Exception as e:
            logger.error(f"Error fetching arXiv papers by category {category}: {e}")
            return []
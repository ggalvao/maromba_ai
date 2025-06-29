from typing import List, Dict, Any, Optional
import requests
import json
from loguru import logger
from .base_collector import BaseCollector, PaperMetadata

class SemanticScholarCollector(BaseCollector):
    def __init__(self, api_key: Optional[str] = None, rate_limit: float = 1.67):  # 100 requests per minute
        super().__init__(rate_limit=rate_limit)
        self.api_key = api_key
        self.base_url = "https://api.semanticscholar.org/graph/v1"
        self.source = "semantic_scholar"
        
        # Set up headers
        self.headers = {
            "User-Agent": "Sports-Science-Dataset-Builder/1.0",
            "Content-Type": "application/json"
        }
        
        if api_key:
            self.headers["x-api-key"] = api_key
    
    def search_papers(
        self, 
        query: str, 
        max_results: int = 100,
        year_start: int = 2010,
        year_end: int = 2024
    ) -> List[PaperMetadata]:
        try:
            papers = []
            offset = 0
            limit = min(100, max_results)  # Semantic Scholar max is 100 per request
            
            while len(papers) < max_results:
                batch_size = min(limit, max_results - len(papers))
                
                # Build search parameters
                params = {
                    "query": query,
                    "limit": batch_size,
                    "offset": offset,
                    "fields": "paperId,title,authors,year,abstract,venue,citationCount,url,openAccessPdf,publicationDate"
                }
                
                logger.info(f"Searching Semantic Scholar: {query} (offset: {offset})")
                
                response = self._make_request_with_retry(
                    requests.get,
                    f"{self.base_url}/paper/search",
                    params=params,
                    headers=self.headers
                )
                
                if response.status_code != 200:
                    logger.error(f"Semantic Scholar API error: {response.status_code} - {response.text}")
                    break
                
                data = response.json()
                batch_papers = data.get("data", [])
                
                if not batch_papers:
                    break
                
                for paper_data in batch_papers:
                    paper = self._parse_semantic_scholar_paper(paper_data)
                    if paper and self._filter_by_year(paper, year_start, year_end):
                        paper.source = self.source
                        papers.append(paper)
                
                offset += batch_size
                
                # If we got fewer papers than requested, we've reached the end
                if len(batch_papers) < batch_size:
                    break
            
            logger.info(f"Found {len(papers)} papers from Semantic Scholar for query: {query}")
            return papers[:max_results]
        
        except Exception as e:
            logger.error(f"Error searching Semantic Scholar: {e}")
            return []
    
    def _parse_semantic_scholar_paper(self, paper_data: Dict[str, Any]) -> Optional[PaperMetadata]:
        try:
            title = paper_data.get("title", "").strip()
            if not title:
                return None
            
            # Extract authors
            authors = []
            author_list = paper_data.get("authors", [])
            for author in author_list:
                if "name" in author and author["name"]:
                    authors.append(author["name"])
            
            # Extract abstract
            abstract = paper_data.get("abstract", "") or ""
            
            # Extract year
            year = paper_data.get("year")
            
            # Extract journal/venue
            journal = paper_data.get("venue", "") or ""
            
            # Extract citation count
            citation_count = paper_data.get("citationCount", 0) or 0
            
            # Extract PDF URL
            pdf_url = None
            open_access_pdf = paper_data.get("openAccessPdf")
            if open_access_pdf and "url" in open_access_pdf:
                pdf_url = open_access_pdf["url"]
            
            # Extract Semantic Scholar ID
            semantic_scholar_id = paper_data.get("paperId", "")
            
            # Build metadata
            metadata = {
                "semantic_scholar_url": paper_data.get("url", ""),
                "publication_date": paper_data.get("publicationDate", ""),
                "is_open_access": bool(pdf_url),
                "fields_of_study": paper_data.get("fieldsOfStudy", [])
            }
            
            return PaperMetadata(
                title=title,
                authors=authors,
                abstract=abstract,
                year=year,
                journal=journal,
                semantic_scholar_id=semantic_scholar_id,
                citation_count=citation_count,
                pdf_url=pdf_url,
                source=self.source,
                metadata=metadata
            )
        
        except Exception as e:
            logger.error(f"Error parsing Semantic Scholar paper: {e}")
            return None
    
    def _filter_by_year(self, paper: PaperMetadata, year_start: int, year_end: int) -> bool:
        if not paper.year:
            return True  # Include papers without year information
        return year_start <= paper.year <= year_end
    
    def get_paper_details(self, paper_id: str) -> Optional[PaperMetadata]:
        try:
            params = {
                "fields": "paperId,title,authors,year,abstract,venue,citationCount,url,openAccessPdf,publicationDate,references,citations"
            }
            
            response = self._make_request_with_retry(
                requests.get,
                f"{self.base_url}/paper/{paper_id}",
                params=params,
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error(f"Semantic Scholar API error for paper {paper_id}: {response.status_code}")
                return None
            
            paper_data = response.json()
            paper = self._parse_semantic_scholar_paper(paper_data)
            
            if paper:
                paper.source = self.source
                
                # Add additional metadata from detailed view
                if "references" in paper_data:
                    paper.metadata["reference_count"] = len(paper_data["references"])
                if "citations" in paper_data:
                    paper.metadata["citation_count"] = len(paper_data["citations"])
            
            return paper
        
        except Exception as e:
            logger.error(f"Error fetching Semantic Scholar paper details for ID {paper_id}: {e}")
            return None
    
    def get_paper_by_doi(self, doi: str) -> Optional[PaperMetadata]:
        try:
            params = {
                "fields": "paperId,title,authors,year,abstract,venue,citationCount,url,openAccessPdf,publicationDate"
            }
            
            response = self._make_request_with_retry(
                requests.get,
                f"{self.base_url}/paper/DOI:{doi}",
                params=params,
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.warning(f"Semantic Scholar API error for DOI {doi}: {response.status_code}")
                return None
            
            paper_data = response.json()
            paper = self._parse_semantic_scholar_paper(paper_data)
            
            if paper:
                paper.source = self.source
                paper.doi = doi
            
            return paper
        
        except Exception as e:
            logger.error(f"Error fetching Semantic Scholar paper by DOI {doi}: {e}")
            return None
    
    def get_related_papers(self, paper_id: str, max_results: int = 10) -> List[PaperMetadata]:
        try:
            params = {
                "fields": "paperId,title,authors,year,abstract,venue,citationCount,url,openAccessPdf",
                "limit": max_results
            }
            
            response = self._make_request_with_retry(
                requests.get,
                f"{self.base_url}/paper/{paper_id}/citations",
                params=params,
                headers=self.headers
            )
            
            if response.status_code != 200:
                logger.error(f"Semantic Scholar API error for related papers {paper_id}: {response.status_code}")
                return []
            
            data = response.json()
            citations = data.get("data", [])
            
            related_papers = []
            for citation in citations:
                citing_paper = citation.get("citingPaper", {})
                paper = self._parse_semantic_scholar_paper(citing_paper)
                if paper:
                    paper.source = self.source
                    related_papers.append(paper)
            
            return related_papers
        
        except Exception as e:
            logger.error(f"Error fetching related papers for ID {paper_id}: {e}")
            return []
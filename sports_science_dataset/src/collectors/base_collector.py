from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import time
import asyncio
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

@dataclass
class PaperMetadata:
    title: str
    authors: List[str]
    abstract: str
    year: Optional[int] = None
    journal: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    arxiv_id: Optional[str] = None
    citation_count: Optional[int] = None
    pdf_url: Optional[str] = None
    source: str = ""
    domain: str = ""
    metadata: Optional[Dict[str, Any]] = None

class BaseCollector(ABC):
    def __init__(self, rate_limit: float = 3.0, email: Optional[str] = None):
        self.rate_limit = rate_limit  # requests per second
        self.email = email
        self.last_request_time = 0.0
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
    
    def _rate_limit_wait(self):
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        wait_time = (1.0 / self.rate_limit) - time_since_last
        
        if wait_time > 0:
            time.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def _make_request_with_retry(self, request_func, *args, **kwargs):
        self._rate_limit_wait()
        self.total_requests += 1
        
        try:
            result = request_func(*args, **kwargs)
            self.successful_requests += 1
            return result
        except Exception as e:
            self.failed_requests += 1
            logger.error(f"Request failed: {e}")
            raise
    
    @abstractmethod
    def search_papers(
        self, 
        query: str, 
        max_results: int = 100,
        year_start: int = 2010,
        year_end: int = 2024
    ) -> List[PaperMetadata]:
        pass
    
    @abstractmethod
    def get_paper_details(self, paper_id: str) -> Optional[PaperMetadata]:
        pass
    
    def get_stats(self) -> Dict[str, int]:
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': self.successful_requests / self.total_requests if self.total_requests > 0 else 0
        }
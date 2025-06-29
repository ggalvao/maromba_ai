from typing import List, Dict, Any, Optional
import xml.etree.ElementTree as ET
from Bio import Entrez
from loguru import logger
from .base_collector import BaseCollector, PaperMetadata

class PubMedCollector(BaseCollector):
    def __init__(self, email: str, rate_limit: float = 3.0):
        super().__init__(rate_limit=rate_limit, email=email)
        Entrez.email = email
        self.source = "pubmed"
    
    def search_papers(
        self, 
        query: str, 
        max_results: int = 100,
        year_start: int = 2010,
        year_end: int = 2024
    ) -> List[PaperMetadata]:
        try:
            # Build the search query with date filters
            search_query = f"{query} AND {year_start}[PDAT]:{year_end}[PDAT]"
            
            logger.info(f"Searching PubMed with query: {search_query}")
            
            # Search for paper IDs
            search_handle = self._make_request_with_retry(
                Entrez.esearch,
                db="pubmed",
                term=search_query,
                retmax=max_results,
                sort="relevance"
            )
            
            search_results = Entrez.read(search_handle)
            search_handle.close()
            
            pmids = search_results["IdList"]
            logger.info(f"Found {len(pmids)} papers for query: {query}")
            
            if not pmids:
                return []
            
            # Fetch detailed information for all papers
            papers = self._fetch_paper_details(pmids)
            
            # Set domain and source for all papers
            for paper in papers:
                paper.source = self.source
            
            return papers
        
        except Exception as e:
            logger.error(f"Error searching PubMed: {e}")
            return []
    
    def _fetch_paper_details(self, pmids: List[str]) -> List[PaperMetadata]:
        papers = []
        
        try:
            # Fetch details in batches to avoid overwhelming the API
            batch_size = 20
            for i in range(0, len(pmids), batch_size):
                batch_pmids = pmids[i:i + batch_size]
                
                fetch_handle = self._make_request_with_retry(
                    Entrez.efetch,
                    db="pubmed",
                    id=",".join(batch_pmids),
                    rettype="medline",
                    retmode="xml"
                )
                
                records = Entrez.read(fetch_handle)
                fetch_handle.close()
                
                for record in records['PubmedArticle']:
                    paper = self._parse_pubmed_record(record)
                    if paper:
                        papers.append(paper)
                
                logger.info(f"Processed batch {i//batch_size + 1}/{(len(pmids) + batch_size - 1)//batch_size}")
        
        except Exception as e:
            logger.error(f"Error fetching PubMed paper details: {e}")
        
        return papers
    
    def _parse_pubmed_record(self, record: Dict[str, Any]) -> Optional[PaperMetadata]:
        try:
            medline_citation = record['MedlineCitation']
            article = medline_citation['Article']
            
            # Extract basic information
            title = self._safe_extract_text(article.get('ArticleTitle', ''))
            if not title:
                return None
            
            # Extract authors
            authors = []
            author_list = article.get('AuthorList', [])
            for author in author_list:
                if 'ForeName' in author and 'LastName' in author:
                    full_name = f"{author['ForeName']} {author['LastName']}"
                    authors.append(full_name)
                elif 'CollectiveName' in author:
                    authors.append(author['CollectiveName'])
            
            # Extract abstract
            abstract = ""
            if 'Abstract' in article:
                abstract_texts = article['Abstract'].get('AbstractText', [])
                if isinstance(abstract_texts, list):
                    abstract = ' '.join([self._safe_extract_text(text) for text in abstract_texts])
                else:
                    abstract = self._safe_extract_text(abstract_texts)
            
            # Extract publication year
            year = None
            if 'ArticleDate' in article and article['ArticleDate']:
                year = int(article['ArticleDate'][0].get('Year', 0))
            elif 'Journal' in article and 'JournalIssue' in article['Journal']:
                pub_date = article['Journal']['JournalIssue'].get('PubDate', {})
                if 'Year' in pub_date:
                    year = int(pub_date['Year'])
            
            # Extract journal
            journal = ""
            if 'Journal' in article:
                journal = article['Journal'].get('Title', '')
            
            # Extract DOI
            doi = None
            article_ids = record.get('PubmedData', {}).get('ArticleIdList', [])
            for article_id in article_ids:
                if article_id.attributes.get('IdType') == 'doi':
                    doi = str(article_id)
                    break
            
            # Extract PMID
            pmid = str(medline_citation['PMID'])
            
            # Build metadata
            metadata = {
                'mesh_terms': self._extract_mesh_terms(medline_citation),
                'publication_types': self._extract_publication_types(article),
                'keywords': self._extract_keywords(medline_citation)
            }
            
            return PaperMetadata(
                title=title,
                authors=authors,
                abstract=abstract,
                year=year,
                journal=journal,
                doi=doi,
                pmid=pmid,
                source=self.source,
                metadata=metadata
            )
        
        except Exception as e:
            logger.error(f"Error parsing PubMed record: {e}")
            return None
    
    def _safe_extract_text(self, element) -> str:
        if isinstance(element, str):
            return element.strip()
        elif hasattr(element, 'text') and element.text:
            return element.text.strip()
        elif isinstance(element, dict) and '#text' in element:
            return element['#text'].strip()
        return ""
    
    def _extract_mesh_terms(self, medline_citation: Dict[str, Any]) -> List[str]:
        mesh_terms = []
        mesh_heading_list = medline_citation.get('MeshHeadingList', [])
        
        for mesh_heading in mesh_heading_list:
            descriptor = mesh_heading.get('DescriptorName', {})
            if isinstance(descriptor, dict) and '#text' in descriptor:
                mesh_terms.append(descriptor['#text'])
            elif isinstance(descriptor, str):
                mesh_terms.append(descriptor)
        
        return mesh_terms
    
    def _extract_publication_types(self, article: Dict[str, Any]) -> List[str]:
        pub_types = []
        pub_type_list = article.get('PublicationTypeList', [])
        
        for pub_type in pub_type_list:
            if isinstance(pub_type, dict) and '#text' in pub_type:
                pub_types.append(pub_type['#text'])
            elif isinstance(pub_type, str):
                pub_types.append(pub_type)
        
        return pub_types
    
    def _extract_keywords(self, medline_citation: Dict[str, Any]) -> List[str]:
        keywords = []
        keyword_list = medline_citation.get('KeywordList', [])
        
        for keyword_group in keyword_list:
            if isinstance(keyword_group, list):
                for keyword in keyword_group:
                    if isinstance(keyword, dict) and '#text' in keyword:
                        keywords.append(keyword['#text'])
                    elif isinstance(keyword, str):
                        keywords.append(keyword)
        
        return keywords
    
    def get_paper_details(self, pmid: str) -> Optional[PaperMetadata]:
        try:
            fetch_handle = self._make_request_with_retry(
                Entrez.efetch,
                db="pubmed",
                id=pmid,
                rettype="medline",
                retmode="xml"
            )
            
            records = Entrez.read(fetch_handle)
            fetch_handle.close()
            
            if records['PubmedArticle']:
                paper = self._parse_pubmed_record(records['PubmedArticle'][0])
                if paper:
                    paper.source = self.source
                return paper
            
            return None
        
        except Exception as e:
            logger.error(f"Error fetching PubMed paper details for PMID {pmid}: {e}")
            return None
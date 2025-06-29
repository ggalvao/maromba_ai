from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy import (
    Column, Integer, String, Text, ARRAY, DateTime, Float, 
    CheckConstraint, Index, text, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
import uuid

Base = declarative_base()

class Paper(Base):
    __tablename__ = 'papers'
    
    id = Column(Integer, primary_key=True)
    title = Column(Text, nullable=False)
    authors = Column(ARRAY(Text))
    journal = Column(String(255))
    year = Column(Integer)
    doi = Column(String(255), unique=True)
    pmid = Column(String(50))
    semantic_scholar_id = Column(String(100))
    arxiv_id = Column(String(50))
    abstract = Column(Text)
    full_text = Column(Text)
    sections = Column(JSONB)  # {abstract, methods, results, conclusions}
    domain = Column(String(50))  # load_progression, deload_timing, etc.
    source = Column(String(50))  # pubmed, semantic_scholar, etc.
    quality_score = Column(Integer, CheckConstraint('quality_score >= 1 AND quality_score <= 10'))
    relevance_score = Column(Float, CheckConstraint('relevance_score >= 0 AND relevance_score <= 1'))
    citation_count = Column(Integer, default=0)
    pdf_path = Column(String(500))
    pdf_url = Column(Text)
    metadata = Column(JSONB)
    embedding = Column(Vector(768))  # Using sentence-transformers all-MiniLM-L6-v2
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_papers_doi', 'doi'),
        Index('idx_papers_pmid', 'pmid'),
        Index('idx_papers_domain', 'domain'),
        Index('idx_papers_source', 'source'),
        Index('idx_papers_year', 'year'),
        Index('idx_papers_quality_score', 'quality_score'),
        Index('idx_papers_relevance_score', 'relevance_score'),
        Index('idx_papers_title_gin', text("to_tsvector('english', title)"), postgresql_using='gin'),
        Index('idx_papers_abstract_gin', text("to_tsvector('english', abstract)"), postgresql_using='gin'),
        Index('idx_papers_embedding_cosine', 'embedding', postgresql_using='ivfflat', 
              postgresql_with={'lists': 100}, postgresql_ops={'embedding': 'vector_cosine_ops'}),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'authors': self.authors,
            'journal': self.journal,
            'year': self.year,
            'doi': self.doi,
            'pmid': self.pmid,
            'semantic_scholar_id': self.semantic_scholar_id,
            'arxiv_id': self.arxiv_id,
            'abstract': self.abstract,
            'domain': self.domain,
            'source': self.source,
            'quality_score': self.quality_score,
            'relevance_score': self.relevance_score,
            'citation_count': self.citation_count,
            'pdf_path': self.pdf_path,
            'pdf_url': self.pdf_url,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

class SearchHistory(Base):
    __tablename__ = 'search_history'
    
    id = Column(Integer, primary_key=True)
    domain = Column(String(50))
    query_text = Column(Text, nullable=False)
    source = Column(String(50))
    results_count = Column(Integer, default=0)
    execution_time = Column(String(50))  # Store as string representation of timedelta
    created_at = Column(DateTime, default=datetime.utcnow)

class CollectionStats(Base):
    __tablename__ = 'collection_stats'
    
    id = Column(Integer, primary_key=True)
    domain = Column(String(50))
    source = Column(String(50))
    total_papers = Column(Integer, default=0)
    successful_downloads = Column(Integer, default=0)
    failed_downloads = Column(Integer, default=0)
    duplicates_found = Column(Integer, default=0)
    avg_quality_score = Column(Float)
    collection_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
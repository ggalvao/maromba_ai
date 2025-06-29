from typing import List, Optional, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from sqlalchemy import text
from loguru import logger
from .models import Paper

class EmbeddingManager:
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        self.model_name = model_name
        self.model = None
        self._load_model()
    
    def _load_model(self):
        try:
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"Loaded embedding model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load embedding model {self.model_name}: {e}")
            raise
    
    def generate_embedding(self, text: str) -> List[float]:
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding generation")
            return [0.0] * 384  # Return zero vector for empty text
        
        try:
            embedding = self.model.encode(text, convert_to_tensor=False)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Failed to generate embedding for text: {e}")
            return [0.0] * 384
    
    def generate_paper_embedding(self, paper_data: dict) -> List[float]:
        # Combine title and abstract for embedding generation
        text_parts = []
        
        if paper_data.get('title'):
            text_parts.append(paper_data['title'])
        
        if paper_data.get('abstract'):
            text_parts.append(paper_data['abstract'])
        
        combined_text = ' '.join(text_parts)
        return self.generate_embedding(combined_text)
    
    def find_similar_papers(
        self, 
        session: Session, 
        query_embedding: List[float], 
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[Tuple[Paper, float]]:
        try:
            # Convert embedding to string format for SQL
            embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
            
            # Use cosine similarity search
            query = text(f"""
                SELECT *, 1 - (embedding <=> '{embedding_str}') as similarity
                FROM papers 
                WHERE embedding IS NOT NULL
                AND 1 - (embedding <=> '{embedding_str}') > :threshold
                ORDER BY embedding <=> '{embedding_str}'
                LIMIT :limit
            """)
            
            result = session.execute(
                query, 
                {'threshold': similarity_threshold, 'limit': limit}
            )
            
            papers_with_similarity = []
            for row in result:
                paper = session.get(Paper, row.id)
                if paper:
                    papers_with_similarity.append((paper, row.similarity))
            
            return papers_with_similarity
        
        except Exception as e:
            logger.error(f"Failed to find similar papers: {e}")
            return []
    
    def update_paper_embedding(self, session: Session, paper_id: int) -> bool:
        try:
            paper = session.get(Paper, paper_id)
            if not paper:
                logger.warning(f"Paper with ID {paper_id} not found")
                return False
            
            paper_data = {
                'title': paper.title,
                'abstract': paper.abstract
            }
            
            embedding = self.generate_paper_embedding(paper_data)
            paper.embedding = embedding
            
            session.commit()
            logger.info(f"Updated embedding for paper ID {paper_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to update embedding for paper ID {paper_id}: {e}")
            session.rollback()
            return False
    
    def batch_update_embeddings(self, session: Session, batch_size: int = 100) -> int:
        try:
            # Get papers without embeddings
            papers_without_embeddings = session.query(Paper).filter(
                Paper.embedding.is_(None)
            ).limit(batch_size).all()
            
            updated_count = 0
            for paper in papers_without_embeddings:
                paper_data = {
                    'title': paper.title,
                    'abstract': paper.abstract
                }
                
                embedding = self.generate_paper_embedding(paper_data)
                paper.embedding = embedding
                updated_count += 1
            
            session.commit()
            logger.info(f"Updated embeddings for {updated_count} papers")
            return updated_count
        
        except Exception as e:
            logger.error(f"Failed to batch update embeddings: {e}")
            session.rollback()
            return 0
    
    def get_embedding_stats(self, session: Session) -> dict:
        try:
            total_papers = session.query(Paper).count()
            papers_with_embeddings = session.query(Paper).filter(
                Paper.embedding.is_not(None)
            ).count()
            
            return {
                'total_papers': total_papers,
                'papers_with_embeddings': papers_with_embeddings,
                'papers_without_embeddings': total_papers - papers_with_embeddings,
                'embedding_coverage': papers_with_embeddings / total_papers if total_papers > 0 else 0
            }
        
        except Exception as e:
            logger.error(f"Failed to get embedding stats: {e}")
            return {
                'total_papers': 0,
                'papers_with_embeddings': 0,
                'papers_without_embeddings': 0,
                'embedding_coverage': 0
            }
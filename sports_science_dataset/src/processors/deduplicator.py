from typing import List, Dict, Set, Tuple, Optional
import re
from difflib import SequenceMatcher
from fuzzywuzzy import fuzz
from loguru import logger
from ..collectors.base_collector import PaperMetadata

class Deduplicator:
    def __init__(
        self,
        title_similarity_threshold: float = 0.85,
        doi_priority: bool = True,
        author_similarity_threshold: float = 0.7
    ):
        self.title_similarity_threshold = title_similarity_threshold
        self.doi_priority = doi_priority
        self.author_similarity_threshold = author_similarity_threshold
        
        # Statistics tracking
        self.total_papers_processed = 0
        self.duplicates_found = 0
        self.doi_matches = 0
        self.title_matches = 0
        self.author_title_matches = 0
    
    def deduplicate_papers(self, papers: List[PaperMetadata]) -> List[PaperMetadata]:
        """Main deduplication method"""
        self.total_papers_processed = len(papers)
        logger.info(f"Starting deduplication of {len(papers)} papers")
        
        # Step 1: Remove exact DOI duplicates
        papers = self._remove_doi_duplicates(papers)
        
        # Step 2: Remove title-based duplicates
        papers = self._remove_title_duplicates(papers)
        
        # Step 3: Remove author+title combination duplicates
        papers = self._remove_author_title_duplicates(papers)
        
        # Step 4: Handle special cases (preprints vs published versions)
        papers = self._handle_preprint_duplicates(papers)
        
        logger.info(f"Deduplication complete: {len(papers)} unique papers remaining")
        logger.info(f"Removed {self.duplicates_found} duplicates ({self.duplicates_found/self.total_papers_processed*100:.1f}%)")
        
        return papers
    
    def _remove_doi_duplicates(self, papers: List[PaperMetadata]) -> List[PaperMetadata]:
        """Remove papers with identical DOIs"""
        seen_dois = set()
        unique_papers = []
        
        for paper in papers:
            if paper.doi:
                # Normalize DOI
                normalized_doi = self._normalize_doi(paper.doi)
                
                if normalized_doi not in seen_dois:
                    seen_dois.add(normalized_doi)
                    unique_papers.append(paper)
                else:
                    self.duplicates_found += 1
                    self.doi_matches += 1
                    logger.debug(f"DOI duplicate removed: {paper.title[:50]}...")
            else:
                unique_papers.append(paper)
        
        logger.info(f"DOI deduplication: {len(papers)} -> {len(unique_papers)} papers")
        return unique_papers
    
    def _remove_title_duplicates(self, papers: List[PaperMetadata]) -> List[PaperMetadata]:
        """Remove papers with highly similar titles"""
        unique_papers = []
        
        for i, paper in enumerate(papers):
            is_duplicate = False
            normalized_title = self._normalize_title(paper.title)
            
            # Compare with already processed papers
            for existing_paper in unique_papers:
                existing_title = self._normalize_title(existing_paper.title)
                
                similarity = self._calculate_title_similarity(normalized_title, existing_title)
                
                if similarity >= self.title_similarity_threshold:
                    # Choose the better paper (prefer published over preprint, more citations, etc.)
                    if self._should_keep_existing(existing_paper, paper):
                        is_duplicate = True
                        self.duplicates_found += 1
                        self.title_matches += 1
                        logger.debug(f"Title duplicate removed: {paper.title[:50]}...")
                        break
                    else:
                        # Replace existing paper with the new one
                        unique_papers.remove(existing_paper)
                        self.duplicates_found += 1
                        self.title_matches += 1
                        logger.debug(f"Title duplicate replaced: {existing_paper.title[:50]}...")
                        break
            
            if not is_duplicate:
                unique_papers.append(paper)
        
        logger.info(f"Title deduplication: {len(papers)} -> {len(unique_papers)} papers")
        return unique_papers
    
    def _remove_author_title_duplicates(self, papers: List[PaperMetadata]) -> List[PaperMetadata]:
        """Remove papers with similar authors and titles (handles variations)"""
        unique_papers = []
        
        for paper in papers:
            is_duplicate = False
            
            for existing_paper in unique_papers:
                # Check if authors are similar
                author_similarity = self._calculate_author_similarity(paper.authors, existing_paper.authors)
                
                # Check if titles are moderately similar (lower threshold than pure title matching)
                title_similarity = self._calculate_title_similarity(
                    self._normalize_title(paper.title),
                    self._normalize_title(existing_paper.title)
                )
                
                # If both authors and titles are similar, consider it a duplicate
                if (author_similarity >= self.author_similarity_threshold and 
                    title_similarity >= 0.7):  # Lower threshold for title when authors match
                    
                    if self._should_keep_existing(existing_paper, paper):
                        is_duplicate = True
                        self.duplicates_found += 1
                        self.author_title_matches += 1
                        logger.debug(f"Author+Title duplicate removed: {paper.title[:50]}...")
                        break
                    else:
                        unique_papers.remove(existing_paper)
                        self.duplicates_found += 1
                        self.author_title_matches += 1
                        logger.debug(f"Author+Title duplicate replaced: {existing_paper.title[:50]}...")
                        break
            
            if not is_duplicate:
                unique_papers.append(paper)
        
        logger.info(f"Author+Title deduplication: {len(papers)} -> {len(unique_papers)} papers")
        return unique_papers
    
    def _handle_preprint_duplicates(self, papers: List[PaperMetadata]) -> List[PaperMetadata]:
        """Handle cases where both preprint and published versions exist"""
        unique_papers = []
        
        # Group papers by normalized title and authors
        paper_groups = {}
        
        for paper in papers:
            key = self._create_paper_key(paper)
            
            if key not in paper_groups:
                paper_groups[key] = []
            paper_groups[key].append(paper)
        
        # For each group, keep the best version
        for group in paper_groups.values():
            if len(group) == 1:
                unique_papers.append(group[0])
            else:
                # Multiple versions found - choose the best one
                best_paper = self._choose_best_version(group)
                unique_papers.append(best_paper)
                
                self.duplicates_found += len(group) - 1
                logger.debug(f"Preprint handling: kept {best_paper.source} version of '{best_paper.title[:50]}...'")
        
        logger.info(f"Preprint handling: {len(papers)} -> {len(unique_papers)} papers")
        return unique_papers
    
    def _normalize_doi(self, doi: str) -> str:
        """Normalize DOI for comparison"""
        if not doi:
            return ""
        
        # Remove common prefixes and clean up
        doi = doi.lower().strip()
        doi = re.sub(r'^(doi:|https?://doi\.org/|https?://dx\.doi\.org/)', '', doi)
        doi = re.sub(r'\s+', '', doi)  # Remove whitespace
        
        return doi
    
    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison"""
        if not title:
            return ""
        
        # Convert to lowercase and remove punctuation
        title = title.lower()
        title = re.sub(r'[^\w\s]', ' ', title)
        title = re.sub(r'\s+', ' ', title)
        title = title.strip()
        
        # Remove common words that don't affect meaning
        stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        words = [word for word in title.split() if word not in stop_words]
        
        return ' '.join(words)
    
    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles"""
        if not title1 or not title2:
            return 0.0
        
        # Use multiple similarity metrics and take the maximum
        ratio = fuzz.ratio(title1, title2) / 100.0
        token_sort_ratio = fuzz.token_sort_ratio(title1, title2) / 100.0
        token_set_ratio = fuzz.token_set_ratio(title1, title2) / 100.0
        
        return max(ratio, token_sort_ratio, token_set_ratio)
    
    def _calculate_author_similarity(self, authors1: List[str], authors2: List[str]) -> float:
        """Calculate similarity between author lists"""
        if not authors1 or not authors2:
            return 0.0
        
        # Normalize author names
        norm_authors1 = [self._normalize_author_name(name) for name in authors1]
        norm_authors2 = [self._normalize_author_name(name) for name in authors2]
        
        # Calculate Jaccard similarity
        set1 = set(norm_authors1)
        set2 = set(norm_authors2)
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def _normalize_author_name(self, name: str) -> str:
        """Normalize author name for comparison"""
        if not name:
            return ""
        
        # Remove titles and degrees
        name = re.sub(r'\b(Dr|Prof|PhD|MD|MSc|BSc)\.?\b', '', name, flags=re.IGNORECASE)
        
        # Convert to lowercase and remove extra spaces
        name = re.sub(r'\s+', ' ', name.lower().strip())
        
        # Handle different name formats (Last, First vs First Last)
        if ',' in name:
            parts = name.split(',')
            if len(parts) == 2:
                last_name = parts[0].strip()
                first_name = parts[1].strip()
                # Take first initial + last name
                if first_name:
                    return f"{first_name[0]} {last_name}"
                return last_name
        
        # For "First Last" format, take first initial + last word
        parts = name.split()
        if len(parts) >= 2:
            return f"{parts[0][0]} {parts[-1]}"
        
        return name
    
    def _should_keep_existing(self, existing: PaperMetadata, new: PaperMetadata) -> bool:
        """Decide which paper to keep when duplicates are found"""
        
        # Priority 1: Prefer papers with DOI
        if existing.doi and not new.doi:
            return True
        if new.doi and not existing.doi:
            return False
        
        # Priority 2: Prefer published over preprint
        existing_is_preprint = existing.source == 'arxiv' or 'preprint' in (existing.journal or '').lower()
        new_is_preprint = new.source == 'arxiv' or 'preprint' in (new.journal or '').lower()
        
        if not existing_is_preprint and new_is_preprint:
            return True
        if existing_is_preprint and not new_is_preprint:
            return False
        
        # Priority 3: Prefer papers with more citations
        existing_citations = existing.citation_count or 0
        new_citations = new.citation_count or 0
        
        if existing_citations != new_citations:
            return existing_citations > new_citations
        
        # Priority 4: Prefer more recent papers
        if existing.year and new.year:
            if existing.year != new.year:
                return existing.year > new.year
        
        # Priority 5: Prefer papers with abstracts
        if existing.abstract and not new.abstract:
            return True
        if new.abstract and not existing.abstract:
            return False
        
        # Default: keep existing
        return True
    
    def _create_paper_key(self, paper: PaperMetadata) -> str:
        """Create a key for grouping similar papers"""
        title_key = self._normalize_title(paper.title)[:50]  # First 50 chars
        
        # Create author key from first few authors
        author_keys = []
        for author in (paper.authors or [])[:3]:  # First 3 authors
            normalized = self._normalize_author_name(author)
            if normalized:
                author_keys.append(normalized)
        
        author_key = '|'.join(sorted(author_keys))
        
        return f"{title_key}#{author_key}"
    
    def _choose_best_version(self, papers: List[PaperMetadata]) -> PaperMetadata:
        """Choose the best version from a group of similar papers"""
        # Sort by preference
        def sort_key(paper):
            score = 0
            
            # Prefer papers with DOI
            if paper.doi:
                score += 100
            
            # Prefer published over preprint
            if paper.source != 'arxiv' and 'preprint' not in (paper.journal or '').lower():
                score += 50
            
            # Prefer papers with more citations
            score += (paper.citation_count or 0)
            
            # Prefer more recent papers
            if paper.year:
                score += paper.year * 0.1
            
            # Prefer papers with abstracts
            if paper.abstract:
                score += 10
            
            return score
        
        return max(papers, key=sort_key)
    
    def get_deduplication_stats(self) -> Dict[str, any]:
        """Get statistics about the deduplication process"""
        return {
            'total_papers_processed': self.total_papers_processed,
            'duplicates_found': self.duplicates_found,
            'duplicate_rate': self.duplicates_found / self.total_papers_processed if self.total_papers_processed > 0 else 0,
            'doi_matches': self.doi_matches,
            'title_matches': self.title_matches,
            'author_title_matches': self.author_title_matches,
            'unique_papers_remaining': self.total_papers_processed - self.duplicates_found
        }
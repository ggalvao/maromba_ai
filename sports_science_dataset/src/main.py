#!/usr/bin/env python3
"""
Sports Science Literature Dataset Builder
Main orchestration script for automated literature collection pipeline
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
import click
from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

# Add src to path for imports
sys.path.append(str(Path(__file__).parent))

from collectors import PubMedCollector, SemanticScholarCollector, ArxivCollector
from processors import PDFProcessor, AIFilter, Deduplicator
from database import DatabaseManager, get_session, Paper, SearchHistory, CollectionStats, EmbeddingManager

# Load environment variables
load_dotenv()

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

# Initialize console for rich output
console = Console()

# Domain search queries
DOMAIN_QUERIES = {
    "load_progression": [
        "progressive overload strength training",
        "training load progression resistance",
        "autoregulation training load RPE"
    ],
    "deload_timing": [
        "deload fatigue monitoring training",
        "training reduction recovery protocols",
        "overreaching detection biomarkers"
    ],
    "exercise_selection": [
        "exercise selection biomechanics muscle activation",
        "compound isolation exercise effectiveness",
        "movement pattern optimization training"
    ],
    "periodization": [
        "periodization strength training athletes",
        "block periodization linear undulating",
        "competition preparation peaking strategies"
    ]
}

class SportsScienteDatasetBuilder:
    def __init__(self):
        self.setup_environment()
        self.initialize_components()
        
    def setup_environment(self):
        """Setup environment and validate configuration"""
        # Validate required environment variables
        required_vars = ["OPENAI_API_KEY", "NCBI_EMAIL"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {missing_vars}")
            sys.exit(1)
        
        # Setup directories
        self.raw_papers_dir = Path(os.getenv("RAW_PAPERS_DIR", "./data/raw_papers"))
        self.processed_papers_dir = Path(os.getenv("PROCESSED_PAPERS_DIR", "./data/processed_papers"))
        self.logs_dir = Path(os.getenv("LOGS_DIR", "./data/logs"))
        
        for directory in [self.raw_papers_dir, self.processed_papers_dir, self.logs_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Collection parameters
        self.target_papers_per_domain = int(os.getenv("TARGET_PAPERS_PER_DOMAIN", "50"))
        self.min_quality_score = int(os.getenv("MINIMUM_QUALITY_SCORE", "6"))
        self.min_relevance_score = float(os.getenv("MINIMUM_RELEVANCE_SCORE", "0.6"))
        self.max_concurrent_downloads = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "5"))
        
    def initialize_components(self):
        """Initialize all pipeline components"""
        # Database
        self.db_manager = DatabaseManager(
            os.getenv("DATABASE_URL", "postgresql://admin:sports_science_password@localhost:5432/sports_science")
        )
        
        # Collectors
        self.pubmed_collector = PubMedCollector(
            email=os.getenv("NCBI_EMAIL"),
            rate_limit=float(os.getenv("PUBMED_RATE_LIMIT", "3"))
        )
        
        self.semantic_scholar_collector = SemanticScholarCollector(
            api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
            rate_limit=float(os.getenv("SEMANTIC_SCHOLAR_RATE_LIMIT", "100")) / 60  # Convert to per second
        )
        
        self.arxiv_collector = ArxivCollector(
            rate_limit=float(os.getenv("ARXIV_RATE_LIMIT", "10")) / 60  # Convert to per second
        )
        
        # Processors
        self.pdf_processor = PDFProcessor(download_dir=str(self.raw_papers_dir))
        self.ai_filter = AIFilter(api_key=os.getenv("OPENAI_API_KEY"))
        self.deduplicator = Deduplicator()
        self.embedding_manager = EmbeddingManager()
        
    def run_collection_pipeline(self, domains: Optional[List[str]] = None):
        """Run the complete collection pipeline"""
        if domains is None:
            domains = list(DOMAIN_QUERIES.keys())
            
        logger.info(f"Starting collection pipeline for domains: {domains}")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            
            main_task = progress.add_task("Overall Progress", total=len(domains))
            
            for domain in domains:
                domain_task = progress.add_task(f"Processing {domain}", total=7)
                
                try:
                    # Step 1: Collect papers from all sources
                    progress.update(domain_task, description=f"Collecting papers for {domain}")
                    papers = self.collect_papers_for_domain(domain)
                    progress.advance(domain_task)
                    
                    # Step 2: Deduplicate papers
                    progress.update(domain_task, description=f"Deduplicating papers")
                    unique_papers = self.deduplicator.deduplicate_papers(papers)
                    progress.advance(domain_task)
                    
                    # Step 3: AI filtering
                    progress.update(domain_task, description=f"AI filtering papers")
                    filtered_papers = self.filter_papers_with_ai(unique_papers, domain)
                    progress.advance(domain_task)
                    
                    # Step 4: Download and process PDFs
                    progress.update(domain_task, description=f"Processing PDFs")
                    papers_with_text = self.process_pdfs(filtered_papers)
                    progress.advance(domain_task)
                    
                    # Step 5: Generate embeddings
                    progress.update(domain_task, description=f"Generating embeddings")
                    papers_with_embeddings = self.generate_embeddings(papers_with_text)
                    progress.advance(domain_task)
                    
                    # Step 6: Store in database
                    progress.update(domain_task, description=f"Storing in database")
                    self.store_papers_in_database(papers_with_embeddings, domain)
                    progress.advance(domain_task)
                    
                    # Step 7: Update statistics
                    progress.update(domain_task, description=f"Updating statistics")
                    self.update_collection_stats(domain, papers, filtered_papers)
                    progress.advance(domain_task)
                    
                    progress.update(domain_task, description=f"✅ Completed {domain}")
                    
                except Exception as e:
                    logger.error(f"Error processing domain {domain}: {e}")
                    progress.update(domain_task, description=f"❌ Failed {domain}")
                
                progress.advance(main_task)
        
        logger.info("Collection pipeline completed")
        self.generate_final_report()
    
    def collect_papers_for_domain(self, domain: str) -> List:
        """Collect papers from all sources for a domain"""
        all_papers = []
        queries = DOMAIN_QUERIES[domain]
        
        for query in queries:
            logger.info(f"Collecting papers for query: {query}")
            
            # PubMed
            try:
                pubmed_papers = self.pubmed_collector.search_papers(
                    query, 
                    max_results=self.target_papers_per_domain // len(queries)
                )
                for paper in pubmed_papers:
                    paper.domain = domain
                all_papers.extend(pubmed_papers)
                logger.info(f"PubMed: {len(pubmed_papers)} papers")
            except Exception as e:
                logger.error(f"PubMed collection failed: {e}")
            
            # Semantic Scholar
            try:
                ss_papers = self.semantic_scholar_collector.search_papers(
                    query,
                    max_results=self.target_papers_per_domain // len(queries)
                )
                for paper in ss_papers:
                    paper.domain = domain
                all_papers.extend(ss_papers)
                logger.info(f"Semantic Scholar: {len(ss_papers)} papers")
            except Exception as e:
                logger.error(f"Semantic Scholar collection failed: {e}")
            
            # arXiv
            try:
                arxiv_papers = self.arxiv_collector.search_papers(
                    query,
                    max_results=self.target_papers_per_domain // len(queries) // 2  # Fewer from arXiv
                )
                for paper in arxiv_papers:
                    paper.domain = domain
                all_papers.extend(arxiv_papers)
                logger.info(f"arXiv: {len(arxiv_papers)} papers")
            except Exception as e:
                logger.error(f"arXiv collection failed: {e}")
        
        logger.info(f"Total papers collected for {domain}: {len(all_papers)}")
        return all_papers
    
    def filter_papers_with_ai(self, papers, domain: str):
        """Filter papers using AI assessment"""
        logger.info(f"Starting AI filtering for {len(papers)} papers")
        
        filtered_results = self.ai_filter.batch_assess_papers(
            papers,
            domain,
            min_relevance_score=self.min_relevance_score,
            min_quality_score=self.min_quality_score
        )
        
        # Extract papers and store assessments
        filtered_papers = []
        for paper, assessment in filtered_results:
            # Add assessment to paper metadata
            if not paper.metadata:
                paper.metadata = {}
            paper.metadata['ai_assessment'] = assessment
            filtered_papers.append(paper)
        
        logger.info(f"AI filtering complete: {len(filtered_papers)} papers passed")
        return filtered_papers
    
    def process_pdfs(self, papers):
        """Download and process PDFs for papers"""
        papers_with_text = []
        
        for paper in papers:
            if paper.pdf_url:
                try:
                    # Generate unique paper ID for filename
                    paper_id = f"{paper.source}_{paper.pmid or paper.semantic_scholar_id or paper.arxiv_id}"
                    
                    result = self.pdf_processor.process_pdf_complete(paper.pdf_url, paper_id)
                    
                    if result['success']:
                        # Add extracted text to paper
                        if not paper.metadata:
                            paper.metadata = {}
                        
                        paper.metadata['pdf_processing'] = {
                            'file_path': result['file_path'],
                            'page_count': result['page_count'],
                            'word_count': result['word_count'],
                            'pdf_metadata': result['pdf_metadata']
                        }
                        
                        # Update paper with full text and sections
                        paper.metadata['full_text'] = result['full_text']
                        paper.metadata['sections'] = result['sections']
                        
                        papers_with_text.append(paper)
                        logger.debug(f"PDF processed: {paper.title[:50]}...")
                    else:
                        # Still include paper even if PDF processing failed
                        papers_with_text.append(paper)
                        logger.warning(f"PDF processing failed: {paper.title[:50]}...")
                
                except Exception as e:
                    logger.error(f"Error processing PDF for paper: {e}")
                    papers_with_text.append(paper)  # Include paper anyway
            else:
                papers_with_text.append(paper)
        
        logger.info(f"PDF processing complete: {len(papers_with_text)} papers")
        return papers_with_text
    
    def generate_embeddings(self, papers):
        """Generate embeddings for papers"""
        papers_with_embeddings = []
        
        for paper in papers:
            try:
                paper_data = {
                    'title': paper.title,
                    'abstract': paper.abstract
                }
                
                embedding = self.embedding_manager.generate_paper_embedding(paper_data)
                
                # Add embedding to paper metadata
                if not paper.metadata:
                    paper.metadata = {}
                paper.metadata['embedding'] = embedding
                
                papers_with_embeddings.append(paper)
                
            except Exception as e:
                logger.error(f"Error generating embedding: {e}")
                papers_with_embeddings.append(paper)  # Include without embedding
        
        logger.info(f"Embedding generation complete: {len(papers_with_embeddings)} papers")
        return papers_with_embeddings
    
    def store_papers_in_database(self, papers, domain: str):
        """Store papers in the database"""
        stored_count = 0
        
        with get_session() as session:
            for paper in papers:
                try:
                    # Check if paper already exists (by DOI or PMID)
                    existing_paper = None
                    if paper.doi:
                        existing_paper = session.query(Paper).filter(Paper.doi == paper.doi).first()
                    elif paper.pmid:
                        existing_paper = session.query(Paper).filter(Paper.pmid == paper.pmid).first()
                    
                    if existing_paper:
                        logger.debug(f"Paper already exists in database: {paper.title[:50]}...")
                        continue
                    
                    # Create new paper record
                    db_paper = Paper(
                        title=paper.title,
                        authors=paper.authors,
                        journal=paper.journal,
                        year=paper.year,
                        doi=paper.doi,
                        pmid=paper.pmid,
                        semantic_scholar_id=paper.semantic_scholar_id,
                        arxiv_id=paper.arxiv_id,
                        abstract=paper.abstract,
                        full_text=paper.metadata.get('full_text') if paper.metadata else None,
                        sections=paper.metadata.get('sections') if paper.metadata else None,
                        domain=domain,
                        source=paper.source,
                        quality_score=paper.metadata.get('ai_assessment', {}).get('quality_score') if paper.metadata else None,
                        relevance_score=paper.metadata.get('ai_assessment', {}).get('relevance_score') if paper.metadata else None,
                        citation_count=paper.citation_count,
                        pdf_path=paper.metadata.get('pdf_processing', {}).get('file_path') if paper.metadata else None,
                        pdf_url=paper.pdf_url,
                        metadata=paper.metadata,
                        embedding=paper.metadata.get('embedding') if paper.metadata else None
                    )
                    
                    session.add(db_paper)
                    stored_count += 1
                    
                except Exception as e:
                    logger.error(f"Error storing paper in database: {e}")
                    session.rollback()
                    continue
            
            session.commit()
        
        logger.info(f"Stored {stored_count} papers in database for domain {domain}")
    
    def update_collection_stats(self, domain: str, original_papers, filtered_papers):
        """Update collection statistics"""
        with get_session() as session:
            for source in ['pubmed', 'semantic_scholar', 'arxiv']:
                original_count = len([p for p in original_papers if p.source == source])
                filtered_count = len([p for p in filtered_papers if p.source == source])
                
                # Update or create stats record
                stats = session.query(CollectionStats).filter(
                    CollectionStats.domain == domain,
                    CollectionStats.source == source
                ).first()
                
                if stats:
                    stats.total_papers = original_count
                    stats.successful_downloads = filtered_count
                    stats.failed_downloads = original_count - filtered_count
                else:
                    stats = CollectionStats(
                        domain=domain,
                        source=source,
                        total_papers=original_count,
                        successful_downloads=filtered_count,
                        failed_downloads=original_count - filtered_count
                    )
                    session.add(stats)
            
            session.commit()
    
    def generate_final_report(self):
        """Generate final collection report"""
        with get_session() as session:
            # Get overall statistics
            total_papers = session.query(Paper).count()
            
            # Create summary table
            table = Table(title="Sports Science Dataset Collection Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Total Papers Collected", str(total_papers))
            
            # Domain breakdown
            for domain in DOMAIN_QUERIES.keys():
                domain_count = session.query(Paper).filter(Paper.domain == domain).count()
                table.add_row(f"{domain.title()} Papers", str(domain_count))
            
            # Source breakdown
            for source in ['pubmed', 'semantic_scholar', 'arxiv']:
                source_count = session.query(Paper).filter(Paper.source == source).count()
                table.add_row(f"{source.title()} Papers", str(source_count))
            
            # Quality metrics
            avg_quality = session.query(Paper.quality_score).filter(Paper.quality_score.is_not(None)).all()
            if avg_quality:
                avg_quality_score = sum(score[0] for score in avg_quality) / len(avg_quality)
                table.add_row("Average Quality Score", f"{avg_quality_score:.1f}")
            
            avg_relevance = session.query(Paper.relevance_score).filter(Paper.relevance_score.is_not(None)).all()
            if avg_relevance:
                avg_relevance_score = sum(score[0] for score in avg_relevance) / len(avg_relevance)
                table.add_row("Average Relevance Score", f"{avg_relevance_score:.2f}")
            
            console.print(table)
            
            # Save report to file
            report_path = self.logs_dir / "collection_report.txt"
            with open(report_path, 'w') as f:
                console.print(table, file=f)
            
            logger.info(f"Collection report saved to: {report_path}")

@click.command()
@click.option('--domains', default=None, help='Comma-separated list of domains to process')
@click.option('--setup-db', is_flag=True, help='Setup database tables')
@click.option('--test-connection', is_flag=True, help='Test database connection')
def main(domains, setup_db, test_connection):
    """Sports Science Literature Dataset Builder"""
    
    try:
        builder = SportsScienteDatasetBuilder()
        
        if test_connection:
            if builder.db_manager.test_connection():
                console.print("✅ Database connection successful", style="green")
            else:
                console.print("❌ Database connection failed", style="red")
                sys.exit(1)
            return
        
        if setup_db:
            builder.db_manager.create_tables()
            console.print("✅ Database tables created", style="green")
            return
        
        # Parse domains
        domain_list = None
        if domains:
            domain_list = [d.strip() for d in domains.split(',')]
            invalid_domains = [d for d in domain_list if d not in DOMAIN_QUERIES]
            if invalid_domains:
                console.print(f"❌ Invalid domains: {invalid_domains}", style="red")
                console.print(f"Valid domains: {list(DOMAIN_QUERIES.keys())}", style="yellow")
                sys.exit(1)
        
        # Run the collection pipeline
        builder.run_collection_pipeline(domain_list)
        
    except KeyboardInterrupt:
        console.print("\n⚠️ Collection interrupted by user", style="yellow")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        console.print(f"❌ Fatal error: {e}", style="red")
        sys.exit(1)

if __name__ == "__main__":
    main()
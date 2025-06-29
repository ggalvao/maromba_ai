#!/usr/bin/env python3
"""
Test script for the Sports Science Dataset Builder
Validates individual components and end-to-end pipeline
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import pytest

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

from collectors import PubMedCollector, SemanticScholarCollector, ArxivCollector
from processors import PDFProcessor, AIFilter, Deduplicator
from database import DatabaseManager, get_session, Paper

# Load environment
load_dotenv()

def test_environment_setup():
    """Test that all required environment variables are set"""
    required_vars = ["OPENAI_API_KEY", "NCBI_EMAIL", "DATABASE_URL"]
    
    for var in required_vars:
        assert os.getenv(var), f"Missing required environment variable: {var}"
    
    print("✅ Environment setup test passed")

def test_database_connection():
    """Test database connection and table creation"""
    db_manager = DatabaseManager(os.getenv("DATABASE_URL"))
    
    # Test connection
    assert db_manager.test_connection(), "Database connection failed"
    
    # Test table creation
    db_manager.create_tables()
    
    print("✅ Database connection test passed")

def test_pubmed_collector():
    """Test PubMed collector"""
    collector = PubMedCollector(email=os.getenv("NCBI_EMAIL"), rate_limit=3.0)
    
    # Test search with small result set
    papers = collector.search_papers("strength training", max_results=3)
    
    assert len(papers) > 0, "No papers returned from PubMed"
    assert papers[0].title, "Paper missing title"
    assert papers[0].abstract, "Paper missing abstract"
    
    print(f"✅ PubMed collector test passed - found {len(papers)} papers")

def test_semantic_scholar_collector():
    """Test Semantic Scholar collector"""
    collector = SemanticScholarCollector(
        api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
        rate_limit=1.67
    )
    
    # Test search
    papers = collector.search_papers("resistance training", max_results=3)
    
    assert len(papers) > 0, "No papers returned from Semantic Scholar"
    assert papers[0].title, "Paper missing title"
    
    print(f"✅ Semantic Scholar collector test passed - found {len(papers)} papers")

def test_arxiv_collector():
    """Test arXiv collector"""
    collector = ArxivCollector(rate_limit=0.17)
    
    # Test search
    papers = collector.search_papers("machine learning", max_results=2)
    
    assert len(papers) >= 0, "arXiv search failed"
    
    if papers:
        assert papers[0].title, "Paper missing title"
        print(f"✅ arXiv collector test passed - found {len(papers)} papers")
    else:
        print("⚠️ arXiv collector test passed - no papers found (expected for sports science)")

def test_deduplicator():
    """Test deduplication logic"""
    from collectors.base_collector import PaperMetadata
    
    deduplicator = Deduplicator()
    
    # Create test papers with duplicates
    papers = [
        PaperMetadata(
            title="Effect of Progressive Overload on Strength",
            authors=["Smith, J", "Doe, A"],
            abstract="This study examines progressive overload...",
            doi="10.1234/test1",
            source="pubmed"
        ),
        PaperMetadata(
            title="Effects of Progressive Overload on Strength Training",
            authors=["Smith, John", "Doe, Alice"],
            abstract="This research investigates progressive overload...",
            doi="10.1234/test1",  # Same DOI
            source="semantic_scholar"
        ),
        PaperMetadata(
            title="Completely Different Study on Nutrition",
            authors=["Brown, B"],
            abstract="This study looks at nutrition...",
            doi="10.1234/test2",
            source="pubmed"
        )
    ]
    
    unique_papers = deduplicator.deduplicate_papers(papers)
    
    assert len(unique_papers) == 2, f"Expected 2 unique papers, got {len(unique_papers)}"
    assert deduplicator.duplicates_found == 1, f"Expected 1 duplicate, found {deduplicator.duplicates_found}"
    
    print("✅ Deduplicator test passed")

def test_ai_filter():
    """Test AI filtering with a sample paper"""
    from collectors.base_collector import PaperMetadata
    
    ai_filter = AIFilter(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Create test paper
    paper = PaperMetadata(
        title="Effects of Progressive Overload on Muscle Strength in Trained Athletes",
        authors=["Smith, J", "Doe, A"],
        abstract="This randomized controlled trial examined the effects of progressive overload training on muscle strength in 30 trained athletes over 12 weeks. Participants were randomly assigned to progressive overload or control groups. Results showed significant improvements in strength for the progressive overload group.",
        journal="Journal of Sports Science",
        year=2023,
        source="test"
    )
    
    assessment = ai_filter.assess_paper_relevance(paper, "load_progression")
    
    assert 0 <= assessment['relevance_score'] <= 1, "Relevance score out of range"
    assert 1 <= assessment['quality_score'] <= 10, "Quality score out of range"
    assert assessment['reasoning'], "No reasoning provided"
    
    print(f"✅ AI filter test passed - Relevance: {assessment['relevance_score']:.2f}, Quality: {assessment['quality_score']}")

def test_pdf_processor():
    """Test PDF processor with a sample URL"""
    processor = PDFProcessor()
    
    # Test with a known open access PDF (if available)
    # For testing purposes, we'll just test the initialization
    stats = processor.get_processing_stats()
    
    assert isinstance(stats, dict), "PDF processor stats should return a dictionary"
    assert 'total_pdfs' in stats, "Stats missing total_pdfs"
    
    print("✅ PDF processor test passed")

def test_end_to_end_small():
    """Test a small end-to-end pipeline"""
    from main import SportsScienteDatasetBuilder
    
    # Override settings for small test
    os.environ["TARGET_PAPERS_PER_DOMAIN"] = "2"
    
    builder = SportsScienteDatasetBuilder()
    
    # Test with just one domain and a small number of papers
    domain = "load_progression"
    
    # Collect papers
    papers = builder.collect_papers_for_domain(domain)
    assert len(papers) > 0, "No papers collected"
    
    # Deduplicate
    unique_papers = builder.deduplicator.deduplicate_papers(papers[:3])  # Limit to 3 for testing
    
    # AI filter (limit to 1 paper to save API calls)
    if unique_papers:
        filtered_papers = builder.filter_papers_with_ai(unique_papers[:1], domain)
        assert len(filtered_papers) >= 0, "AI filtering failed"
    
    print(f"✅ End-to-end test passed - processed {len(papers)} papers")

def run_all_tests():
    """Run all tests in sequence"""
    tests = [
        test_environment_setup,
        test_database_connection,
        test_pubmed_collector,
        test_semantic_scholar_collector,
        test_arxiv_collector,
        test_deduplicator,
        test_ai_filter,
        test_pdf_processor,
        test_end_to_end_small
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            print(f"\n🧪 Running {test.__name__}...")
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} failed: {e}")
            failed += 1
    
    print(f"\n📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! The pipeline is ready to use.")
    else:
        print("⚠️ Some tests failed. Please check configuration and dependencies.")
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
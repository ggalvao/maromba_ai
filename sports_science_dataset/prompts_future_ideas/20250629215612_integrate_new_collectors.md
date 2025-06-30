# Integration Guide: Adding Google Scholar and DOAJ Collectors to Pipeline

**Created:** 2025-06-29 21:56:12  
**Status:** Ready for Implementation  
**Difficulty:** Medium  
**Estimated Time:** 2-3 hours  

## Overview

This prompt provides step-by-step instructions to integrate the newly created Google Scholar and DOAJ collectors into the main sports science dataset collection pipeline. These collectors will significantly expand the dataset coverage by adding:

- **Google Scholar**: Massive coverage including grey literature, theses, preprints
- **DOAJ**: High-quality open access journals with downloadable PDFs

## Prerequisites

1. ✅ Google Scholar Collector implemented (`src/collectors/google_scholar_collector.py`)
2. ✅ DOAJ Collector implemented (`src/collectors/doaj_collector.py`) 
3. ✅ New dependencies added to `requirements.txt`
4. ✅ Collectors added to `__init__.py`

## Step-by-Step Integration

### Step 1: Install New Dependencies

```bash
# Navigate to project directory
cd /path/to/sports_science_dataset

# Install new dependencies
../venv/bin/pip install beautifulsoup4==4.12.2 scholarly==1.7.11
```

### Step 2: Update Environment Configuration

Add new environment variables to `config/api_keys.env`:

```bash
# Google Scholar Configuration
# Option 1: Use SerpAPI (Recommended for production - $50/month)
SERPAPI_KEY=your_serpapi_key_here
GOOGLE_SCHOLAR_USE_SERPAPI=true

# Option 2: Use web scraping (Free but risky)
GOOGLE_SCHOLAR_USE_SERPAPI=false

# Rate Limits (requests per second)
GOOGLE_SCHOLAR_RATE_LIMIT=0.03  # 1 request per 30 seconds (very conservative)
DOAJ_RATE_LIMIT=2.0             # 2 requests per second
```

### Step 3: Update Main Pipeline

**File:** `src/main.py`

#### 3.1 Import New Collectors

Add to imports at top of file:

```python
from .collectors import (
    PubMedCollector, 
    SemanticScholarCollector, 
    ArxivCollector,
    GoogleScholarCollector,    # ADD THIS
    DOAJCollector             # ADD THIS
)
```

#### 3.2 Initialize New Collectors

In the `initialize_components()` method, add after existing collectors:

```python
def initialize_components(self):
    # ... existing collector initialization ...
    
    # Google Scholar Collector
    self.google_scholar_collector = GoogleScholarCollector(
        rate_limit=float(os.getenv("GOOGLE_SCHOLAR_RATE_LIMIT", "0.03")),
        use_serpapi=os.getenv("GOOGLE_SCHOLAR_USE_SERPAPI", "false").lower() == "true",
        serpapi_key=os.getenv("SERPAPI_KEY")
    )
    
    # DOAJ Collector  
    self.doaj_collector = DOAJCollector(
        rate_limit=float(os.getenv("DOAJ_RATE_LIMIT", "2.0"))
    )
    
    # ... rest of initialization ...
```

#### 3.3 Add to Collection Pipeline

In the `collect_papers_for_domain()` method, add new collection calls:

```python
def collect_papers_for_domain(self, domain: str) -> List:
    all_papers = []
    queries = DOMAIN_QUERIES[domain]
    
    for query in queries:
        logger.info(f"Collecting papers for query: {query}")
        
        # ... existing PubMed, Semantic Scholar, arXiv collection ...
        
        # Google Scholar
        try:
            gs_papers = self.google_scholar_collector.search_papers(
                query, 
                max_results=self.target_papers_per_domain // len(queries) // 4  # Smaller portion
            )
            for paper in gs_papers:
                paper.domain = domain
            all_papers.extend(gs_papers)
            logger.info(f"Google Scholar: {len(gs_papers)} papers")
        except Exception as e:
            logger.error(f"Google Scholar collection failed: {e}")
        
        # DOAJ
        try:
            doaj_papers = self.doaj_collector.search_papers(
                query,
                max_results=self.target_papers_per_domain // len(queries) // 4
            )
            for paper in doaj_papers:
                paper.domain = domain
            all_papers.extend(doaj_papers)
            logger.info(f"DOAJ: {len(doaj_papers)} papers")
        except Exception as e:
            logger.error(f"DOAJ collection failed: {e}")
    
    logger.info(f"Total papers collected for {domain}: {len(all_papers)}")
    return all_papers
```

#### 3.4 Update Statistics Tracking

In the `update_collection_stats()` method, add new sources:

```python
def update_collection_stats(self, domain: str, original_papers, filtered_papers):
    with get_session() as session:
        # Add 'google_scholar' and 'doaj' to the sources list
        for source in ['pubmed', 'semantic_scholar', 'arxiv', 'google_scholar', 'doaj']:
            original_count = len([p for p in original_papers if p.source == source])
            filtered_count = len([p for p in filtered_papers if p.source == source])
            
            # ... rest of stats logic remains the same ...
```

#### 3.5 Update Final Report

In the `generate_final_report()` method, add new sources to breakdown:

```python
# Source breakdown
for source in ['pubmed', 'semantic_scholar', 'arxiv', 'google_scholar', 'doaj']:
    source_count = session.query(Paper).filter(Paper.source == source).count()
    table.add_row(f"{source.replace('_', ' ').title()} Papers", str(source_count))
```

### Step 4: Update Database Initialization

**File:** `sql/init.sql`

Add new collection stats entries:

```sql
-- Insert initial collection stats (add at the end)
INSERT INTO collection_stats (domain, source, total_papers) VALUES
    -- ... existing entries ...
    
    -- Google Scholar entries
    ('load_progression', 'google_scholar', 0),
    ('deload_timing', 'google_scholar', 0),
    ('exercise_selection', 'google_scholar', 0),
    ('periodization', 'google_scholar', 0),
    
    -- DOAJ entries
    ('load_progression', 'doaj', 0),
    ('deload_timing', 'doaj', 0),
    ('exercise_selection', 'doaj', 0),
    ('periodization', 'doaj', 0)
ON CONFLICT DO NOTHING;
```

### Step 5: Update Documentation

#### 5.1 Update Project Summary

**File:** `PROJECT_SUMMARY.md`

Add to the "Multi-Source Collection" section:

```markdown
### 🔍 Multi-Source Collection
- **PubMed**: Bio-python3 Entrez API with robust error handling
- **Semantic Scholar**: Free API with optional key for higher limits  
- **arXiv**: XML API for recent preprints and research
- **Google Scholar**: Massive coverage via SerpAPI or web scraping
- **DOAJ**: High-quality open access journals with PDFs
```

Add new rate limits to configuration section:

```markdown
# Rate limiting (requests per time period)
PUBMED_RATE_LIMIT=3              # per second
SEMANTIC_SCHOLAR_RATE_LIMIT=100  # per minute
ARXIV_RATE_LIMIT=10              # per minute
GOOGLE_SCHOLAR_RATE_LIMIT=0.03   # per second (very conservative)
DOAJ_RATE_LIMIT=2                # per second
OPENAI_RATE_LIMIT=60             # per minute
```

#### 5.2 Update README

Add new setup instructions for API keys:

```markdown
### API Keys Configuration

Required:
- `OPENAI_API_KEY`: For AI quality assessment
- `NCBI_EMAIL`: For PubMed access

Optional:
- `SEMANTIC_SCHOLAR_API_KEY`: Higher rate limits
- `SERPAPI_KEY`: Reliable Google Scholar access ($50/month)

Configuration:
- `GOOGLE_SCHOLAR_USE_SERPAPI=true`: Use SerpAPI (recommended)
- `GOOGLE_SCHOLAR_USE_SERPAPI=false`: Use web scraping (free but risky)
```

### Step 6: Testing Integration

#### 6.1 Test Individual Collectors

```bash
# Test Google Scholar collector
PYTHONPATH=. ../venv/bin/python -c "
from src.collectors import GoogleScholarCollector
collector = GoogleScholarCollector(rate_limit=0.1)
papers = collector.search_papers('resistance training', max_results=5)
print(f'Found {len(papers)} papers')
"

# Test DOAJ collector  
PYTHONPATH=. ../venv/bin/python -c "
from src.collectors import DOAJCollector
collector = DOAJCollector()
papers = collector.search_papers('resistance training', max_results=5)
print(f'Found {len(papers)} papers')
"
```

#### 6.2 Test Full Pipeline

```bash
# Run with limited domains for testing
PYTHONPATH=. ../venv/bin/python -m src.main --domains "load_progression"
```

### Step 7: Production Considerations

#### 7.1 Google Scholar Best Practices

**For Web Scraping (Free):**
- Use very conservative rate limits (1 request per 30+ seconds)
- Implement random delays and user agent rotation
- Monitor for blocking and have fallback strategies
- Consider using proxy rotation services

**For SerpAPI (Paid):**
- More reliable and faster
- $50/month for 5,000 searches
- Better for production environments
- No risk of being blocked

#### 7.2 Rate Limit Recommendations

```bash
# Conservative settings (recommended for initial runs)
GOOGLE_SCHOLAR_RATE_LIMIT=0.03  # 1 request per 30 seconds
DOAJ_RATE_LIMIT=1.0             # 1 request per second

# Aggressive settings (use with caution)
GOOGLE_SCHOLAR_RATE_LIMIT=0.1   # 1 request per 10 seconds  
DOAJ_RATE_LIMIT=3.0             # 3 requests per second
```

#### 7.3 Expected Results

With new collectors integrated:
- **Total papers**: 200-300 (up from ~116)
- **PDF availability**: Significantly higher due to DOAJ open access
- **Coverage**: Better grey literature and preprint coverage
- **Collection time**: 3-4 hours (up from 2-3 hours)

### Step 8: Troubleshooting

#### Common Issues:

**Google Scholar blocking:**
```bash
# Check if blocked
curl -s "https://scholar.google.com" | grep -i "blocked"

# Solutions:
# 1. Increase rate limits (reduce frequency)
# 2. Use different IP/proxy
# 3. Switch to SerpAPI
```

**DOAJ API errors:**
```bash
# Test DOAJ API directly
curl "https://doaj.org/api/search/articles?q=sports&pageSize=1"

# Usually indicates:
# - Network connectivity issues
# - API temporarily down
# - Malformed query
```

#### Monitoring:

```bash
# Check collection progress
tail -f data/logs/collection_*.log | grep -E "(Google Scholar|DOAJ)"

# Monitor database growth
docker compose exec postgres psql -U admin -d sports_science -c "
SELECT source, COUNT(*) as papers 
FROM papers 
GROUP BY source 
ORDER BY papers DESC;
"
```

## Success Criteria

- [ ] Both collectors successfully initialize
- [ ] Papers are collected from Google Scholar (if SerpAPI key provided)
- [ ] Papers are collected from DOAJ
- [ ] No duplicate papers (deduplication works across all sources)
- [ ] Statistics tracking includes new sources
- [ ] Final report shows breakdown by all sources
- [ ] Collection completes without errors

## Notes

- **Start small**: Test with single domain first
- **Monitor closely**: Watch for rate limiting and blocking
- **Consider costs**: SerpAPI costs money but is more reliable
- **Backup strategy**: Have fallback if Google Scholar gets blocked

This integration will significantly expand your dataset coverage and provide access to a much broader range of sports science literature.
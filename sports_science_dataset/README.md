# Sports Science Literature Dataset Builder

An automated pipeline for collecting, processing, and storing sports science research papers from multiple academic sources. Built for AI Engineering capstone project focusing on Adaptive Training AI with Physiological Modeling.

## Features

- **Multi-source Collection**: PubMed, Semantic Scholar, and arXiv APIs
- **AI-Powered Filtering**: OpenAI-based relevance and quality assessment
- **Smart Deduplication**: DOI, title, and author-based duplicate detection
- **PDF Processing**: Full-text extraction with section identification using PyMuPDF
- **Vector Embeddings**: Sentence-transformers for semantic search capabilities
- **PostgreSQL + pgvector**: Production-ready database with vector search
- **Comprehensive Logging**: Rich console output and detailed logging

## Quick Start

### 1. Environment Setup

```bash
# Clone and navigate to the project
cd sports_science_dataset

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment files
cp config/api_keys.env.example config/api_keys.env
cp config/database.env.example config/database.env

# Edit config files with your API keys
nano config/api_keys.env
```

### 2. Database Setup

```bash
# Start PostgreSQL with pgvector
docker-compose up -d postgres

# Initialize database tables
python src/main.py --setup-db

# Test database connection
python src/main.py --test-connection
```

### 3. Run Collection Pipeline

```bash
# Collect papers for all domains (recommended for first run)
python src/main.py

# Collect papers for specific domains
python src/main.py --domains "load_progression,deload_timing"

# Background execution with logging
nohup python src/main.py > collection.log 2>&1 &
```

## Configuration

### Required API Keys

1. **OpenAI API Key**: For AI-powered paper assessment
   - Get from: https://platform.openai.com/api-keys
   - Set in: `config/api_keys.env` → `OPENAI_API_KEY`

2. **NCBI Email**: Required for PubMed API access
   - Set in: `config/api_keys.env` → `NCBI_EMAIL`

3. **Semantic Scholar API Key** (Optional): Increases rate limits
   - Get from: https://www.semanticscholar.org/product/api
   - Set in: `config/api_keys.env` → `SEMANTIC_SCHOLAR_API_KEY`

### Collection Parameters

Edit `.env` file to customize:

```bash
# Target papers per domain (default: 50)
TARGET_PAPERS_PER_DOMAIN=75

# Quality thresholds
MINIMUM_QUALITY_SCORE=6
MINIMUM_RELEVANCE_SCORE=0.6

# Concurrency settings
MAX_CONCURRENT_DOWNLOADS=5
```

## Research Domains

The system collects papers across four key sports science domains:

### 1. Load Progression
- Progressive overload strategies
- Training load autoregulation
- RPE-based programming

### 2. Deload Timing
- Fatigue monitoring protocols
- Recovery strategies
- Overreaching detection

### 3. Exercise Selection
- Biomechanical analysis
- Muscle activation patterns
- Movement optimization

### 4. Periodization
- Training program design
- Block vs linear periodization
- Competition preparation

## Database Schema

```sql
-- Main papers table
papers (
    id, title, authors[], journal, year, doi, pmid,
    semantic_scholar_id, arxiv_id, abstract, full_text,
    sections (JSON), domain, source, quality_score,
    relevance_score, citation_count, pdf_path, pdf_url,
    metadata (JSON), embedding (vector), created_at
)

-- Collection tracking
search_history (id, domain, query_text, source, results_count)
collection_stats (id, domain, source, total_papers, successful_downloads)
```

## Pipeline Architecture

```
1. Multi-source Collection
   ├── PubMed (Entrez API)
   ├── Semantic Scholar API
   └── arXiv API

2. Deduplication Engine
   ├── DOI matching
   ├── Title similarity (fuzzy)
   └── Author+Title combination

3. AI Quality Assessment
   ├── Relevance scoring (0-1)
   ├── Quality scoring (1-10)
   └── Methodology classification

4. PDF Processing
   ├── Download and validation
   ├── Text extraction (PyMuPDF)
   └── Section identification

5. Vector Embeddings
   ├── Title+Abstract embedding
   ├── Sentence-transformers
   └── pgvector storage

6. Database Storage
   ├── Structured metadata
   ├── Full-text search
   └── Vector similarity search
```

## Data Quality Controls

- **Year Range**: 2010-2024 for recent relevance
- **Study Types**: Prioritizes RCTs, meta-analyses, systematic reviews
- **Population**: Healthy adults, trained individuals, athletes
- **Language**: English only
- **AI Assessment**: Minimum 6/10 quality, 0.6/1.0 relevance
- **Deduplication**: Multi-level duplicate detection

## Performance & Monitoring

### Rate Limiting
- PubMed: 3 requests/second
- Semantic Scholar: 100 requests/minute
- arXiv: 10 requests/minute
- OpenAI: 60 requests/minute

### Expected Timeline
- ~2-3 hours for complete collection (200 papers)
- ~500MB storage for papers + PDFs
- ~50% duplicate rate across sources

### Monitoring
```bash
# View real-time progress
tail -f data/logs/collection.log

# Check database stats
python -c "
from src.database import get_session, Paper
with get_session() as session:
    print(f'Total papers: {session.query(Paper).count()}')
"

# Adminer database viewer
open http://localhost:8080
```

## Extending the System

### Adding New Sources

1. Create collector in `src/collectors/new_source_collector.py`
2. Inherit from `BaseCollector`
3. Implement `search_papers()` and `get_paper_details()`
4. Add to main pipeline in `src/main.py`

### Adding New Domains

1. Define search queries in `DOMAIN_QUERIES`
2. Add domain criteria to `AIFilter.domain_criteria`
3. Update database schema if needed

### Custom Processing

1. Extend `PDFProcessor` for specialized text extraction
2. Modify `AIFilter` prompts for domain-specific assessment
3. Add custom deduplication rules in `Deduplicator`

## Troubleshooting

### Common Issues

**Database Connection Failed**
```bash
# Check PostgreSQL is running
docker-compose ps
docker-compose logs postgres

# Verify connection settings
python src/main.py --test-connection
```

**API Rate Limiting**
```bash
# Check rate limit settings in config/api_keys.env
# Increase delays between requests if needed
```

**PDF Download Failures**
```bash
# Check internet connectivity and PDF URLs
# Verify download directory permissions
ls -la data/raw_papers/
```

**Memory Issues**
```bash
# Reduce batch sizes in .env
MAX_CONCURRENT_DOWNLOADS=3
TARGET_PAPERS_PER_DOMAIN=25
```

### Log Analysis
```bash
# Error patterns
grep "ERROR" data/logs/collection.log

# Success rates
grep "papers accepted" data/logs/collection.log

# PDF processing stats
grep "PDF processed" data/logs/collection.log
```

## Production Deployment

### Docker Deployment
```bash
# Build production image
docker build -t sports-science-dataset .

# Run with docker-compose
docker-compose up -d
```

### Cron Job Setup
```bash
# Daily collection (incremental)
0 2 * * * cd /path/to/project && python src/main.py >> daily_collection.log 2>&1
```

### Monitoring & Alerts
- Set up log monitoring (ELK stack)
- Database size alerts
- API quota monitoring
- Failed collection notifications

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/new-feature`)
3. Commit changes (`git commit -am 'Add new feature'`)
4. Push to branch (`git push origin feature/new-feature`)
5. Create Pull Request

## License

MIT License - see LICENSE file for details.

## Support

For issues and questions:
- Create GitHub issue for bugs/features
- Check logs in `data/logs/` for troubleshooting
- Validate configuration with test commands
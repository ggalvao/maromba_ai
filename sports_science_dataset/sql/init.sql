-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create papers table with vector embeddings support
CREATE TABLE IF NOT EXISTS papers (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT[],
    journal VARCHAR(255),
    year INTEGER,
    doi VARCHAR(255) UNIQUE,
    pmid VARCHAR(50),
    semantic_scholar_id VARCHAR(100),
    arxiv_id VARCHAR(50),
    abstract TEXT,
    full_text TEXT,
    sections JSONB, -- {abstract, methods, results, conclusions}
    domain VARCHAR(50), -- load_progression, deload_timing, etc.
    source VARCHAR(50), -- pubmed, semantic_scholar, etc.
    quality_score INTEGER CHECK (quality_score >= 1 AND quality_score <= 10),
    relevance_score FLOAT CHECK (relevance_score >= 0 AND relevance_score <= 1),
    citation_count INTEGER DEFAULT 0,
    pdf_path VARCHAR(500),
    pdf_url TEXT,
    metadata JSONB,
    embedding VECTOR(768), -- Using sentence-transformers all-MiniLM-L6-v2
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_pmid ON papers(pmid);
CREATE INDEX IF NOT EXISTS idx_papers_domain ON papers(domain);
CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_quality_score ON papers(quality_score);
CREATE INDEX IF NOT EXISTS idx_papers_relevance_score ON papers(relevance_score);
CREATE INDEX IF NOT EXISTS idx_papers_title_gin ON papers USING gin(to_tsvector('english', title));
CREATE INDEX IF NOT EXISTS idx_papers_abstract_gin ON papers USING gin(to_tsvector('english', abstract));

-- Create vector similarity index for embeddings
CREATE INDEX IF NOT EXISTS idx_papers_embedding_cosine ON papers USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Create search history table for tracking queries
CREATE TABLE IF NOT EXISTS search_history (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(50),
    query_text TEXT NOT NULL,
    source VARCHAR(50),
    results_count INTEGER DEFAULT 0,
    execution_time INTERVAL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create collection stats table
CREATE TABLE IF NOT EXISTS collection_stats (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(50),
    source VARCHAR(50),
    total_papers INTEGER DEFAULT 0,
    successful_downloads INTEGER DEFAULT 0,
    failed_downloads INTEGER DEFAULT 0,
    duplicates_found INTEGER DEFAULT 0,
    avg_quality_score FLOAT,
    collection_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_papers_updated_at BEFORE UPDATE ON papers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert initial collection stats
INSERT INTO collection_stats (domain, source, total_papers) VALUES
    ('load_progression', 'pubmed', 0),
    ('load_progression', 'semantic_scholar', 0),
    ('load_progression', 'arxiv', 0),
    ('deload_timing', 'pubmed', 0),
    ('deload_timing', 'semantic_scholar', 0),
    ('deload_timing', 'arxiv', 0),
    ('exercise_selection', 'pubmed', 0),
    ('exercise_selection', 'semantic_scholar', 0),
    ('exercise_selection', 'arxiv', 0),
    ('periodization', 'pubmed', 0),
    ('periodization', 'semantic_scholar', 0),
    ('periodization', 'arxiv', 0)
ON CONFLICT DO NOTHING;

# Study Guide: Sports Science Dataset Builder

## 1. Introduction

This document provides a comprehensive deep dive into the `sports_science_dataset` project. Its purpose is to serve as a technical guide for developers who need to understand, maintain, or extend the system. The project's mission is to automate the creation of a high-quality, specialized dataset of sports science literature for use in AI applications.

The pipeline is designed to be modular and robust, handling everything from data collection and AI-powered quality control to PDF processing and storage in a vector-enabled database.

---

## 2. High-Level Architecture & Data Flow

The entire pipeline can be visualized as a multi-stage process where a large volume of raw academic data is progressively filtered and enriched until a small, high-quality dataset remains.

The data flows in the following sequence:

```
+-----------------------+
|   1. Collectors       |
| (PubMed, ArXiv, etc.) |
+-----------+-----------+
            |
            v
+-----------+-----------+
|   2. Deduplicator     |
| (Removes duplicates)  |
+-----------+-----------+
            |
            v
+-----------+-----------+
|     3. AI Filter      |
|  (Quality/Relevance)  |
+-----------+-----------+
            |
            v
+-----------+-----------+
|   4. PDF Processor    |
| (Downloads & Extracts)|
+-----------+-----------+
            |
            v
+-----------+-----------+
| 5. Embedding Manager  |
| (Generates Vectors)   |
+-----------+-----------+
            |
            v
+-----------+-----------+
|   6. Database         |
| (Stores Final Data)   |
+-----------------------+
```

--- 

## 3. Project Components (Deep Dive)

This section breaks down the project by its directory structure, explaining the role of each key component.

### `run.sh` - The Interactive Entry Point

This shell script is the user-friendly front door to the application. It is designed to guide a user through the entire setup and execution process.

- **Functionality**: It's a menu-driven script that automates:
  1.  **Environment Setup**: Copies `database.env.example` to `.env` and prompts the user to enter their API keys.
  2.  **Docker Management**: Starts the `postgres` and `adminer` services using `docker compose up -d`.
  3.  **Database Initialization**: Executes `python3 src/main.py --setup-db` to create the database schema.
  4.  **Pipeline Execution**: Runs the main collection script `python3 src/main.py`.

### `docker compose.yml` - The Environment

This file defines the services required to run the project, ensuring a consistent and reproducible environment.

- **`postgres` service**:
  - **Image**: `pgvector/pgvector:pg15`. This is a standard PostgreSQL image that comes with the `pgvector` extension pre-installed, which is crucial for storing and querying vector embeddings.
  - **Environment**: Sets up the database name, user, and password.
  - **Volumes**:
    - `- ./data/postgres_data:/var/lib/postgresql/data`: This is a **bind mount**. It maps the `data/postgres_data` directory from your local machine directly into the container. This ensures data persists even if the container is destroyed and makes backups as easy as copying a folder.
    - `- ./sql/init.sql:/docker-entrypoint-initdb.d/init.sql`: This mounts the `init.sql` script into a special directory within the container. The PostgreSQL image automatically executes any `.sql` scripts found here upon its first startup, which is how our tables are created.
- **`adminer` service**:
  - A lightweight, web-based database management tool. It's useful for quickly inspecting the data in the `sports_science_db`.

### `src/main.py` - The Orchestrator

This is the heart of the application. It's a command-line interface (CLI) application built using the `click` library that orchestrates the entire data collection pipeline.

- **`SportsScienteDatasetBuilder` class**: This class encapsulates the entire pipeline logic.
  - **`setup_environment()`**: Reads environment variables from the `.env` file and creates the necessary data directories (`raw_papers`, `processed_papers`, `logs`).
  - **`initialize_components()`**: This is where all the modular pieces (collectors, processors) are instantiated with their required configurations (API keys, rate limits, etc.).
  - **`run_collection_pipeline()`**: This is the main execution loop. It iterates through the `DOMAIN_QUERIES` and, for each domain, executes the data processing steps in the correct order (collect, deduplicate, filter, process, embed, store).
  - **`store_papers_in_database()`**: This method contains a crucial safeguard. Before adding a paper, it queries the database to see if a paper with the same `doi` or `pmid` already exists. This prevents duplicate entries if the script is run multiple times.
- **`@click.command()` functions**: This section defines the CLI commands you can use:
  - `main()`: The default command that runs the entire pipeline.
  - `--setup-db`: A flag to only run the database table creation logic.
  - `--test-connection`: A flag to verify that the application can connect to the database.
  - `--domains`: An option to run the pipeline for a specific subset of domains.

### `src/collectors/` - The Data Gatherers

This module is responsible for fetching paper metadata from various academic sources.

- **`base_collector.py`**: Defines an abstract base class. This is a good practice that could be used to enforce a standard interface for all collectors (e.g., they must all have a `search_papers` method).
- **`pubmed_collector.py`**: Uses the `Bio.Entrez` library to query the PubMed database.
- **`semantic_scholar_collector.py` / `arxiv_collector.py`**: Use the `requests` library to interact with the respective web APIs.

### `src/processors/` - The Data Refiners

This module is responsible for cleaning, filtering, and enriching the raw data.

- **`deduplicator.py`**: Takes a list of papers collected from all sources and removes duplicates based on DOI, PMID, or a fuzzy match of titles.
- **`ai_filter.py`**: This is a key component. It takes paper abstracts and sends them to the OpenAI API with a carefully crafted prompt, asking the model to score the paper on **quality** and **relevance** based on predefined criteria.
- **`pdf_processor.py`**: Handles the downloading of PDF files from their URLs. It then uses the `fitz` (PyMuPDF) library to open the PDF, extract the full text, and even attempt to parse out sections like "Methods" and "Results".

### `src/database/` - The Data Store

This module handles all interactions with the PostgreSQL database.

- **`connection.py`**: Manages the database connection using SQLAlchemy. The `get_session` function provides a session context for performing database operations, ensuring connections are properly handled and closed.
- **`models.py`**: Defines the database schema using SQLAlchemy's ORM (Object-Relational Mapping). The `Paper`, `SearchHistory`, and `CollectionStats` classes directly map to the tables in the database.
- **`embeddings.py`**: Contains the logic for generating vector embeddings. It uses the `sentence-transformers` library (specifically the `all-MiniLM-L6-v2` model) to convert a paper's title and abstract into a 768-dimension vector.

### `sql/init.sql` - The Database Blueprint

This script sets up the database schema from scratch.

- **`CREATE EXTENSION IF NOT EXISTS vector;`**: This is the first and most important command. It enables the `pgvector` extension in the database.
- **Table Definitions**: It defines the `papers`, `search_history`, and `collection_stats` tables.
- **`embedding VECTOR(768)`**: This is the special column type provided by `pgvector` used to store the paper's vector embedding.
- **Indexes**: It creates several indexes to speed up queries. The most important are:
  - **GIN Indexes**: `idx_papers_title_gin` and `idx_papers_abstract_gin` are used for efficient full-text search.
  - **IVFFLAT Index**: `idx_papers_embedding_cosine` is a special index for vector similarity searches. It dramatically speeds up finding the most similar papers based on their embeddings.

--- 

## 4. How to Make Changes

Understanding the modular structure is key to modifying the project.

-   **To Add a New Data Source**:
    1.  Create a new collector file in `src/collectors/` (e.g., `biorxiv_collector.py`).
    2.  Create a class that inherits from `BaseCollector` and implements the `search_papers` method.
    3.  Instantiate your new collector in `src/main.py`'s `initialize_components` method.
    4.  Call your new collector in the `collect_papers_for_domain` method.

-   **To Change the AI Filtering Logic**:
    1.  Open `src/processors/ai_filter.py`.
    2.  Modify the prompt in the `assess_paper` or `batch_assess_papers` method to change the criteria the AI uses for scoring.

-   **To Add a New Field to the Database**:
    1.  Add the new column to the `papers` table definition in `sql/init.sql`.
    2.  Add the corresponding property to the `Paper` class in `src/database/models.py`.
    3.  Update the `store_papers_in_database` method in `src/main.py` to populate the new field.
    4.  **Important**: If your database is already created, you will need to manually add the column using an `ALTER TABLE` command or wipe your database volume (`./data/postgres_data`) and restart the `docker compose` process to have `init.sql` run again.

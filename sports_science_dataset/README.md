# Sports Science Literature Dataset Builder

An automated pipeline for collecting, processing, and storing sports science research papers from multiple academic sources. This project is designed to build a high-quality dataset for AI applications in sports science, such as an "Adaptive Training AI with Physiological Modeling."

## Features

- **Multi-Source Collection**: Gathers data from PubMed, Semantic Scholar, and arXiv.
- **AI-Powered Filtering**: Uses OpenAI's GPT models to assess the relevance and quality of research papers.
- **Smart Deduplication**: Employs a multi-level strategy (DOI, title, author) to eliminate duplicate entries.
- **Advanced PDF Processing**: Extracts full text and identifies document sections using PyMuPDF.
- **Vector Embeddings**: Generates sentence-transformer embeddings for semantic search and analysis.
- **Production-Ready Database**: Utilizes PostgreSQL with the `pgvector` extension for efficient vector similarity search.
- **Interactive Setup**: Comes with a `run.sh` script to simplify setup and execution.

## Getting Started

This project can be set up quickly using the interactive script or by following the manual steps.

### Prerequisites

- Python 3.9+
- Docker and Docker Compose
- An OpenAI API key
- A valid email address for PubMed API access

### Quick Start (Recommended)

The `run.sh` script provides a guided setup process that handles environment configuration, database setup, and pipeline execution.

1.  **Navigate to the project directory:**
    ```bash
    cd sports_science_dataset
    ```

2.  **Make the script executable:**
    ```bash
    chmod +x run.sh
    ```

3.  **Run the interactive setup script:**
    ```bash
    ./run.sh
    ```

    Follow the on-screen prompts. The script will help you:
    - Create and configure your environment files (`.env`).
    - Start the PostgreSQL database using Docker.
    - Initialize the database schema.
    - Run the full data collection pipeline.

### Manual Setup

For developers who prefer a step-by-step approach:

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configure Environment:**
    Copy the example environment files:
    ```bash
    cp config/database.env.example .env
    ```
    Now, edit the `.env` file to add your API keys and set your configuration.
    ```ini
    # .env

    # Required
    OPENAI_API_KEY="your_openai_api_key_here"
    NCBI_EMAIL="your_email@example.com"

    # Optional
    SEMANTIC_SCHOLAR_API_KEY="your_semantic_scholar_key"

    # Collection Targets
    TARGET_PAPERS_PER_DOMAIN=50
    MINIMUM_QUALITY_SCORE=6
    MINIMUM_RELEVANCE_SCORE=0.6

    # Performance
    MAX_CONCURRENT_DOWNLOADS=5
    ```

3.  **Start the Database:**
    This command starts a PostgreSQL container with the `pgvector` extension enabled.
    ```bash
    docker compose up -d postgres
    ```
    The database files will be stored in `./data/postgres_data` as configured in the `docker compose.yml`.

4.  **Initialize the Database Schema:**
    This command creates the necessary tables and indexes.
    ```bash
    python3 src/main.py --setup-db
    ```

5.  **Test the Connection:**
    Verify that the application can connect to the database.
    ```bash
    python3 src/main.py --test-connection
    ```

6.  **Run the Collection Pipeline:**
    This will start the process of fetching, processing, and storing papers.
    ```bash
    # Run for all domains
    python3 src/main.py

    # Or, for specific domains
    python3 src/main.py --domains "load_progression,deload_timing"
    ```

## Project Structure

```
sports_science_dataset/
├── docker compose.yml      # Docker configuration for PostgreSQL
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── run.sh                  # Interactive setup script
├── src/                    # Source code
│   ├── main.py             # Main orchestration script
│   ├── collectors/         # Data collection modules
│   ├── processors/         # Data processing modules
│   └── database/           # Database interaction logic
├── data/                   # Data storage
│   ├── postgres_data/      # PostgreSQL data (bind mount)
│   └── ...
├── config/                 # Configuration files
│   └── database.env.example # Example environment file
└── sql/                    # SQL scripts
    └── init.sql            # Database initialization script
```

## Database

The project uses a PostgreSQL database with the `pgvector` extension to store and query paper data and vector embeddings.

-   **Database Viewer**: You can connect to the database using any standard PostgreSQL client or the provided Adminer service.
    -   **URL**: `http://localhost:8080`
    -   **Server**: `postgres`
    -   **Username**: `admin`
    -   **Password**: `sports_science_password` (or as set in your `.env`)
    -   **Database**: `sports_science`

## Troubleshooting

-   **Database Connection Failed**:
    -   Ensure Docker is running.
    -   Check the `postgres` container logs: `docker compose logs postgres`.
    -   Verify the database credentials in your `.env` file.

-   **API Rate Limiting**:
    -   The application has built-in rate limit handling, but if you encounter persistent issues, you may need to check your API key usage or adjust the rate limit settings in the code.

-   **PDF Download Failures**:
    -   Check your internet connection.
    -   Some papers may be behind paywalls, leading to download failures. The pipeline is designed to handle these gracefully.

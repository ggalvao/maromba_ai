#!/bin/bash

# Sports Science Dataset Builder - Quick Start Script

set -e

echo "🏋️ Sports Science Literature Dataset Builder"
echo "============================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Function to check if database is ready
wait_for_db() {
    echo "⏳ Waiting for database to be ready..."
    for i in {1..30}; do
        if docker-compose exec -T postgres pg_isready -U admin -d sports_science > /dev/null 2>&1; then
            echo "✅ Database is ready!"
            return 0
        fi
        echo "  Attempt $i/30... database not ready yet"
        sleep 2
    done
    echo "❌ Database failed to start within 60 seconds"
    exit 1
}

# Function to setup environment
setup_environment() {
    echo "🔧 Setting up environment..."
    
    # Check if API keys are configured
    if [ ! -f "config/api_keys.env" ]; then
        echo "⚠️  Creating API keys configuration file..."
        cp config/api_keys.env.example config/api_keys.env 2>/dev/null || echo "
# API Keys Configuration
OPENAI_API_KEY=your_openai_api_key_here
NCBI_EMAIL=your_email@example.com
SEMANTIC_SCHOLAR_API_KEY=optional_semantic_scholar_key
PUBMED_RATE_LIMIT=3
SEMANTIC_SCHOLAR_RATE_LIMIT=100
ARXIV_RATE_LIMIT=10
OPENAI_RATE_LIMIT=60" > config/api_keys.env
        
        echo "📝 Please edit config/api_keys.env with your API keys before continuing"
        echo "   Required: OPENAI_API_KEY and NCBI_EMAIL"
        echo "   Optional: SEMANTIC_SCHOLAR_API_KEY"
        exit 1
    fi
    
    # Check for required API keys
    source config/api_keys.env
    if [ "$OPENAI_API_KEY" = "your_openai_api_key_here" ] || [ -z "$OPENAI_API_KEY" ]; then
        echo "❌ Please set your OPENAI_API_KEY in config/api_keys.env"
        exit 1
    fi
    
    if [ "$NCBI_EMAIL" = "your_email@example.com" ] || [ -z "$NCBI_EMAIL" ]; then
        echo "❌ Please set your NCBI_EMAIL in config/api_keys.env"
        exit 1
    fi
    
    echo "✅ Environment configuration looks good"
}

# Function to install dependencies
install_dependencies() {
    echo "📦 Installing Python dependencies..."
    if ! command -v pip &> /dev/null; then
        echo "❌ pip not found. Please install Python and pip first."
        exit 1
    fi
    
    pip install -r requirements.txt
    echo "✅ Dependencies installed"
}

# Function to start database
start_database() {
    echo "🐘 Starting PostgreSQL database..."
    docker-compose up -d postgres
    wait_for_db
}

# Function to setup database
setup_database() {
    echo "🏗️  Setting up database tables..."
    python src/main.py --setup-db
    
    echo "🧪 Testing database connection..."
    python src/main.py --test-connection
    
    echo "✅ Database setup complete"
}

# Function to run tests
run_tests() {
    echo "🧪 Running pipeline tests..."
    python test_pipeline.py
}

# Function to start collection
start_collection() {
    echo "🚀 Starting literature collection..."
    echo "This will collect papers from PubMed, Semantic Scholar, and arXiv"
    echo "Expected runtime: 2-3 hours for complete dataset"
    echo ""
    
    read -p "Start collection now? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "📚 Starting collection pipeline..."
        python src/main.py | tee data/logs/collection_$(date +%Y%m%d_%H%M%S).log
    else
        echo "Collection cancelled. Run 'python src/main.py' when ready."
    fi
}

# Main menu
show_menu() {
    echo ""
    echo "Choose an option:"
    echo "1) Full setup (recommended for first time)"
    echo "2) Start database only"
    echo "3) Setup database tables"
    echo "4) Run tests"
    echo "5) Start collection pipeline"
    echo "6) View database (Adminer)"
    echo "7) Check status"
    echo "8) Stop all services"
    echo "9) Exit"
    echo ""
}

# Status check
check_status() {
    echo "📊 System Status:"
    echo "=================="
    
    # Docker containers
    echo "Docker Containers:"
    docker-compose ps 2>/dev/null || echo "  No containers running"
    
    # Database stats
    if docker-compose exec -T postgres pg_isready -U admin -d sports_science > /dev/null 2>&1; then
        echo ""
        echo "Database Status: ✅ Connected"
        
        # Count papers if possible
        paper_count=$(python -c "
try:
    from src.database import get_session, Paper
    with get_session() as session:
        count = session.query(Paper).count()
        print(f'Papers in database: {count}')
except:
    print('Papers in database: Unable to connect')
" 2>/dev/null)
        echo "$paper_count"
    else
        echo "Database Status: ❌ Not connected"
    fi
    
    echo ""
    echo "Disk Usage:"
    du -sh data/ 2>/dev/null || echo "  No data directory"
}

# Main script
main() {
    # Create directories
    mkdir -p data/raw_papers data/processed_papers data/logs config
    
    while true; do
        show_menu
        read -p "Enter your choice [1-9]: " choice
        
        case $choice in
            1)
                setup_environment
                install_dependencies
                start_database
                setup_database
                echo "🎉 Setup complete! You can now run the collection pipeline."
                ;;
            2)
                start_database
                ;;
            3)
                setup_database
                ;;
            4)
                run_tests
                ;;
            5)
                start_collection
                ;;
            6)
                echo "🌐 Opening Adminer at http://localhost:8080"
                echo "Database details:"
                echo "  System: PostgreSQL"
                echo "  Server: postgres"
                echo "  Username: admin"
                echo "  Password: sports_science_password"
                echo "  Database: sports_science"
                
                if command -v open &> /dev/null; then
                    open http://localhost:8080
                elif command -v xdg-open &> /dev/null; then
                    xdg-open http://localhost:8080
                else
                    echo "Please open http://localhost:8080 in your browser"
                fi
                ;;
            7)
                check_status
                ;;
            8)
                echo "🛑 Stopping all services..."
                docker-compose down
                echo "✅ All services stopped"
                ;;
            9)
                echo "👋 Goodbye!"
                exit 0
                ;;
            *)
                echo "❌ Invalid option. Please choose 1-9."
                ;;
        esac
        
        echo ""
        read -p "Press Enter to continue..."
    done
}

# Run main function
main
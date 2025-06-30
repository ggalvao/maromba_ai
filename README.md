# Maromba AI

A comprehensive monorepo for AI-powered fitness and sports science applications, featuring automated research data collection, workout tracking, and intelligent chatbot interfaces.

## 📋 Overview

This monorepo contains three main applications designed to support AI-driven fitness and sports science research:

1. **Sports Science Dataset Builder** - Automated research paper collection and processing pipeline
2. **Workout Tracker Bot** - Intelligent Telegram bot for weight training tracking
3. **Chatbot UI** - Streamlit-based conversational interface for fitness guidance

## 🏗️ Architecture

```
maromba_ai/
├── sports_science_dataset/     # Research paper collection pipeline
├── tracker_bot/               # Telegram workout tracking bot
├── chatbot-ui/               # Streamlit chatbot interface
├── data/                     # Shared data storage
└── requirements.txt          # Shared dependencies
```

## 🚀 Applications

### 1. Sports Science Dataset Builder

**Location**: `sports_science_dataset/`

An automated pipeline for collecting, processing, and storing sports science research papers from multiple academic sources including PubMed, Semantic Scholar, and arXiv.

**Key Features:**
- Multi-source academic paper collection
- AI-powered relevance filtering using GPT models
- Smart deduplication and quality assessment
- Vector embeddings for semantic search
- PostgreSQL database with pgvector extension

**Quick Start:**
```bash
cd sports_science_dataset
./run.sh
```

### 2. Workout Tracker Bot

**Location**: `tracker_bot/`

A Telegram bot for tracking weight training workouts with template-based exercise logging and Google Sheets integration.

**Key Features:**
- Template-based workout tracking
- Structured exercise logging (weight × reps × sets)
- RIR/RPE tracking support
- Google Sheets integration for data persistence
- User-friendly Telegram interface

**Quick Start:**
```bash
cd tracker_bot
# Set up environment variables
pip install -r requirements.txt
python bot.py
```

### 3. Chatbot UI

**Location**: `chatbot-ui/`

A Streamlit-based conversational interface powered by OpenAI's GPT models for fitness guidance and support.

**Key Features:**
- OpenAI GPT-4 integration
- Streamlit web interface
- Conversation history management
- Configurable AI responses

**Quick Start:**
```bash
cd chatbot-ui
pip install -r requirements.txt
streamlit run src/streamlit_app.py
```

## 🔧 Prerequisites

- Python 3.9+
- Docker and Docker Compose (for sports science dataset)
- OpenAI API key
- Telegram Bot Token (for tracker bot)
- Google Sheets API credentials (optional, for tracker bot)

## ⚙️ Environment Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd maromba_ai
   ```

2. **Install shared dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up individual applications:**
   - Follow the specific README files in each application directory
   - Configure environment variables as needed for each service

## 📊 Data Flow

The applications can work independently or together:

1. **Sports Science Dataset** generates research data and embeddings
2. **Tracker Bot** collects workout data from users
3. **Chatbot UI** can leverage both research data and user data for intelligent responses

## 🔐 Security & Privacy

- All API keys are managed through environment variables
- Google Sheets integration uses service account authentication
- User data is handled according to privacy best practices
- No sensitive information is committed to version control

## 🧪 Testing

Each application includes its own testing suite:

```bash
# Sports Science Dataset
cd sports_science_dataset && python test_pipeline.py

# Tracker Bot
cd tracker_bot && python -m pytest (if tests exist)

# Chatbot UI
cd chatbot-ui && python -m pytest (if tests exist)
```

## 📈 Monitoring & Logging

- Comprehensive logging throughout all applications
- Progress tracking for data collection pipeline
- Error handling and retry mechanisms
- Performance metrics collection

## 🔄 Development Workflow

1. **Branch Strategy**: Feature branches with pull requests
2. **Code Style**: Black formatting, consistent Python conventions
3. **Documentation**: Inline comments and comprehensive READMEs
4. **Testing**: Unit tests for core functionality

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📞 Support

For issues and questions:
- Check application-specific README files
- Review logs in respective `data/logs/` directories
- Open an issue in the repository

## 📄 License

This project is licensed under the MIT License - see individual application directories for specific license files.

## 🎯 Future Roadmap

- [ ] Integration between applications for unified data flow
- [ ] Enhanced AI models for personalized recommendations
- [ ] Mobile app development
- [ ] Advanced analytics and reporting features
- [ ] Multi-language support
- [ ] API development for third-party integrations

---

**Note**: This is a research and development project. Ensure proper configuration and testing before production use.
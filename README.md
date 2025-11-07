# Company Profile Builder

AI-powered recruitment research tool that generates comprehensive company profiles from just a name, website, or LinkedIn URL.

## Project Structure

```
company-profile-builder/
├── backend/                    # Python Flask API
│   ├── app.py                 # Flask server
│   ├── agent_flow.py          # LangGraph agent logic
│   ├── config.py              # API keys and settings
│   ├── tools.py               # LinkedIn scraping tool
│   └── requirements.txt       # Python dependencies
│
└── frontend/                   # React UI
    ├── src/
    │   ├── App.jsx            # Main React component
    │   ├── App.css            # Styling
    │   ├── main.jsx           # React entry point
    │   └── index.css          # Global styles
    ├── index.html             # HTML template
    ├── package.json           # Node dependencies
    └── vite.config.js         # Vite configuration
```

## Features

- **Smart Input Parsing**: Accepts company name, website URL, or LinkedIn URL
- **Comprehensive Data Collection**:
  - Company details (size, industry, headquarters, founded year)
  - LinkedIn data (followers, specialties, key personnel)
  - Competitor analysis (similarPages)
  - Job openings from careers pages and LinkedIn posts
  - Recent news and funding information
- **AI-Powered Synthesis**: Uses Gemini to intelligently combine and structure all data
- **Clean UI**: Simple React interface with formatted results

## Tech Stack

**Backend:**
- Flask (API server)
- LangGraph (agentic workflow)
- Google Gemini 2.0 Flash (LLM)
- Tavily (web search)
- ScrapeCreators (LinkedIn data)

**Frontend:**
- React 18
- Vite (dev server and build tool)

## Setup Instructions

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Set Environment Variables

Create a `.env` file in the backend folder or set environment variables:

```bash
# Windows PowerShell:
$env:TAVILY_API_KEY="your_tavily_key_here"
$env:SCRAPECREATORS_API_KEY="your_scrapecreators_key_here"
$env:GOOGLE_API_KEY="your_google_key_here"

# Windows CMD:
set TAVILY_API_KEY=your_tavily_key_here
set SCRAPECREATORS_API_KEY=your_scrapecreators_key_here
set GOOGLE_API_KEY=your_google_key_here

# Mac/Linux:
export TAVILY_API_KEY="your_tavily_key_here"
export SCRAPECREATORS_API_KEY="your_scrapecreators_key_here"
export GOOGLE_API_KEY="your_google_key_here"
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install
```

## Running the Application

You need TWO terminals running simultaneously:

**Terminal 1 - Backend:**
```bash
cd backend
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux
python app.py
```

Backend will run on: `http://127.0.0.1:5000`

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

Frontend will run on: `http://localhost:5173`

Open your browser to `http://localhost:5173` and start researching companies!

## Usage

1. Enter a company name, website URL, or LinkedIn company URL
2. Click "Research"
3. Wait for the AI agent to:
   - Find the LinkedIn profile (if needed)
   - Scrape comprehensive company data
   - Search for job openings and recent news
   - Synthesize everything into a structured report
4. View the formatted results

## Configuration

Edit `backend/config.py` to change:
- `GEMINI_MODEL_NAME`: Switch between Gemini models (default: "gemini-2.0-flash-exp")
- `FLASK_PORT`: Change backend port (default: 5000)

## API Endpoint

**POST** `/research`

Request body:
```json
{
  "input": "Outstaffer" 
}
```

Response: `CompanyReport` JSON object with all company data

## Next Steps for Production

- Add error handling and retry logic
- Implement caching for LinkedIn data
- Add authentication
- Deploy backend to Google Cloud Run
- Deploy frontend to Firebase Hosting or Cloud Storage + CDN
- Add database for storing reports
- Implement rate limiting

## Troubleshooting

**"Module not found" errors:**
- Make sure virtual environment is activated
- Run `pip install -r requirements.txt` again

**CORS errors:**
- Check that CORS origins in `app.py` match your frontend URL
- Default is set for `http://localhost:5173`

**API key errors:**
- Verify environment variables are set correctly
- Check that keys are valid and have credits

**Frontend can't connect to backend:**
- Ensure backend is running on port 5000
- Check fetch URL in `App.jsx` matches backend address

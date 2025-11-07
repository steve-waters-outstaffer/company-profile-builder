# Quick Start Guide

## First Time Setup (5 minutes)

1. **Run the setup script:**
   ```
   setup.bat
   ```
   This installs all dependencies for both backend and frontend.

2. **Set your API keys:**
   
   Open PowerShell in this directory and run:
   ```powershell
   $env:TAVILY_API_KEY="your_tavily_key"
   $env:SCRAPECREATORS_API_KEY="your_scrapecreators_key"
   $env:GOOGLE_API_KEY="your_google_gemini_key"
   ```

   Or in CMD:
   ```cmd
   set TAVILY_API_KEY=your_tavily_key
   set SCRAPECREATORS_API_KEY=your_scrapecreators_key
   set GOOGLE_API_KEY=your_google_gemini_key
   ```

## Running the App (Daily Use)

You need TWO terminal windows:

**Terminal 1 - Backend:**
```
run-backend.bat
```
Wait until you see "Running on http://127.0.0.1:5000"

**Terminal 2 - Frontend:**
```
run-frontend.bat
```
Wait until you see "Local: http://localhost:5173"

Then open your browser to: **http://localhost:5173**

## How to Use

1. Enter a company name, website, or LinkedIn URL
2. Click "Research"
3. Wait 30-60 seconds for the AI to gather data
4. View the comprehensive company profile

## Example Inputs

- Company name: `Outstaffer`
- Website: `https://outstaffer.com`
- LinkedIn: `https://www.linkedin.com/company/outstaffer`

## Troubleshooting

**Backend won't start:**
- Check that API keys are set in the same terminal session
- Make sure virtual environment is activated (you should see `(venv)` in prompt)

**Frontend can't connect:**
- Ensure backend is running first (port 5000)
- Check that both are running without errors

**Agent fails:**
- Check API key validity and credits
- Review backend terminal for error messages
- Common: Tavily rate limits, ScrapeCreators quota

## What the Agent Does

1. **Parses input** - Figures out if you gave a name, URL, or LinkedIn
2. **Finds LinkedIn** - Uses Tavily to locate company LinkedIn profile
3. **Scrapes LinkedIn** - Uses ScrapeCreators API to get structured data
4. **Finds jobs & news** - Searches for careers pages and recent articles
5. **Synthesizes report** - Uses Gemini to combine everything into clean JSON

## Next Steps

- Check `README.md` for full documentation
- Modify `backend/config.py` to change Gemini model
- Edit `frontend/src/App.jsx` to customize UI
- Deploy to GCP when ready (instructions coming)

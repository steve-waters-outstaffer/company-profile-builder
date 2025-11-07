# tools.py
import requests
import config

from langchain_core.tools import tool

@tool
def scrape_linkedin_company(company_linkedin_url: str) -> dict:
    """
    Scrapes a LinkedIn company profile using the ScrapeCreators API 
    to get detailed, structured data.
    """
    api_key = config.SCRAPECREATORS_API_KEY
    if not api_key:
        return {"error": "ScrapeCreators API key not found."}

    api_url = "https://api.scrapecreators.com/v1/linkedin/company"
    headers = {"x-api-key": api_key}
    params = {"url": company_linkedin_url}

    try:
        response = requests.get(api_url, headers=headers, params=params)
        response.raise_for_status() 
        return response.json()

    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to scrape LinkedIn profile: {e}"}

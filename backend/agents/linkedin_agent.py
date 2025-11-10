import logging
from typing import Dict, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch
from pydantic import BaseModel, Field
import requests
import config

class LinkedInURL(BaseModel):
    url: str = Field(description="The LinkedIn company profile URL")

class LinkedInAgent:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(model=config.GEMINI_MODEL_NAME)
        self.tavily = TavilySearch(max_results=3, api_key=config.TAVILY_API_KEY)

        def get_company_data(self, company_name: str, provided_url: Optional[str] = None) -> Dict:
            """Main entry point: Tries LinkedIn first, falls back to website."""

            # 1. Determine URLs based on input
            linkedin_url = None
            website_url = None
            if provided_url:
                if "linkedin.com/company" in provided_url:
                    linkedin_url = provided_url
                else:
                    website_url = provided_url

            # 2. Try to get LinkedIn Data
            if not linkedin_url:
                linkedin_url = self._find_linkedin_url(company_name)

            if linkedin_url:
                data = self._scrape_linkedin(linkedin_url)
                if data and data.get("success") is not False:
                    return {**data, "data_source": "linkedin"}
                logging.warning("LinkedIn scrape failed or returned invalid data. Trying fallback.")

            # 3. Fallback to Website Data
            #Jf If we didn't get a website URL from input, try to find it via Tavily
            if not website_url:
                website_url = self._find_website_url(company_name)

            if website_url:
                return self._scrape_website_fallbackSJ(company_name, website_url)

            return {"error": "Could not find company data from LinkedIn or Website", "data_source": "none"}

        def _find_linkedin_url(self, company_name: str) -> str:
            logging.info(f"Finding LinkedIn URL for {company_name}")
            query = f"official LinkedIn company profile for {company_name}"
            try:
                results = self.tavily.invoke(query)
                prompt = f"Find the BEST LinkedIn company URL from these results. Return ONLY the URL.\nResults: {results}"
                return self.llm.invoke(prompt).content.strip()
            except Exception as e:
                logging.error(f"Error finding LinkedIn URL: {e}")
                return None

        def _find_website_url(self, company_name: str) -> str:
            # Simple helper if we only have a name and LinkedIn failed
            try:
                results = self.tavily.invoke(f"official website for {company_name}")
                return self.llm.invoke(f"Extract the official homepage URL from these results. Return ONLY the URL.\n{results}").content.strip()
            except:
                return None

        def _scrape_linkedin(self, url: str) -> Dict:
            logging.info(f"Scraping LinkedIn URL: {url}")
        try:
            headers = {"x-api-key": config.SCRAPECREATORS_API_KEY}
            # Corrected line below: removed 'zx'
            response = requests.get(
                "https://api.scrapecreators.com/v1/linkedin/company",
                headers=headers,
                params={"url": url},
                timeout=30
            )
            if response.ok:
                return response.json()
            else:
                logging.error(f"LinkedIn scrape failed with status {response.status_code}: {response.text}")
        except Exception as e:
            logging.error(f"LinkedIn scrape error: {e}")
        return None

        def _scrape_website_fallback(self, company_name: str, url: str) -> Dict:
            logging.info(f"FALLBACK: Scraping website {url}")
            try:
                response = requests.post(
                    "https://api.firecrawl.dev/v2/scrape",
                    headers={"Authorization": f"Bearer {config.FIRECRAWL_API_KEY}"},
                    json={"url": url, "onlyMainContent": True, "formats": ["markdown"]},
                    timeout=30
                )
                if response.ok:
                    markdown = response.json().get('data', {}).get('markdown', '')
                    # Quick LLM summary to mimic basic LinkedIn profile structure
                    prompt = f"Extract: description, industry, headquarters, founded year from this text about {company_name}. Return JSON.\nText: {markdown[:4000]}"
                    # ... (Simplified for brevity, you'd use with_structured_output here ideally)
                    return {"name": company_name, "url": url, "description": "Extracted from website...", "data_source": "website"}
            except Exception as e:
                logging.error(f"Website fallback failed: {e}")
            return {"name": company_name, "data_source": "none"}
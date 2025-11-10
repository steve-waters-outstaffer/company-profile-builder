import logging
from typing import Dict, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch
from pydantic import BaseModel, Field
import requests
import config

logger = logging.getLogger(__name__)


class LinkedInURL(BaseModel):
    url: str = Field(description="The LinkedIn company profile URL")


class LinkedInAgent:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(model=config.GEMINI_MODEL_NAME)
        self.tavily = TavilySearch(max_results=3, api_key=config.TAVILY_API_KEY)
        logger.info("[LINKEDIN_AGENT] Initialized")

    def get_company_data(self, company_name: str, provided_url: Optional[str] = None) -> Dict:
        """Main entry point: tries LinkedIn first, falls back to the company website."""
        logger.info(f"[LINKEDIN_AGENT] Starting | company: '{company_name}' | provided_url: '{provided_url}'")
        
        linkedin_url: Optional[str] = None
        website_url: Optional[str] = None

        # If caller provided a URL, classify it
        if provided_url:
            if "linkedin.com/company" in provided_url:
                linkedin_url = provided_url
                logger.info(f"[LINKEDIN_AGENT] Using provided LinkedIn URL | url: {linkedin_url}")
            else:
                website_url = provided_url
                logger.info(f"[LINKEDIN_AGENT] Using provided website URL | url: {website_url}")

        # Try to discover LinkedIn URL if not given
        if not linkedin_url:
            linkedin_url = self._find_linkedin_url(company_name)

        # Scrape LinkedIn if we have it
        if linkedin_url:
            logger.info(f"[LINKEDIN_AGENT] Attempting LinkedIn scrape | url: {linkedin_url}")
            data = self._scrape_linkedin(linkedin_url)
            if data and data.get("success") is not False:
                logger.info(f"[LINKEDIN_AGENT] SUCCESS - LinkedIn data retrieved | company: '{company_name}'")
                return {**data, "data_source": "linkedin"}
            logger.warning(f"[LINKEDIN_AGENT] LinkedIn scrape failed | company: '{company_name}' | falling back to website")

        # Fallback: find website if needed
        if not website_url:
            logger.info(f"[LINKEDIN_AGENT] Searching for website | company: '{company_name}'")
            website_url = self._find_website_url(company_name)

        if website_url:
            logger.info(f"[LINKEDIN_AGENT] Using website fallback | url: {website_url}")
            return self._scrape_website_fallback(company_name, website_url)

        logger.error(f"[LINKEDIN_AGENT] FAILED - No data sources available | company: '{company_name}'")
        return {"error": "Could not find company data from LinkedIn or website", "data_source": "none"}

    def _find_linkedin_url(self, company_name: str) -> Optional[str]:
        logger.info(f"[LINKEDIN_AGENT] Finding LinkedIn URL | company: '{company_name}'")
        query = f"official LinkedIn company profile for {company_name}"
        try:
            results = self.tavily.invoke(query)
            logger.info(f"[LINKEDIN_AGENT] Tavily search complete | company: '{company_name}'")
            
            prompt = (
                "Find the BEST LinkedIn company URL from these results. "
                "Return ONLY the URL.\n"
                f"Results: {results}"
            )
            url = self.llm.invoke(prompt).content.strip()
            
            if url.startswith("http"):
                logger.info(f"[LINKEDIN_AGENT] LinkedIn URL found | company: '{company_name}' | url: {url}")
                return url
            else:
                logger.warning(f"[LINKEDIN_AGENT] No valid LinkedIn URL | company: '{company_name}'")
                return None
        except Exception as e:
            logger.error(f"[LINKEDIN_AGENT] Error finding LinkedIn URL | company: '{company_name}' | error: {str(e)}")
            return None

    def _find_website_url(self, company_name: str) -> Optional[str]:
        logger.info(f"[LINKEDIN_AGENT] Finding website URL | company: '{company_name}'")
        try:
            results = self.tavily.invoke(f"official website for {company_name}")
            logger.info(f"[LINKEDIN_AGENT] Tavily search complete for website | company: '{company_name}'")
            
            prompt = (
                "Extract the official homepage URL from these results. "
                "Return ONLY the URL.\n"
                f"{results}"
            )
            url = self.llm.invoke(prompt).content.strip()
            
            if url.startswith("http"):
                logger.info(f"[LINKEDIN_AGENT] Website URL found | company: '{company_name}' | url: {url}")
                return url
            else:
                logger.warning(f"[LINKEDIN_AGENT] No valid website URL | company: '{company_name}'")
                return None
        except Exception as e:
            logger.error(f"[LINKEDIN_AGENT] Error finding website URL | company: '{company_name}' | error: {str(e)}")
            return None

    def _scrape_linkedin(self, url: str) -> Optional[Dict]:
        logger.info(f"[LINKEDIN_AGENT] Scraping LinkedIn | url: {url}")
        try:
            headers = {"x-api-key": config.SCRAPECREATORS_API_KEY}
            response = requests.get(
                "https://api.scrapecreators.com/v1/linkedin/company",
                headers=headers,
                params={"url": url},
                timeout=30,
            )
            
            if response.ok:
                data = response.json()
                logger.info(f"[LINKEDIN_AGENT] LinkedIn scrape SUCCESS | url: {url}")
                return data
            else:
                logger.error(f"[LINKEDIN_AGENT] LinkedIn scrape FAILED | url: {url} | status: {response.status_code} | response: {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"[LINKEDIN_AGENT] LinkedIn scrape ERROR | url: {url} | error: {str(e)}")
            return None

    def _scrape_website_fallback(self, company_name: str, url: str) -> Dict:
        logger.info(f"[LINKEDIN_AGENT] FALLBACK - Scraping website | company: '{company_name}' | url: {url}")
        try:
            response = requests.post(
                "https://api.firecrawl.dev/v2/scrape",
                headers={"Authorization": f"Bearer {config.FIRECRAWL_API_KEY}"},
                json={"url": url, "onlyMainContent": True, "formats": ["markdown"]},
                timeout=30,
            )
            
            if response.ok:
                markdown = response.json().get("data", {}).get("markdown", "")
                logger.info(f"[LINKEDIN_AGENT] Website scrape SUCCESS | company: '{company_name}' | content_length: {len(markdown)}")
                
                prompt = (
                    f"Extract a concise JSON with keys: description, industry, headquarters, founded "
                    f"from this text about {company_name}. Return JSON only.\n"
                    f"Text: {markdown[:4000]}"
                )
                try:
                    summary = self.llm.invoke(prompt).content
                    logger.info(f"[LINKEDIN_AGENT] LLM summary generated | company: '{company_name}'")
                except Exception as e:
                    logger.warning(f"[LINKEDIN_AGENT] LLM summary failed | company: '{company_name}' | error: {str(e)}")
                    summary = None
                
                return {
                    "name": company_name,
                    "url": url,
                    "website_extract": summary or "Extracted from website.",
                    "data_source": "website",
                }
            else:
                logger.error(f"[LINKEDIN_AGENT] Website scrape FAILED | company: '{company_name}' | status: {response.status_code}")
        except Exception as e:
            logger.error(f"[LINKEDIN_AGENT] Website fallback ERROR | company: '{company_name}' | error: {str(e)}")
        
        return {"name": company_name, "data_source": "none"}

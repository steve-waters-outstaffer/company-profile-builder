import logging
import json
import requests
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
import config
from langchain_tavily import TavilySearch
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

class CareersURL(BaseModel):
    """Schema for LLM to return the best careers page URL."""
    url: str = Field(description="The best careers/jobs page URL from the search results")
    reasoning: str = Field(description="Brief explanation of why this is the best match")

class JobsDiscoveryAgent:
    """
    Simple job discovery:
    1. Find careers URL via Tavily search
    2. Fetch HTML and ask Gemini to extract jobs
    No Firecrawl, no complex fallbacks.
    """

    def __init__(self, tavily_api_key: str = config.TAVILY_API_KEY):
        self.tavily_api_key = tavily_api_key
        self.llm = ChatGoogleGenerativeAI(model=config.GEMINI_MODEL_NAME)
        self.tavily = TavilySearch(max_results=5, api_key=tavily_api_key)
        logger.info("[JOBS_AGENT] Initialized")

    def discover_jobs(self, company_name: str, company_url: Optional[str], location: Optional[str] = None) -> Dict:
        """Main entry point for job discovery."""
        logger.info(f"[JOBS_AGENT] Starting job discovery | company: '{company_name}' | url: '{company_url}' | location: '{location}'")

        try:
            # 1. Find careers page
            careers_url = self._find_careers_page(company_name, company_url, location)
            if not careers_url:
                logger.warning(f"[JOBS_AGENT] No careers page found | company: '{company_name}'")
                return {"job_listings": [], "error": "No careers page found", "source": "none"}

            # 2. Extract jobs via Gemini
            logger.info(f"[JOBS_AGENT] Extracting jobs from {careers_url}")
            jobs = self._extract_jobs_gemini(careers_url)
            logger.info(f"[JOBS_AGENT] SUCCESS | company: '{company_name}' | jobs_found: {len(jobs)}")

            return {
                "job_listings": jobs,
                "careers_url": careers_url,
                "source": "gemini" if jobs else "error"
            }

        except Exception as e:
            logger.error(f"[JOBS_AGENT] ERROR | company: '{company_name}' | error: {str(e)}", exc_info=True)
            return {"job_listings": [], "error": str(e), "source": "error"}

    def _find_careers_page(self, company_name: str, company_url: Optional[str], location: Optional[str] = None) -> Optional[str]:
        """Find careers URL using Tavily + LLM selection."""
        logger.info(f"[JOBS_AGENT] Finding careers page | company: '{company_name}'")

        query = f"{company_name} official careers page job openings"
        if location:
            query += f" {location}"

        try:
            logger.info(f"[JOBS_AGENT] Tavily search | query: '{query}'")
            results = self.tavily.invoke(query)

            prompt = f"""You are an expert recruiter finding the direct careers page URL for {company_name}.
            Select the BEST URL that directly lists open positions.

            Priority:
            1. careers.company.com or jobs.company.com (dedicated careers domain)
            2. company.com/careers or company.com/jobs (careers on main site)
            3. ATS platform (greenhouse.io, lever.co, etc)
            4. LinkedIn /jobs/ page ONLY

            DO NOT select: homepage, about pages, blog posts, or generic profiles.

            Results: {results}

            Return the single best URL."""

            structured_llm = self.llm.with_structured_output(CareersURL)
            result = structured_llm.invoke(prompt)

            if result.url and result.url.startswith('http'):
                logger.info(f"[JOBS_AGENT] Found careers URL | url: {result.url}")
                return result.url
            else:
                logger.warning(f"[JOBS_AGENT] Invalid URL from LLM")
                return None

        except Exception as e:
            logger.error(f"[JOBS_AGENT] Error finding careers page | {str(e)}")
            return None

    def _extract_jobs_gemini(self, careers_url: str) -> List[Dict]:
        """
        Fetch careers page HTML and ask Gemini to extract job listings.
        Returns structured job data.
        """
        try:
            # 1. Fetch the page
            logger.info(f"[JOBS_AGENT] Fetching {careers_url}")
            response = requests.get(careers_url, timeout=15)
            response.raise_for_status()
            html = response.text[:150000]  # Limit to first 150k chars
            logger.info(f"[JOBS_AGENT] Fetched {len(html)} chars from {careers_url}")

            # 2. Ask Gemini to extract jobs
            prompt = f"""Extract ALL job openings from this careers page HTML.
            
Return ONLY valid JSON (no markdown, no preamble):
{{"jobs": [{{"title": "Job Title", "location": "Location", "url": "Apply URL"}}]}}

If you cannot find specific URLs, use the main careers page URL.
Return an empty jobs array if no positions are found.

HTML:
{html}"""

            logger.info(f"[JOBS_AGENT] Asking Gemini to extract jobs")
            result = self.llm.invoke(prompt)
            
            # Parse JSON from response
            try:
                # Try to extract JSON from the response
                content = result.content if hasattr(result, 'content') else str(result)
                # Remove markdown code blocks if present
                content = content.replace('```json', '').replace('```', '').strip()
                parsed = json.loads(content)
                jobs = parsed.get('jobs', [])
                logger.info(f"[JOBS_AGENT] Extracted {len(jobs)} jobs from Gemini")
                return jobs
            except json.JSONDecodeError as je:
                logger.error(f"[JOBS_AGENT] Failed to parse Gemini response | error: {str(je)} | content: {content[:200]}")
                return []

        except requests.RequestException as e:
            logger.error(f"[JOBS_AGENT] Failed to fetch {careers_url} | {str(e)}")
            return []
        except Exception as e:
            logger.error(f"[JOBS_AGENT] Error extracting jobs | {str(e)}", exc_info=True)
            return []

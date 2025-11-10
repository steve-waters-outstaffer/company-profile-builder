import logging
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
    Simplified job discovery agent using Tavily to find careers page, directly followed by Firecrawl Extract.
    """

    def __init__(self, firecrawl_api_key: str = config.FIRECRAWL_API_KEY, tavily_api_key: str = config.TAVILY_API_KEY):
        self.firecrawl_api_key = firecrawl_api_key
        self.tavily_api_key = tavily_api_key
        self.llm = ChatGoogleGenerativeAI(model=config.GEMINI_MODEL_NAME)
        self.base_url = "https://api.firecrawl.dev/v2"
        self.headers = {
            "Authorization": f"Bearer {self.firecrawl_api_key}",
            "Content-Type": "application/json"
        }
        self.tavily = TavilySearch(max_results=5, api_key=tavily_api_key)
        logger.info("[JOBS_AGENT] Initialized")

    def discover_jobs(self, company_name: str, company_url: Optional[str]) -> Dict:
        """Main entry point for job discovery."""
        logger.info(f"[JOBS_AGENT] Starting job discovery | company: '{company_name}' | url: '{company_url}'")

        try:
            # 1. Find careers page
            careers_url = self._find_careers_page(company_name, company_url)
            if not careers_url:
                logger.warning(f"[JOBS_AGENT] No careers page found | company: '{company_name}'")
                return {"job_listings": [], "error": "No careers page found"}

            # 2. Extract jobs
            logger.info(f"[JOBS_AGENT] Extracting jobs | company: '{company_name}' | careers_url: {careers_url}")
            jobs = self._extract_jobs(careers_url)
            logger.info(f"[JOBS_AGENT] SUCCESS - Jobs extracted | company: '{company_name}' | count: {len(jobs)}")

            return {"job_listings": jobs, "careers_url": careers_url}

        except Exception as e:
            logger.error(f"[JOBS_AGENT] ERROR | company: '{company_name}' | error: {str(e)}", exc_info=True)
            return {"job_listings": [], "error": str(e)}

    def _find_careers_page(self, company_name: str, company_url: Optional[str]) -> Optional[str]:
        logger.info(f"[JOBS_AGENT] Finding careers page | company: '{company_name}'")

        # 1. Tighter Search Query
        # Focus on "listings" and "openings" to avoid generic corporate pages.
        # If we have a URL, we still prefer a broad search first, as many modern companies
        # host jobs on subdomains (jobs.company.com) or ATS (greenhouse.io)
        # which a 'site:' operator might sometimes miss if strictly applied.
        query = f"{company_name} official careers page job openings listings"

        try:
            logger.info(f"[JOBS_AGENT] Tavily search starting | company: '{company_name}' | query: '{query}'")
            results = self.tavily.invoke(query)
            # ... (keep your existing logging) ...

            # 2. Stricter LLM Prompt (The Magic Fix)
            # explicitly tells it standard patterns to look for and what to avoid.
            prompt = f"""You are an expert recruiter finding the direct link to apply for jobs at {company_name}.
            Analyze the search results and select the BEST URL that directly lists currently open positions.

            Follow this PRIORITY order for selection:
            1. A dedicated careers subdomain (e.g., jobs.outstaffer.com, careers.company.com).
            2. A direct ATS link used by the company (e.g., greenhouse.io/company, lever.co/company).
            3. A clear careers path on their main site (e.g., company.com/careers, company.com/jobs).
            4. A LinkedIn page ONLY IF it specifically ends in '/jobs/' (avoid generic company profiles).

            STRICT NEGATIVE RULES (Do NOT select these):
            - Do NOT select the company homepage (e.g., outstaffer.com/).
            - Do NOT select 'About Us', 'Contact', or 'Team' pages unless NO other option exists.
            - Do NOT select blog posts or press releases.

            Search results: {results}

            Return the single best URL and your reasoning based on the priority above."""

            structured_llm = self.llm.with_structured_output(CareersURL)
            result = structured_llm.invoke(prompt)
            
            logger.info(f"[JOBS_AGENT] LLM selection | company: '{company_name}' | url: {result.url} | reasoning: {result.reasoning}")
            
            if result.url and result.url.startswith('http'):
                return result.url
            else:
                logger.warning(f"[JOBS_AGENT] No valid careers URL found | company: '{company_name}'")
                return None
        except Exception as e:
            logger.error(f"[JOBS_AGENT] Error finding careers page | company: '{company_name}' | error: {str(e)}", exc_info=True)
            return None

    def _extract_jobs(self, source_url: str) -> List[Dict]:
        logger.info(f"[JOBS_AGENT] Starting Firecrawl extraction | url: {source_url}")
        try:
            # ... [KEEP YOUR SCHEMA AND PROMPT THE SAME AS BEFORE] ...
            schema = {
                "type": "object",
                "properties": {
                    "jobs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "location": {"type": "string"},
                                "url": {"type": "string"},
                                "posted_date": {"type": "string"}
                            },
                            "required": ["title", "url"]
                        }
                    }
                },
                "required": ["jobs"]
            }

            payload = {
                "urls": [source_url],
                "schema": schema,
                "prompt": "Extract all individual job postings. Required fields: 'title' (must be the specific role name, strictly AVOID using locations like 'Remote' or 'New York' as the title), 'location', and 'url' (direct link to apply). Optional fields: 'posted_date' and 'description' (Short summary of the role). Ignore general page text."
            }

            logger.info(f"[JOBS_AGENT] Calling Firecrawl API | url: {source_url}")

            # --- NUCLEAR DEBUG LOGGING ---
            logger.info(f"[JOBS_AGENT] DEBUG: API Key starts with: {self.firecrawl_api_key[:4]}...") # Verify key is actually loaded

            response = requests.post(
                f"{self.base_url}/extract",
                json=payload,
                headers=self.headers,
                timeout=60
            )

            # Log RAW details before ANY parsing
            logger.info(f"[JOBS_AGENT] DEBUG: Status Code: {response.status_code}")
            logger.info(f"[JOBS_AGENT] DEBUG: Raw Response Text: {response.text}")
            # -----------------------------

            if response.ok:
                try:
                    data = response.json().get('data', {})
                except Exception as json_e:
                    logger.error(f"[JOBS_AGENT] FATAL: Response was OK but not valid JSON: {json_e}")
                    return []

                if isinstance(data, list) and len(data) > 0:
                    jobs_data = data[0].get('jobs', [])
                elif isinstance(data, dict):
                    jobs_data = data.get('jobs', [])
                else:
                    jobs_data = []

                valid_jobs = [
                    {**job, 'url': job.get('url', source_url)}
                    for job in jobs_data
                    if job.get('title')
                ]

                logger.info(f"[JOBS_AGENT] Extraction SUCCESS | url: {source_url} | raw_count: {len(jobs_data)} | valid_count: {len(valid_jobs)}")
                return valid_jobs
            else:
                logger.error(f"[JOBS_AGENT] Firecrawl extraction FAILED | url: {source_url} | status: {response.status_code} | response: {response.text}")
                return []

        except Exception as e:
            logger.error(f"[JOBS_AGENT] Extraction ERROR | url: {source_url} | error: {str(e)}", exc_info=True)
            return []

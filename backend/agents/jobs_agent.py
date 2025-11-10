import logging
import time
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
import config
from langchain_tavily import TavilySearch
from langchain_google_genai import ChatGoogleGenerativeAI
# NEW IMPORT
from firecrawl import FirecrawlApp

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

        # Initialize standard FirecrawlApp client
        # This client automatically handles polling for async jobs.
        self.firecrawl = FirecrawlApp(api_key=self.firecrawl_api_key)

        self.tavily = TavilySearch(max_results=5, api_key=tavily_api_key)
        logger.info("[JOBS_AGENT] Initialized")

    # ... [keep your existing discover_jobs method unchanged] ...
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

    # ... [keep your existing _find_careers_page method unchanged] ...
    def _find_careers_page(self, company_name: str, company_url: Optional[str]) -> Optional[str]:
        logger.info(f"[JOBS_AGENT] Finding careers page | company: '{company_name}'")

        # Use the tighter query that worked for you
        query = f"{company_name} official careers page job openings listings"

        try:
            logger.info(f"[JOBS_AGENT] Tavily search starting | company: '{company_name}' | query: '{query}'")
            results = self.tavily.invoke(query)
            logger.info(f"[JOBS_AGENT] Tavily search complete | company: '{company_name}' | results_count: {len(results) if isinstance(results, list) else 'N/A'}")

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
        logger.info(f"[JOBS_AGENT] Starting Firecrawl SDK extraction | url: {source_url}")
        try:
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

            # Use the prompt that worked in Playground
            playground_prompt = (
                "Extract all individual job postings. Required fields: 'title' (must be the specific role name, "
                "strictly AVOID using locations like 'Remote' or 'New York' as the title), 'location', and 'url' "
                "(direct link to apply). Optional fields: 'posted_date' and 'description' (Short summary of the role). "
                "Ignore general page text."
            )

            params = {
                'prompt': playground_prompt,
                'schema': schema
            }

            # The SDK's scrape_url (with extract format) OR extract methods
            # generally handle polling if the job goes async.
            # We use 'extract' here as it matches your playground usage.
            logger.info(f"[JOBS_AGENT] Calling Firecrawl SDK... this may take time if polling is needed.")

            # NOTE: SDK might take 60s+ if it has to poll. Ensure your Cloud Run timeout handles this.
            result = self.firecrawl.extract(
                [source_url],
                params=params
            )

            # SDK usually returns the final data structure directly if successful.
            # It might look like: {'success': True, 'data': {'jobs': [...]}}
            # OR it might be a list of results if you passed a list of URLs.

            logger.info(f"[JOBS_AGENT] RAW SDK RESULT: {result}") # Keep this for one run to confirm structure

            jobs_data = []
            # Handle potential different return structures from SDK
            if isinstance(result, dict):
                if 'data' in result and 'jobs' in result['data']:
                    jobs_data = result['data']['jobs']
                elif 'jobs' in result:
                    # rare case where it unwrap data
                    jobs_data = result['jobs']
            elif isinstance(result, list) and len(result) > 0:
                # If it returns a list of results (one per URL)
                jobs_data = result[0].get('data', {}).get('jobs', [])

            valid_jobs = [
                {**job, 'url': job.get('url', source_url)}
                for job in jobs_data
                if job.get('title')
            ]

            logger.info(f"[JOBS_AGENT] Extraction SUCCESS | url: {source_url} | valid_count: {len(valid_jobs)}")
            return valid_jobs

        except Exception as e:
            logger.error(f"[JOBS_AGENT] SDK Extraction ERROR | url: {source_url} | error: {str(e)}", exc_info=True)
            return []
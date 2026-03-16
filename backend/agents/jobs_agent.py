import logging
import time
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
    Job discovery with Firecrawl primary (60s timeout) + Tavily hiring search fallback.
    """

    def __init__(self, firecrawl_api_key: str = config.FIRECRAWL_API_KEY, tavily_api_key: str = config.TAVILY_API_KEY):
        self.firecrawl_api_key = firecrawl_api_key
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

            # 2. Extract jobs
            logger.info(f"[JOBS_AGENT] Extracting jobs | company: '{company_name}' | careers_url: {careers_url}")
            jobs = self._extract_jobs(careers_url)
            logger.info(f"[JOBS_AGENT] SUCCESS - Jobs extracted | company: '{company_name}' | count: {len(jobs)}")

            return {"job_listings": jobs, "careers_url": careers_url, "source": "firecrawl" if jobs else "tavily_fallback"}

        except Exception as e:
            logger.error(f"[JOBS_AGENT] ERROR | company: '{company_name}' | error: {str(e)}", exc_info=True)
            return {"job_listings": [], "error": str(e), "source": "error"}

    def _find_careers_page(self, company_name: str, company_url: Optional[str], location: Optional[str] = None) -> Optional[str]:
        logger.info(f"[JOBS_AGENT] Finding careers page | company: '{company_name}' | location: '{location}'")

        query = f"{company_name} official careers page job openings listings"
        
        if location:
            query += f" {location}"

        try:
            logger.info(f"[JOBS_AGENT] Tavily search starting | query: '{query}'")
            results = self.tavily.invoke(query)
            logger.info(f"[JOBS_AGENT] Tavily search complete | results: {len(results) if isinstance(results, list) else 'N/A'}")

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

            logger.info(f"[JOBS_AGENT] LLM selection | url: {result.url}")

            if result.url and result.url.startswith('http'):
                return result.url
            else:
                logger.warning(f"[JOBS_AGENT] No valid careers URL found")
                return None
        except Exception as e:
            logger.error(f"[JOBS_AGENT] Error finding careers page | error: {str(e)}")
            return None

    def _extract_jobs(self, source_url: str) -> List[Dict]:
        """
        Extracts jobs using Firecrawl with 60s hard timeout.
        Falls back to Tavily hiring search if Firecrawl fails or times out.
        """
        logger.info(f"[JOBS_AGENT] Starting job extraction | url: {source_url}")

        # Try Firecrawl first (faster, structured)
        jobs = self._extract_jobs_firecrawl(source_url)
        if jobs:
            logger.info(f"[JOBS_AGENT] Firecrawl succeeded | jobs found: {len(jobs)}")
            return jobs

        # Fallback to Tavily hiring search
        logger.warning(f"[JOBS_AGENT] Firecrawl failed/timed out, trying Tavily fallback")
        jobs = self._extract_jobs_tavily_fallback(source_url)
        logger.info(f"[JOBS_AGENT] Tavily fallback complete | jobs found: {len(jobs)}")
        return jobs

    def _extract_jobs_firecrawl(self, source_url: str) -> List[Dict]:
        """
        Firecrawl extraction with 60s hard timeout (12 retries x 5s).
        Returns empty list on timeout or error (triggers fallback).
        """
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
                            "url": {"type": "string"}
                        },
                        "required": ["title", "location"]
                    }
                }
            },
            "required": ["jobs"]
        }

        prompt = "Extract all jobs. For each job: 'title' is the role name like 'Accountant' or 'Billing Manager', 'location' is where the job is based, 'url' is the apply link."

        post_url = "https://api.firecrawl.dev/v2/extract"
        headers = {
            "Authorization": f"Bearer {self.firecrawl_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "urls": [source_url],
            "prompt": prompt,
            "schema": schema
        }

        job_id = None
        try:
            logger.info(f"[JOBS_AGENT] Firecrawl: Submitting job")
            response = requests.post(post_url, headers=headers, data=json.dumps(payload), timeout=10)
            response.raise_for_status()

            post_data = response.json()
            job_id = post_data.get('id')

            if not job_id:
                logger.warning(f"[JOBS_AGENT] Firecrawl: No job ID in response")
                return []

            logger.info(f"[JOBS_AGENT] Firecrawl: Job submitted | ID: {job_id}")

        except Exception as e:
            logger.warning(f"[JOBS_AGENT] Firecrawl: Submit failed | error: {str(e)}")
            return []

        # Poll with 60s hard cap (12 x 5s)
        get_url = f"https://api.firecrawl.dev/v2/extract/{job_id}"
        get_headers = {"Authorization": f"Bearer {self.firecrawl_api_key}"}
        max_retries = 12  # 12 * 5s = 60s max

        for attempt in range(max_retries):
            try:
                time.sleep(5)
                response = requests.get(get_url, headers=get_headers, timeout=10)
                response.raise_for_status()

                status_data = response.json()
                status = status_data.get('status')

                logger.info(f"[JOBS_AGENT] Firecrawl: Poll {attempt + 1}/{max_retries} | status: {status}")

                if status == 'completed':
                    jobs_data = status_data.get('data', {}).get('jobs', [])
                    valid_jobs = [
                        {**job, 'url': job.get('url', source_url)}
                        for job in jobs_data
                        if job.get('url')
                    ]
                    logger.info(f"[JOBS_AGENT] Firecrawl: Complete | jobs: {len(valid_jobs)}")
                    return valid_jobs

                elif status in ['failed', 'cancelled']:
                    logger.warning(f"[JOBS_AGENT] Firecrawl: Job {status}")
                    return []

            except Exception as e:
                logger.warning(f"[JOBS_AGENT] Firecrawl: Poll error {attempt + 1}/{max_retries} | {str(e)}")
                continue

        logger.warning(f"[JOBS_AGENT] Firecrawl: Timeout after 60s")
        return []

    def _extract_jobs_tavily_fallback(self, source_url: str) -> List[Dict]:
        """
        Fallback: Search for hiring signals via Tavily.
        Returns simplified job objects from web search results.
        """
        try:
            logger.info(f"[JOBS_AGENT] Tavily: Searching for hiring signals")
            query = f"careers hiring jobs available openings {source_url}"
            results = self.tavily.invoke(query)

            jobs = []
            if results and isinstance(results, list):
                # Convert search results to job-like objects
                for result in results[:5]:  # Limit to top 5
                    title = result.get('title', 'View Careers Page')
                    url = result.get('url', source_url)
                    jobs.append({
                        "title": title[:100],
                        "location": "Visit careers page",
                        "url": url
                    })

            logger.info(f"[JOBS_AGENT] Tavily: Found {len(jobs)} hiring signals")
            return jobs

        except Exception as e:
            logger.warning(f"[JOBS_AGENT] Tavily fallback error | {str(e)}")
            return []

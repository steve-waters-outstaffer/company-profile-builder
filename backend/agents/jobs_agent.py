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
    Simplified job discovery agent using Tavily to find careers page, directly followed by Firecrawl Extract.
    """

    def __init__(self, firecrawl_api_key: str = config.FIRECRAWL_API_KEY, tavily_api_key: str = config.TAVILY_API_KEY):
        self.firecrawl_api_key = firecrawl_api_key
        self.tavily_api_key = tavily_api_key
        self.llm = ChatGoogleGenerativeAI(model=config.GEMINI_MODEL_NAME)
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
            results_count = len(results) if isinstance(results, list) else 'N/A'
            logger.info(f"[JOBS_AGENT] Tavily search complete | company: '{company_name}' | results_count: {results_count}")
            logger.info(f"[JOBS_AGENT] Tavily raw results | company: '{company_name}' | results: {results}")

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

            logger.info(f"[JOBS_AGENT] LLM prompt | company: '{company_name}' | prompt_length: {len(prompt)}")
            
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
        """
        Extracts jobs using the raw API POST/GET polling method that
        was confirmed to work in test_firecrawl.py.
        """
        logger.info(f"[JOBS_AGENT] Starting RAW API extract w/ polling | url: {source_url}")

        # --- Use the exact schema & prompt from the successful test ---
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

        # --- STEP 1: POST to start the job (Raw API call) ---
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
            logger.info(f"[JOBS_AGENT] Submitting job to {post_url}...")
            response = requests.post(post_url, headers=headers, data=json.dumps(payload), timeout=10)
            response.raise_for_status()

            post_data = response.json()
            job_id = post_data.get('id')

            if not job_id:
                logger.error(f"[JOBS_AGENT] Error: API did not return a 'id'. Response: {post_data}")
                return []

            logger.info(f"[JOBS_AGENT] Job submitted successfully! Job ID: {job_id}")

        except Exception as e:
            logger.error(f"[JOBS_AGENT] Error submitting job | error: {str(e)}", exc_info=True)
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response Body: {e.response.text}")
            return []

        # --- STEP 2: GET to poll for results (Raw API call) ---
        get_url = f"https://api.firecrawl.dev/v2/extract/{job_id}"
        get_headers = {"Authorization": f"Bearer {self.firecrawl_api_key}"}

        max_retries = 20  # 20 * 5s = 100s timeout
        for attempt in range(max_retries):
            logger.info(f"[JOBS_AGENT] Polling attempt {attempt + 1}/{max_retries} | Job ID: {job_id}")
            try:
                time.sleep(5) # Wait *before* polling (except first time, which we do)

                response = requests.get(get_url, headers=get_headers, timeout=10)
                response.raise_for_status()

                status_data = response.json()
                status = status_data.get('status')

                logger.info(f"[JOBS_AGENT] Current status: {status}")

                if status == 'completed':
                    logger.info(f"[JOBS_AGENT] Job completed! | Job ID: {job_id}")

                    final_data = status_data.get('data', {})
                    jobs_data = final_data.get('jobs', [])

                    if jobs_data:
                        logger.info(f"📊 Successfully found {len(jobs_data)} jobs.")
                    else:
                        logger.warning("⚠️  Job completed but 'jobs' array was empty or missing.")

                    # Keep jobs even if title is empty, but ensure URL exists
                    valid_jobs = [
                        {**job, 'url': job.get('url', source_url)}
                        for job in jobs_data
                        if job.get('url')  # Only require URL, allow empty titles
                    ]
                    logger.info(f"[JOBS_AGENT] Returning {len(valid_jobs)} valid jobs (titles may be empty).")
                    return valid_jobs

                elif status == 'failed' or status == 'cancelled':
                    logger.error(f"[JOBS_AGENT] Job {status}. Halting. | Job ID: {job_id} | Response: {status_data}")
                    return []

                # If 'processing', loop continues...

            except Exception as e:
                logger.error(f"[JOBS_AGENT] Error polling job status | error: {str(e)}", exc_info=True)
                if hasattr(e, 'response') and e.response:
                    logger.error(f"Response Body: {e.response.text}")
                # Continue polling even if one request fails

        logger.error(f"[JOBS_AGENT] Job timed out after 100s. | Job ID: {job_id}")
        return []
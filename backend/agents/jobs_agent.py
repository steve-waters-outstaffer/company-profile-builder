import logging
import requests
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
import config
from langchain_tavily import TavilySearch
from langchain_google_genai import ChatGoogleGenerativeAI

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

    def discover_jobs(self, company_name: str, company_url: Optional[str]) -> Dict:
        """Main entry point for job discovery."""
        logging.info(f"Starting job discovery for: {company_name}")

        try:
            # 1. Find careers page
            careers_url = self._find_careers_page(company_name, company_url)
            if not careers_url:
                return {"jobs": [], "error": "No careers page found"}

            # 2. Extract jobs directly
            logging.info(f"Extracting jobs from: {careers_url}")
            jobs = self._extract_jobs(careers_url)
            logging.info(f"Found {len(jobs)} jobs")

            return {"job_listings": jobs, "careers_url": careers_url}

        except Exception as e:
            logging.error(f"Job discovery failed: {e}", exc_info=True)
            return {"job_listings": [], "error": str(e)}

    def _find_careers_page(self, company_name: str, company_url: Optional[str]) -> Optional[str]:
        query = f"official careers page for {company_name}"
        if company_url:
            query += f" site:{company_url}"

        try:
            results = self.tavily.invoke(query)
            prompt = f"""Find the official page (URL) for listing and advertising open careers/jobs URL for {company_name} from these results.
            Return ONLY the URL.
            Results: {results}"""

            # Simple extraction for now to save time, can use structured output if needed
            url = self.llm.invoke(prompt).content.strip()
            if url.startswith('http'):
                return url
        except Exception as e:
            logging.error(f"Error finding careers page: {e}")
        return None

    def _extract_jobs(self, source_url: str) -> List[Dict]:
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
                            "required": ["title"]
                        }
                    }
                },
                "required": ["jobs"]
            }

            payload = {
                # FIXED: v2/extract requires 'urls' as a list, not 'url' string
                "urls": [source_url],
                "schema": schema,
                "prompt": "Extract all individual job postings. Required fields: 'title' (must be the specific role name, strictly AVOID using locations like 'Remote' or 'New York' as the title), 'location', and 'url' (direct link to apply). Optional fields: 'posted_date' and 'description' (Short summary of the role). Ignore general page text."
            }

            response = requests.post(
                f"{self.base_url}/extract",
                json=payload,
                headers=self.headers,
                timeout=60
            )

            if response.ok:
                data = response.json().get('data', {})
                # Handle potential empty list if 'data' is a list (batch response) or dict
                if isinstance(data, list) and len(data) > 0:
                    jobs_data = data[0].get('jobs', [])
                elif isinstance(data, dict):
                    jobs_data = data.get('jobs', [])
                else:
                    jobs_data = []

                return [
                    {**job, 'url': job.get('url', source_url)}
                    for job in jobs_data
                    if job.get('title')
                ]
            else:
                logging.error(f"Firecrawl extract failed: {response.status_code} {response.text}")
                return []

        except Exception as e:
            logging.error(f"Extraction failed: {e}")
            return []
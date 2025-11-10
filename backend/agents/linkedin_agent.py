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
        """Main entry point: tries LinkedIn first, falls back to provided URL or searches for website."""
        logger.info(f"[LINKEDIN_AGENT] Starting | company: '{company_name}' | provided_url: '{provided_url}'")

        linkedin_url: Optional[str] = None
        website_url: Optional[str] = None

        # Extract website_url if provided (regardless of type)
        if provided_url:
            provided_url = provided_url.strip()
            if "linkedin.com/company/" in provided_url:
                linkedin_url = provided_url
                logger.info(f"[LINKEDIN_AGENT] LinkedIn URL provided | url: {linkedin_url}")
            else:
                # Store as website_url for later fallback
                website_url = provided_url
                logger.info(f"[LINKEDIN_AGENT] Website URL provided | url: {website_url}")

        # ALWAYS try to find LinkedIn URL if we don't have one yet (even if they pasted a website)
        if not linkedin_url:
            linkedin_url = self._find_linkedin_url(company_name)

        # Try LinkedIn scrape if we have a URL
        if linkedin_url:
            logger.info(f"[LINKEDIN_AGENT] Attempting LinkedIn scrape | url: {linkedin_url}")
            data = self._scrape_linkedin(linkedin_url)
            if data and data.get("success") is not False:
                logger.info(f"[LINKEDIN_AGENT] SUCCESS - LinkedIn data retrieved | company: '{company_name}'")
                return {**data, "data_source": "linkedin"}
            logger.warning(f"[LINKEDIN_AGENT] LinkedIn scrape failed | company: '{company_name}' | falling back")

        # Fallback 1: Use provided website URL if we have it
        if website_url:
            logger.info(f"[LINKEDIN_AGENT] Using provided website URL as fallback | url: {website_url}")
            return self._scrape_website_fallback(company_name, website_url)

        # Fallback 2: Search for website
        logger.info(f"[LINKEDIN_AGENT] Searching for website | company: '{company_name}'")
        website_url = self._find_website_url(company_name)

        if website_url:
            logger.info(f"[LINKEDIN_AGENT] Found website, using as fallback | url: {website_url}")
            return self._scrape_website_fallback(company_name, website_url)

        # Everything failed
        logger.error(f"[LINKEDIN_AGENT] FAILED - No data sources available | company: '{company_name}'")
        return {"error": "Could not find company data from LinkedIn or website", "data_source": "none"}

    def _find_linkedin_url(self, company_name: str) -> Optional[str]:
        logger.info(f"[LINKEDIN_AGENT] Finding LinkedIn URL | company: '{company_name}'")

        # More specific query to avoid posts and personal profiles
        query = f'"{company_name}" LinkedIn company page'

        try:
            results = self.tavily.invoke(query)
            results_count = len(results) if isinstance(results, list) else 'N/A'
            logger.info(f"[LINKEDIN_AGENT] Tavily search complete | company: '{company_name}' | results_count: {results_count}")
            logger.info(f"[LINKEDIN_AGENT] Tavily raw results | company: '{company_name}' | results: {results}")

            prompt = (
                "Find the BEST LinkedIn company page URL from these results.\n"
                "RULES:\n"
                "- MUST be a company page (linkedin.com/company/...)\n"
                "- AVOID personal profiles (linkedin.com/in/...)\n"
                "- AVOID individual posts (linkedin.com/posts/...)\n"
                "- If you only see posts or profiles, extract the company slug from post URLs\n"
                "  Example: from 'linkedin.com/posts/corehesion-pty-ltd_...', extract 'corehesion-pty-ltd'\n"
                "  and return 'https://www.linkedin.com/company/corehesion-pty-ltd'\n"
                "Return ONLY the company page URL.\n\n"
                f"Results: {results}"
            )
            logger.info(f"[LINKEDIN_AGENT] LLM prompt | company: '{company_name}' | prompt_length: {len(prompt)}")

            response = self.llm.invoke(prompt)
            url = response.content.strip()
            logger.info(f"[LINKEDIN_AGENT] LLM response | company: '{company_name}' | response: {url}")

            # Validate it's a company URL
            if url.startswith("http") and "/company/" in url:
                logger.info(f"[LINKEDIN_AGENT] LinkedIn URL found | company: '{company_name}' | url: {url}")
                return url
            else:
                logger.warning(f"[LINKEDIN_AGENT] No valid LinkedIn company URL found | company: '{company_name}' | got: {url}")
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
                raw_data = response.json()
                logger.info(f"[LINKEDIN_AGENT] LinkedIn scrape SUCCESS | url: {url}")

                # Transform the description for sales readability
                transformed_data = self._transform_linkedin_description(raw_data)
                return transformed_data
            else:
                logger.error(f"[LINKEDIN_AGENT] LinkedIn scrape FAILED | url: {url} | status: {response.status_code} | response: {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"[LINKEDIN_AGENT] LinkedIn scrape ERROR | url: {url} | error: {str(e)}")
            return None

    def _transform_linkedin_description(self, linkedin_data: Dict) -> Dict:
        """Transform raw LinkedIn data into a sales-ready format with rewritten description."""
        logger.info(f"[LINKEDIN_AGENT] Transforming description for sales readability")

        try:
            # Build context from all available LinkedIn fields
            context_parts = []

            company_name = linkedin_data.get('name', 'This company')
            if linkedin_data.get('description'):
                context_parts.append(f"Description: {linkedin_data['description']}")
            if linkedin_data.get('industry'):
                context_parts.append(f"Industry: {linkedin_data['industry']}")
            if linkedin_data.get('headquarters'):
                context_parts.append(f"Headquarters: {linkedin_data['headquarters']}")
            if linkedin_data.get('company_size'):
                context_parts.append(f"Size: {linkedin_data['company_size']}")
            if linkedin_data.get('specialties'):
                context_parts.append(f"Specialties: {linkedin_data['specialties']}")
            if linkedin_data.get('founded'):
                context_parts.append(f"Founded: {linkedin_data['founded']}")

            context = "\n".join(context_parts)

            prompt = f"""You are writing a company summary for recruitment sales professionals.
            
Using the LinkedIn data below, write a concise 2-3 sentence third-person description of {company_name}.

Style guidelines:
- Write in third person (e.g., "{company_name} is a...", "The company specializes in...")
- Focus on what they do, who they serve, and what makes them notable
- Be professional but conversational
- Include key details like location, size, or industry if relevant
- Keep it under 100 words
- Return ONLY the description text, no extra formatting or labels

LinkedIn Data:
{context}
"""

            logger.info(f"[LINKEDIN_AGENT] Generating sales-ready description | company: {company_name}")
            new_description = self.llm.invoke(prompt).content.strip()
            logger.info(f"[LINKEDIN_AGENT] Description transformed | company: {company_name} | length: {len(new_description)}")

            # Replace the description with the transformed version
            linkedin_data['description'] = new_description

        except Exception as e:
            logger.warning(f"[LINKEDIN_AGENT] Description transformation failed, using original | error: {str(e)}")

        return linkedin_data

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
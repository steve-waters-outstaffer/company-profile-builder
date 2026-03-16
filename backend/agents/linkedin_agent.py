import logging
import json
import re
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

    def get_company_data(self, company_name: str, provided_url: Optional[str] = None, url_type: Optional[str] = None) -> Dict:
        """
        Main entry point.
        IMPROVED FLOW:
        1. If website URL provided, scrape it FIRST to establish ground truth (location, industry).
        2. Use ground truth to perform a targeted LinkedIn search.
        3. Merge LinkedIn data (if found) with website data.
        
        Args:
            company_name: Company name (always provided)
            provided_url: Optional URL (website or LinkedIn)
            url_type: 'website' | 'linkedin' | None
        """
        logger.info(f"[LINKEDIN_AGENT] Starting | company: '{company_name}' | url: '{provided_url}' | url_type: '{url_type}'")
        
        linkedin_url: Optional[str] = None
        website_url: Optional[str] = None
        ground_truth_data: Optional[Dict] = None
        
        # --- STEP 1: Classify the Provided URL ---
        if provided_url:
            if url_type == 'linkedin':
                linkedin_url = provided_url
                logger.info(f"[LINKEDIN_AGENT] LinkedIn URL provided by user | url: {linkedin_url}")
            elif url_type == 'website':
                website_url = provided_url
                logger.info(f"[LINKEDIN_AGENT] Website URL provided by user | url: {website_url}")
            else:
                # Fallback: guess based on URL content (shouldn't happen with new frontend)
                if "linkedin.com/company/" in provided_url:
                    linkedin_url = provided_url
                else:
                    website_url = provided_url
        
        # --- STEP 2: Scrape Website for Ground Truth (if available) ---
        if website_url:
            logger.info(f"[LINKEDIN_AGENT] Scraping provided website for ground truth | url: {website_url}")
            ground_truth_data = self._scrape_website(company_name, website_url)
            
            if ground_truth_data.get("description"):
                logger.info(f"[LINKEDIN_AGENT] Ground truth established | name: '{ground_truth_data.get('name')}' | HQ: '{ground_truth_data.get('headquarters', 'N/A')}'")
                
                # Use verified company name for LinkedIn search
                company_name = ground_truth_data.get('name', company_name)
        
        # --- STEP 3: Find LinkedIn URL ---
        if not linkedin_url:
            # Build a targeted query if we have ground truth or URL hints
            custom_query = None
            if website_url:
                # Start with site search constrained to LinkedIn company pages
                custom_query = f'site:linkedin.com/company "{company_name}"'
                
                # Add location hint from TLD
                if ".au" in website_url:
                    custom_query += " Australia"
                elif ".uk" in website_url or ".co.uk" in website_url:
                    custom_query += " UK"
                elif ".ca" in website_url:
                    custom_query += " Canada"
                elif ".nz" in website_url:
                    custom_query += " New Zealand"
                
                # Add industry hint if we successfully extracted it from ground truth
                if ground_truth_data and ground_truth_data.get("industry") and ground_truth_data["industry"] != "N/A":
                    custom_query += f" {ground_truth_data['industry']}"
                
                logger.info(f"[LINKEDIN_AGENT] Using targeted LinkedIn search | query: '{custom_query}'")
            
            linkedin_url = self._find_linkedin_url(company_name, custom_query=custom_query)
        
        # --- STEP 4: Scrape LinkedIn and Merge ---
        if linkedin_url:
            logger.info(f"[LINKEDIN_AGENT] Attempting LinkedIn scrape | url: {linkedin_url}")
            linkedin_data = self._scrape_linkedin(linkedin_url)
            
            if linkedin_data and linkedin_data.get("success") is not False:
                logger.info(f"[LINKEDIN_AGENT] SUCCESS - LinkedIn data retrieved")
                
                # If we have ground truth, merge them. LinkedIn generally takes precedence for structured info,
                # but we ensure website URL is correct.
                if ground_truth_data:
                    # Start with website data, overwrite with LinkedIn data
                    merged_data = {**ground_truth_data, **linkedin_data}
                    # Ensure the originally provided website is kept if LinkedIn has none or a different one
                    if website_url:
                        merged_data['website'] = website_url
                    merged_data["data_source"] = "linkedin_with_website"
                    return merged_data
                
                return {**linkedin_data, "data_source": "linkedin"}
            else:
                logger.warning(f"[LINKEDIN_AGENT] LinkedIn scrape failed, falling back")
        
        # --- STEP 5: Fallbacks ---
        
        # Fallback 1: Return ground truth if we have it
        if ground_truth_data:
            logger.info(f"[LINKEDIN_AGENT] Falling back to website ground truth")
            ground_truth_data["data_source"] = "website"
            return ground_truth_data
        
        # Fallback 2: If no URL was provided initially, try to find one now
        if not website_url:
            logger.info(f"[LINKEDIN_AGENT] No data yet, searching for company website | company: '{company_name}'")
            found_website_url = self._find_website_url(company_name)
            if found_website_url:
                logger.info(f"[LINKEDIN_AGENT] Found website, scraping now | url: {found_website_url}")
                return self._scrape_website(company_name, found_website_url)
        
        logger.error(f"[LINKEDIN_AGENT] FAILED - No data sources available | company: '{company_name}'")
        return {"error": "Could not find company data from LinkedIn or website", "data_source": "none"}

    def _find_linkedin_url(self, company_name: str, custom_query: Optional[str] = None) -> Optional[str]:
        logger.info(f"[LINKEDIN_AGENT] Finding LinkedIn URL | company: '{company_name}'")
        
        query = custom_query if custom_query else f'site:linkedin.com/company "{company_name}"'
        
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
                "- Return ONLY the URL starting with https://\n"
                f"Results: {results}"
            )
            logger.info(f"[LINKEDIN_AGENT] LLM prompt | company: '{company_name}' | prompt_length: {len(prompt)}")
            
            response = self.llm.invoke(prompt)
            url = response.content.strip()
            logger.info(f"[LINKEDIN_AGENT] LLM response | company: '{company_name}' | response: {url}")
            
            # Basic validation and cleanup using regex
            match = re.search(r'https://www\.linkedin\.com/company/[\w-]+/?', url)
            if match:
                clean_url = match.group(0).rstrip('/')
                logger.info(f"[LINKEDIN_AGENT] LinkedIn URL found | url: {clean_url}")
                return clean_url
            else:
                logger.warning(f"[LINKEDIN_AGENT] No valid LinkedIn company URL found in LLM response | response: {url}")
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

    def _scrape_website(self, company_name: str, url: str) -> Dict:
        """Scrapes website and attempts to extract structured ground truth data."""
        logger.info(f"[LINKEDIN_AGENT] Scraping website | url: {url}")
        base_data = {"name": company_name, "url": url, "data_source": "website"}
        
        try:
            response = requests.post(
                "https://api.firecrawl.dev/v2/scrape",
                headers={"Authorization": f"Bearer {config.FIRECRAWL_API_KEY}"},
                json={"url": url, "onlyMainContent": True, "formats": ["markdown"]},
                timeout=30,
            )
            
            if response.ok:
                markdown = response.json().get("data", {}).get("markdown", "")
                if not markdown:
                    logger.warning(f"[LINKEDIN_AGENT] Website scrape returned empty markdown | url: {url}")
                    return base_data
                
                logger.info(f"[LINKEDIN_AGENT] Website content retrieved | url: {url} | length: {len(markdown)}")
                
                # Try to extract structured data for ground truth
                prompt = (
                    f"Analyze this website text for {company_name}. "
                    "Extract a JSON object with these exact keys: "
                    "'description' (2-3 sentence summary), 'industry' (short string), "
                    "'headquarters' (City, Country format if possible), 'founded' (year). "
                    "If a field cannot be found, use 'N/A'.\n"
                    "Return ONLY valid JSON, no markdown formatting.\n\n"
                    f"Website Text:\n{markdown[:6000]}"
                )
                
                try:
                    llm_response = self.llm.invoke(prompt).content.strip()
                    
                    # Clean up common LLM JSON formatting mistakes
                    clean_json = llm_response.strip()
                    # Strip markdown code blocks
                    clean_json = re.sub(r'^```json\s*', '', clean_json)
                    clean_json = re.sub(r'\s*```$', '', clean_json)
                    # If LLM added explanation before/after, try to extract just the JSON
                    json_match = re.search(r'\{.*\}', clean_json, re.DOTALL)
                    if json_match:
                        clean_json = json_match.group(0)
                    
                    extracted_data = json.loads(clean_json)
                    
                    logger.info(f"[LINKEDIN_AGENT] Website structured data extracted successfully | url: {url}")
                    return {**base_data, **extracted_data, "website": url}
                    
                except json.JSONDecodeError as je:
                    logger.warning(f"[LINKEDIN_AGENT] Failed to parse JSON from website scrape | error: {str(je)}")
                    # Fallback to just description if JSON fails
                    return {**base_data, "description": "Failed to extract structured data from website.", "website": url}
            else:
                logger.error(f"[LINKEDIN_AGENT] Website scrape failed | url: {url} | status: {response.status_code}")
        except Exception as e:
            logger.error(f"[LINKEDIN_AGENT] Website scrape error | url: {url} | error: {str(e)}")
            
        return {**base_data, "website": url}

# agent_flow.py
import config
import datetime
import requests
import logging
from typing import List, Optional, TypedDict
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch
from langgraph.graph import StateGraph, END
from tools import scrape_linkedin_company
from google.cloud import logging as cloud_logging

# Setup structured GCP logging
try:
    client = cloud_logging.Client()
    client.setup_logging()
    logging.info("GCP Cloud Logging initialized")
except Exception as e:
    logging.basicConfig(level=logging.INFO)
    logging.warning(f"Failed to initialize GCP logging, using basic logging: {e}")

# --- 1. Define Only What LLM Needs to Generate ---

class LinkedInURL(BaseModel):
    url: str = Field(description="The LinkedIn company profile URL")

class JobOpening(BaseModel):
    title: str = Field(description="The job title")
    location: str = Field(description="Location of the job")
    link: str = Field(description="Direct URL to the job posting")

class LLMGeneratedData(BaseModel):
    """Only the data that LLM needs to extract/generate."""
    job_openings: List[JobOpening] = Field(description="Jobs extracted from careers page")
    recent_news_summary: str = Field(description="5-10 line summary of recent company news")

# --- 2. Define the Agent's "State" ---

class AgentState(TypedDict, total=False):
    initial_input: str
    provided_url: Optional[str]
    company_name: str
    website_url: Optional[str]
    linkedin_url: Optional[str]
    linkedin_data: dict  # Raw JSON from ScrapeCreators - save as-is
    careers_page_url: Optional[str]
    careers_page_content: str  # Full scraped markdown from Firecrawl
    recent_news: str  # Raw text from Tavily
    job_openings: List[dict]  # LLM-generated jobs
    recent_news_summary: str  # LLM-generated news summary
    data_source: str  # Track where company data came from: "linkedin" or "website"

# --- 3. Define the Agent's Tools ---

tavily_tool = TavilySearch(max_results=3, api_key=config.TAVILY_API_KEY)

# --- 4. Define the Agent's Nodes ---

llm = ChatGoogleGenerativeAI(model=config.GEMINI_MODEL_NAME)

def start_node(state: AgentState):
    """Parses the initial input to kick off the flow."""
    logging.info(f"Starting research for: {state['initial_input']}")
    state['company_name'] = state['initial_input'].strip()
    
    if state.get('provided_url'):
        url = state['provided_url']
        if "linkedin.com/company" in url:
            state['linkedin_url'] = url
            logging.info(f"LinkedIn URL provided: {url}")
        else:
            state['website_url'] = url
            logging.info(f"Website URL provided: {url}")

    return state

def find_linkedin_url_node(state: AgentState):
    """If we don't have a LinkedIn URL, find it with Tavily."""
    if state.get('linkedin_url'):
        logging.info("LinkedIn URL already present, skipping search")
        return state

    query = f"official LinkedIn company profile for {state['company_name']}"
    logging.info(f"Searching for LinkedIn URL with query: {query}")
    
    try:
        results = tavily_tool.invoke(query)
        logging.debug(f"Tavily results: {results}")

        prompt = f"Find the single best LinkedIn company URL from these search results: {results}"
        url = llm.invoke(prompt).content
        
        state['linkedin_url'] = url.strip()
        logging.info(f"Found LinkedIn URL: {state['linkedin_url']}")
    except Exception as e:
        logging.error(f"Failed to find LinkedIn URL: {str(e)}", exc_info=True)
        state['linkedin_url'] = None

    return state

def scrape_company_website_fallback(state: AgentState):
    """Fallback: scrape company website directly if LinkedIn fails."""
    logging.warning("Using website fallback - scraping company website directly")
    
    if not state.get('website_url'):
        logging.error("No website URL available for fallback")
        return {
            'name': state['company_name'],
            'website': None,
            'description': 'Company information unavailable',
            'data_source': 'none'
        }
    
    try:
        logging.info(f"Scraping website: {state['website_url']}")
        url = "https://api.firecrawl.dev/v2/scrape"
        payload = {
            "url": state['website_url'],
            "onlyMainContent": True,
            "formats": ["markdown"]
        }
        headers = {
            "Authorization": f"Bearer {config.FIRECRAWL_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        content = result.get('data', {}).get('markdown', '')
        logging.info(f"Scraped {len(content)} characters from website")
        
        # Use LLM to extract basic company info from website
        extract_prompt = f"""
        Extract basic company information from this website content:
        
        {content[:5000]}
        
        Return a brief summary with:
        - Company name
        - Brief description (2-3 sentences)
        - Industry (if mentioned)
        - Location/headquarters (if mentioned)
        
        Format as plain text.
        """
        
        summary = llm.invoke(extract_prompt).content
        logging.info("Extracted company info from website")
        
        return {
            'name': state['company_name'],
            'website': state['website_url'],
            'description': summary,
            'industry': 'Unknown',
            'headquarters': 'Unknown',
            'size': 'Unknown',
            'founded': 'Unknown',
            'data_source': 'website'
        }
        
    except Exception as e:
        logging.error(f"Website fallback failed: {str(e)}", exc_info=True)
        return {
            'name': state['company_name'],
            'website': state.get('website_url'),
            'description': 'Company information unavailable',
            'data_source': 'none'
        }

def scrape_linkedin_node(state: AgentState):
    """Scrapes the LinkedIn page to get the structured JSON data."""
    logging.info(f"Attempting to scrape LinkedIn: {state.get('linkedin_url')}")
    
    if not state.get('linkedin_url'):
        logging.warning("No LinkedIn URL available, using website fallback")
        state['linkedin_data'] = scrape_company_website_fallback(state)
        state['data_source'] = state['linkedin_data'].get('data_source', 'none')
        return state

    try:
        linkedin_data = scrape_linkedin_company.invoke({"company_linkedin_url": state['linkedin_url']})
        
        # Check if ScrapeCreators returned valid data
        if not linkedin_data or not isinstance(linkedin_data, dict):
            logging.error(f"ScrapeCreators returned invalid data: {linkedin_data}")
            state['linkedin_data'] = scrape_company_website_fallback(state)
            state['data_source'] = 'website'
        elif linkedin_data.get('success') == False or not linkedin_data.get('name'):
            logging.error(f"ScrapeCreators failed: {linkedin_data.get('error', 'Unknown error')}")
            state['linkedin_data'] = scrape_company_website_fallback(state)
            state['data_source'] = 'website'
        else:
            logging.info(f"Successfully scraped LinkedIn for: {linkedin_data.get('name')}")
            state['linkedin_data'] = linkedin_data
            state['data_source'] = 'linkedin'
            
            # Update company name and website from LinkedIn data
            state['company_name'] = linkedin_data.get('name', state['company_name'])
            state['website_url'] = linkedin_data.get('website', state['website_url'])
            
    except Exception as e:
        logging.error(f"LinkedIn scrape exception: {str(e)}", exc_info=True)
        state['linkedin_data'] = scrape_company_website_fallback(state)
        state['data_source'] = 'website'

    return state

def find_jobs_and_news_node(state: AgentState):
    """Finds the careers page URL and recent news."""
    jobs_query = f"careers page job openings for {state['company_name']} site:{state['website_url']}"
    logging.info(f"Searching for careers page with query: {jobs_query}")
    
    try:
        careers_results = tavily_tool.invoke(jobs_query)
        logging.debug(f"Careers page search results: {careers_results}")
        
        careers_prompt = f"""
        From these search results, extract the single best URL for the company's careers/jobs page.
        Return ONLY the URL, nothing else.
        
        Search results:
        {careers_results}
        """
        
        careers_url = llm.invoke(careers_prompt).content.strip()
        state['careers_page_url'] = careers_url
        logging.info(f"Found careers page URL: {careers_url}")
    except Exception as e:
        logging.error(f"Failed to find careers page: {str(e)}", exc_info=True)
        state['careers_page_url'] = None

    news_query = f"recent news 2024 2025 for {state['company_name']}"
    logging.info(f"Searching for recent news with query: {news_query}")
    
    try:
        state['recent_news'] = tavily_tool.invoke(news_query)
        logging.info("News search complete")
    except Exception as e:
        logging.error(f"Failed to get news: {str(e)}", exc_info=True)
        state['recent_news'] = ""

    return state

def scrape_careers_page_node(state: AgentState):
    """Scrapes the full careers page content using Firecrawl v2 API."""
    if not state.get('careers_page_url'):
        logging.warning("No careers URL found, skipping scrape")
        state['careers_page_content'] = "No careers page found."
        return state
    
    try:
        logging.info(f"Scraping careers page: {state['careers_page_url']}")
        
        url = "https://api.firecrawl.dev/v2/scrape"
        payload = {
            "url": state['careers_page_url'],
            "onlyMainContent": True,
            "formats": ["markdown"]
        }
        headers = {
            "Authorization": f"Bearer {config.FIRECRAWL_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        state['careers_page_content'] = result.get('data', {}).get('markdown', '')
        logging.info(f"Scraped {len(state['careers_page_content'])} characters from careers page")
        
    except Exception as e:
        logging.error(f"Firecrawl scrape failed: {str(e)}", exc_info=True)
        state['careers_page_content'] = f"Failed to scrape careers page: {str(e)}"
    
    return state

def generate_final_report_node(state: AgentState):
    """Use LLM only to extract jobs from careers page and summarize news."""
    logging.info("Generating final report with LLM")

    prompt = f"""
    You are a recruitment research analyst. Extract two things:

    1. JOB OPENINGS from the careers page content:
       - Extract REAL job titles (e.g., "Senior Data Engineer", "Product Manager")
       - DO NOT extract sentences from descriptions as jobs
       - Each job needs: title, location, link (URL to apply)
       - If no jobs found or page failed to scrape, return empty array

    2. NEWS SUMMARY from recent news:
       - Summarize into 5-10 lines about recent company developments
       - Focus on growth, funding, awards, expansions, new products

    CAREERS PAGE CONTENT (Markdown):
    {state.get('careers_page_content', 'No careers page content available')}
    
    RECENT NEWS RESULTS:
    {state['recent_news']}
    
    Return structured JSON with job_openings array and recent_news_summary string.
    """
    
    try:
        structured_llm = llm.with_structured_output(LLMGeneratedData)
        llm_result = structured_llm.invoke(prompt)
        
        state['job_openings'] = [job.dict() for job in llm_result.job_openings]
        state['recent_news_summary'] = llm_result.recent_news_summary
        
        logging.info(f"Extracted {len(state['job_openings'])} jobs and news summary")
    except Exception as e:
        logging.error(f"LLM extraction failed: {str(e)}", exc_info=True)
        state['job_openings'] = []
        state['recent_news_summary'] = "Unable to generate news summary"

    return state

# --- 5. Define the Graph ---

def get_research_graph():
    builder = StateGraph(AgentState)

    builder.add_node("start", start_node)
    builder.add_node("find_linkedin_url", find_linkedin_url_node)
    builder.add_node("scrape_linkedin", scrape_linkedin_node)
    builder.add_node("find_jobs_and_news", find_jobs_and_news_node)
    builder.add_node("scrape_careers_page", scrape_careers_page_node)
    builder.add_node("generate_final_report", generate_final_report_node)

    builder.set_entry_point("start")
    builder.add_edge("start", "find_linkedin_url")
    builder.add_edge("find_linkedin_url", "scrape_linkedin")
    builder.add_edge("scrape_linkedin", "find_jobs_and_news")
    builder.add_edge("find_jobs_and_news", "scrape_careers_page")
    builder.add_edge("scrape_careers_page", "generate_final_report")
    builder.add_edge("generate_final_report", END)

    return builder.compile()

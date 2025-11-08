# agent_flow.py
import config
import datetime
import requests
from typing import List, Optional, TypedDict
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch
from langgraph.graph import StateGraph, END
from tools import scrape_linkedin_company

# --- 1. Define Only What LLM Needs to Generate ---

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

# --- 3. Define the Agent's Tools ---

tavily_tool = TavilySearch(max_results=3, api_key=config.TAVILY_API_KEY)

# --- 4. Define the Agent's Nodes ---

llm = ChatGoogleGenerativeAI(model=config.GEMINI_MODEL_NAME)

def start_node(state: AgentState):
    """Parses the initial input to kick off the flow."""
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Entering node: start_node")
    state['company_name'] = state['initial_input'].strip()
    
    if state.get('provided_url'):
        url = state['provided_url']
        if "linkedin.com/company" in url:
            state['linkedin_url'] = url
        else:
            state['website_url'] = url

    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Exiting node: start_node")
    return state

def find_linkedin_url_node(state: AgentState):
    """If we don't have a LinkedIn URL, find it with Tavily."""
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Entering node: find_linkedin_url_node")
    if state.get('linkedin_url'):
        print(f"[TRACE] {datetime.datetime.now().isoformat()}: LinkedIn URL already present, skipping search.")
        return state

    query = f"official LinkedIn company profile for {state['company_name']}"
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking Tavily for LinkedIn URL...")
    results = tavily_tool.invoke(query)
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Tavily search complete.")

    prompt = f"Find the single best LinkedIn company URL from these search results: {results}"
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking LLM for URL extraction...")
    url = llm.invoke(prompt).content
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: LLM extraction complete.")

    state['linkedin_url'] = url.strip()
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Exiting node: find_linkedin_url_node")
    return state

def scrape_linkedin_node(state: AgentState):
    """Scrapes the LinkedIn page to get the structured JSON data."""
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Entering node: scrape_linkedin_node")

    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking ScrapeCreators...")
    linkedin_data = scrape_linkedin_company.invoke({"company_linkedin_url": state['linkedin_url']})
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: ScrapeCreators complete.")

    state['linkedin_data'] = linkedin_data

    state['company_name'] = linkedin_data.get('name', state['company_name'])
    state['website_url'] = linkedin_data.get('website', state['website_url'])

    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Exiting node: scrape_linkedin_node")
    return state

def find_jobs_and_news_node(state: AgentState):
    """Finds the careers page URL and recent news."""
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Entering node: find_jobs_and_news_node")

    jobs_query = f"careers page job openings for {state['company_name']} site:{state['website_url']}"
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking Tavily to find careers page URL...")
    careers_results = tavily_tool.invoke(jobs_query)
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Tavily careers URL search complete.")
    
    careers_prompt = f"""
    From these search results, extract the single best URL for the company's careers/jobs page.
    Return ONLY the URL, nothing else.
    
    Search results:
    {careers_results}
    """
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking LLM to extract careers URL...")
    careers_url = llm.invoke(careers_prompt).content.strip()
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Extracted careers URL: {careers_url}")
    state['careers_page_url'] = careers_url

    news_query = f"recent news 2024 2025 for {state['company_name']}"
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking Tavily for news...")
    state['recent_news'] = tavily_tool.invoke(news_query)
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Tavily news search complete.")

    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Exiting node: find_jobs_and_news_node")
    return state

def scrape_careers_page_node(state: AgentState):
    """Scrapes the full careers page content using Firecrawl v2 API."""
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Entering node: scrape_careers_page_node")
    
    if not state.get('careers_page_url'):
        print(f"[TRACE] {datetime.datetime.now().isoformat()}: No careers URL found, skipping scrape.")
        state['careers_page_content'] = "No careers page found."
        return state
    
    try:
        print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking Firecrawl to scrape {state['careers_page_url']}...")
        
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
        
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        
        print(f"[TRACE] {datetime.datetime.now().isoformat()}: Firecrawl scrape complete.")
        
        # v2 API returns data.markdown
        state['careers_page_content'] = result.get('data', {}).get('markdown', '')
        print(f"[TRACE] {datetime.datetime.now().isoformat()}: Extracted {len(state['careers_page_content'])} characters of careers page content.")
        
    except Exception as e:
        print(f"[ERROR] {datetime.datetime.now().isoformat()}: Firecrawl scrape failed: {str(e)}")
        state['careers_page_content'] = f"Failed to scrape careers page: {str(e)}"
    
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Exiting node: scrape_careers_page_node")
    return state

def generate_final_report_node(state: AgentState):
    """Use LLM only to extract jobs from careers page and summarize news."""
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Entering node: generate_final_report_node")

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
    
    structured_llm = llm.with_structured_output(LLMGeneratedData)
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking LLM for jobs and news extraction...")
    llm_result = structured_llm.invoke(prompt)
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: LLM extraction complete.")

    state['job_openings'] = [job.dict() for job in llm_result.job_openings]
    state['recent_news_summary'] = llm_result.recent_news_summary

    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Extracted {len(state['job_openings'])} jobs")
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Exiting node: generate_final_report_node")
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

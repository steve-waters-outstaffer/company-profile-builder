# agent_flow.py
import config
import datetime
from typing import List, Optional, TypedDict
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch
from langgraph.graph import StateGraph, END
from tools import scrape_linkedin_company

# --- 1. Define All Data Structures (Pydantic) ---
# This is our "goal" - the final JSON output structure

class FundingRound(BaseModel):
    type: str = Field(description="Type of funding round, e.g., 'Seed'")
    date: str = Field(description="Date of the funding round")
    amount: str = Field(description="Amount raised, e.g., 'US$ 1.5M'")

class LinkedInEmployee(BaseModel):
    name: str = Field(description="Full name of the employee")
    title: str = Field(description="Job title")
    link: str = Field(description="URL to their LinkedIn profile")

class LinkedInPost(BaseModel):
    url: str
    text: str
    datePublished: str

class JobOpening(BaseModel):
    title: str = Field(description="The job title being advertised")
    location: str = Field(description="Location of the job")
    link: Optional[str] = Field(description="Direct URL to the job posting, if found")

class CompanyReport(BaseModel):
    """The final, synthesized report on the target company."""
    company_name: str = Field(description="Official name of the company")
    linkedin_url: str = Field(description="The company's LinkedIn profile URL")
    website: str = Field(description="The company's official website")
    description: str = Field(description="The company's 'About' description from LinkedIn")
    industry: str
    followers: int
    employee_count: int
    company_size_bracket: str = Field(description="e.g., 51-200 employees")
    founded_year: int
    headquarters: str = Field(description="e.g., Melbourne, Victoria")
    specialties: List[str] = Field(description="List of company specialties from LinkedIn")
    funding: Optional[FundingRound] = Field(description="Details of the last funding round")
    key_personnel: List[LinkedInEmployee] = Field(description="List of key employees")
    competitors: List[str] = Field(description="List of competitor names from 'similarPages'")
    job_openings: List[JobOpening] = Field(description="List of open jobs found")
    recent_news_summary: str = Field(description="A 2-3 sentence summary of recent news")

# --- 2. Define the Agent's "State" ---
# This is the agent's memory or "whiteboard" as it works.

class AgentState(TypedDict, total=False):
    initial_input: str
    provided_url: Optional[str]  # NEW: Explicit URL provided by user
    company_name: str
    website_url: Optional[str]
    linkedin_url: Optional[str]
    linkedin_data: dict  # Raw JSON from ScrapeCreators
    careers_page_content: str # Raw text/HTML from Tavily search
    recent_news: str # Raw text from Tavily search
    final_report: Optional[CompanyReport] # The final Pydantic object

# --- 3. Define the Agent's Tools ---

tavily_tool = TavilySearch(max_results=3, api_key=config.TAVILY_API_KEY)

# --- 4. Define the Agent's Nodes (The "Functions") ---

llm = ChatGoogleGenerativeAI(model=config.GEMINI_MODEL_NAME)

def start_node(state: AgentState):
    """Parses the initial input to kick off the flow."""
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Entering node: start_node")
    # Use the company name directly
    state['company_name'] = state['initial_input'].strip()
    
    # Check if user provided a URL explicitly
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
        return state # Skip if we already have it

    query = f"official LinkedIn company profile for {state['company_name']}"
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking Tavily for LinkedIn URL...")
    results = tavily_tool.invoke(query)
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Tavily search complete.")

    # Use LLM to extract the *best* URL from the search results
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

    # Invoke the tool properly - it's a LangChain tool, not a regular function
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking ScrapeCreators...")
    linkedin_data = scrape_linkedin_company.invoke({"company_linkedin_url": state['linkedin_url']})
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: ScrapeCreators complete.")

    state['linkedin_data'] = linkedin_data

    # Also, populate our state with confirmed data
    state['company_name'] = linkedin_data.get('name', state['company_name'])
    state['website_url'] = linkedin_data.get('website', state['website_url'])

    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Exiting node: scrape_linkedin_node")
    return state

def find_jobs_and_news_node(state: AgentState):
    """Finds the careers page and recent news."""
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Entering node: find_jobs_and_news_node")

    # Find jobs
    jobs_query = f"job openings or careers page for {state['company_name']} at {state['website_url']}"
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking Tavily for jobs...")
    state['careers_page_content'] = tavily_tool.invoke(jobs_query)
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Tavily jobs search complete.")

    # Find news
    news_query = f"recent news 2024 2025 for {state['company_name']}"
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking Tavily for news...")
    state['recent_news'] = tavily_tool.invoke(news_query)
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Tavily news search complete.")

    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Exiting node: find_jobs_and_news_node")
    return state

def generate_final_report_node(state: AgentState):
    """The final step. Synthesizes all data into the Pydantic model."""
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Entering node: generate_final_report_node")

    # This is the "synthesis" prompt
    prompt = f"""
    You are a world-class recruitment research analyst.
    Your task is to synthesize all the information I provide into a single, perfect JSON object
    matching the 'CompanyReport' structure.

    RULES:
    1.  Parse the 'linkedin_data.posts' for job openings.
    2.  Parse the 'careers_page_content' for job openings. Combine all jobs.
    3.  Extract 'similarPages' as the 'competitors' list.
    4.  Summarize 'recent_news' into a 2-3 sentence summary.
    5.  Fill in all other fields directly from the 'linkedin_data'.

    DATA:
    ---
    LinkedIn Data (JSON):
    {state['linkedin_data']}
    ---
    Careers Page Search Results (Text):
    {state['careers_page_content']}
    ---
    Recent News Search Results (Text):
    {state['recent_news']}
    ---
    
    Now, generate the final 'CompanyReport' JSON object.
    """
    
    # Use the .with_structured_output() method to force JSON
    structured_llm = llm.with_structured_output(CompanyReport)
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Invoking LLM for final report synthesis...")
    report = structured_llm.invoke(prompt)
    print(f"[TRACE] {datetime.datetime.now().isoformat()}: LLM synthesis complete.")

    state['final_report'] = report.dict() # Convert Pydantic model to dict for JSON

    print(f"[TRACE] {datetime.datetime.now().isoformat()}: Exiting node: generate_final_report_node")
    return state

# --- 5. Define the Graph (The "Flow") ---

def get_research_graph():
    builder = StateGraph(AgentState)

    # Add the nodes (functions)
    builder.add_node("start", start_node)
    builder.add_node("find_linkedin_url", find_linkedin_url_node)
    builder.add_node("scrape_linkedin", scrape_linkedin_node)
    builder.add_node("find_jobs_and_news", find_jobs_and_news_node)
    builder.add_node("generate_final_report", generate_final_report_node)

    # Add the edges (the flow)
    builder.set_entry_point("start")
    builder.add_edge("start", "find_linkedin_url")
    builder.add_edge("find_linkedin_url", "scrape_linkedin")
    builder.add_edge("scrape_linkedin", "find_jobs_and_news")
    builder.add_edge("find_jobs_and_news", "generate_final_report")
    builder.add_edge("generate_final_report", END)

    return builder.compile()

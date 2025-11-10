# agent_flow.py
import logging
from typing import TypedDict, List, Optional, Any
from langgraph.graph import StateGraph, END
from google.cloud import logging as cloud_logging
import config

# Import our new specialist agents
from agents.linkedin_agent import LinkedInAgent
from agents.news_agent import NewsAgent
from agents.jobs_agent import JobsDiscoveryAgent

# --- Setup ---
# (Keep your existing logging setup here)

# --- State Definition ---
class AgentState(TypedDict):
    initial_input: str
    provided_url: Optional[str]
    company_name: str
    website_url: Optional[str]
    # Data gathered by agents
    linkedin_data: dict          # From LinkedInAgent
    recent_news_summary: str     # From NewsAgent
    job_openings: List[dict]     # From JobsAgent
    data_source: str             # Meta-data

# --- Nodes (Now just thin wrappers around Agents) ---

def init_node(state: AgentState):
    """Just sets up the initial state based on input."""
    state['company_name'] = state['initial_input']
    # Simple check if the input IS a URL
    if state['initial_input'].startswith('http'):
        state['provided_url'] = state['initial_input']
        # Rough attempt to extract name from URL if user just gave a URL
        # (You might want better logic here or let the agents handle it)
    return state

def company_profile_node(state: AgentState):
    agent = LinkedInAgent()
    # Delegate all profile gathering logic to the agent
    data = agent.get_company_data(state['company_name'], state.get('provided_url'))

    state['linkedin_data'] = data
    state['data_source'] = data.get('data_source', 'none')
    # Update name/web if we found better ones
    state['company_name'] = data.get('name', state['company_name'])
    state['website_url'] = data.get('website', state.get('website_url'))
    return state

def news_node(state: AgentState):
    agent = NewsAgent()
    state['recent_news_summary'] = agent.get_recent_news_summary(state['company_name'])
    return state

def jobs_node(state: AgentState):
    # We need a website URL to find the careers page effectively
    company_url = state.get('website_url') or state.get('provided_url')
    if not company_url:
        state['job_openings'] = []
        return state

    # Initialize the agent with required keys
    agent = JobsDiscoveryAgent(
        firecrawl_api_key=config.FIRECRAWL_API_KEY,
        tavily_api_key=config.TAVILY_API_KEY
    )

    result = agent.discover_jobs(state['company_name'], company_url)
    state['job_openings'] = result.get('job_listings', [])
    return state

# --- Graph Construction ---
# Much simpler now: a linear flow of 3 main parallelizable tasks
# (For now we keep it linear for simplicity, but News and Jobs could run in parallel)

def get_research_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("init", init_node)
    workflow.add_node("build_profile", company_profile_node)
    workflow.add_node("get_news", news_node)
    workflow.add_node("get_jobs", jobs_node)

    workflow.set_entry_point("init")
    workflow.add_edge("init", "build_profile")
    workflow.add_edge("build_profile", "get_news")
    workflow.add_edge("get_news", "get_jobs")
    workflow.add_edge("get_jobs", END)

    return workflow.compile()
# agent_flow.py
import logging
from typing import TypedDict, List, Optional, Any
from langgraph.graph import StateGraph, END
from google.cloud import logging as cloud_logging
import config

from agents.linkedin_agent import LinkedInAgent
from agents.news_agent import NewsAgent
from agents.jobs_agent import JobsDiscoveryAgent

# Setup Cloud Logging
try:
    client = cloud_logging.Client()
    client.setup_logging()
    logger = logging.getLogger(__name__)
except Exception as e:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.warning(f"Cloud logging unavailable: {e}")

# --- State Definition ---
class AgentState(TypedDict):
    initial_input: str
    provided_url: Optional[str]
    company_name: str
    website_url: Optional[str]
    linkedin_data: dict
    recent_news_summary: str
    job_openings: List[dict]
    data_source: str

# --- Nodes ---

def init_node(state: AgentState):
    """Initialize state based on input."""
    logger.info(f"[AGENT_FLOW] INIT | input: '{state['initial_input']}' | url: '{state.get('provided_url')}'")
    
    state['company_name'] = state['initial_input']
    
    if state['initial_input'].startswith('http'):
        state['provided_url'] = state['initial_input']
        logger.info(f"[AGENT_FLOW] INIT | Detected URL as input | url: {state['initial_input']}")
    
    return state

def company_profile_node(state: AgentState):
    logger.info(f"[AGENT_FLOW] BUILD_PROFILE starting | company: '{state['company_name']}'")
    try:
        agent = LinkedInAgent()
        data = agent.get_company_data(state['company_name'], state.get('provided_url'))
        
        state['linkedin_data'] = data
        state['data_source'] = data.get('data_source', 'none')
        state['company_name'] = data.get('name', state['company_name'])
        state['website_url'] = data.get('website', state.get('website_url'))
        
        logger.info(f"[AGENT_FLOW] BUILD_PROFILE complete | company: '{state['company_name']}' | source: {state['data_source']}")
    except Exception as e:
        logger.error(f"[AGENT_FLOW] BUILD_PROFILE ERROR | company: '{state['company_name']}' | error: {str(e)}", exc_info=True)
        state['linkedin_data'] = {"error": str(e)}
        state['data_source'] = 'error'
    return state

def news_node(state: AgentState):
    logger.info(f"[AGENT_FLOW] GET_NEWS starting | company: '{state['company_name']}'")
    try:
        agent = NewsAgent()
        state['recent_news_summary'] = agent.get_recent_news_summary(state['company_name'])
        logger.info(f"[AGENT_FLOW] GET_NEWS complete | company: '{state['company_name']}'")
    except Exception as e:
        logger.error(f"[AGENT_FLOW] GET_NEWS ERROR | company: '{state['company_name']}' | error: {str(e)}", exc_info=True)
        state['recent_news_summary'] = "Error fetching news."
    return state

def jobs_node(state: AgentState):
    logger.info(f"[AGENT_FLOW] GET_JOBS starting | company: '{state['company_name']}'")
    try:
        company_url = state.get('website_url') or state.get('provided_url')
        
        if not company_url:
            logger.warning(f"[AGENT_FLOW] GET_JOBS | No URL available | company: '{state['company_name']}'")
            state['job_openings'] = []
            return state

        agent = JobsDiscoveryAgent(
            firecrawl_api_key=config.FIRECRAWL_API_KEY,
            tavily_api_key=config.TAVILY_API_KEY
        )
        result = agent.discover_jobs(state['company_name'], company_url)
        state['job_openings'] = result.get('job_listings', [])
        
        logger.info(f"[AGENT_FLOW] GET_JOBS complete | company: '{state['company_name']}' | jobs_found: {len(state['job_openings'])}")
    except Exception as e:
        logger.error(f"[AGENT_FLOW] GET_JOBS ERROR | company: '{state['company_name']}' | error: {str(e)}", exc_info=True)
        state['job_openings'] = []
    return state

# --- Graph Construction ---

def get_research_graph():
    logger.info("[AGENT_FLOW] Building research graph")
    
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

    logger.info("[AGENT_FLOW] Research graph compiled")
    return workflow.compile()

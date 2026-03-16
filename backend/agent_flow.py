# agent_flow.py
import logging
from typing import TypedDict, List, Optional, Dict
from langgraph.graph import StateGraph, END
import config

from agents.linkedin_agent import LinkedInAgent
from agents.news_agent import NewsAgent
from agents.jobs_agent import JobsDiscoveryAgent
from agents.client_summary_agent import ClientSummaryAgent

logger = logging.getLogger(__name__)

# --- State Definition ---
class AgentState(TypedDict):
    company_name: str
    url: Optional[str]
    url_type: Optional[str]  # 'website' | 'linkedin' | None
    website_url: Optional[str]
    linkedin_data: dict
    recent_news_summary: str
    job_openings: List[dict]
    data_source: str
    client_brief: Dict
    step_status: Dict  # Track step results (✅, ⚠️, ❌)

# --- Nodes ---

def init_node(state: AgentState):
    """Initialize state - company name and optional URL are already set."""
    company_name = state.get('company_name')
    url = state.get('url')
    url_type = state.get('url_type')
    
    logger.info(f"[AGENT_FLOW] INIT | company: '{company_name}' | url: '{url}' | url_type: '{url_type}'")
    
    # Initialize step status tracker
    if 'step_status' not in state:
        state['step_status'] = {}
    
    return state

def company_profile_node(state: AgentState):
    """Build company profile from LinkedIn or website."""
    company_name = state['company_name']
    logger.info(f"[AGENT_FLOW] BUILD_PROFILE starting | company: '{company_name}'")
    
    try:
        agent = LinkedInAgent()
        data = agent.get_company_data(
            company_name, 
            state.get('url'),
            state.get('url_type')
        )
        
        state['linkedin_data'] = data
        state['data_source'] = data.get('data_source', 'none')
        state['company_name'] = data.get('name', company_name)
        state['website_url'] = data.get('website', state.get('website_url'))
        
        # Mark step as complete
        state['step_status']['build_profile'] = {'status': '✅', 'source': state['data_source']}
        
        logger.info(f"[AGENT_FLOW] BUILD_PROFILE complete | company: '{state['company_name']}' | source: {state['data_source']}")
    except Exception as e:
        logger.error(f"[AGENT_FLOW] BUILD_PROFILE ERROR | company: '{company_name}' | error: {str(e)}", exc_info=True)
        state['linkedin_data'] = {"error": str(e)}
        state['data_source'] = 'error'
        state['step_status']['build_profile'] = {'status': '❌', 'error': str(e)}
    
    return state

def news_node(state: AgentState):
    """Search for recent news about company."""
    company_name = state['company_name']
    logger.info(f"[AGENT_FLOW] GET_NEWS starting | company: '{company_name}'")
    
    try:
        agent = NewsAgent()
        
        # Extract location from LinkedIn data if available
        location = None
        if state.get('linkedin_data'):
            headquarters = state['linkedin_data'].get('headquarters')
            if headquarters:
                location = headquarters
        
        state['recent_news_summary'] = agent.get_recent_news_summary(
            company_name,
            location=location,
            website=state.get('website_url')
        )
        
        state['step_status']['get_news'] = {'status': '✅', 'news_found': len(state['recent_news_summary']) > 50}
        
        logger.info(f"[AGENT_FLOW] GET_NEWS complete | company: '{company_name}'")
    except Exception as e:
        logger.error(f"[AGENT_FLOW] GET_NEWS ERROR | company: '{company_name}' | error: {str(e)}", exc_info=True)
        state['recent_news_summary'] = ""
        state['step_status']['get_news'] = {'status': '⚠️', 'reason': 'Failed to fetch news, continuing...'}
    
    return state

def jobs_node(state: AgentState):
    """Discover job openings."""
    company_name = state['company_name']
    logger.info(f"[AGENT_FLOW] GET_JOBS starting | company: '{company_name}'")
    
    try:
        company_url = state.get('website_url') or state.get('url')
        
        if not company_url:
            logger.warning(f"[AGENT_FLOW] GET_JOBS | No URL available | company: '{company_name}'")
            state['job_openings'] = []
            state['step_status']['get_jobs'] = {'status': '⚠️', 'reason': 'No URL available'}
            return state

        # Extract location from LinkedIn data if available
        location = None
        if state.get('linkedin_data'):
            headquarters = state['linkedin_data'].get('headquarters')
            if headquarters:
                location = headquarters

        agent = JobsDiscoveryAgent(
            firecrawl_api_key=config.FIRECRAWL_API_KEY,
            tavily_api_key=config.TAVILY_API_KEY
        )
        result = agent.discover_jobs(
            company_name, 
            company_url,
            location=location
        )
        state['job_openings'] = result.get('job_listings', [])
        job_source = result.get('source', 'unknown')
        
        # Track whether we used primary method or fallback
        if job_source == 'firecrawl':
            state['step_status']['get_jobs'] = {'status': '✅', 'method': 'Firecrawl', 'count': len(state['job_openings'])}
        elif job_source == 'tavily_fallback':
            state['step_status']['get_jobs'] = {'status': '⚠️', 'method': 'Tavily (Firecrawl timeout)', 'count': len(state['job_openings'])}
        else:
            state['step_status']['get_jobs'] = {'status': '⚠️', 'reason': 'No careers page found'}
        
        logger.info(f"[AGENT_FLOW] GET_JOBS complete | company: '{company_name}' | jobs_found: {len(state['job_openings'])} | source: {job_source}")
    except Exception as e:
        logger.error(f"[AGENT_FLOW] GET_JOBS ERROR | company: '{company_name}' | error: {str(e)}", exc_info=True)
        state['job_openings'] = []
        state['step_status']['get_jobs'] = {'status': '❌', 'error': str(e)}
    
    return state

def client_summary_node(state: AgentState):
    """Generate sales-ready brief."""
    company_name = state['company_name']
    logger.info(f"[AGENT_FLOW] CLIENT_SUMMARY starting | company: '{company_name}'")
    
    try:
        agent = ClientSummaryAgent()
        
        brief = agent.create_brief(
            company_name=company_name,
            linkedin_data=state.get('linkedin_data'),
            website_markdown=None,
            news_summary=state.get('recent_news_summary'),
            job_listings=state.get('job_openings')
        )
        
        state['client_brief'] = brief
        state['step_status']['client_summary'] = {'status': '✅', 'brief_generated': bool(brief)}
        
        logger.info(f"[AGENT_FLOW] CLIENT_SUMMARY complete | company: '{company_name}'")
    except Exception as e:
        logger.error(f"[AGENT_FLOW] CLIENT_SUMMARY ERROR | company: '{company_name}' | error: {str(e)}", exc_info=True)
        state['client_brief'] = {}
        state['step_status']['client_summary'] = {'status': '❌', 'error': str(e)}
    
    return state

# --- Graph Construction ---

def get_research_graph():
    logger.info("[AGENT_FLOW] Building research graph")
    
    workflow = StateGraph(AgentState)

    workflow.add_node("init", init_node)
    workflow.add_node("build_profile", company_profile_node)
    workflow.add_node("get_news", news_node)
    workflow.add_node("get_jobs", jobs_node)
    workflow.add_node("client_summary", client_summary_node)

    workflow.set_entry_point("init")
    workflow.add_edge("init", "build_profile")
    workflow.add_edge("build_profile", "get_news")
    workflow.add_edge("get_news", "get_jobs")
    workflow.add_edge("get_jobs", "client_summary")
    workflow.add_edge("client_summary", END)

    logger.info("[AGENT_FLOW] Research graph compiled")
    return workflow.compile()

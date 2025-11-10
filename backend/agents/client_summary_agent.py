import logging
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
import config

logger = logging.getLogger(__name__)


class ClientBrief(BaseModel):
    """Sales-ready company brief for recruiters."""
    company_name: str = Field(description="Company name")
    summary: str = Field(description="3-4 sentences covering what they do, who they serve, their market position, and any notable differentiators")
    hiring_context: str = Field(description="2-3 sentences on current hiring activity, growth signals, or recruitment-relevant insights")
    key_points: List[str] = Field(description="4-6 conversational bullet points a recruiter can use in a pitch or discovery call")
    approach: str = Field(description="2-4 words describing how to approach them (e.g., 'Technical and direct', 'Consultative', 'Startup energy')")
    sources_used: List[str] = Field(description="Provenance tags like 'website#about', 'linkedin#description'")


class ClientSummaryAgent:
    """Creates deterministic, grounded company briefs for sales conversations."""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=config.GEMINI_MODEL_NAME,
            temperature=0
        )
        logger.info("[CLIENT_SUMMARY_AGENT] Initialized")
    
    def create_brief(
        self,
        company_name: str,
        linkedin_data: Optional[Dict],
        website_markdown: Optional[str],
        news_summary: Optional[str],
        job_listings: Optional[List[Dict]]
    ) -> Dict:
        """Generate client brief from gathered data."""
        logger.info(f"[CLIENT_SUMMARY_AGENT] Creating brief | company: '{company_name}'")
        
        try:
            prompt = self._build_prompt(
                company_name,
                linkedin_data,
                website_markdown,
                news_summary,
                job_listings
            )
            
            structured_llm = self.llm.with_structured_output(ClientBrief)
            brief = structured_llm.invoke(prompt)
            brief_dict = self._postprocess(brief.model_dump())
            
            logger.info(
                f"[CLIENT_SUMMARY_AGENT] Brief created | company: '{company_name}' | "
                f"summary_len: {len(brief_dict['summary'])} | key_points: {len(brief_dict.get('key_points', []))} | "
                f"sources: {brief_dict['sources_used']}"
            )
            
            return brief_dict
            
        except Exception as e:
            logger.error(f"[CLIENT_SUMMARY_AGENT] ERROR | company: '{company_name}' | error: {str(e)}", exc_info=True)
            return self._fallback_brief(company_name, linkedin_data)
    
    def _build_prompt(
        self,
        company_name: str,
        linkedin_data: Optional[Dict],
        website_markdown: Optional[str],
        news_summary: Optional[str],
        job_listings: Optional[List[Dict]]
    ) -> str:
        """Build prompt from available data sources."""
        
        # Extract LinkedIn fields
        linkedin_excerpt = "N/A"
        if linkedin_data and isinstance(linkedin_data, dict):
            parts = []
            if linkedin_data.get('description'):
                parts.append(f"About: {linkedin_data['description'][:500]}")
            if linkedin_data.get('industry'):
                parts.append(f"Industry: {linkedin_data['industry']}")
            if linkedin_data.get('headquarters'):
                parts.append(f"HQ: {linkedin_data['headquarters']}")
            if linkedin_data.get('company_size'):
                parts.append(f"Size: {linkedin_data['company_size']}")
            if linkedin_data.get('founded'):
                parts.append(f"Founded: {linkedin_data['founded']}")
            linkedin_excerpt = "\n".join(parts) if parts else "N/A"
        
        # Website excerpt
        website_excerpt = "N/A"
        if website_markdown:
            website_excerpt = website_markdown[:3000]
        
        # Jobs brief
        jobs_count = len(job_listings) if job_listings else 0
        top_titles = []
        if job_listings and len(job_listings) > 0:
            top_titles = [job.get('title', 'Untitled') for job in job_listings[:3]]
        
        jobs_brief = f"- openings_count: {jobs_count}\n- sample_titles: {top_titles if top_titles else 'None'}"
        
        prompt = f"""You create factual, concise company briefs for recruiters meeting prospective clients.
Use ONLY the provided data. Be direct and useful - avoid marketing fluff unless it's a direct quote.
Write in clear, conversational Australian English.

COMPANY_NAME: {company_name}

WEBSITE_EXCERPT:
{website_excerpt}

LINKEDIN_DATA:
{linkedin_excerpt}

NEWS_SUMMARY:
{news_summary or "N/A"}

JOBS_BRIEF:
{jobs_brief}

Note: Jobs and News are displayed separately in the UI, so don't repeat those lists here.

Create a ClientBrief with:
- summary: 3-4 sentences that give a recruiter the full picture - what they do, who they serve, their market position, what makes them different or notable. Make this meaty enough to brief someone who's never heard of them.
- hiring_context: 2-3 sentences on what's happening with their hiring right now - are they growing? What roles? Any signals about their recruitment needs?
- key_points: 4-6 conversational bullet points a recruiter can reference in a pitch or discovery call. Think "talking points for a coffee meeting" not "corporate presentation slides"
- approach: 2-4 words describing how to approach them (e.g., "Technical and direct", "Consultative sell", "Fast-paced startup", "Enterprise formal")
- sources_used: tags like 'website#about', 'linkedin#description', 'news#summary', 'jobs#listings'
"""
        
        return prompt
    
    def _postprocess(self, brief_dict: Dict) -> Dict:
        """Enforce length limits and clean up output."""
        
        if 'summary' in brief_dict:
            brief_dict['summary'] = brief_dict['summary'][:600]  # Increased for meatier summary
        
        if 'hiring_context' in brief_dict:
            brief_dict['hiring_context'] = brief_dict['hiring_context'][:400]  # Slightly more room
        
        if 'key_points' in brief_dict:
            brief_dict['key_points'] = [
                bullet[:180] 
                for bullet in brief_dict['key_points'][:6]
                if bullet.strip()
            ]
        
        brief_dict = {k: v for k, v in brief_dict.items() if v}
        
        return brief_dict
    
    def _fallback_brief(self, company_name: str, linkedin_data: Optional[Dict]) -> Dict:
        """Minimal fallback if LLM fails."""
        logger.warning(f"[CLIENT_SUMMARY_AGENT] Using fallback brief | company: '{company_name}'")
        
        summary = f"{company_name} is a company"
        if linkedin_data:
            if linkedin_data.get('industry'):
                summary += f" in the {linkedin_data['industry']} industry"
            if linkedin_data.get('headquarters'):
                summary += f", headquartered in {linkedin_data['headquarters']}"
            summary += "."
        
        return {
            "company_name": company_name,
            "summary": summary,
            "hiring_context": "No current hiring signals available",
            "key_points": ["Company profile available for review"],
            "approach": "Standard",
            "sources_used": ["linkedin#basic"] if linkedin_data else []
        }

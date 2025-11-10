import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch
import config

logger = logging.getLogger(__name__)


class NewsAgent:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(model=config.GEMINI_MODEL_NAME)
        self.tavily = TavilySearch(max_results=5, api_key=config.TAVILY_API_KEY)
        logger.info("[NEWS_AGENT] Initialized")

    def get_recent_news_summary(self, company_name: str) -> str:
        logger.info(f"[NEWS_AGENT] Starting news search | company: '{company_name}'")
        try:
            query = f"recent news 2024 2025 for {company_name} -site:linkedin.com"
            logger.info(f"[NEWS_AGENT] Tavily search starting | company: '{company_name}'")
            results = self.tavily.invoke(query)
            logger.info(f"[NEWS_AGENT] Tavily search complete | company: '{company_name}'")

            prompt = f"""
            Summarize the most important recent developments for {company_name} based on these search results.
            Focus on funding, product launches, major hires, or expansions.
            Keep it to a concise 5-10 line paragraph.
            
            IMPORTANT: Return ONLY plain text with simple line breaks. Do NOT use markdown formatting, bullet points, asterisks, or special characters.
            
            SEARCH RESULTS:
            {results}
            """
            logger.info(f"[NEWS_AGENT] LLM summarization starting | company: '{company_name}'")
            summary = self.llm.invoke(prompt).content.strip()
            logger.info(f"[NEWS_AGENT] SUCCESS - Summary generated | company: '{company_name}' | length: {len(summary)}")
            return summary
        except Exception as e:
            logger.error(f"[NEWS_AGENT] ERROR | company: '{company_name}' | error: {str(e)}", exc_info=True)
            return "Could not retrieve recent news."

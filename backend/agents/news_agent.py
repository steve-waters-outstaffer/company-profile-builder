import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch
import config

class NewsAgent:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(model=config.GEMINI_MODEL_NAME)
        self.tavily = TavilySearch(max_results=5, api_key=config.TAVILY_API_KEY)

    def get_recent_news_summary(self, company_name: str) -> str:
        logging.info(f"Finding news for {company_name}")
        try:
            # 1. Search
            query = f"recent news 2024 2025 for {company_name} -site:linkedin.com"
            results = self.tavily.invoke(query)

            # 2. Summarize immediately
            prompt = f"""
            Summarize the most important recent developments for {company_name} based on these search results.
            Focus on funding, product launches, major hires, or expansions.
            Keep it to a concise 5-10 line paragraph.
            
            SEARCH RESULTS:
            {results}
            """
            return self.llm.invoke(prompt).content.strip()
        except Exception as e:
            logging.error(f"News agent failed: {e}")
            return "Could not retrieve recent news."
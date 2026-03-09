import random
import os
from dotenv import load_dotenv

# third‑party clients (optional imports)
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import google.genai as genai
except ImportError:
    try:
        import google.generativeai as genai  # fallback to deprecated library
    except ImportError:
        genai = None

from core.base_strategy import BaseStrategy
from utils import config

load_dotenv()

# configure providers
client = None
if config.OPENAI_API_KEY and OpenAI:
    client = OpenAI(api_key=config.OPENAI_API_KEY)

if config.GEMINI_API_KEY and genai:
    genai.configure(api_key=config.GEMINI_API_KEY)

class LLMStrategy(BaseStrategy):
    def __init__(self, use_api=False):
        """
        use_api = False  → Local simulated model
        use_api = True   → Call configured LLM provider (OpenAI or Gemini)
        """
        self.use_api = use_api
        self.name = "LLM_PREDICTION"

    # =====================================================
    # MAIN ANALYZE FUNCTION
    def analyze(self, market_data: dict) -> dict:

        question = market_data.get("market", "")

        price_yes = market_data.get("price_yes")
        price_no = market_data.get("price_no")

        if price_yes is None or price_no is None:
            return {
                "direction": "HOLD",
                "confidence": 0,
                "reason": "Invalid price data"
            }

        # if we are connected to a real LLM, ask it for a probability estimate
        if self.use_api:
            model_prob = self.get_llm_probability(question)
            # treat probability as fair value directly; the 0.05 offset
            # used in simulation is not needed when we have a model output
            fair_value = model_prob
        else:
            # simple demo heuristic when no API available
            fair_value = price_yes + 0.05

        edge = round((fair_value - price_yes) * 100, 2)

        # -------------------------------------------------
        # 3️⃣ Compute edge
        # Edge = Model Probability - Market Price
        edge_yes = round((fair_value - price_yes) * 100, 2)
        edge_no = round(((1 - fair_value) - price_no) * 100, 2)

        # -------------------------------------------------
        # 4️⃣ Decide direction
        direction = "HOLD"
        if edge > 0:
            direction = "BUY_YES"
        elif edge < 0:
            direction = "BUY_NO"

        # -------------------------------------------------
        # 5️⃣ Confidence (based on distance from 50%)
        confidence = round(abs(edge) * 5, 2)
        
        return {
            "direction": direction,
            "confidence_percent": confidence, # percentage
            "fair_value": fair_value,
            "edge": edge,             # %
            "strategy": self.name
        }

    # =====================================================
    # LLM PREDICTION (openai / gemini)
    def call_real_llm(self, question: str) -> float:
        """Dispatch to the provider configured in utils.config.LLM_PROVIDER."""
        provider = config.LLM_PROVIDER
        if provider == "gemini":
            return self.call_gemini_llm(question)
        else:
            return self.call_openai_llm(question)

    def call_openai_llm(self, question: str) -> float:
        if not client:
            return 0.55

        prompt = f"""
        Estimate probability (0 to 1 only number) of YES outcome:
        Market Question: {question}
        Return only decimal value.
        """

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            prob = float(response.choices[0].message.content.strip())
            return min(max(prob, 0), 1)
        except Exception:
            return 0.55

    def call_gemini_llm(self, question: str) -> float:
        # requires google-genai (or deprecated google-generativeai) package and GEMINI_API_KEY set
        if genai is None:
            return 0.55

        prompt = f"""
        Estimate probability (0 to 1 only number) of YES outcome:
        Market Question: {question}
        Return only decimal value.
        """

        try:
            # Use the newer google.genai API if available
            if hasattr(genai, 'GenerativeModel'):
                model = genai.GenerativeModel("gemini-1.5-flash")
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.2,
                        max_output_tokens=10,
                    ) if hasattr(genai, 'types') else None,
                )
            else:
                # Fallback for older google.genai API
                response = genai.Client().models.generate_content(
                    model="gemini-1.5-flash",
                    contents=prompt,
                )
            
            if response and response.text:
                prob = float(response.text.strip())
                return min(max(prob, 0), 1)
            return 0.55
        except Exception:
            return 0.55

    def get_llm_probability(self, question: str) -> float:
        if self.use_api:
            return self.call_real_llm(question)

        # Demo local logic (temporary smart simulation)
        return round(random.uniform(0.35, 0.65), 3)

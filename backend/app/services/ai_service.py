import logging
import json
from openai import AsyncOpenAI
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..core.config import settings

logger = logging.getLogger(__name__)
_openai_client = None

def get_openai_client():
    """Lazy-initialize the OpenAI client so the app starts without a key configured."""
    global _openai_client
    if _openai_client is None:
        if not settings.OPENAI_API_KEY:
            return None
        _openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client

class AIService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def get_insight(self, lead_id: str, field: str, prompt: str, refresh: bool = False) -> str:
        # Check cache first (unless refresh is requested)
        lead = await self.db.leads.find_one({"id": lead_id})
        if not lead:
            raise ValueError("Lead not found")

        if not refresh and lead.get(field):
            return lead[field]

        if not settings.OPENAI_API_KEY:
            return "AI insights require an OpenAI API key. Please configure OPENAI_API_KEY in the backend .env file."

        # Build clean lead dict for the prompt (strip MongoDB internals)
        lead_clean = {k: v for k, v in lead.items() if not k.startswith("_") and k != "id"}

        # Call OpenAI
        try:
            ai_client = get_openai_client()
            if not ai_client:
                return "AI insights require an OpenAI API key. Please configure OPENAI_API_KEY in the backend .env file."
            response = await ai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior real estate sales strategist for Rustomjee properties, "
                            "one of Mumbai's most prestigious real estate developers since 1996. "
                            "You produce concise, actionable, and data-driven insights."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Lead Data:\n{json.dumps(lead_clean, default=str)}\n\nTask: {prompt}"
                    }
                ],
                temperature=0.7,
                max_tokens=400
            )
            insight = response.choices[0].message.content.strip()

            # Cache result in lead document
            await self.db.leads.update_one(
                {"id": lead_id},
                {"$set": {field: insight}}
            )
            return insight
        except Exception as e:
            logger.error(f"Error calling OpenAI for lead {lead_id}: {e}")
            return f"Unable to generate AI insight at this time. Error: {str(e)}"

    async def generate_persona(self, lead_id: str, refresh: bool = False) -> str:
        prompt = (
            "Create a concise 2-3 sentence psychological persona of this customer based on their "
            "location, budget, configuration preference, and purchase intent. "
            "Focus on their lifestyle, motivations, and buying behavior. "
            "Use markdown bold (**text**) for key traits."
        )
        return await self.get_insight(lead_id, "aiPersonaSummary", prompt, refresh=refresh)

    async def generate_strategic_move(self, lead_id: str, refresh: bool = False) -> str:
        prompt = (
            "Suggest the single best strategic next move for the Rustomjee sales team to convert this lead. "
            "Consider their temperature, budget, project interest, and last interaction. "
            "Be specific and immediately actionable (e.g., 'Schedule a site visit to Urban Woods this weekend, "
            "emphasize the 2BHK corner unit under 2 Cr which fits their budget exactly.'). "
            "Use markdown bold (**text**) to highlight the key action."
        )
        return await self.get_insight(lead_id, "strategicNextMove", prompt, refresh=refresh)

    async def generate_call_summary(self, lead_id: str, refresh: bool = False) -> str:
        # First get the lead to find its mobile_digits
        lead = await self.db.leads.find_one({"id": lead_id})
        if not lead:
            raise ValueError("Lead not found")

        mobile_digits = lead.get("mobile_digits", "")

        # Search call_history collection by mobile_digits
        call_history_records = []
        if mobile_digits:
            call_history_records = await self.db.call_history.find(
                {"mobile_digits": mobile_digits}
            ).sort("created_at", -1).to_list(length=10)

        # Also check leads collection for call data (from webhook upserts)
        lead_call_data = []
        if mobile_digits:
            lead_call_data = await self.db.leads.find(
                {"mobile_digits": mobile_digits, "call_status": {"$exists": True, "$ne": ""}}
            ).sort("call_date", -1).to_list(length=10)

        all_calls = call_history_records + lead_call_data

        if not all_calls:
            # Fall back to transcript on the lead itself
            transcript = lead.get("transcript", "")
            if not transcript:
                prompt = (
                    "Based on this lead's profile data (no call transcript available yet), "
                    "write a brief 2-sentence status summary describing their current stage "
                    "in the sales funnel and their likely sentiment."
                )
                return await self.get_insight(lead_id, "lastCallSummary", prompt, refresh=refresh)

        call_text_parts = []
        for c in all_calls[:5]:
            date_str = str(c.get("created_at", c.get("call_date", "Unknown date")))
            transcript = c.get("transcript", "") or ""
            outcome = c.get("disposition", "") or c.get("outcome", "") or c.get("call_status", "")
            duration = c.get("duration", 0) or c.get("call_duration", 0) or 0
            call_text_parts.append(
                f"Call on {date_str} (Duration: {duration}s, Outcome: {outcome}):\n{transcript[:500] if transcript else 'No transcript.'}"
            )

        call_text = "\n\n".join(call_text_parts)

        prompt = (
            f"Summarize the recent interactions with this Rustomjee prospect. "
            f"Recent calls:\n{call_text}\n\n"
            f"Provide a concise 3-4 sentence summary covering: their current sentiment, "
            f"key objections raised, what they seem most interested in, and recommended follow-up approach."
        )
        return await self.get_insight(lead_id, "lastCallSummary", prompt, refresh=refresh)

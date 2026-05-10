from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from ...core.database import get_db

router = APIRouter()

# Default AI agents seeded if collection is empty
DEFAULT_AGENTS = [
    {
        "id": "sales-closer",
        "name": "Sales Closer Pro",
        "description": "Aggressive closing agent for hot leads",
        "color": "#C5A059",
        "prompt": (
            "You are an expert real estate sales closer for Rustomjee properties. Your goal is to:\n"
            "1. Build rapport quickly and understand the customer's immediate needs\n"
            "2. Present compelling property options based on their preferences\n"
            "3. Create urgency with limited-time offers and availability\n"
            "4. Handle objections professionally and guide towards site visit booking\n"
            "5. Always maintain a professional yet persuasive tone\n\n"
            "Key talking points:\n"
            "- Rustomjee's legacy of quality construction since 1996\n"
            "- Prime locations across Mumbai\n"
            "- Flexible payment plans and bank tie-ups\n"
            "- Ready possession and under-construction options available"
        ),
    },
    {
        "id": "nurture-agent",
        "name": "Lead Nurturer",
        "description": "Gentle follow-up agent for warm leads",
        "color": "#10B981",
        "prompt": (
            "You are a friendly real estate consultant for Rustomjee properties. Your approach is:\n"
            "1. Check in on the customer's property search progress\n"
            "2. Provide valuable market insights and updates\n"
            "3. Share new project launches and offers\n"
            "4. Answer questions patiently without pressure\n"
            "5. Keep the conversation warm and helpful\n\n"
            "Key talking points:\n"
            "- New project launches and early bird offers\n"
            "- Market trends in their preferred location\n"
            "- Investment potential and rental yields\n"
            "- Community features and lifestyle amenities"
        ),
    },
    {
        "id": "reactivation-agent",
        "name": "Re-engagement Specialist",
        "description": "Win-back agent for cold/dormant leads",
        "color": "#3B82F6",
        "prompt": (
            "You are a customer win-back specialist for Rustomjee properties. Your strategy is:\n"
            "1. Acknowledge the time gap since last interaction\n"
            "2. Understand if their property needs have changed\n"
            "3. Present new options that might interest them\n"
            "4. Offer exclusive comeback incentives\n"
            "5. Be respectful of their time and decision\n\n"
            "Key talking points:\n"
            "- 'We have exciting new options since we last spoke'\n"
            "- Exclusive offers for returning customers\n"
            "- Changed market conditions and opportunities\n"
            "- No-pressure approach with value-first conversation"
        ),
    },
]

@router.get("/", response_model=List[Dict[str, Any]])
async def list_agents(db = Depends(get_db)):
    """Return all AI agents, seeding defaults if none exist."""
    agents = await db.ai_agents.find({}, {"_id": 0}).to_list(length=50)
    if not agents:
        # Seed defaults
        seed_data = [dict(a) for a in DEFAULT_AGENTS]
        await db.ai_agents.insert_many(seed_data)
        agents = DEFAULT_AGENTS
    return agents

@router.post("/", response_model=Dict[str, Any])
async def create_agent(agent: Dict[str, Any], db = Depends(get_db)):
    """Create or update an AI agent configuration."""
    if "_id" in agent:
        del agent["_id"]
    await db.ai_agents.update_one(
        {"id": agent["id"]},
        {"$set": agent},
        upsert=True
    )
    return agent

@router.post("/seed")
async def seed_agents(db = Depends(get_db)):
    """Force-seed default agents into MongoDB."""
    for agent in DEFAULT_AGENTS:
        await db.ai_agents.update_one(
            {"id": agent["id"]},
            {"$set": agent},
            upsert=True
        )
    return {"status": "seeded", "count": len(DEFAULT_AGENTS)}

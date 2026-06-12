import asyncio
import os
import sys
import logging
import argparse
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from motor.motor_asyncio import AsyncIOMotorClient

# Make sure structured_ai_service is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.services.structured_ai_service import StructuredAIService, worthy_call_gate

MONGO_URL = os.getenv("MONGO_URL", "")
DB_NAME   = os.getenv("DB_NAME", "rustomjee_db")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

async def run(dry_run: bool):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    ai_service = StructuredAIService(db)
    
    # Target orphan leads created from Futwork push that lack qualification
    q = {
        "source": "futwork_orphan_call",
        "$or": [
            {"qualification_category": {"$in": ["", None]}},
            {"temperature": {"$in": ["", None]}},
            {"budget_category": {"$in": ["", None]}}
        ]
    }
    
    leads_cursor = db.leads.find(q)
    orphan_leads = await leads_cursor.to_list(length=1000)
    count = len(orphan_leads)
    
    print("=" * 70)
    print(f"  ORPHAN LEAD BACKFILL SCRIPT {'(DRY RUN)' if dry_run else ''}")
    print("=" * 70)
    print(f"Total orphan leads missing category/temperature data: {count}\n")
    
    if count == 0:
        client.close()
        return

    ai_eligible_count = 0
    fallback_count = 0
    
    # First pass: Determine AI eligibility (Dry run analysis)
    for lead in orphan_leads:
        lead_id = lead.get("id")
        
        # Check if lead has a worthy call associated
        worthy_call = await ai_service._latest_worthy_call_doc_for_lead(lead)
        
        if worthy_call:
            ai_eligible_count += 1
            if dry_run:
                duration = worthy_call.get("duration", 0)
                status = worthy_call.get("status", "")
                call_id = worthy_call.get("id") or worthy_call.get("call_sid")
                print(f"[AI ELIGIBLE] Lead: {lead_id} | Call: {call_id} | Status: {status} | Duration: {duration}s")
                snippet = str(worthy_call.get('transcript', ''))[:100].encode('ascii', 'ignore').decode('ascii')
                print(f"  -> Transcript snippet: {snippet}...\n")
        else:
            fallback_count += 1
            if dry_run:
                print(f"[FALLBACK] Lead: {lead_id}")
                print(f"  -> No worthy call found. Will use safe default tags.\n")

    print("-" * 70)
    print("SUMMARY OF PROPOSED ACTIONS:")
    print(f"  - AI Extractions (LLM calls): {ai_eligible_count}")
    print(f"  - Fallbacks (Safe Defaults):  {fallback_count}")
    print("-" * 70)
    
    if dry_run:
        print("\nDry run completed. No changes were made to the database.")
        print("Run without --dry-run to execute the AI extractions and database updates.")
        client.close()
        return

    # Second pass: Execute
    print("\nExecuting backfill...")
    success_count = 0
    actual_fallback_count = 0
    
    for lead in orphan_leads:
        lead_id = lead.get("id")
        if not lead_id:
            continue
            
        try:
            logger.info(f"Processing orphan lead {lead_id} via LLM extraction...")
            res = await ai_service.generate_call_summary_unified(lead_id=lead_id, refresh=True)
            
            if res and "not contain enough actionable" not in res:
                logger.info(f"Successfully processed {lead_id} via AI extraction.")
                success_count += 1
            else:
                logger.info(f"Lead {lead_id} had insufficient transcript for AI. Falling back to defaults.")
                await db.leads.update_one(
                    {"id": lead_id},
                    {"$set": {
                        "qualification_category": "Unqualified", 
                        "temperature": "Warm",
                        "budget_category": "Not Specified",
                        "location_category": "Not Specified",
                        "project": "General Inquiry"
                    }}
                )
                actual_fallback_count += 1
        except Exception as e:
            logger.error(f"Error processing lead {lead_id}: {e}")
            
    print("-" * 70)
    print(f"Finished execution.")
    print(f"Successfully updated via AI Extractions: {success_count}")
    print(f"Updated via Default fallbacks: {actual_fallback_count}")
        
    client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill missing categories on orphan leads using AI.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without making changes.")
    args = parser.parse_args()
    
    asyncio.run(run(dry_run=args.dry_run))

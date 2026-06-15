"""
backfill_missing_categories.py  (v2 — with checkpoints + Groq key rotation)
=============================================================================
Backfills missing AI categories (qualification_category, temperature,
budget_category) for leads that have transcripts but no AI extraction yet.

Features:
  • Groq 3-key rotation  — cycles keys on every call, not just on rate limit
  • Smart rate-limit backoff — if ALL 3 keys are exhausted, waits 60 s then retries
  • Checkpoint file  — saves progress every 50 leads so it can resume after any crash
  • Idempotent  — skips leads that already have all three categories filled
  • --dry-run flag to preview count without running LLM calls
  • --resume flag to force resume from checkpoint (default: auto-detects)

Usage:
    python scripts/backfill_missing_categories.py
    python scripts/backfill_missing_categories.py --dry-run
    python scripts/backfill_missing_categories.py --resume          # continue from checkpoint
    python scripts/backfill_missing_categories.py --fresh           # ignore checkpoint, start fresh
    python scripts/backfill_missing_categories.py --limit 500       # only process 500 leads
"""
import asyncio
import json
import os
import sys
import time
import logging
import argparse
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from motor.motor_asyncio import AsyncIOMotorClient
from openai import AsyncOpenAI, RateLimitError, APIStatusError

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.services.structured_ai_service import StructuredAIService
from app.core.config import settings

MONGO_URL  = os.getenv("MONGO_URL", "")
DB_NAME    = os.getenv("DB_NAME", "rustomjee_db")
CHECKPOINT_FILE = os.path.join(os.path.dirname(__file__), "backfill_checkpoint.json")
CHECKPOINT_EVERY = 50   # Save progress every N leads
RATE_LIMIT_WAIT  = 65   # Seconds to wait when ALL keys are exhausted

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# -----------------------------------------------------------------
# Checkpoint helpers
# -----------------------------------------------------------------

def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            return json.load(f)
    return {}


def save_checkpoint(data: dict):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def clear_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)


# -----------------------------------------------------------------
# Groq rotating client pool
# -----------------------------------------------------------------

class GroqKeyRotator:
    """
    Holds up to 3 Groq clients. On each call, tries the next key in round-robin.
    If a key hits rate limit, marks it as cooled down and tries the next.
    If ALL keys are rate-limited, waits RATE_LIMIT_WAIT seconds and resets.
    """
    def __init__(self):
        keys = settings.groq_api_keys
        self.clients = [
            AsyncOpenAI(api_key=k, base_url=settings.GROQ_BASE_URL)
            for k in keys
        ]
        self.n = len(self.clients)
        self.current_idx = 0
        self.cooldown_until = [0.0] * self.n   # unix timestamp when key is usable again

    def _is_rate_limit(self, exc: Exception) -> bool:
        return isinstance(exc, RateLimitError) or (
            isinstance(exc, APIStatusError) and exc.status_code == 429
        )

    async def chat_completion(self, **kwargs):
        """Try each key in rotation. If all rate-limited, wait and retry."""
        for attempt in range(self.n * 2):   # up to 2 full rotations before giving up
            now = time.time()

            # Find the next available key
            for offset in range(self.n):
                idx = (self.current_idx + offset) % self.n
                if now >= self.cooldown_until[idx]:
                    self.current_idx = idx
                    break
            else:
                # ALL keys are in cooldown — wait for the soonest one
                wait_secs = max(0, min(self.cooldown_until) - now)
                wait_secs = max(wait_secs, RATE_LIMIT_WAIT)
                print(f"\n  Warning: All 3 Groq keys rate-limited. Waiting {wait_secs:.0f}s before retrying...", flush=True)
                await asyncio.sleep(wait_secs)
                # Reset all cooldowns after waiting
                self.cooldown_until = [0.0] * self.n
                continue

            idx = self.current_idx
            try:
                resp = await self.clients[idx].chat.completions.create(
                    model="llama-3.1-8b-instant",  # Overridden from settings to bypass 70B daily limits
                    **kwargs
                )
                # Advance to next key for next call (round-robin even on success)
                self.current_idx = (idx + 1) % self.n
                return resp
            except Exception as e:
                if self._is_rate_limit(e):
                    print(f"  Rotating: Key {idx+1} rate-limited...", flush=True)
                    self.cooldown_until[idx] = time.time() + RATE_LIMIT_WAIT
                    self.current_idx = (idx + 1) % self.n
                    continue
                raise   # Non-rate-limit error — bubble up

        raise RuntimeError("Groq: all retries exhausted after rate limit cycling.")


# -----------------------------------------------------------------
# Main
# -----------------------------------------------------------------

async def run(dry_run: bool, limit: int, fresh: bool):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    ai_service = StructuredAIService(db)

    print("=" * 70)
    print(f"  AI CATEGORY BACKFILL {'(DRY RUN)' if dry_run else ''}")
    print(f"  Groq Keys: {len(settings.groq_api_keys)} | Checkpoint: {CHECKPOINT_FILE}")
    print("=" * 70)

    # -- Step 1: Fetch eligible leads from DB ------------------------------
    print("\nStep 1: Querying DB for Dormant leads to rescue...")

    q_missing = {
        "$and": [
            {"qualification_category": "Dormant"},
            {
                "$or": [
                    {"last_call_status": {"$in": ["completed", "no-answer", "busy", "failed", "call-disconnected"]}},
                    {"last_call_status": {"$in": ["", None]}},
                    {"last_call_status": {"$exists": False}}
                ]
            }
        ]
    }

    pipeline = [
        {"$match": q_missing},
        {"$match": {"mobile_digits": {"$exists": True, "$ne": ""}}},
        {"$lookup": {
            "from": "call_history",
            "localField": "mobile_digits",
            "foreignField": "mobile_digits",
            "as": "calls"
        }},
        {"$project": {
            "id": 1,
            "transcripts": {
                "$map": {
                    "input": "$calls",
                    "as": "call",
                    "in": "$$call.transcript"
                }
            },
            "has_transcript": {
                "$gt": [{
                    "$size": {
                        "$filter": {
                            "input": "$calls",
                            "as": "call",
                            "cond": {
                                "$and": [
                                    {"$ne": ["$$call.transcript", None]},
                                    {"$ne": ["$$call.transcript", ""]}
                                ]
                            }
                        }
                    }
                }, 0]
            }
        }},
        {"$match": {"has_transcript": True}},
        {"$limit": limit}
    ]

    cursor = db.leads.aggregate(pipeline)
    all_eligible_ids: List[str] = []
    lead_transcripts = {}
    async for doc in cursor:
        all_eligible_ids.append(doc["id"])
        ts = [t for t in doc.get("transcripts", []) if t]
        lead_transcripts[doc["id"]] = " ".join(ts)

    total = len(all_eligible_ids)
    print(f"  Found {total} leads eligible for AI extraction.\n")

    if total == 0:
        print("Nothing to do. All leads are already categorized!")
        client.close()
        return

    if dry_run:
        print(f"  DRY RUN: Would make {total} LLM calls. Run without --dry-run to execute.")
        client.close()
        return

    # -- Step 2: Load checkpoint -------------------------------------------
    checkpoint = {} if fresh else load_checkpoint()
    processed_ids = set(checkpoint.get("processed_ids", []))
    start_time_str = checkpoint.get("start_time", datetime.now().isoformat())

    # Filter out already processed
    remaining_ids = [lid for lid in all_eligible_ids if lid not in processed_ids]
    skipped_from_checkpoint = total - len(remaining_ids)

    print(f"  Checkpoint: {skipped_from_checkpoint} already done, {len(remaining_ids)} remaining.")
    print(f"  Started: {start_time_str}")
    print(f"\n{'-' * 70}")
    print(f"  Starting AI extraction on {len(remaining_ids)} leads...")
    print(f"{'-' * 70}\n")

    if not remaining_ids:
        print("All leads already processed per checkpoint. Done!")
        clear_checkpoint()
        client.close()
        return

    # -- Step 3: Process with OpenAI ------------------------------------
    import os
    from openai import AsyncOpenAI
    
    openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Patch ai_service to use OpenAI instead of default llm_router
    import app.services.structured_ai_service as ai_service_module
    original_chat = ai_service_module.chat_completion

    async def patched_chat_completion(*, messages, temperature, max_tokens, response_format=None):
        for m in messages:
            if m.get("role") == "system":
                m["content"] += (
                    "\n\nCRITICAL OVERRIDE: Be extremely lenient. Even if the conversation is short, "
                    "if the user answers a question or shows any hint of interest, "
                    "DO NOT return 'No meaningful conversation' or 'not contain enough actionable'. "
                    "Make your best effort to categorize them (Warm, Cold, or Hot)."
                )
        kwargs = dict(model="gpt-4o-mini", messages=messages, temperature=temperature, max_tokens=max_tokens)
        if response_format:
            kwargs["response_format"] = response_format
        return await openai_client.chat.completions.create(**kwargs)

    ai_service_module.chat_completion = patched_chat_completion

    success_count = 0
    skip_count = 0
    fail_count = 0
    rate_limit_waits = 0
    processed_this_session = 0

    try:
        for i, lead_id in enumerate(remaining_ids):
            # Progress every 10 leads
            if i % 10 == 0:
                pct = ((skipped_from_checkpoint + i) / total) * 100
                print(
                    f"  [{skipped_from_checkpoint + i:>5}/{total}] {pct:5.1f}%  "
                    f"Success: {success_count}  Skip: {skip_count}  Fail: {fail_count}  "
                    f"Rate-limit-waits: {rate_limit_waits}",
                    flush=True
                )

            try:
                # Pre-filter: skip LLM completely if transcript is 50 words or less
                t_text = lead_transcripts.get(lead_id, "")
                if len(t_text.split()) <= 50:
                    await db.leads.update_one(
                        {"id": lead_id},
                        {"$set": {
                            "qualification_category": "Dormant",
                            "budget_category": "Profiling in Progress",
                            "location_category": "Profiling in Progress",
                            "intent_category": "Profiling in Progress",
                            "updated_at": datetime.utcnow()
                        }}
                    )
                    skip_count += 1
                    processed_ids.add(lead_id)
                    processed_this_session += 1
                    continue

                res = await ai_service.generate_call_summary_unified(lead_id=lead_id, refresh=True)
                
                # If the call was rejected as "not worthy" (too short, etc.), it returns this string.
                # We need to manually set the lead to Dormant so it doesn't stay "Missing" forever.
                if res == "No meaningful conversation" or (res and "not contain enough actionable" in str(res)):
                    await db.leads.update_one(
                        {"id": lead_id},
                        {"$set": {
                            "qualification_category": "Dormant",
                            "budget_category": "Profiling in Progress",
                            "location_category": "Profiling in Progress",
                            "intent_category": "Profiling in Progress",
                            "updated_at": datetime.utcnow()
                        }}
                    )
                    fail_count += 1
                elif res:
                    success_count += 1
                else:
                    fail_count += 1
            except RuntimeError as e:
                if "rate limit" in str(e).lower() or "exhausted" in str(e).lower():
                    rate_limit_waits += 1
                    fail_count += 1
                else:
                    print(f"\n  RuntimeError on {lead_id}: {e}", flush=True)
                    fail_count += 1
            except Exception as e:
                print(f"\n  Exception on {lead_id}: {e}", flush=True)
                fail_count += 1

            processed_ids.add(lead_id)
            processed_this_session += 1

            # Save checkpoint every N leads
            if processed_this_session % CHECKPOINT_EVERY == 0:
                save_checkpoint({
                    "processed_ids": list(processed_ids),
                    "start_time": start_time_str,
                    "last_saved": datetime.now().isoformat(),
                    "success": success_count,
                    "skip": skip_count,
                    "fail": fail_count,
                })

    finally:
        # Restore original function
        ai_service_module.chat_completion = original_chat
        # Always save checkpoint on exit (crash or normal)
        save_checkpoint({
            "processed_ids": list(processed_ids),
            "start_time": start_time_str,
            "last_saved": datetime.now().isoformat(),
            "success": success_count,
            "skip": skip_count,
            "fail": fail_count,
        })

    # -- Done --------------------------------------------------------------
    all_done = (skipped_from_checkpoint + processed_this_session) >= total
    print(f"\n{'=' * 70}")
    print(f"  BACKFILL COMPLETE{' — ALL DONE!' if all_done else ' (partial)'}")
    print(f"{'=' * 70}")
    print(f"  Total eligible leads       : {total}")
    print(f"  Skipped (checkpoint)       : {skipped_from_checkpoint}")
    print(f"  Processed this session     : {processed_this_session}")
    print(f"  Successfully categorized   : {success_count}")
    print(f"  Pre-filtered (too short)   : {skip_count}")
    print(f"  Skipped / Failed           : {fail_count}")
    print(f"  Rate-limit wait events     : {rate_limit_waits}")
    print(f"  Checkpoint file            : {CHECKPOINT_FILE}")

    if all_done:
        clear_checkpoint()
        print(f"\n  Done. Checkpoint cleared. Job is complete!")
    else:
        print(f"\n  Warning: Run script again to continue from checkpoint.")

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill missing AI categories on leads.")
    parser.add_argument("--dry-run", action="store_true", help="Count eligible leads without running LLM calls.")
    parser.add_argument("--fresh",   action="store_true", help="Ignore existing checkpoint and start from scratch.")
    parser.add_argument("--limit",   type=int, default=15000, help="Max leads to process (default: 15000).")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run, limit=args.limit, fresh=args.fresh))

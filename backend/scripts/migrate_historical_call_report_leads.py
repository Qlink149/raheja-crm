"""
migrate_historical_call_report_leads.py — One-time resumable migration

Reads backend/unmasked_call_report_completed.csv and upserts grouped leads into MongoDB.

Rules:
- Group rows by Unmasked_Mobile_Number (normalized to mobile_digits).
- A lead is "Worthy" of an AI call iff any row has:
    - transcript length > 50 chars, OR
    - non-empty extractedData_call_summary
- If not Worthy: store as Dormant and skip OpenAI (category fields only on update).
- If Worthy: combine transcripts + summaries, call StructuredAIService.extract_unified()
  (same pipeline as webhooks) to fill budget_category, location_category, intent_category,
  disposition, matches, qualification_category, and related AI fields.

Existing leads: $set only category / AI classification fields so other CRM data is preserved.
New leads: $set identity + categories, $setOnInsert for defaults.

Clear checkpoint to re-process every mobile (PowerShell):

  Remove-Item -Force .\\scripts\\checkpoints\\historical_call_report_leads.json

Bash:

  rm -f scripts/checkpoints/historical_call_report_leads.json

Or clear via this script then run as usual:

  python scripts/migrate_historical_call_report_leads.py --reset-checkpoint

Run from backend:

  cd backend
  python scripts/migrate_historical_call_report_leads.py
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from tqdm import tqdm

# Allow imports from backend/app/...
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.structured_ai_service import StructuredAIService
from app.utils.csv_processor import normalize_phone


DEFAULT_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "unmasked_call_report_completed.csv")
DEFAULT_CHECKPOINT_PATH = os.path.join(
    os.path.dirname(__file__), "checkpoints", "historical_call_report_leads.json"
)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    s = str(v)
    return s.strip()


def _is_placeholder_name(name: str) -> bool:
    n = (name or "").strip()
    if not n:
        return True
    if n in ("-", ".", "Unknown", "unknown", "NA", "N/A"):
        return True
    return False


def _parse_iso_dt(raw: Any) -> Optional[datetime]:
    s = _safe_str(raw)
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _is_worthy(rows: Sequence[Dict[str, Any]]) -> bool:
    for r in rows:
        transcript = _safe_str(r.get("transcript"))
        summary = _safe_str(r.get("extractedData_call_summary"))
        if len(transcript) > 50:
            return True
        if summary:
            return True
    return False


def _combined_text(rows: Sequence[Dict[str, Any]], *, max_chars: int = 15000) -> str:
    # Sort by createdAt when possible; fallback to original order.
    enriched: List[Tuple[Optional[datetime], int, Dict[str, Any]]] = []
    for idx, r in enumerate(rows):
        enriched.append((_parse_iso_dt(r.get("createdAt")), idx, r))
    enriched.sort(key=lambda t: (t[0] is None, t[0] or datetime.min, t[1]))

    parts: List[str] = []
    for created_at, _, r in enriched:
        call_sid = _safe_str(r.get("callSid") or r.get("callSid".lower()) or "")
        status = _safe_str(r.get("status"))
        disposition = _safe_str(r.get("disposition"))
        summary = _safe_str(r.get("extractedData_call_summary"))
        transcript = _safe_str(r.get("transcript"))

        header = [
            f"--- call {call_sid or 'unknown'} ---",
            f"createdAt: {created_at.isoformat() if created_at else ''}",
            f"status: {status}",
            f"disposition: {disposition}",
        ]
        block = "\n".join(header)
        if summary:
            block += f"\nsummary: {summary}"
        if transcript:
            block += f"\ntranscript:\n{transcript}"
        parts.append(block)

    text = "\n\n".join(parts).strip()
    if len(text) <= max_chars:
        return text
    # Keep the most recent tail; prepend a short note.
    tail = text[-max_chars:]
    return ("[TRUNCATED: keeping most recent content]\n\n" + tail).strip()


def _dormant_category_patch(now: datetime) -> Dict[str, Any]:
    """Category-only fields for CSV rows that are not worthy of OpenAI (no transcript/summary signal)."""
    return {
        "budget_match": False,
        "area_match": False,
        "timeline_match": False,
        "qualification_category": "Dormant",
        "budget_category": "Other",
        "location_category": "Other",
        "intent_category": "Other",
        "updated_at": now,
    }


def _best_metadata_row(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Prefer latest row with disposition or recording for unified extraction context."""
    enriched: List[Tuple[Optional[datetime], int, Dict[str, Any]]] = []
    for idx, r in enumerate(rows):
        enriched.append((_parse_iso_dt(r.get("createdAt")), idx, r))
    enriched.sort(key=lambda t: (t[0] is None, t[0] or datetime.min, t[1]))
    for _, _, r in reversed(enriched):
        if _safe_str(r.get("disposition")) or _safe_str(r.get("recording_url")):
            return r
    return rows[-1] if rows else {}


def _seed_key_from_mobile(mobile_digits: str) -> str:
    return hashlib.sha256(mobile_digits.encode()).hexdigest()


def _best_name(rows: Sequence[Dict[str, Any]]) -> str:
    # Prefer the latest non-placeholder name.
    for r in reversed(rows):
        name = _safe_str(r.get("contextDetails_recipientData_customer_name"))
        if not _is_placeholder_name(name):
            return name
    return "Unknown"


def _best_raw_mobile(rows: Sequence[Dict[str, Any]], mobile_digits: str) -> str:
    # Keep original unmasked if present; otherwise format digits.
    for r in reversed(rows):
        raw = _safe_str(r.get("Unmasked_Mobile_Number") or r.get("contextDetails_recipientPhoneNumber") or "")
        if raw:
            return raw
    return mobile_digits


def _pick_correlation(rows: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    # Prefer completed calls for ids if present; else last row.
    def score(r: Dict[str, Any]) -> int:
        st = _safe_str(r.get("status")).lower()
        return 1 if st == "completed" else 0

    best = None
    best_score = -1
    for r in rows:
        s = score(r)
        if s > best_score:
            best_score = s
            best = r
    best = best or (rows[-1] if rows else {})

    out: Dict[str, str] = {}
    for src, dst in (
        ("contextDetails_recipientData_campaignId", "campaign_id"),
        ("contextDetails_recipientData_leadId", "futwork_lead_id"),
        ("contextDetails_recipientData_unique_identifier", "external_id"),
    ):
        v = _safe_str(best.get(src))
        if v:
            out[dst] = v
    return out


def _load_checkpoint(path: str) -> set[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        completed = data.get("completed_mobile_digits") or []
        return {str(x).strip() for x in completed if str(x).strip()}
    except FileNotFoundError:
        return set()
    except Exception:
        # If checkpoint is corrupted, start fresh (but do not crash).
        return set()


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


async def _retry_openai(
    fn,
    *,
    retries: int = 5,
    base_delay_s: float = 1.0,
    verbose: bool = False,
    openai_context: str = "",
) -> Any:
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return await fn()
        except Exception as e:
            last_err = e
            if verbose:
                ctx = f" {openai_context}" if openai_context else ""
                tqdm.write(
                    f"[OPENAI RETRY]{ctx} attempt {attempt + 1}/{retries}: {e!s}"
                )
            # Exponential backoff with a small deterministic jitter.
            delay = base_delay_s * (2 ** attempt) + (attempt * 0.1)
            await asyncio.sleep(delay)
    if last_err:
        raise last_err
    raise RuntimeError("OpenAI retry failed without exception")


async def migrate(
    *,
    csv_path: str,
    checkpoint_path: str,
    concurrency: int,
    dry_run: bool,
    flush_every: int,
    reset_checkpoint: bool,
    verbose: bool,
) -> None:
    load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

    mongo_url = os.environ.get("MONGO_URL", "").strip()
    db_name = os.environ.get("DB_NAME", "rustomjee_db").strip() or "rustomjee_db"
    groq_keys = [
        k
        for k in (
            os.environ.get("GROQ_API_KEY_1", "").strip(),
            os.environ.get("GROQ_API_KEY_2", "").strip(),
            os.environ.get("GROQ_API_KEY_3", "").strip(),
        )
        if k
    ]
    openai_key = (os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY") or "").strip()
    llm_configured = bool(groq_keys) or bool(openai_key)

    if not mongo_url and not dry_run:
        raise RuntimeError("Missing MONGO_URL in backend/.env (or environment).")

    if reset_checkpoint:
        _atomic_write_json(
            checkpoint_path,
            {
                "schema_version": 1,
                "updated_at": _utcnow().isoformat(),
                "completed_mobile_digits": [],
            },
        )
        print("Checkpoint cleared (completed_mobile_digits reset).\n")

    # ---- Load + group CSV -------------------------------------------------
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    skipped_rows = 0

    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_phone = _safe_str(
                row.get("Unmasked_Mobile_Number")
                or row.get("contextDetails_recipientPhoneNumber")
                or row.get("telephonyData_toNumber")
                or ""
            )
            mobile_digits = normalize_phone(raw_phone)
            if not mobile_digits:
                skipped_rows += 1
                continue
            groups[mobile_digits].append(row)

    completed = _load_checkpoint(checkpoint_path)
    mobile_digits_all = sorted(groups.keys())
    mobile_digits_todo = [m for m in mobile_digits_all if m not in completed]

    worthy_count = sum(1 for m in mobile_digits_todo if _is_worthy(groups[m]))
    dormant_only_count = len(mobile_digits_todo) - worthy_count

    print(f"\nUnique leads (by mobile_digits): {len(mobile_digits_all):,}")
    print(f"Already completed (checkpoint):  {len(completed):,}")
    print(f"To process now:                 {len(mobile_digits_todo):,}")
    print(f"Worthy (OpenAI):                {worthy_count:,}")
    print(f"Not-worthy (Dormant, no AI):    {dormant_only_count:,}")
    print(f"Skipped rows (no phone):        {skipped_rows:,}\n")

    if dry_run:
        return

    if worthy_count > 0 and not llm_configured:
        raise RuntimeError(
            "GROQ_API_KEY_1 (or OPENAI_API_KEY / EMERGENT_LLM_KEY) is required when there are worthy leads to extract."
        )

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    ai_svc = StructuredAIService(db)

    sem = asyncio.Semaphore(max(1, int(concurrency)))

    checkpoint_completed = set(completed)
    newly_completed: List[str] = []

    async def process_one(mobile_digits: str) -> Tuple[str, Optional[str]]:
        rows = groups[mobile_digits]
        name = _best_name(rows)
        raw_mobile = _best_raw_mobile(rows, mobile_digits)
        corr = _pick_correlation(rows)
        now = _utcnow()

        worthy = _is_worthy(rows)
        if not worthy:
            category_patch = _dormant_category_patch(now)
        else:
            text = _combined_text(rows)
            meta = _best_metadata_row(rows)
            try:
                if verbose:
                    tqdm.write(f"[OPENAI] Calling for lead: {name} ({mobile_digits})")
                async with sem:
                    extraction = await _retry_openai(
                        lambda: ai_svc.extract_unified(
                            customer_name=name,
                            phone_number=raw_mobile or mobile_digits,
                            system_disposition=_safe_str(meta.get("disposition")),
                            recording_url=_safe_str(meta.get("recording_url")),
                            transcript=text,
                        ),
                        retries=5,
                        base_delay_s=1.0,
                        verbose=verbose,
                        openai_context=f"{name} ({mobile_digits})",
                    )
                if verbose:
                    tqdm.write(
                        f"[SUCCESS] {name} -> Cat: {extraction.location_category}, "
                        f"Budget: {extraction.budget_category}, Dispo: {extraction.disposition}."
                    )
                category_patch = ai_svc.to_db_lead_patch_unified(extraction)
            except Exception as e:
                if verbose:
                    tqdm.write(f"[ERROR] OpenAI failed for lead: {name} ({mobile_digits}): {e!s}")
                return mobile_digits, str(e)

        existing = await db.leads.find_one({"mobile_digits": mobile_digits}, {"_id": 1})

        set_doc: Dict[str, Any] = dict(category_patch)
        if not existing:
            set_doc.update(
                {
                    "mobile": raw_mobile,
                    "mobile_digits": mobile_digits,
                    "full_name": name,
                    "source": "Historical call report migration",
                    **corr,
                }
            )

        qc = (category_patch.get("qualification_category") or "").strip()
        lead_set_on_insert: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "created_at": now,
            "_seed_key": _seed_key_from_mobile(mobile_digits),
            "temperature": "",
            "qualification_category": qc or "Dormant",
            "status": "Inquiry",
            "project": "",
            "is_vip": False,
            "is_hni": False,
            "vip_category": "",
            "futwork_sync_status": "pushed",
            "email": "",
            "location": "",
            "budget": "",
            "intent": "",
        }

        update_doc: Dict[str, Any] = {"$set": set_doc}
        if not existing:
            update_doc["$setOnInsert"] = lead_set_on_insert

        try:
            await db.leads.update_one({"mobile_digits": mobile_digits}, update_doc, upsert=True)
            return mobile_digits, None
        except Exception as e:
            if verbose:
                tqdm.write(f"[ERROR] DB update failed for lead: {name} ({mobile_digits}): {e!s}")
            return mobile_digits, str(e)

    errors: List[Tuple[str, str]] = []

    # Process in chunks to keep memory stable and to checkpoint frequently.
    pbar = tqdm(total=len(mobile_digits_todo), desc="Migrating leads", unit="lead")
    try:
        batch: List[str] = []
        for m in mobile_digits_todo:
            batch.append(m)
            if len(batch) < max(concurrency * 5, 50):
                continue

            results = await asyncio.gather(*(process_one(x) for x in batch))
            batch = []

            for mobile_digits, err in results:
                pbar.update(1)
                if err:
                    errors.append((mobile_digits, err))
                    continue
                checkpoint_completed.add(mobile_digits)
                newly_completed.append(mobile_digits)

            if len(newly_completed) >= flush_every:
                _atomic_write_json(
                    checkpoint_path,
                    {
                        "schema_version": 1,
                        "updated_at": _utcnow().isoformat(),
                        "completed_mobile_digits": sorted(checkpoint_completed),
                    },
                )
                newly_completed.clear()

        if batch:
            results = await asyncio.gather(*(process_one(x) for x in batch))
            for mobile_digits, err in results:
                pbar.update(1)
                if err:
                    errors.append((mobile_digits, err))
                    continue
                checkpoint_completed.add(mobile_digits)
                newly_completed.append(mobile_digits)
    finally:
        pbar.close()

    if newly_completed:
        _atomic_write_json(
            checkpoint_path,
            {
                "schema_version": 1,
                "updated_at": _utcnow().isoformat(),
                "completed_mobile_digits": sorted(checkpoint_completed),
            },
        )

    client.close()

    print("\nDone.")
    if errors:
        print(f"Errors: {len(errors):,}")
        # Print a small sample for immediate visibility.
        for mobile_digits, err in errors[:10]:
            print(f" - {mobile_digits}: {err}")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", dest="csv_path", default=DEFAULT_CSV_PATH)
    p.add_argument("--checkpoint", dest="checkpoint_path", default=DEFAULT_CHECKPOINT_PATH)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--flush-every", type=int, default=25)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Clear completed_mobile_digits in the checkpoint file before running (re-process all mobiles).",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Log each OpenAI call, success, retries, and errors via tqdm.write (progress bar safe).",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        migrate(
            csv_path=args.csv_path,
            checkpoint_path=args.checkpoint_path,
            concurrency=args.concurrency,
            dry_run=bool(args.dry_run),
            flush_every=max(1, int(args.flush_every)),
            reset_checkpoint=bool(args.reset_checkpoint),
            verbose=bool(args.verbose),
        )
    )

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ...core.config import settings
from ...core.database import get_db
from ...utils.campaign_stats import (
    compute_inc_delta,
    is_terminal_status,
    map_disposition_to_key,
    map_futwork_raw_to_live_key,
)
from ...utils.csv_processor import normalize_phone

logger = logging.getLogger(__name__)
router = APIRouter()


# Map Futwork raw status to internal `call_history.status` (normalized, snake-friendly).
STATUS_NORMALIZATION_MAP = {
    "call-disconnected": "call-disconnected",  # keep distinct from "completed"
    "completed":         "completed",
    "no-answer":         "no-answer",
    "no_answer":         "no-answer",
    "busy":              "busy",
    "failed":            "failed",
    "call-failed":       "failed",
    "in-progress":       "in-progress",
    "ringing":           "ringing",
    "initiated":         "initiated",
}


def _normalize_status(status_raw: str) -> str:
    """Pass-through normalization that preserves intermediate states (so we can see them in DB)."""
    if not status_raw:
        return ""
    key = str(status_raw).strip().lower()
    return STATUS_NORMALIZATION_MAP.get(key, key or "")


def _as_dict(value: Any) -> Dict[str, Any]:
    """Return value if it's a dict, else an empty dict. Guards against malformed payloads."""
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    """Parse value to int via float, defaulting on garbage like 'abc' or None."""
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


@router.post("/futwork")
async def futwork_webhook(
    request: Request,
    x_api_key: str = Header(None),
    x_webhook_secret: str = Header(None),
    db=Depends(get_db),
):
    """
    Handles Futwork postback webhooks (platform.futwork.ai schema).

    A single call lifecycle produces multiple webhooks (initiated -> ringing ->
    in-progress -> completed/call-disconnected/failed). This handler:

    1. Logs the raw payload (greppable by callSid + phase).
    2. Requires `callSid` so we can dedupe by it.
    3. Reads the previous `call_history` row to compute delta increments,
       so retries / lifecycle replays do NOT inflate campaign counters.
    4. Upserts `call_history` with `$setOnInsert(created_at)` and
       `$push(status_history)` for full debug visibility.
    5. Updates the matching `leads` document, but refuses to overwrite a
       prior terminal status with a delayed intermediate webhook.
    """
    # ---- Auth ---------------------------------------------------------------
    received_key = x_api_key or x_webhook_secret
    if settings.FUTWORK_WEBHOOK_SECRET:
        if received_key != settings.FUTWORK_WEBHOOK_SECRET:
            logger.warning("Unauthorized Futwork webhook | received_key=%s", received_key)
            raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        data = await request.json()
    except Exception as e:
        raw_body = await request.body()
        logger.error(f"FUTWORK WEBHOOK ERROR | Failed to parse JSON payload | Error: {e} | Raw Body: {raw_body}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=400, detail="Webhook payload must be a JSON object"
        )

    # ---- Verbose lifecycle log (one line per hook) --------------------------
    logger.info(
        "FUTWORK WEBHOOK INCOMING | Headers: %s | Raw Payload: %s",
        dict(request.headers),
        json.dumps(data, default=str),
    )
    logger.info(
        "Futwork webhook parsed | callSid=%s | status=%s",
        data.get("callSid"),
        data.get("status"),
    )

    # ---- Top-level identifiers ----------------------------------------------
    call_sid       = (data.get("callSid") or "").strip()
    lead_id        = data.get("leadId", "")
    campaign_id    = data.get("campaignId", "")
    agent_id       = data.get("agentId", "")
    status_raw     = data.get("status", "") or ""
    transcript     = data.get("transcript", "")
    disposition    = (data.get("disposition") or "").strip()
    extracted_data = data.get("extractedData")

    # ---- Dedup precondition: require callSid --------------------------------
    if not call_sid:
        logger.warning(
            "Futwork webhook ignored: missing callSid | status=%s | leadId=%s",
            status_raw,
            lead_id,
        )
        return {"status": "ignored", "reason": "missing callSid"}

    # ---- Telephony data (duration & recordingUrl live here) -----------------
    telephony        = _as_dict(data.get("telephonyData"))
    duration_seconds = _safe_int(telephony.get("duration"), default=0)
    recording_url    = telephony.get("recordingUrl", "") or ""
    to_number        = telephony.get("toNumber", "") or ""
    from_number      = telephony.get("fromNumber", "") or ""
    provider         = telephony.get("provider", "") or ""
    provider_call_id = telephony.get("providerCallId", "") or ""

    # ---- Context details (echoes back the original lead payload) ------------
    context        = _as_dict(data.get("contextDetails"))
    raw_phone      = context.get("recipientPhoneNumber", "") or to_number
    recipient_data = _as_dict(context.get("recipientData"))
    customer_name  = recipient_data.get("customer_name", "Unknown")

    # ---- Normalize phone ----------------------------------------------------
    mobile_digits = normalize_phone(str(raw_phone))
    if not mobile_digits:
        logger.warning(
            "Futwork webhook ignored: no phone | callSid=%s | status=%s | toNumber=%s",
            call_sid,
            status_raw,
            to_number,
        )
        return {"status": "ignored", "reason": "no phone", "call_sid": call_sid}

    # ---- Resolve campaign name from campaignId ------------------------------
    campaign_name = ""
    if campaign_id:
        resolve_clauses: list[Dict[str, Any]] = [
            {"futwork_campaign_id": campaign_id},
            {"id": campaign_id},
        ]
        env_fid = (settings.FUTWORK_CAMPAIGN_ID or "").strip()
        if env_fid and env_fid != campaign_id:
            resolve_clauses.append({"id": env_fid})
        campaign_doc = await db.campaigns.find_one(
            {"$or": resolve_clauses},
            {"name": 1},
        )
        campaign_name = campaign_doc.get("name", "") if campaign_doc else ""

    # ---- Read previous state (drives delta math) ----------------------------
    prev_call: Optional[Dict[str, Any]] = await db.call_history.find_one(
        {"id": call_sid},
        {"futwork_status": 1, "disposition": 1, "status": 1},
    )
    prev_status_raw = (prev_call or {}).get("futwork_status", "") or ""
    prev_disposition = (prev_call or {}).get("disposition", "") or ""

    # ---- Terminal-status guard ----------------------------------------------
    # If the prior webhook for this callSid was already terminal (completed,
    # busy, no-answer, call-disconnected, failed) and this one is NOT terminal
    # (a delayed `ringing` / `in-progress` arriving after `completed`),
    # we MUST NOT regress `futwork_status`/`status` or rebalance counters.
    # We still append to status_history for the audit trail.
    prev_terminal     = is_terminal_status(prev_status_raw)
    incoming_terminal = is_terminal_status(status_raw)
    is_stale_intermediate = prev_terminal and not incoming_terminal

    if is_stale_intermediate:
        logger.info(
            "ignoring stale intermediate webhook | callSid=%s | prev=%s | new=%s",
            call_sid,
            prev_status_raw,
            status_raw,
        )

    # ---- Build call_history $set fields (only value-bearing) ----------------
    call_status = _normalize_status(status_raw)
    set_fields: Dict[str, Any] = {
        "id":               call_sid,
        "call_sid":         call_sid,
        "lead_id":          lead_id,
        "campaign_id":      campaign_id,
        "agent_id":         agent_id,
        "phone":            raw_phone,
        "mobile_digits":    mobile_digits,
        "customer_name":    customer_name,
        "campaign":         campaign_name,
        "to_number":        to_number,
        "from_number":      from_number,
        "provider":         provider,
        "provider_call_id": provider_call_id,
        "updated_at":       datetime.utcnow(),
    }
    # Only regress futwork_status/status if we are NOT in a stale-intermediate
    # case (otherwise a delayed `in-progress` after `completed` would corrupt
    # the terminal record).
    if not is_stale_intermediate:
        set_fields["futwork_status"] = status_raw
        set_fields["status"]         = call_status

    # Only persist value-bearing fields when present so a late ringing
    # webhook can't overwrite a terminal transcript / recording with "".
    if duration_seconds:           set_fields["duration"]       = duration_seconds
    if recording_url:              set_fields["recording_url"]  = recording_url
    if transcript:                 set_fields["transcript"]     = transcript
    if disposition:                set_fields["disposition"]    = disposition
    if extracted_data is not None: set_fields["extracted_data"] = extracted_data

    await db.call_history.update_one(
        {"id": call_sid},
        {
            "$set": set_fields,
            "$setOnInsert": {"created_at": datetime.utcnow()},
            "$push": {"status_history": {"status": status_raw, "at": datetime.utcnow()}},
        },
        upsert=True,
    )

    # ---- Compute campaign deltas (live_status + dispositions) ---------------
    # Stale intermediates contribute zero delta so we never decrement a
    # counter that was already incremented for the terminal phase.
    if is_stale_intermediate:
        live_delta: Dict[str, int]  = {}
        dispo_delta: Dict[str, int] = {}
    else:
        prev_live_key = map_futwork_raw_to_live_key(prev_status_raw)
        new_live_key  = map_futwork_raw_to_live_key(status_raw)
        live_delta    = compute_inc_delta(prev_live_key, new_live_key)

        prev_dispo_key = map_disposition_to_key(prev_disposition)
        new_dispo_key  = map_disposition_to_key(disposition)
        dispo_delta    = compute_inc_delta(prev_dispo_key, new_dispo_key)

    if campaign_id and (live_delta or dispo_delta):
        try:
            or_clauses = [{"futwork_campaign_id": campaign_id}]
            if campaign_name:
                or_clauses.append({"name": campaign_name})
            fid = (settings.FUTWORK_CAMPAIGN_ID or "").strip()
            if fid:
                or_clauses.append({"id": fid})

            inc: Dict[str, int] = {}
            for k, v in live_delta.items():
                inc[f"live_status.{k}"] = v
            for k, v in dispo_delta.items():
                inc[f"dispositions.{k}"] = v

            await db.campaigns.update_one(
                {"$or": or_clauses},
                {
                    "$inc": inc,
                    "$set": {"updated_at": datetime.utcnow()},
                },
            )
        except Exception:
            logger.exception(
                "Failed to apply campaign deltas | campaign_id=%s | live_delta=%s | dispo_delta=%s",
                campaign_id,
                live_delta,
                dispo_delta,
            )

    # ---- Update lead — respect terminal status ------------------------------
    update_filter: Dict[str, Any] = {"mobile_digits": mobile_digits}
    if lead_id:
        update_filter = {
            "$or": [{"futwork_lead_id": lead_id}, {"mobile_digits": mobile_digits}]
        }

    existing_lead = await db.leads.find_one(
        update_filter,
        {"last_call_status_raw": 1, "last_call_status": 1},
    )
    prior_status_raw = (existing_lead or {}).get("last_call_status_raw") or (
        existing_lead or {}
    ).get("last_call_status", "") or ""
    prev_lead_terminal = is_terminal_status(prior_status_raw)
    can_advance_lead   = incoming_terminal or not prev_lead_terminal

    lead_set: Dict[str, Any] = {
        "mobile":        raw_phone,
        "mobile_digits": mobile_digits,
        "updated_at":    datetime.utcnow(),
    }
    # Backfill the indexed correlation key so the next webhook can match by
    # futwork_lead_id directly instead of falling back to phone digits.
    if lead_id:
        lead_set["futwork_lead_id"] = lead_id
    if customer_name and customer_name != "Unknown":
        lead_set["full_name"] = customer_name

    if can_advance_lead:
        lead_set["last_call_date"]       = datetime.utcnow()
        lead_set["last_call_status"]     = call_status
        lead_set["last_call_status_raw"] = status_raw
        if duration_seconds:
            lead_set["last_call_duration"] = duration_seconds
        if recording_url:
            lead_set["last_recording_url"] = recording_url
        if disposition:
            lead_set["disposition"] = disposition
        if transcript:
            lead_set["transcript"] = transcript

    lead_result = await db.leads.update_one(update_filter, {"$set": lead_set}, upsert=False)

    # ---- Final summary log --------------------------------------------------
    logger.info(
        "Futwork webhook processed | callSid=%s | phase=%s | live_delta=%s | dispo_delta=%s | "
        "lead_advanced=%s | lead_matched=%s",
        call_sid,
        status_raw,
        live_delta,
        dispo_delta,
        can_advance_lead,
        bool(lead_result.matched_count),
    )

    return {
        "status": "ok",
        "call_sid": call_sid,
        "phase": status_raw,
        "live_delta": live_delta,
        "dispo_delta": dispo_delta,
        "lead_advanced": can_advance_lead,
        "lead_matched": bool(lead_result.matched_count),
    }

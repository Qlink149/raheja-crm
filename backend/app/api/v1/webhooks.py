import json
import logging
from typing import Any, Dict, List, Optional

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
from ...utils.lead_qualification_tags import apply_canonical_tags_to_lead_patch
from ...utils.context_updates import persist_lead_context_updates
from ...utils.orphan_call_link import ensure_lead_for_unmatched_webhook
from ...utils.webhook_lead import (
    call_history_lead_id_value,
    has_webhook_id_hints,
    lead_update_filter,
    resolve_lead_for_webhook,
)
from ...core.time_utils import utc_now
from ...services.notification_service import create_notification, _lead_display_name
from ...services.structured_ai_service import (
    StructuredAIService,
    not_worthy_call_history_patch,
    worthy_call_gate,
)

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


_LEAD_RESOLVE_PROJECTION = {
    "id": 1,
    "last_call_status_raw": 1,
    "last_call_status": 1,
    "futwork_lead_id": 1,
    "assigned_user_id": 1,
}


async def _resolve_existing_lead(
    db,
    *,
    webhook_futwork_id: str,
    echo_client_id: str,
    raw_phone: str,
    mobile_digits: str,
) -> Optional[Dict[str, Any]]:
    """Match lead: phone first, then optional client/futwork ids."""
    existing_lead = await resolve_lead_for_webhook(
        db,
        webhook_futwork_id=webhook_futwork_id,
        echo_client_id=echo_client_id,
        raw_phone=raw_phone,
        projection=_LEAD_RESOLVE_PROJECTION,
    )
    if not existing_lead and echo_client_id:
        logger.error(
            "Futwork webhook: client_lead_id echo present but no lead matched | client_lead_id=%s | futwork_lead_id=%s",
            echo_client_id,
            webhook_futwork_id,
        )
    return existing_lead


async def _notify_ai_call_summary(
    db,
    *,
    call_sid: str,
    lead_id: str,
    unified_extraction: Any,
    effective_transcript: str,
    duration_seconds: int,
) -> None:
    """Send rep notification after terminal AI extraction (matched + orphan leads)."""
    lead_row = await db.leads.find_one(
        {"id": lead_id},
        {
            "_id": 0,
            "id": 1,
            "full_name": 1,
            "first_name": 1,
            "last_name": 1,
            "assigned_user_id": 1,
            "assigned_to": 1,
        },
    )
    if not lead_row or not lead_row.get("assigned_user_id"):
        return
    summary = (getattr(unified_extraction, "call_summary", None) or "")[:120]
    if not summary and effective_transcript:
        summary = str(effective_transcript)[:120] + "..."
    today = utc_now().strftime("%Y-%m-%d")
    await create_notification(
        db,
        type="ai_call_summary",
        title="AI Call Summary",
        message=summary or f"High-intent call ({duration_seconds or 0}s)",
        lead_id=lead_row["id"],
        lead_name=_lead_display_name(lead_row),
        recipient_user_id=lead_row["assigned_user_id"],
        recipient_name=lead_row.get("assigned_to") or "",
        assigned_to=lead_row.get("assigned_to") or "",
        severity="medium",
        urgency="action_needed",
        dedupe_key=f"notification:call:{call_sid}:{today}",
    )


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
    echo_client_id = str(
        recipient_data.get("leadId")
        or recipient_data.get("unique_identifier")
        or ""
    ).strip()
    webhook_futwork_id = str(lead_id or "").strip()

    # ---- Normalize phone (call_history only; not used to find lead doc) ----
    mobile_digits = normalize_phone(str(raw_phone))

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
        {"futwork_status": 1, "disposition": 1, "status": 1, "structured_extraction": 1, "ai_disposition": 1},
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

    # ---- Resolve lead before call_history upsert (internal lead_id on call row) ----
    existing_lead = await _resolve_existing_lead(
        db,
        webhook_futwork_id=webhook_futwork_id,
        echo_client_id=echo_client_id,
        raw_phone=raw_phone,
        mobile_digits=mobile_digits,
    )
    lead_update_flt = lead_update_filter(existing_lead)
    internal_lead_id = call_history_lead_id_value(
        existing_lead,
        echo_client_id=echo_client_id,
        webhook_futwork_id=webhook_futwork_id,
    )

    # ---- Build call_history $set fields (only value-bearing) ----------------
    call_status = _normalize_status(status_raw)
    set_fields: Dict[str, Any] = {
        "id":               call_sid,
        "call_sid":         call_sid,
        "lead_id":          internal_lead_id,
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
        "updated_at":       utc_now(),
    }
    if webhook_futwork_id:
        set_fields["futwork_lead_id"] = webhook_futwork_id
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
            "$setOnInsert": {"created_at": utc_now()},
            "$push": {"status_history": {"status": status_raw, "at": utc_now()}},
        },
        upsert=True,
    )

    # ---- Compute campaign deltas (live_status only) -------------------------
    # Stale intermediates contribute zero delta so we never decrement a
    # counter that was already incremented for the terminal phase.
    if is_stale_intermediate:
        live_delta: Dict[str, int]  = {}
    else:
        prev_live_key = map_futwork_raw_to_live_key(prev_status_raw)
        new_live_key  = map_futwork_raw_to_live_key(status_raw)
        live_delta    = compute_inc_delta(prev_live_key, new_live_key)

    if campaign_id and live_delta:
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

            await db.campaigns.update_one(
                {"$or": or_clauses},
                {
                    "$inc": inc,
                    "$set": {"updated_at": utc_now()},
                },
            )
        except Exception:
            logger.exception(
                "Failed to apply campaign live deltas | campaign_id=%s | live_delta=%s",
                campaign_id,
                live_delta,
            )

    # ---- Update lead snapshot (existing_lead resolved above) ------------------
    prior_status_raw = (existing_lead or {}).get("last_call_status_raw") or (
        existing_lead or {}
    ).get("last_call_status", "") or ""
    prev_lead_terminal = is_terminal_status(prior_status_raw)
    can_advance_lead   = incoming_terminal or not prev_lead_terminal

    lead_set: Dict[str, Any] = {
        "updated_at": utc_now(),
    }
    if raw_phone:
        lead_set["mobile"] = raw_phone
    if mobile_digits:
        lead_set["mobile_digits"] = mobile_digits
    if webhook_futwork_id:
        lead_set["futwork_lead_id"] = webhook_futwork_id
    if customer_name and customer_name != "Unknown":
        lead_set["full_name"] = customer_name

    if can_advance_lead:
        lead_set["last_call_date"]       = utc_now()
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

        # If we got a terminal update, mark futwork_sync_status as pushed
        # so this lead is removed from the pending eligible push queue.
        if incoming_terminal:
            lead_set["futwork_sync_status"] = "pushed"

    # Maintain alias field for frontend compatibility when lead has residence location.
    # (Some writers only set current_residence_location; frontend also reads the alias.)
    # We do not overwrite with empty.
    if lead_set.get("current_residence_location") and not lead_set.get("current_residential_location"):
        lead_set["current_residential_location"] = lead_set.get("current_residence_location")

    lead_set = apply_canonical_tags_to_lead_patch(lead_set, existing_lead or {})

    lead_created = False
    lead_created_id = ""
    if (
        settings.auto_create_lead_from_orphan_webhook
        and not existing_lead
        and incoming_terminal
        and not is_stale_intermediate
        and len(mobile_digits) == 10
    ):
        call_doc_for_orphan = dict(set_fields)
        call_doc_for_orphan.setdefault("id", call_sid)
        call_doc_for_orphan.setdefault("call_sid", call_sid)
        ensured_lead, is_new_lead, orphan_reason = await ensure_lead_for_unmatched_webhook(
            db,
            call_doc=call_doc_for_orphan,
            lead_set_patch=lead_set if can_advance_lead else {
                k: lead_set[k]
                for k in ("updated_at", "mobile", "mobile_digits", "full_name", "futwork_lead_id")
                if k in lead_set
            },
            auto_create_enabled=True,
            auto_assign_new=True,
        )
        if ensured_lead and ensured_lead.get("id"):
            lead_created = is_new_lead
            lead_created_id = str(ensured_lead["id"])
            existing_lead = await db.leads.find_one(
                {"id": lead_created_id},
                {"_id": 0, **_LEAD_RESOLVE_PROJECTION},
            )
            lead_update_flt = lead_update_filter(existing_lead)
            internal_lead_id = lead_created_id
            set_fields["lead_id"] = internal_lead_id
            await db.call_history.update_one(
                {"id": call_sid},
                {"$set": {"lead_id": internal_lead_id}},
            )
        else:
            logger.warning(
                "Futwork webhook: orphan lead ensure failed | callSid=%s | reason=%s | mobile_digits=%s",
                call_sid,
                orphan_reason,
                mobile_digits,
            )

    lead_result = None
    if lead_update_flt:
        lead_result = await db.leads.update_one(lead_update_flt, {"$set": lead_set})
    elif has_webhook_id_hints(webhook_futwork_id, echo_client_id) or mobile_digits:
        logger.warning(
            "Futwork webhook: no lead matched | futwork_lead_id=%s | client_lead_id=%s | callSid=%s",
            webhook_futwork_id,
            echo_client_id,
            call_sid,
        )

    # ---- Structured AI extraction (terminal webhooks only) ------------------
    unified_extraction = None
    if can_advance_lead and incoming_terminal and (transcript or extracted_data):
        try:
            svc = StructuredAIService(db)
            effective_transcript = transcript or (_as_dict(extracted_data).get("transcript") if extracted_data else "") or ""
            worthy, reasons = worthy_call_gate(
                status_raw,
                effective_transcript,
                duration_seconds=duration_seconds,
                disposition=disposition,
            )
            if not worthy:
                logger.info(
                    "Skipping OpenAI extraction (not worthy) | callSid=%s | status=%s | reasons=%s",
                    call_sid,
                    status_raw,
                    reasons,
                )
                await db.call_history.update_one(
                    {"id": call_sid},
                    {"$set": not_worthy_call_history_patch()},
                )
            else:
                unified_extraction = await svc.extract_unified(
                    customer_name=customer_name,
                    phone_number=raw_phone,
                    system_disposition=disposition,
                    recording_url=recording_url,
                    transcript=effective_transcript,
                )
                await db.call_history.update_one(
                    {"id": call_sid},
                    {"$set": svc.to_db_call_history_patch_unified(unified_extraction)},
                )
                if lead_update_flt:
                    ai_lead_patch = apply_canonical_tags_to_lead_patch(
                        svc.to_db_lead_patch_unified(unified_extraction),
                        existing_lead or {},
                    )
                    await db.leads.update_one(
                        lead_update_flt,
                        {
                            "$set": ai_lead_patch,
                            "$unset": {"aiPersonaSummary": "", "strategicNextMove": ""},
                        },
                    )
                    if existing_lead and existing_lead.get("id"):
                        await _notify_ai_call_summary(
                            db,
                            call_sid=call_sid,
                            lead_id=str(existing_lead["id"]),
                            unified_extraction=unified_extraction,
                            effective_transcript=effective_transcript,
                            duration_seconds=duration_seconds,
                        )
                else:
                    late_lead = await resolve_lead_for_webhook(
                        db,
                        webhook_futwork_id=webhook_futwork_id,
                        echo_client_id=echo_client_id,
                        raw_phone=raw_phone,
                        projection=_LEAD_RESOLVE_PROJECTION,
                    )
                    late_flt = lead_update_filter(late_lead)
                    if late_flt and unified_extraction is not None:
                        lead_patch = apply_canonical_tags_to_lead_patch(
                            {
                                **lead_set,
                                **svc.to_db_lead_patch_unified(unified_extraction),
                            },
                            late_lead or {},
                        )
                        await db.leads.update_one(
                            late_flt,
                            {
                                "$set": lead_patch,
                                "$unset": {"aiPersonaSummary": "", "strategicNextMove": ""},
                            },
                        )
                        lid = str(late_lead.get("id") or "")
                        if lid:
                            await db.call_history.update_one(
                                {"id": call_sid},
                                {"$set": {"lead_id": lid}},
                            )
                        logger.info(
                            "Linked orphan call to lead after AI extraction | callSid=%s | lead_id=%s",
                            call_sid,
                            lid,
                        )
                        if late_lead.get("id"):
                            await _notify_ai_call_summary(
                                db,
                                call_sid=call_sid,
                                lead_id=str(late_lead["id"]),
                                unified_extraction=unified_extraction,
                                effective_transcript=effective_transcript,
                                duration_seconds=duration_seconds,
                            )
                    else:
                        logger.warning(
                            "Skipping lead AI patch (no matched lead) | callSid=%s",
                            call_sid,
                        )
        except Exception:
            logger.exception("Structured AI extraction failed | callSid=%s", call_sid)

    # ---- Campaign dispositions: always align with transcript-derived outcome --
    # Prefer AI extraction; fall back to system disposition when AI is unavailable.
    if not is_stale_intermediate and campaign_id and incoming_terminal:
        try:
            svc = StructuredAIService(db)
            prev_bucket = None
            if prev_call:
                prev_struct = (prev_call or {}).get("structured_extraction") or {}
                prev_ai_disp = (prev_struct.get("disposition") if isinstance(prev_struct, dict) else None) or (prev_call or {}).get("ai_disposition")
                prev_bucket = (
                    svc.campaign_bucket_from_ai_disposition_value(prev_ai_disp)
                    if prev_ai_disp
                    else map_disposition_to_key(prev_disposition)
                )

            if unified_extraction is not None:
                new_bucket = svc.campaign_bucket_from_ai_disposition_value(unified_extraction.disposition)
            else:
                new_bucket = map_disposition_to_key(disposition)

            dispo_delta = compute_inc_delta(prev_bucket, new_bucket)
            if dispo_delta:
                or_clauses = [{"futwork_campaign_id": campaign_id}]
                if campaign_name:
                    or_clauses.append({"name": campaign_name})
                fid = (settings.FUTWORK_CAMPAIGN_ID or "").strip()
                if fid:
                    or_clauses.append({"id": fid})
                inc: Dict[str, int] = {f"dispositions.{k}": v for k, v in dispo_delta.items()}
                await db.campaigns.update_one(
                    {"$or": or_clauses},
                    {"$inc": inc, "$set": {"updated_at": utc_now()}},
                )
        except Exception:
            logger.exception("Failed to apply disposition delta | callSid=%s", call_sid)

    # ---- Context updates (same pipeline for matched + orphan-created leads) --
    final_lead_id = str(
        lead_created_id
        or (existing_lead or {}).get("id")
        or internal_lead_id
        or ""
    ).strip()
    if final_lead_id and incoming_terminal and can_advance_lead:
        try:
            await persist_lead_context_updates(db, final_lead_id)
        except Exception:
            logger.exception(
                "Failed to persist context_updates | lead_id=%s | callSid=%s",
                final_lead_id,
                call_sid,
            )

    # ---- Final summary log --------------------------------------------------
    lead_matched = bool(lead_update_flt) and (
        bool(lead_result and lead_result.matched_count) or bool(lead_created_id)
    )
    logger.info(
        "Futwork webhook processed | callSid=%s | phase=%s | live_delta=%s | "
        "lead_advanced=%s | lead_matched=%s | lead_created=%s | lead_id=%s | mobile_digits=%s",
        call_sid,
        status_raw,
        live_delta,
        can_advance_lead,
        lead_matched,
        lead_created,
        lead_created_id or (existing_lead or {}).get("id", ""),
        mobile_digits,
    )

    return {
        "status": "ok",
        "call_sid": call_sid,
        "phase": status_raw,
        "live_delta": live_delta,
        "lead_advanced": can_advance_lead,
        "lead_matched": lead_matched,
        "lead_created": lead_created,
        "lead_id": lead_created_id or (existing_lead or {}).get("id", ""),
    }

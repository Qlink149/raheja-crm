from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase
from openai import AsyncOpenAI

from ..core.config import settings
from ..models.structured_extraction import (
    BatchSummaryObject,
    BatchSummaryPayload,
    StructuredCallExtraction,
    StructuredDisposition,
    UnifiedStructuredExtraction,
)
from ..utils.csv_processor import get_intent_category

logger = logging.getLogger(__name__)
_openai_client: Optional[AsyncOpenAI] = None

NOT_WORTHY_MESSAGE = "No meaningful conversation"
PERSONA_INSUFFICIENT = "Insufficient interaction to determine buyer persona."
STRATEGIC_INSUFFICIENT = "Insufficient interaction to recommend a strategic next move."


def get_openai_client() -> Optional[AsyncOpenAI]:
    global _openai_client
    if _openai_client is None:
        if not settings.OPENAI_API_KEY:
            return None
        _openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def mask_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) <= 4:
        return "**********" if digits else ""
    last4 = digits[-4:]
    return f"******{last4}"


INSIGHT_TRANSCRIPT_MAX_CHARS = 16000

_INSIGHT_LEAD_WHITELIST = frozenset(
    {
        "full_name",
        "project",
        "location",
        "budget",
        "temperature",
        "intent",
        "configuration",
        "bhk",
        "disposition",
        "lastCallSummary",
        "presales_description",
        "context_summary",
        "budget_category",
        "location_category",
        "intent_category",
        "qualification_category",
        "is_vip",
        "is_hni",
        "vip_category",
        "current_residence_location",
        "current_residential_location",
        "possession_requirement",
        "reason_for_purchase",
        "suggested_next_project",
        "designation",
        "carpet_area",
        "ai_summary",
        "ai_key_signals",
        "ai_disposition",
    }
)

_INSIGHT_LOW_SIGNAL_STRINGS = frozenset(
    {
        "",
        "other",
        "profiling in progress",
        "unknown",
        "not captured",
    }
)


def _truncate_transcript(text: str, max_chars: int = INSIGHT_TRANSCRIPT_MAX_CHARS) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    omitted = len(t) - max_chars
    return t[:max_chars] + f"\n\n[... transcript truncated, {omitted} chars omitted ...]"


def _insight_value_is_meaningful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    s = str(value).strip()
    if not s:
        return False
    if s.lower() in _INSIGHT_LOW_SIGNAL_STRINGS:
        return False
    return True


def _lead_context_for_insight(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Slim CRM payload for persona/strategic insights — omits empty/default noise."""
    out: Dict[str, Any] = {}
    for key in _INSIGHT_LEAD_WHITELIST:
        if key not in lead:
            continue
        value = lead[key]
        if not _insight_value_is_meaningful(value):
            continue
        out[key] = value
    return out


def _call_context_for_insight(call_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Latest worthy call context: transcript (primary) plus optional structured extraction."""
    transcript = _truncate_transcript((call_doc.get("transcript") or "").strip())
    ctx: Dict[str, Any] = {
        "call_id": call_doc.get("id") or call_doc.get("call_sid"),
        "created_at": call_doc.get("created_at"),
        "status": call_doc.get("status"),
        "futwork_status": call_doc.get("futwork_status"),
        "disposition": call_doc.get("disposition"),
        "transcript": transcript,
    }
    se = call_doc.get("structured_extraction") or {}
    if isinstance(se, dict) and int(se.get("schema_version") or 0) == 2:
        extraction: Dict[str, Any] = {}
        for key in (
            "call_summary",
            "key_signals",
            "preferred_location",
            "unit_configuration",
            "disposition",
        ):
            val = se.get(key)
            if _insight_value_is_meaningful(val):
                extraction[key] = val
        if extraction:
            ctx["structured_extraction"] = extraction
    return {k: v for k, v in ctx.items() if _insight_value_is_meaningful(v)}


def _build_insight_user_content(
    lead: Dict[str, Any],
    prompt: str,
    *,
    worthy_call: Optional[Dict[str, Any]] = None,
) -> str:
    if worthy_call is not None:
        lead_ctx = _lead_context_for_insight(lead)
        call_ctx = _call_context_for_insight(worthy_call)
        parts = [
            "Lead Data (CRM — supplementary):\n"
            + json.dumps(lead_ctx, default=str, ensure_ascii=False),
            "Latest worthy call:\n" + json.dumps(call_ctx, default=str, ensure_ascii=False),
            f"Task: {prompt}",
        ]
        return "\n\n".join(parts)
    lead_clean = {k: v for k, v in lead.items() if not k.startswith("_") and k != "id"}
    return f"Lead Data:\n{json.dumps(lead_clean, default=str)}\n\nTask: {prompt}"


def worthy_call_gate(status_raw: str, transcript: str) -> Tuple[bool, List[str]]:
    """
    Strict gate: skip OpenAI if transcript < 50 chars, no User: turn, or terminal miss statuses.
    """
    reasons: List[str] = []
    s = (status_raw or "").strip().lower().replace("_", "-")
    if s in ("no-answer", "busy", "failed", "call-failed"):
        reasons.append(f"status_excluded:{s}")
    t = (transcript or "").strip()
    if len(t) < 50:
        reasons.append("transcript_lt_50")
    if not re.search(
        r"(?im)^\s*(?:User|Customer|ग्राहक|यूज़र|उपयोगकर्ता)\s*:",
        t,
    ):
        reasons.append("no_user_turn")
    return (len(reasons) == 0, reasons)


def not_worthy_call_history_patch(now: Optional[datetime] = None) -> Dict[str, Any]:
    ts = now or datetime.utcnow()
    return {
        "ai_worthy": False,
        "structured_extraction": {
            "schema_version": 2,
            "call_summary": NOT_WORTHY_MESSAGE,
            "budget_match": False,
            "budget_category": "Other",
            "area_match": False,
            "location_category": "Other",
            "timeline_match": False,
            "intent_category": "Other",
            "disposition": "",
            "lead_name": "Unknown",
            "phone": "",
            "system_tag_correct": True,
            "key_signals": [],
        },
        "ai_disposition": "",
        "updated_at": ts,
    }


def qualification_category_from_matches(budget_match: bool, area_match: bool, timeline_match: bool) -> str:
    if (not budget_match) and (not area_match) and (not timeline_match):
        return "Dormant"
    if (not budget_match) and (area_match or timeline_match):
        return "Cold"
    if budget_match and area_match and timeline_match:
        return "Qualified"
    if budget_match and area_match and (not timeline_match):
        return "VIP Pipeline"
    if budget_match and (not area_match):
        return "Hot"
    return "Cold"


def _not_captured_to_db(value: str) -> str:
    v = (value or "").strip()
    if not v or v.lower() == "not captured":
        return "Profiling in Progress"
    return v


def _is_captured_db_value(v: str) -> bool:
    s = (v or "").strip()
    if not s:
        return False
    if s.lower() == "not captured":
        return False
    if s.lower() == "profiling in progress":
        return False
    return True


def _budget_category_from_budget_text(budget_text: str) -> str:
    t = (budget_text or "").strip().lower()
    if not t or t == "not captured":
        return "Profiling in Progress"
    t = t.replace("lakhs", "lakh").replace("lacs", "lakh").replace("lac", "lakh")
    t = t.replace("crores", "crore").replace("cr.", "cr").replace("crore", "cr")
    nums = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", t) if x not in ("", ".", "+", "-")]
    if not nums:
        return "Profiling in Progress"
    n = max(nums)
    if "lakh" in t:
        cr_value = n / 100.0
    elif "cr" in t:
        cr_value = n
    else:
        if n >= 100:
            cr_value = n / 100.0
        elif n < 10 and "." in t:
            cr_value = n
        else:
            cr_value = n / 100.0
    if cr_value < 1:
        return "<1 Cr"
    if cr_value <= 2:
        return "1-2 Cr"
    if cr_value <= 5:
        return "2-5 Cr"
    return "5 Cr+"


def _location_category_from_preference(location_text: str) -> str:
    t = (location_text or "").strip().lower()
    if not t or t == "not captured":
        return "Profiling in Progress"
    if any(x in t for x in ["thane", "majivada", "kalyan", "dombivli", "bhiwandi", "majiwada"]):
        return "Thane"
    if any(x in t for x in ["bandra", "bkc", "santacruz", "santa cruz", "khar", "juhu"]):
        return "Bandra/BKC"
    if any(
        x in t
        for x in ["colaba", "worli", "prabhadevi", "dadar", "lower parel", "fort", "nariman", "churchgate"]
    ):
        return "South Mumbai"
    if any(x in t for x in ["andheri", "malad", "kandivali", "borivali", "goregaon", "vikhroli", "powai"]):
        return "Suburbs"
    return "Other"


_VALID_BUDGET_BUCKETS = frozenset({"<1 Cr", "1-2 Cr", "2-5 Cr", "5 Cr+", "Other", "Profiling in Progress"})
_VALID_LOCATION_BUCKETS = frozenset(
    {"Thane", "Bandra/BKC", "South Mumbai", "Suburbs", "Other", "Profiling in Progress"}
)
_VALID_INTENT_BUCKETS = frozenset({"Other", "Investor", "Home Seeker", "Profiling in Progress"})


def _normalize_budget_category_ai(raw: str) -> str:
    s = (raw or "").strip()
    if s in _VALID_BUDGET_BUCKETS:
        return s
    return _budget_category_from_budget_text(raw)


def _normalize_location_category_ai(raw: str) -> str:
    s = (raw or "").strip()
    if s in _VALID_LOCATION_BUCKETS:
        return s
    return _location_category_from_preference(raw)


def _normalize_intent_category_ai(raw: str) -> str:
    s = (raw or "").strip()
    if s in _VALID_INTENT_BUCKETS:
        return s
    return get_intent_category(raw)


def _budget_band_mid_cr(bc: str) -> str:
    """Representative Cr value for DNA display when only the bucket is known."""
    m = {
        "<1 Cr": "0.5",
        "1-2 Cr": "1.5",
        "2-5 Cr": "3.5",
        "5 Cr+": "6",
    }
    return m.get((bc or "").strip(), "")


class StructuredAIService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    def _build_unified_messages(
        self,
        *,
        customer_name: str,
        phone_number: str,
        system_disposition: str,
        recording_url: str,
        transcript: str,
    ) -> List[Dict[str, str]]:
        system_prompt = (
            "You are an expert real estate analyst for Rustomjee Developers (Mumbai / Thane markets). "
            "Analyze the call transcript and output STRICT JSON only with exactly these keys:\n"
            "- budget_match (boolean): true if stated budget aligns with a typical Rustomjee purchase (crore-scale).\n"
            "- budget_category (string): one of: <1 Cr | 1-2 Cr | 2-5 Cr | 5 Cr+ | Other | Profiling in Progress\n"
            "- area_match (boolean): true if preferred area matches Rustomjee focus (Mumbai/Thane/nearby).\n"
            "- location_category (string): one of: Thane | Bandra/BKC | South Mumbai | Suburbs | Other | Profiling in Progress\n"
            "- timeline_match (boolean): true if realistic purchase timeline within ~12 months or clear near-term intent.\n"
            "- intent_category (string): one of: Other | Investor | Home Seeker | Profiling in Progress\n"
            "- disposition (string): exactly one of: Hot Lead | Semi-Interested | Mildly interested | "
            "Not Interested | Voicemail | Wrong Number | Already Bought\n"
            "- call_summary (string): 3-5 concise actionable sentences.\n"
            "- preferred_location (string): neighborhood or area the customer stated, else empty string.\n"
            "- unit_configuration (string): BHK / unit type (e.g. 2 BHK) if stated, else empty string.\n"
            "Also include schema_version: 2, lead_name, phone (masked like ******1234), system_tag_correct (boolean), "
            "key_signals (array of short strings).\n"
            "If information is missing, use false and Profiling in Progress / Other as appropriate. "
            "Never invent a conversation; if transcript is unclear, lower confidence via key_signals."
        )
        user_obj = {
            "customer_name": customer_name or "Unknown",
            "system_disposition": system_disposition or "",
            "recording_url": recording_url or "",
            "transcript": transcript or "",
        }
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_obj, ensure_ascii=False)},
        ]

    async def extract_unified(
        self,
        *,
        customer_name: str,
        phone_number: str,
        system_disposition: str,
        recording_url: str,
        transcript: str,
    ) -> UnifiedStructuredExtraction:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        client = get_openai_client()
        if not client:
            raise RuntimeError("OpenAI client unavailable")

        messages = self._build_unified_messages(
            customer_name=customer_name,
            phone_number=phone_number,
            system_disposition=system_disposition,
            recording_url=recording_url,
            transcript=transcript,
        )
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.2,
            max_tokens=900,
            response_format={"type": "json_object"},
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("schema_version", 2)
        data["phone"] = mask_phone(phone_number)
        data["lead_name"] = (data.get("lead_name") or customer_name or "Unknown").strip() or "Unknown"
        return UnifiedStructuredExtraction.model_validate(data)

    def to_db_call_history_patch_unified(self, extraction: UnifiedStructuredExtraction) -> Dict[str, Any]:
        payload = extraction.model_dump()
        return {
            "structured_extraction": payload,
            "ai_disposition": extraction.disposition or "",
            "ai_worthy": True,
            "updated_at": datetime.utcnow(),
        }

    def to_db_lead_patch_unified(self, extraction: UnifiedStructuredExtraction) -> Dict[str, Any]:
        bc = _normalize_budget_category_ai(extraction.budget_category)
        lc = _normalize_location_category_ai(extraction.location_category)
        ic = _normalize_intent_category_ai(extraction.intent_category)
        qc = qualification_category_from_matches(
            bool(extraction.budget_match),
            bool(extraction.area_match),
            bool(extraction.timeline_match),
        )
        dispo = (extraction.disposition or "").strip()

        patch: Dict[str, Any] = {
            "ai_disposition": dispo,
            "ai_summary": extraction.call_summary or "",
            "budget_match": bool(extraction.budget_match),
            "area_match": bool(extraction.area_match),
            "timeline_match": bool(extraction.timeline_match),
            "qualification_category": qc,
            "budget_category": bc,
            "location_category": lc,
            "intent_category": ic,
            "ai_key_signals": extraction.key_signals or [],
            "system_tag_correct": bool(extraction.system_tag_correct),
            "updated_at": datetime.utcnow(),
        }
        if dispo:
            patch["disposition"] = dispo

        pl = (extraction.preferred_location or "").strip()
        uc = (extraction.unit_configuration or "").strip()
        if pl:
            patch["location"] = pl
            patch["current_residence_location"] = pl
            patch["current_residential_location"] = pl
        elif lc and lc not in ("Other", "Profiling in Progress"):
            patch["location"] = lc
            patch["current_residence_location"] = lc
            patch["current_residential_location"] = lc
        if uc:
            patch["configuration"] = uc
            patch["bhk"] = uc

        mid_cr = _budget_band_mid_cr(bc)
        if mid_cr:
            patch["budget"] = mid_cr

        return patch

    @staticmethod
    def campaign_bucket_from_ai_disposition(d: StructuredDisposition) -> Optional[str]:
        if d == StructuredDisposition.hot_lead:
            return "interested"
        if d == StructuredDisposition.semi_interested:
            return "semiInterested"
        if d == StructuredDisposition.mildly_interested:
            return "callback"
        if d in (
            StructuredDisposition.not_interested,
            StructuredDisposition.voicemail,
            StructuredDisposition.wrong_number,
            StructuredDisposition.already_bought,
        ):
            return "notInterested"
        return None

    @staticmethod
    def campaign_bucket_from_ai_disposition_value(value: Any) -> Optional[str]:
        if isinstance(value, StructuredDisposition):
            return StructuredAIService.campaign_bucket_from_ai_disposition(value)
        s = (str(value or "")).strip()
        if not s:
            return None
        for d in StructuredDisposition:
            if d.value.lower() == s.lower():
                return StructuredAIService.campaign_bucket_from_ai_disposition(d)
        return None

    @staticmethod
    def should_exclude(d: StructuredDisposition) -> bool:
        return d in (
            StructuredDisposition.not_interested,
            StructuredDisposition.voicemail,
            StructuredDisposition.wrong_number,
        )

    async def _latest_worthy_call_doc_for_lead(self, lead: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Most recent call_history row for this lead that passes worthy_call_gate (same bar as summaries)."""
        mobile_digits = (lead.get("mobile_digits") or "").strip()
        if not mobile_digits:
            return None
        docs = (
            await self.db.call_history.find({"mobile_digits": mobile_digits})
            .sort("created_at", -1)
            .to_list(40)
        )
        for d in docs:
            tr = (d.get("transcript") or "").strip()
            st = str(d.get("futwork_status") or d.get("status") or "")
            ok, _ = worthy_call_gate(st, tr)
            if ok:
                return d
        return None

    async def get_insight(
        self,
        lead_id: str,
        field: str,
        prompt: str,
        refresh: bool = False,
        *,
        worthy_call: Optional[Dict[str, Any]] = None,
    ) -> str:
        lead = await self.db.leads.find_one({"id": lead_id})
        if not lead:
            raise ValueError("Lead not found")
        if not refresh and lead.get(field):
            return lead[field]
        if not settings.OPENAI_API_KEY:
            return "AI insights require an OpenAI API key. Please configure OPENAI_API_KEY in the backend .env file."
        client = get_openai_client()
        if not client:
            return "AI insights require an OpenAI API key. Please configure OPENAI_API_KEY in the backend .env file."
        user_content = _build_insight_user_content(lead, prompt, worthy_call=worthy_call)
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior real estate sales strategist for Rustomjee properties, "
                            "one of Mumbai's most prestigious real estate developers since 1996. "
                            "You produce concise, actionable, and data-driven insights."
                        ),
                    },
                    {
                        "role": "user",
                        "content": user_content,
                    },
                ],
                temperature=0.7,
                max_tokens=400,
            )
            insight = (response.choices[0].message.content or "").strip()
            await self.db.leads.update_one({"id": lead_id}, {"$set": {field: insight}})
            return insight
        except Exception as e:
            logger.error("Error calling OpenAI for lead %s: %s", lead_id, e)
            return f"Unable to generate AI insight at this time. Error: {str(e)}"

    async def generate_persona(self, lead_id: str, refresh: bool = False) -> str:
        lead = await self.db.leads.find_one({"id": lead_id})
        if not lead:
            raise ValueError("Lead not found")

        worthy_call = await self._latest_worthy_call_doc_for_lead(lead)
        if not worthy_call:
            await self.db.leads.update_one({"id": lead_id}, {"$set": {"aiPersonaSummary": PERSONA_INSUFFICIENT}})
            return PERSONA_INSUFFICIENT

        had_insufficient = (lead.get("aiPersonaSummary") or "").strip() == PERSONA_INSUFFICIENT
        eff_refresh = refresh or had_insufficient

        prompt = (
            "Generate a 1-2 sentence Buyer Profile. Your primary source is "
            "Latest worthy call → transcript; CRM fields are supplementary only. "
            "Stick STRICTLY to facts from the transcript. "
            "Do NOT infer lifestyle or psychological motivations if they aren't explicitly mentioned. "
            "If the transcript is brief (e.g., just greetings), return exactly: "
            "\"Insufficient interaction to determine buyer persona.\" "
            "Use markdown bold (**text**) only for short labels drawn from explicit transcript facts."
        )
        return await self.get_insight(
            lead_id,
            "aiPersonaSummary",
            prompt,
            refresh=eff_refresh,
            worthy_call=worthy_call,
        )

    async def generate_strategic_move(self, lead_id: str, refresh: bool = False) -> str:
        lead = await self.db.leads.find_one({"id": lead_id})
        if not lead:
            raise ValueError("Lead not found")

        worthy_call = await self._latest_worthy_call_doc_for_lead(lead)
        if not worthy_call:
            await self.db.leads.update_one({"id": lead_id}, {"$set": {"strategicNextMove": STRATEGIC_INSUFFICIENT}})
            return STRATEGIC_INSUFFICIENT

        had_insufficient = (lead.get("strategicNextMove") or "").strip() == STRATEGIC_INSUFFICIENT
        eff_refresh = refresh or had_insufficient

        prompt = (
            "Suggest the single best strategic next move for the Rustomjee sales team to convert this lead. "
            "Base your recommendation primarily on the call transcript and structured_extraction signals; "
            "use CRM temperature, budget, and project interest only when they add concrete detail. "
            "Be specific and immediately actionable (e.g., 'Schedule a site visit to Urban Woods this weekend, "
            "emphasize the 2BHK corner unit under 2 Cr which fits their budget exactly.'). "
            "Use markdown bold (**text**) to highlight the key action."
        )
        return await self.get_insight(
            lead_id,
            "strategicNextMove",
            prompt,
            refresh=eff_refresh,
            worthy_call=worthy_call,
        )

    async def generate_call_summary_unified(
        self,
        lead_id: str,
        *,
        call_sid: Optional[str] = None,
        refresh: bool = False,
    ) -> str:
        lead = await self.db.leads.find_one({"id": lead_id})
        if not lead:
            raise ValueError("Lead not found")
        mobile_digits = (lead.get("mobile_digits") or "").strip()
        customer_name = (lead.get("full_name") or "Unknown").strip() or "Unknown"
        phone = (lead.get("mobile") or "").strip() or mobile_digits

        if call_sid:
            flt: Dict[str, Any] = {"id": call_sid}
            if mobile_digits:
                flt["mobile_digits"] = mobile_digits
            doc = await self.db.call_history.find_one(flt)
        else:
            doc = await self._latest_worthy_call_doc_for_lead(lead)
        if not doc:
            return NOT_WORTHY_MESSAGE

        cid = doc.get("id") or doc.get("call_sid")
        transcript = (doc.get("transcript") or "").strip()
        status_raw = str(doc.get("futwork_status") or doc.get("status") or "")
        worthy, _ = worthy_call_gate(status_raw, transcript)

        if not worthy:
            se = doc.get("structured_extraction") or {}
            if doc.get("ai_worthy") is False and se.get("call_summary") == NOT_WORTHY_MESSAGE:
                return NOT_WORTHY_MESSAGE
            if cid:
                await self.db.call_history.update_one(
                    {"id": cid},
                    {"$set": not_worthy_call_history_patch()},
                )
            return NOT_WORTHY_MESSAGE

        if not refresh:
            se = doc.get("structured_extraction") or {}
            if (
                doc.get("ai_worthy") is True
                and isinstance(se, dict)
                and int(se.get("schema_version") or 0) == 2
                and (se.get("call_summary") or "").strip()
            ):
                return str(se.get("call_summary")).strip()

        unified = await self.extract_unified(
            customer_name=customer_name,
            phone_number=phone,
            system_disposition=str(doc.get("disposition") or ""),
            recording_url=str(doc.get("recording_url") or ""),
            transcript=transcript,
        )
        ch_patch = self.to_db_call_history_patch_unified(unified)
        if cid:
            await self.db.call_history.update_one({"id": cid}, {"$set": ch_patch})
        lp = self.to_db_lead_patch_unified(unified)
        lp["lastCallSummary"] = unified.call_summary
        if cid:
            lp["last_structured_call_sid"] = str(cid)
        await self.db.leads.update_one({"id": lead_id}, {"$set": lp})
        return unified.call_summary

    @staticmethod
    def build_batch_summary(extractions: List[StructuredCallExtraction]) -> BatchSummaryObject:
        summary = BatchSummaryPayload()
        summary.total_calls = len(extractions)

        incorrect = 0
        hot = semi = mild = not_i = vw = bought = 0
        priority: List[Tuple[int, str]] = []
        issues: List[str] = []

        for e in extractions:
            if not e.system_tag_correct:
                incorrect += 1
            if e.disposition == StructuredDisposition.hot_lead:
                hot += 1
                priority.append((3, f"{e.lead_name} ({e.phone})"))
            elif e.disposition == StructuredDisposition.semi_interested:
                semi += 1
                priority.append((2, f"{e.lead_name} ({e.phone})"))
            elif e.disposition == StructuredDisposition.mildly_interested:
                mild += 1
                priority.append((1, f"{e.lead_name} ({e.phone})"))
            elif e.disposition == StructuredDisposition.not_interested:
                not_i += 1
            elif e.disposition in (StructuredDisposition.voicemail, StructuredDisposition.wrong_number):
                vw += 1
            elif e.disposition == StructuredDisposition.already_bought:
                bought += 1

            for s in e.key_signals or []:
                if "called multiple times" in s.lower() or "too many calls" in s.lower() or "bar bar" in s.lower():
                    issues.append("Leads complaining about over-calling; reduce retries and use human callback.")
                    break

        summary.hot_leads = hot
        summary.semi_interested = semi
        summary.mildly_interested = mild
        summary.not_interested = not_i
        summary.voicemail_wrong_number = vw
        summary.already_bought = bought
        summary.system_tags_incorrect = incorrect

        priority_sorted = sorted(priority, key=lambda x: x[0], reverse=True)
        summary.top_priority_leads = [p[1] for p in priority_sorted[:3]]

        summary.crm_issues_detected = list(dict.fromkeys(issues))
        return BatchSummaryObject(batch_summary=summary)

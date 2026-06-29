import re
import hashlib
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

from .lead_tag_sync import reconcile_temperature_with_status

# Column mappings from CSV headers to internal DB field names
COLUMN_MAPPINGS = {
    # ---- Standard Rustomjee CRM columns ----
    'Full Name': 'full_name',
    'Mobile': 'mobile',
    'Email': 'email',
    'Project': 'project',
    'Location': 'location',
    'Lead Source': 'source',
    'Lead Status': 'status',
    'Temperature': 'temperature',
    'Budget': 'budget',
    'Intent': 'intent',
    'Disposition': 'disposition',
    'Configuration': 'configuration',
    'Current Residence Type': 'current_residence_type',
    'Current Residence Location': 'current_residence_location',
    'Current Residential Location': 'current_residence_location',
    'Last Interaction': 'last_interaction',
    'Designation': 'designation',
    'Ethnicity': 'ethnicity',
    'Carpet Area': 'carpet_area',
    'Possession Requirement': 'possession_requirement',
    'Reason for Purchase': 'reason_for_purchase',
    'Presales Description': 'presales_description',
    'Context Summary': 'context_summary',
    'Suggested Next Project': 'suggested_next_project',
    'Next Action Date': 'next_action_date',
    'First Name': 'first_name',
    'Last Name': 'last_name',
    # ---- Futwork CSV columns (recipientPhoneNumber, customer_name) ----
    'recipientPhoneNumber': 'mobile',
    'customer_name': 'full_name',
    # ---- Optional external correlation key from upload template ----
    'unique_identifier': 'external_id',
    'Unique Identifier': 'external_id',
    # ---- Upload template (Lead ID, Name, Mobile) ----
    'Lead ID': 'client_lead_id',
    'Lead Id': 'client_lead_id',
    'Name': 'full_name',
    'name': 'full_name',
}

def normalize_phone(phone: str) -> str:
    """
    Normalize to 10-digit Indian mobile for storage and lookup.

    Handles +91 / 91 prefix and trunk 0 before 10-digit local numbers.
    """
    digits = re.sub(r"\D", "", str(phone or ""))
    if not digits:
        return ""
    if len(digits) >= 12 and digits.startswith("91"):
        return digits[-10:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def _ten_digit_alt_with_leading_nine(ten_digits: str) -> str:
    """8696979791 -> 9869697979 (replace leading 6/7/8 with 9, keep 10 digits)."""
    if len(ten_digits) != 10 or ten_digits[0] not in "678":
        return ""
    return "9" + ten_digits[1:]


def phone_lookup_candidates(phone: str) -> list[str]:
    """
    Distinct 10-digit keys to match leads when Futwork/CRM formats differ.

    Example: Futwork 08696979791 -> 8696979791 and 9869697979 (leading-9 variant).
    """
    raw = re.sub(r"\D", "", str(phone or ""))
    primary = normalize_phone(phone)
    if not primary and not raw:
        return []

    out: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        v = (value or "").strip()
        if len(v) == 10 and v.isdigit() and v not in seen:
            seen.add(v)
            out.append(v)

    add(primary)
    alt = _ten_digit_alt_with_leading_nine(primary)
    if alt:
        add(alt)

    if len(raw) == 11 and raw.startswith("0"):
        body = raw[1:]
        if body != primary:
            add(body)
            alt_body = _ten_digit_alt_with_leading_nine(body)
            if alt_body:
                add(alt_body)

    return out

def get_budget_category(budget_str: str) -> str:
    budget_str = str(budget_str).lower().strip()
    if not budget_str or budget_str in ('', 'nan', 'none', 'profiling in progress'):
        return "Other"
    if 'cr' in budget_str or 'crore' in budget_str:
        try:
            val = float(re.findall(r"[-+]?\d*\.?\d+", budget_str)[0])
            if val < 1: return "<1 Cr"
            if val <= 2: return "1-2 Cr"
            if val <= 5: return "2-5 Cr"
            return "5 Cr+"
        except (IndexError, ValueError):
            pass
    # Try to parse plain numbers (treat as Crores)
    try:
        val = float(re.findall(r"[-+]?\d*\.?\d+", budget_str)[0])
        if val < 1: return "<1 Cr"
        if val <= 2: return "1-2 Cr"
        if val <= 5: return "2-5 Cr"
        if val > 5: return "5 Cr+"
    except (IndexError, ValueError):
        pass
    return "Other"

def get_location_category(location: str) -> str:
    if not location:
        return "Other"
    loc = str(location).lower()
    if any(x in loc for x in ['thane', 'majivada', 'kalyan', 'dombivli', 'bhiwandi']): return "Thane"
    if any(x in loc for x in ['bandra', 'bkc', 'santacruz', 'khar', 'juhu']): return "Bandra/BKC"
    if any(x in loc for x in ['colaba', 'worli', 'prabhadevi', 'dadar', 'lower parel', 'fort', 'nariman']): return "South Mumbai"
    if any(x in loc for x in ['andheri', 'malad', 'kandivali', 'borivali', 'goregaon', 'vikhroli', 'powai']): return "Suburbs"
    return "Other"

def get_intent_category(intent: str) -> str:
    if not intent:
        return "Other"
    intent_lower = str(intent).lower()
    if any(x in intent_lower for x in ['invest', 'rental', 'roi', 'return']): return "Investor"
    if any(x in intent_lower for x in ['home', 'self', 'family', 'live', 'reside', 'end use']): return "Home Seeker"
    return "Other"

def normalize_agent_name(name: str) -> str:
    """Lowercase, collapse whitespace for agent name lookup keys."""
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def slugify_agent_email(full_name: str, domain: str = "rustomjee.com") -> str:
    """Build placeholder email from presales agent display name."""
    parts = re.sub(r"[^a-z0-9\s]", "", str(full_name or "").lower()).split()
    local = ".".join(parts) if parts else "agent"
    return f"{local}@{domain}"


def build_phone_key(country_code: str, mobile_digits: str) -> str:
    cc = re.sub(r"\D", "", str(country_code or ""))
    md = str(mobile_digits or "").strip()
    if cc and md:
        return f"{cc}:{md}"
    return ""


def _clean_csv_cell(val: Any) -> str:
    s = str(val or "").strip()
    if s in ("-", "nan", "None", "NaN", ""):
        return ""
    return s


def _cell(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key not in row:
            continue
        val = _clean_csv_cell(row.get(key))
        if val:
            return val
    return ""


def process_lead_upload_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flexible CSV upload: Name + Mobile (required), optional Lead ID, or full presales dump.
    Raheja identity is mobile_digits; client_lead_id is optional legacy correlation.
    """
    r = row or {}
    if _cell(r, "Presales Agent") or _cell(r, "Presales Last Call Attempt Status"):
        return process_presales_dump_row(r)

    raw_mobile = _cell(
        r,
        "Mobile Number",
        "Mobile",
        "Mobile 1",
        "recipientPhoneNumber",
    )
    mobile_digits = normalize_phone(raw_mobile)
    if len(mobile_digits) != 10:
        return {}

    client_lead_id = _cell(
        r,
        "Lead ID",
        "Lead Id",
        "lead_id",
        "client_lead_id",
    )
    name = _cell(r, "Name", "Full Name", "Last Name", "customer_name")

    lead: Dict[str, Any] = {
        "mobile": raw_mobile or mobile_digits,
        "mobile_digits": mobile_digits,
        "project": _cell(r, "Project"),
        "updated_at": datetime.utcnow(),
    }
    if client_lead_id:
        lead["client_lead_id"] = client_lead_id
        lead["external_id"] = client_lead_id
    if name:
        lead["full_name"] = name
        if _cell(r, "Last Name") or r.get("Last Name") is not None:
            lead["last_name"] = name
    return lead


def process_presales_dump_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map Rustomjee presales lead dump CSV row to lead document fields.

  Headers: Lead Id, Presales Agent, Last Name, Dialing Country 1,
            Country Code 1, Mobile 1, Project, Presales Last Call Attempt Status
    """
    r = row or {}
    client_lead_id = _clean_csv_cell(r.get("Lead Id"))
    country = _clean_csv_cell(r.get("Dialing Country 1"))
    country_code = re.sub(r"\D", "", _clean_csv_cell(r.get("Country Code 1")))
    raw_mobile = _clean_csv_cell(r.get("Mobile 1"))
    mobile_digits = normalize_phone(raw_mobile)
    phone_key = build_phone_key(country_code, mobile_digits)

    last_name = _clean_csv_cell(r.get("Last Name"))
    project = _clean_csv_cell(r.get("Project"))
    presales_status = _clean_csv_cell(r.get("Presales Last Call Attempt Status"))
    agent_name = _clean_csv_cell(r.get("Presales Agent"))

    mobile = raw_mobile
    if country_code and mobile_digits and not raw_mobile.startswith("+"):
        mobile = f"+{country_code}{mobile_digits}"

    lead: Dict[str, Any] = {
        "client_lead_id": client_lead_id,
        "external_id": client_lead_id,
        "country": country,
        "country_code": country_code,
        "mobile": mobile,
        "mobile_digits": mobile_digits,
        "phone_key": phone_key,
        "project": project,
        "last_name": last_name,
        "presales_agent_name": agent_name,
        "presales_status": presales_status,
        "updated_at": datetime.utcnow(),
    }

    if last_name:
        lead["full_name"] = last_name

    return lead


def generate_seed_key(row: Dict[str, Any]) -> str:
    """Generate a deterministic key for a CSV row to prevent duplicates."""
    name   = row.get('Full Name') or row.get('customer_name', '')
    mobile = row.get('Mobile') or row.get('recipientPhoneNumber', '')
    project = row.get('Project', '')
    key_str = f"{name}{mobile}{project}"
    return hashlib.sha256(key_str.encode()).hexdigest()

def process_row_to_lead(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map a CSV row to the Lead internal schema."""
    lead = {}
    cid = _cell(row, "Lead ID", "Lead Id", "lead_id", "client_lead_id")
    if cid:
        lead["client_lead_id"] = cid
        lead["external_id"] = cid
    name = _cell(row, "Name", "Full Name", "customer_name")
    if name:
        lead["full_name"] = name

    _skip_fields = frozenset({"client_lead_id", "external_id", "full_name"})

    for csv_col, model_field in COLUMN_MAPPINGS.items():
        if model_field in _skip_fields:
            continue
        # Specifically handle the two possible column names for residence location
        if model_field == 'current_residence_location':
            val = row.get('Current Residence Location') or row.get('Current Residential Location', "")
        else:
            val = row.get(csv_col, "")
        
        # Treat placeholder values as empty
        if str(val).strip() in ("Profiling in Progress", "nan", "None", "NaN"):
            val = ""
        lead[model_field] = str(val).strip() if val else ""

    # Build full_name from first/last if not present
    if not lead.get('full_name') and (lead.get('first_name') or lead.get('last_name')):
        lead['full_name'] = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()

    # Enrich and Normalize
    lead['mobile_digits'] = normalize_phone(lead.get('mobile', ''))
    lead['budget_category'] = get_budget_category(lead.get('budget', ''))
    lead['location_category'] = get_location_category(lead.get('location', '') or lead.get('current_residence_location', ''))
    lead['intent_category'] = get_intent_category(lead.get('intent', '') or lead.get('reason_for_purchase', ''))

    # Always set current_residential_location as alias (frontend reads this variant)
    lead['current_residential_location'] = lead.get('current_residence_location', '')

    # Optional baseline preservation (baseline = CSV upload)
    # These are useful to compare against AI-refined fields later.
    # Keep them lightweight and only set when present.
    if lead.get("budget"):
        lead["baseline_budget"] = lead.get("budget", "")
    if lead.get("location"):
        lead["baseline_location"] = lead.get("location", "")
    if lead.get("configuration"):
        lead["baseline_configuration"] = lead.get("configuration", "")
    if lead.get("source"):
        lead["baseline_source"] = lead.get("source", "")
    lead["baseline_uploaded_at"] = datetime.utcnow()

    # Derived flags
    lead['is_hni'] = lead.get('budget_category') == '5 Cr+'

    # Metadata
    lead['updated_at'] = datetime.utcnow()

    # Guarantee: these fields must always exist and never be None in the DB.
    # This protects against CSV uploads that are missing source columns
    # (e.g. Futwork call reports that lack Budget / Location / Intent columns).
    for field in (
        'budget_category', 'location_category', 'intent_category',
        'vip_category', 'project', 'temperature', 'status', 'disposition',
    ):
        if lead.get(field) is None:
            lead[field] = ""

    if lead.get("client_lead_id") and not lead.get("external_id"):
        lead["external_id"] = lead["client_lead_id"]

    return reconcile_temperature_with_status(lead)


def _parse_iso_datetime(raw: Any) -> Optional[datetime]:
    """
    Parse Futwork ISO strings like '2026-05-08T20:25:23.674Z' into datetime.
    Returns None on invalid input.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        # Handle trailing 'Z'
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def process_call_report_row_to_call_history_and_lead_patches(
    row: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """
    Curated mapping for Futwork unmasked call report CSV rows.

    Returns:
      (call_history_set_fields, lead_set_fields, call_sid)

    Rule: only include customer-useful fields; do not persist internal/system columns
    unless they are required to correlate and analyze calls.
    """
    r = row or {}
    call_sid = str(r.get("callSid") or "").strip()

    # Prefer unmasked mobile for matching; fall back to other phone columns.
    raw_phone = (
        r.get("Unmasked_Mobile_Number")
        or r.get("contextDetails_recipientPhoneNumber")
        or r.get("telephonyData_toNumber")
        or ""
    )
    raw_phone = str(raw_phone).strip()
    mobile_digits = normalize_phone(raw_phone)

    duration_seconds = 0
    try:
        duration_seconds = int(float(str(r.get("duration") or 0).strip() or 0))
    except Exception:
        duration_seconds = 0

    status_raw = str(r.get("status") or "").strip()
    disposition = str(r.get("disposition") or "").strip()
    transcript = str(r.get("transcript") or "").strip()
    recording_url = str(r.get("recordingUrl") or "").strip()

    created_at = _parse_iso_datetime(r.get("createdAt"))
    updated_at = _parse_iso_datetime(r.get("updatedAt"))
    lead_uploaded_on = _parse_iso_datetime(r.get("leadUploadedOn"))

    # ---- call_history (call-level truth) -----------------------------------
    call_history_set: Dict[str, Any] = {
        "id": call_sid,
        "call_sid": call_sid,
        "mobile_digits": mobile_digits,
        "phone": raw_phone,
        "updated_at": datetime.utcnow(),
    }

    # Value-bearing fields only (so blank CSV doesn't wipe good data).
    if status_raw:
        call_history_set["futwork_status"] = status_raw
        call_history_set["status"] = status_raw
    if disposition:
        call_history_set["disposition"] = disposition
    if duration_seconds:
        call_history_set["duration"] = duration_seconds
    if recording_url:
        call_history_set["recording_url"] = recording_url
    if transcript:
        call_history_set["transcript"] = transcript

    # Timing: preserve vendor timestamps when present.
    if created_at:
        call_history_set["created_at"] = created_at
    if updated_at:
        call_history_set["provider_updated_at"] = updated_at
    if lead_uploaded_on:
        call_history_set["lead_uploaded_on"] = lead_uploaded_on

    # Correlation keys (useful for joining webhook ↔ lead ↔ campaign)
    for src, dst in (
        ("agentId", "agent_id"),
        ("contextDetails_recipientData_campaignId", "campaign_id"),
        ("contextDetails_recipientData_leadId", "lead_id"),
        ("contextDetails_recipientData_unique_identifier", "external_id"),
        ("telephonyData_provider", "provider"),
        ("telephonyData_providerCallId", "provider_call_id"),
        ("telephonyData_direction", "direction"),
        ("telephonyData_fromNumber", "from_number"),
        ("telephonyData_toNumber", "to_number"),
        ("telephonyData_hangupBy", "hangup_by"),
        ("telephonyData_hangupReason", "hangup_reason"),
        ("dropoff", "dropoff"),
    ):
        val = r.get(src)
        if val is None:
            continue
        sval = str(val).strip()
        if sval:
            call_history_set[dst] = sval

    # Optional system extraction fields from Futwork report (raw, not AI truth)
    extracted_call_summary = str(r.get("extractedData_call_summary") or "").strip()
    extracted_disposition = str(r.get("extractedData_disposition") or "").strip()
    extracted_callback_dt = str(r.get("extractedData_callback_date_time") or "").strip()
    extracted_data: Dict[str, Any] = {}
    if extracted_call_summary:
        extracted_data["call_summary"] = extracted_call_summary
    if extracted_disposition:
        extracted_data["disposition"] = extracted_disposition
    if extracted_callback_dt:
        extracted_data["callback_date_time"] = extracted_callback_dt
    if extracted_data:
        call_history_set["extracted_data"] = extracted_data

    # ---- leads (snapshot fields only) --------------------------------------
    lead_set: Dict[str, Any] = {
        "mobile_digits": mobile_digits,
        "mobile": raw_phone,
        "updated_at": datetime.utcnow(),
    }
    if created_at:
        lead_set["last_call_date"] = created_at
    if status_raw:
        lead_set["last_call_status_raw"] = status_raw
        lead_set["last_call_status"] = status_raw
    if duration_seconds:
        lead_set["last_call_duration"] = duration_seconds
    if recording_url:
        lead_set["last_recording_url"] = recording_url
    if disposition:
        lead_set["disposition"] = disposition
    if transcript:
        lead_set["transcript"] = transcript

    # Preserve correlation ids on the lead doc (useful for matching webhooks)
    lead_id = str(r.get("contextDetails_recipientData_leadId") or "").strip()
    if lead_id:
        lead_set["futwork_lead_id"] = lead_id
    external_id = str(r.get("contextDetails_recipientData_unique_identifier") or "").strip()
    if external_id:
        lead_set["external_id"] = external_id
        lead_set["client_lead_id"] = external_id
    campaign_id = str(r.get("contextDetails_recipientData_campaignId") or "").strip()
    if campaign_id:
        lead_set["campaign_id"] = campaign_id
    customer_name = str(r.get("contextDetails_recipientData_customer_name") or "").strip()
    if customer_name and customer_name != "-":
        lead_set["full_name"] = customer_name

    return call_history_set, lead_set, call_sid

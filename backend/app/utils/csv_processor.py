import re
import hashlib
from datetime import datetime
from typing import Dict, Any

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
}

def normalize_phone(phone: str) -> str:
    """Normalize phone number to digits only and extract last 10 digits."""
    digits = re.sub(r'\D', '', str(phone))
    return digits[-10:] if len(digits) >= 10 else digits

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

    for csv_col, model_field in COLUMN_MAPPINGS.items():
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

    # Derived flags
    lead['is_vip'] = (
        lead.get('temperature') == 'Hot' or
        lead.get('budget_category') in ('5 Cr+', '2-5 Cr')
    )
    lead['is_hni'] = lead.get('budget_category') == '5 Cr+'

    # vip_category — used by frontend for crown icon rendering
    lead['vip_category'] = "VIP/HNI" if lead['is_vip'] else ""

    # Metadata
    lead['updated_at'] = datetime.utcnow()

    return lead

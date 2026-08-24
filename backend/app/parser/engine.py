# backend/app/parser/engine.py
import os
import json
import re
from google import genai
from google.genai import types
from dotenv import load_dotenv

# ==========================================
# LAYER 1: FAST LOCAL DETERMINISTIC PARSING (FREE)
# ==========================================
def extract_amount(text):
    patterns = [
        r'(?:Rs\.?|INR|₹)\s*([\d,]+\.?\d*)',
        r'debited by\s*([\d,]+\.?\d*)',
        r'credited by\s*([\d,]+\.?\d*)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(',', ''))
    return None

def extract_type(text):
    text_lower = text.lower()
    
    # Smarter detection for card expenses and standard UPI outflows
    if any(word in text_lower for word in ["debited", "spent", "paid", "debit", "txn of", "txn on card"]):
        return "DEBIT"
    elif any(word in text_lower for word in ["credited", "received", "credit", "refund"]):
        return "CREDIT"
    
    return "DEBIT"

def extract_bank(text):
    text_upper = text.upper()
    for bank in ["HDFC", "SBI", "ICICI", "AXIS", "KOTAK", "PNB", "BOB"]:
        if bank in text_upper:
            return bank
    return "UPI / BANK"

# backend/app/parser/engine.py

def extract_merchant(text):
    patterns = [
        # Added 'for' right into the capture pipeline group
        r'(?:trf to|spent at|paid to|vpa|at|for)\s+([A-Za-z0-9\s\*&\-_.]+?)(?:\s+was|\s+ref|\s+on|\s+date|\.|$)',
        r'transfer to\s+([A-Za-z0-9\s\*&\-_.]+?)(?:\s+ref|\s+on|\s+date|\.|$)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match and match.group(1):
            raw_merchant = match.group(1).split("Ref")[0].split("on")[0].strip()
            
            # Clean star patterns common in UPI logs
            if '*' in raw_merchant:
                parts = [p for p in raw_merchant.split('*') if p.upper() not in ["MKSH", "TP", "PAYMENT"]]
                raw_merchant = " ".join(parts)
            
            # Clean up long corporate suffixes like "Entertainment India"
            raw_merchant = re.sub(r'\s+(?:Entertainment|India|Private|Limited|Ltd|Pvt)\b', '', raw_merchant, flags=re.IGNORECASE)
            
            # Remove messy terminal city suffix blocks
            raw_merchant = re.sub(r'-(?:BOM|MUMBAI|BLR|BANGALORE|DEL|DELHI|CHG|HYD|MAS)(?:\b|$)', '', raw_merchant, flags=re.IGNORECASE)
            
            clean_name = re.sub(r'\s+', ' ', raw_merchant).strip()
            return clean_name.title()
            
    return "Unknown Merchant"

def detect_category(merchant):
    if not merchant or merchant == "UNKNOWN":
        return "Other"
    merchant_lower = merchant.lower()
    if any(w in merchant_lower for w in ["zomato", "swiggy", "cafe", "restaurant", "food", "starbucks"]):
        return "Food & Dining"
    elif any(w in merchant_lower for w in ["amazon", "flipkart", "myntra", "blinkit", "zepto"]):
        return "Shopping & Groceries"
    elif any(w in merchant_lower for w in ["uber", "ola", "rapido", "irctc", "petrol", "fuel"]):
        return "Travel & Fuel"
    elif any(w in merchant_lower for w in ["jio", "airtel", "netflix", "spotify", "bill", "electricity"]):
        return "Bills & Subscriptions"
    return "Other / Miscellaneous"

# ==========================================
# LAYER 2: INTELLIGENT REMOTE AI FALLBACK (GEMINI)
# ==========================================
def parse_via_ai_fallback(sms_text: str) -> dict:
    load_dotenv()
    API_KEY = os.getenv("GOOGLE_API_KEY")
    
    if not API_KEY:
        raise ValueError("Missing API key credentials block.")
        
    client = genai.Client(api_key=API_KEY)
    prompt = f"Extract structured data parameters from this Indian banking SMS context: {sms_text}"

    pure_json_schema = {
        "type": "OBJECT",
        "properties": {
            "amount": {"type": "NUMBER", "description": "The cash value of the transaction"},
            "merchant": {"type": "STRING", "description": "Clean merchant or person name"},
            "bank_name": {"type": "STRING", "description": "The bank origin (e.g., HDFC, SBI)"},
            "type": {"type": "STRING", "enum": ["DEBIT", "CREDIT", "UNKNOWN"]},
            "category": {"type": "STRING", "description": "Category like Food, Shopping, Bills, Other"},
            "plain_language_summary": {"type": "STRING", "description": "Short plain language sentence explaining the spend"}
        },
        "required": ["merchant", "bank_name", "type", "category", "plain_language_summary"]
    }

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=pure_json_schema,
        ),
    )
    return json.loads(response.text)

# ==========================================
# CORE INTEGRATION ROUTER PIPELINE
# ==========================================
def clearspend_parser(sms_text: str) -> dict:
    print("\n⚡ ClearSpend Routing Pipeline Triggered...")
    
    # Run local regex matching layer first
    amount = extract_amount(sms_text)
    txn_type = extract_type(sms_text)
    bank_name = extract_bank(sms_text)
    merchant = extract_merchant(sms_text)
    category = detect_category(merchant)
    
    # If regex found the core values, create a flawless plain language view instantly
    if amount and merchant != "Unknown Merchant":
        action = "spent" if txn_type == "DEBIT" else "received"
        preposition = "at" if txn_type == "DEBIT" else "from"
        summary = f"You {action} ₹{amount} {preposition} {merchant} via your {bank_name} account."
        
        return {
            "amount": amount,
            "merchant": merchant,
            "bank_name": bank_name,
            "type": txn_type,
            "category": category,
            "plain_language_summary": summary
        }
    
    # FALLBACK ENGINE ACTIVATION: Call AI if regex results are incomplete
    print("⚠️ [HYBRID ENGINE]: Local pattern fuzzy. Routing string payload to Gemini AI layer...")
    try:
        ai_data = parse_via_ai_fallback(sms_text)
        print("🚀 [HYBRID ENGINE]: Gemini AI successfully handled anomaly extraction.")
        return ai_data
    except Exception as e:
        print(f"❌ [HYBRID ENGINE]: Fallback complete fault line: {e}")
        # Universal safe database failover matrix
        return {
            "amount": amount or None,
            "merchant": merchant or "Unknown Merchant",
            "bank_name": bank_name or "UPI / BANK",
            "type": txn_type,
            "category": category or "Other",
            "plain_language_summary": "Transaction logged locally with limited structural parameters."
        }
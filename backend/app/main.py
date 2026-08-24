# backend/app/main.py
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import jwt
import re
import hashlib
import os
from datetime import datetime, timedelta

DATABASE_URL = "sqlite:///./clearspend.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Cryptography Settings
SECRET_KEY = "SUPER_SECRET_CLEARSPEND_KEY_KEEP_THIS_SAFE"
ALGORITHM = "HS256"

# ==========================================
# 1. NATIVE DATABASE SCHEMA SCHEMAS
# ==========================================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

class TransactionRecord(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    amount = Column(Float, nullable=True)
    merchant = Column(String, default="Unknown Merchant")
    bank_name = Column(String, default="UNKNOWN")
    type = Column(String, default="DEBIT")
    category = Column(String, default="Other")
    plain_language_summary = Column(String)

Base.metadata.create_all(bind=engine)

# ==========================================
# 2. PYDANTIC VALIDATION MODELS
# ==========================================
class AuthRequest(BaseModel):
    email: EmailStr
    password: str

class ParseRequest(BaseModel):
    sms: str

# FastAPI Init
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 3. SECURE NATIVE CRYPTOGRAPHY HELPER (PBKDF2)
# ==========================================
def get_password_hash(password: str) -> str:
    # Uses a fixed cryptographic salt configuration for local database storage tracking
    salt = b'clearspend_secure_local_salt_vector_hash'
    iterations = 100000
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return dk.hex()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return get_password_hash(plain_password) == hashed_password

def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(days=7) # Long-lived session persistence token
    to_encode = {"sub": str(user_id), "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_id(authorization: str = Header(default=None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header token.")
    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session parameters.")
        return int(user_id)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or corrupted.")

# Local text parser utility module logic mapping rules
def clearspend_parser(text: str):
    amount = None
    amt_match = re.search(r'(?:Rs\.|INR|₹)\s*([\d,]+\.?\d*)', text, re.IGNORECASE)
    if amt_match:
        amount = float(amt_match.group(1).replace(',', ''))
    bank = "UPI / BANK"
    if "HDFC" in text.upper(): bank = "HDFC"
    elif "SBI" in text.upper(): bank = "SBI"
    merchant = "Merchant"
    if "ZOMATO" in text.upper(): merchant = "Zomato"
    elif "ZEPTO" in text.upper(): merchant = "Zepto"
    category = "Other / Miscellaneous"
    if merchant == "Zomato": category = "Food & Dining"
    elif merchant == "Zepto": category = "Shopping & Groceries"
    return {
        "amount": amount, "merchant": merchant, "bank_name": bank, "type": "DEBIT", "category": category,
        "plain_language_summary": f"You spent ₹{amount} at {merchant} via your {bank} account." if amount else "Transaction logged."
    }

# ==========================================
# 4. SECURE AUTHENTICATION ENDPOINTS
# ==========================================
@app.post("/api/v1/auth/signup")
async def signup(payload: AuthRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="An account with this email address already exists.")
    
    new_user = User(email=payload.email, hashed_password=get_password_hash(payload.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    token = create_access_token(new_user.id)
    return {"token": token, "email": new_user.email}

@app.post("/api/v1/auth/login")
async def login(payload: AuthRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email address or password confirmation check.")
    
    token = create_access_token(user.id)
    return {"token": token, "email": user.email}

# ==========================================
# 5. PROTECTED OPERATIONAL LEDGER ENDPOINTS
# ==========================================
@app.post("/api/v1/parse")
async def process_sms_telemetry(payload: ParseRequest, current_user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    raw_input = payload.sms.strip()
    if not raw_input: raise HTTPException(status_code=400, detail="Text stream empty.")
    
    sms_lines = [line.strip() for line in raw_input.split("\n") if line.strip()]
    last_parsed_response = None
    
    for sms_line in sms_lines:
        parsed_response = clearspend_parser(sms_line)
        db_record = TransactionRecord(
            user_id=current_user_id,
            amount=parsed_response.get("amount"),
            merchant=parsed_response.get("merchant"),
            bank_name=parsed_response.get("bank_name"),
            type=parsed_response.get("type"),
            category=parsed_response.get("category"),
            plain_language_summary=parsed_response.get("plain_language_summary")
        )
        db.add(db_record)
        last_parsed_response = parsed_response
        
    db.commit()
    return last_parsed_response

@app.get("/api/v1/analytics")
async def get_financial_analytics(current_user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    total_spent = db.query(func.sum(TransactionRecord.amount)).filter(TransactionRecord.user_id == current_user_id, TransactionRecord.type == "DEBIT").scalar() or 0.0
    categories_query = db.query(TransactionRecord.category, func.sum(TransactionRecord.amount)).filter(TransactionRecord.user_id == current_user_id, TransactionRecord.type == "DEBIT").group_by(TransactionRecord.category).order_by(func.sum(TransactionRecord.amount).desc()).all()
    
    breakdown = [{"category": row[0], "amount": round(row[1], 2)} for row in categories_query]
    top_cat = breakdown[0]["category"] if breakdown else "None Yet"
    top_cat_amt = breakdown[0]["amount"] if breakdown else 0.0
    return {"total_spent": round(total_spent, 2), "top_category": top_cat, "top_category_amount": top_cat_amt, "breakdown": breakdown}

@app.get("/api/v1/history")
async def get_session_history(current_user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return db.query(TransactionRecord).filter(TransactionRecord.user_id == current_user_id).order_by(TransactionRecord.id.desc()).all()

@app.delete("/api/v1/reset")
async def reset_session_ledger(current_user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    db.query(TransactionRecord).filter(TransactionRecord.user_id == current_user_id).delete()
    db.commit()
    return {"status": "success"}
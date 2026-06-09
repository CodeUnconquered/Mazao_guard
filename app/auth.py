"""
MAZAO GUARD - Authentication Routes with Password
Login: username + password only
Registration: username + password + optional phone/email
"""

from fastapi import APIRouter, Depends, Form
from app.database import get_db, create_farmer, authenticate_farmer, get_farmer_bags
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register")
async def register_farmer(
    username: str = Form(...),
    password: str = Form(...),
    phone_number: str = Form(None),
    email: str = Form(None),
    notification_preference: str = Form("sms"),
    region: str = Form(None),
    db: Session = Depends(get_db)
):
    """
    Register a new farmer
    
    Required:
    - username (unique, at least 3 characters, letters/numbers/underscores only)
    - password (at least 6 characters)
    
    Optional:
    - phone_number (+2547... or +2541...)
    - email (valid format)
    - notification_preference (sms, email, both)
    - region
    """
    
    # Clean inputs
    username = username.strip() if username else ""
    password = password if password else ""
    
    if not username:
        return {"success": False, "message": "❌ Username is required"}
    
    if not password:
        return {"success": False, "message": "❌ Password is required"}
    
    if len(password) < 6:
        return {"success": False, "message": "❌ Password must be at least 6 characters"}
    
    # Handle empty strings as None
    phone_number = phone_number.strip() if phone_number else None
    email = email.strip().lower() if email else None
    
    if phone_number == "":
        phone_number = None
    if email == "":
        email = None
    
    farmer, error = create_farmer(
        db=db,
        username=username,
        password=password,
        phone_number=phone_number,
        email=email,
        notification_preference=notification_preference,
        region=region
    )
    
    if error:
        return {"success": False, "message": f"❌ {error}"}
    
    return {
        "success": True,
        "message": f"✅ Registration successful! Welcome {farmer.username}. You can now login.",
        "farmer": farmer.to_dict()
    }


@router.post("/login")
async def login_farmer(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Login with username and password only
    
    Required:
    - username
    - password
    """
    
    username = username.strip() if username else ""
    password = password if password else ""
    
    if not username:
        return {"success": False, "message": "❌ Username is required"}
    
    if not password:
        return {"success": False, "message": "❌ Password is required"}
    
    farmer, error = authenticate_farmer(db, username, password)
    
    if error:
        return {"success": False, "message": f"❌ {error}"}
    
    # Get farmer's bags
    bags = get_farmer_bags(db, farmer.id)
    
    return {
        "success": True,
        "message": f"✅ Welcome back, {farmer.username}!",
        "farmer": farmer.to_dict(),
        "bags": bags
    }


@router.get("/check-username/{username}")
async def check_username_availability(username: str, db: Session = Depends(get_db)):
    """Check if a username is available for registration"""
    from app.database import Farmer
    
    farmer = db.query(Farmer).filter(Farmer.username == username).first()
    
    return {
        "available": farmer is None,
        "message": "Username available" if not farmer else "Username already taken"
    }


@router.get("/farmer/{username}")
async def get_farmer_info(username: str, db: Session = Depends(get_db)):
    """Get farmer information by username"""
    from app.database import Farmer, get_farmer_bags
    
    farmer = db.query(Farmer).filter(Farmer.username == username).first()
    
    if not farmer:
        return {"success": False, "message": f"Farmer '{username}' not found"}
    
    bags = get_farmer_bags(db, farmer.id)
    
    return {
        "success": True,
        "farmer": farmer.to_dict(),
        "bags": bags
    }
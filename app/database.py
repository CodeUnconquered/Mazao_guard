"""
MAZAO GUARD - Professional Database with Retry Logic and Connection Pooling
Stable database operations with automatic retry on locks
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import NullPool
from datetime import datetime, timedelta
import re
import json
import hashlib
import secrets
import time
import logging
from functools import wraps

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== KENYA TIMEZONE HELPER ==========
# Kenya is UTC+3 (East Africa Time)

def get_kenya_time():
    """Return current time in Kenya (UTC+3) as timezone-aware datetime"""
    return datetime.utcnow() + timedelta(hours=3)


def get_kenya_time_naive():
    """Return current time in Kenya as naive datetime (for SQLite storage)"""
    return datetime.utcnow() + timedelta(hours=3)


# Database setup - Optimized SQLite for stability
DATABASE_URL = "sqlite:///./mazao_guard.db"

# Create engine with connection pooling and retry settings
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30  # Wait up to 30 seconds for lock
    },
    pool_size=10,
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=3600,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ========== RETRY DECORATOR FOR DATABASE OPERATIONS ==========

def retry_on_lock(max_retries=3, delay=0.5):
    """
    Decorator to retry database operations when SQLite is locked
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_msg = str(e).lower()
                    # Check if it's a lock error (SQLite busy)
                    if "locked" in error_msg or "busy" in error_msg or "database" in error_msg:
                        logger.warning(f"Database locked, retry {attempt + 1}/{max_retries}...")
                        time.sleep(delay * (attempt + 1))  # Exponential backoff
                        continue
                    # If not a lock error, raise immediately
                    raise
            # If we exhausted retries
            logger.error(f"Failed after {max_retries} retries: {last_exception}")
            raise last_exception
        return wrapper
    return decorator


# ========== VALIDATION FUNCTIONS ==========

def hash_password(password: str) -> str:
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return hash_password(password) == hashed


def generate_reset_token() -> str:
    """Generate a secure reset token"""
    return secrets.token_urlsafe(32)


def validate_phone_number(phone: str) -> tuple:
    """Validate Kenyan phone number (+2547... or +2541...)"""
    if not phone or phone == "":
        return True, None
    
    phone = phone.strip()
    pattern = r'^\+254[17]\d{8}$'
    if not bool(re.match(pattern, phone)):
        return False, "Phone number must be +254 followed by 9 digits (e.g., +254712345678)"
    
    return True, None


def validate_email(email: str) -> tuple:
    """Validate email format"""
    if not email or email == "":
        return True, None
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not bool(re.match(pattern, email)):
        return False, "Invalid email format (e.g., name@example.com)"
    
    return True, None


def validate_username(username: str) -> tuple:
    """Validate username (letters, numbers, underscores only)"""
    if not username or username == "":
        return False, "Username is required"
    
    username = username.strip()
    
    if len(username) < 3:
        return False, "Username must be at least 3 characters"
    
    if len(username) > 50:
        return False, "Username must be less than 50 characters"
    
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores"
    
    return True, None


def validate_password(password: str) -> tuple:
    """Validate password strength"""
    if not password:
        return False, "Password is required"
    
    if len(password) < 6:
        return False, "Password must be at least 6 characters"
    
    return True, None


# ========== DATABASE MODELS ==========

class Farmer(Base):
    """Farmer with username + password authentication"""
    __tablename__ = "farmers"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(64), nullable=False)
    phone_number = Column(String(20), unique=True, index=True, nullable=True)
    email = Column(String(100), unique=True, index=True, nullable=True)
    notification_preference = Column(String(20), default="sms")
    region = Column(String(50), nullable=True)
    registered_at = Column(DateTime, default=get_kenya_time_naive)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    bags = relationship("Bag", back_populates="farmer", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'phone_number': self.phone_number,
            'email': self.email,
            'notification_preference': self.notification_preference,
            'region': self.region,
            'registered_at': self.registered_at.isoformat() if self.registered_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'is_active': self.is_active
        }


class Bag(Base):
    """Individual bag or section of maize"""
    __tablename__ = "bags"
    
    id = Column(Integer, primary_key=True, index=True)
    bag_id = Column(String(100), unique=True, index=True, nullable=False)
    farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=False)
    name = Column(String(100), nullable=False)
    location_notes = Column(Text, nullable=True)
    maize_variety = Column(String(50), nullable=True)
    harvest_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_kenya_time_naive)
    
    farmer = relationship("Farmer", back_populates="bags")
    readings = relationship("Reading", back_populates="bag", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            'id': self.id,
            'bag_id': self.bag_id,
            'name': self.name,
            'location_notes': self.location_notes,
            'maize_variety': self.maize_variety,  # FIXED: was 'mize_variety'
            'harvest_date': self.harvest_date.isoformat() if self.harvest_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Reading(Base):
    """Sensor reading for a specific bag"""
    __tablename__ = "readings"
    
    id = Column(Integer, primary_key=True, index=True)
    bag_id = Column(Integer, ForeignKey("bags.id"), nullable=False)
    temperature = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    co2 = Column(Float, nullable=True)
    risk_score = Column(Float, default=0.0)
    risk_level = Column(String(20), default="UNKNOWN")
    detected_patterns = Column(Text, nullable=True)
    recommendation = Column(Text, default="")
    timestamp = Column(DateTime, default=get_kenya_time_naive)
    
    bag = relationship("Bag", back_populates="readings")
    
    def to_dict(self):
        return {
            'id': self.id,
            'temperature': self.temperature,
            'humidity': self.humidity,
            'co2': self.co2,
            'risk_score': self.risk_score,
            'risk_level': self.risk_level,
            'detected_patterns': json.loads(self.detected_patterns) if self.detected_patterns else [],
            'recommendation': self.recommendation,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


# ========== DATABASE FUNCTIONS WITH RETRY ==========

def get_db():
    """Dependency for FastAPI routes"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database initialized")


@retry_on_lock(max_retries=3)
def create_farmer(db, username, password, phone_number=None, email=None, notification_preference="sms", region=None):
    """
    Create a new farmer with username and password
    
    Returns:
        (farmer_object, error_message)
    """
    
    # Clean inputs
    username = username.strip() if username else ""
    password = password if password else ""
    phone_number = phone_number.strip() if phone_number else None
    email = email.strip().lower() if email else None
    
    # Handle empty strings as None
    if phone_number == "":
        phone_number = None
    if email == "":
        email = None
    
    # Validate username
    is_valid, error = validate_username(username)
    if not is_valid:
        return None, error
    
    # Check if username exists
    existing = db.query(Farmer).filter(Farmer.username == username).first()
    if existing:
        return None, f"Username '{username}' already exists. Please choose a different username."
    
    # Validate password
    is_valid, error = validate_password(password)
    if not is_valid:
        return None, error
    
    # Validate phone number (if provided)
    if phone_number:
        is_valid, error = validate_phone_number(phone_number)
        if not is_valid:
            return None, error
        
        existing_phone = db.query(Farmer).filter(Farmer.phone_number == phone_number).first()
        if existing_phone:
            return None, f"Phone number {phone_number} is already registered to another farmer."
    
    # Validate email (if provided)
    if email:
        is_valid, error = validate_email(email)
        if not is_valid:
            return None, error
        
        existing_email = db.query(Farmer).filter(Farmer.email == email).first()
        if existing_email:
            return None, f"Email {email} is already registered to another farmer."
    
    # Create farmer with hashed password
    farmer = Farmer(
        username=username,
        password_hash=hash_password(password),
        phone_number=phone_number,
        email=email,
        notification_preference=notification_preference,
        region=region
    )
    
    db.add(farmer)
    db.commit()
    db.refresh(farmer)
    
    return farmer, None


@retry_on_lock(max_retries=3)
def authenticate_farmer(db, username, password):
    """
    Authenticate farmer by username and password
    
    Returns:
        (farmer_object, error_message)
    """
    
    username = username.strip() if username else ""
    
    if not username:
        return None, "Username is required"
    
    if not password:
        return None, "Password is required"
    
    # Find farmer by username
    farmer = db.query(Farmer).filter(Farmer.username == username).first()
    
    if not farmer:
        return None, f"Username '{username}' not found. Please register first."
    
    # Verify password
    if not verify_password(password, farmer.password_hash):
        return None, "Incorrect password. Please try again."
    
    # Update last login with KENYA TIME
    farmer.last_login = get_kenya_time_naive()
    db.commit()
    db.refresh(farmer)
    
    return farmer, None


@retry_on_lock(max_retries=3)
def create_bag(db, farmer_id, name, location_notes=None, maize_variety=None, harvest_date=None):
    """Create a new bag for a farmer"""
    name = name.strip() if name else ""
    
    if not name:
        return None, "Bag name is required"
    
    if len(name) < 2:
        return None, "Bag name must be at least 2 characters"
    
    # Create unique bag_id
    bag_id = f"F{farmer_id}_{name.replace(' ', '_')}"
    
    # Check if bag exists
    existing = db.query(Bag).filter(Bag.bag_id == bag_id).first()
    if existing:
        return None, f"Bag '{name}' already exists for this farmer"
    
    # Create bag
    bag = Bag(
        bag_id=bag_id,
        farmer_id=farmer_id,
        name=name,
        location_notes=location_notes,
        maize_variety=maize_variety,
        harvest_date=harvest_date
    )
    
    db.add(bag)
    db.commit()
    db.refresh(bag)
    
    return bag, None


@retry_on_lock(max_retries=3)
def add_reading_to_bag(db, bag_id, temperature, humidity, co2, risk_score, risk_level, detected_patterns, recommendation):
    """Add a reading to a bag with KENYA TIME timestamp"""
    # Convert detected_patterns to JSON string if it's a list
    if isinstance(detected_patterns, list):
        detected_patterns = json.dumps(detected_patterns)
    
    reading = Reading(
        bag_id=bag_id,
        temperature=temperature,
        humidity=humidity,
        co2=co2,
        risk_score=risk_score,
        risk_level=risk_level,
        detected_patterns=detected_patterns,
        recommendation=recommendation,
        timestamp=get_kenya_time_naive()
    )
    
    db.add(reading)
    db.commit()
    db.refresh(reading)
    
    return reading


@retry_on_lock(max_retries=3)
def get_farmer_bags(db, farmer_id):
    """Get all bags for a farmer with their latest readings"""
    bags = db.query(Bag).filter(Bag.farmer_id == farmer_id).all()
    
    result = []
    for bag in bags:
        # Get latest reading
        latest_reading = db.query(Reading).filter(
            Reading.bag_id == bag.id
        ).order_by(Reading.timestamp.desc()).first()
        
        # Count total readings
        readings_count = db.query(Reading).filter(Reading.bag_id == bag.id).count()
        
        bag_dict = bag.to_dict()
        bag_dict['readings_count'] = readings_count
        
        if latest_reading:
            bag_dict['latest_risk_score'] = latest_reading.risk_score
            bag_dict['latest_risk_level'] = latest_reading.risk_level
            bag_dict['latest_timestamp'] = latest_reading.timestamp.isoformat()
            bag_dict['detected_patterns'] = json.loads(latest_reading.detected_patterns) if latest_reading.detected_patterns else []
            bag_dict['recommendation'] = latest_reading.recommendation
        else:
            bag_dict['latest_risk_score'] = None
            bag_dict['latest_risk_level'] = "NO_DATA"
            bag_dict['latest_timestamp'] = None
            bag_dict['detected_patterns'] = []
            bag_dict['recommendation'] = None
        
        result.append(bag_dict)
    
    return result


@retry_on_lock(max_retries=3)
def get_bag_readings(db, bag_id, limit=30):
    """Get reading history for a specific bag"""
    readings = db.query(Reading).filter(
        Reading.bag_id == bag_id
    ).order_by(Reading.timestamp.desc()).limit(limit).all()
    
    return [r.to_dict() for r in readings]


@retry_on_lock(max_retries=3)
def get_farmer_by_username(db, username):
    """Get farmer by username"""
    return db.query(Farmer).filter(Farmer.username == username).first()


@retry_on_lock(max_retries=3)
def delete_bag(db, bag_id):
    """Delete a bag and all its readings"""
    bag = db.query(Bag).filter(Bag.bag_id == bag_id).first()
    if bag:
        db.delete(bag)
        db.commit()
        return True
    return False
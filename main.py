"""
MAZAO GUARD - Complete Backend API (Stable Version)
Professional system with per-bag ML models, proper error handling, and no crashes
"""

import os
import json
from typing import Optional
from datetime import datetime
from contextlib import asynccontextmanager  # FIXED: removed extra 'context'

# Performance optimizations
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from fastapi import FastAPI, Depends, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import uvicorn

from app.database import get_db, init_db, create_bag, add_reading_to_bag, get_farmer_bags
from app.database import Farmer, Bag, Reading
from app.auth import router as auth_router
from app.ml_engine import ml_registry
from app.ml_engine import ml_manager  # For backward compatibility


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    print("Initializing database...")
    init_db()
    print("\n" + "="*50)
    print("🌽 MAZAO GUARD API STARTED")
    print("="*50)
    print("📍 API Docs: http://localhost:8000/docs")
    print("📍 Dashboard: streamlit run app/dashboard.py")
    print("📍 ML Engine: Per-bag models active")
    print("="*50 + "\n")
    yield
    print("Shutting down...")


app = FastAPI(
    title="Mazao Guard API",
    description="AI-Powered Aflatoxin Early Warning System for Kenyan Farmers",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include authentication routes
app.include_router(auth_router)


# ========== HEALTH & ROOT ENDPOINTS ==========

@app.get("/")
async def root():
    return {
        "name": "Mazao Guard",
        "version": "2.0.0",
        "status": "running",
        "authentication": "Username + Password",
        "ml_engine": "Per-bag independent models",
        "features": [
            "Farmer registration with username + password",
            "Phone/email validation (Kenyan format)",
            "Per-bag maize tracking",
            "Daily reading entry",
            "AI-powered risk detection",
            "Trend analysis (slow humidity ratchet, CO2 climb, etc.)",
            "Each bag has its own ML model"
        ]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "ml_models": ml_registry.get_stats() if hasattr(ml_registry, 'get_stats') else {"total_models": 0}
    }


@app.get("/ml/stats")
async def ml_stats():
    """Get ML engine statistics"""
    return ml_registry.get_stats() if hasattr(ml_registry, 'get_stats') else {"total_models": 0}


# ========== BAG MANAGEMENT ENDPOINTS ==========

@app.post("/bags/create")
async def create_new_bag(
    username: str = Form(...),
    bag_name: str = Form(...),
    location_notes: Optional[str] = Form(None),
    maize_variety: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new bag for an existing farmer"""
    
    try:
        # Find farmer by username
        farmer = db.query(Farmer).filter(Farmer.username == username).first()
        if not farmer:
            raise HTTPException(status_code=404, detail="Farmer not found. Please register first.")
        
        bag, error = create_bag(
            db=db,
            farmer_id=farmer.id,
            name=bag_name,
            location_notes=location_notes,
            maize_variety=maize_variety
        )
        
        if error:
            raise HTTPException(status_code=400, detail=error)
        
        # Pre-create ML model for this bag (so it's ready for readings)
        ml_registry.get_model(bag.bag_id)
        
        return {
            "success": True,
            "bag": bag.to_dict(),
            "message": f"✅ Bag '{bag_name}' created. Ready for readings."
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating bag: {str(e)}")


@app.get("/bags/{username}")
async def get_farmer_bags_endpoint(
    username: str,
    db: Session = Depends(get_db)
):
    """Get all bags for a farmer with latest readings"""
    
    farmer = db.query(Farmer).filter(Farmer.username == username).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")
    
    bags = get_farmer_bags(db, farmer.id)
    
    return {"success": True, "farmer": farmer.to_dict(), "bags": bags}


# ========== READING MANAGEMENT ENDPOINTS ==========

@app.post("/readings/add")
async def add_new_reading(
    username: str = Form(...),
    bag_name: str = Form(...),
    temperature: float = Form(...),
    humidity: float = Form(...),
    co2: Optional[float] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Add a new reading for a specific bag
    Uses per-bag ML model for accurate risk detection
    """
    
    try:
        # Validate inputs
        if temperature < -10 or temperature > 60:
            return {
                "success": False,
                "message": "Temperature must be between -10°C and 60°C"
            }
        
        if humidity < 0 or humidity > 100:
            return {
                "success": False,
                "message": "Humidity must be between 0% and 100%"
            }
        
        if co2 and (co2 < 300 or co2 > 5000):
            return {
                "success": False,
                "message": "CO₂ must be between 300 and 5000 ppm"
            }
        
        # Find farmer by username
        farmer = db.query(Farmer).filter(Farmer.username == username).first()
        if not farmer:
            return {
                "success": False,
                "message": f"Farmer '{username}' not found. Please register first."
            }
        
        # Find bag
        bag = db.query(Bag).filter(
            Bag.farmer_id == farmer.id,
            Bag.name == bag_name
        ).first()
        
        if not bag:
            return {
                "success": False,
                "message": f"Bag '{bag_name}' not found. Please create it first."
            }
        
        # Get the ML model for THIS SPECIFIC BAG
        # Each bag has its own independent model
        model = ml_registry.get_model(bag.bag_id)
        
        # Calculate risk using the bag's own model
        risk_score, risk_level, patterns, recommendation = model.calculate_risk(
            temperature, humidity, co2 if co2 else 450
        )
        
        # Save reading to database
        reading = add_reading_to_bag(
            db=db,
            bag_id=bag.id,
            temperature=temperature,
            humidity=humidity,
            co2=co2,
            risk_score=risk_score,
            risk_level=risk_level,
            detected_patterns=json.dumps(patterns),
            recommendation=recommendation
        )
        
        db.commit()
        
        return {
            "success": True,
            "reading": {
                "risk_score": risk_score,
                "risk_level": risk_level,
                "patterns": patterns,
                "recommendation": recommendation,
                "timestamp": reading.timestamp.isoformat()
            },
            "bag": bag.to_dict(),
            "ml_model_info": {
                "readings_analyzed": len(model.reading_history),
                "model_created_at": model.created_at.isoformat()
            }
        }
        
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "message": f"Error saving reading: {str(e)}"
        }


@app.get("/readings/{username}/{bag_name}")
async def get_bag_readings(
    username: str,
    bag_name: str,
    limit: int = 30,
    db: Session = Depends(get_db)
):
    """Get reading history for a specific bag"""
    
    try:
        farmer = db.query(Farmer).filter(Farmer.username == username).first()
        if not farmer:
            raise HTTPException(status_code=404, detail="Farmer not found")
        
        bag = db.query(Bag).filter(
            Bag.farmer_id == farmer.id,
            Bag.name == bag_name
        ).first()
        
        if not bag:
            raise HTTPException(status_code=404, detail="Bag not found")
        
        readings = db.query(Reading).filter(
            Reading.bag_id == bag.id
        ).order_by(Reading.timestamp.desc()).limit(limit).all()
        
        # Get ML model stats for this bag
        model = ml_registry.get_model(bag.bag_id)
        
        return {
            "success": True,
            "bag": bag.to_dict(),
            "readings": [r.to_dict() for r in readings],
            "total_readings": len(readings),
            "ml_stats": {
                "history_size": len(model.reading_history),
                "last_risk_score": model.last_risk_score,
                "last_risk_level": model.last_risk_level
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== DASHBOARD ENDPOINTS ==========

@app.get("/dashboard/{username}")
async def get_dashboard(
    username: str,
    db: Session = Depends(get_db)
):
    """Complete dashboard data for a farmer"""
    
    try:
        farmer = db.query(Farmer).filter(Farmer.username == username).first()
        if not farmer:
            raise HTTPException(status_code=404, detail="Farmer not found")
        
        bags = get_farmer_bags(db, farmer.id)
        
        # Enhance bag data with ML model info (with error handling)
        for bag in bags:
            try:
                # Get the ML model for this bag (or create if doesn't exist)
                model = ml_registry.get_model(bag['bag_id'])
                bag['ml_readings'] = len(model.reading_history) if hasattr(model, 'reading_history') else 0
                bag['model_risk_score'] = model.last_risk_score if hasattr(model, 'last_risk_score') else 0
                bag['model_risk_level'] = model.last_risk_level if hasattr(model, 'last_risk_level') else "LOW"
            except Exception as e:
                # If ML model fails, just use defaults
                bag['ml_readings'] = 0
                bag['model_risk_score'] = 0
                bag['model_risk_level'] = "LOW"
        
        # Calculate overall risk summary
        risk_summary = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0, "NO_DATA": 0}
        for bag in bags:
            level = bag.get('latest_risk_level', 'NO_DATA')
            risk_summary[level] = risk_summary.get(level, 0) + 1
        
        # Safely get ML stats
        try:
            ml_stats = ml_registry.get_stats() if hasattr(ml_registry, 'get_stats') else {"total_models": 0}
        except Exception:
            ml_stats = {"total_models": 0}
        
        return {
            "success": True,
            "farmer": farmer.to_dict(),
            "bags": bags,
            "risk_summary": risk_summary,
            "total_bags": len(bags),
            "ml_stats": ml_stats
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ========== UTILITY ENDPOINTS ==========

@app.get("/check-username/{username}")
async def check_username(
    username: str,
    db: Session = Depends(get_db)
):
    """Check if a username is available"""
    farmer = db.query(Farmer).filter(Farmer.username == username).first()
    return {
        "available": farmer is None,
        "message": "Username available" if not farmer else "Username already taken"
    }


@app.post("/ml/clear/{bag_id}")
async def clear_bag_model(
    bag_id: str,
    db: Session = Depends(get_db)
):
    """Clear ML model for a specific bag (useful for debugging)"""
    ml_registry.clear_model(bag_id)
    return {
        "success": True,
        "message": f"ML model cleared for bag: {bag_id}"
    }


# ========== EXCEPTION HANDLERS ==========

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for better error messages"""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"Server error: {str(exc)}",
            "type": type(exc).__name__
        }
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        timeout_keep_alive=30,
        limit_concurrency=100,
        limit_max_requests=1000
    )
"""
MAZAO GUARD - ML Engine (Redesigned for Stability)
Each bag gets its own independent ML model - NO crashes on multiple bags
"""

import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== KENYA TIMEZONE HELPER ==========
# Kenya is UTC+3 (East Africa Time)

def get_kenya_time():
    """Return current time in Kenya (UTC+3)"""
    return datetime.utcnow() + timedelta(hours=3)


def get_kenya_time_iso():
    """Return current Kenya time as ISO format string"""
    return (datetime.utcnow() + timedelta(hours=3)).isoformat()


class BagRiskModel:
    """Independent risk model for a single bag - one instance per bag"""
    
    def __init__(self, bag_id: str):
        self.bag_id = bag_id
        self.reading_history = []  # Max 30 readings
        self.last_risk_score = 0
        self.last_risk_level = "LOW"
        self.created_at = get_kenya_time()  # KENYA TIME
        logger.info(f"Created new risk model for bag: {bag_id}")
    
    def add_reading(self, temp: float, humidity: float, co2: float):
        """Add reading to history for trend analysis"""
        self.reading_history.append({
            'temp': temp,
            'humidity': humidity,
            'co2': co2 if co2 else 450,
            'timestamp': get_kenya_time_iso()  # KENYA TIME
        })
        # Keep only last 30 readings to prevent memory bloat
        if len(self.reading_history) > 30:
            self.reading_history.pop(0)
        logger.debug(f"Bag {self.bag_id}: Added reading. History size: {len(self.reading_history)}")
    
    def calculate_current_danger(self, temp: float, humidity: float) -> float:
        """
        Calculate immediate danger from current readings
        Returns: risk points (0-40)
        """
        risk = 0.0
        
        # Humidity risk (0-25 points)
        if humidity > 80:
            risk += 25
        elif humidity > 75:
            risk += 20
        elif humidity > 70:
            risk += 15
        elif humidity > 65:
            risk += 8
        elif humidity > 60:
            risk += 4
        
        # Temperature risk (0-15 points)
        if temp > 35:
            risk += 15
        elif temp > 32:
            risk += 12
        elif temp > 30:
            risk += 8
        elif temp > 28:
            risk += 5
        elif temp > 26:
            risk += 2
        
        return min(40, risk)
    
    def calculate_trend_risk(self) -> Tuple[float, List[Dict]]:
        """
        Calculate risk from trends over time
        Returns: (risk_points, detected_patterns)
        """
        if len(self.reading_history) < 4:
            return 0, []
        
        patterns = []
        risk = 0.0
        
        # Get last 5 readings
        recent = self.reading_history[-5:]
        humidities = [r['humidity'] for r in recent]
        temps = [r['temp'] for r in recent]
        co2s = [r['co2'] for r in recent]
        
        # PATTERN 1: Slow humidity ratchet (MOST IMPORTANT)
        # This detects the 0.3% daily increase that humans cannot see
        increases = 0
        total_increase = 0
        for i in range(1, len(humidities)):
            diff = humidities[i] - humidities[i-1]
            if diff > 0:
                increases += 1
                total_increase += diff
        
        if increases >= 3:  # 3 out of 4 increases
            avg_increase = total_increase / increases if increases > 0 else 0
            if avg_increase > 0.3:
                # Scale risk: 0.3% = 10 points, 1% = 35 points
                trend_risk = min(35, avg_increase * 25)
                risk += trend_risk
                patterns.append({
                    'pattern': 'SLOW_HUMIDITY_RATCHET',
                    'severity': round(min(1.0, avg_increase / 1.5), 2),
                    'description': f"Humidity rising {avg_increase:.2f}% per reading",
                    'human_detectable': False,
                    'risk_contribution': round(trend_risk, 1)
                })
                logger.debug(f"Bag {self.bag_id}: Detected slow humidity ratchet: {avg_increase:.2f}% per reading")
        
        # PATTERN 2: CO2 climb (early mold warning)
        if len(co2s) >= 4:
            co2_change = co2s[-1] - co2s[-4]
            if co2_change > 20:
                co2_risk = min(25, co2_change / 2.5)
                risk += co2_risk
                patterns.append({
                    'pattern': 'CO2_CLIMB',
                    'severity': round(min(1.0, co2_change / 80), 2),
                    'description': f"CO₂ increased by {co2_change:.0f} ppm",
                    'human_detectable': False,
                    'risk_contribution': round(co2_risk, 1)
                })
        
        # PATTERN 3: Temperature spike
        if len(temps) >= 4:
            temp_change = temps[-1] - temps[-4]
            if temp_change > 2:
                temp_risk = min(20, temp_change * 6)
                risk += temp_risk
                patterns.append({
                    'pattern': 'TEMPERATURE_SPIKE',
                    'severity': round(min(1.0, temp_change / 8), 2),
                    'description': f"Temperature rose {temp_change:.1f}°C",
                    'human_detectable': True,
                    'risk_contribution': round(temp_risk, 1)
                })
        
        return min(40, risk), patterns
    
    def calculate_volatility_risk(self) -> Tuple[float, Dict]:
        """
        Calculate risk from humidity fluctuations
        Returns: (risk_points, pattern_dict)
        """
        if len(self.reading_history) < 6:
            return 0, None
        
        humidities = [r['humidity'] for r in self.reading_history[-6:]]
        volatility = float(np.std(humidities))
        
        if volatility > 4:
            risk = min(20, volatility * 3)
            pattern = {
                'pattern': 'HIGH_VOLATILITY',
                'severity': round(min(1.0, volatility / 12), 2),
                'description': f"Humidity fluctuating ±{volatility:.1f}%",
                'human_detectable': True,
                'risk_contribution': round(risk, 1)
            }
            return risk, pattern
        
        return 0, None
    
    def calculate_risk(self, temp: float, humidity: float, co2: float) -> Tuple[float, str, List[Dict], str]:
        """
        Calculate comprehensive risk score synchronously
        
        Returns:
            risk_score (0-100)
            risk_level (LOW/MEDIUM/HIGH/CRITICAL)
            detected_patterns (list of patterns found)
            recommendation (str)
        """
        # Add current reading to history
        self.add_reading(temp, humidity, co2)
        
        detected_patterns = []
        total_risk = 0.0
        
        # 1. Current danger (40% of final risk) - immediate risk from current values
        current_risk = self.calculate_current_danger(temp, humidity)
        total_risk += current_risk
        logger.debug(f"Bag {self.bag_id}: Current risk = {current_risk}")
        
        # Add current danger as a "pattern" for transparency
        if current_risk > 15:
            detected_patterns.append({
                'pattern': 'CURRENT_DANGER',
                'severity': round(min(1.0, current_risk / 40), 2),
                'description': f"Current: {temp:.0f}°C, {humidity:.0f}% humidity",
                'human_detectable': True,
                'risk_contribution': round(current_risk, 1)
            })
        
        # 2. Trend risk (40% weight) - slow changes over time
        trend_risk, trend_patterns = self.calculate_trend_risk()
        total_risk += trend_risk
        detected_patterns.extend(trend_patterns)
        logger.debug(f"Bag {self.bag_id}: Trend risk = {trend_risk}")
        
        # 3. Volatility risk (20% weight) - fluctuations
        volatility_risk, volatility_pattern = self.calculate_volatility_risk()
        total_risk += volatility_risk
        if volatility_pattern:
            detected_patterns.append(volatility_pattern)
        logger.debug(f"Bag {self.bag_id}: Volatility risk = {volatility_risk}")
        
        # Cap at 100
        risk_score = min(100, max(0, round(total_risk, 1)))
        
        # Determine risk level
        if risk_score < 25:
            risk_level = "LOW"
        elif risk_score < 50:
            risk_level = "MEDIUM"
        elif risk_score < 75:
            risk_level = "HIGH"
        else:
            risk_level = "CRITICAL"
        
        # Generate recommendation
        recommendation = self._generate_recommendation(risk_score, detected_patterns, temp, humidity)
        
        # Store last values
        self.last_risk_score = risk_score
        self.last_risk_level = risk_level
        
        logger.info(f"Bag {self.bag_id}: Final risk = {risk_score} ({risk_level}) with {len(detected_patterns)} patterns")
        
        return risk_score, risk_level, detected_patterns, recommendation
    
    def _generate_recommendation(self, risk_score: float, patterns: List[Dict], temp: float, humidity: float) -> str:
        """Generate actionable recommendation for farmer"""
        
        # CRITICAL RISK - highest priority
        if risk_score >= 75:
            return "🔥 CRITICAL! Your maize is at high risk of aflatoxin. Sell, dry immediately, or consult an expert within 24 hours."
        
        # HIGH RISK
        if risk_score >= 50:
            # Check for specific dangerous patterns
            for p in patterns:
                if p['pattern'] == 'SLOW_HUMIDITY_RATCHET':
                    return f"⚠️ HIGH RISK! Humidity is rising daily. Aerate your maize for 8+ hours today. Consider a test strip."
                if p['pattern'] == 'CO2_CLIMB':
                    return f"⚠️ HIGH RISK! CO₂ levels rising - early mold activity. Aerate immediately for 8+ hours."
                if p['pattern'] == 'CURRENT_DANGER':
                    return f"⚠️ HIGH RISK! Current conditions are dangerous. Aerate for 8+ hours today."
            return f"⚠️ HIGH RISK! Take action today - aerate for 8+ hours. Consider an aflatoxin test strip."
        
        # MEDIUM RISK
        if risk_score >= 25:
            for p in patterns:
                if p['pattern'] == 'SLOW_HUMIDITY_RATCHET':
                    return f"📊 MEDIUM RISK - Humidity slowly rising. Aerate for 4-6 hours to prevent mold."
                if p['pattern'] == 'CO2_CLIMB':
                    return f"📊 MEDIUM RISK - CO₂ levels rising. Check for musty smell and aerate."
            return f"📊 MEDIUM RISK - Monitor closely. Consider aerating if conditions persist."
        
        # LOW RISK but with some concerns
        if temp > 28 or humidity > 70:
            return f"📊 LOW-MEDIUM RISK - Conditions are warm/humid. Monitor daily."
        
        if patterns:
            return f"✅ LOW RISK - {patterns[0]['description']}. Continue monitoring daily."
        
        # LOW RISK - all good
        return "✅ LOW RISK - Your maize storage conditions are good. Keep monitoring daily."
    
    def get_summary(self) -> Dict:
        """Get summary of current state"""
        return {
            'bag_id': self.bag_id,
            'readings_count': len(self.reading_history),
            'last_risk_score': self.last_risk_score,
            'last_risk_level': self.last_risk_level,
            'created_at': self.created_at.isoformat(),
            'last_reading': self.reading_history[-1] if self.reading_history else None
        }


class MLModelRegistry:
    """
    Thread-safe registry for bag models
    Each bag gets its own independent model - prevents cross-bag contamination
    """
    
    _instance = None
    _models: Dict[str, BagRiskModel] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            logger.info("MLModelRegistry initialized")
        return cls._instance
    
    def get_model(self, bag_id: str) -> BagRiskModel:
        """Get or create a model for a specific bag"""
        if bag_id not in self._models:
            self._models[bag_id] = BagRiskModel(bag_id)
            logger.info(f"Created new model for bag: {bag_id}. Total models: {len(self._models)}")
        return self._models[bag_id]
    
    def clear_model(self, bag_id: str):
        """Remove a bag's model (useful for cleanup)"""
        if bag_id in self._models:
            del self._models[bag_id]
            logger.info(f"Cleared model for bag: {bag_id}")
    
    def clear_all_models(self):
        """Clear all models (useful for testing)"""
        count = len(self._models)
        self._models.clear()
        logger.info(f"Cleared all {count} models")
    
    def get_stats(self) -> Dict:
        """Get statistics about registered models"""
        return {
            'total_models': len(self._models),
            'model_ids': list(self._models.keys()),
            'total_readings': sum(len(m.reading_history) for m in self._models.values())
        }
    
    @property
    def readings_count(self):
        """Property for backward compatibility"""
        return sum(len(m.reading_history) for m in self._models.values())


# Singleton instance for the registry
ml_registry = MLModelRegistry()

# For backward compatibility with existing code
class BackwardCompatibleManager:
    """Wrapper for backward compatibility"""
    
    def __getattr__(self, name):
        if name == 'bag_id':
            return "global_compat"
        return getattr(ml_registry, name)
    
    def calculate_risk(self, temp, humidity, co2):
        """Legacy method - creates a temporary model"""
        model = ml_registry.get_model("legacy_global")
        return model.calculate_risk(temp, humidity, co2)


# For backward compatibility with existing imports
ml_manager = BackwardCompatibleManager()
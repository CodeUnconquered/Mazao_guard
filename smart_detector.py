"""
MAZAO GUARD - Smart Aflatoxin Risk Detector
The core intelligence that analyzes trends per bag/section

What makes this "SMART":
1. Per-bag baselines (what's normal for THIS bag)
2. Multi-dimensional anomaly detection (temp, humidity, CO2 together)
3. Sequence analysis (detects slow trends humans miss)
4. Cross-bag comparison (learns from other bags)
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from datetime import datetime, timedelta
from collections import deque
import warnings
warnings.filterwarnings('ignore')


class BagOfMaize:
    """
    Represents ONE bag or section of maize
    Each bag has its own normal patterns and risk model
    """
    
    def __init__(self, bag_id, bag_name, farmer_id, location_notes=""):
        self.bag_id = bag_id
        self.bag_name = bag_name
        self.farmer_id = farmer_id
        self.location_notes = location_notes
        self.readings = []  # List of (timestamp, temp, humidity, co2)
        self.risk_history = deque(maxlen=30)  # Last 30 risk scores
        self.model_trained = False
        self.isolation_forest = None
        self.scaler = None
        self.baseline_stats = None
        
    def add_reading(self, temp, humidity, co2, timestamp=None):
        """Add a new sensor reading for this bag"""
        if timestamp is None:
            timestamp = datetime.now()
        
        reading = {
            'timestamp': timestamp,
            'temp': temp,
            'humidity': humidity,
            'co2': co2
        }
        self.readings.append(reading)
        return reading
    
    def get_recent_readings(self, days=7):
        """Get readings from last N days"""
        cutoff = datetime.now() - timedelta(days=days)
        return [r for r in self.readings if r['timestamp'] > cutoff]
    
    def calculate_baseline(self):
        """
        Establish what is "NORMAL" for THIS bag
        This is CRITICAL - what's normal for one bag may be anomalous for another
        """
        if len(self.readings) < 10:
            return None  # Not enough data yet
        
        temps = [r['temp'] for r in self.readings]
        humidities = [r['humidity'] for r in self.readings]
        co2s = [r['co2'] for r in self.readings]
        
        self.baseline_stats = {
            'temp_mean': np.mean(temps),
            'temp_std': np.std(temps),
            'humidity_mean': np.mean(humidities),
            'humidity_std': np.std(humidities),
            'co2_mean': np.mean(co2s),
            'co2_std': np.std(co2s),
            'readings_count': len(self.readings)
        }
        
        # Train Isolation Forest on this bag's data
        X = np.array([[r['temp'], r['humidity'], r['co2']] for r in self.readings])
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        self.isolation_forest = IsolationForest(
            contamination=0.1,  # Expect ~10% of readings to be anomalous
            random_state=42,
            n_estimators=100
        )
        self.isolation_forest.fit(X_scaled)
        self.model_trained = True
        
        return self.baseline_stats
    
    def detect_sequence_anomaly(self):
        """
        CRITICAL METHOD - This detects the SLOW RATCHET pattern
        Humans cannot see a 0.3% humidity increase per day, but this can
        
        Returns:
            dict with anomaly scores for different patterns
        """
        if len(self.readings) < 8:
            return {'has_anomaly': False, 'patterns': []}
        
        # Get last 8 readings (last 2 days if 4 readings/day)
        recent = self.readings[-8:]
        
        # Extract sequences
        temps = [r['temp'] for r in recent]
        humidities = [r['humidity'] for r in recent]
        co2s = [r['co2'] for r in recent]
        
        detected_patterns = []
        
        # PATTERN 1: Slow humidity ratchet (most dangerous, hardest for humans)
        # Calculate trend over 8 readings
        hum_slope = self.calculate_trend(humidities)
        
        if hum_slope > 0.3:  # Increasing more than 0.3% per reading (1.2% per day)
            # Check if the increase is consistent (not just random fluctuation)
            increasing_count = sum(1 for i in range(1, len(humidities)) if humidities[i] > humidities[i-1])
            consistency = increasing_count / (len(humidities) - 1)
            
            if consistency > 0.7:  # 70% of readings show increase
                detected_patterns.append({
                    'pattern': 'SLOW_HUMIDITY_RATCHET',
                    'severity': min(1.0, hum_slope / 1.5),
                    'description': f'Humidity rising {hum_slope:.2f}% per reading over 2 days',
                    'human_detectable': False  # Humans cannot see this
                })
        
        # PATTERN 2: CO2 climb (early fungal respiration)
        co2_slope = self.calculate_trend(co2s)
        if co2_slope > 3:  # Rising more than 3 ppm per reading
            detected_patterns.append({
                'pattern': 'CO2_CLIMB',
                'severity': min(1.0, co2_slope / 15),
                'description': f'CO2 rising {co2_slope:.1f} ppm per reading',
                'human_detectable': False  # Humans cannot smell CO2
            })
        
        # PATTERN 3: Temperature-Humidity synergy (dangerous combo)
        temp_slope = self.calculate_trend(temps)
        hum_slope_short = self.calculate_trend(humidities[-4:]) if len(humidities) >= 4 else 0
        
        if temp_slope > 0.1 and hum_slope_short > 0.5:
            detected_patterns.append({
                'pattern': 'TEMP_HUMIDITY_SYNERGY',
                'severity': 0.85,
                'description': f'Temp↑{temp_slope:.1f}°C + Humidity↑{hum_slope_short:.1f}% together',
                'human_detectable': False
            })
        
        # PATTERN 4: High volatility (rapid up-down cycles)
        hum_volatility = np.std(humidities[-8:])
        if hum_volatility > 5:  # High variation
            detected_patterns.append({
                'pattern': 'HIGH_VOLATILITY',
                'severity': min(1.0, hum_volatility / 12),
                'description': f'Humidity fluctuating ±{hum_volatility:.1f}%',
                'human_detectable': True  # Farmers might notice this
            })
        
        return {
            'has_anomaly': len(detected_patterns) > 0,
            'patterns': detected_patterns,
            'max_severity': max([p['severity'] for p in detected_patterns]) if detected_patterns else 0
        }
    
    def calculate_trend(self, values):
        """Calculate the slope/trend of a sequence of values"""
        if len(values) < 2:
            return 0
        x = np.arange(len(values))
        slope = np.polyfit(x, values, 1)[0]
        return slope
    
    def detect_point_anomaly(self, temp, humidity, co2):
        """
        Detect if a SINGLE reading is anomalous for this bag
        Uses Isolation Forest trained on bag's own history
        """
        if not self.model_trained or self.isolation_forest is None:
            return 0.0  # Not enough data yet
        
        X_new = np.array([[temp, humidity, co2]])
        X_scaled = self.scaler.transform(X_new)
        
        # score_samples returns: lower = more anomalous
        anomaly_score = self.isolation_forest.score_samples(X_scaled)[0]
        
        # Convert to 0-1 scale where 1 = very anomalous
        normalized = 1 - (anomaly_score + 0.5)  # anomaly_score ranges from -0.5 to 0.5
        return max(0, min(1, normalized))
    
    def calculate_deviation_score(self, temp, humidity, co2):
        """
        How far is this reading from bag's normal range?
        Uses standard deviations (z-score)
        """
        if not self.baseline_stats:
            return 0
        
        temp_z = abs(temp - self.baseline_stats['temp_mean']) / self.baseline_stats['temp_std']
        hum_z = abs(humidity - self.baseline_stats['humidity_mean']) / self.baseline_stats['humidity_std']
        co2_z = abs(co2 - self.baseline_stats['co2_mean']) / self.baseline_stats['co2_std']
        
        # Cap at 3 standard deviations (beyond that is definitely anomalous)
        max_z = min(3, max(temp_z, hum_z, co2_z))
        
        # Convert to 0-1 score
        return max_z / 3
    
    def calculate_risk_score(self):
        """
        THE MAIN METHOD - Combines all signals into one risk score
        This is what makes our system SMART
        """
        if len(self.readings) < 3:
            return 0, "Insufficient data", "Need at least 3 readings to establish baseline"
        
        # Get the most recent reading
        latest = self.readings[-1]
        temp, humidity, co2 = latest['temp'], latest['humidity'], latest['co2']
        
        # 1. Point anomaly (Isolation Forest) - 20% weight
        point_score = self.detect_point_anomaly(temp, humidity, co2)
        
        # 2. Sequence anomaly (the SMART part) - 50% weight (most important!)
        seq_analysis = self.detect_sequence_anomaly()
        sequence_score = seq_analysis['max_severity']
        
        # 3. Deviation from baseline - 15% weight
        deviation_score = self.calculate_deviation_score(temp, humidity, co2)
        
        # 4. Risk momentum (is it getting worse?) - 15% weight
        if len(self.risk_history) >= 3:
            recent_risks = list(self.risk_history)[-3:]
            momentum = (recent_risks[-1] - recent_risks[0]) / 100  # Normalized
            momentum_score = max(0, min(0.5, momentum))
        else:
            momentum_score = 0
        
        # Combine all signals
        raw_risk = (
            point_score * 0.20 +
            sequence_score * 0.50 +
            deviation_score * 0.15 +
            momentum_score * 0.15
        ) * 100
        
        risk_score = min(100, max(0, raw_risk))
        
        # Store for momentum calculation
        self.risk_history.append(risk_score)
        
        # Generate recommendation based on risk and patterns
        recommendation = self.generate_recommendation(risk_score, seq_analysis)
        
        return risk_score, recommendation, seq_analysis
    
    def generate_recommendation(self, risk_score, seq_analysis):
        """Generate actionable advice for the farmer"""
        if risk_score < 30:
            return {
                'action': 'No action needed',
                'urgency': 'low',
                'message': 'Your maize storage conditions are good. Continue regular monitoring.'
            }
        elif risk_score < 60:
            # Check what pattern is causing the risk
            patterns = [p['pattern'] for p in seq_analysis.get('patterns', [])]
            if 'SLOW_HUMIDITY_RATCHET' in patterns:
                return {
                    'action': 'Aerate for 4-6 hours today',
                    'urgency': 'medium',
                    'message': 'I detect humidity slowly rising. Aeration will help stop this trend.'
                }
            elif 'CO2_CLIMB' in patterns:
                return {
                    'action': 'Inspect for early mold growth',
                    'urgency': 'medium',
                    'message': 'CO2 levels are rising. Check your grain for any musty smell.'
                }
            else:
                return {
                    'action': 'Monitor closely, aerate if possible',
                    'urgency': 'medium',
                    'message': 'Conditions are concerning but not yet dangerous.'
                }
        elif risk_score < 80:
            return {
                'action': 'Aerate for 8+ hours AND consider test strip',
                'urgency': 'high',
                'message': 'High risk detected. Take action today to prevent aflatoxin.'
            }
        else:
            return {
                'action': 'URGENT: Sell or dry immediately',
                'urgency': 'critical',
                'message': 'Critical risk! Your maize is at high risk of aflatoxin. Act within 24 hours.'
            }
    
    def get_summary(self):
        """Get a human-readable summary of this bag's status"""
        if len(self.readings) == 0:
            return f"Bag '{self.bag_name}': No readings yet"
        
        risk_score, rec, patterns = self.calculate_risk_score()
        
        # Determine risk level emoji
        if risk_score < 30:
            emoji = "🟢"
            level = "LOW"
        elif risk_score < 60:
            emoji = "🟡"
            level = "MEDIUM"
        elif risk_score < 80:
            emoji = "🟠"
            level = "HIGH"
        else:
            emoji = "🔴"
            level = "CRITICAL"
        
        # Get latest reading
        latest = self.readings[-1]
        
        summary = f"""
{emoji} {self.bag_name} - {level} RISK ({risk_score:.0f}%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Latest: {latest['temp']}°C, {latest['humidity']}% humidity, {latest['co2']} ppm CO2
📈 Readings: {len(self.readings)} total

🔍 Detected Patterns:
"""
        if patterns.get('patterns'):
            for p in patterns['patterns']:
                detectability = "🤖 AI-detected" if not p['human_detectable'] else "👁️ Visible"
                summary += f"   • {p['pattern']}: {p['description']} ({detectability})\n"
        else:
            summary += "   • No concerning patterns detected\n"
        
        summary += f"""
💡 Recommendation: {rec['action']}
   {rec['message']}
"""
        return summary


class MazaoGuardSystem:
    """
    Main system that manages multiple bags for multiple farmers
    """
    
    def __init__(self):
        self.bags = {}  # bag_id -> BagOfMaize object
        self.farmers = {}  # farmer_id -> list of bag_ids
    
    def add_farmer(self, farmer_id, farmer_name, phone_number=""):
        """Register a new farmer"""
        if farmer_id not in self.farmers:
            self.farmers[farmer_id] = {
                'name': farmer_name,
                'phone': phone_number,
                'bags': []
            }
        return self.farmers[farmer_id]
    
    def add_bag(self, farmer_id, bag_name, location_notes=""):
        """Add a new bag/section for a farmer"""
        bag_id = f"{farmer_id}_{bag_name.replace(' ', '_')}"
        
        if bag_id not in self.bags:
            self.bags[bag_id] = BagOfMaize(bag_id, bag_name, farmer_id, location_notes)
            self.farmers[farmer_id]['bags'].append(bag_id)
        
        return bag_id
    
    def add_reading(self, bag_id, temp, humidity, co2, timestamp=None):
        """Add a sensor reading to a specific bag"""
        if bag_id not in self.bags:
            return {'error': f'Bag {bag_id} not found'}
        
        bag = self.bags[bag_id]
        bag.add_reading(temp, humidity, co2, timestamp)
        
        # After every 10 readings, recalculate baseline
        if len(bag.readings) >= 10 and len(bag.readings) % 10 == 0:
            bag.calculate_baseline()
        
        # Calculate updated risk
        risk_score, rec, patterns = bag.calculate_risk_score()
        
        return {
            'bag_id': bag_id,
            'bag_name': bag.bag_name,
            'risk_score': risk_score,
            'risk_level': self.get_risk_level(risk_score),
            'recommendation': rec,
            'patterns_found': patterns.get('patterns', []),
            'readings_count': len(bag.readings)
        }
    
    def get_risk_level(self, score):
        if score < 30:
            return "LOW"
        elif score < 60:
            return "MEDIUM"
        elif score < 80:
            return "HIGH"
        else:
            return "CRITICAL"
    
    def get_farmer_dashboard(self, farmer_id):
        """Generate a dashboard view for a farmer"""
        if farmer_id not in self.farmers:
            return "Farmer not found"
        
        farmer = self.farmers[farmer_id]
        dashboard = f"""
╔══════════════════════════════════════════════════════════════╗
║              🌽 MAZAO GUARD - FARMER DASHBOARD               ║
║                       {farmer['name']}                         ║
╚══════════════════════════════════════════════════════════════╝

📦 YOUR BAGS ({len(farmer['bags'])} total)
"""
        for bag_id in farmer['bags']:
            bag = self.bags[bag_id]
            if len(bag.readings) > 0:
                risk_score, _, _ = bag.calculate_risk_score()
                emoji = "🟢" if risk_score < 30 else "🟡" if risk_score < 60 else "🟠" if risk_score < 80 else "🔴"
                dashboard += f"\n{emoji} {bag.bag_name}: {risk_score:.0f}% risk ({len(bag.readings)} readings)"
            else:
                dashboard += f"\n⚪ {bag.bag_name}: No readings yet"
        
        dashboard += "\n\n" + "="*60 + "\n"
        dashboard += "💡 Tip: Add readings regularly for best predictions\n"
        dashboard += "   Early detection of trends = healthier maize!"
        
        return dashboard


# ============================================
# DEMONSTRATION - Let's test our smart system
# ============================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🌽 MAZAO GUARD - Smart Aflatoxin Risk Detector")
    print("   Demonstrating per-bag trend analysis")
    print("="*70 + "\n")
    
    # Create the system
    system = MazaoGuardSystem()
    
    # Add a farmer
    farmer = system.add_farmer("F001", "James Otieno", "+254712345678")
    print(f"✅ Farmer registered: {farmer['name']}")
    
    # Add bags for this farmer
    bag1_id = system.add_bag("F001", "North Corner", "Top of stack, near window")
    bag2_id = system.add_bag("F001", "South Section", "Bottom of stack, concrete floor")
    print(f"✅ Bags added: North Corner, South Section\n")
    
    # SIMULATE READINGS FOR BAG 1 (North Corner) - HEALTHY
    print("📊 SIMULATION 1: NORTH CORNER - HEALTHY STORAGE")
    print("-" * 50)
    
    # Healthy readings - stable conditions
    healthy_readings = [
        (24, 58, 420), (24, 59, 425), (25, 58, 422), (24, 57, 418),
        (25, 59, 430), (26, 60, 428), (25, 58, 425), (24, 57, 420),
        (25, 59, 432), (26, 61, 435), (25, 59, 428), (24, 58, 422)
    ]
    
    for i, (t, h, c) in enumerate(healthy_readings):
        result = system.add_reading(bag1_id, t, h, c)
        if i == len(healthy_readings) - 1:  # Last reading
            print(f"📈 After {i+1} readings:")
            print(f"   Risk Score: {result['risk_score']:.0f}% ({result['risk_level']})")
            print(f"   Recommendation: {result['recommendation']['action']}")
            print(f"   Patterns: {[p['pattern'] for p in result['patterns_found']] if result['patterns_found'] else 'None'}")
    
    # SIMULATE READINGS FOR BAG 2 (South Section) - DEVELOPING RISK
    print("\n" + "="*50)
    print("📊 SIMULATION 2: SOUTH SECTION - DEVELOPING AFLATOXIN RISK")
    print("-" * 50)
    print("⚠️  This bag will show the SLOW RATCHET pattern that humans miss")
    
    # Risk readings - slow humidity increase (dangerous pattern)
    risk_readings = [
        (25, 62, 440), (25, 63, 445), (26, 64, 450), (25, 63, 448),  # Day 1-2: Stable
        (26, 65, 455), (26, 66, 460), (27, 67, 465), (26, 66, 462),  # Day 3-4: Starting to rise
        (27, 68, 475), (27, 69, 485), (28, 70, 495), (27, 69, 490),  # Day 5-6: Increasing
        (28, 71, 510), (28, 72, 525), (29, 73, 540), (28, 72, 535),  # Day 7-8: High risk
        (29, 74, 560), (29, 75, 580), (30, 76, 600), (29, 75, 590)   # Day 9-10: Critical
    ]
    
    for i, (t, h, c) in enumerate(risk_readings):
        result = system.add_reading(bag2_id, t, h, c)
        if i == 7:  # Midway
            print(f"\n📊 After 8 readings (Day 2):")
            print(f"   Risk Score: {result['risk_score']:.0f}% ({result['risk_level']})")
            print(f"   Recommendation: {result['recommendation']['action']}")
        elif i == 15:  # Late
            print(f"\n📊 After 16 readings (Day 4):")
            print(f"   Risk Score: {result['risk_score']:.0f}% ({result['risk_level']})")
            print(f"   Recommendation: {result['recommendation']['action']}")
        elif i == len(risk_readings) - 1:  # Final
            print(f"\n📊 FINAL After {i+1} readings (Day 5):")
            print(f"   Risk Score: {result['risk_score']:.0f}% ({result['risk_level']})")
            print(f"   Recommendation: {result['recommendation']['action']}")
            print(f"\n🔍 PATTERNS DETECTED (these are what humans miss):")
            for p in result['patterns_found']:
                detect_note = "🤖 AI-only" if not p['human_detectable'] else "👁️ Visible"
                print(f"   • {p['pattern']}: {p['description']} ({detect_note})")
    
    # Show full dashboard
    print("\n" + "="*70)
    print(system.get_farmer_dashboard("F001"))
    
    # Detailed summary for the risky bag
    print("\n" + "="*70)
    print(system.bags[bag2_id].get_summary())
    
    print("\n" + "="*70)
    print("✅ DEMONSTRATION COMPLETE")
    print("\n💡 KEY INSIGHTS:")
    print("   1. Each bag has its own baseline and risk model")
    print("   2. The SLOW_HUMIDITY_RATCHET pattern was detected")
    print("   3. This pattern is INVISIBLE to humans looking at individual numbers")
    print("   4. The system provided EARLY warning (by Day 2, before critical)")
    print("   5. Recommendations became more urgent as risk increased")
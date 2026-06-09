"""
MAZAO GUARD - Professional Dashboard with AI Trend Analysis
Complete farmer interface with username/password authentication, bag management, and time-series trend detection
"""

import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import json
import time

st.set_page_config(
    page_title="Mazao Guard - Aflatoxin Risk Monitor",
    page_icon="🌽",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_URL = "http://localhost:8000"
REQUEST_TIMEOUT = 15

# Session state initialization
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'selected_bag' not in st.session_state:
    st.session_state.selected_bag = None
if 'show_reading_form' not in st.session_state:
    st.session_state.show_reading_form = False
if 'current_bag' not in st.session_state:
    st.session_state.current_bag = None
if 'retry_count' not in st.session_state:
    st.session_state.retry_count = 0


def api_request(method, endpoint, data=None, max_retries=2):
    """Make API request with retry logic"""
    url = f"{API_URL}{endpoint}"
    
    for attempt in range(max_retries):
        try:
            if method == "GET":
                response = requests.get(url, timeout=REQUEST_TIMEOUT)
            else:
                response = requests.post(url, data=data, timeout=REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                return response.json()
            else:
                if attempt == max_retries - 1:
                    st.error(f"API Error: {response.status_code}")
                    return None
        except requests.exceptions.ConnectionError:
            if attempt == max_retries - 1:
                st.error("Cannot connect to backend. Make sure it's running.")
                return None
            time.sleep(1)
        except Exception as e:
            if attempt == max_retries - 1:
                st.error(f"Error: {str(e)}")
                return None
            time.sleep(1)
    
    return None


def login_user(username, password):
    """Login user"""
    return api_request("POST", "/auth/login", {"username": username, "password": password})


def register_user(username, password, phone, email, pref, region):
    """Register new user"""
    data = {
        "username": username,
        "password": password,
        "notification_preference": pref,
        "region": region
    }
    if phone:
        data["phone_number"] = phone
    if email:
        data["email"] = email
    return api_request("POST", "/auth/register", data)


def get_dashboard_data(username):
    """Get dashboard data"""
    return api_request("GET", f"/dashboard/{username}")


def create_bag(username, bag_name, location_notes, maize_variety):
    """Create new bag"""
    data = {
        "username": username,
        "bag_name": bag_name,
        "location_notes": location_notes,
        "maize_variety": maize_variety
    }
    return api_request("POST", "/bags/create", data)


def add_reading(username, bag_name, temp, hum, co2):
    """Add reading"""
    data = {
        "username": username,
        "bag_name": bag_name,
        "temperature": temp,
        "humidity": hum,
        "co2": co2
    }
    return api_request("POST", "/readings/add", data)


def get_reading_history(username, bag_name):
    """Get reading history"""
    return api_request("GET", f"/readings/{username}/{bag_name}")


def main():
    # Header
    st.markdown("""
    <div style='background: linear-gradient(135deg, #1a5d2a 0%, #0d3b1a 100%); padding: 2rem; border-radius: 10px; margin-bottom: 2rem;'>
        <h1 style='color: white; margin: 0;'>🌽 Mazao Guard</h1>
        <p style='color: #a8e6a8; margin: 0;'>AI-Powered Aflatoxin Early Warning System</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("### 👨‍🌾 Farmer Portal")
        
        if not st.session_state.logged_in:
            tab1, tab2 = st.tabs(["🔓 Login", "📝 Register"])
            
            with tab1:
                st.markdown("#### Login")
                login_username = st.text_input("Username", key="login_username")
                login_password = st.text_input("Password", type="password", key="login_password")
                
                if st.button("Login", width='stretch'):
                    if login_username and login_password:
                        with st.spinner("Logging in..."):
                            result = login_user(login_username, login_password)
                            if result and result.get('success'):
                                st.session_state.logged_in = True
                                st.session_state.username = login_username
                                st.success(f"Welcome {login_username}!")
                                st.rerun()
                            else:
                                error_msg = result.get('message', 'Login failed') if result else 'Connection failed'
                                st.error(error_msg)
                    else:
                        st.warning("Enter username and password")
            
            with tab2:
                st.markdown("#### Register")
                reg_username = st.text_input("Username*", key="reg_username")
                reg_password = st.text_input("Password*", type="password", key="reg_password")
                reg_confirm = st.text_input("Confirm Password*", type="password", key="reg_confirm")
                reg_phone = st.text_input("Phone (+254...)", key="reg_phone")
                reg_email = st.text_input("Email", key="reg_email")
                reg_pref = st.selectbox("Notifications", ["sms", "email", "both"], key="reg_pref")
                reg_region = st.selectbox("Region", ["Nairobi", "Kisumu", "Uasin Gishu", "Machakos", "Trans Nzoia", "Other"], key="reg_region")
                
                if st.button("Register", width='stretch'):
                    if not reg_username or not reg_password:
                        st.warning("Username and password required")
                    elif reg_password != reg_confirm:
                        st.error("Passwords don't match")
                    elif len(reg_password) < 6:
                        st.error("Password must be at least 6 characters")
                    else:
                        with st.spinner("Creating account..."):
                            result = register_user(reg_username, reg_password, reg_phone, reg_email, reg_pref, reg_region)
                            if result and result.get('success'):
                                st.success("Registration successful! Please login.")
                            else:
                                error_msg = result.get('message', 'Registration failed') if result else 'Connection failed'
                                st.error(error_msg)
        else:
            st.success(f"✅ Logged in as: **{st.session_state.username}**")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Refresh", width='stretch'):
                    st.rerun()
            with col2:
                if st.button("🚪 Logout", width='stretch'):
                    st.session_state.logged_in = False
                    st.session_state.username = None
                    st.rerun()
    
    # Main content when logged in
    if st.session_state.logged_in:
        st.markdown(f"## Welcome, {st.session_state.username}!")
        
        # Fetch dashboard data
        with st.spinner("Loading your data..."):
            dashboard = get_dashboard_data(st.session_state.username)
        
        if dashboard and dashboard.get('success'):
            bags = dashboard.get('bags', [])
            risk_summary = dashboard.get('risk_summary', {})
            
            # Summary metrics
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("📦 Total Bags", dashboard.get('total_bags', 0))
            with col2:
                st.metric("🟢 Low", risk_summary.get('LOW', 0))
            with col3:
                st.metric("🟡 Medium", risk_summary.get('MEDIUM', 0))
            with col4:
                st.metric("🟠 High", risk_summary.get('HIGH', 0))
            with col5:
                st.metric("🔴 Critical", risk_summary.get('CRITICAL', 0))
            
            st.divider()
            
            # Create tabs
            tabs = st.tabs(["📦 My Bags", "➕ Create New Bag", "📈 Risk Analysis", "📊 Trend Analysis"])
            
            # ========== TAB 1: MY BAGS ==========
            with tabs[0]:
                if not bags:
                    st.info("📭 No bags yet. Create your first bag in the 'Create New Bag' tab.")
                else:
                    for bag in bags:
                        with st.expander(f"📦 {bag.get('name', 'Unknown')}", expanded=True):
                            col1, col2 = st.columns([2, 1])
                            
                            with col1:
                                risk_score = bag.get('latest_risk_score')
                                risk_level = bag.get('latest_risk_level', 'NO_DATA')
                                
                                if risk_score is not None:
                                    if risk_level == 'LOW':
                                        color = "#10b981"
                                        emoji = "🟢"
                                    elif risk_level == 'MEDIUM':
                                        color = "#f59e0b"
                                        emoji = "🟡"
                                    elif risk_level == 'HIGH':
                                        color = "#ef4444"
                                        emoji = "🟠"
                                    else:
                                        color = "#7f1d1d"
                                        emoji = "🔴"
                                    
                                    st.markdown(f"### {emoji} Risk Score: {risk_score:.0f}%")
                                    
                                    # Simple progress bar (faster than Plotly)
                                    st.progress(risk_score / 100)
                                    st.caption(f"Risk Level: {risk_level}")
                                    
                                    patterns = bag.get('detected_patterns', [])
                                    if patterns:
                                        st.markdown("**🔍 Detected:**")
                                        for p in patterns[:2]:
                                            st.caption(f"• {p.get('description', 'Unknown pattern')}")
                                    
                                    recommendation = bag.get('recommendation')
                                    if recommendation:
                                        st.info(f"💡 {recommendation[:150]}")
                                else:
                                    st.caption("📭 No readings yet")
                                
                                st.caption(f"📊 {bag.get('readings_count', 0)} readings")
                            
                            with col2:
                                st.markdown("**📝 Add Reading**")
                                temp = st.number_input("Temp (°C)", 0.0, 50.0, 25.0, 0.5, key=f"temp_{bag.get('bag_id', bag.get('name'))}")
                                hum = st.number_input("Humidity (%)", 0.0, 100.0, 60.0, 1.0, key=f"hum_{bag.get('bag_id', bag.get('name'))}")
                                co2 = st.number_input("CO₂ (ppm)", 300, 2000, 450, 10, key=f"co2_{bag.get('bag_id', bag.get('name'))}")
                                
                                if st.button("💾 Save", width='stretch', key=f"save_{bag.get('bag_id', bag.get('name'))}"):
                                    with st.spinner("Analyzing..."):
                                        result = add_reading(
                                            st.session_state.username,
                                            bag.get('name'),
                                            temp, hum, co2
                                        )
                                        if result and result.get('success'):
                                            rd = result.get('reading', {})
                                            st.success(f"✅ Saved! Risk: {rd.get('risk_level', 'UNKNOWN')} ({rd.get('risk_score', 0):.0f}%)")
                                            time.sleep(1)
                                            st.rerun()
                                        else:
                                            error_msg = result.get('message', 'Failed') if result else 'Connection error'
                                            st.error(f"Failed: {error_msg}")
            
            # ========== TAB 2: CREATE NEW BAG ==========
            with tabs[1]:
                st.markdown("### ➕ Create New Bag")
                
                col1, col2 = st.columns(2)
                with col1:
                    new_bag_name = st.text_input("Bag Name", placeholder="e.g., North Corner")
                with col2:
                    maize_variety = st.selectbox("Maize Variety", ["Local", "H614", "KDV1", "Other"])
                
                location_notes = st.text_area("Location Notes (optional)", placeholder="e.g., Top of stack")
                
                if st.button("🌾 Create Bag", width='stretch'):
                    if new_bag_name:
                        with st.spinner("Creating bag..."):
                            result = create_bag(
                                st.session_state.username,
                                new_bag_name,
                                location_notes,
                                maize_variety
                            )
                            if result and result.get('success'):
                                st.success(f"✅ Bag '{new_bag_name}' created!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                error_msg = result.get('message', 'Failed') if result else 'Connection error'
                                st.error(f"Failed: {error_msg}")
                    else:
                        st.warning("Enter a bag name")
            
            # ========== TAB 3: RISK ANALYSIS ==========
            with tabs[2]:
                st.markdown("### 📊 Risk Analysis")
                
                if bags:
                    chart_data = []
                    for bag in bags:
                        if bag.get('latest_risk_score') is not None:
                            chart_data.append({
                                'Bag': bag.get('name', 'Unknown'),
                                'Risk Score': bag.get('latest_risk_score', 0),
                                'Risk Level': bag.get('latest_risk_level', 'UNKNOWN'),
                                'Readings': bag.get('readings_count', 0)
                            })
                    
                    if chart_data:
                        df = pd.DataFrame(chart_data)
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            fig = px.bar(df, x='Bag', y='Risk Score', color='Risk Level',
                                        title='Risk Score by Bag',
                                        color_discrete_map={'LOW': '#10b981', 'MEDIUM': '#f59e0b',
                                                           'HIGH': '#ef4444', 'CRITICAL': '#7f1d1d'})
                            st.plotly_chart(fig, use_container_width=True)
                        
                        with col2:
                            fig = px.pie(df, values='Readings', names='Bag', title='Readings Distribution')
                            st.plotly_chart(fig, use_container_width=True)
                        
                        st.markdown("---")
                        st.markdown("### 🧠 How AI Detects Risk")
                        st.markdown("""
                        | Pattern | What It Means | Human Detectable? |
                        |---------|---------------|-------------------|
                        | 🌊 Slow Humidity Ratchet | 0.2%+ increase per reading | ❌ No |
                        | 💨 CO₂ Climb | Rising CO₂ indicates mold activity | ❌ No |
                        | 🔥 Danger Zone | >75% humidity + >28°C | ✅ Yes |
                        | 📊 High Volatility | Rapid humidity fluctuations | ✅ Yes |
                        """)
                    else:
                        st.info("📊 Add readings to see analytics")
                else:
                    st.info("📭 Create bags to see analytics")
            
            # ========== TAB 4: PROFESSIONAL TREND ANALYSIS (USING ML ENGINE RESULTS) ==========
            with tabs[3]:
                st.markdown("### 📈 Trend Analysis - Powered by ML Engine")
                st.caption("The AI (ml_engine.py) analyzes time-series data to detect dangerous patterns")
                
                if bags:
                    bag_names = [bag.get('name', 'Unknown') for bag in bags]
                    selected_bag = st.selectbox("Select Bag for Analysis", bag_names, key="history_bag")
                    
                    if selected_bag:
                        with st.spinner("Loading ML engine analysis..."):
                            history = get_reading_history(st.session_state.username, selected_bag)
                        
                        if history and history.get('success'):
                            readings = history.get('readings', [])
                            
                            if len(readings) >= 2:
                                # Convert to DataFrame with proper datetime
                                df = pd.DataFrame(readings)
                                df['timestamp'] = pd.to_datetime(df['timestamp'])
                                df = df.sort_values('timestamp')
                                
                                # ===== PROFESSIONAL TIME-SERIES CHART =====
                                st.markdown("#### 📊 Time-Series Trend Chart")
                                
                                # Create figure with dual y-axis
                                fig = go.Figure()
                                
                                # Risk score line (primary axis) - THIS COMES FROM ML ENGINE
                                fig.add_trace(go.Scatter(
                                    x=df['timestamp'],
                                    y=df['risk_score'],
                                    name='Risk Score (%) - ML Engine',
                                    line=dict(color='#ef4444', width=3),
                                    fill='tozeroy',
                                    fillcolor='rgba(239, 68, 68, 0.1)',
                                    hovertemplate='<b>%{x|%b %d, %H:%M}</b><br>Risk: %{y:.0f}%<extra></extra>'
                                ))
                                
                                # Temperature line (secondary axis)
                                fig.add_trace(go.Scatter(
                                    x=df['timestamp'],
                                    y=df['temperature'],
                                    name='Temperature (°C)',
                                    line=dict(color='#f59e0b', width=2, dash='dot'),
                                    yaxis='y2',
                                    hovertemplate='<b>%{x|%b %d, %H:%M}</b><br>Temp: %{y:.1f}°C<extra></extra>'
                                ))
                                
                                # Humidity line (secondary axis)
                                fig.add_trace(go.Scatter(
                                    x=df['timestamp'],
                                    y=df['humidity'],
                                    name='Humidity (%)',
                                    line=dict(color='#10b981', width=2, dash='dot'),
                                    yaxis='y2',
                                    hovertemplate='<b>%{x|%b %d, %H:%M}</b><br>Humidity: %{y:.0f}%<extra></extra>'
                                ))
                                
                                # Danger threshold lines
                                fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5,
                                              annotation_text="⚠️ Danger Zone (70%)", annotation_position="top right")
                                fig.add_hline(y=50, line_dash="dash", line_color="orange", opacity=0.3,
                                              annotation_text="Warning (50%)", annotation_position="bottom right")
                                
                                # Layout
                                fig.update_layout(
                                    title=dict(text=f"<b>ML Engine Trend Analysis: {selected_bag}</b>", x=0.5),
                                    xaxis=dict(
                                        title="Date & Time",
                                        showgrid=True,
                                        gridcolor='#e5e7eb',
                                        tickformat='%b %d, %H:%M',
                                        rangeslider=dict(visible=True, thickness=0.05),
                                        rangeselector=dict(
                                            buttons=[
                                                dict(count=1, label="1d", step="day", stepmode="backward"),
                                                dict(count=3, label="3d", step="day", stepmode="backward"),
                                                dict(count=7, label="1w", step="day", stepmode="backward"),
                                                dict(count=14, label="2w", step="day", stepmode="backward"),
                                                dict(step="all", label="All")
                                            ]
                                        )
                                    ),
                                    yaxis=dict(title="Risk Score (%)", range=[0, 100]),
                                    yaxis2=dict(title="Temperature (°C) / Humidity (%)", overlaying='y', side='right', range=[0, 100]),
                                    hovermode='x unified',
                                    height=500,
                                    template='plotly_white'
                                )
                                
                                st.plotly_chart(fig, use_container_width=True)
                                
                                # ===== DISPLAY ML ENGINE'S STORED PATTERNS =====
                                st.markdown("---")
                                st.markdown("#### 🧠 ML Engine Detected Patterns (from saved readings)")
                                
                                # Collect all unique patterns from readings
                                all_patterns = []
                                for r in readings:
                                    patterns = r.get('detected_patterns', [])
                                    if patterns:
                                        if isinstance(patterns, str):
                                            try:
                                                patterns = json.loads(patterns)
                                            except:
                                                patterns = []
                                        for p in patterns:
                                            if p not in all_patterns:
                                                all_patterns.append(p)
                                
                                # Display patterns detected by ML engine
                                if all_patterns:
                                    for p in all_patterns:
                                        pattern_name = p.get('pattern', 'Unknown').replace('_', ' ').title()
                                        st.info(f"🔍 **{pattern_name}** - {p.get('description', 'No description')}")
                                else:
                                    st.success("✅ No dangerous patterns detected by ML engine")
                                
                                # ===== LATEST ML ENGINE RECOMMENDATION =====
                                st.markdown("---")
                                st.markdown("#### 💡 ML Engine Recommendation")
                                
                                latest = readings[-1]
                                recommendation = latest.get('recommendation', 'No recommendation available')
                                
                                risk_level = latest.get('risk_level', 'UNKNOWN')
                                if risk_level == 'CRITICAL':
                                    st.error(f"🔥 {recommendation}")
                                elif risk_level == 'HIGH':
                                    st.error(f"⚠️ {recommendation}")
                                elif risk_level == 'MEDIUM':
                                    st.warning(f"📊 {recommendation}")
                                else:
                                    st.success(f"✅ {recommendation}")
                                
                                # ===== DATA TABLE =====
                                st.markdown("---")
                                st.markdown("#### 📋 Detailed Reading History (with ML Results)")
                                
                                # Create display DataFrame
                                display_df = pd.DataFrame([{
                                    'Date/Time': r.get('timestamp', '')[:19] if r.get('timestamp') else 'Unknown',
                                    'Temp (°C)': r.get('temperature', 0),
                                    'Humidity (%)': r.get('humidity', 0),
                                    'CO₂ (ppm)': r.get('co2', 'N/A'),
                                    'Risk Score (%)': r.get('risk_score', 0),
                                    'Risk Level': r.get('risk_level', 'UNKNOWN'),
                                    'ML Recommendation': r.get('recommendation', '')[:60]
                                } for r in readings])
                                
                                st.dataframe(display_df, use_container_width=True, height=300)
                                
                                # Download button
                                csv = display_df.to_csv(index=False)
                                st.download_button(
                                    label="📥 Download Data as CSV",
                                    data=csv,
                                    file_name=f"{selected_bag}_ml_analysis.csv",
                                    mime="text/csv"
                                )
                                
                            else:
                                st.info(f"📭 Need at least 2 readings. Currently have {len(readings)} reading(s).")
                                st.caption("Add more readings for ML engine to detect patterns.")
                        else:
                            st.error("Failed to load reading history")
                else:
                    st.info("📭 Create a bag and add readings for ML engine analysis")
        
        elif dashboard is None:
            st.error("Cannot connect to backend. Make sure the server is running.")
            st.info("Run: python main.py in a separate terminal")
        else:
            st.error(f"Failed to load data: {dashboard.get('message', 'Unknown error') if dashboard else 'No response'}")
    
    else:
        # Welcome screen
        st.markdown("""
        <div style='text-align: center; padding: 3rem;'>
            <h2>🌽 Protect Your Maize from Aflatoxin</h2>
            <p style='font-size: 1.2rem;'>Mazao Guard uses AI to detect dangerous storage conditions before they become a problem.</p>
            <br>
            <p><strong>Login or Register using the sidebar to get started.</strong></p>
        </div>
        """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
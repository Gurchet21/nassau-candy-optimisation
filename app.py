import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import re
from io import StringIO
import warnings

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────
# PAGE CONFIGURATION
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🏭 Factory & Shipping Optimization",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────────────────
# DATA LOADING & AUTO-CLEANING
# ─────────────────────────────────────────────────────────────
@st.cache_data
def load_and_clean_data():
    filename = "Nassau Candy Distributor (1).csv"
    try:
        with open(filename, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        st.error(f"📁 File not found: `{filename}`\nEnsure the CSV is in the same folder as app.py.")
        return None

    st.info("🔧 Auto-fixing concatenated CSV records...")

    # 🔑 ROBUST REGEX: Splits merged Cost + Row ID before US-/CA- prefixes
    # Handles both decimal costs (e.g., 2.282 -> 2.28\n2) and integer costs (e.g., 63494 -> 6\n3494)
    raw = re.sub(r'(\d+\.\d+)(\d+),(US-\d{4}|CA-\d{4})', r'\1\n\2,\3', raw)
    raw = re.sub(r'(\d+)(\d{3,4}),(US-\d{4}|CA-\d{4})', r'\1\n\2,\3', raw)

    # Define correct header
    header = "Row ID,Order ID,Order Date,Ship Date,Ship Mode,Customer ID,Country/Region,City,State/Province,Postal Code,Division,Region,Product ID,Product Name,Sales,Units,Gross Profit,Cost"
    
    # Remove duplicate headers & clean whitespace
    lines = [line.strip() for line in raw.splitlines() if line.strip() and line != header]
    clean_csv = header + "\n" + "\n".join(lines)

    try:
        df = pd.read_csv(StringIO(clean_csv))
    except Exception as e:
        st.error(f"❌ CSV parsing failed: {e}")
        return None

    df.columns = df.columns.str.strip()
    st.success(f"📊 Parsed {len(df)} rows, {len(df.columns)} columns")

    # 🔢 Force numeric types
    for col in ['Sales', 'Units', 'Cost', 'Gross Profit']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 📅 Parse dates
    for col in ['Order Date', 'Ship Date']:
        df[col] = pd.to_datetime(df[col], format='%d-%m-%Y', errors='coerce')

    # 🧹 Clean & validate
    df = df.dropna(subset=['Sales', 'Gross Profit', 'Units', 'Order Date', 'Product Name', 'Region'])
    df = df[(df['Sales'] > 0) & (df['Units'] > 0)]
    
    # Remove accidental numeric-only product names
    df = df[~df['Product Name'].astype(str).str.match(r'^\d+\.?\d*$')]
    
    if df.empty:
        st.error("⚠️ Dataset is empty after cleaning. Check CSV format or file name.")
        return None

    st.success(f"✅ Ready! {len(df)} valid rows loaded.")

    # 📊 Calculated metrics
    df['Gross Margin (%)'] = np.where(df['Sales'] > 0, (df['Gross Profit'] / df['Sales']) * 100, 0)
    df['Profit per Unit'] = df['Gross Profit'] / df['Units']
    df['Shipping Cost Estimate'] = df['Units'] * 0.5
    df['Delivery Days'] = (df['Ship Date'] - df['Order Date']).dt.days.clip(lower=1, upper=365)
    
    for col in ['Division', 'Region', 'Product Name', 'Ship Mode', 'City', 'State/Province']:
        df[col] = df[col].astype(str).str.strip().str.title()

    return df

# ─────────────────────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────────────────────
st.title("🏭 Factory Reallocation & Shipping Optimization")

df_raw = load_and_clean_data()

if df_raw is None or df_raw.empty:
    st.stop()

# SIDEBAR FILTERS
st.sidebar.header("🎛️ Optimization Filters")
min_date = df_raw['Order Date'].min().date()
max_date = df_raw['Order Date'].max().date()
selected_date = st.sidebar.date_input("📅 Order Date Range", value=[min_date, max_date], min_value=min_date, max_value=max_date)
start_date, end_date = (pd.Timestamp(selected_date[0]), pd.Timestamp(selected_date[1])) if len(selected_date)==2 else (pd.Timestamp(min_date), pd.Timestamp(max_date))

regions = sorted(df_raw['Region'].unique())
selected_regions = st.sidebar.multiselect("🌍 Region(s)", regions, default=regions)
divisions = sorted(df_raw['Division'].unique())
selected_divisions = st.sidebar.multiselect("🏷️ Division(s)", divisions, default=divisions)
ship_modes = sorted(df_raw['Ship Mode'].unique())
selected_ship_modes = st.sidebar.multiselect("🚚 Ship Mode(s)", ship_modes, default=ship_modes)

mask = (df_raw['Order Date'].between(start_date, end_date) & 
        df_raw['Region'].isin(selected_regions) & 
        df_raw['Division'].isin(selected_divisions) & 
        df_raw['Ship Mode'].isin(selected_ship_modes))
df = df_raw[mask].copy()

if df.empty:
    st.warning("⚠️ No data matches filters. Try widening your selections.")
    st.stop()

# KPIs
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("📦 Total Orders", f"{len(df):,}")
c2.metric("💰 Total Revenue", f"${df['Sales'].sum():,.0f}")
c3.metric("📈 Total Profit", f"${df['Gross Profit'].sum():,.0f}")
c4.metric("🚚 Avg Delivery", f"{df['Delivery Days'].mean():.1f} days")
c5.metric("📊 Avg Margin", f"{df['Gross Margin (%)'].mean():.1f}%")
st.divider()

# TABS
tab_geo, tab_ship, tab_factory, tab_cost, tab_rec = st.tabs([
    "🗺️ Geographic Demand", 
    "🚚 Shipping Optimization", 
    "🏭 Factory Location", 
    "💰 Cost-Benefit", 
    "✅ Recommendations"
])

with tab_geo:
    st.subheader("🗺️ Regional Demand & Delivery Performance")
    reg = df.groupby('Region').agg(Sales=('Sales','sum'), Orders=('Order ID','count'), Days=('Delivery Days','mean')).reset_index()
    c1,c2 = st.columns(2)
    c1.plotly_chart(px.bar(reg.sort_values('Sales',ascending=False), x='Sales', y='Region', orientation='h', color='Sales', color_continuous_scale='Blues'), use_container_width=True)
    c2.plotly_chart(px.bar(reg.sort_values('Days',ascending=False), x='Days', y='Region', orientation='h', color='Days', color_continuous_scale='Reds'), use_container_width=True)

with tab_ship:
    st.subheader("🚚 Shipping Mode Performance")
    ship = df.groupby('Ship Mode').agg(Sales=('Sales','sum'), Profit=('Gross Profit','sum'), Units=('Units','sum'), Days=('Delivery Days','mean'), Orders=('Order ID','count')).reset_index()
    ship['Net_Profit'] = ship['Profit'] - (ship['Units'] * 0.5)
    ship['Profit_per_Order'] = ship['Net_Profit'] / ship['Orders']
    c1,c2 = st.columns(2)
    c1.plotly_chart(px.bar(ship.sort_values('Net_Profit',ascending=False), x='Net_Profit', y='Ship Mode', orientation='h', color='Net_Profit', color_continuous_scale='Greens'), use_container_width=True)
    c2.plotly_chart(px.scatter(ship, x='Days', y='Units', size='Orders', color='Ship Mode'), use_container_width=True)
    best = ship.loc[ship['Profit_per_Order'].idxmax()]
    st.success(f"💰 Most Profitable: {best['Ship Mode']} | Avg Profit/Order: ${best['Profit_per_Order']:.2f}")

with tab_factory:
    st.subheader("🏭 Optimal Factory Placement")
    state = df.groupby(['State/Province','Region']).agg(Sales=('Sales','sum'), Units=('Units','sum'), Orders=('Order ID','count'), Days=('Delivery Days','mean')).reset_index()
    state['Demand_Score'] = (state['Sales'].rank(pct=True)*0.4 + state['Units'].rank(pct=True)*0.3 + state['Orders'].rank(pct=True)*0.3)*100
    state['Priority'] = state['Demand_Score']*0.6 + state['Days'].rank(pct=True)*40
    top5 = state.nlargest(5, 'Priority')[['State/Province','Region','Demand_Score','Days','Priority']]
    st.dataframe(top5.style.format({'Demand_Score':'{:.1f}','Days':'{:.1f}','Priority':'{:.1f}'}).background_gradient(subset=['Priority'], cmap='YlOrRd'), use_container_width=True)
    st.info("💡 Priority = (Demand × 60%) + (Delivery Time Rank × 40%). Higher = better factory candidate.")

with tab_cost:
    st.subheader("💰 Cost-Benefit Analysis")
    curr_ship = df['Units'].sum() * 0.5
    opt_ship = curr_ship * 0.7
    savings = curr_ship - opt_ship
    c1,c2,c3 = st.columns(3)
    c1.metric("📦 Current Shipping", f"${curr_ship:,.0f}")
    c2.metric("🎯 Optimized Shipping", f"${opt_ship:,.0f}")
    # ✅ FIXED: Changed success() to metric() to match KPI style
    c3.metric("💰 Potential Savings", f"${savings:,.0f}") 

with tab_rec:
    st.subheader("✅ Prioritized Action Plan")
    recs = pd.DataFrame([
        {"Priority":"🔴 High","Action":"Shift orders to most profitable shipping mode","Impact":"~15% profit increase","Timeline":"1-2 mo","Owner":"Logistics"},
        {"Priority":"🟡 Medium","Action":"Feasibility study for top-ranked factory location","Impact":"30% shipping reduction","Timeline":"6-12 mo","Owner":"Operations"},
        {"Priority":"🟢 Low","Action":"Increase inventory in highest-revenue region","Impact":"Reduce stockouts","Timeline":"Immediate","Owner":"Supply Chain"}
    ])
    st.dataframe(recs.style.applymap(lambda x: 'background:#FEE2E2' if 'High' in x else ('background:#FEF3C7' if 'Med' in x else 'background:#D1FAE5'), subset=['Priority']), hide_index=True, use_container_width=True)

st.divider()
st.caption("🔄 Data refreshed on load • Adjust filters to recalculate")
import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# Configuración de la página
st.set_page_config(
    page_title="TCG Collector Live Tracker",
    page_icon="📦",
    layout="centered"
)

# Estilos CSS estilo Dashboard / Collector App
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3em; font-weight: bold; }
    
    /* Contenedor de Tarjeta */
    .collector-card {
        background-color: #1e222a;
        border: 1px solid #2d3139;
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 14px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
    }
    
    .product-img {
        width: 75px;
        height: 75px;
        object-fit: contain;
        background-color: #14171d;
        border-radius: 8px;
        padding: 4px;
        flex-shrink: 0;
    }
    
    .card-content {
        flex-grow: 1;
    }
    
    .card-price-container {
        text-align: right;
        flex-shrink: 0;
    }
    
    /* Badges de tendencia */
    .badge-up {
        background-color: rgba(0, 230, 118, 0.15);
        color: #00e676;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 0.82em;
    }
    .badge-down {
        background-color: rgba(255, 82, 82, 0.15);
        color: #ff5252;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 0.82em;
    }
    .badge-flat {
        background-color: rgba(255, 255, 255, 0.1);
        color: #aaa;
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.82em;
    }
    
    .card-price {
        font-size: 1.15em;
        font-weight: bold;
        color: #ffffff;
    }
    .card-title {
        font-size: 0.95em;
        font-weight: 600;
        color: #f0f2f6;
        margin-bottom: 4px;
        line-height: 1.2;
    }
    .card-subtitle {
        font-size: 0.78em;
        color: #8b949e;
        margin-bottom: 6px;
    }
    </style>
""", unsafe_allow_html=True)

DEFAULT_IMG = "https://tcgplayer-cdn.tcgplayer.com/product/284000_200w.jpg"

# 1. Obtener Tipo de Cambio USD -> MXN
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return res.json().get("rates", {}).get("MXN", 18.0)
    except Exception:
        pass
    return 18.0

# 2. Cargar TODAS las colecciones registradas
@st.cache_data(ttl=3600, show_spinner=False)
def get_tcg_groups():
    url = "https://tcgcsv.com/tcgplayer/3/groups"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            df = pd.DataFrame(res.json().get("results", []))
            return df.sort_values(by='name', ascending=False) # Las más recientes primero
    except Exception:
        pass
    return pd.DataFrame()

# 3. FILTRO MAESTRO ANTI-CARTAS (Garantiza 100% producto sellado)
def is_strictly_sealed(name):
    n_lower = str(name).lower()
    
    # LISTA NEGRA ABSOLUTA: Si contieneCualquiera de estos términos, SE DESCARTA INMEDIATAMENTE
    forbidden_terms = [
        'pattern', 'poke ball', 'poké ball', 'holo', 'reverse', 'secret rare', 
        'illustration rare', 'full art', 'alt art', 'promo card', 'single', 
        'energy', 'cube', 'trainer', 'supporter', 'item', 'stadium', 'code card',
        'ex ', 'gx ', 'vmax', 'vstar', 'v-union', 'radiant', 'amazing rare'
    ]
    for term in forbidden_terms:
        if term in n_lower:
            return False
            
    # REGLA DE FORMATO NUMÉRICO: Bloquear nombres que sean claramente cartas con números/sets (ej. "001/198")
    if '/' in n_lower:
        return False

    # LISTA BLANCA OBLIGATORIA: El nombre DEBE contener al menos una palabra clave de producto sellado físico
    valid_sealed_keywords = [
        'booster box', 'elite trainer box', 'etb', 'booster bundle', 
        'collection box', 'mini tin', 'tin', 'blister', 'display', 'case',
        'ultra-premium', 'ultra premium', 'upc', 'premium collection', 
        'box set', 'collector chest', 'mini portfolio', 'booster pack', 
        'binder collection', 'three pack', '3-pack', 'build & battle', 
        'build and battle', 'checklane', 'sleeved booster', 'deck', 'fates tins', 
        'checklane blister', 'build & battle stadium', 'poster collection'
    ]
    
    has_valid_container = any(keyword in n_lower for keyword in valid_sealed_keywords)
    if not has_valid_container:
        return False

    return True

# 4. Cargar productos sellados de un grupo específico
@st.cache_data(ttl=900, show_spinner=False)
def get_sealed_boxes_only(group_id):
    headers = {"User-Agent": "Mozilla/5.0"}
    prod_url = f"https://tcgcsv.com/tcgplayer/3/{group_id}/products"
    price_url = f"https://tcgcsv.com/tcgplayer/3/{group_id}/prices"
    
    try:
        p_res = requests.get(prod_url, headers=headers, timeout=10)
        pr_res = requests.get(price_url, headers=headers, timeout=10)
        
        if p_res.status_code == 200 and pr_res.status_code == 200:
            df_prod = pd.DataFrame(p_res.json().get("results", []))
            df_price = pd.DataFrame(pr_res.json().get("results", []))
            
            if not df_prod.empty and not df_price.empty:
                merged = pd.merge(df_prod, df_price, on="productId")
                
                df_sealed = merged[merged['cleanName'].apply(is_strictly_sealed)].copy()
                
                df_sealed['market_price'] = df_sealed['marketPrice'].fillna(0.0)
                df_sealed['low_price'] = df_sealed['lowPrice'].fillna(0.0)
                
                if 'imageUrl' not in df_sealed.columns:
                    df_sealed['imageUrl'] = DEFAULT_IMG
                else:
                    df_sealed['imageUrl'] = df_sealed['imageUrl'].fillna(DEFAULT_IMG)
                
                def calc_trend(row):
                    mp = row['market_price']
                    lp = row['low_price']
                    if mp > 0 and lp > 0:
                        diff = ((mp - lp) / lp) * 100
                        return round(diff, 1)
                    return 0.0
                
                df_sealed['trend_pct'] = df_sealed.apply(calc_trend, axis=1)
                # Filtramos precios válidos y descartamos anomalías de mercado extremas (> 400% o < -95%)
                df_sealed = df_sealed[(df_sealed['market_price'] > 0) & (df_sealed['trend_pct'].between(-95, 400))]
                return df_sealed
    except Exception:
        pass
    return pd.DataFrame()

# 5. Cargar dinámicamente las colecciones más populares recientes para la pestaña principal
@st.cache_data(ttl=1800, show_spinner=False)
def get_daily_market_highlights(df_groups):
    if df_groups.empty:
        return pd.DataFrame()
        
    # Tomamos las colecciones más recientes (primeras 25 del listado general de TCGPlayer)
    recent_groups = df_groups.head(25)
    
    all_items = []
    for _, group in recent_groups.iterrows():
        df_items = get_sealed_boxes_only(group['groupId'])
        if not df_items.empty:
            df_items['group_name'] = group['name']
            all_items.append(df_items)
            
    if all_items:
        return pd.concat(all_items, ignore_index=True)
    return pd.DataFrame()


# Cargar datos base
usd_mxn = get_exchange_rate()
df_groups = get_tcg_groups()

# HEADER Y MONEDA
st.title("📦 TCG Sealed Box Collector Tracker")

currency_mode = st.radio(
    "Moneda de visualización:", 
    ["USD ($)", f"MXN ($ - Tipo de cambio: ${usd_mxn:.2f})"], 
    horizontal=True
)
is_mxn = "MXN" in currency_mode
mult = usd_mxn if is_mxn else 1.0
symbol = "MXN $" if is_mxn else "$"

# PESTAÑAS PRINCIPALES
tab_home, tab_search = st.tabs(["🏠 Tendencias Diarias del Mercado", "🔍 Buscador por Colección"])

# ---------------------------------------------------------
# PESTAÑA 1: TENDENCIAS DIARIAS (Dinámica y Automática)
# ---------------------------------------------------------
with tab_home:
    current_date_str = datetime.now().strftime("%d de %B de %Y")
    st.subheader(f"🔥 Productos Sellados Más Populares — Actualizado al día")
    st.caption(f"📅 Fecha de análisis: {current_date_str}. Mostrando variaciones en tiempo real de cajas, ETBs y bundles.")
    
    st.markdown("---")
    
    with st.spinner("Analizando fluctuaciones diarias en colecciones populares..."):
        df_daily_market = get_daily_market_highlights(df_groups)
        
    if not df_daily_market.empty:
        col_up, col_down = st.columns(2)
        
        # --- COLUMNA 1: PRODUCTOS SELLADOS A LA ALZA ---
        with col_up:
            st.subheader("📈 Cajas a la Alza (+)")
            top_gainers = df_daily_market.sort_values(by='trend_pct', ascending=False).head(8)
            
            for _, item in top_gainers.iterrows():
                p_val = item['market_price'] * mult
                trend = item['trend_pct']
                img_url = item['imageUrl']
                sign = "+" if trend > 0 else ""
                
                st.markdown(f"""
                <div class="collector-card">
                    <img src="{img_url}" class="product-img" alt="product">
                    <div class="card-content">
                        <div class="card-title">{item['cleanName']}</div>
                        <div class="card-subtitle">📁 {item['group_name']}</div>
                        <div><span class="badge-up">▲ {sign}{trend}%</span></div>
                    </div>
                    <div class="card-price-container">
                        <div class="card-price">{symbol}{p_val:,.2f}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        # --- COLUMNA 2: PRODUCTOS SELLADOS A LA BAJA ---
        with col_down:
            st.subheader("📉 Cajas a la Baja (-)")
            top_losers = df_daily_market.sort_values(by='trend_pct', ascending=True).head(8)
            
            for _, item in top_losers.iterrows():
                p_val = item['market_price'] * mult
                trend = item['trend_pct']
                img_url = item['imageUrl']
                badge_class = "badge-down" if trend < 0 else "badge-flat"
                sign = "" if trend < 0 else "+"
                
                st.markdown(f"""
                <div class="collector-card">
                    <img src="{img_url}" class="product-img" alt="product">
                    <div class="card-content">
                        <div class="card-title">{item['cleanName']}</div>
                        <div class="card-subtitle">📁 {item['group_name']}</div>
                        <div><span class="{badge_class}">▼ {sign}{trend}%</span></div>
                    </div>
                    <div class="card-price-container">
                        <div class="card-price">{symbol}{p_val:,.2f}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.warning("No se pudieron cargar las tendencias del mercado en este momento.")

# ---------------------------------------------------------
# PESTAÑA 2: BUSCADOR POR COLECCIÓN
# ---------------------------------------------------------
with tab_search:
    st.subheader("🔍 Buscador de Producto Sellado por Colección")
    
    if not df_groups.empty:
        search_list_of_groups = ["📁 Selecciona una expansión..."] + df_groups['name'].tolist()
        
        selected_search_collection = st.selectbox(
            "Elige la colección:",
            search_list_of_groups,
            index=0,
            key="search_selectbox"
        )
        
        st.markdown("---")
        
        if selected_search_collection != "📁 Selecciona una expansión...":
            target_group = df_groups[df_groups['name'] == selected_search_collection].iloc[0]
            
            with st.spinner(f"Buscando cajas y productos sellados en {selected_search_collection}..."):
                df_search_items = get_sealed_boxes_only(target_group['groupId'])
                
                if not df_search_items.empty:
                    df_search_items = df_search_items.sort_values(by='market_price', ascending=False)
                    st.success(f"Se encontraron {len(df_search_items)} productos sellados legítimos:")
                    
                    for _, item in df_search_items.iterrows():
                        p_val = item['market_price'] * mult
                        trend = item['trend_pct']
                        img_url = item['imageUrl']
                        
                        if trend > 1.0:
                            badge = f"<span class='badge-up'>▲ +{trend}%</span>"
                        elif trend < -1.0:
                            badge = f"<span class='badge-down'>▼ {trend}%</span>"
                        else:
                            badge = f"<span class='badge-flat'>➔ {trend}%</span>"
                        
                        st.markdown(f"""
                        <div class="collector-card">
                            <img src="{img_url}" class="product-img" alt="product">
                            <div class="card-content">
                                <div class="card-title">{item['cleanName']}</div>
                                <div style="margin-top: 4px;">{badge}</div>
                            </div>
                            <div class="card-price-container">
                                <div class="card-price">{symbol}{p_val:,.2f}</div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.warning("No hay productos sellados registrados para esta colección específica.")
        else:
            st.info("💡 Selecciona una colección en el menú superior para ver su inventario sellado.")
    else:
        st.error("No se pudieron cargar las colecciones.")

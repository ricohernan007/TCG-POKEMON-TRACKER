import streamlit as st
import requests
import pandas as pd

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
            return df.sort_values(by='name')
    except Exception:
        pass
    return pd.DataFrame()

# 3. Cargar EXCLUSIVAMENTE CAJAS Y PRODUCTO SELLADO (Bloqueo absoluto de cartas, energías y cubos)
@st.cache_data(ttl=900, show_spinner=False)
def get_sealed_boxes_only(group_id):
    headers = {"User-Agent": "Mozilla/5.0"}
    prod_url = f"https://tcgcsv.com/tcgplayer/3/{group_id}/products"
    price_url = f"https://tcgcsv.com/tcgplayer/3/{group_id}/prices"
    
    try:
        p_res = requests.get(prod_url, headers=headers, timeout=12)
        pr_res = requests.get(price_url, headers=headers, timeout=12)
        
        if p_res.status_code == 200 and pr_res.status_code == 200:
            df_prod = pd.DataFrame(p_res.json().get("results", []))
            df_price = pd.DataFrame(pr_res.json().get("results", []))
            
            if not df_prod.empty and not df_price.empty:
                merged = pd.merge(df_prod, df_price, on="productId")
                
                def is_strictly_sealed(name):
                    n_lower = str(name).lower()
                    
                    # REGLA 0: Bloquear términos prohibidos de cartas individuales, energías o cartas de juego sueltas
                    forbidden_card_terms = [
                        'energy', 'cube', 'trainer', 'supporter', 'item card', 'stadium',
                        'code card', 'pattern', 'holo', 'reverse', 'secret', 'illustration', 
                        'full art', 'alt art', 'rare', 'promo card', 'single', 'ex ', 'gx ', 'vmax', 'vstar'
                    ]
                    for term in forbidden_card_terms:
                        if term in n_lower:
                            return False
                            
                    # REGLA 1: Bloquear si contiene numeraciones o diagonales típicas de cartas (ej. "01", "02", "01/198")
                    if any(char.isdigit() for char in n_lower) and not any(box_word in n_lower for box_word in ['box', 'pack', 'tin', 'etb', 'case', 'bundle', 'collection', 'deck', 'set', 'display']):
                        # Si tiene números pero no es una caja explícita, evaluamos si parece una carta numerada
                        if '/' in n_lower:
                            return False

                    # REGLA 2: LISTA BLANCA ESTRICTA DE CONTENEDORES SELLADOS FÍSICOS
                    valid_sealed_keywords = [
                        'booster box', 'elite trainer box', 'etb', 'booster bundle', 
                        'collection box', 'mini tin', 'tin', 'blister', 'display', 'case',
                        'ultra-premium', 'ultra premium', 'upc', 'premium collection', 
                        'box set', 'collector chest', 'mini portfolio', 'booster pack', 
                        'binder collection', 'poké ball', 'poke ball', 'three pack',
                        '3-pack', 'build & battle', 'build and battle', 'checklane', 
                        'sleeved booster', 'deck', 'fates tins', 'checklane blister'
                    ]
                    
                    has_valid_container = any(keyword in n_lower for keyword in valid_sealed_keywords)
                    if not has_valid_container:
                        return False

                    return True

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
                df_sealed = df_sealed[df_sealed['market_price'] > 0]
                return df_sealed
    except Exception:
        pass
    return pd.DataFrame()

# Cargar catálogo destacado inicial para el Home
@st.cache_data(ttl=1800, show_spinner=False)
def get_featured_market_data(df_groups):
    featured_keywords = ['151', 'Evolving Skies', 'Paldea', 'Crown Zenith', 'Obsidian', 'Prismatic', 'Stellar', 'Surging', 'Twilight']
    pattern = '|'.join(featured_keywords)
    
    featured_groups = df_groups[df_groups['name'].str.contains(pattern, case=False, na=False)].head(15)
    
    all_items = []
    for _, group in featured_groups.iterrows():
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

# PESTAÑAS PRINCIPALES DE LA APP
tab_home, tab_search = st.tabs(["🏠 Inicio / Tendencias de Cajas", "🔍 Buscador de Cajas por Colección"])

# ---------------------------------------------------------
# PESTAÑA 1: HOME CON FILTRO EXCLUSIVO DE CAJAS
# ---------------------------------------------------------
with tab_home:
    st.subheader("📊 Mercado de Cajas y Colecciones Selladas")
    
    if not df_groups.empty:
        list_of_groups = ["🔥 Mercado General Destacado"] + df_groups['name'].tolist()
        
        selected_collection_name = st.selectbox(
            "📁 Selecciona una Colección o Set:",
            list_of_groups,
            index=0,
            key="home_selectbox"
        )
        
        st.markdown("---")
        
        df_display_items = pd.DataFrame()
        
        if selected_collection_name == "🔥 Mercado General Destacado":
            with st.spinner("Cargando tendencias de cajas destacadas..."):
                df_display_items = get_featured_market_data(df_groups)
        else:
            selected_group = df_groups[df_groups['name'] == selected_collection_name].iloc[0]
            with st.spinner(f"Cargando cajas de {selected_collection_name}..."):
                df_items = get_sealed_boxes_only(selected_group['groupId'])
                if not df_items.empty:
                    df_items['group_name'] = selected_collection_name
                    df_display_items = df_items

        if not df_display_items.empty:
            col_up, col_down = st.columns(2)
            
            # --- COLUMNA 1: CAJAS A LA ALZA ---
            with col_up:
                st.subheader("🔥 Cajas a la Alza (+)")
                top_gainers = df_display_items.sort_values(by='trend_pct', ascending=False).head(10)
                
                gainers_filtered = top_gainers[top_gainers['trend_pct'] > 0]
                if gainers_filtered.empty:
                    gainers_filtered = top_gainers
                
                for _, item in gainers_filtered.iterrows():
                    p_val = item['market_price'] * mult
                    trend = item['trend_pct']
                    img_url = item['imageUrl']
                    
                    st.markdown(f"""
                    <div class="collector-card">
                        <img src="{img_url}" class="product-img" alt="product">
                        <div class="card-content">
                            <div class="card-title">{item['cleanName']}</div>
                            <div class="card-subtitle">📁 {item['group_name']}</div>
                            <div><span class="badge-up">▲ +{trend}%</span></div>
                        </div>
                        <div class="card-price-container">
                            <div class="card-price">{symbol}{p_val:,.2f}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # --- COLUMNA 2: CAJAS A LA BAJA ---
            with col_down:
                st.subheader("📉 Cajas a la Baja (-)")
                top_losers = df_display_items.sort_values(by='trend_pct', ascending=True).head(10)
                
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
            st.warning("No se encontraron cajas selladas registradas para esta selección.")
    else:
        st.error("No se pudieron cargar las colecciones del mercado.")

# ---------------------------------------------------------
# PESTAÑA 2: BUSCADOR POR COLECCIÓN
# ---------------------------------------------------------
with tab_search:
    st.subheader("🔍 Buscador de Cajas por Colección Específica")
    
    if not df_groups.empty:
        search_list_of_groups = ["📁 Selecciona una colección para explorar..."] + df_groups['name'].tolist()
        
        selected_search_collection = st.selectbox(
            "Elige la expansión o set:",
            search_list_of_groups,
            index=0,
            key="search_selectbox"
        )
        
        st.markdown("---")
        
        if selected_search_collection != "📁 Selecciona una colección para explorar...":
            target_group = df_groups[df_groups['name'] == selected_search_collection].iloc[0]
            
            with st.spinner(f"Buscando producto sellado en {selected_search_collection}..."):
                df_search_items = get_sealed_boxes_only(target_group['groupId'])
                
                if not df_search_items.empty:
                    df_search_items = df_search_items.sort_values(by='market_price', ascending=False)
                    st.success(f"Se encontraron {len(df_search_items)} productos sellados en esta colección:")
                    
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
            st.info("💡 Selecciona una colección en el menú desplegable superior para consultar su inventario sellado.")
    else:
        st.error("No se pudieron cargar las colecciones.")

import streamlit as st
import requests
import pandas as pd

st.set_page_config(
    page_title="TCG Live Market & Trend Tracker",
    page_icon="📦",
    layout="centered"
)

# Estilos visuales personalizados
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3em; font-weight: bold; }
    .product-row { 
        display: flex; 
        justify-content: space-between; 
        align-items: center; 
        padding: 12px 0; 
        border-bottom: 1px solid #2d3139; 
    }
    .price-tag { font-size: 1.1em; font-weight: bold; color: #ffffff; }
    .trend-up { color: #00e676; font-weight: bold; font-size: 0.9em; }
    .trend-down { color: #ff5252; font-weight: bold; font-size: 0.9em; }
    .trend-flat { color: #888888; font-size: 0.9em; }
    </style>
""", unsafe_allow_html=True)

# 1. Obtener Tipo de Cambio USD -> MXN en tiempo real
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

# 2. Cargar todas las expansiones de Pokémon TCG
@st.cache_data(ttl=3600, show_spinner=False)
def get_tcg_groups():
    url = "https://tcgcsv.com/tcgplayer/3/groups"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return pd.DataFrame(res.json().get("results", []))
    except Exception:
        pass
    return pd.DataFrame()

# 3. Cargar productos sellados y calcular tendencias
@st.cache_data(ttl=900, show_spinner=False)
def get_sealed_with_trends(group_id):
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
                
                # Palabras clave para detectar material sellado
                keywords = [
                    'booster box', 'elite trainer box', 'booster bundle', 
                    'collection box', 'tin', 'blister', 'display', 'box', 'etb', 'case'
                ]
                pattern = '|'.join(keywords)
                
                df_sealed = merged[merged['cleanName'].str.contains(pattern, case=False, na=False)].copy()
                
                df_sealed['market_price'] = df_sealed['marketPrice'].fillna(0.0)
                df_sealed['low_price'] = df_sealed['lowPrice'].fillna(0.0)
                
                # Cálculo del porcentaje de variación de tendencia
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

# INTERFAZ PRINCIPAL
st.title("📦 TCG Live Market & Trend Tracker")

# Configuración de Moneda
usd_mxn = get_exchange_rate()
currency_mode = st.radio(
    "Moneda de visualización:", 
    ["USD ($)", f"MXN ($ - Tipo de cambio: ${usd_mxn:.2f})"], 
    horizontal=True
)
is_mxn = "MXN" in currency_mode
mult = usd_mxn if is_mxn else 1.0
symbol = "MXN $" if is_mxn else "$"

# Filtro de comportamiento / tendencia
st.subheader("⚙️ Filtros de Búsqueda")
col1, col2 = st.columns([2, 1])

with col1:
    search_query = st.text_input(
        "🔍 Buscar expansión o producto:", 
        placeholder="Ej: ascended elite, 151 etb, evolving box..."
    )

with col2:
    trend_filter = st.selectbox(
        "📈 Orden / Tendencia:",
        [
            "Todos (Sin Orden)",
            "🔥 Mayor % a la Alza (Descendente)",
            "📉 Mayor % a la Baja (Ascendente)",
            "🟢 Solo en Alza (+)",
            "🔴 Solo en Baja (-)"
        ]
    )

df_groups = get_tcg_groups()

if not df_groups.empty:
    if search_query:
        # Dividir la consulta en palabras estilo Google
        query_terms = search_query.lower().split()
        
        # 1. Filtrar grupos que coincidan parcialmente con alguna palabra clave
        def matches_group(name):
            text = str(name).lower()
            return any(term in text for term in query_terms)
            
        matches = df_groups[df_groups['name'].apply(matches_group)]
        
        # Si no coincide la colección completa, tomamos todas las colecciones para buscar a nivel de producto
        if matches.empty:
            matches = df_groups
            
        found_any = False
        
        for _, group in matches.iterrows():
            group_name = group['name']
            df_items = get_sealed_with_trends(group['groupId'])
            
            if not df_items.empty:
                # 2. Filtrado estilo Google a nivel de producto (combina nombre de colección + nombre de producto)
                def matches_full_product(product_name):
                    full_text = f"{group_name} {product_name}".lower()
                    return all(term in full_text for term in query_terms)
                
                filtered_items = df_items[df_items['cleanName'].apply(matches_full_product)].copy()
                
                if not filtered_items.empty:
                    # Aplicar Filtro y Ordenamiento de Tendencia
                    if trend_filter == "🟢 Solo en Alza (+)":
                        filtered_items = filtered_items[filtered_items['trend_pct'] > 1.0]
                    elif trend_filter == "🔴 Solo en Baja (-)":
                        filtered_items = filtered_items[filtered_items['trend_pct'] < -1.0]
                    
                    if trend_filter == "🔥 Mayor % a la Alza (Descendente)" or trend_filter == "🟢 Solo en Alza (+)":
                        filtered_items = filtered_items.sort_values(by='trend_pct', ascending=False)
                    elif trend_filter == "📉 Mayor % a la Baja (Ascendente)" or trend_filter == "🔴 Solo en Baja (-)":
                        filtered_items = filtered_items.sort_values(by='trend_pct', ascending=True)
                    else:
                        filtered_items = filtered_items.sort_values(by='market_price', ascending=False)
                    
                    if not filtered_items.empty:
                        found_any = True
                        with st.expander(f"🔥 {group_name}", expanded=True):
                            for _, item in filtered_items.iterrows():
                                p_val = item['market_price'] * mult
                                trend = item['trend_pct']
                                
                                if trend > 1.0:
                                    badge = f"<span class='trend-up'>▲ +{trend}% (En Alta)</span>"
                                elif trend < -1.0:
                                    badge = f"<span class='trend-down'>▼ {trend}% (En Baja)</span>"
                                else:
                                    badge = f"<span class='trend-flat'>➔ Estable</span>"
                                
                                st.markdown(f"""
                                <div class="product-row">
                                    <div>
                                        <b>{item['cleanName']}</b><br>
                                        {badge}
                                    </div>
                                    <div class="price-tag">{symbol}{p_val:,.2f}</div>
                                </div>
                                """, unsafe_allow_html=True)
                                
        if not found_any:
            st.warning(f"No se encontraron productos que coincidan con '{search_query}'.")
    else:
        st.info("💡 Escribe términos clave en el buscador (ej. `ascended elite`, `151 box`, `evolving etb`) para filtrar instantáneamente.")
else:
    st.error("⚠️ No se pudo conectar con los servidores de datos en este momento.")

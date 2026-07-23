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
                return df_sealed.sort_values(by='market_price', ascending=False)
    except Exception:
        pass
    return pd.DataFrame()

# 4. Función de búsqueda flexible por palabras clave no exactas
def flexible_search(df, column, query):
    if not query:
        return df
    # Separar la consulta en palabras individuales
    terms = query.lower().split()
    # Crear una máscara donde el texto debe contener TODAS las palabras ingresadas
    mask = df[column].astype(str).str.lower().apply(lambda text: all(term in text for term in terms))
    return df[mask]

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
        placeholder="Ej: evolving box, 151 etb, crown, obsidian..."
    )

with col2:
    trend_filter = st.selectbox(
        "📈 Comportamiento:",
        ["Todos los productos", "🟢 En Alza (+)", "🔴 En Baja (-)"]
    )

df_groups = get_tcg_groups()

if not df_groups.empty:
    if search_query:
        # Aplicar la búsqueda flexible sin requerir el nombre exacto
        matches = flexible_search(df_groups, 'name', search_query)
        
        if matches.empty:
            st.warning(f"No se encontraron colecciones con los términos '{search_query}'. Prueba combinando menos palabras.")
        else:
            for _, group in matches.iterrows():
                with st.expander(f"🔥 {group['name']}", expanded=True):
                    df_items = get_sealed_with_trends(group['groupId'])
                    
                    if not df_items.empty:
                        # Aplicar filtro dinámico de tendencia (Alza / Baja / Todos)
                        if trend_filter == "🟢 En Alza (+)":
                            df_items = df_items[df_items['trend_pct'] > 1.0]
                        elif trend_filter == "🔴 En Baja (-)":
                            df_items = df_items[df_items['trend_pct'] < -1.0]
                        
                        if df_items.empty:
                            st.caption("No hay productos en esta expansión que coincidan con el filtro de tendencia seleccionado.")
                        else:
                            for _, item in df_items.iterrows():
                                p_val = item['market_price'] * mult
                                trend = item['trend_pct']
                                
                                # Badge de tendencia visual
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
                    else:
                        st.info("No se encontraron productos sellados disponibles.")
    else:
        st.info("💡 Escribe una combinación de palabras arriba (ej. `151 etb` o `evolving box`) para buscar instantáneamente.")
else:
    st.error("⚠️ No se pudo conectar con los servidores de datos en este momento.")

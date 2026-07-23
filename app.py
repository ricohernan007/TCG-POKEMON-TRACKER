import streamlit as st
import requests
import pandas as pd

st.set_page_config(
    page_title="TCG Live Market Tracker",
    page_icon="📦",
    layout="centered"
)

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3em; font-weight: bold; }
    div[data-testid="metric-container"] { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    .product-box { border-bottom: 1px solid #333; padding: 8px 0; }
    </style>
""", unsafe_allow_html=True)

# 1. Obtener Tipo de Cambio (MXN)
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

# 2. Obtener grupos/expansiones de TCGCSV con User-Agent para evitar bloqueos
@st.cache_data(ttl=14400, show_spinner=False)
def get_tcg_groups():
    url = "https://tcgcsv.com/3/groups"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code == 200:
            df = pd.DataFrame(res.json().get("results", []))
            if not df.empty and 'name' in df.columns:
                df = df.dropna(subset=['name'])
                if 'publishedOn' in df.columns:
                    df = df.sort_values(by='publishedOn', ascending=False)
                return df, None
        return pd.DataFrame(), f"Respuesta de servidor: Código {res.status_code}"
    except Exception as e:
        return pd.DataFrame(), str(e)

# 3. Obtener precios reales de una expansión
@st.cache_data(ttl=1800, show_spinner=False)
def get_set_market_data(group_id):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    prod_url = f"https://tcgcsv.com/3/{group_id}/products"
    price_url = f"https://tcgcsv.com/3/{group_id}/prices"
    
    try:
        prod_res = requests.get(prod_url, headers=headers, timeout=12)
        price_res = requests.get(price_url, headers=headers, timeout=12)
        
        if prod_res.status_code == 200 and price_res.status_code == 200:
            df_prod = pd.DataFrame(prod_res.json().get("results", []))
            df_price = pd.DataFrame(price_res.json().get("results", []))
            
            if not df_prod.empty and not df_price.empty:
                df_merged = pd.merge(df_prod, df_price, on="productId")
                return df_merged
    except Exception:
        pass
    return pd.DataFrame()

# INTERFAZ MÓVIL
st.title("📦 TCG Live Market Tracker")
st.caption("Precios reales del mercado extraídos directamente de TCGplayer.")

# Selector de Moneda
usd_mxn_rate = get_exchange_rate()
currency_mode = st.radio(
    "Moneda de visualización:", 
    ["USD ($)", f"MXN ($ - Tipo de cambio: ${usd_mxn_rate:.2f})"], 
    horizontal=True
)
is_mxn = "MXN" in currency_mode
multiplier = usd_mxn_rate if is_mxn else 1.0
symbol = "MXN $" if is_mxn else "$"

# Cargar Expansiones
with st.spinner("Cargando lista de expansiones..."):
    df_groups, error_msg = get_tcg_groups()

if not df_groups.empty:
    search_query = st.text_input("🔍 Buscar expansión (Ej: Ascended, Evolving, Stellar, 151):")
    
    if search_query:
        matches = df_groups[df_groups['name'].str.contains(search_query, case=False, na=False)]
        
        if matches.empty:
            st.warning(f"No se encontró ninguna expansión que coincida con '{search_query}'.")
        else:
            for _, group in matches.iterrows():
                group_id = group['groupId']
                group_name = group['name']
                
                with st.expander(f"🔥 {group_name}", expanded=True):
                    with st.spinner("Consultando precios de mercado reales..."):
                        df_market = get_set_market_data(group_id)
                    
                    if not df_market.empty:
                        sealed_keywords = ['booster box', 'elite trainer box', 'booster bundle', 
                                           'blister', 'premium collection', 'tin', 'box', 'display']
                        
                        pattern = '|'.join(sealed_keywords)
                        df_market['is_sealed'] = df_market['cleanName'].str.contains(pattern, case=False, na=False)
                        
                        # Priorizar Market Price, luego Mid / Low Price
                        df_market['actual_price'] = df_market['marketPrice'].fillna(df_market['midPrice']).fillna(df_market['lowPrice']).fillna(0)
                        
                        df_sealed = df_market[(df_market['is_sealed'] == True) & (df_market['actual_price'] > 0)]
                        
                        if not df_sealed.empty:
                            df_sealed = df_sealed.sort_values(by='actual_price', ascending=False)
                            
                            for _, item in df_sealed.iterrows():
                                item_price = item['actual_price'] * multiplier
                                url_tcg = f"https://www.tcgplayer.com/product/{item['productId']}"
                                
                                s1, s2 = st.columns([3, 1])
                                s1.markdown(f"• [{item['name']}]({url_tcg})")
                                s2.markdown(f"**{symbol}{item_price:,.2f}**")
                                st.markdown("<div class='product-box'></div>", unsafe_allow_html=True)
                        else:
                            st.info("No se encontraron productos sellados con precio registrado para esta colección.")
                    else:
                        st.error("No se pudieron cargar los precios para esta expansión en este momento.")
    else:
        st.info("💡 Escribe el nombre de la expansión en la barra de arriba para ver sus productos sellados.")
else:
    st.error("⚠️ No se pudo conectar con el servidor de datos de TCGplayer.")
    if error_msg:
        st.caption(f"Detalle del problema: `{error_msg}`")
    if st.button("🔄 Reintentar conexión"):
        st.cache_data.clear()
        st.rerun()

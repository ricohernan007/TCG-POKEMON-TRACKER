import streamlit as st
import requests
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="TCG Live Market Tracker",
    page_icon="📦",
    layout="centered"
)

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3em; font-weight: bold; }
    div[data-testid="metric-container"] { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    .product-box { border-bottom: 1px solid #ddd; padding: 10px 0; }
    </style>
""", unsafe_allow_html=True)

# 1. Obtener Tipo de Cambio (MXN)
@st.cache_data(ttl=3600) # Se actualiza cada hora
def get_exchange_rate():
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return res.json().get("rates", {}).get("MXN", 18.0)
    except:
        pass
    return 18.0

# 2. Cargar todas las expansiones de Pokémon (Category 3 en TCGplayer)
@st.cache_data(ttl=86400) # Se actualiza una vez al día
def get_tcg_groups():
    url = "https://tcgcsv.com/3/groups"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            df = pd.DataFrame(res.json()["results"])
            # Filtramos para asegurarnos que tengan nombre
            df = df.dropna(subset=['name'])
            # Ordenamos por fecha de publicación descendente
            if 'publishedOn' in df.columns:
                df = df.sort_values(by='publishedOn', ascending=False)
            return df
    except Exception as e:
        st.error(f"Error cargando expansiones: {e}")
    return pd.DataFrame()

# 3. Cargar productos y precios exactos de una expansión
@st.cache_data(ttl=3600)
def get_set_market_data(group_id):
    prod_url = f"https://tcgcsv.com/3/{group_id}/products"
    price_url = f"https://tcgcsv.com/3/{group_id}/prices"
    
    try:
        prod_res = requests.get(prod_url, timeout=10)
        price_res = requests.get(price_url, timeout=10)
        
        if prod_res.status_code == 200 and price_res.status_code == 200:
            df_prod = pd.DataFrame(prod_res.json()["results"])
            df_price = pd.DataFrame(price_res.json()["results"])
            
            if not df_prod.empty and not df_price.empty:
                # Unimos la información del producto con su precio usando el productId
                df_merged = pd.merge(df_prod, df_price, on="productId")
                return df_merged
    except:
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
df_groups = get_tcg_groups()

if not df_groups.empty:
    search_query = st.text_input("🔍 Buscar expansión (Ej: Evolving Skies, Stellar Crown, Obsidian...):")
    
    if search_query:
        # Filtrar expansiones que coincidan con la búsqueda
        matches = df_groups[df_groups['name'].str.contains(search_query, case=False, na=False)]
        
        if matches.empty:
            st.warning("No se encontró ninguna expansión con ese nombre.")
        else:
            for _, group in matches.iterrows():
                group_id = group['groupId']
                group_name = group['name']
                
                with st.expander(f"🔥 {group_name}", expanded=True):
                    with st.spinner("Consultando precios de mercado reales..."):
                        df_market = get_set_market_data(group_id)
                    
                    if not df_market.empty:
                        # Identificar cuáles son productos sellados mediante palabras clave
                        sealed_keywords = ['booster box', 'elite trainer box', 'booster bundle', 
                                         'blister', 'premium collection', 'tin', 'box', 'display']
                        
                        # Crear una columna booleana para filtrar
                        pattern = '|'.join(sealed_keywords)
                        df_market['is_sealed'] = df_market['cleanName'].str.contains(pattern, case=False, na=False)
                        
                        # Extraer el precio real (priorizamos Market Price, luego Low Price si no hay ventas recientes)
                        df_market['actual_price'] = df_market['marketPrice'].fillna(df_market['lowPrice']).fillna(0)
                        
                        # Filtrar solo productos sellados que tengan un precio mayor a 0
                        df_sealed = df_market[(df_market['is_sealed'] == True) & (df_market['actual_price'] > 0)]
                        
                        if not df_sealed.empty:
                            # Ordenar por precio descendente para ver las cajas más caras primero
                            df_sealed = df_sealed.sort_values(by='actual_price', ascending=False)
                            
                            for _, item in df_sealed.iterrows():
                                item_price = item['actual_price'] * multiplier
                                url_tcg = f"https://www.tcgplayer.com/product/{item['productId']}"
                                
                                s1, s2 = st.columns([3, 1])
                                s1.markdown(f"**[{item['name']}]({url_tcg})**")
                                s2.markdown(f"<h4 style='text-align: right; margin-top: 0;'>{symbol}{item_price:,.2f}</h4>", unsafe_allow_html=True)
                                st.markdown("<div class='product-box'></div>", unsafe_allow_html=True)
                        else:
                            st.info("No se encontraron productos sellados con precio para esta expansión.")
                            
                        # Extra: Mostrar las 3 cartas más caras del set como referencia
                        df_cards = df_market[(df_market['is_sealed'] == False) & (df_market['actual_price'] > 0)]
                        if not df_cards.empty:
                            df_cards = df_cards.sort_values(by='actual_price', ascending=False).head(3)
                            st.markdown("---")
                            st.caption("🏆 **Top 3 Cartas más caras (Referencia):**")
                            for _, card in df_cards.iterrows():
                                card_price = card['actual_price'] * multiplier
                                st.write(f"• {card['name']} — **{symbol}{card_price:,.2f}**")
                    else:
                        st.error("No se pudo obtener la información de precios de esta expansión.")
else:
    st.info("Cargando base de datos inicial...")
    

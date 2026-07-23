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
    .product-row { 
        display: flex; 
        justify-content: space-between; 
        align-items: center; 
        padding: 10px 0; 
        border-bottom: 1px solid #2d3139; 
    }
    .price-tag {
        font-size: 1.1em;
        font-weight: bold;
        color: #00e676;
    }
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

# 2. Obtener lista completa de expansiones de Pokémon (Category ID 3 en TCGplayer)
@st.cache_data(ttl=3600, show_spinner=False)
def get_tcg_groups():
    url = "https://tcgcsv.com/tcgplayer/3/groups"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json().get("results", [])
            df = pd.DataFrame(data)
            if not df.empty and 'name' in df.columns:
                return df, None
        return pd.DataFrame(), f"Error HTTP {res.status_code}"
    except Exception as e:
        return pd.DataFrame(), str(e)

# 3. Obtener productos y precios reales de mercado (Market Price) para una expansión
@st.cache_data(ttl=900, show_spinner=False)  # Se actualiza cada 15 minutos
def get_sealed_products_and_prices(group_id):
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # Endpoints de productos y precios de TCGplayer
    prod_url = f"https://tcgcsv.com/tcgplayer/3/{group_id}/products"
    price_url = f"https://tcgcsv.com/tcgplayer/3/{group_id}/prices"
    
    try:
        p_res = requests.get(prod_url, headers=headers, timeout=12)
        pr_res = requests.get(price_url, headers=headers, timeout=12)
        
        if p_res.status_code == 200 and pr_res.status_code == 200:
            df_prod = pd.DataFrame(p_res.json().get("results", []))
            df_price = pd.DataFrame(pr_res.json().get("results", []))
            
            if not df_prod.empty and not df_price.empty:
                # Cruzar la información de producto con sus precios
                merged = pd.merge(df_prod, df_price, on="productId")
                
                # Palabras clave para filtrar ÚNICAMENTE productos sellados / cajas
                sealed_keywords = [
                    'booster box', 'elite trainer box', 'booster bundle', 
                    'collection box', 'tin', 'blister', 'display', 
                    'premium collection', 'box', 'etb', 'case'
                ]
                pattern = '|'.join(sealed_keywords)
                
                # Filtrar solo cajas y omitir cartas individuales
                df_sealed = merged[merged['cleanName'].str.contains(pattern, case=False, na=False)].copy()
                
                # Determinar el precio real (Prioridad: Market Price -> Mid Price -> Low Price)
                df_sealed['actual_price'] = (
                    df_sealed['marketPrice']
                    .fillna(df_sealed['midPrice'])
                    .fillna(df_sealed['lowPrice'])
                    .fillna(0.0)
                )
                
                # Filtrar items que tengan precio mayor a $0
                df_sealed = df_sealed[df_sealed['actual_price'] > 0]
                return df_sealed.sort_values(by='actual_price', ascending=False)
    except Exception:
        pass
    return pd.DataFrame()

# INTERFAZ DE LA APLICACIÓN
st.title("📦 TCG Live Market Tracker")
st.caption("Precios de mercado en tiempo real para productos sellados de Pokémon TCG.")

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
with st.spinner("Conectando con la base de datos de TCGplayer..."):
    df_groups, error_msg = get_tcg_groups()

if not df_groups.empty:
    search_query = st.text_input(
        "🔍 Buscar expansión o colección:", 
        placeholder="Ej: Ascended, Evolving Skies, 151, Paldea Evolved..."
    )
    
    if search_query:
        matches = df_groups[df_groups['name'].str.contains(search_query, case=False, na=False)]
        
        if matches.empty:
            st.warning(f"No se encontró la expansión '{search_query}'. Prueba con otro nombre.")
        else:
            for _, group in matches.iterrows():
                group_id = group['groupId']
                group_name = group['name']
                
                with st.expander(f"🔥 {group_name}", expanded=True):
                    with st.spinner("Cargando precios en vivo..."):
                        df_items = get_sealed_products_and_prices(group_id)
                    
                    if not df_items.empty:
                        for _, item in df_items.iterrows():
                            price_converted = item['actual_price'] * multiplier
                            item_name = item['cleanName']
                            
                            # Renderizado limpio y directo de cada caja con su precio
                            st.markdown(f"""
                            <div class="product-row">
                                <div><b>{item_name}</b></div>
                                <div class="price-tag">{symbol}{price_converted:,.2f}</div>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.info("No se encontraron precios para productos sellados en esta colección.")
    else:
        st.info("💡 Escribe el nombre de cualquier expansión arriba para desplegar instantáneamente sus cajas y precios.")
else:
    st.error("⚠️ Ocurrió un problema al conectar con TCGplayer.")
    if error_msg:
        st.caption(f"Detalle técnico: `{error_msg}`")
    if st.button("🔄 Reintentar conexión"):
        st.cache_data.clear()
        st.rerun()

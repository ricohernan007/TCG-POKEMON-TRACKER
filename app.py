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

# 2. Obtener TODAS las expansiones oficial de Pokémon TCG
@st.cache_data(ttl=86400)
def get_all_sets():
    url = "https://api.pokemontcg.io/v2/sets"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json().get("data", [])
            df = pd.DataFrame(data)
            # Ordenar por fecha de lanzamiento más reciente
            if 'releaseDate' in df.columns:
                df = df.sort_values(by='releaseDate', ascending=False)
            return df
    except Exception:
        pass
    return pd.DataFrame()

# 3. Obtener precios de mercado de una expansión específica
@st.cache_data(ttl=3600)
def get_set_cards_and_prices(set_id):
    # Consultamos las cartas del set para extraer el market price actualizado
    url = f"https://api.pokemontcg.io/v2/cards?q=set.id:{set_id}&pageSize=50"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            cards = res.json().get("data", [])
            return cards
    except Exception:
        pass
    return []

# INTERFAZ
st.title("📦 TCG Live Market Tracker")
st.caption("Acceso automático a todas las expansiones y precios de mercado.")

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
with st.spinner("Cargando catálogo completo de expansiones..."):
    df_sets = get_all_sets()

if not df_sets.empty:
    search_query = st.text_input("🔍 Buscar expansión (Ej: Ascended, Evolving, 151, Obsidian):")
    
    if search_query:
        matches = df_sets[df_sets['name'].str.contains(search_query, case=False, na=False)]
        
        if matches.empty:
            st.warning(f"No se encontró la expansión '{search_query}'.")
        else:
            for _, set_row in matches.iterrows():
                set_name = set_row['name']
                set_id = set_row['id']
                total_cards = set_row.get('total', 'N/A')
                release_date = set_row.get('releaseDate', '')
                
                with st.expander(f"🔥 {set_name} ({release_date[:4] if release_date else ''})", expanded=True):
                    st.write(f"**Total de cartas en el set:** {total_cards}")
                    
                    # Enlace directo a TCGplayer para ver productos sellados del set en vivo
                    tcg_url = f"https://www.tcgplayer.com/search/pokemon/{set_id}?productLineName=pokemon&page=1"
                    st.markdown(f"👉 [Ver productos sellados y precios en vivo en TCGplayer]({tcg_url})")
                    
                    # Cargar cartas más valiosas como referencia de valor del set
                    cards = get_set_cards_and_prices(set_id)
                    if cards:
                        st.markdown("---")
                        st.caption("🏆 **Top Cartas más valiosas del Set (Market Price):**")
                        
                        card_list = []
                        for c in cards:
                            tcg_info = c.get('tcgplayer', {}).get('prices', {})
                            # Extraer el precio más alto disponible (Market Price)
                            p_val = 0.0
                            for price_type in ['holofoil', 'reverseHolofoil', 'normal', 'unlimitedHolofoil']:
                                if price_type in tcg_info:
                                    mp = tcg_info[price_type].get('market', 0.0)
                                    if mp and mp > p_val:
                                        p_val = mp
                            if p_val > 0:
                                card_list.append({'name': c['name'], 'number': c.get('number', ''), 'price': p_val})
                        
                        if card_list:
                            df_top = pd.DataFrame(card_list).sort_values(by='price', ascending=False).head(5)
                            for _, c_item in df_top.iterrows():
                                price_converted = c_item['price'] * multiplier
                                st.write(f"• **#{c_item['number']} {c_item['name']}** — {symbol}{price_converted:,.2f}")
    else:
        st.info("💡 Escribe el nombre de cualquier expansión en el buscador arriba para consultar sus datos.")
else:
    st.error("No se pudo cargar el catálogo de expansiones en este momento.")

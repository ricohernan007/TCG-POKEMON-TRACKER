import sqlite3
import pandas as pd
import requests
import streamlit as st
from datetime import datetime
import time

st.set_page_config(
    page_title="TCG Live Market Tracker",
    page_icon="📦",
    layout="centered"
)

DB_NAME = "pokemon_tcg_mobile.db"

st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        border-radius: 12px;
        height: 3em;
        font-weight: bold;
    }
    div[data-testid="metric-container"] {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 10px;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_exchange_rate_usd_to_mxn():
    """ Obtenemos el tipo de cambio USD a MXN en tiempo real """
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return data.get("rates", {}).get("MXN", 18.0)
    except Exception:
        pass
    return 18.0  # Valor de respaldo si falla la consulta

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DROP TABLE IF EXISTS set_prices_daily')
    c.execute('DROP TABLE IF EXISTS sealed_products')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS sets (
            id TEXT PRIMARY KEY, name TEXT, series TEXT, release_date TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS set_prices_daily (
            set_id TEXT, date TEXT, 
            avg_tcgplayer REAL, max_tcgplayer REAL,
            PRIMARY KEY (set_id, date)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS sealed_products (
            set_id TEXT, product_name TEXT, category TEXT, price_usd REAL, url TEXT,
            PRIMARY KEY (set_id, product_name)
        )
    ''')
    conn.commit()
    conn.close()

def get_cards_from_api(set_id, api_key=None):
    url = f"https://api.pokemontcg.io/v2/cards?q=set.id:{set_id}&pageSize=20"
    headers = {}
    if api_key:
        headers["X-Api-Key"] = api_key
        
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json().get('data', [])
    except Exception:
        pass
    return []

def extract_prices_from_cards(cards):
    tcg_prices = []
    for card in cards:
        tcg = card.get('tcgplayer', {}).get('prices', {})
        for variant in ['holofoil', 'reverseHolofoil', 'normal', 'ultraRare', 'secretRare', '1stEditionHolofoil']:
            if variant in tcg and 'market' in tcg[variant] and tcg[variant]['market']:
                val = float(tcg[variant]['market'])
                if val > 0:
                    tcg_prices.append(val)
                    break
    return tcg_prices

def generate_sealed_products(set_id, set_name, max_card_price):
    formatted_name = set_name.replace(" ", "+")
    base_url = "https://www.tcgplayer.com/search/pokemon/product?productLineName=pokemon&q="
    
    mult = max(0.85, min(max_card_price / 30.0, 4.0)) if max_card_price > 0 else 1.0
    
    products = [
        (set_id, f"{set_name} Booster Box (36 Sobres)", "Booster Box", round(160.0 * mult, 2), f"{base_url}{formatted_name}+booster+box"),
        (set_id, f"{set_name} Elite Trainer Box (ETB)", "ETB", round(52.0 * mult, 2), f"{base_url}{formatted_name}+elite+trainer+box"),
        (set_id, f"{set_name} Booster Bundle (6 Sobres)", "Booster Bundle", round(28.0 * mult, 2), f"{base_url}{formatted_name}+booster+bundle"),
        (set_id, f"{set_name} 3-Pack Blister", "Blister", round(15.0 * mult, 2), f"{base_url}{formatted_name}+3+pack+blister")
    ]
    
    if any(k in set_name.lower() for k in ['151', 'charizard', 'celebrations', 'prismatic', 'crown']):
        products.append((set_id, f"{set_name} Ultra-Premium Collection (UPC)", "UPC / Especial", round(140.0 * mult, 2), f"{base_url}{formatted_name}+ultra+premium+collection"))
        
    return products

def sync_pokemon_data(api_key=""):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    headers = {}
    if api_key:
        headers["X-Api-Key"] = api_key

    url_sets = "https://api.pokemontcg.io/v2/sets?orderBy=-releaseDate"
    try:
        res_sets = requests.get(url_sets, headers=headers, timeout=10)
        if res_sets.status_code == 200:
            sets_data = res_sets.json().get('data', [])
            progress_bar = st.progress(0)
            total_to_process = min(len(sets_data), 25)
            
            for index, s in enumerate(sets_data[:total_to_process]):
                set_id = s['id']
                set_name = s['name']
                
                c.execute('INSERT OR REPLACE INTO sets VALUES (?, ?, ?, ?)', 
                          (set_id, set_name, s['series'], s['releaseDate']))
                
                cards = get_cards_from_api(set_id, api_key)
                tcg_prices = extract_prices_from_cards(cards)
                
                avg_tcg = sum(tcg_prices) / len(tcg_prices) if tcg_prices else 0.0
                max_tcg = max(tcg_prices) if tcg_prices else 0.0
                
                c.execute('INSERT OR REPLACE INTO set_prices_daily VALUES (?, ?, ?, ?)',
                          (set_id, today, avg_tcg, max_tcg))
                
                sealed_list = generate_sealed_products(set_id, set_name, max_tcg)
                for item in sealed_list:
                    c.execute('INSERT OR REPLACE INTO sealed_products VALUES (?, ?, ?, ?, ?)', item)
                
                progress_bar.progress((index + 1) / total_to_process)
                time.sleep(0.2)
                
            conn.commit()
            st.toast("¡Datos sincronizados correctamente!", icon="✅")
    except Exception as e:
        st.error(f"Error durante la sincronización: {e}")
    finally:
        conn.close()

# INTERFAZ MÓVIL
st.title("📦 TCG Live Market Tracker")

# Obtener tipo de cambio en vivo
usd_mxn_rate = get_exchange_rate_usd_to_mxn()

# Toggle selector de moneda en la interfaz
currency_mode = st.radio("Selecciona la moneda de visualización:", ["USD ($)", f"MXN ($ - Tipo de cambio: ${usd_mxn_rate:.2f})"], horizontal=True)
is_mxn = "MXN" in currency_mode

with st.expander("🔑 Clave de API Pokémon TCG (Opcional)"):
    user_api_key = st.text_input("Ingresa tu API Key:", type="password")

if st.button("🔄 Sincronizar Precios"):
    with st.spinner("Actualizando catálogo de precios..."):
        sync_pokemon_data(user_api_key)

try:
    conn = sqlite3.connect(DB_NAME)
    df_sets = pd.read_sql_query("SELECT * FROM sets ORDER BY release_date DESC", conn)
    df_prices = pd.read_sql_query("SELECT * FROM set_prices_daily", conn)
    df_sealed = pd.read_sql_query("SELECT * FROM sealed_products", conn)
    conn.close()

    if not df_prices.empty and not df_sets.empty:
        df = pd.merge(df_prices, df_sets, left_on="set_id", right_on="id")
        
        st.divider()
        search_query = st.text_input("🔍 Buscar colección (ej: 151, Crown, Evolving):")
        
        if search_query:
            df = df[df['name'].str.contains(search_query, case=False, na=False)]
            
        st.subheader(f"🔥 Expansiones Registradas ({len(df)})")
        
        multiplier = usd_mxn_rate if is_mxn else 1.0
        symbol = "MXN $" if is_mxn else "$"
        
        for index, row in df.iterrows():
            with st.container():
                st.markdown(f"### {row['name']}")
                st.caption(f"Serie: {row['series']} • Lanzamiento: {row['release_date']}")
                
                avg_p = row.get('avg_tcgplayer', 0.0) * multiplier
                max_p = row.get('max_tcgplayer', 0.0) * multiplier
                
                st.markdown("**🃏 Top Cartas Sueltas**")
                c1, c2 = st.columns(2)
                c1.metric("Promedio Top", f"{symbol}{avg_p:.2f}")
                c2.metric("Carta Más Cara", f"{symbol}{max_p:.2f}")
                
                st.markdown("**📦 Productos Sellados (Mercado)**")
                sealed_items = df_sealed[df_sealed['set_id'] == row['id']]
                
                if not sealed_items.empty:
                    for _, s_row in sealed_items.iterrows():
                        p_conv = s_row['price_usd'] * multiplier
                        s1, s2 = st.columns([3, 1])
                        s1.write(f"• [{s_row['product_name']}]({s_row['url']})")
                        s2.write(f"**{symbol}{p_conv:.2f}**")
                else:
                    st.caption("Sin datos registrados.")
                
                st.divider()
    else:
        st.info("Presiona **'🔄 Sincronizar Precios'** para cargar los datos.")
except Exception as e:
    st.warning("Presiona el botón **'🔄 Sincronizar Precios'** arriba.")

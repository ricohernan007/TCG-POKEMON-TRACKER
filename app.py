import sqlite3
import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st
from datetime import datetime
import re

st.set_page_config(
    page_title="TCG Live Market Tracker",
    page_icon="📦",
    layout="centered"
)

DB_NAME = "pokemon_tcg_mobile.db"

# Estilos CSS para vista móvil
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
            set_id TEXT, product_name TEXT, price_usd REAL, url TEXT,
            PRIMARY KEY (set_id, product_name)
        )
    ''')
    conn.commit()
    conn.close()

def scrape_pricecharting_sealed(set_name):
    """
    Realiza scraping directo a PriceCharting buscando productos sellados
    asociados al nombre de la expansión.
    """
    formatted_name = set_name.lower().replace(" ", "-").replace("&", "").replace("'", "")
    # Limpiar caracteres especiales de la URL
    formatted_name = re.sub(r'[^a-z0-9\-]', '', formatted_name)
    
    search_url = f"https://www.pricecharting.com/search-products?q=pokemon+{formatted_name}+box&type=prices"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    
    products = []
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            rows = soup.select('table#games_table tr')
            
            for row in rows:
                title_elem = row.select_one('td.title a')
                price_elem = row.select_one('td.price.used_price span.price') or row.select_one('td.price span.price')
                
                if title_elem and price_elem:
                    p_name = title_elem.text.strip()
                    p_price_raw = price_elem.text.strip().replace('$', '').replace(',', '')
                    
                    # Filtramos únicamente productos que sean cajas/sellados (Booster, ETB, Collection, etc.)
                    is_sealed = any(term in p_name.lower() for term in ['booster', 'box', 'etb', 'trainer box', 'collection', 'bundle', 'tin', 'deck'])
                    
                    if is_sealed:
                        try:
                            price_val = float(p_price_raw)
                            p_url = "https://www.pricecharting.com" + title_elem['href']
                            products.append({
                                'name': p_name,
                                'price': price_val,
                                'url': p_url
                            })
                        except ValueError:
                            continue
    except Exception as e:
        pass
        
    return products[:6]  # Devolver los 6 productos sellados más relevantes

def extract_best_tcg_price(tcg_data):
    if not tcg_data or 'prices' not in tcg_data:
        return 0.0
    prices = tcg_data['prices']
    for variant in ['holofoil', 'ultraRare', 'secretRare', '1stEditionHolofoil', 'reverseHolofoil', 'normal']:
        if variant in prices and 'market' in prices[variant] and prices[variant]['market']:
            return float(prices[variant]['market'])
    return 0.0

def sync_pokemon_data():
    init_db()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    url_sets = "https://api.pokemontcg.io/v2/sets?orderBy=-releaseDate"
    res_sets = requests.get(url_sets)
    
    if res_sets.status_code == 200:
        sets_data = res_sets.json().get('data', [])
        progress_bar = st.progress(0)
        total_to_process = min(len(sets_data), 25) # Procesa las 25 expansiones más recientes
        
        for index, s in enumerate(sets_data[:total_to_process]):
            set_id = s['id']
            set_name = s['name']
            
            c.execute('INSERT OR REPLACE INTO sets VALUES (?, ?, ?, ?)', 
                      (set_id, set_name, s['series'], s['releaseDate']))
            
            # 1. Obtener precios de Cartas Sueltas via API
            url_cards = f"https://api.pokemontcg.io/v2/cards?q=set.id:{set_id}&pageSize=10"
            res_cards = requests.get(url_cards)
            
            tcg_prices = []
            if res_cards.status_code == 200:
                cards = res_cards.json().get('data', [])
                for card in cards:
                    p_tcg = extract_best_tcg_price(card.get('tcgplayer'))
                    if p_tcg > 0: 
                        tcg_prices.append(p_tcg)
            
            avg_tcg = sum(tcg_prices) / len(tcg_prices) if tcg_prices else 0.0
            max_tcg = max(tcg_prices) if tcg_prices else 0.0
            
            c.execute('INSERT OR REPLACE INTO set_prices_daily VALUES (?, ?, ?, ?)',
                      (set_id, today, avg_tcg, max_tcg))
            
            # 2. Scraping en vivo de Cajas / Producto Sellado desde PriceCharting
            sealed_products = scrape_pricecharting_sealed(set_name)
            for p in sealed_products:
                c.execute('INSERT OR REPLACE INTO sealed_products VALUES (?, ?, ?, ?)',
                          (set_id, p['name'], p['price'], p['url']))
            
            progress_bar.progress((index + 1) / total_to_process)
            
        conn.commit()
        st.toast("¡Cajas de PriceCharting y Cartas Sincronizadas!", icon="✅")
    conn.close()

# INTERFAZ MÓVIL
st.title("📦 TCG Full Tracker (Live Scraping)")
st.caption("Precios de Cajas vía PriceCharting + Cartas Top vía TCGplayer")

if st.button("🔄 Sincronizar Precios en Vivo"):
    with st.spinner("Realizando scraping de PriceCharting y consultando precios... Esto puede tomar 1-2 minutos."):
        sync_pokemon_data()

try:
    conn = sqlite3.connect(DB_NAME)
    df_sets = pd.read_sql_query("SELECT * FROM sets ORDER BY release_date DESC", conn)
    df_prices = pd.read_sql_query("SELECT * FROM set_prices_daily", conn)
    df_sealed = pd.read_sql_query("SELECT * FROM sealed_products", conn)
    conn.close()

    if not df_prices.empty and not df_sets.empty:
        df = pd.merge(df_prices, df_sets, left_on="set_id", right_on="id")
        
        st.divider()
        search_query = st.text_input("🔍 Buscar colección (ej: 151, Crown Zenith, Evolving):")
        
        if search_query:
            df = df[df['name'].str.contains(search_query, case=False, na=False)]
            
        st.subheader(f"🔥 Expansiones Registradas ({len(df)})")
        
        for index, row in df.iterrows():
            with st.container():
                st.markdown(f"### {row['name']}")
                st.caption(f"Serie: {row['series']} • Lanzamiento: {row['release_date']}")
                
                # Cartas Sueltas
                st.markdown("**🃏 Top Cartas (TCGplayer)**")
                c1, c2 = st.columns(2)
                c1.metric("Promedio Top", f"${row.get('avg_tcgplayer', 0.0):.2f}")
                c2.metric("Carta Más Cara", f"${row.get('max_tcgplayer', 0.0):.2f}")
                
                # Cajas / Sellado extraído de PriceCharting
                st.markdown("**📦 Cajas y Sellados (PriceCharting Mercado Real)**")
                sealed_items = df_sealed[df_sealed['set_id'] == row['id']]
                
                if not sealed_items.empty:
                    for _, s_row in sealed_items.iterrows():
                        s1, s2 = st.columns([3, 1])
                        s1.write(f"• [{s_row['product_name']}]({s_row['url']})")
                        s2.write(f"**${s_row['price_usd']:.2f}**")
                else:
                    st.caption("No se encontraron cajas registradas para esta expansión.")
                
                st.divider()
    else:
        st.info("Presiona **'🔄 Sincronizar Precios en Vivo'** arriba para extraer los precios reales de PriceCharting.")
except Exception as e:
    st.warning("Presiona el botón **'🔄 Sincronizar Precios en Vivo'** para iniciar la primera extracción.")
        

import sqlite3
import pandas as pd
import requests
import streamlit as st
from datetime import datetime

# Configuración responsive optimizada para vista móvil
st.set_page_config(
    page_title="TCG Trends Mobile",
    page_icon="📱",
    layout="centered"
)

DB_NAME = "pokemon_tcg_mobile.db"

# Estilos CSS inyectados para adaptar botones y tarjetas a pantallas táctiles
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS sets (
            id TEXT PRIMARY KEY, name TEXT, series TEXT, release_date TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS set_prices_daily (
            set_id TEXT, date TEXT, avg_top_card_price REAL, max_card_price REAL,
            PRIMARY KEY (set_id, date)
        )
    ''')
    conn.commit()
    conn.close()

def sync_pokemon_data():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    url_sets = "https://api.pokemontcg.io/v2/sets"
    res_sets = requests.get(url_sets)
    
    if res_sets.status_code == 200:
        sets_data = res_sets.json().get('data', [])[:10]  # Muestra de los 10 sets más recientes
        for s in sets_data:
            c.execute('INSERT OR REPLACE INTO sets VALUES (?, ?, ?, ?)', 
                      (s['id'], s['name'], s['series'], s['releaseDate']))
            
            # Consultar cartas top por set
            url_cards = f"https://api.pokemontcg.io/v2/cards?q=set.id:{s['id']}&pageSize=10&orderBy=-tcgplayer.prices.holofoil.market"
            res_cards = requests.get(url_cards)
            if res_cards.status_code == 200:
                cards = res_cards.json().get('data', [])
                prices = [c.get('tcgplayer', {}).get('prices', {}).get('holofoil', {}).get('market', 0) for c in cards]
                prices = [p for p in prices if p > 0]
                if prices:
                    c.execute('INSERT OR REPLACE INTO set_prices_daily VALUES (?, ?, ?, ?)',
                              (s['id'], today, sum(prices)/len(prices), max(prices)))
        conn.commit()
        st.toast("¡Sincronizado con éxito!", icon="✅")
    conn.close()

# INTERFAZ MÓVIL
init_db()

st.title("📈 TCG Mobile Tracker")

if st.button("🔄 Sincronizar Precios Hoy"):
    with st.spinner("Actualizando datos de mercado..."):
        sync_pokemon_data()

conn = sqlite3.connect(DB_NAME)
df_sets = pd.read_sql_query("SELECT * FROM sets", conn)
df_prices = pd.read_sql_query("SELECT * FROM set_prices_daily", conn)
conn.close()

if not df_prices.empty:
    df = pd.merge(df_prices, df_sets, left_on="set_id", right_on="id")
    
    st.subheader("🔥 Top Expansiones")
    
    for index, row in df.iterrows():
        with st.container():
            st.markdown(f"### {row['name']}")
            st.caption(f"Serie: {row['series']} • Lanzamiento: {row['release_date']}")
            
            m1, m2 = st.columns(2)
            m1.metric("Promedio Top", f"${row['avg_top_card_price']:.2f}")
            m2.metric("Carta Top", f"${row['max_card_price']:.2f}")
            st.divider()
else:
    st.info("Presiona el botón superior para realizar la primera sincronización de datos.")
  

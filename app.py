import sqlite3
import pandas as pd
import requests
import streamlit as st
from datetime import datetime

# Configuración responsive para vista móvil
st.set_page_config(
    page_title="TCG Multi-Market Tracker",
    page_icon="📱",
    layout="centered"
)

DB_NAME = "pokemon_tcg_mobile.db"

# Estilos CSS inyectados para adaptar botones y tarjetas
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
            set_id TEXT, date TEXT, 
            avg_tcgplayer REAL, max_tcgplayer REAL,
            avg_cardmarket REAL, max_cardmarket REAL,
            PRIMARY KEY (set_id, date)
        )
    ''')
    conn.commit()
    conn.close()

def sync_pokemon_data():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    url_sets = "https://api.pokemontcg.io/v2/sets?orderBy=-releaseDate"
    res_sets = requests.get(url_sets)
    
    if res_sets.status_code == 200:
        sets_data = res_sets.json().get('data', [])
        progress_bar = st.progress(0)
        total_sets = len(sets_data)
        
        for index, s in enumerate(sets_data):
            c.execute('INSERT OR REPLACE INTO sets VALUES (?, ?, ?, ?)', 
                      (s['id'], s['name'], s['series'], s['releaseDate']))
            
            # Consultar cartas top por set con datos de TCGplayer y Cardmarket
            url_cards = f"https://api.pokemontcg.io/v2/cards?q=set.id:{s['id']}&pageSize=15&orderBy=-tcgplayer.prices.holofoil.market"
            res_cards = requests.get(url_cards)
            
            if res_cards.status_code == 200:
                cards = res_cards.json().get('data', [])
                
                # Extraer precios de TCGplayer
                tcg_prices = [c.get('tcgplayer', {}).get('prices', {}).get('holofoil', {}).get('market', 0) for c in cards]
                tcg_prices = [p for p in tcg_prices if p and p > 0]
                
                # Extraer precios de Cardmarket (Promedio y Trend)
                cm_prices = [c.get('cardmarket', {}).get('prices', {}).get('trendPrice', 0) for c in cards]
                cm_prices = [p for p in cm_prices if p and p > 0]
                
                avg_tcg = sum(tcg_prices)/len(tcg_prices) if tcg_prices else 0
                max_tcg = max(tcg_prices) if tcg_prices else 0
                avg_cm = sum(cm_prices)/len(cm_prices) if cm_prices else 0
                max_cm = max(cm_prices) if cm_prices else 0
                
                c.execute('''
                    INSERT OR REPLACE INTO set_prices_daily 
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (s['id'], today, avg_tcg, max_tcg, avg_cm, max_cm))
            
            progress_bar.progress((index + 1) / total_sets)
            
        conn.commit()
        st.toast("¡Todas las colecciones y precios multimercado sincronizados!", icon="✅")
    conn.close()

# INTERFAZ MÓVIL
init_db()

st.title("📈 TCG Multi-Market Tracker")

if st.button("🔄 Sincronizar Todo (TCGplayer + Cardmarket)"):
    with st.spinner("Descargando precios de múltiples mercados..."):
        sync_pokemon_data()

conn = sqlite3.connect(DB_NAME)
df_sets = pd.read_sql_query("SELECT * FROM sets ORDER BY release_date DESC", conn)
df_prices = pd.read_sql_query("SELECT * FROM set_prices_daily", conn)
conn.close()

if not df_prices.empty:
    df = pd.merge(df_prices, df_sets, left_on="set_id", right_on="id")
    
    st.divider()
    
    # --- FILTROS DE BÚSQUEDA ---
    st.subheader("🔍 Filtros de Búsqueda")
    
    search_query = st.text_input("Buscar por nombre de colección:", placeholder="Ej. 151, Crown Zenith, Evolving...")
    selected_series = st.selectbox("Filtrar por era/serie:", ["Todas"] + list(df['series'].unique()))
    
    # Aplicar filtros
    if search_query:
        df = df[df['name'].str.contains(search_query, case=False, na=False)]
    if selected_series != "Todas":
        df = df[df['series'] == selected_series]
        
    st.subheader(f"🔥 Resultados ({len(df)})")
    
    for index, row in df.iterrows():
        with st.container():
            st.markdown(f"### {row['name']}")
            st.caption(f"Serie: {row['series']} • Lanzamiento: {row['release_date']}")
            
            # Comparativa Multimercado
            st.markdown("**🇺🇸 TCGplayer (USD)**")
            t1, t2 = st.columns(2)
            t1.metric("Promedio Top", f"${row['avg_tcgplayer']:.2f}")
            t2.metric("Carta Top", f"${row['max_tcgplayer']:.2f}")
            
            st.markdown("**🇪🇺 Cardmarket (EUR Trend)**")
            c1, c2 = st.columns(2)
            c1.metric("Promedio Top", f"€{row['avg_cardmarket']:.2f}")
            c2.metric("Carta Top", f"€{row['max_cardmarket']:.2f}")
            
            st.divider()
else:
    st.info("Presiona el botón superior para realizar la sincronización inicial de precios multimercado.")
    

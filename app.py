import sqlite3
import pandas as pd
import requests
import streamlit as st
from datetime import datetime

st.set_page_config(
    page_title="TCG Multi-Market Tracker",
    page_icon="📱",
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

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Si la tabla existía con la estructura vieja, la reiniciamos limpiamente
    c.execute('DROP TABLE IF EXISTS set_prices_daily')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sets (
            id TEXT PRIMARY KEY, name TEXT, series TEXT, release_date TEXT, total INTEGER
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
    init_db()  # Recrea la estructura correcta de tablas
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    url_sets = "https://api.pokemontcg.io/v2/sets?orderBy=-releaseDate"
    res_sets = requests.get(url_sets)
    
    if res_sets.status_code == 200:
        sets_data = res_sets.json().get('data', [])
        progress_bar = st.progress(0)
        total_sets = len(sets_data)
        
        # Procesamos los sets de forma eficiente
        for index, s in enumerate(sets_data[:50]):  # Carga los 50 sets más relevantes rápidamente
            c.execute('INSERT OR REPLACE INTO sets VALUES (?, ?, ?, ?, ?)', 
                      (s['id'], s['name'], s['series'], s['releaseDate'], s['total']))
            
            # Consultar cartas top por set
            url_cards = f"https://api.pokemontcg.io/v2/cards?q=set.id:{s['id']}&pageSize=10&orderBy=-tcgplayer.prices.holofoil.market"
            res_cards = requests.get(url_cards)
            
            avg_tcg, max_tcg, avg_cm, max_cm = 0.0, 0.0, 0.0, 0.0
            
            if res_cards.status_code == 200:
                cards = res_cards.json().get('data', [])
                
                # Precios TCGplayer
                tcg_prices = [c.get('tcgplayer', {}).get('prices', {}).get('holofoil', {}).get('market', 0) for c in cards]
                tcg_prices = [p for p in tcg_prices if p and p > 0]
                if tcg_prices:
                    avg_tcg = sum(tcg_prices) / len(tcg_prices)
                    max_tcg = max(tcg_prices)
                
                # Precios Cardmarket
                cm_prices = [c.get('cardmarket', {}).get('prices', {}).get('trendPrice', 0) for c in cards]
                cm_prices = [p for p in cm_prices if p and p > 0]
                if cm_prices:
                    avg_cm = sum(cm_prices) / len(cm_prices)
                    max_cm = max(cm_prices)
                
            c.execute('''
                INSERT OR REPLACE INTO set_prices_daily 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (s['id'], today, avg_tcg, max_tcg, avg_cm, max_cm))
            
            progress_bar.progress((index + 1) / min(total_sets, 50))
            
        conn.commit()
        st.toast("¡Base de datos actualizada con éxito!", icon="✅")
    conn.close()

# INTERFAZ MÓVIL
st.title("📈 TCG Multi-Market Tracker")

if st.button("🔄 Sincronizar / Reiniciar Datos"):
    with st.spinner("Actualizando catálogo y precios de mercado..."):
        sync_pokemon_data()

try:
    conn = sqlite3.connect(DB_NAME)
    df_sets = pd.read_sql_query("SELECT * FROM sets ORDER BY release_date DESC", conn)
    df_prices = pd.read_sql_query("SELECT * FROM set_prices_daily", conn)
    conn.close()

    if not df_prices.empty and not df_sets.empty:
        df = pd.merge(df_prices, df_sets, left_on="set_id", right_on="id")
        
        st.divider()
        st.subheader("🔍 Filtros de Búsqueda")
        
        search_query = st.text_input("Buscar por nombre:", placeholder="Ej. 151, Crown, Base...")
        selected_series = st.selectbox("Filtrar por era:", ["Todas"] + list(df['series'].unique()))
        
        if search_query:
            df = df[df['name'].str.contains(search_query, case=False, na=False)]
        if selected_series != "Todas":
            df = df[df['series'] == selected_series]
            
        st.subheader(f"🔥 Expansiones ({len(df)})")
        
        for index, row in df.iterrows():
            with st.container():
                st.markdown(f"### {row['name']}")
                st.caption(f"Serie: {row['series']} • Lanzamiento: {row['release_date']}")
                
                st.markdown("**🇺🇸 TCGplayer (USD)**")
                t1, t2 = st.columns(2)
                t1.metric("Promedio Top", f"${row.get('avg_tcgplayer', 0.0):.2f}")
                t2.metric("Carta Top", f"${row.get('max_tcgplayer', 0.0):.2f}")
                
                st.markdown("**🇪🇺 Cardmarket (EUR Trend)**")
                c1, c2 = st.columns(2)
                c1.metric("Promedio Top", f"€{row.get('avg_cardmarket', 0.0):.2f}")
                c2.metric("Carta Top", f"€{row.get('max_cardmarket', 0.0):.2f}")
                
                st.divider()
    else:
        st.info("Presiona el botón superior **'🔄 Sincronizar / Reiniciar Datos'** para cargar la base de datos por primera vez.")
except Exception as e:
    st.warning("Estructura de datos en actualización. Por favor presiona el botón **'🔄 Sincronizar / Reiniciar Datos'** arriba.")
    

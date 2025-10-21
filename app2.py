import os
from datetime import date
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_plotly_events import plotly_events

# -------------------------------
# Configuration de la page
# -------------------------------
st.set_page_config(
    page_title="Press Release Radar",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -------------------------------
# CSS
# -------------------------------
st.markdown("""
<style>
body { background-color: #fafafa; }
.sidebar .block-container {
    width: 340px !important; /* élargit la barre latérale */
}
.metric-container {
    display: flex;
    justify-content: space-between;
    gap: 1.2rem;
    margin-top: 1rem;
    margin-bottom: 2rem;
}
.metric-card {
    flex: 1;
    background: linear-gradient(180deg, #ffffff 0%, #f8f9fb 100%);
    border: 1px solid rgba(0,0,0,0.05);
    border-radius: 18px;
    padding: 22px 24px;
    box-shadow: 0 3px 10px rgba(0,0,0,0.05);
    text-align: center;
}
.metric-title { font-size: 0.95rem; color: #666; margin-bottom: 8px; font-weight: 500; }
.metric-value { font-size: 2rem; font-weight: 600; color: #222; }

/* Carte de détails colorée et animée */
.detail-card {
    padding: 22px;
    border-radius: 14px;
    color: white;
    margin-top: 25px;
    animation: fadeIn 0.7s ease-in-out;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}
@keyframes fadeIn {
    from {opacity: 0; transform: translateY(10px);}
    to {opacity: 1; transform: translateY(0);}
}
.detail-card h3 { margin-top: 0; margin-bottom: 10px; font-weight: 700; }
.detail-card p { line-height: 1.5em; }
.detail-card a { color: white; text-decoration: underline; }
</style>
""", unsafe_allow_html=True)

# -------------------------------
# Chargement du CSV
# -------------------------------
@st.cache_data(show_spinner=False)
def load_data():
    csv_path = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")
    if not os.path.exists(csv_path):
        st.error(f"Fichier CSV introuvable : {csv_path}")
        st.stop()
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    return df

df = load_data()

# -------------------------------
# Filtres
# -------------------------------
with st.sidebar:
    st.header("🔎 Filtres")

    companies = sorted(df["company"].dropna().unique())
    selected_companies = st.multiselect("Compagnies", companies, default=companies)

    valid_dates = df["date"].dropna()
    min_d, max_d = valid_dates.min(), valid_dates.max()
    selected_range = st.date_input("Période", value=(min_d, max_d), min_value=min_d, max_value=max_d)

    query = st.text_input("Recherche texte (titre, résumé, impact)", "")

# -------------------------------
# Filtrage
# -------------------------------
def filter_df(df, companies, date_range, query):
    f = df.copy()
    if companies:
        f = f[f["company"].isin(companies)]
    if date_range and all(date_range):
        start, end = date_range
        f = f[(f["date"] >= start) & (f["date"] <= end)]
    if query:
        q = query.lower()
        f = f[
            f["title"].str.lower().str.contains(q, na=False)
            | f["description"].str.lower().str.contains(q, na=False)
            | f["summary_ai"].str.lower().str.contains(q, na=False)
            | f["impact_for_zhone"].str.lower().str.contains(q, na=False)
        ]
    return f.sort_values("date", ascending=False)

filtered = filter_df(df, selected_companies, selected_range, query)

# -------------------------------
# En-tête
# -------------------------------
st.title("🛰️ Press Release Radar")
st.caption("Cliquez sur un point de la timeline pour voir les détails correspondants ci-dessous.")

by_co = filtered.groupby("company")["id"].count().sort_values(ascending=False)
top_co = by_co.index[0] if not by_co.empty else "—"
earliest = filtered["date"].min()
latest = filtered["date"].max()

st.markdown(f"""
<div class="metric-container">
  <div class="metric-card"><div class="metric-title">Communiqués</div><div class="metric-value">{len(filtered):,}</div></div>
  <div class="metric-card"><div class="metric-title">Top émetteur</div><div class="metric-value">{top_co}</div></div>
  <div class="metric-card"><div class="metric-title">Plus ancien</div><div class="metric-value">{earliest if pd.notna(earliest) else '—'}</div></div>
  <div class="metric-card"><div class="metric-title">Plus récent</div><div class="metric-value">{latest if pd.notna(latest) else '—'}</div></div>
</div>
""", unsafe_allow_html=True)

# -------------------------------
# Timeline interactive cliquable
# -------------------------------
if not filtered.empty:
    tl = filtered.copy()
    tl["y"] = tl["company"]

    COLOR_MAP = {
        "Calix": "#00b894",
        "Nokia": "#0984e3",
        "Huawei": "#d63031",
        "Adtran": "#6c5ce7",
    }

    fig = px.scatter(
        tl,
        x="date",
        y="y",
        color="company",
        hover_name="title",
        custom_data=["id"],
        color_discrete_map=COLOR_MAP,
        template="plotly_white",
    )
    fig.update_traces(marker=dict(size=12, line=dict(width=0.5, color="rgba(0,0,0,.3)")))
    fig.update_layout(
        title="🗓️ Timeline des communiqués (cliquable)",
        xaxis_title="Date",
        yaxis_title="Compagnie",
        hovermode="closest",
        height=420,
        margin=dict(l=20, r=20, t=60, b=20),
        legend_title_text="Compagnie",
    )

    selected_points = plotly_events(fig, click_event=True, hover_event=False)

    def _select_row_from_event(ev):
        if not ev:
            return None
        cd = ev.get("customdata", None)
        if cd is not None:
            sel_id = cd[0] if isinstance(cd, (list, tuple)) else cd
            match = filtered[filtered["id"] == sel_id]
            if not match.empty:
                return match.iloc[0]
        x, y = ev.get("x", None), ev.get("y", None)
        try:
            x_date = pd.to_datetime(x).date() if x else None
        except Exception:
            x_date = None
        subset = filtered.copy()
        if x_date is not None:
            subset = subset[subset["date"] == x_date]
        if y is not None:
            subset = subset[subset["company"] == y]
        return subset.iloc[0] if len(subset) else None

    row = _select_row_from_event(selected_points[0]) if selected_points else None

    # --- Détails sous la timeline ---
    if row is not None:
        color = COLOR_MAP.get(row["company"], "#333")
        st.markdown(
            f"""
            <div class="detail-card" style="background:{color};">
                <h3>📄 {row['company']} — {row['title']}</h3>
                <p><strong>Date :</strong> {row['date']}</p>
                <p><strong>Description :</strong> {row.get('description','')}</p>
                <p><strong>Résumé AI :</strong> {row.get('summary_ai','')}</p>
                <p><strong>Impact pour Zhone Technologies :</strong> {row.get('impact_for_zhone','')}</p>
                <p><a href="{row['link']}" target="_blank">🔗 Lire le communiqué complet</a></p>
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.info("Aucun communiqué trouvé avec ces filtres.")

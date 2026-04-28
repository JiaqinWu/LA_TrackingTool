import uuid
from datetime import datetime, date

import altair as alt
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# -----------------------------
# Page & theme
# -----------------------------
st.set_page_config(
    page_title="LA Outreach Tracking",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

THEME = {
    "accent": "#0d9488",
    "accent_soft": "#ccfbf1",
    "ink": "#0f172a",
    "muted": "#64748b",
    "surface": "#f8fafc",
    "border": "#e2e8f0",
}


def inject_styles():
    """Custom CSS: typography, metrics, tabs, tables."""
    st.markdown(
        f"""
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Source+Serif+4:opsz,wght@8..60,600&display=swap" rel="stylesheet">
        <style>
            html, body, [class*="stApp"] {{
                font-family: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, sans-serif;
                color: {THEME["ink"]};
            }}
            .block-container {{
                padding-top: 1.25rem;
                max-width: 1200px;
            }}
            .la-hero {{
                padding: 1.5rem 0 0.5rem 0;
                border-bottom: 1px solid {THEME["border"]};
                margin-bottom: 1.25rem;
            }}
            .la-hero .eyebrow {{
                font-size: 0.75rem;
                font-weight: 600;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: {THEME["accent"]};
                margin: 0 0 0.35rem 0;
            }}
            .la-hero h1 {{
                font-family: "Source Serif 4", Georgia, serif;
                font-size: clamp(1.75rem, 3vw, 2.25rem);
                font-weight: 600;
                line-height: 1.15;
                margin: 0 0 0.5rem 0;
                color: {THEME["ink"]};
            }}
            .la-hero .sub {{
                font-size: 1rem;
                color: {THEME["muted"]};
                margin: 0;
                max-width: 42rem;
                line-height: 1.5;
            }}
            div[data-testid="stMetric"] {{
                background: linear-gradient(145deg, #ffffff 0%, {THEME["surface"]} 100%);
                border: 1px solid {THEME["border"]};
                border-radius: 12px;
                padding: 0.85rem 1rem;
                box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
            }}
            div[data-testid="stMetric"] label {{
                color: {THEME["muted"]} !important;
                font-weight: 500 !important;
                font-size: 0.8rem !important;
            }}
            div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
                color: {THEME["ink"]} !important;
                font-weight: 700 !important;
            }}
            .stTabs [data-baseweb="tab-list"] {{
                gap: 6px;
                background-color: transparent;
                border-bottom: 1px solid {THEME["border"]};
                padding-bottom: 0;
            }}
            .stTabs [data-baseweb="tab"] {{
                border-radius: 8px 8px 0 0;
                padding: 0.6rem 1rem;
                font-weight: 500;
            }}
            .stTabs [aria-selected="true"] {{
                color: {THEME["accent"]} !important;
            }}
            section[data-testid="stSidebar"] {{
                background: linear-gradient(180deg, #f1f5f9 0%, #ffffff 28%);
                border-right: 1px solid {THEME["border"]};
            }}
            section[data-testid="stSidebar"] .block-container {{
                padding-top: 1.5rem;
            }}
            section[data-testid="stSidebar"] h1,
            section[data-testid="stSidebar"] h2,
            section[data-testid="stSidebar"] h3 {{
                font-size: 0.95rem !important;
                font-weight: 600 !important;
                color: {THEME["ink"]} !important;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }}
            div[data-testid="stExpander"] details {{
                border: 1px solid {THEME["border"]};
                border-radius: 10px;
                background: #fff;
            }}
            footer {{ visibility: hidden; height: 0; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero():
    st.markdown(
        """
        <div class="la-hero">
            <p class="eyebrow">Community outreach · Los Angeles</p>
            <h1>Outreach tracking dashboard</h1>
            <p class="sub">Filter caseloads, review activity, add clients, and log contacts—synced with your Google Sheet.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def bar_chart_counts(df: pd.DataFrame, x_col: str, title_x: str, color_scheme: str = "tealblues"):
    """Altair bar chart with consistent styling."""
    if df.empty or x_col not in df.columns:
        return None
    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=4, size=28)
        .encode(
            x=alt.X(f"{x_col}:N", sort="-y", title=title_x),
            y=alt.Y("count:Q", title="Count"),
            color=alt.Color(
                f"{x_col}:N",
                legend=None,
                scale=alt.Scale(scheme=color_scheme),
            ),
            tooltip=[alt.Tooltip(f"{x_col}:N", title=title_x), alt.Tooltip("count:Q", title="Count")],
        )
        .properties(height=300)
        .configure_axis(labelLimit=200, titleFontWeight=500)
        .configure_view(stroke=None)
    )
    return chart


inject_styles()
render_hero()

# -----------------------------
# Configuration
# -----------------------------
CLIENTS_SHEET = "Clients"
LOG_SHEET = "Outreach_Log"

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# -----------------------------
# Google Sheets connection
# -----------------------------
@st.cache_resource
def get_gspread_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPE,
    )
    return gspread.authorize(creds)

@st.cache_resource
def get_workbook():
    client = get_gspread_client()
    sheet_url = st.secrets["app"]["sheet_url"]
    return client.open_by_url(sheet_url)

def get_worksheet(name: str):
    wb = get_workbook()
    return wb.worksheet(name)

@st.cache_data(ttl=60)
def load_clients() -> pd.DataFrame:
    ws = get_worksheet(CLIENTS_SHEET)
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        df = pd.DataFrame(columns=[
            "client_id", "dob", "phone_1", "phone_2","text_consent",
            "email", "social_media_profile", "risk_factor", "current_status","notes",
            "assigned_staff",  "created_at", "updated_at"
        ])
    return df

@st.cache_data(ttl=60)
def load_logs() -> pd.DataFrame:
    ws = get_worksheet(LOG_SHEET)
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        df = pd.DataFrame(columns=[
            "log_id", "client_id", "contact_date", "contact_method",
            "outreach_status", "outcome", "location", "staff_name",
            "next_followup_date", "notes", "created_at"
        ])
    return df

def append_row(sheet_name: str, row: list):
    ws = get_worksheet(sheet_name)
    ws.append_row(row, value_input_option="USER_ENTERED")
    st.cache_data.clear()

def ensure_sheet_headers():
    """Run once if sheets are blank."""
    clients_ws = get_worksheet(CLIENTS_SHEET)
    logs_ws = get_worksheet(LOG_SHEET)

    if not clients_ws.get_all_values():
        clients_ws.append_row([
            "client_id", "dob", "phone_1", "phone_2",
            "email", "text_consent", "social_media_profile", "risk_factor", "current_status",
            "assigned_staff", "notes", "created_at", "updated_at"
        ])

    if not logs_ws.get_all_values():
        logs_ws.append_row([
            "log_id", "client_id", "contact_date", "contact_method",
            "outreach_status", "outcome", "location", "staff_name",
            "next_followup_date", "notes", "created_at"
        ])

# -----------------------------
# Helper functions
# -----------------------------
def safe_to_datetime(series):
    return pd.to_datetime(series, errors="coerce")

def prep_data():
    clients = load_clients().copy()
    logs = load_logs().copy()

    if "dob" in clients.columns:
        clients["dob"] = safe_to_datetime(clients["dob"]).dt.date

    if "contact_date" in logs.columns:
        logs["contact_date"] = safe_to_datetime(logs["contact_date"]).dt.date

    if "next_followup_date" in logs.columns:
        logs["next_followup_date"] = safe_to_datetime(logs["next_followup_date"]).dt.date

    return clients, logs

def latest_log_per_client(logs: pd.DataFrame) -> pd.DataFrame:
    if logs.empty:
        return pd.DataFrame()
    temp = logs.copy()
    temp["contact_date_sort"] = pd.to_datetime(temp["contact_date"], errors="coerce")
    temp = temp.sort_values(["client_id", "contact_date_sort"])
    return temp.groupby("client_id", as_index=False).tail(1)

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.caption("Sheet & filters")
    with st.expander("Setup", expanded=False):
        if st.button("Initialize sheet headers", use_container_width=True):
            ensure_sheet_headers()
            st.success("Headers checked/initialized.")

clients, logs = prep_data()

with st.sidebar:
    st.divider()
    staff_options = ["All"] + sorted([x for x in clients.get("assigned_staff", pd.Series(dtype=str)).dropna().unique() if str(x).strip()])
    selected_staff = st.selectbox("Assigned staff", staff_options)

    status_options = ["All"] + sorted([x for x in clients.get("current_status", pd.Series(dtype=str)).dropna().unique() if str(x).strip()])
    selected_status = st.selectbox("Client status", status_options)

    method_options = ["All"]
    if not logs.empty and "contact_method" in logs.columns:
        method_options += sorted([x for x in logs["contact_method"].dropna().unique() if str(x).strip()])
    selected_method = st.selectbox("Contact method", method_options)

# -----------------------------
# Apply filters
# -----------------------------
filtered_clients = clients.copy()
filtered_logs = logs.copy()

if selected_staff != "All":
    filtered_clients = filtered_clients[filtered_clients["assigned_staff"] == selected_staff]

if selected_status != "All":
    filtered_clients = filtered_clients[filtered_clients["current_status"] == selected_status]

if selected_method != "All" and not filtered_logs.empty:
    filtered_logs = filtered_logs[filtered_logs["contact_method"] == selected_method]

if not filtered_logs.empty and not filtered_clients.empty:
    filtered_logs = filtered_logs[filtered_logs["client_id"].isin(filtered_clients["client_id"])]

# -----------------------------
# KPIs
# -----------------------------
latest_logs = latest_log_per_client(filtered_logs)

total_clients = len(filtered_clients)
total_logs = len(filtered_logs)
contacted_clients = filtered_logs["client_id"].nunique() if not filtered_logs.empty else 0

overdue_followups = 0
if not latest_logs.empty and "next_followup_date" in latest_logs.columns:
    overdue_followups = latest_logs["next_followup_date"].apply(
        lambda x: pd.notna(x) and x < date.today()
    ).sum()

st.caption("Overview · current filters")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total clients", f"{total_clients:,}")
col2.metric("Outreach attempts", f"{total_logs:,}")
col3.metric("Clients contacted", f"{contacted_clients:,}")
col4.metric("Overdue follow-ups", f"{int(overdue_followups):,}")

st.divider()

# -----------------------------
# Tabs
# -----------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "Dashboard",
    "Client search",
    "Add client",
    "Log outreach",
])

# -----------------------------
# TAB 1: Dashboard
# -----------------------------
with tab1:
    left, right = st.columns([1, 1])

    with left:
        st.subheader("Clients by status")
        if not filtered_clients.empty and "current_status" in filtered_clients.columns:
            status_counts = (
                filtered_clients["current_status"]
                .fillna("Unknown")
                .value_counts()
                .rename_axis("status")
                .reset_index(name="count")
            )
            c = bar_chart_counts(status_counts, "status", "Status")
            if c:
                st.altair_chart(c, use_container_width=True)
        else:
            st.info("No client status data yet.")

    with right:
        st.subheader("Outreach by method")
        if not filtered_logs.empty and "contact_method" in filtered_logs.columns:
            method_counts = (
                filtered_logs["contact_method"]
                .fillna("Unknown")
                .value_counts()
                .rename_axis("method")
                .reset_index(name="count")
            )
            c = bar_chart_counts(method_counts, "method", "Method", color_scheme="blues")
            if c:
                st.altair_chart(c, use_container_width=True)
        else:
            st.info("No outreach log data yet.")

    st.subheader("Recent outreach activity")
    if not filtered_logs.empty:
        recent_cols = [
            c for c in [
                "contact_date", "client_id", "contact_method", "outreach_status",
                "outcome", "staff_name", "next_followup_date", "notes"
            ] if c in filtered_logs.columns
        ]
        recent_view = filtered_logs.copy()
        recent_view["contact_date_sort"] = pd.to_datetime(recent_view["contact_date"], errors="coerce")
        recent_view = recent_view.sort_values("contact_date_sort", ascending=False)
        st.dataframe(
            recent_view[recent_cols].head(20),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No outreach activity yet.")

# -----------------------------
# TAB 2: Client Search
# -----------------------------
with tab2:
    st.subheader("Search clients")
    search = st.text_input(
        "Search by client ID, phone, or email",
        placeholder="Type to filter…",
    )

    search_df = filtered_clients.copy()
    if search:
        q = search.strip().lower()

        def row_match(row):
            values = [
                str(row.get("client_id", "")),
                str(row.get("phone_1", "")),
                str(row.get("phone_2", "")),
                str(row.get("email", "")),
            ]
            return any(q in v.lower() for v in values)

        search_df = search_df[search_df.apply(row_match, axis=1)]

    display_cols = [
        c for c in [
            "client_id",
            "dob",
            "phone_1",
            "phone_2",
            "email",
            "text_consent",
            "social_media_profile",
            "risk_factor",
            "current_status",
            "assigned_staff",
        ] if c in search_df.columns
    ]
    st.dataframe(search_df[display_cols], use_container_width=True, hide_index=True)

    st.subheader("Client detail")
    if not search_df.empty:
        client_ids = search_df["client_id"].astype(str).tolist()
        selected_client = st.selectbox("Select client", client_ids)
        client_row = search_df[search_df["client_id"].astype(str) == selected_client].iloc[0]

        info_col1, info_col2 = st.columns(2)
        with info_col1:
            st.markdown("**Demographics & contact**")
            st.write(f"**DOB:** {client_row.get('dob', '')}")
            st.write(f"**Phone 1:** {client_row.get('phone_1', '')}")
            st.write(f"**Phone 2:** {client_row.get('phone_2', '')}")
            st.write(f"**Email:** {client_row.get('email', '')}")
            st.write(f"**Text consent:** {client_row.get('text_consent', '')}")
        with info_col2:
            st.markdown("**Case**")
            st.write(f"**Social profile:** {client_row.get('social_media_profile', '')}")
            st.write(f"**Risk factor:** {client_row.get('risk_factor', '')}")
            st.write(f"**Current status:** {client_row.get('current_status', '')}")
            st.write(f"**Assigned staff:** {client_row.get('assigned_staff', '')}")

        notes_val = client_row.get("notes", "")
        if str(notes_val).strip():
            st.markdown("**Notes**")
            st.info(str(notes_val))

        st.markdown("#### Outreach history")
        if not logs.empty:
            client_logs = logs[logs["client_id"].astype(str) == str(selected_client)].copy()
            if not client_logs.empty:
                client_logs["contact_date_sort"] = pd.to_datetime(client_logs["contact_date"], errors="coerce")
                client_logs = client_logs.sort_values("contact_date_sort", ascending=False)

                history_cols = [
                    c for c in [
                        "contact_date", "contact_method", "outreach_status", "outcome",
                        "location", "staff_name", "next_followup_date", "notes"
                    ] if c in client_logs.columns
                ]
                st.dataframe(client_logs[history_cols], use_container_width=True, hide_index=True)
            else:
                st.info("No outreach history for this client yet.")

# -----------------------------
# TAB 3: Add Client
# -----------------------------
with tab3:
    st.subheader("Add new client")

    with st.form("add_client_form"):
        c1, c2 = st.columns(2)
        with c1:
            dob = st.date_input("DOB", value=None)
            phone_1 = st.text_input("Phone 1")
            phone_2 = st.text_input("Phone 2")
            email = st.text_input("Email")
            risk_factor = st.selectbox("Risk factor", ["Low", "Medium", "High"])
        with c2:
            text_consent = st.selectbox("Text consent", ["Yes", "No", "Unknown"])
            social_media_profile = st.text_input("Social media profile")
            assigned_staff = st.text_input("Assigned staff")
            current_status = st.selectbox("Current status", ["Active","At Risk","Out of Care"])

        notes = st.text_area("Notes")

        submitted = st.form_submit_button("Save client", type="primary", use_container_width=True)

        if submitted:
            client_id = str(uuid.uuid4())[:8]
            now_str = datetime.now().strftime("%Y-%m-%d")

            row = [
                client_id,
                dob.isoformat() if dob else "",
                phone_1,
                phone_2,
                email,
                text_consent,
                social_media_profile,
                risk_factor,
                current_status,
                notes,
                assigned_staff,
                now_str,
                now_str,
            ]
            append_row(CLIENTS_SHEET, row)
            st.success(f"Client saved. New client_id: **{client_id}**")

# -----------------------------
# TAB 4: Log Outreach
# -----------------------------
with tab4:
    st.subheader("Add outreach log")

    if filtered_clients.empty:
        st.warning("Add clients first before logging outreach.")
    else:
        client_options = (
            filtered_clients[["client_id"]]
            .fillna("")
            .assign(label=lambda d: d["client_id"].astype(str))
        )

        with st.form("log_outreach_form"):
            selected_label = st.selectbox("Client", client_options["label"].tolist())
            selected_client_id = selected_label.split(" - ")[0]

            col_a, col_b = st.columns(2)
            with col_a:
                contact_date = st.date_input("Contact date", value=date.today())
                contact_method = st.selectbox("Contact method", [
                    "Phone", "Text", "Email", "In-person", "Social Media", "Other"
                ])
                outreach_status = st.selectbox("Outreach status", [
                    "Attempted", "Reached", "No Answer", "Left Message", "Invalid Contact", "Closed"
                ])

            with col_b:
                outcome = st.text_input("Outcome")
                location = st.text_input("Location")
                staff_name = st.text_input("Staff name")

            next_followup_date = st.date_input("Next follow-up date", value=None)
            notes = st.text_area("Notes")

            submitted_log = st.form_submit_button("Save outreach log", type="primary", use_container_width=True)

            if submitted_log:
                log_id = str(uuid.uuid4())[:10]
                now_str = datetime.now().strftime("%Y-%m-%d")

                row = [
                    log_id,
                    selected_client_id,
                    contact_date.isoformat() if contact_date else "",
                    contact_method,
                    outreach_status,
                    outcome,
                    location,
                    staff_name,
                    next_followup_date.isoformat() if next_followup_date else "",
                    notes,
                    now_str,
                ]
                append_row(LOG_SHEET, row)
                st.success("Outreach log saved.")

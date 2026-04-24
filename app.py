import uuid
from datetime import datetime, date

import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Los Angeles Outreach Tracking Dashboard", layout="wide")

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
            "client_id", "first_name", "last_name", "dob", "phone_1", "phone_2",
            "email", "text_consent", "address", "risk_level", "current_status",
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
# App header
# -----------------------------
st.title("Los Angeles Outreach Tracking Dashboard")

with st.sidebar:
    st.header("Setup")
    if st.button("Initialize sheet headers"):
        ensure_sheet_headers()
        st.success("Headers checked/initialized.")

clients, logs = prep_data()

# -----------------------------
# Sidebar filters
# -----------------------------
with st.sidebar:
    st.header("Filters")

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

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Clients", total_clients)
col2.metric("Outreach Attempts", total_logs)
col3.metric("Clients Contacted", contacted_clients)
col4.metric("Overdue Follow-ups", int(overdue_followups))

st.divider()

# -----------------------------
# Tabs
# -----------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "Dashboard", "Client Search", "Add Client", "Log Outreach"
])

# -----------------------------
# TAB 1: Dashboard
# -----------------------------
with tab1:
    left, right = st.columns([1, 1])

    with left:
        st.subheader("Clients by Status")
        if not filtered_clients.empty and "current_status" in filtered_clients.columns:
            status_counts = (
                filtered_clients["current_status"]
                .fillna("Unknown")
                .value_counts()
                .rename_axis("status")
                .reset_index(name="count")
            )
            st.bar_chart(status_counts.set_index("status"))
        else:
            st.info("No client status data yet.")

    with right:
        st.subheader("Outreach by Method")
        if not filtered_logs.empty and "contact_method" in filtered_logs.columns:
            method_counts = (
                filtered_logs["contact_method"]
                .fillna("Unknown")
                .value_counts()
                .rename_axis("method")
                .reset_index(name="count")
            )
            st.bar_chart(method_counts.set_index("method"))
        else:
            st.info("No outreach log data yet.")

    st.subheader("Recent Outreach Activity")
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
        st.dataframe(recent_view[recent_cols].head(20), use_container_width=True)
    else:
        st.info("No outreach activity yet.")

# -----------------------------
# TAB 2: Client Search
# -----------------------------
with tab2:
    st.subheader("Search Client")
    search = st.text_input("Search by client ID, name, phone, or email")

    search_df = filtered_clients.copy()
    if search:
        q = search.strip().lower()

        def row_match(row):
            values = [
                str(row.get("client_id", "")),
                str(row.get("full_name", "")),
                str(row.get("phone_1", "")),
                str(row.get("phone_2", "")),
                str(row.get("email", "")),
            ]
            return any(q in v.lower() for v in values)

        search_df = search_df[search_df.apply(row_match, axis=1)]

    display_cols = [
        c for c in [
            "client_id", "full_name", "dob", "phone_1", "email",
            "risk_level", "current_status", "assigned_staff"
        ] if c in search_df.columns
    ]
    st.dataframe(search_df[display_cols], use_container_width=True)

    st.subheader("Client Detail")
    if not search_df.empty:
        client_ids = search_df["client_id"].astype(str).tolist()
        selected_client = st.selectbox("Select client", client_ids)
        client_row = search_df[search_df["client_id"].astype(str) == selected_client].iloc[0]

        info_col1, info_col2 = st.columns(2)
        with info_col1:
            st.write(f"**DOB:** {client_row.get('dob', '')}")
            st.write(f"**Phone 1:** {client_row.get('phone_1', '')}")
            st.write(f"**Text Consent:** {client_row.get('text_consent', '')}")
            st.write(f"**Email:** {client_row.get('email', '')}")
            st.write(f"**Social Media Profile:** {client_row.get('social_media_profile', '')}")
            st.write(f"**Risk Factor:** {client_row.get('risk_factor', '')}")
            st.write(f"**Current Status:** {client_row.get('current_status', '')}")
            st.write(f"**Assigned Staff:** {client_row.get('assigned_staff', '')}")

        st.markdown("#### Outreach History")
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
                st.dataframe(client_logs[history_cols], use_container_width=True)
            else:
                st.info("No outreach history for this client yet.")

# -----------------------------
# TAB 3: Add Client
# -----------------------------
with tab3:
    st.subheader("Add New Client")

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
            current_status = st.selectbox("Current status", ["Open", "Active Outreach", "Pending Follow-up", "Closed", "Escalated"])

        notes = st.text_area("Notes")

        submitted = st.form_submit_button("Save Client")

        if submitted:
            client_id = str(uuid.uuid4())[:8]
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
            st.success(f"Client saved. New client_id: {client_id}")

# -----------------------------
# TAB 4: Log Outreach
# -----------------------------
with tab4:
    st.subheader("Add Outreach Log")

    if filtered_clients.empty:
        st.warning("Add clients first before logging outreach.")
    else:
        client_options = (
            filtered_clients[["client_id", "full_name"]]
            .fillna("")
            .assign(label=lambda d: d["client_id"].astype(str) + " - " + d["full_name"].astype(str))
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

            submitted_log = st.form_submit_button("Save Outreach Log")

            if submitted_log:
                log_id = str(uuid.uuid4())[:10]
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
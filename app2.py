
GEMINI_API_KEY = st.secrets.get("GOOGLE_API_KEY", None)
DB_URL='postgresql://postgres.hnbvlalatrskmnwhnxwa:/vW9dn#2$C?,7%40k@aws-1-ap-south-1.pooler.supabase.com:5432/postgres'

import json
import re

import pandas as pd
import streamlit as st

from google import genai
from sqlalchemy import create_engine, text

# =========================
# CONFIG
# =========================

if not GEMINI_API_KEY:
    st.error("GOOGLE_API_KEY belum diset di Streamlit Secrets")
    st.stop()

if not DB_URL:
    st.error("DATABASE_URL belum diset di Streamlit Secrets")
    st.stop()

# =========================
# GEMINI CLIENT
# =========================

@st.cache_resource
def get_client():
    return genai.Client(api_key=GEMINI_API_KEY)

client = get_client()

# =========================
# DATABASE
# =========================

@st.cache_resource
def get_engine():
    return create_engine(DB_URL)

engine = get_engine()

# =========================
# SCHEMA
# =========================

SCHEMA_STR = """
employees(
    nip PRIMARY KEY,
    nama,
    divisi,
    jabatan,
    join_date
)

trainings(
    training_id PRIMARY KEY,
    nama_diklat,
    tanggal
)

enrollments(
    nip PRIMARY KEY FOREIGN KEY REFERENCES employees(nip),
    training_id PRIMARY KEY FOREIGN KEY REFERENCES trainings(training_id),
    status,
    nilai
)
"""

# =========================
# PROMPT
# =========================

def build_prompt(question: str) -> str:
    return f"""
Anda adalah generator SQL PostgreSQL.

Schema database:

{SCHEMA_STR}

Aturan:
- HANYA hasilkan SATU query PostgreSQL SELECT.
- Jangan gunakan INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE.
- Jangan gunakan markdown.
- Jangan gunakan penjelasan.
- Output hanya SQL.

Pertanyaan:
{question}

SQL:
"""

# =========================
# PARSER SQL
# =========================

def ambil_sql(text_response) -> str:
    if isinstance(text_response, dict):

        if "sql" in text_response:
            return str(text_response["sql"]).strip().rstrip(";")

        args = text_response.get("arguments", {})

        if isinstance(args, dict) and "sql" in args:
            return str(args["sql"]).strip().rstrip(";")

        text_response = json.dumps(text_response)

    teks = str(text_response).strip()

    m = re.search(r"```(?:sql)?\s*(.*?)```", teks, re.I | re.S)
    if m:
        teks = m.group(1).strip()

    if teks.startswith("{"):
        try:
            obj = json.loads(teks)
            if "sql" in obj:
                teks = obj["sql"]
        except Exception:
            pass

    m = re.search(r"(select\b.*)", teks, re.I | re.S)
    if m:
        teks = m.group(1)

    return teks.strip().rstrip(";")

# =========================
# GENERATE SQL
# =========================

def generate_sql(question: str) -> str:
    prompt = build_prompt(question)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    return ambil_sql(response.text)

# =========================
# VALIDATE SQL
# =========================

FORBIDDEN = [
    "drop",
    "delete",
    "update",
    "insert",
    "alter",
    "truncate",
    "create",
    "grant",
]

def validate_sql(sql: str) -> bool:

    if not sql:
        return False

    s = sql.lower().strip()

    if not s.startswith("select"):
        return False

    for keyword in FORBIDDEN:
        if keyword in s:
            return False

    if s.count(";") > 1:
        return False

    if ";" in s and not s.endswith(";"):
        return False

    return True

# =========================
# EXECUTE SQL
# =========================

def run_sql(sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)

def run_sql_safe(sql: str):
    try:
        return run_sql(sql), None
    except Exception as e:
        return None, str(e)

# =========================
# VISUALIZE
# =========================

def visualize(df: pd.DataFrame):

    if df is None or df.empty:
        st.info("Tidak ada data.")
        return

    if len(df.columns) != 2:
        st.dataframe(df, use_container_width=True)
        return

    col1, col2 = df.columns

    if pd.api.types.is_numeric_dtype(df[col2]):
        st.bar_chart(df.set_index(col1))
    else:
        st.dataframe(df, use_container_width=True)

# =========================
# PIPELINE
# =========================

def ask(question: str):

    sql = generate_sql(question)

    if not validate_sql(sql):

        sql = generate_sql(question)

        if not validate_sql(sql):
            return None, pd.DataFrame(
                {"error": ["Gagal menghasilkan SQL yang aman"]}
            )

    df, err = run_sql_safe(sql)

    if err:
        return sql, pd.DataFrame({"error": [err]})

    return sql, df

# =========================
# STREAMLIT UI
# =========================

st.title("NL2SQL Chat App")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for role, content in st.session_state.chat_history:

    with st.chat_message(role):
        st.write(content)

question = st.chat_input("Tanyakan sesuatu...")

if question:

    st.session_state.chat_history.append(("user", question))

    with st.chat_message("user"):
        st.write(question)

    sql, df = ask(question)

    with st.chat_message("assistant"):

        if sql is None:
            st.error("Gagal menghasilkan SQL yang aman.")
        else:
            st.code(sql, language="sql")

            st.dataframe(df, use_container_width=True)

            visualize(df)

    st.session_state.chat_history.append(
        ("assistant", f"SQL:\n{sql}")
    )

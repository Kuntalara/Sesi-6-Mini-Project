# import streamlit as st
# import pandas as pd
# import re
# import google.generativeai as genai

# Import library utama Streamlit
import streamlit as st
# Import pandas untuk data tabel
import pandas as pd
# Import client Gemini
from google import genai
# Import 'types' untuk konfigurasi (system prompt, temperature)
from google.genai import types
import re
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
# =========================
# CONFIG
# =========================
GEMINI_API_KEY = st.secrets.get("GOOGLE_API_KEY", None)
DB_URL='postgresql://postgres.hnbvlalatrskmnwhnxwa:/vW9dn#2$C?,7@k@aws-1-ap-south-1.pooler.supabase.com:5432/postgres'
engine = create_engine(DB_URL)

# genai.configure(api_key=GEMINI_API_KEY)
client = genai.Client(api_key=GEMINI_API_KEY)
# model = genai.GenerativeModel("gemini-2.5-flash")
def generate_sql(question: str):
    prompt = build_prompt(question)

    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    sql = resp.text.strip()

    sql = re.sub(r"```sql", "", sql, flags=re.I)
    sql = sql.replace("```", "").strip()

    return sql




# =========================
# SCHEMA
# =========================
SCHEMA_STR = """
employees(nip PK, nama, divisi, jabatan, join_date)
trainings(training_id PK, nama_diklat, tanggal)
enrollments(nip PK FK, training_id PK FK, status, nilai)
"""

# =========================
# PROMPT
# =========================
def build_prompt(question: str) -> str:
    return f"""
Anda adalah SQL generator PostgreSQL.

Schema:
{SCHEMA_STR}

Aturan:
- HANYA output SQL SELECT
- Tidak boleh ada penjelasan
- Tidak boleh markdown
- 1 query saja

Pertanyaan:
{question}

SQL:
"""

# =========================
# GENERATE SQL
# =========================
# def generate_sql(question: str):
#     prompt = build_prompt(question)
#     resp = model.generate_content(prompt)
#     sql = resp.text.strip()

#     sql = re.sub(r"```sql", "", sql, flags=re.I)
#     sql = sql.replace("```", "").strip()

#     return sql

# =========================
# VALIDATE SQL
# =========================
FORBIDDEN = ["drop", "delete", "update", "insert", "alter", "truncate", "create", "grant"]

def validate_sql(sql: str) -> bool:
    if not sql or not sql.strip():
        return False

    s = sql.lower().strip()

    if not s.startswith("select"):
        return False

    for f in FORBIDDEN:
        if f in s:
            return False

    if s.count(";") > 1:
        return False

    if ";" in s and not s.endswith(";"):
        return False

    return True

# =========================
# FAKE RUN SQL (replace dengan DB kamu)
# =========================

def eksekusi(sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)

def eksekusi_aman(sql: str):
    try:
        return eksekusi(sql), None        # sukses
    except Exception as e:
        return None, str(e)               # pesan error -> umpan balik

def run_sql(sql: str):
    return pd.DataFrame({
        "message": ["run_sql belum dihubungkan ke database"]
    })

def ambil_sql(resp) -> str:
    # function calling / dict
    if isinstance(resp, dict):
        if 'sql' in resp: return str(resp['sql']).rstrip(';').strip()
        args = resp.get('arguments') or {}
        if isinstance(args, dict) and 'sql' in args:
            return str(args['sql']).rstrip(';').strip()
        resp = json.dumps(resp)
    teks = str(resp).strip()
    # buang code fence ```sql ... ```
    m = re.search(r'```(?:sql|json)?\s*(.+?)```', teks, re.S)
    if m: teks = m.group(1).strip()
    # JSON {"sql": ...}
    if teks.startswith('{'):
        try: teks = json.loads(teks).get('sql', teks)
        except Exception: pass
    # ambil mulai dari SELECT (buang teks pengantar)
    m = re.search(r'(select\b.+)', teks, re.I | re.S)
    if m: teks = m.group(1)
    return teks.rstrip(';').strip()

# Uji parser pada beberapa bentuk respons
for contoh in [
    'SELECT 1',
    '```sql\nSELECT 2\n```',
    '{"sql": "SELECT 3"}',
    {'name': 'run_sql', 'arguments': {'sql': 'SELECT 4'}},
    'Tentu, ini querinya:\nSELECT 5 FROM employee',
]:
    print(repr(ambil_sql(contoh)))

# =========================
# VISUALIZE
# =========================
def visualize(df: pd.DataFrame):
    if df is None or df.empty:
        st.write("No data")
        return

    if len(df.columns) != 2:
        st.dataframe(df)
        return

    col1, col2 = df.columns

    if pd.api.types.is_numeric_dtype(df[col2]):
        st.bar_chart(df.set_index(col1))
    else:
        st.dataframe(df)

# =========================
# ASK PIPELINE
# =========================
def ask(question: str):
    sql = generate_sql(question)

    if not validate_sql(sql):
        sql = generate_sql(question)
        if not validate_sql(sql):
            return None, None

    try:
        df = eksekusi_aman(sql)
    except Exception as e:
        return sql, pd.DataFrame({"error": [str(e)]})

    return sql, df

# =========================
# STREAMLIT UI
# =========================
st.title("NL2SQL Chat App")

if "chat" not in st.session_state:
    st.session_state.chat = []

for role, msg in st.session_state.chat:
    with st.chat_message(role):
        st.write(msg)

question = st.chat_input("Tanyakan SQL...")

if question:
    st.session_state.chat.append(("user", question))

    sql, df = ask(question)

    with st.chat_message("assistant"):
        if sql is None:
            st.write("Gagal menghasilkan SQL aman.")
        else:
            st.code(sql, language="sql")
            st.dataframe(df)
            visualize(df)

    st.session_state.chat.append(("assistant", f"SQL: {sql}"))

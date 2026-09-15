import json
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

@st.cache_resource
def init_gspread():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Secrets에 저장된 json_cert 텍스트를 파이썬 사전(dict)으로 파싱
    raw_json = st.secrets["gcp_service_account"]["json_cert"]
    creds_dict = json.loads(raw_json, strict=False)

    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    url = st.secrets["sheets"]["spreadsheet_url"]
    doc = client.open_by_url(url)
    return doc

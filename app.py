import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

@st.cache_resource
def init_gspread():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Secrets에서 개별 값 읽어서 인증 정보 조합
    gcp_info = st.secrets["gcp_service_account"]
    creds_dict = {
        "type": "service_account",
        "project_id": gcp_info["project_id"],
        "private_key": gcp_info["private_key"].replace("\\n", "\n"),
        "client_email": gcp_info["client_email"],
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    url = st.secrets["sheets"]["spreadsheet_url"]
    doc = client.open_by_url(url)
    return doc

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pandas as pd

# Page Configuration
st.set_page_config(page_title="농산물 수불 관리 시스템", layout="centered")

# ---------------------------------------------------------
# 1. 구글 시트 연동 함수
# ---------------------------------------------------------
@st.cache_resource
def init_gspread():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    gcp_secrets = st.secrets["gcp_service_account"]
    
    private_key = gcp_secrets.get("private_key", "")
    if "\\n" in private_key:
        private_key = private_key.replace("\\n", "\n")
    
    creds_dict = {
        "type": "service_account",
        "project_id": gcp_secrets.get("project_id", ""),
        "private_key_id": gcp_secrets.get("private_key_id", ""),
        "private_key": private_key,
        "client_email": gcp_secrets.get("client_email", ""),
        "client_id": gcp_secrets.get("client_id", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": gcp_secrets.get("client_x509_cert_url", "")
    }

    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    url = st.secrets["sheets"]["spreadsheet_url"]
    doc = client.open_by_url(url)
    return doc

# ---------------------------------------------------------
# 2. 마스터 데이터 정의
# ---------------------------------------------------------
ITEMS = [
    "카이피라", "프릴아이스", "버터헤드", "레드오크", 
    "로메인", "치커리", "적근대", "케일", 
    "양상추", "양배추", "적채", "당근"
]

INBOUND_VENDORS = ["에상스팜", "승승장구", "한스", "기타"]
OUTBOUND_VENDORS = ["스윗밸런스", "나무숲", "쿠팡"]

# ---------------------------------------------------------
# 3. 메인 화면 구성
# ---------------------------------------------------------
st.title("🥬 농산물 입출고 수불 관리")

# 구글 시트 문서 로드
try:
    doc = init_gspread()
    # 첫 번째 워크시트 선택 (필요시 doc.worksheet("시트명") 으로 변경 가능)
    sheet = doc.sheet1
except Exception as e:
    st.error(f"구글 시트 연동 실패: {e}")
    st.stop()

#탭 분리: [내역 입력] / [최근 내역 조회]
tab1, tab2 = st.tabs(["📝 입출고 입력", "📊 내역 조회"])

with tab1:
    st.subheader("신규 입출고 데이터 입력")
    
    with st.form("inventory_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            record_date = st.date_input("날짜", value=datetime.today())
            transaction_type = st.radio("구분", ["입고", "출고"], horizontal=True)
            item = st.selectbox("품목명", ITEMS)

        with col2:
            # 구분(입고/출고)에 따라 거래처 목록을 동적으로 변경
            if transaction_type == "입고":
                vendor = st.selectbox("입고 거래처", INBOUND_VENDORS)
            else:
                vendor = st.selectbox("출고 거래처", OUTBOUND_VENDORS)
                
            quantity = st.number_input("수량 (kg 또는 개)", min_value=1, step=1)
            note = st.text_input("비고", placeholder="필요시 메모 작성")

        submitted = st.form_submit_button("입력 완료", use_container_width=True)

        if submitted:
            # 시트에 추가할 데이터 행 (날짜, 구분, 품목, 거래처, 수량, 비고, 등록일시)
            row_data = [
                str(record_date),
                transaction_type,
                item,
                vendor,
                quantity,
                note,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            
            try:
                sheet.append_row(row_data)
                st.success(f"✅ [{transaction_type}] {item} {quantity}개 ({vendor}) 입력 완료!")
            except Exception as e:
                st.error(f"데이터 저장 실패: {e}")

with tab2:
    st.subheader("최근 등록 내역")
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()

    try:
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("등록된 데이터가 없습니다.")
    except Exception as e:
        st.error(f"데이터 조회 중 오류 발생: {e}")

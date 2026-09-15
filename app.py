import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime

# 페이지 기본 설정
st.set_page_config(page_title="야채 원재료 수불부", layout="wide")

# ---------------------------------------------------------
# 1. 구글 시트 연동 함수 (Secrets 파싱 및 에러 방지 최신화)
# ---------------------------------------------------------
@st.cache_resource
def init_gspread():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Secrets에서 json_cert 읽기
    raw_json = st.secrets["gcp_service_account"]["json_cert"]
    
    # Dict 형태이든 String 형태이든 안전하게 파싱
    if isinstance(raw_json, str):
        creds_dict = json.loads(raw_json, strict=False)
    else:
        creds_dict = dict(raw_json)

    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # 구글 시트 열기
    url = st.secrets["sheets"]["spreadsheet_url"]
    doc = client.open_by_url(url)
    return doc

# ---------------------------------------------------------
# 2. 메인 화면 구성
# ---------------------------------------------------------
st.title("🥬 야채 원재료 수불부 작성 앱")

try:
    doc = init_gspread()
    # 첫 번째 워크시트(탭) 가져오기
    sheet = doc.get_worksheet(0)
    st.success("✅ 구글 시트 연동 성공!")
except Exception as e:
    st.error(f"❌ 구글 시트 연동에 실패했습니다: {e}")
    st.stop()

st.divider()

# --- [입력 폼 영역] ---
st.subheader("📝 수불 내역 등록")

with st.form("subul_form", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    
    with col1:
        date_input = st.date_input("일자", datetime.now())
        item_name = st.text_input("품목명 (예: 양파, 당근)")
        
    with col2:
        in_qty = st.number_input("입고량 (kg/개)", min_value=0.0, step=0.1)
        out_qty = st.number_input("출고량 (kg/개)", min_value=0.0, step=0.1)
        
    with col3:
        unit_price = st.number_input("단가 (원)", min_value=0, step=100)
        remark = st.text_input("비고 (비고/거래처 등)")

    submitted = st.form_submit_button("수불 내역 저장하기", use_container_width=True)

    if submitted:
        if not item_name.strip():
            st.warning("품목명을 입력해 주세요.")
        else:
            # 시트에 추가할 행 데이터 (일자, 품목명, 입고량, 출고량, 단가, 비고, 등록시간)
            new_row = [
                str(date_input),
                item_name,
                in_qty,
                out_qty,
                unit_price,
                remark,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            
            try:
                sheet.append_row(new_row)
                st.success(f"'{item_name}' 수불 내역이 구글 시트에 성공적으로 저장되었습니다!")
            except Exception as e:
                st.error(f"데이터 저장 실패: {e}")

st.divider()

# --- [시트 데이터 조회 영역] ---
st.subheader("📊 현재 수불 기록 조회")

try:
    data = sheet.get_all_records()
    if data:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
    else:
        # 데이터가 없을 경우 가이드 표시
        st.info("구글 시트에 아직 데이터가 없습니다. 위 입력 폼을 통해 내역을 작성해 보세요.")
except Exception as e:
    # 시트 헤더가 없거나 열 형식이 작성되지 않았을 때 표 그대로 받아오기
    try:
        raw_rows = sheet.get_all_values()
        if raw_rows:
            df = pd.DataFrame(raw_rows[1:], columns=raw_rows[0])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("시트가 비어 있습니다. 내역을 등록하면 자동으로 기록됩니다.")
    except Exception as read_err:
        st.warning("데이터를 불러오는 중입니다. 첫 입력을 등록해 보세요.")

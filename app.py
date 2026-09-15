import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import pandas as pd
import io

st.set_page_config(page_title="농산물 수불 관리 시스템", layout="wide")

# ---------------------------------------------------------
# 1. 구글 시트 연동
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
    return client.open_by_url(url)

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
st.title("🥬 농산물 입출고 & 입고 리스트 관리")

try:
    doc = init_gspread()
    sheet = doc.sheet1
except Exception as e:
    st.error(f"구글 시트 연동 실패: {e}")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📝 입출고 입력", "📅 기간별 입고 리스트", "📊 전체 내역 조회"])

# ---------------------------------------------------------
# TAB 1: 데이터 입력 (출고 시 단가 제거)
# ---------------------------------------------------------
with tab1:
    st.subheader("신규 입출고 등록")
    
    with st.form("inventory_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            record_date = st.date_input("날짜", value=datetime.today())
            transaction_type = st.radio("구분", ["입고", "출고"], horizontal=True)
            item = st.selectbox("품목명", ITEMS)

        with col2:
            if transaction_type == "입고":
                vendor = st.selectbox("입고 거래처", INBOUND_VENDORS)
                weight = st.number_input("입고 중량 (kg)", min_value=0.0, step=0.5, format="%.1f")
                unit_price = st.number_input("입고 단가 (원/kg)", min_value=0, step=100)
                total_price = int(weight * unit_price)
                st.info(f"💡 **입고 총 금액:** `{total_price:,} 원`")
            else:
                vendor = st.selectbox("출고 거래처", OUTBOUND_VENDORS)
                weight = st.number_input("출고 중량 (kg)", min_value=0.0, step=0.5, format="%.1f")
                unit_price = 0
                total_price = 0
                
            note = st.text_input("비고", placeholder="특이사항 메모")

        submitted = st.form_submit_button("저장하기", use_container_width=True)

        if submitted:
            row_data = [
                str(record_date),
                transaction_type,
                item,
                vendor,
                weight,
                unit_price if transaction_type == "입고" else "-",
                total_price if transaction_type == "입고" else "-",
                note,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            
            try:
                sheet.append_row(row_data)
                st.success(f"✅ [{transaction_type}] {item} {weight}kg ({vendor}) 저장 완료!")
            except Exception as e:
                st.error(f"저장 실패: {e}")

# ---------------------------------------------------------
# TAB 2: 기간별 입고 리스트
# ---------------------------------------------------------
with tab2:
    st.subheader("📅 기간별 입고 리스트 & 정산")
    
    col_date1, col_date2, col_vendor = st.columns(3)
    with col_date1:
        start_date = st.date_input("시작일", value=date(datetime.now().year, datetime.now().month, 1))
    with col_date2:
        end_date = st.date_input("종료일", value=datetime.today())
    with col_vendor:
        selected_vendor = st.selectbox("입고 거래처 필터", ["전체"] + INBOUND_VENDORS)

    try:
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            
            # 입고 데이터만 필터링
            inbound_df = df[df["구분"] == "입고"].copy()
            
            if not inbound_df.empty:
                # 숫자형 타입 변환
                inbound_df["날짜"] = pd.to_datetime(inbound_df["날짜"]).dt.date
                inbound_df["중량(kg)"] = pd.to_numeric(inbound_df["중량(kg)"], errors='coerce').fillna(0)
                inbound_df["단가(원)"] = pd.to_numeric(inbound_df["단가(원)"], errors='coerce').fillna(0)
                inbound_df["총금액(원)"] = pd.to_numeric(inbound_df["총금액(원)"], errors='coerce').fillna(0)
                
                # 날짜 및 거래처 필터 적용
                filtered_df = inbound_df[(inbound_df["날짜"] >= start_date) & (inbound_df["날짜"] <= end_date)]
                
                if selected_vendor != "전체":
                    filtered_df = filtered_df[filtered_df["거래처"] == selected_vendor]
                    
                if not filtered_df.empty:
                    # Metrics 요약
                    st.markdown("---")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("총 입고 건수", f"{len(filtered_df):,} 건")
                    m2.metric("총 입고 중량", f"{filtered_df['중량(kg)'].sum():,.1f} kg")
                    m3.metric("총 입고 금액", f"{filtered_df['총금액(원)'].sum():,} 원")
                    st.markdown("---")

                    # 테이블 출력
                    display_cols = ["날짜", "거래처", "품목", "중량(kg)", "단가(원)", "총금액(원)", "비고"]
                    out_df = filtered_df[display_cols].sort_values(by="날짜", ascending=False)
                    st.dataframe(out_df, use_container_width=True)

                    # 엑셀 다운로드 버튼
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        out_df.to_excel(writer, index=False, sheet_name='입고리스트')
                    
                    st.download_button(
                        label="📥 선택한 입고 리스트 엑셀 다운로드",
                        data=excel_buffer.getvalue(),
                        file_name=f"입고리스트_{start_date}_{end_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.info("선택한 조건에 해당하는 입고 데이터가 없습니다.")
            else:
                st.info("입고 내역이 존재하지 않습니다.")
        else:
            st.info("등록된 데이터가 없습니다.")
            
    except Exception as e:
        st.error(f"데이터 조회 중 오류 발생: {e}")

# ---------------------------------------------------------
# TAB 3: 전체 내역 조회
# ---------------------------------------------------------
with tab3:
    st.subheader("전체 입출고 데이터")
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        
    try:
        data = sheet.get_all_records()
        if data:
            st.dataframe(pd.DataFrame(data), use_container_width=True)
    except Exception as e:
        st.error(f"조회 실패: {e}")

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

INBOUND_VENDORS = ["에상스팜", "승승장구", "한스", "넥스토팜", "기타"]
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

tab1, tab2, tab3, tab4 = st.tabs([
    "📥 입고 등록", 
    "📤 출고 등록", 
    "📅 기간별 입고 리스트", 
    "📊 전체 내역 조회 & 출력"
])

# ---------------------------------------------------------
# TAB 1: 입고 전용 입력 폼
# ---------------------------------------------------------
with tab1:
    st.subheader("📥 입고 데이터 등록")
    
    with st.form("inbound_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            record_date = st.date_input("입고 날짜", value=datetime.today())
            item = st.selectbox("품목명", ITEMS)
            vendor = st.selectbox("입고 거래처", INBOUND_VENDORS)

        with col2:
            weight = st.number_input("입고 중량 (kg)", min_value=0.0, step=0.5, format="%.1f")
            unit_price = st.number_input("입고 단가 (원/kg)", min_value=0, step=100)
            total_price = int(weight * unit_price)
            st.info(f"💡 **입고 총 금액:** `{total_price:,} 원`")
            note = st.text_input("비고", placeholder="특이사항 메모")

        submitted = st.form_submit_button("입고 저장하기", use_container_width=True)

        if submitted:
            row_data = [
                str(record_date),
                "입고",
                item,
                vendor,
                weight,
                unit_price,
                total_price,
                note,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            
            try:
                sheet.append_row(row_data)
                st.success(f"✅ [입고] {item} {weight}kg ({vendor}) / {total_price:,}원 저장 완료!")
            except Exception as e:
                st.error(f"저장 실패: {e}")

# ---------------------------------------------------------
# TAB 2: 출고 전용 입력 폼
# ---------------------------------------------------------
with tab2:
    st.subheader("📤 출고 데이터 등록")
    
    with st.form("outbound_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            record_date = st.date_input("출고 날짜", value=datetime.today())
            item = st.selectbox("품목명", ITEMS)

        with col2:
            vendor = st.selectbox("출고 거래처", OUTBOUND_VENDORS)
            weight = st.number_input("출고 중량 (kg)", min_value=0.0, step=0.5, format="%.1f")
            note = st.text_input("비고", placeholder="특이사항 메모")

        submitted = st.form_submit_button("출고 저장하기", use_container_width=True)

        if submitted:
            row_data = [
                str(record_date),
                "출고",
                item,
                vendor,
                weight,
                "-",
                "-",
                note,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            
            try:
                sheet.append_row(row_data)
                st.success(f"✅ [출고] {item} {weight}kg ({vendor}) 저장 완료!")
            except Exception as e:
                st.error(f"저장 실패: {e}")

# ---------------------------------------------------------
# TAB 3: 기간별 입고 리스트 (작동이 확인된 기존 코드 기반)
# ---------------------------------------------------------
with tab3:
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
            
            inbound_df = df[df["구분"] == "입고"].copy()
            
            if not inbound_df.empty:
                inbound_df["날짜"] = pd.to_datetime(inbound_df["날짜"]).dt.date
                inbound_df["중량(kg)"] = pd.to_numeric(inbound_df["중량(kg)"], errors='coerce').fillna(0)
                inbound_df["단가(원)"] = pd.to_numeric(inbound_df["단가(원)"], errors='coerce').fillna(0)
                inbound_df["총금액(원)"] = pd.to_numeric(inbound_df["총금액(원)"], errors='coerce').fillna(0)
                
                filtered_df = inbound_df[(inbound_df["날짜"] >= start_date) & (inbound_df["날짜"] <= end_date)]
                
                if selected_vendor != "전체":
                    filtered_df = filtered_df[filtered_df["거래처"] == selected_vendor]
                    
                if not filtered_df.empty:
                    st.markdown("---")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("총 입고 건수", f"{len(filtered_df):,} 건")
                    m2.metric("총 입고 중량", f"{filtered_df['중량(kg)'].sum():,.1f} kg")
                    m3.metric("총 입고 금액", f"{filtered_df['총금액(원)'].sum():,} 원")
                    st.markdown("---")

                    display_cols = ["날짜", "거래처", "품목", "중량(kg)", "단가(원)", "총금액(원)", "비고"]
                    out_df = filtered_df[display_cols].sort_values(by="날짜", ascending=False)
                    st.dataframe(out_df, use_container_width=True)

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
# TAB 4: 전체 내역 조회 & 기간 검색 및 다운로드
# ---------------------------------------------------------
with tab4:
    st.subheader("📊 전체 입출고 내역 검색 및 출력")
    
    # 상단 컨트롤바
    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([1, 1, 1, 0.8])
    with ctrl1:
        s_date = st.date_input("조회 시작일", value=date(datetime.now().year, datetime.now().month, 1), key="tab4_sdate")
    with ctrl2:
        e_date = st.date_input("조회 종료일", value=datetime.today(), key="tab4_edate")
    with ctrl3:
        g_filter = st.selectbox("구분", ["전체", "입고", "출고"], key="tab4_gfilter")
    with ctrl4:
        st.write(" ")
        if st.button("🔄 새로고침", use_container_width=True):
            st.cache_data.clear()

    try:
        data = sheet.get_all_records()
        if data:
            df_all = pd.DataFrame(data)
            
            # 날짜 변환
            df_all["날짜_검색용"] = pd.to_datetime(df_all["날짜"]).dt.date
            
            # 기간 필터링
            df_filtered = df_all[(df_all["날짜_검색용"] >= s_date) & (df_all["날짜_검색용"] <= e_date)].copy()
            
            # 입/출고 구분 필터링
            if g_filter != "전체":
                df_filtered = df_filtered[df_filtered["구분"] == g_filter]
                
            df_filtered = df_filtered.sort_values(by="날짜_검색용", ascending=False)
            df_filtered = df_filtered.drop(columns=["날짜_검색용"]) # 임시 컬럼 삭제

            if not df_filtered.empty:
                # 요약 지표
                st.markdown("---")
                m1, m2 = st.columns(2)
                m1.metric("조회 건수", f"{len(df_filtered):,} 건")
                
                # 중량 컬럼 숫자로 안전 변환 후 합계 계산
                weight_numeric = pd.to_numeric(df_filtered["중량(kg)"], errors='coerce').fillna(0)
                m2.metric("총 중량 합계", f"{weight_numeric.sum():,.1f} kg")
                st.markdown("---")

                # 테이블 출력
                st.dataframe(df_filtered, use_container_width=True)

                # 하단 버튼
                btn1, btn2 = st.columns(2)
                with btn1:
                    excel_all = io.BytesIO()
                    with pd.ExcelWriter(excel_all, engine='openpyxl') as writer:
                        df_filtered.to_excel(writer, index=False, sheet_name='전체입출고내역')
                    
                    st.download_button(
                        label="📥 검색 결과 엑셀 다운로드",
                        data=excel_all.getvalue(),
                        file_name=f"전체입출고내역_{s_date}_{e_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                with btn2:
                    st.components.v1.html("""
                        <button onclick="window.print()" style="
                            width: 100%;
                            height: 38px;
                            background-color: #FF4B4B;
                            color: white;
                            border: none;
                            border-radius: 8px;
                            font-size: 14px;
                            font-weight: bold;
                            cursor: pointer;
                        ">🖨️ 인쇄 / PDF 저장</button>
                    """, height=45)
            else:
                st.info("선택한 기간 및 조건에 해당하는 내역이 없습니다.")
        else:
            st.info("등록된 데이터가 없습니다.")

    except Exception as e:
        st.error(f"데이터 조회 오류: {e}")

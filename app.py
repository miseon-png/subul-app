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
# 2. 날짜 안전 변환 함수
# ---------------------------------------------------------
def safe_parse_date(series):
    parsed = pd.to_datetime(series, errors='coerce', format='mixed')
    return parsed.dt.date

# ---------------------------------------------------------
# 3. 마스터 데이터 정의
# ---------------------------------------------------------
ITEMS = [
    "카이피라", "프릴아이스", "버터헤드", "레드오크", 
    "로메인", "치커리", "적근대", "케일", 
    "양상추", "양배추", "적채", "당근"
]

INBOUND_VENDORS = ["에상스팜", "승승장구", "한스", "넥스토팜", "기타"]
OUTBOUND_VENDORS = ["스윗밸런스", "나무숲", "쿠팡"]

# ---------------------------------------------------------
# 4. 메인 화면 구성
# ---------------------------------------------------------
st.title("🥬 농산물 입출고 & 수불부 관리 시스템")

try:
    doc = init_gspread()
    sheet = doc.sheet1
except Exception as e:
    st.error(f"구글 시트 연동 실패: {e}")
    st.stop()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📥 입고 등록", 
    "📤 출고 등록", 
    "🚮 로스 등록",
    "📅 기간별 입고 리스트", 
    "📊 수불부 (기간 정산)"
])

# ---------------------------------------------------------
# TAB 1: 입고 등록
# ---------------------------------------------------------
with tab1:
    st.subheader("📥 입고 데이터 등록")
    
    with st.form("inbound_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            record_date = st.date_input("입고 날짜", value=datetime.today(), key="in_date")
            item = st.selectbox("품목명", ITEMS, key="in_item")
            vendor = st.selectbox("입고 거래처", INBOUND_VENDORS, key="in_vendor")

        with col2:
            weight = st.number_input("입고 중량 (kg)", min_value=0.0, step=0.5, format="%.1f", key="in_weight")
            unit_price = st.number_input("입고 단가 (원/kg)", min_value=0, step=100, key="in_price")
            total_price = int(weight * unit_price)
            st.info(f"💡 **입고 총 금액:** `{total_price:,} 원`")
            note = st.text_input("비고", placeholder="특이사항 메모", key="in_note")

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
# TAB 2: 출고 등록
# ---------------------------------------------------------
with tab2:
    st.subheader("📤 출고 데이터 등록")
    
    with st.form("outbound_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            record_date = st.date_input("출고 날짜", value=datetime.today(), key="out_date")
            item = st.selectbox("품목명", ITEMS, key="out_item")

        with col2:
            vendor = st.selectbox("출고 거래처", OUTBOUND_VENDORS, key="out_vendor")
            weight = st.number_input("출고 중량 (kg)", min_value=0.0, step=0.5, format="%.1f", key="out_weight")
            note = st.text_input("비고", placeholder="특이사항 메모", key="out_note")

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
# TAB 3: 로스(손실) 등록
# ---------------------------------------------------------
with tab3:
    st.subheader("🚮 로스(손실) 데이터 등록")
    
    with st.form("loss_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            record_date = st.date_input("로스 발생 날짜", value=datetime.today(), key="loss_date")
            item = st.selectbox("품목명", ITEMS, key="loss_item")

        with col2:
            weight = st.number_input("로스 중량 (kg)", min_value=0.0, step=0.5, format="%.1f", key="loss_weight")
            note = st.text_input("사유 및 메모", placeholder="예: 폐기, 부패 등", key="loss_note")

        submitted = st.form_submit_button("로스 저장하기", use_container_width=True)

        if submitted:
            row_data = [
                str(record_date),
                "로스",
                item,
                "자체폐기",
                weight,
                "-",
                "-",
                note,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            
            try:
                sheet.append_row(row_data)
                st.success(f"✅ [로스] {item} {weight}kg 저장 완료!")
            except Exception as e:
                st.error(f"저장 실패: {e}")

# ---------------------------------------------------------
# TAB 4: 기간별 입고 리스트 (정산용)
# ---------------------------------------------------------
with tab4:
    st.subheader("📅 기간별 입고 리스트 & 정산")
    
    col_date1, col_date2, col_vendor = st.columns(3)
    with col_date1:
        start_date = st.date_input("시작일", value=date(2024, 1, 1), key="tab4_start")
    with col_date2:
        end_date = st.date_input("종료일", value=datetime.today(), key="tab4_end")
    with col_vendor:
        selected_vendor = st.selectbox("입고 거래처 필터", ["전체"] + INBOUND_VENDORS, key="tab4_vendor")

    try:
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            inbound_df = df[df["구분"] == "입고"].copy()
            
            if not inbound_df.empty:
                inbound_df["날짜_parsed"] = safe_parse_date(inbound_df["날짜"])
                inbound_df["중량(kg)"] = pd.to_numeric(inbound_df["중량(kg)"], errors='coerce').fillna(0)
                inbound_df["단가(원)"] = pd.to_numeric(inbound_df["단가(원)"], errors='coerce').fillna(0)
                inbound_df["총금액(원)"] = pd.to_numeric(inbound_df["총금액(원)"], errors='coerce').fillna(0)
                
                filtered_df = inbound_df[
                    (inbound_df["날짜_parsed"].notnull()) & 
                    (inbound_df["날짜_parsed"] >= start_date) & 
                    (inbound_df["날짜_parsed"] <= end_date)
                ]
                
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
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_tab4"
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
# TAB 5: 수불부 (전일재고 + 입고 - 출고 - 로스 = 당일재고)
# ---------------------------------------------------------
with tab5:
    st.subheader("📊 농산물 수불부 (재고 정산)")
    
    ctrl1, ctrl2, ctrl3 = st.columns([1, 1, 0.8])
    with ctrl1:
        s_date = st.date_input("정산 시작일", value=date(2024, 1, 1), key="subul_sdate")
    with ctrl2:
        e_date = st.date_input("정산 종료일", value=datetime.today(), key="subul_edate")
    with ctrl3:
        st.write(" ")
        if st.button("🔄 수불부 새로고침", use_container_width=True):
            st.cache_data.clear()

    try:
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            df["날짜_dt"] = safe_parse_date(df["날짜"])
            df["중량(kg)"] = pd.to_numeric(df["중량(kg)"], errors='coerce').fillna(0)
            
            # 1. 시작일 이전 데이터 (전일 재고 산출용)
            prior_df = df[(df["날짜_dt"].notnull()) & (df["날짜_dt"] < s_date)]
            
            # 2. 지정 기간 내 데이터 (기간 입고/출고/로스 산출용)
            period_df = df[
                (df["날짜_dt"].notnull()) & 
                (df["날짜_dt"] >= s_date) & 
                (df["날짜_dt"] <= e_date)
            ]

            # 품목별 수불 집계 테이블 생성
            subul_list = []
            
            for item in ITEMS:
                # --- 전일 재고 계산 ---
                prior_item = prior_df[prior_df["품목"] == item]
                p_in = prior_item[prior_item["구분"] == "입고"]["중량(kg)"].sum()
                p_out = prior_item[prior_item["구분"] == "출고"]["중량(kg)"].sum()
                p_loss = prior_item[prior_item["구분"] == "로스"]["중량(kg)"].sum()
                prev_stock = p_in - p_out - p_loss # 전일재고 수식

                # --- 기간 내 수량 계산 ---
                period_item = period_df[period_df["품목"] == item]
                curr_in = period_item[period_item["구분"] == "입고"]["중량(kg)"].sum()
                curr_out = period_item[period_item["구분"] == "출고"]["중량(kg)"].sum()
                curr_loss = period_item[period_item["구분"] == "로스"]["중량(kg)"].sum()

                # --- 당일 재고 (전일재고 + 입고 - 출고 - 로스) ---
                curr_stock = prev_stock + curr_in - curr_out - curr_loss

                # 한 번이라도 거래가 있었거나 재고가 있는 항목만 추가
                if prev_stock != 0 or curr_in != 0 or curr_out != 0 or curr_loss != 0 or curr_stock != 0:
                    subul_list.append({
                        "품목명": item,
                        "전일재고 (kg)": round(prev_stock, 1),
                        "입고량 (kg)": round(curr_in, 1),
                        "출고량 (kg)": round(curr_out, 1),
                        "로스량 (kg)": round(curr_loss, 1),
                        "당일재고 (kg)": round(curr_stock, 1)
                    })

            if subul_list:
                subul_df = pd.DataFrame(subul_list)
                
                # 수불 요약 지표 표시
                st.markdown("---")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("총 전일재고", f"{subul_df['전일재고 (kg)'].sum():,.1f} kg")
                m2.metric("총 입고량", f"{subul_df['입고량 (kg)'].sum():,.1f} kg")
                m3.metric("총 출고량", f"{subul_df['출고량 (kg)'].sum():,.1f} kg")
                m4.metric("현재 당일재고", f"{subul_df['당일재고 (kg)'].sum():,.1f} kg")
                st.markdown("---")

                st.write("##### 📋 품목별 수불 요약표")
                st.dataframe(subul_df, use_container_width=True)

                # 하단 다운로드 및 인쇄 버튼
                b1, b2 = st.columns(2)
                with b1:
                    excel_subul = io.BytesIO()
                    with pd.ExcelWriter(excel_subul, engine='openpyxl') as writer:
                        subul_df.to_excel(writer, index=False, sheet_name='수불부')
                    
                    st.download_button(
                        label="📥 수불부 엑셀 다운로드",
                        data=excel_subul.getvalue(),
                        file_name=f"수불부_{s_date}_{e_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="dl_subul"
                    )
                with b2:
                    st.components.v1.html("""
                        <button onclick="window.print()" style="
                            width: 100%;
                            height: 38px;
                            background-color: #4CAF50;
                            color: white;
                            border: none;
                            border-radius: 8px;
                            font-size: 14px;
                            font-weight: bold;
                            cursor: pointer;
                        ">🖨️ 수불부 인쇄 / PDF 저장</button>
                    """, height=45)
            else:
                st.info("해당 기간 동안 수불 내역이 없습니다.")
        else:
            st.info("등록된 데이터가 없습니다.")

    except Exception as e:
        st.error(f"수불부 계산 오류: {e}")

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import pandas as pd
import io

st.set_page_config(page_title="야채 원재료 수불 관리 시스템", layout="wide")

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

# 안전한 날짜 변환 보조 함수
def safe_parse_date(series):
    parsed = pd.to_datetime(series, errors='coerce', format='mixed')
    return parsed.dt.date

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
# 3. 메인 화면 구성 및 시트 로드
# ---------------------------------------------------------
st.title("🥬 야채 원재료 수불 관리 시스템")

try:
    doc = init_gspread()
    sheet = doc.worksheet("시트1")
except Exception as e:
    st.error(f"구글 시트 로드 실패: {e}")
    st.stop()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📥 입고 등록", 
    "📤 출고(사용) 등록", 
    "🚮 로스 등록", 
    "📅 기간별 입고 정산",
    "📊 수불부 (재고 정산)"
])

# 해당 품목의 최신 당일재고(전일재고용) 가져오기 보조 함수
def get_latest_stock(sheet_obj, item_name):
    all_data = sheet_obj.get_all_records()
    if not all_data:
        return 0
    df_all = pd.DataFrame(all_data)
    item_df = df_all[df_all["원료명"] == item_name]
    if item_df.empty:
        return 0
    last_stock = item_df.iloc[-1].get("당일재고", 0)
    return pd.to_numeric(last_stock, errors='coerce') or 0

# ---------------------------------------------------------
# TAB 1: 입고 등록 (단가 & 면세 금액 계산 추가)
# ---------------------------------------------------------
with tab1:
    st.subheader("📥 원재료 입고 등록")
    
    with st.form("inbound_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            record_date = st.date_input("입고일자", value=datetime.today())
            vendor = st.selectbox("입고 거래처", INBOUND_VENDORS)
            item = st.selectbox("원료명", ITEMS)

        with col2:
            weight = st.number_input("입고 중량 (kg)", min_value=0.0, step=0.5, format="%.1f")
            unit_price = st.number_input("단가 (원/kg)", min_value=0, step=100)
            
            # 면세 농산물이므로 부가세 제외, 공급가액 = 총 금액
            total_price = int(weight * unit_price)
            st.info(f"💡 **입고 총 금액 (면세):** `{total_price:,} 원`")
            note = st.text_input("비고", placeholder="특이사항 메모")

        submitted = st.form_submit_button("입고 저장하기", use_container_width=True)

        if submitted:
            try:
                prev_stock = get_latest_stock(sheet, item)
                day_stock = prev_stock + weight # 당일재고 = 전일재고 + 당일입고
                
                # 시트1 확장 구조: 일자, 구분, 원료명, 전일재고, 당일입고, 당일사용, 로스, 당일재고, 거래처, 단가, 총금액, 비고
                row_data = [
                    str(record_date),
                    "야채 원재료",
                    item,
                    prev_stock,
                    weight,
                    0,
                    0,
                    day_stock,
                    vendor,
                    unit_price,
                    total_price,
                    note
                ]
                
                sheet.append_row(row_data)
                st.success(f"✅ [입고 완료] {item} {weight}kg ({vendor}) / 단가: {unit_price:,}원 ➡️ 총 {total_price:,}원")
            except Exception as e:
                st.error(f"저장 실패: {e}")

# ---------------------------------------------------------
# TAB 2: 출고(사용) 등록
# ---------------------------------------------------------
with tab2:
    st.subheader("📤 원재료 출고(사용) 등록")
    
    with st.form("outbound_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            record_date = st.date_input("출고일자", value=datetime.today(), key="out_date")
            vendor = st.selectbox("출고 거래처", OUTBOUND_VENDORS, key="out_vendor")
            item = st.selectbox("원료명", ITEMS, key="out_item")

        with col2:
            usage_weight = st.number_input("출고(사용) 중량 (kg)", min_value=0.0, step=0.5, format="%.1f", key="out_weight")
            note = st.text_input("비고", placeholder="특이사항 메모", key="out_note")

        submitted = st.form_submit_button("출고 저장하기", use_container_width=True)

        if submitted:
            try:
                prev_stock = get_latest_stock(sheet, item)
                day_stock = prev_stock - usage_weight
                
                row_data = [
                    str(record_date),
                    "야채 원재료",
                    item,
                    prev_stock,
                    0,
                    usage_weight,
                    0,
                    day_stock,
                    vendor,
                    "-",
                    "-",
                    note
                ]
                
                sheet.append_row(row_data)
                st.success(f"✅ [출고 완료] {item} {usage_weight}kg ({vendor}) / 전일재고: {prev_stock}kg ➡️ 당일재고: {day_stock}kg")
            except Exception as e:
                st.error(f"저장 실패: {e}")

# ---------------------------------------------------------
# TAB 3: 로스 등록
# ---------------------------------------------------------
with tab3:
    st.subheader("🚮 로스(폐기/손실) 등록")
    
    with st.form("loss_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            record_date = st.date_input("발생일자", value=datetime.today(), key="loss_date")
            item = st.selectbox("원료명", ITEMS, key="loss_item")

        with col2:
            loss_weight = st.number_input("로스 중량 (kg)", min_value=0.0, step=0.5, format="%.1f", key="loss_weight")
            note = st.text_input("사유", placeholder="예: 부패, 훼손 등", key="loss_note")

        submitted = st.form_submit_button("로스 저장하기", use_container_width=True)

        if submitted:
            try:
                prev_stock = get_latest_stock(sheet, item)
                day_stock = prev_stock - loss_weight
                
                row_data = [
                    str(record_date),
                    "야채 원재료",
                    item,
                    prev_stock,
                    0,
                    0,
                    loss_weight,
                    day_stock,
                    "자체폐기",
                    "-",
                    "-",
                    note
                ]
                
                sheet.append_row(row_data)
                st.success(f"✅ [로스 완료] {item} {loss_weight}kg / 전일재고: {prev_stock}kg ➡️ 당일재고: {day_stock}kg")
            except Exception as e:
                st.error(f"저장 실패: {e}")

# ---------------------------------------------------------
# TAB 4: 기간별 입고 정산 (거래처/단가/총금액 조회)
# ---------------------------------------------------------
with tab4:
    st.subheader("📅 기간별 야채 입고 정산 내역")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        s_date_in = st.date_input("시작일", value=date(2024, 7, 1), key="in_sdate")
    with c2:
        e_date_in = st.date_input("종료일", value=datetime.today(), key="in_edate")
    with c3:
        v_filter = st.selectbox("거래처 필터", ["전체"] + INBOUND_VENDORS)

    try:
        all_records = sheet.get_all_records()
        if all_records:
            df = pd.DataFrame(all_records)
            df["일자_parsed"] = safe_parse_date(df["일자"])
            
            # 입고 수량이 있는 행만 추출
            df["당일입고"] = pd.to_numeric(df["당일입고"], errors='coerce').fillna(0)
            in_df = df[df["당일입고"] > 0].copy()
            
            if not in_df.empty:
                filtered_in = in_df[
                    (in_df["일자_parsed"].notnull()) & 
                    (in_df["일자_parsed"] >= s_date_in) & 
                    (in_df["일자_parsed"] <= e_date_in)
                ]
                
                if "거래처" in filtered_in.columns and v_filter != "전체":
                    filtered_in = filtered_in[filtered_in["거래처"] == v_filter]
                    
                if not filtered_in.empty:
                    # 금액 숫자형 자동 변환
                    if "총금액" in filtered_in.columns:
                        filtered_in["총금액_num"] = pd.to_numeric(filtered_in["총금액"], errors='coerce').fillna(0)
                    else:
                        filtered_in["총금액_num"] = 0

                    st.markdown("---")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("총 입고 건수", f"{len(filtered_in):,} 건")
                    m2.metric("총 입고 중량", f"{filtered_in['당일입고'].sum():,.1f} kg")
                    m3.metric("총 입고 금액", f"{filtered_in['총금액_num'].sum():,} 원")
                    st.markdown("---")

                    show_cols = [c for c in filtered_in.columns if c not in ["일자_parsed", "총금액_num"]]
                    st.dataframe(filtered_in[show_cols].sort_values(by="일자", ascending=False), use_container_width=True)

                    excel_in = io.BytesIO()
                    with pd.ExcelWriter(excel_in, engine='openpyxl') as writer:
                        filtered_in[show_cols].to_excel(writer, index=False, sheet_name='입고정산')
                    
                    st.download_button(
                        label="📥 선택 기간 입고정산 엑셀 다운로드",
                        data=excel_in.getvalue(),
                        file_name=f"야채입고정산_{s_date_in}_{e_date_in}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.info("선택 조건에 해당하는 입고 내역이 없습니다.")
            else:
                st.info("입고된 데이터가 없습니다.")
        else:
            st.info("등록된 데이터가 없습니다.")
    except Exception as e:
        st.error(f"입고 정산 조회 오류: {e}")

# ---------------------------------------------------------
# TAB 5: 수불부 (기간별 재고 정산)
# ---------------------------------------------------------
with tab5:
    st.subheader("📊 야채 원재료 수불부 (기간 정산)")
    
    ctrl1, ctrl2, ctrl3 = st.columns([1, 1, 0.8])
    with ctrl1:
        s_date = st.date_input("정산 시작일", value=date(2024, 7, 1), key="subul_sdate")
    with ctrl2:
        e_date = st.date_input("정산 종료일", value=datetime.today(), key="subul_edate")
    with ctrl3:
        st.write(" ")
        if st.button("🔄 수불부 새로고침", use_container_width=True):
            st.cache_data.clear()

    try:
        all_records = sheet.get_all_records()
        if all_records:
            df = pd.DataFrame(all_records)
            df["일자_parsed"] = safe_parse_date(df["일자"])
            
            for col in ["전일재고", "당일입고", "당일사용", "로스", "당일재고"]:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            # 1. 시작일 이전 데이터
            prior_df = df[(df["일자_parsed"].notnull()) & (df["일자_parsed"] < s_date)]
            
            # 2. 지정 기간 내 데이터
            period_df = df[
                (df["일자_parsed"].notnull()) & 
                (df["일자_parsed"] >= s_date) & 
                (df["일자_parsed"] <= e_date)
            ]

            summary_rows = []
            
            for item in ITEMS:
                prior_item = prior_df[prior_df["원료명"] == item]
                prev_stock = prior_item.iloc[-1]["당일재고"] if not prior_item.empty else 0
                
                period_item = period_df[period_df["원료명"] == item]
                curr_in = period_item["당일입고"].sum()
                curr_use = period_item["당일사용"].sum()
                curr_loss = period_item["로스"].sum()
                
                curr_stock = prev_stock + curr_in - curr_use - curr_loss
                
                if prev_stock != 0 or curr_in != 0 or curr_use != 0 or curr_loss != 0 or curr_stock != 0:
                    summary_rows.append({
                        "원료명": item,
                        "전일재고 (kg)": round(prev_stock, 1),
                        "당일입고 (kg)": round(curr_in, 1),
                        "당일사용 (kg)": round(curr_use, 1),
                        "로스 (kg)": round(curr_loss, 1),
                        "당일재고 (kg)": round(curr_stock, 1)
                    })

            if summary_rows:
                subul_df = pd.DataFrame(summary_rows)
                
                st.markdown("---")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("총 전일재고", f"{subul_df['전일재고 (kg)'].sum():,.1f} kg")
                m2.metric("총 입고량", f"{subul_df['당일입고 (kg)'].sum():,.1f} kg")
                m3.metric("총 사용량", f"{subul_df['당일사용 (kg)'].sum():,.1f} kg")
                m4.metric("현재 당일재고", f"{subul_df['당일재고 (kg)'].sum():,.1f} kg")
                st.markdown("---")

                st.write("##### 📋 품목별 수불 집계 요약표")
                st.dataframe(subul_df, use_container_width=True)

                b1, b2 = st.columns(2)
                with b1:
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        subul_df.to_excel(writer, index=False, sheet_name='수불부')
                    
                    st.download_button(
                        label="📥 수불부 정산표 엑셀 다운로드",
                        data=excel_buffer.getvalue(),
                        file_name=f"야채원재료_수불부_{s_date}_{e_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
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
                st.info("지정한 기간 동안 입력된 수불 내역이 없습니다.")
        else:
            st.info("시트에 입력된 데이터가 없습니다.")
            
    except Exception as e:
        st.error(f"수불부 계산 오류: {e}")

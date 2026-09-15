import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import pandas as pd
import io

st.set_page_config(page_title="야채 원재료 수불 관리 시스템", layout="wide")

# ---------------------------------------------------------
# 1. 구글 시트 연동 및 보조 함수
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

# 해당 월의 1일 날짜를 자동으로 가져오는 보조 함수
def get_first_day_of_month():
    today = date.today()
    return date(today.year, today.month, 1)

# 빈 헤더/중복 헤더 에러를 방지하는 안전한 시트 로더 함수
def get_safe_dataframe(sheet_obj):
    all_values = sheet_obj.get_all_values()
    if not all_values or len(all_values) <= 1:
        return pd.DataFrame()
    
    headers = all_values[0]
    data = all_values[1:]
    
    safe_headers = []
    for idx, h in enumerate(headers):
        h_str = str(h).strip()
        if not h_str:
            safe_headers.append(f"열_{idx+1}")
        else:
            safe_headers.append(h_str)
            
    df = pd.DataFrame(data, columns=safe_headers)
    return df

# 안전한 날짜 변환 보조 함수
def safe_parse_date(series):
    parsed = pd.to_datetime(series, errors='coerce', format='mixed')
    return parsed.dt.date

# ---------------------------------------------------------
# 2. 마스터 데이터 및 배합비(Recipe) 정의
# ---------------------------------------------------------
RAW_ITEMS = [
    "카이피라", "프릴아이스", "버터헤드", "레드오크", 
    "로메인", "치커리", "적근대", "케일", 
    "양상추", "양배추", "적채", "당근"
]
ITEMS = ["선택 안함"] + RAW_ITEMS

INBOUND_VENDORS = ["에상스팜", "승승장구", "한스", "넥스토팜", "기타"]
OUTBOUND_VENDORS = ["스윗밸런스", "나무숲", "쿠팡"]

# 자동 배합비 레시피
DEFAULT_RECIPES = {
    "스윗밸런스 브런치빈 1kg": {
        "양상추": 0.6,
        "양배추": 0.2,
        "적채": 0.1,
        "프릴아이스": 0.1
    },
    "쿠팡 당근 200(6ea)": {
        "당근": 1.0
    },
    "쿠팡 당근 400(8ea)": {
        "당근": 3.0
    }
}

if "in_rows" not in st.session_state:
    st.session_state.in_rows = 4
if "out_rows" not in st.session_state:
    st.session_state.out_rows = 4

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

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📥 입고 등록 (다중)", 
    "📤 출고(사용) 등록 (다중)", 
    "🥗 배합비 자동 출고",
    "🚮 로스 등록", 
    "📅 거래처별 입고 정산",
    "🚚 거래처별 출고 정산",
    "📊 수불부 (재고 정산)"
])

# 최신 당일재고 가져오기
def get_latest_stock(sheet_obj, item_name):
    df_all = get_safe_dataframe(sheet_obj)
    if df_all.empty or "원료명" not in df_all.columns:
        return 0.0
    item_df = df_all[df_all["원료명"] == item_name]
    if item_df.empty:
        return 0.0
    last_stock = item_df.iloc[-1].get("당일재고", 0)
    val = pd.to_numeric(str(last_stock).replace(',', ''), errors='coerce')
    return float(val) if pd.notnull(val) else 0.0

# ---------------------------------------------------------
# TAB 1: 입고 등록
# ---------------------------------------------------------
with tab1:
    st.subheader("📥 원재료 입고 일괄 등록")
    
    col_date, col_vendor, col_btn = st.columns([1.5, 1.5, 1])
    with col_date:
        record_date = st.date_input("입고일자", value=datetime.today(), key="in_multi_date")
    with col_vendor:
        vendor = st.selectbox("입고 거래처", INBOUND_VENDORS, key="in_multi_vendor")
    with col_btn:
        st.write(" ")
        if st.button("➕ 품목 행 추가", use_container_width=True):
            st.session_state.in_rows += 1

    st.markdown("---")
    
    with st.form("multi_inbound_form", clear_on_submit=True):
        in_inputs = []
        
        h1, h2, h3, h4 = st.columns([2, 1.5, 1.5, 2])
        h1.caption("**원료명**")
        h2.caption("**입고 중량 (kg)**")
        h3.caption("**단가 (원/kg)**")
        h4.caption("**비고**")

        for i in range(st.session_state.in_rows):
            c1, c2, c3, c4 = st.columns([2, 1.5, 1.5, 2])
            with c1:
                item = st.selectbox(f"품목 #{i+1}", ITEMS, index=0, key=f"in_item_{i}", label_visibility="collapsed")
            with c2:
                weight = st.number_input(f"중량 #{i+1}", min_value=0.0, step=0.5, format="%.1f", key=f"in_weight_{i}", label_visibility="collapsed")
            with c3:
                price = st.number_input(f"단가 #{i+1}", min_value=0, step=100, key=f"in_price_{i}", label_visibility="collapsed")
            with c4:
                note = st.text_input(f"비고 #{i+1}", placeholder="특이사항 메모", key=f"in_note_{i}", label_visibility="collapsed")
                
            in_inputs.append({"item": item, "weight": weight, "price": price, "note": note})

        submitted = st.form_submit_button("📥 입력한 모든 입고 항목 일괄 저장하기", use_container_width=True)

        if submitted:
            saved_count = 0
            try:
                for row in in_inputs:
                    itm = str(row["item"])
                    w = float(row["weight"])
                    p = int(row["price"])
                    
                    if itm != "선택 안함" and w > 0:
                        nt = str(row["note"])
                        tot = int(round(w * p))
                        
                        prev_stock = get_latest_stock(sheet, itm)
                        day_stock = round(prev_stock + w, 2)
                        
                        row_data = [
                            str(record_date),
                            "야채 원재료",
                            itm,
                            float(prev_stock),
                            float(w),
                            0.0,
                            0.0,
                            float(day_stock),
                            str(vendor),
                            int(p),
                            int(tot),
                            nt
                        ]
                        sheet.append_row(row_data)
                        saved_count += 1

                if saved_count > 0:
                    st.success(f"✅ 총 {saved_count}개 입고 품목 저장 완료!")
                else:
                    st.warning("⚠️ 선택된 품목이 없거나 입고 중량이 0kg 초과인 항목이 없습니다.")
            except Exception as e:
                st.error(f"저장 실패: {e}")

    st.markdown("---")
    st.markdown("##### 🔍 구글 시트 실시간 저장 결과 (최근 8건)")
    try:
        recent_in_df = get_safe_dataframe(sheet)
        if not recent_in_df.empty:
            st.dataframe(recent_in_df.tail(8), use_container_width=True)
    except Exception:
        st.caption("최근 기록 조회 중...")

# ---------------------------------------------------------
# TAB 2: 출고(사용) 등록
# ---------------------------------------------------------
with tab2:
    st.subheader("📤 원재료 출고(사용) 일괄 등록")
    
    col_date2, col_vendor2, col_btn2 = st.columns([1.5, 1.5, 1])
    with col_date2:
        record_date_out = st.date_input("출고일자", value=datetime.today(), key="out_multi_date")
    with col_vendor2:
        vendor_out = st.selectbox("출고 거래처", OUTBOUND_VENDORS, key="out_multi_vendor")
    with col_btn2:
        st.write(" ")
        if st.button("➕ 출고 행 추가", use_container_width=True):
            st.session_state.out_rows += 1

    st.markdown("---")
    
    with st.form("multi_outbound_form", clear_on_submit=True):
        out_inputs = []
        
        h1, h2, h3 = st.columns([2, 2, 3])
        h1.caption("**원료명**")
        h2.caption("**출고(사용) 중량 (kg)**")
        h3.caption("**비고**")

        for i in range(st.session_state.out_rows):
            c1, c2, c3 = st.columns([2, 2, 3])
            with c1:
                item = st.selectbox(f"출고품목 #{i+1}", ITEMS, index=0, key=f"out_item_{i}", label_visibility="collapsed")
            with c2:
                weight = st.number_input(f"출고중량 #{i+1}", min_value=0.0, step=0.5, format="%.1f", key=f"out_weight_{i}", label_visibility="collapsed")
            with c3:
                note = st.text_input(f"출고비고 #{i+1}", placeholder="특이사항 메모", key=f"out_note_{i}", label_visibility="collapsed")
                
            out_inputs.append({"item": item, "weight": weight, "note": note})

        submitted_out = st.form_submit_button("📤 입력한 모든 출고 항목 일괄 저장하기", use_container_width=True)

        if submitted_out:
            saved_count = 0
            try:
                for row in out_inputs:
                    itm = str(row["item"])
                    w = float(row["weight"])
                    
                    if itm != "선택 안함" and w > 0:
                        nt = str(row["note"])
                        
                        prev_stock = get_latest_stock(sheet, itm)
                        day_stock = round(prev_stock - w, 2)
                        
                        row_data = [
                            str(record_date_out),
                            "야채 원재료",
                            itm,
                            float(prev_stock),
                            0.0,
                            float(w),
                            0.0,
                            float(day_stock),
                            str(vendor_out),
                            "-",
                            "-",
                            nt
                        ]
                        sheet.append_row(row_data)
                        saved_count += 1

                if saved_count > 0:
                    st.success(f"✅ 총 {saved_count}개 출고 품목 저장 완료!")
                else:
                    st.warning("⚠️ 선택된 품목이 없거나 출고 중량이 0kg 초과인 항목이 없습니다.")
            except Exception as e:
                st.error(f"저장 실패: {e}")

    st.markdown("---")
    st.markdown("##### 🔍 구글 시트 실시간 저장 결과 (최근 8건)")
    try:
        recent_out_df = get_safe_dataframe(sheet)
        if not recent_out_df.empty:
            st.dataframe(recent_out_df.tail(8), use_container_width=True)
    except Exception:
        st.caption("최근 기록 조회 중...")

# ---------------------------------------------------------
# TAB 3: 배합비(Recipe) 기반 자동 출고 등록
# ---------------------------------------------------------
with tab3:
    st.subheader("🥗 배합비(레시피) 기반 자동 출고 등록")
    
    col_r1, col_r2, col_r3 = st.columns([1.5, 1.5, 1.5])
    with col_r1:
        recipe_date = st.date_input("출고일자", value=datetime.today(), key="recipe_date")
    with col_r2:
        recipe_vendor = st.selectbox("출고 거래처", OUTBOUND_VENDORS, key="recipe_vendor")
    with col_r3:
        product_name = st.selectbox("생산/출고 제품 선택", list(DEFAULT_RECIPES.keys()), key="recipe_product")

    col_q1, col_q2 = st.columns([2, 2])
    with col_q1:
        prod_qty = st.number_input("생산/출고 수량 (개)", min_value=1, step=10, value=100, key="recipe_qty")
    with col_q2:
        recipe_note = st.text_input("비고", placeholder="예: 1차 생산분 출고", key="recipe_note")

    st.markdown("##### 📋 선택한 제품의 원재료 배합비 기준 사용량 계산")
    
    current_recipe = DEFAULT_RECIPES.get(product_name, {})
    
    recipe_calc_rows = []
    for item_name, unit_kg in current_recipe.items():
        total_needed_kg = round(unit_kg * prod_qty, 2)
        recipe_calc_rows.append({
            "원료명": item_name,
            "1개당 필요량 (kg)": unit_kg,
            "출고 수량 (개)": prod_qty,
            "총 필요 중량 (kg)": total_needed_kg
        })

    recipe_calc_df = pd.DataFrame(recipe_calc_rows)
    
    edited_recipe_df = st.data_editor(
        recipe_calc_df,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "원료명": st.column_config.SelectboxColumn("원료명", options=RAW_ITEMS, required=True),
            "1개당 필요량 (kg)": st.column_config.NumberColumn("1개당 필요량 (kg)", format="%.3f"),
            "출고 수량 (개)": st.column_config.NumberColumn("수량 (개)", disabled=True),
            "총 필요 중량 (kg)": st.column_config.NumberColumn("총 필요 중량 (kg)", format="%.2f")
        }
    )

    if st.button("🚀 계산된 배합비 원재료 일괄 출고 저장", use_container_width=True, type="primary"):
        saved_count = 0
        try:
            for idx, row in edited_recipe_df.iterrows():
                itm = str(row["원료명"])
                total_w = float(pd.to_numeric(row["총 필요 중량 (kg)"], errors='coerce') or 0.0)
                
                if itm and itm != "선택 안함" and total_w > 0:
                    prev_stock = get_latest_stock(sheet, itm)
                    day_stock = round(prev_stock - total_w, 2)
                    
                    full_note = f"[{product_name} {prod_qty}개 배합출고] {recipe_note}".strip()
                    
                    row_data = [
                        str(recipe_date),
                        "야채 원재료",
                        itm,
                        float(prev_stock),
                        0.0,
                        float(total_w),
                        0.0,
                        float(day_stock),
                        str(recipe_vendor),
                        "-",
                        "-",
                        full_note
                    ]
                    sheet.append_row(row_data)
                    saved_count += 1
            
            if saved_count > 0:
                st.success(f"✅ [{product_name} {prod_qty}개] 배합비에 따른 야채 원재료 {saved_count}종 출고 저장 완료!")
            else:
                st.warning("⚠️ 출고 중량이 0kg 초과인 원재료가 없습니다.")
        except Exception as e:
            st.error(f"배합비 출고 저장 실패: {e}")

# ---------------------------------------------------------
# TAB 4: 로스 등록
# ---------------------------------------------------------
with tab4:
    st.subheader("🚮 로스(폐기/손실) 등록")
    
    with st.form("loss_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            record_date = st.date_input("발생일자", value=datetime.today(), key="loss_date")
            item = st.selectbox("원료명", RAW_ITEMS, key="loss_item")

        with col2:
            loss_weight = st.number_input("로스 중량 (kg)", min_value=0.0, step=0.5, format="%.1f", key="loss_weight")
            note = st.text_input("사유", placeholder="예: 부패, 훼손 등", key="loss_note")

        submitted = st.form_submit_button("로스 저장하기", use_container_width=True)

        if submitted:
            try:
                itm = str(item)
                lw = float(loss_weight)
                prev_stock = get_latest_stock(sheet, itm)
                day_stock = round(prev_stock - lw, 2)
                
                row_data = [
                    str(record_date),
                    "야채 원재료",
                    itm,
                    float(prev_stock),
                    0.0,
                    0.0,
                    float(lw),
                    float(day_stock),
                    "자체폐기",
                    "-",
                    "-",
                    str(note)
                ]
                
                sheet.append_row(row_data)
                st.success(f"✅ [로스 완료] {itm} {lw}kg / 전일재고: {prev_stock}kg ➡️ 당일재고: {day_stock}kg")
            except Exception as e:
                st.error(f"저장 실패: {e}")

# ---------------------------------------------------------
# TAB 5: 거래처별 입고 정산 (해당 월 1일 자동 설정 적용)
# ---------------------------------------------------------
with tab5:
    st.subheader("📅 거래처별 입고 정산 내역")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        # 해당 월의 1일로 기본값 지정
        s_date_in = st.date_input("정산 시작일", value=get_first_day_of_month(), key="vendor_sdate")
    with c2:
        e_date_in = st.date_input("정산 종료일", value=datetime.today(), key="vendor_edate")
    with c3:
        v_filter = st.selectbox("거래처 필터", ["전체"] + INBOUND_VENDORS, key="vendor_filter")

    try:
        df = get_safe_dataframe(sheet)
        if not df.empty and "일자" in df.columns:
            df["일자_parsed"] = safe_parse_date(df["일자"])
            
            if "당일입고" in df.columns:
                s_in = df["당일입고"].astype(str).str.replace(',', '')
                df["당일입고"] = pd.to_numeric(s_in, errors='coerce').fillna(0)
            else:
                df["당일입고"] = 0.0

            in_df = df[df["당일입고"] > 0].copy()
            
            if not in_df.empty:
                filtered_in = in_df[
                    (in_df["일자_parsed"].notnull()) & 
                    (in_df["일자_parsed"] >= s_date_in) & 
                    (in_df["일자_parsed"] <= e_date_in)
                ].copy()
                
                if "거래처" not in filtered_in.columns:
                    filtered_in["거래처"] = "미지정"
                else:
                    filtered_in["거래처"] = filtered_in["거래처"].astype(str).replace(["", "None", "nan"], "미지정")
                
                if v_filter != "전체":
                    filtered_in = filtered_in[filtered_in["거래처"] == v_filter]
                    
                if not filtered_in.empty:
                    if "단가" in filtered_in.columns:
                        s_price = filtered_in["단가"].astype(str).str.replace(',', '')
                        filtered_in["단가_num"] = pd.to_numeric(s_price, errors='coerce').fillna(0)
                    else:
                        filtered_in["단가_num"] = 0.0

                    if "총금액" in filtered_in.columns:
                        s_tot = filtered_in["총금액"].astype(str).str.replace(',', '')
                        filtered_in["총금액_num"] = pd.to_numeric(s_tot, errors='coerce').fillna(0)
                    else:
                        filtered_in["총금액_num"] = 0.0

                    filtered_in["총금액_num"] = filtered_in.apply(
                        lambda r: r["총금액_num"] if r["총금액_num"] > 0 else round(r["당일입고"] * r["단가_num"]),
                        axis=1
                    )

                    if "비고" not in filtered_in.columns:
                        filtered_in["비고"] = "-"

                    period_str = f"{s_date_in} ~ {e_date_in}"

                    st.markdown("---")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("총 입고 건수", f"{len(filtered_in):,} 건")
                    m2.metric("총 입고 중량", f"{filtered_in['당일입고'].sum():,.1f} kg")
                    m3.metric("총 입고 금액", f"{filtered_in['총금액_num'].sum():,} 원")
                    st.markdown("---")

                    vendor_summary = filtered_in.groupby(["거래처", "원료명"]).agg(
                        총중량=("당일입고", "sum"),
                        총액=("총금액_num", "sum"),
                        평균단가=("단가_num", "mean"),
                        비고모음=("비고", lambda x: ", ".join(set(filter(None, map(str, x)))))
                    ).reset_index()

                    vendor_summary["총액_calc"] = vendor_summary.apply(
                        lambda r: r["총액"] if r["총액"] > 0 else round(r["총중량"] * r["평균단가"]),
                        axis=1
                    )

                    display_vendor_df = pd.DataFrame({
                        "기간": period_str,
                        "거래처": vendor_summary["거래처"],
                        "품명": vendor_summary["원료명"],
                        "입고 중량 (kg)": vendor_summary["총중량"].round(1),
                        "단가": vendor_summary["평균단가"].round(0),
                        "총액": vendor_summary["총액_calc"],
                        "비고": vendor_summary["비고모음"]
                    })

                    st.write("##### 📋 거래처별 입고 정산 집계표")
                    st.dataframe(
                        display_vendor_df.style.format({"단가": "{:,.0f}원", "총액": "{:,.0f}원"}),
                        use_container_width=True
                    )

                    with st.expander("🔍 일자별 개별 입고 상세 내역 보기 (날짜 오름차순)"):
                        detail_df = pd.DataFrame({
                            "기간": filtered_in["일자"],
                            "거래처": filtered_in["거래처"],
                            "품명": filtered_in["원료명"],
                            "입고 중량 (kg)": filtered_in["당일입고"],
                            "단가": filtered_in["단가_num"],
                            "총액": filtered_in["총금액_num"],
                            "비고": filtered_in["비고"]
                        }).sort_values(by="기간", ascending=True)
                        
                        st.dataframe(
                            detail_df.style.format({"단가": "{:,.0f}원", "총액": "{:,.0f}원"}),
                            use_container_width=True
                        )

                    b1, b2 = st.columns(2)
                    with b1:
                        excel_vendor = io.BytesIO()
                        with pd.ExcelWriter(excel_vendor, engine='openpyxl') as writer:
                            display_vendor_df.to_excel(writer, index=False, sheet_name='거래처별입고정산')
                        
                        st.download_button(
                            label="📥 거래처별 입고정산표 엑셀 다운로드",
                            data=excel_vendor.getvalue(),
                            file_name=f"거래처별_입고정산_{s_date_in}_{e_date_in}.xlsx",
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
                            ">🖨️ 정산표 인쇄 / PDF 저장</button>
                        """, height=45)
                else:
                    st.info("선택 조건에 해당하는 입고 내역이 없습니다.")
            else:
                st.info("입고된 데이터가 없습니다.")
        else:
            st.info("등록된 데이터가 없습니다.")
    except Exception as e:
        st.error(f"거래처별 입고 정산 조회 오류: {e}")

# ---------------------------------------------------------
# TAB 6: 거래처별 출고 정산 (해당 월 1일 자동 설정 적용)
# ---------------------------------------------------------
with tab6:
    st.subheader("🚚 거래처별 출고 정산 내역")
    
    o1, o2, o3 = st.columns(3)
    with o1:
        # 해당 월의 1일로 기본값 지정
        s_date_out = st.date_input("정산 시작일", value=get_first_day_of_month(), key="out_vendor_sdate")
    with o2:
        e_date_out = st.date_input("정산 종료일", value=datetime.today(), key="out_vendor_edate")
    with o3:
        vo_filter = st.selectbox("출고 거래처 필터", ["전체"] + OUTBOUND_VENDORS, key="out_vendor_filter")

    try:
        df = get_safe_dataframe(sheet)
        if not df.empty and "일자" in df.columns:
            df["일자_parsed"] = safe_parse_date(df["일자"])
            
            if "당일사용" in df.columns:
                s_use = df["당일사용"].astype(str).str.replace(',', '')
                df["당일사용"] = pd.to_numeric(s_use, errors='coerce').fillna(0)
            else:
                df["당일사용"] = 0.0

            out_df = df[df["당일사용"] > 0].copy()
            
            if not out_df.empty:
                filtered_out = out_df[
                    (out_df["일자_parsed"].notnull()) & 
                    (out_df["일자_parsed"] >= s_date_out) & 
                    (out_df["일자_parsed"] <= e_date_out)
                ].copy()
                
                if "거래처" not in filtered_out.columns:
                    filtered_out["거래처"] = "미지정"
                else:
                    filtered_out["거래처"] = filtered_out["거래처"].astype(str).replace(["", "None", "nan"], "미지정")
                
                if vo_filter != "전체":
                    filtered_out = filtered_out[filtered_out["거래처"] == vo_filter]
                    
                if not filtered_out.empty:
                    if "비고" not in filtered_out.columns:
                        filtered_out["비고"] = "-"

                    period_out_str = f"{s_date_out} ~ {e_date_out}"

                    st.markdown("---")
                    om1, om2 = st.columns(2)
                    om1.metric("총 출고 건수", f"{len(filtered_out):,} 건")
                    om2.metric("총 출고 중량", f"{filtered_out['당일사용'].sum():,.1f} kg")
                    st.markdown("---")

                    out_vendor_summary = filtered_out.groupby(["거래처", "원료명"]).agg(
                        총출고중량=("당일사용", "sum"),
                        출고건수=("당일사용", "count"),
                        비고모음=("비고", lambda x: ", ".join(set(filter(None, map(str, x)))))
                    ).reset_index()

                    display_out_vendor_df = pd.DataFrame({
                        "기간": period_out_str,
                        "거래처": out_vendor_summary["거래처"],
                        "원료명": out_vendor_summary["원료명"],
                        "총 출고 중량 (kg)": out_vendor_summary["총출고중량"].round(1),
                        "출고 건수": out_vendor_summary["출고건수"],
                        "비고": out_vendor_summary["비고모음"]
                    })

                    st.write("##### 📋 거래처별 출고 집계표")
                    st.dataframe(display_out_vendor_df, use_container_width=True)

                    with st.expander("🔍 일자별 개별 출고 상세 내역 보기 (날짜 오름차순)"):
                        out_detail_df = pd.DataFrame({
                            "일자": filtered_out["일자"],
                            "거래처": filtered_out["거래처"],
                            "원료명": filtered_out["원료명"],
                            "출고 중량 (kg)": filtered_out["당일사용"],
                            "비고": filtered_out["비고"]
                        }).sort_values(by="일자", ascending=True)
                        
                        st.dataframe(out_detail_df, use_container_width=True)

                    ob1, ob2 = st.columns(2)
                    with ob1:
                        excel_out_vendor = io.BytesIO()
                        with pd.ExcelWriter(excel_out_vendor, engine='openpyxl') as writer:
                            display_out_vendor_df.to_excel(writer, index=False, sheet_name='거래처별출고정산')
                        
                        st.download_button(
                            label="📥 거래처별 출고정산표 엑셀 다운로드",
                            data=excel_out_vendor.getvalue(),
                            file_name=f"거래처별_출고정산_{s_date_out}_{e_date_out}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    with ob2:
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
                            ">🖨️ 정산표 인쇄 / PDF 저장</button>
                        """, height=45)
                else:
                    st.info("선택 조건에 해당하는 출고 내역이 없습니다.")
            else:
                st.info("출고된 데이터가 없습니다.")
        else:
            st.info("등록된 데이터가 없습니다.")
    except Exception as e:
        st.error(f"거래처별 출고 정산 조회 오류: {e}")

# ---------------------------------------------------------
# TAB 7: 수불부 (해당 월 1일 자동 설정 적용)
# ---------------------------------------------------------
with tab7:
    st.subheader("📊 야채 원재료 수불부 (재고 정산)")
    
    ctrl1, ctrl2, ctrl3 = st.columns([1, 1, 0.8])
    with ctrl1:
        # 해당 월의 1일로 기본값 지정
        s_date = st.date_input("정산 시작일", value=get_first_day_of_month(), key="subul_sdate")
    with ctrl2:
        e_date = st.date_input("정산 종료일", value=datetime.today(), key="subul_edate")
    with ctrl3:
        st.write(" ")
        if st.button("🔄 수불부 새로고침", use_container_width=True):
            st.cache_data.clear()

    try:
        df = get_safe_dataframe(sheet)
        if not df.empty and "일자" in df.columns:
            df["일자_parsed"] = safe_parse_date(df["일자"])
            
            for col in ["전일재고", "당일입고", "당일사용", "로스", "당일재고"]:
                if col in df.columns:
                    s_val = df[col].astype(str).str.replace(',', '')
                    df[col] = pd.to_numeric(s_val, errors='coerce').fillna(0)
                else:
                    df[col] = 0.0

            prior_df = df[(df["일자_parsed"].notnull()) & (df["일자_parsed"] < s_date)]
            
            period_df = df[
                (df["일자_parsed"].notnull()) & 
                (df["일자_parsed"] >= s_date) & 
                (df["일자_parsed"] <= e_date)
            ].copy()

            summary_rows = []
            for item in RAW_ITEMS:
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

                st.write("##### 📅 선택 기간 일자별 상세 수불 내역 (날짜 오름차순)")
                if not period_df.empty:
                    display_period = pd.DataFrame({
                        "일자": period_df["일자"],
                        "원료명": period_df["원료명"],
                        "전일재고 (kg)": period_df["전일재고"],
                        "당일입고 (kg)": period_df["당일입고"],
                        "당일사용 (kg)": period_df["당일사용"],
                        "로스 (kg)": period_df["로스"],
                        "당일재고 (kg)": period_df["당일재고"]
                    }).sort_values(by=["일자", "원료명"], ascending=[True, True])
                    
                    st.dataframe(display_period, use_container_width=True)
                else:
                    st.info("선택 기간에 발생한 거래 이력이 없습니다.")

                with st.expander("📊 품목별 수불 집계 요약표 보기"):
                    st.dataframe(subul_df, use_container_width=True)

                b1, b2 = st.columns(2)
                with b1:
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        if not period_df.empty:
                            display_period.to_excel(writer, index=False, sheet_name='일별수불이력')
                        subul_df.to_excel(writer, index=False, sheet_name='품목별집계')
                    
                    st.download_button(
                        label="📥 수불부 엑셀 다운로드",
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

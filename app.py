import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import pandas as pd
import io

st.set_page_config(page_title="야채 원재료 수불 관리 시스템", layout="wide")

# ---------------------------------------------------------
# 1. 구글 시트 연동 및 보조 함수 (API 429 에러 방지 캐싱 적용)
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

@st.cache_data(ttl=60)
def fetch_sheet_data():
    doc = init_gspread()
    sheet_obj = doc.worksheet("시트1")
    all_values = sheet_obj.get_all_values()
    if not all_values or len(all_values) <= 1:
        return pd.DataFrame(columns=["일자", "구분", "거래처", "원료명", "수량(kg)", "단가", "총금액", "비고"])
    
    headers = [str(h).strip() for h in all_values[0]]
    data = all_values[1:]
    
    df = pd.DataFrame(data, columns=headers)
    
    if "구분" in df.columns:
        df["구분"] = df["구분"].astype(str).str.strip()
        df["구분"] = df["구분"].replace({
            "당일입고": "입고",
            "당일사용": "출고",
            "사용": "출고",
            "폐기": "로스",
            "손실": "로스"
        })
        
    return df

def get_first_day_of_month():
    today = date.today()
    return date(today.year, today.month, 1)

def safe_parse_date(series):
    s = series.astype(str).str.strip()
    parsed = pd.to_datetime(s, errors='coerce', format='mixed')
    return parsed.dt.date

# ---------------------------------------------------------
# 페이지마다 상단 제목 및 정산기간 고정 인쇄 컴포넌트
# ---------------------------------------------------------
# [버전 1] 거래처 & 비고 모두 포함 인쇄
def render_full_subul_print(df_summary, df_detail, period_str):
    tot_prev = df_summary['전일재고 (kg)'].sum() if '전일재고 (kg)' in df_summary else 0
    tot_in = df_summary['당일입고 (kg)'].sum() if '당일입고 (kg)' in df_summary else 0
    tot_use = df_summary['당일사용 (kg)'].sum() if '당일사용 (kg)' in df_summary else 0
    tot_loss = df_summary['로스 (kg)'].sum() if '로스 (kg)' in df_summary else 0
    tot_day = df_summary['당일재고 (kg)'].sum() if '당일재고 (kg)' in df_summary else 0
    
    summary_html = df_summary.to_html(index=False, classes="print-table").replace("\n", " ").replace("'", "\\'")
    detail_html = df_detail.to_html(index=False, classes="print-table").replace("\n", " ").replace("'", "\\'") if df_detail is not None and not df_detail.empty else "<p>상세 내역이 없습니다.</p>"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: sans-serif; margin: 0; padding: 0; }}
            .btn {{
                width: 100%;
                height: 38px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
                cursor: pointer;
            }}
            .btn:hover {{ background-color: #45a049; }}
        </style>
        <script>
            function runPrint() {{
                var pWin = window.open('', '_blank', 'width=1050,height=900');
                if (!pWin) {{
                    alert('팝업 차단을 해제해 주세요.');
                    return;
                }}
                var doc = pWin.document;
                doc.open();
                doc.write('<html><head><title>일자별 상세 수불부 보고서 (전체 포함)</title>');
                doc.write('<style>');
                doc.write('body {{ font-family: sans-serif; padding: 10px; color: #333; }}');
                doc.write('h2 {{ color: #1e3a8a; margin: 0 0 5px 0; font-size: 20px; }}');
                doc.write('h3 {{ margin-top: 15px; margin-bottom: 8px; color: #334155; border-bottom: 2px solid #cbd5e1; padding-bottom: 4px; font-size: 14px; }}');
                doc.write('.period {{ font-size: 13px; color: #475569; margin-bottom: 10px; font-weight: bold; }}');
                doc.write('.metric-table {{ width: 100%; margin-top: 15px; border-spacing: 6px; border-collapse: separate; }}');
                doc.write('.metric-card {{ background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px; text-align: center; }}');
                doc.write('.metric-title {{ font-size: 11px; color: #64748b; font-weight: bold; }}');
                doc.write('.metric-val {{ font-size: 14px; color: #0f172a; font-weight: bold; margin-top: 2px; }}');
                
                doc.write('.print-table {{ width: 100%; border-collapse: collapse; margin-top: 5px; font-size: 11px; }}');
                doc.write('.print-table th, .print-table td {{ border: 1px solid #cbd5e1; padding: 5px 4px; text-align: center; white-space: nowrap; }}');
                doc.write('.print-table th {{ background-color: #f1f5f9; font-weight: bold; }}');
                doc.write('.print-table td:last-child {{ white-space: normal; text-align: center; padding: 5px 6px; }}');
                
                doc.write('@media print {{');
                doc.write('  .repeat-header {{ display: table-header-group; }}');
                doc.write('  thead {{ display: table-header-group; }}');
                doc.write('  tr {{ page-break-inside: avoid; }}');
                doc.write('  body {{ padding: 0; }}');
                doc.write('}}');
                
                doc.write('</style></head><body>');
                
                doc.write('<table style="width:100%; border-collapse:collapse; border:none;">');
                doc.write('  <thead class="repeat-header">');
                doc.write('    <tr>');
                doc.write('      <th style="border:none; background:transparent; padding:0; text-align:left;">');
                doc.write('        <h2>📊 야채 원재료 수불 정산 보고서</h2>');
                doc.write('        <div class="period">정산 기간: {period_str}</div>');
                doc.write('      </th>');
                doc.write('    </tr>');
                doc.write('  </thead>');
                doc.write('  <tbody>');
                doc.write('    <tr>');
                doc.write('      <td style="border:none; padding:0; text-align:left;">');
                doc.write('        <h3>1. 일자별 개별 수불 상세 내역</h3>');
                doc.write('        {detail_html}');
                doc.write('        <h3>2. 품목별 수불 집계 요약표</h3>');
                doc.write('        {summary_html}');
                doc.write('        <h3 style="margin-top:20px;">3. 정산 기간 총량 집계 요약</h3>');
                doc.write('        <table class="metric-table"><tr><td class="metric-card"><div class="metric-title">기준일 이월재고 (정산시작 전일)</div><div class="metric-val">{tot_prev:,.1f} kg</div></td><td class="metric-card"><div class="metric-title">총 입고량</div><div class="metric-val">{tot_in:,.1f} kg</div></td><td class="metric-card"><div class="metric-title">총 출고/로스 사용량</div><div class="metric-val">{(tot_use + tot_loss):,.1f} kg</div></td><td class="metric-card"><div class="metric-title">정산 기말재고 (정산종료일)</div><div class="metric-val">{tot_day:,.1f} kg</div></td></tr></table>');
                doc.write('      </td>');
                doc.write('    </tr>');
                doc.write('  </tbody>');
                doc.write('</table>');
                
                doc.write('</body></html>');
                doc.close();
                pWin.focus();
                setTimeout(function(){{ pWin.print(); }}, 500);
            }}
        </script>
    </head>
    <body>
        <button class="btn" onclick="runPrint()">🖨️ 인쇄 (거래처/비고 포함)</button>
    </body>
    </html>
    """
    st.components.v1.html(html_content, height=45)

# [버전 2] 거래처 미포함 & 비고 미포함 인쇄
def render_full_subul_print_no_vendor(df_summary, df_detail, period_str):
    tot_prev = df_summary['전일재고 (kg)'].sum() if '전일재고 (kg)' in df_summary else 0
    tot_in = df_summary['당일입고 (kg)'].sum() if '당일입고 (kg)' in df_summary else 0
    tot_use = df_summary['당일사용 (kg)'].sum() if '당일사용 (kg)' in df_summary else 0
    tot_loss = df_summary['로스 (kg)'].sum() if '로스 (kg)' in df_summary else 0
    tot_day = df_summary['당일재고 (kg)'].sum() if '당일재고 (kg)' in df_summary else 0
    
    # 상세 내역에서 '거래처' 및 '비고' 열 제외 처리
    df_detail_clean = df_detail.copy() if df_detail is not None else None
    if df_detail_clean is not None and not df_detail_clean.empty:
        cols_to_drop = [col for col in ["거래처", "비고"] if col in df_detail_clean.columns]
        if cols_to_drop:
            df_detail_clean = df_detail_clean.drop(columns=cols_to_drop)

    summary_html = df_summary.to_html(index=False, classes="print-table").replace("\n", " ").replace("'", "\\'")
    detail_html = df_detail_clean.to_html(index=False, classes="print-table").replace("\n", " ").replace("'", "\\'") if df_detail_clean is not None and not df_detail_clean.empty else "<p>상세 내역이 없습니다.</p>"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: sans-serif; margin: 0; padding: 0; }}
            .btn {{
                width: 100%;
                height: 38px;
                background-color: #0284c7;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
                cursor: pointer;
            }}
            .btn:hover {{ background-color: #0369a1; }}
        </style>
        <script>
            function runPrint() {{
                var pWin = window.open('', '_blank', 'width=1050,height=900');
                if (!pWin) {{
                    alert('팝업 차단을 해제해 주세요.');
                    return;
                }}
                var doc = pWin.document;
                doc.open();
                doc.write('<html><head><title>일자별 상세 수불부 보고서 (거래처/비고 제외)</title>');
                doc.write('<style>');
                doc.write('body {{ font-family: sans-serif; padding: 10px; color: #333; }}');
                doc.write('h2 {{ color: #1e3a8a; margin: 0 0 5px 0; font-size: 20px; }}');
                doc.write('h3 {{ margin-top: 15px; margin-bottom: 8px; color: #334155; border-bottom: 2px solid #cbd5e1; padding-bottom: 4px; font-size: 14px; }}');
                doc.write('.period {{ font-size: 13px; color: #475569; margin-bottom: 10px; font-weight: bold; }}');
                doc.write('.metric-table {{ width: 100%; margin-top: 15px; border-spacing: 6px; border-collapse: separate; }}');
                doc.write('.metric-card {{ background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px; text-align: center; }}');
                doc.write('.metric-title {{ font-size: 11px; color: #64748b; font-weight: bold; }}');
                doc.write('.metric-val {{ font-size: 14px; color: #0f172a; font-weight: bold; margin-top: 2px; }}');
                
                doc.write('.print-table {{ width: 100%; border-collapse: collapse; margin-top: 5px; font-size: 11px; }}');
                doc.write('.print-table th, .print-table td {{ border: 1px solid #cbd5e1; padding: 5px 4px; text-align: center; white-space: nowrap; }}');
                doc.write('.print-table th {{ background-color: #f1f5f9; font-weight: bold; }}');
                
                doc.write('@media print {{');
                doc.write('  .repeat-header {{ display: table-header-group; }}');
                doc.write('  thead {{ display: table-header-group; }}');
                doc.write('  tr {{ page-break-inside: avoid; }}');
                doc.write('  body {{ padding: 0; }}');
                doc.write('}}');
                
                doc.write('</style></head><body>');
                
                doc.write('<table style="width:100%; border-collapse:collapse; border:none;">');
                doc.write('  <thead class="repeat-header">');
                doc.write('    <tr>');
                doc.write('      <th style="border:none; background:transparent; padding:0; text-align:left;">');
                doc.write('        <h2>📊 야채 원재료 수불 정산 보고서</h2>');
                doc.write('        <div class="period">정산 기간: {period_str}</div>');
                doc.write('      </th>');
                doc.write('    </tr>');
                doc.write('  </thead>');
                doc.write('  <tbody>');
                doc.write('    <tr>');
                doc.write('      <td style="border:none; padding:0; text-align:left;">');
                doc.write('        <h3>1. 일자별 개별 수불 상세 내역</h3>');
                doc.write('        {detail_html}');
                doc.write('        <h3>2. 품목별 수불 집계 요약표</h3>');
                doc.write('        {summary_html}');
                doc.write('        <h3 style="margin-top:20px;">3. 정산 기간 총량 집계 요약</h3>');
                doc.write('        <table class="metric-table"><tr><td class="metric-card"><div class="metric-title">기준일 이월재고 (정산시작 전일)</div><div class="metric-val">{tot_prev:,.1f} kg</div></td><td class="metric-card"><div class="metric-title">총 입고량</div><div class="metric-val">{tot_in:,.1f} kg</div></td><td class="metric-card"><div class="metric-title">총 출고/로스 사용량</div><div class="metric-val">{(tot_use + tot_loss):,.1f} kg</div></td><td class="metric-card"><div class="metric-title">정산 기말재고 (정산종료일)</div><div class="metric-val">{tot_day:,.1f} kg</div></td></tr></table>');
                doc.write('      </td>');
                doc.write('    </tr>');
                doc.write('  </tbody>');
                doc.write('</table>');
                
                doc.write('</body></html>');
                doc.close();
                pWin.focus();
                setTimeout(function(){{ pWin.print(); }}, 500);
            }}
        </script>
    </head>
    <body>
        <button class="btn" onclick="runPrint()">🖨️ 인쇄 (거래처/비고 미포함)</button>
    </body>
    </html>
    """
    st.components.v1.html(html_content, height=45)

def render_clean_summary_print(df_summary, period_str):
    table_html = df_summary.to_html(index=False, classes="print-table").replace('\n', ' ').replace("'", "\\'")
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: sans-serif; margin: 0; padding: 0; }}
            .btn {{
                width: 100%;
                height: 38px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                cursor: pointer;
            }}
        </style>
        <script>
            function runPrint() {{
                var pWin = window.open('', '_blank', 'width=850,height=900');
                if (!pWin) {{
                    alert('팝업 차단을 해제해 주세요.');
                    return;
                }}
                var doc = pWin.document;
                doc.open();
                doc.write('<html><head><title>거래처 정산 집계표</title>');
                doc.write('<style>');
                doc.write('body {{ font-family: sans-serif; padding: 20px; }}');
                doc.write('h2 {{ color: #1e3a8a; margin: 0 0 5px 0; }}');
                doc.write('.print-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; }}');
                doc.write('.print-table th, .print-table td {{ border: 1px solid #cbd5e1; padding: 6px; text-align: center; white-space: nowrap; }}');
                doc.write('.print-table th {{ background: #f1f5f9; }}');
                doc.write('.print-table td:last-child {{ white-space: normal; text-align: center; }}');
                doc.write('@media print {{ thead {{ display: table-header-group; }} tr {{ page-break-inside: avoid; }} }}');
                doc.write('</style>');
                doc.write('</head><body>');
                doc.write('<table style="width:100%; border-collapse:collapse;">');
                doc.write('  <thead>');
                doc.write('    <tr><th style="border:none; background:transparent; text-align:left; padding:0;">');
                doc.write('      <h2>📋 거래처 정산 집계표</h2>');
                doc.write('      <div style="margin-bottom:10px;"><b>정산 기간:</b> {period_str}</div>');
                doc.write('    </th></tr>');
                doc.write('  </thead>');
                doc.write('  <tbody>');
                doc.write('    <tr><td style="border:none; padding:0;">{table_html}</td></tr>');
                doc.write('  </tbody>');
                doc.write('</table>');
                doc.close();
                pWin.focus();
                setTimeout(function(){{ pWin.print(); }}, 500);
            }}
        </script>
    </head>
    <body>
        <button class="btn" onclick="runPrint()">🖨️ 정산 집계표 인쇄 / PDF 저장</button>
    </body>
    </html>
    """
    st.components.v1.html(html_content, height=45)

# ---------------------------------------------------------
# 2. 마스터 데이터 및 완제품 목록 정의
# ---------------------------------------------------------
RAW_ITEMS = [
    "카이피라", "프릴아이스", "버터헤드", "레드오크", 
    "로메인", "치커리", "적근대", "케일", 
    "양상추", "양배추", "적채", "당근"
]
ITEMS = ["선택 안함"] + RAW_ITEMS

INBOUND_VENDORS = ["에상스팜", "승승장구", "한스", "넥스토팜", "구름", "기타"]
OUTBOUND_VENDORS = ["스윗밸런스", "나무숲", "쿠팡", "기타"]

VENDOR_PRODUCT_MAP = {
    "스윗밸런스": ["브런치빈 믹스 1kg"],
    "쿠팡": ["쿠팡 당근 200(6ea)", "쿠팡 당근 400(8ea)"],
    "나무숲": ["선택 안함"],
    "기타": ["선택 안함"]
}

DEFAULT_RECIPES = {
    "스윗밸런스 브런치빈 1kg": {
        "양상추": 0.6,
        "양배추": 0.2,
        "적채": 0.1,
        "프릴아이스": 0.1
    },
    "쿠팡 당근 200(6ea)": {
        "당근": 0.181
    },
    "쿠팡 당근 400(8ea)": {
        "당근": 0.363
    }
}

if "in_rows" not in st.session_state:
    st.session_state.in_rows = 4
if "out_rows" not in st.session_state:
    st.session_state.out_rows = 4

# ---------------------------------------------------------
# 3. 메인 화면 및 시트 연동
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

# ---------------------------------------------------------
# TAB 1: 입고 등록
# ---------------------------------------------------------
with tab1:
    st.subheader("📥 원재료 입고 일괄 등록 (반품 시 -중량 입력)")
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
                weight = st.number_input(f"중량 #{i+1}", min_value=None, step=0.5, format="%.1f", key=f"in_weight_{i}", label_visibility="collapsed")
            with c3:
                price = st.number_input(f"단가 #{i+1}", min_value=None, step=100, key=f"in_price_{i}", label_visibility="collapsed")
            with c4:
                note = st.

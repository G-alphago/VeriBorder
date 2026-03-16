"""
VeriBorder - AI Cosmetic Regulation Analysis Platform
Main FastAPI Application - v5 (Korean Font + Emoji Fix)
"""

from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from typing import Optional
import anthropic
import base64
import os
import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = FastAPI(title="VeriBorder API", version="5.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 한글 폰트 등록 ───────────────────────────────────────────────────────────

def register_korean_font():
    """Mac에 내장된 한글 폰트 등록"""
    font_paths = [
        # Mac 기본 한글 폰트
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/Library/Fonts/NanumGothic.ttf",
        # 혹시 다른 경로에 있을 경우
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('Korean', path))
                pdfmetrics.registerFont(TTFont('Korean-Bold', path))
                return True
            except:
                continue

    return False

KOREAN_FONT_AVAILABLE = register_korean_font()
FONT_NAME = 'Korean' if KOREAN_FONT_AVAILABLE else 'Helvetica'
FONT_BOLD = 'Korean-Bold' if KOREAN_FONT_AVAILABLE else 'Helvetica-Bold'

# ─── 이모지 → 텍스트 변환 ────────────────────────────────────────────────────

EMOJI_MAP = {
    '🟢': '[GREEN]',
    '🟡': '[YELLOW]',
    '🔴': '[RED]',
    '📷': '[IMG]',
    '📋': '[REPORT]',
    '✅': '[CHECK]',
    '🔬': '[ANALYSIS]',
    '🛒': '[PLATFORM]',
    '💡': '[TIPS]',
    '⚠️': '[CAUTION]',
    '🌐': 'VeriBorder',
    '📄': '[PDF]',
}

def clean_text(text: str) -> str:
    """이모지를 텍스트로 변환하고 reportlab 안전한 문자열로 변환"""
    for emoji, replacement in EMOJI_MAP.items():
        text = text.replace(emoji, replacement)
    # 나머지 이모지/특수문자 제거
    result = ''
    for c in text:
        if ord(c) < 65536:
            result += c
    return result

# ─── System Prompt ────────────────────────────────────────────────────────────

VERIBORDER_SYSTEM_PROMPT = """
# Role
너는 글로벌 화장품 수출 규제 분석 AI 플랫폼 "VeriBorder"다.
화장품 성분표 이미지를 분석하고 국가별 규제 준수 여부를 평가하는 전문 AI다.

# 중요: 성분명 교정 규칙
이미지에서 성분을 읽을 때 반드시 다음을 수행한다:
1. OCR로 읽힌 한글 성분명을 정확한 INCI(국제화장품성분명) 영문명으로 변환
2. 오타나 불완전한 성분명은 가장 가까운 정확한 성분명으로 교정
3. 교정된 경우 "(교정됨)" 표시
예시:
- "카프릴릴/카프릭트리글리세라이드" → "Caprylic/Capric Triglyceride"
- "토코페롤" → "Tocopherol (Vitamin E)"
- "녹차추출물" → "Camellia Sinensis Leaf Extract"

# Supported Countries
United States (USA): MoCRA + FD&C Act 기반
Japan: PMD Act + Japan Cosmetic Ingredient Standards 기반
기타 국가: 글로벌 일반 규제 기준 참고 분석

# Ingredient Risk Levels
GREEN - 허용 성분
YELLOW - 제한/주의 성분
RED - 금지/고위험 성분

# Output Format (반드시 이 형식을 따른다)
---
## [추출 성분] 성분 목록
(이미지에서 읽어낸 성분 / INCI 영문명으로 교정하여 나열)

## [요약] Executive Summary
(제품 판매 가능 여부 2문장 요약)

## [판정] Final Compliance Decision
판정: 판매 가능 / 수정 권고 / 판매 불가
(판정 이유)

## [분석] 성분 규제 분석
| 성분 (INCI) | 위험도 | 판단 근거 |
|-------------|--------|-----------|
| 성분명 | GREEN/YELLOW/RED | 이유 |

## [플랫폼] 판매 전략
(선택 플랫폼별 주의사항)

## [권고] VeriBorder 전문가 권고사항
1. (실행 조치 1)
2. (실행 조치 2)
3. (실행 조치 3)

[주의] 본 분석은 규제 참고용이며 법률 자문을 대체하지 않습니다.
---
"""

# ─── PDF 생성 함수 ────────────────────────────────────────────────────────────

def generate_pdf(report_text: str, product_name: str, country: str, platform: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=15*mm, bottomMargin=15*mm
    )

    # 색상
    DARK = colors.HexColor('#1a1a1a')
    GREEN_COLOR = colors.HexColor('#2d7d46')
    LIGHT_GREEN = colors.HexColor('#eaf3de')
    GRAY = colors.HexColor('#666666')
    LIGHT_GRAY = colors.HexColor('#f5f5f0')
    BORDER = colors.HexColor('#e5e5e0')
    RED_COLOR = colors.HexColor('#cc3333')
    YELLOW_COLOR = colors.HexColor('#cc8800')

    # 스타일
    s_title   = ParagraphStyle('title',   fontName=FONT_BOLD,   fontSize=20, textColor=DARK,  spaceAfter=2)
    s_tagline = ParagraphStyle('tagline', fontName=FONT_NAME,   fontSize=9,  textColor=GRAY,  spaceAfter=8)
    s_meta    = ParagraphStyle('meta',    fontName=FONT_NAME,   fontSize=9,  textColor=GRAY)
    s_section = ParagraphStyle('section', fontName=FONT_BOLD,   fontSize=12, textColor=DARK,  spaceBefore=10, spaceAfter=5)
    s_body    = ParagraphStyle('body',    fontName=FONT_NAME,   fontSize=9,  textColor=DARK,  leading=14, spaceAfter=3)
    s_bullet  = ParagraphStyle('bullet',  fontName=FONT_NAME,   fontSize=9,  textColor=DARK,  leading=14, leftIndent=12, spaceAfter=2)
    s_disc    = ParagraphStyle('disc',    fontName=FONT_NAME,   fontSize=8,  textColor=GRAY,  spaceAfter=4)
    s_center  = ParagraphStyle('center',  fontName=FONT_NAME,   fontSize=8,  textColor=GRAY,  alignment=TA_CENTER)
    s_right   = ParagraphStyle('right',   fontName=FONT_NAME,   fontSize=9,  textColor=GRAY,  alignment=TA_RIGHT)

    story = []

    # ── 헤더 ──────────────────────────────────────────────────────────────────
    header_data = [[
        [Paragraph('VeriBorder', s_title),
         Paragraph('화장품 수출 규제 AI 분석 플랫폼', s_tagline)],
        Paragraph(f'생성일시: {datetime.now().strftime("%Y-%m-%d %H:%M")}', s_right)
    ]]
    ht = Table(header_data, colWidths=[120*mm, 50*mm])
    ht.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'), ('ALIGN',(1,0),(1,0),'RIGHT')]))
    story.append(ht)
    story.append(HRFlowable(width="100%", thickness=2, color=DARK))
    story.append(Spacer(1, 8))

    # ── 제품 정보 ─────────────────────────────────────────────────────────────
    info_data = [
        [Paragraph('제품명', ParagraphStyle('lbl', fontName=FONT_BOLD, fontSize=9, textColor=DARK)),
         Paragraph(clean_text(product_name or '-'), s_body)],
        [Paragraph('분석 국가', ParagraphStyle('lbl', fontName=FONT_BOLD, fontSize=9, textColor=DARK)),
         Paragraph(clean_text(country or '-'), s_body)],
        [Paragraph('판매 플랫폼', ParagraphStyle('lbl', fontName=FONT_BOLD, fontSize=9, textColor=DARK)),
         Paragraph(clean_text(platform or '미지정'), s_body)],
        [Paragraph('분석 일시', ParagraphStyle('lbl', fontName=FONT_BOLD, fontSize=9, textColor=DARK)),
         Paragraph(datetime.now().strftime("%Y년 %m월 %d일"), s_body)],
    ]
    it = Table(info_data, colWidths=[35*mm, 135*mm])
    it.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(0,-1),LIGHT_GRAY),
        ('GRID',(0,0),(-1,-1),0.5,BORDER),
        ('PADDING',(0,0),(-1,-1),6),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
    ]))
    story.append(it)
    story.append(Spacer(1, 12))

    # ── 리포트 본문 파싱 ───────────────────────────────────────────────────────
    lines = report_text.split('\n')
    table_rows = []
    in_table = False

    def flush_table():
        nonlocal table_rows, in_table
        if table_rows:
            col_widths = [75*mm, 22*mm, 73*mm]
            t = Table(table_rows, colWidths=col_widths, repeatRows=1)

            # 위험도 셀 색상 적용
            cell_styles = [
                ('BACKGROUND',(0,0),(-1,0),DARK),
                ('TEXTCOLOR',(0,0),(-1,0),colors.white),
                ('FONTNAME',(0,0),(-1,0),FONT_BOLD),
                ('FONTNAME',(0,1),(-1,-1),FONT_NAME),
                ('FONTSIZE',(0,0),(-1,-1),8),
                ('GRID',(0,0),(-1,-1),0.5,BORDER),
                ('PADDING',(0,0),(-1,-1),5),
                ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                ('ALIGN',(1,0),(1,-1),'CENTER'),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, LIGHT_GRAY]),
            ]
            # 위험도별 색상
            for row_idx, row in enumerate(table_rows[1:], 1):
                if len(row) > 1:
                    val = str(row[1]).strip().upper()
                    if 'GREEN' in val:
                        cell_styles.append(('TEXTCOLOR',(1,row_idx),(1,row_idx),GREEN_COLOR))
                        cell_styles.append(('FONTNAME',(1,row_idx),(1,row_idx),FONT_BOLD))
                    elif 'RED' in val:
                        cell_styles.append(('TEXTCOLOR',(1,row_idx),(1,row_idx),RED_COLOR))
                        cell_styles.append(('FONTNAME',(1,row_idx),(1,row_idx),FONT_BOLD))
                    elif 'YELLOW' in val:
                        cell_styles.append(('TEXTCOLOR',(1,row_idx),(1,row_idx),YELLOW_COLOR))
                        cell_styles.append(('FONTNAME',(1,row_idx),(1,row_idx),FONT_BOLD))

            t.setStyle(TableStyle(cell_styles))
            story.append(t)
            story.append(Spacer(1, 8))
        table_rows = []
        in_table = False

    for line in lines:
        raw = line.strip()
        if not raw or raw == '---':
            if in_table:
                flush_table()
            continue

        # 섹션 헤더
        if raw.startswith('## '):
            if in_table:
                flush_table()
            title = clean_text(raw[3:].strip())
            story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
            story.append(Paragraph(title, s_section))

        # 테이블
        elif raw.startswith('|'):
            cells = [c.strip() for c in raw.split('|') if c.strip()]
            if cells and not all(set(c) <= set('-|: ') for c in cells):
                clean_cells = [clean_text(c) for c in cells]
                while len(clean_cells) < 3:
                    clean_cells.append('')
                table_rows.append(clean_cells[:3])
                in_table = True

        # 번호 리스트
        elif raw and raw[0].isdigit() and '. ' in raw:
            if in_table:
                flush_table()
            story.append(Paragraph(clean_text(raw), s_bullet))

        # 불릿
        elif raw.startswith('- ') or raw.startswith('* '):
            if in_table:
                flush_table()
            story.append(Paragraph('• ' + clean_text(raw[2:]), s_bullet))

        # 면책 조항
        elif '[주의]' in raw or '[CAUTION]' in raw:
            if in_table:
                flush_table()
            story.append(Spacer(1, 8))
            story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
            story.append(Paragraph(clean_text(raw), s_disc))

        # 일반 텍스트
        else:
            if raw and not raw.startswith('###') and not raw.startswith('----'):
                cleaned = clean_text(raw)
                if cleaned.strip():
                    if in_table:
                        flush_table()
                    story.append(Paragraph(cleaned, s_body))

    if in_table:
        flush_table()

    # ── 푸터 ──────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1, color=DARK))
    story.append(Spacer(1, 4))
    story.append(Paragraph('VeriBorder | AI Cosmetic Export Regulation Platform | veriborder.com', s_center))

    doc.build(story)
    return buffer.getvalue()


# ─── 이미지 분석 ───────────────────────────────────────────────────────────────

@app.post("/api/analyze/image")
async def analyze_from_image(
    file: UploadFile = File(...),
    country: str = Form(...),
    platform: Optional[str] = Form(None),
    product_name: Optional[str] = Form("Unnamed Product"),
    product_claims: Optional[str] = Form("")
):
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="JPG, PNG, WEBP 파일만 가능합니다.")

    image_data = await file.read()
    base64_image = base64.standard_b64encode(image_data).decode("utf-8")
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    user_message = [
        {"type": "image", "source": {"type": "base64", "media_type": file.content_type, "data": base64_image}},
        {"type": "text", "text": f"""
이 이미지는 화장품 성분표입니다.
제품명: {product_name}
분석 대상 국가: {country}
판매 플랫폼: {platform or "미지정"}
광고/마케팅 문구: {product_claims or "없음"}

1. 이미지에서 성분 목록을 읽고 정확한 INCI 영문명으로 교정
2. 교정된 성분을 바탕으로 VeriBorder 전문가 규제 분석 리포트 작성
"""}
    ]

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=3000,
            system=VERIBORDER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
        return {"success": True, "report": message.content[0].text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 텍스트 분석 ───────────────────────────────────────────────────────────────

@app.post("/api/analyze/text")
async def analyze_from_text(
    ingredients: str = Form(...),
    country: str = Form(...),
    platform: Optional[str] = Form(None),
    product_name: Optional[str] = Form("Unnamed Product"),
    product_claims: Optional[str] = Form("")
):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    user_message = f"""
제품명: {product_name} / 국가: {country} / 플랫폼: {platform or "미지정"}
성분: {ingredients}
광고문구: {product_claims or "없음"}
VeriBorder 전문가 리포트를 작성해줘.
"""
    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=3000,
            system=VERIBORDER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
        return {"success": True, "report": message.content[0].text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── PDF 다운로드 ──────────────────────────────────────────────────────────────

@app.post("/api/export/pdf")
async def export_pdf(
    report: str = Form(...),
    product_name: Optional[str] = Form("Product"),
    country: Optional[str] = Form(""),
    platform: Optional[str] = Form("")
):
    try:
        pdf_bytes = generate_pdf(report, product_name, country, platform)
        filename = f"VeriBorder_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Health Check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "VeriBorder API v5.0", "korean_font": KOREAN_FONT_AVAILABLE}

@app.get("/api/options")
async def get_options():
    return {
        "countries": [
            {"code": "USA", "name": "United States", "flag": "🇺🇸"},
            {"code": "Japan", "name": "Japan", "flag": "🇯🇵"},
            {"code": "Other", "name": "기타 국가", "flag": "🌍"},
        ],
        "platforms": ["Amazon", "Qoo10", "eBay", "Shopee"]
    }
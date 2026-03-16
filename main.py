"""
VeriBorder - AI Cosmetic Regulation Analysis Platform
Main FastAPI Application - v7 (Final - All Fixes Applied)
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

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ModuleNotFoundError:
    REPORTLAB_AVAILABLE = False

app = FastAPI(title="VeriBorder API", version="7.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 한글 폰트 등록 ───────────────────────────────────────────────────────────

def register_korean_font():
    if not REPORTLAB_AVAILABLE:
        return False
    candidates = [
        "/opt/homebrew/share/fonts/nanum/NanumGothic.ttf",
        "/Library/Fonts/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",  # 서버 환경 fallback
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('KR',   path))
                pdfmetrics.registerFont(TTFont('KR-B', path))
                return True
            except:
                continue
    return False

KOREAN_FONT_AVAILABLE = register_korean_font()
F      = 'KR'   if KOREAN_FONT_AVAILABLE else 'Helvetica'
F_BOLD = 'KR-B' if KOREAN_FONT_AVAILABLE else 'Helvetica-Bold'

# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
# Role
너는 글로벌 화장품 수출 규제 분석 AI 플랫폼 "VeriBorder"다.
화장품 성분표 이미지를 분석하고 국가별 규제 준수 여부를 평가하는 전문 AI다.

# 성분명 교정 규칙
이미지에서 성분을 읽을 때:
1. OCR로 읽힌 한글/불완전한 성분명을 정확한 INCI 영문명으로 변환
2. 오타는 가장 가까운 정확한 성분명으로 교정

# Risk Levels
GREEN - 허용 성분
YELLOW - 제한/주의 성분
RED - 금지/고위험 성분

# 절대 규칙
- 존재하지 않는 법령 조항을 만들어내지 않는다
- 반드시 모든 항목을 완성하여 출력한다. 절대 중간에 끊지 않는다
- 성분이 아무리 많아도 전체를 빠짐없이 분석한다

# Output Format
---
## [추출 성분] 성분 목록
(INCI 영문명으로 교정하여 전체 나열)

## [요약] Executive Summary
(2문장 요약)

## [판정] Final Compliance Decision
판정: 판매 가능 / 수정 권고 / 판매 불가
(판정 이유)

## [분석] 성분 규제 분석
| 성분 (INCI) | 위험도 | 판단 근거 |
|-------------|--------|-----------|
| 성분명 | GREEN/YELLOW/RED | 이유 |

## [플랫폼] 판매 전략
(플랫폼별 주의사항)

## [권고] VeriBorder 전문가 권고사항
1. 조치 1
2. 조치 2
3. 조치 3

[주의] 본 분석은 규제 참고용이며 법률 자문을 대체하지 않습니다.
---
"""

# ─── PDF 스타일 헬퍼 ──────────────────────────────────────────────────────────

def sty(name, size=9, bold=False, color=None, align=TA_LEFT,
        leading=13, before=0, after=3, left=0):
    return ParagraphStyle(name,
        fontName=F_BOLD if bold else F,
        fontSize=size,
        textColor=color or colors.HexColor('#1a1a1a'),
        alignment=align, leading=leading,
        spaceBefore=before, spaceAfter=after, leftIndent=left)

# ─── PDF 생성 ─────────────────────────────────────────────────────────────────

def generate_pdf(report_text: str, product_name: str, country: str, platform: str) -> bytes:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab is not installed")
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=15*mm, bottomMargin=15*mm)

    DARK       = colors.HexColor('#1a1a1a')
    GRAY       = colors.HexColor('#666666')
    LIGHT_GRAY = colors.HexColor('#f5f5f0')
    BORDER     = colors.HexColor('#e5e5e0')
    GREEN_C    = colors.HexColor('#2d7d46')
    YELLOW_C   = colors.HexColor('#cc8800')
    RED_C      = colors.HexColor('#cc3333')

    s_section = sty('section', size=12, bold=True, before=10, after=5)
    s_body    = sty('body',    size=9,  leading=14, after=3)
    s_bullet  = sty('bullet',  size=9,  leading=14, after=2, left=10)
    s_disc    = sty('disc',    size=8,  color=GRAY, after=4)
    s_center  = sty('center',  size=8,  color=GRAY, align=TA_CENTER)
    s_lbl     = sty('lbl',     size=9,  bold=True)
    s_cell    = sty('cell',    size=8,  leading=12, after=0)
    s_c_g     = sty('cg',  size=8, leading=12, after=0, bold=True, color=GREEN_C)
    s_c_y     = sty('cy',  size=8, leading=12, after=0, bold=True, color=YELLOW_C)
    s_c_r     = sty('cr',  size=8, leading=12, after=0, bold=True, color=RED_C)

    story = []

    # ── 헤더: 로고+태그라인을 단일 Paragraph(XML)로 → 절대 겹치지 않음 ────────
    logo_para = Paragraph(
        f'VeriBorder<br/>'
        f'<font name="{F}" size="9" color="#666666">화장품 수출 규제 AI 분석 플랫폼</font>',
        ParagraphStyle('logo', fontName=F_BOLD, fontSize=22, leading=30,
                       textColor=DARK, spaceAfter=0, spaceBefore=0)
    )
    date_para = Paragraph(
        f'생성일시<br/>{datetime.now().strftime("%Y-%m-%d %H:%M")}',
        ParagraphStyle('date', fontName=F, fontSize=9, textColor=GRAY,
                       alignment=TA_RIGHT, leading=14, spaceAfter=0)
    )
    header = Table([[logo_para, date_para]], colWidths=[130*mm, 40*mm])
    header.setStyle(TableStyle([
        ('VALIGN',        (0,0),(-1,-1), 'TOP'),
        ('ALIGN',         (1,0),(1,0),   'RIGHT'),
        ('TOPPADDING',    (0,0),(-1,-1), 0),
        ('BOTTOMPADDING', (0,0),(-1,-1), 0),
        ('LEFTPADDING',   (0,0),(-1,-1), 0),
        ('RIGHTPADDING',  (0,0),(-1,-1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=2, color=DARK))
    story.append(Spacer(1, 8))

    # ── 제품 정보 ─────────────────────────────────────────────────────────────
    info = [
        [Paragraph('제품명',      s_lbl), Paragraph(product_name or '-', s_body)],
        [Paragraph('분석 국가',   s_lbl), Paragraph(country or '-',      s_body)],
        [Paragraph('판매 플랫폼', s_lbl), Paragraph(platform or '미지정', s_body)],
        [Paragraph('분석 일시',   s_lbl),
         Paragraph(datetime.now().strftime("%Y년 %m월 %d일"), s_body)],
    ]
    it = Table(info, colWidths=[30*mm, 140*mm])
    it.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(0,-1), LIGHT_GRAY),
        ('GRID',       (0,0),(-1,-1), 0.5, BORDER),
        ('PADDING',    (0,0),(-1,-1), 6),
        ('VALIGN',     (0,0),(-1,-1), 'MIDDLE'),
    ]))
    story.append(it)
    story.append(Spacer(1, 12))

    # ── 위험도 셀 (색상 텍스트) ───────────────────────────────────────────────
    def risk_cell(text):
        t = text.strip().upper()
        if t == 'GREEN':  return Paragraph('● GREEN',  s_c_g)
        if t == 'YELLOW': return Paragraph('● YELLOW', s_c_y)
        if t == 'RED':    return Paragraph('● RED',    s_c_r)
        return Paragraph(text, s_cell)

    # ── 본문 파싱 ─────────────────────────────────────────────────────────────
    lines = report_text.split('\n')
    tbl_rows = []
    in_tbl   = False

    def flush_tbl():
        nonlocal tbl_rows, in_tbl
        if not tbl_rows:
            in_tbl = False
            return
        # 성분명(68) | 위험도(24) | 판단근거(78) = 170mm
        # Paragraph로 감싸져 있어 자동 줄바꿈 & 셀 높이 자동 확장
        t = Table(tbl_rows, colWidths=[68*mm, 24*mm, 78*mm], repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(-1,0),  DARK),
            ('TEXTCOLOR',     (0,0),(-1,0),  colors.white),
            ('FONTNAME',      (0,0),(-1,0),  F_BOLD),
            ('FONTSIZE',      (0,0),(-1,-1), 8),
            ('GRID',          (0,0),(-1,-1), 0.5, BORDER),
            ('PADDING',       (0,0),(-1,-1), 5),
            ('VALIGN',        (0,0),(-1,-1), 'TOP'),
            ('ALIGN',         (1,0),(1,-1),  'CENTER'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.white, LIGHT_GRAY]),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))
        tbl_rows.clear()
        in_tbl = False

    for line in lines:
        raw = line.strip()

        if not raw or raw == '---':
            if in_tbl: flush_tbl()
            continue

        # 섹션 헤더
        if raw.startswith('## '):
            if in_tbl: flush_tbl()
            story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
            story.append(Paragraph(raw[3:].strip(), s_section))

        # 테이블 행
        elif raw.startswith('|'):
            cells = [c.strip() for c in raw.split('|') if c.strip()]
            if all(set(c) <= set('-|: ') for c in cells):
                continue  # 구분선 무시
            while len(cells) < 3:
                cells.append('')
            tbl_rows.append([
                Paragraph(cells[0], s_cell),
                risk_cell(cells[1]),
                Paragraph(cells[2], s_cell),
            ])
            in_tbl = True

        # 번호 리스트
        elif raw and raw[0].isdigit() and '. ' in raw:
            if in_tbl: flush_tbl()
            story.append(Paragraph(raw, s_bullet))

        # 불릿
        elif raw.startswith(('- ', '* ')):
            if in_tbl: flush_tbl()
            story.append(Paragraph('• ' + raw[2:], s_bullet))

        # 면책 조항
        elif '[주의]' in raw:
            if in_tbl: flush_tbl()
            story.append(Spacer(1, 8))
            story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
            story.append(Paragraph(raw, s_disc))

        # 일반 텍스트
        else:
            cleaned = raw.strip()
            if cleaned and not raw.startswith('###'):
                if in_tbl: flush_tbl()
                story.append(Paragraph(cleaned, s_body))

    if in_tbl: flush_tbl()

    # ── 푸터 ──────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1, color=DARK))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        'VeriBorder | AI Cosmetic Export Regulation Platform | veriborder.com',
        s_center))

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
    allowed = ["image/jpeg", "image/png", "image/webp", "image/gif"]
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="JPG, PNG, WEBP 파일만 가능합니다.")

    image_data = await file.read()
    b64 = base64.standard_b64encode(image_data).decode("utf-8")
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    user_message = [
        {"type": "image", "source": {"type": "base64", "media_type": file.content_type, "data": b64}},
        {"type": "text", "text": f"""
이 이미지는 화장품 성분표입니다.
제품명: {product_name}
분석 대상 국가: {country}
판매 플랫폼: {platform or "미지정"}
광고/마케팅 문구: {product_claims or "없음"}

1. 이미지에서 성분 목록 전체를 읽고 INCI 영문명으로 교정
2. 성분이 아무리 많아도 전부 빠짐없이 분석
3. 모든 항목 완성하여 출력 - 절대 중간에 끊지 말 것
"""}
    ]

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=16000,   # 모델 최대치 - 아무리 긴 리포트도 잘리지 않음
            system=SYSTEM_PROMPT,
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

성분이 아무리 많아도 전부 분석하고, 모든 항목을 빠짐없이 완성하여 출력. 절대 중간에 끊지 말 것.
"""
    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=16000,   # 모델 최대치
            system=SYSTEM_PROMPT,
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
    if not REPORTLAB_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="PDF export is temporarily unavailable (missing dependency: reportlab).",
        )
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


# ─── Health / Options ──────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "VeriBorder API v7.0",
        "korean_font": KOREAN_FONT_AVAILABLE,
        "font": F,
        "pdf_export": REPORTLAB_AVAILABLE,
        "max_tokens": 16000
    }

@app.get("/api/options")
async def get_options():
    return {
        "countries": [
            {"code": "USA",   "name": "United States", "flag": "🇺🇸"},
            {"code": "Japan", "name": "Japan",          "flag": "🇯🇵"},
            {"code": "Other", "name": "기타 국가",       "flag": "🌍"},
        ],
        "platforms": ["Amazon", "Qoo10", "eBay", "Shopee"]
    }
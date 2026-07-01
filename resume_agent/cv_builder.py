"""
Generalized CV builder — no hardcoded contact info.
Accepts cv_data dict from selector.build_cv_data().
"""
from __future__ import annotations
import os
import re
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

FONT_NAME = "Georgia"
NAME_SIZE = Pt(16)
CONTACT_SIZE = Pt(9.5)
SECTION_SIZE = Pt(11)
ROLE_SIZE = Pt(10.5)
BODY_SIZE = Pt(10)
MARGIN = Inches(0.75)
NAVY = RGBColor(0x2E, 0x40, 0x57)
GRAY = RGBColor(0x70, 0x70, 0x70)
LINK_BLUE = RGBColor(0x1A, 0x6E, 0xBD)

EM_DASH_RE = re.compile(r"\s*[—–]\s*")

CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]


def _get_chrome() -> str | None:
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return None


def sanitize(text: str) -> str:
    return EM_DASH_RE.sub(" | ", text)


def _apply_font(run, size, bold=False, italic=False, color=None):
    run.font.name = FONT_NAME
    run.font.size = size
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = color


def _set_margins(doc: Document):
    for section in doc.sections:
        section.top_margin = MARGIN
        section.bottom_margin = MARGIN
        section.left_margin = MARGIN
        section.right_margin = MARGIN


def _add_border(paragraph, color="2E4057"):
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    pBdr.append(bottom)
    pPr.append(pBdr)


def _section_header(doc: Document, title: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(title.upper())
    _apply_font(run, SECTION_SIZE, bold=True, color=NAVY)
    _add_border(p)


def _bullet(doc: Document, text: str):
    pb = doc.add_paragraph(style="List Bullet")
    pb.paragraph_format.space_before = Pt(0)
    pb.paragraph_format.space_after = Pt(1)
    pb.paragraph_format.left_indent = Inches(0.25)
    _apply_font(pb.add_run(sanitize(text)), BODY_SIZE)


def build_docx(cv_data: dict, output_path: str) -> str:
    """Build a CV docx from cv_data. Returns path."""
    contact = cv_data["contact"]

    doc = Document()
    _set_margins(doc)
    doc.styles["Normal"].font.name = FONT_NAME
    doc.styles["Normal"].font.size = BODY_SIZE

    # Header
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    _apply_font(p.add_run(contact["name"]), NAME_SIZE, bold=True, color=NAVY)

    line1_parts = [contact["email"], contact["phone"]]
    line2_parts = [contact["linkedin"]]
    if contact.get("github"):
        line2_parts.append(contact["github"])
    if contact.get("scholar_url"):
        line2_parts.append(contact["scholar_url"])
    line2_parts.append(contact["location"])

    for line in ("  |  ".join(line1_parts), "  |  ".join(line2_parts)):
        pc = doc.add_paragraph()
        pc.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pc.paragraph_format.space_before = Pt(0)
        pc.paragraph_format.space_after = Pt(1)
        _apply_font(pc.add_run(line), CONTACT_SIZE)

    # Summary (if present)
    if cv_data.get("summary"):
        _section_header(doc, "Professional Summary")
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(4)
        _apply_font(p.add_run(sanitize(cv_data["summary"])), BODY_SIZE, italic=True)

    # Experience
    if cv_data.get("experiences"):
        _section_header(doc, "Experience")
        for exp in cv_data["experiences"]:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(5)
            p.paragraph_format.space_after = Pt(2)
            r1 = p.add_run(f"{sanitize(exp['role'])}  |  {exp['org']}")
            _apply_font(r1, ROLE_SIZE, bold=True)
            if exp.get("dates"):
                _apply_font(p.add_run(f"  |  {exp['dates']}"), ROLE_SIZE, color=GRAY)
            for b in exp.get("bullets", []):
                _bullet(doc, b["text"])

    # Projects
    if cv_data.get("projects"):
        _section_header(doc, "Selected Projects")
        for proj in cv_data["projects"]:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(5)
            p.paragraph_format.space_after = Pt(1)
            _apply_font(p.add_run(sanitize(proj["name"])), ROLE_SIZE, bold=True)
            for b in proj.get("bullets", []):
                _bullet(doc, b["text"])

    # Skills
    if cv_data.get("skills"):
        _section_header(doc, "Skills")
        for cat, items in cv_data["skills"].items():
            if not items:
                continue
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            _apply_font(p.add_run(f"{cat}: "), BODY_SIZE, bold=True)
            _apply_font(p.add_run(", ".join(str(i) for i in items)), BODY_SIZE)

    # Achievements
    if cv_data.get("achievements"):
        _section_header(doc, "Selected Achievements")
        for a in cv_data["achievements"]:
            _bullet(doc, a["text"])

    # Education
    if cv_data.get("education"):
        _section_header(doc, "Education")
        for edu in cv_data["education"]:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(1)
            r1 = p.add_run(f"{edu['degree']}  |  {edu['institution']}")
            _apply_font(r1, ROLE_SIZE, bold=True)
            trailing = "  |  ".join(filter(None, [edu.get("dates", ""), edu.get("location", "")]))
            if trailing:
                _apply_font(p.add_run(f"  |  {trailing}"), ROLE_SIZE, color=GRAY)
            for detail in edu.get("details", []):
                _bullet(doc, detail)

    doc.save(output_path)
    return output_path


def build_pdf_via_html(cv_data: dict, pdf_path: str) -> str | None:
    """Generate PDF via Chrome headless from clean HTML. Returns path or None if Chrome not found."""
    chrome = _get_chrome()
    if not chrome:
        return None

    import html as _html

    def esc(s):
        return _html.escape(str(s)) if s else ""

    contact = cv_data["contact"]
    line1 = f"{esc(contact['email'])}  |  {esc(contact['phone'])}"
    line2_parts = [contact["linkedin"]]
    if contact.get("github"):
        line2_parts.append(contact["github"])
    if contact.get("scholar_url"):
        line2_parts.append(contact["scholar_url"])
    line2_parts.append(contact["location"])
    line2 = "  |  ".join(esc(x) for x in line2_parts)

    sections = []

    if cv_data.get("summary"):
        sections.append(
            f'<div class="sh">Summary</div>'
            f'<p class="summary">{esc(sanitize(cv_data["summary"]))}</p>'
        )

    if cv_data.get("experiences"):
        exp_html = '<div class="sh">Experience</div>'
        for e in cv_data["experiences"]:
            bullets = "".join(f"<li>{esc(sanitize(b['text']))}</li>" for b in e.get("bullets", []))
            exp_html += (
                f'<div class="block">'
                f'<div class="eh"><span class="role">{esc(e["role"])}</span>'
                f'<span class="sep"> | </span><span class="org">{esc(e["org"])}</span>'
                f'<span class="dt">{esc(e.get("dates",""))}</span></div>'
                f'<ul>{bullets}</ul></div>'
            )
        sections.append(exp_html)

    if cv_data.get("projects"):
        proj_html = '<div class="sh">Selected Projects</div>'
        for p in cv_data["projects"]:
            bullets = "".join(f"<li>{esc(sanitize(b['text']))}</li>" for b in p.get("bullets", []))
            url = f'<span class="url"> {esc(p["url"])}</span>' if p.get("url") else ""
            proj_html += f'<div class="block"><div><b>{esc(p["name"])}</b>{url}</div><ul>{bullets}</ul></div>'
        sections.append(proj_html)

    if cv_data.get("skills"):
        skill_html = '<div class="sh">Skills</div>'
        for cat, items in cv_data["skills"].items():
            if items:
                skill_html += f'<div class="sr"><b>{esc(cat)}:</b> {", ".join(esc(i) for i in items)}</div>'
        sections.append(skill_html)

    if cv_data.get("achievements"):
        ach = "".join(f"<li>{esc(sanitize(a['text']))}</li>" for a in cv_data["achievements"])
        sections.append(f'<div class="sh">Selected Achievements</div><ul>{ach}</ul>')

    if cv_data.get("education"):
        edu_html = '<div class="sh">Education</div>'
        for edu in cv_data["education"]:
            meta = " | ".join(filter(None, [edu.get("location",""), edu.get("dates","")]))
            details = "".join(f"<li>{esc(d)}</li>" for d in edu.get("details",[]))
            edu_html += (
                f'<div class="block"><div class="eh">'
                f'<span class="role">{esc(edu["degree"])}</span>'
                f'<span class="dt">{esc(meta)}</span></div>'
                f'<div class="org-line">{esc(edu["institution"])}</div>'
                f'{"<ul>"+details+"</ul>" if details else ""}</div>'
            )
        sections.append(edu_html)

    css = """
    @page{size:letter;margin:.75in}
    body{font-family:Georgia,'Times New Roman',serif;font-size:10pt;color:#222;line-height:1.35;margin:0}
    .name{font-size:16pt;font-weight:bold;color:#2E4057;text-align:center;margin-bottom:2pt}
    .ct{font-size:9.5pt;text-align:center;color:#444;margin-bottom:1pt}
    .sh{font-size:11pt;font-weight:bold;color:#2E4057;border-bottom:1pt solid #2E4057;
        margin-top:9pt;margin-bottom:4pt;padding-bottom:1pt}
    .block{margin-bottom:7pt;page-break-inside:avoid}
    .eh{display:flex;justify-content:space-between;align-items:baseline}
    .role{font-weight:bold;font-size:10.5pt}
    .org{font-size:10.5pt}
    .dt{font-size:9.5pt;color:#707070;white-space:nowrap;margin-left:8pt}
    .org-line{font-size:10pt;color:#444;margin-top:1pt}
    ul{margin:2pt 0 0 0;padding-left:15pt}
    li{margin-bottom:1.5pt}
    .summary{font-style:italic;margin:2pt 0 6pt 0;text-align:justify}
    .sr{margin-bottom:2.5pt}
    .url{color:#1A6EBD;font-size:9pt}
    p{margin:0}
    """

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><style>{css}</style></head>
<body>
<div class="name">{esc(contact["name"])}</div>
<div class="ct">{line1}</div>
<div class="ct">{line2}</div>
{"".join(sections)}
</body></html>"""

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as tmp:
        tmp.write(html)
        html_path = tmp.name

    try:
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-sandbox",
             "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}",
             f"file://{html_path}"],
            check=True, capture_output=True, timeout=30,
        )
        return pdf_path
    except Exception:
        return None
    finally:
        if os.path.exists(html_path):
            os.unlink(html_path)

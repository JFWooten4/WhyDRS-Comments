#!/usr/bin/env python
"""Build the SR-OCC-2025-801 letter PDF from markdown.

This renderer is intentionally small and local to the repo. It supports the
formatting needed for the final OCC comment: first-page WhyDRS mark, Times
fonts, legal-style section numbering, page footnotes with continuation, and
basic markdown inline emphasis.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


class RefParagraph(Paragraph):
    def __init__(
        self,
        text: str,
        style: ParagraphStyle,
        refs: list[int] | None = None,
        outline: tuple[str, int] | None = None,
        bulletText: str | None = None,
        **kwargs,
    ):
        self.footnote_refs = refs or []
        self.outline = outline
        super().__init__(text, style, bulletText=bulletText, **kwargs)


class TrackingDoc(SimpleDocTemplate):
    def __init__(self, *args, **kwargs):
        self.page_refs: dict[int, list[int]] = {}
        super().__init__(*args, **kwargs)

    def afterFlowable(self, flowable):
        for ref in getattr(flowable, "footnote_refs", []) or []:
            self.page_refs.setdefault(self.page, [])
            if ref not in self.page_refs[self.page]:
                self.page_refs[self.page].append(ref)

        outline = getattr(flowable, "outline", None)
        if outline:
            title, level = outline
            key = f"h-{self.page}-{abs(hash(title))}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, level=level, closed=False)


def roman(number: int) -> str:
    values = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    output = ""
    for value, symbol in values:
        while number >= value:
            output += symbol
            number -= value
    return output


def alpha(number: int) -> str:
    output = ""
    while number:
        number -= 1
        output = chr(65 + number % 26) + output
        number //= 26
    return output


def extract_letter(markdown: str) -> str:
    match = re.search(r"^# Letter\s*$", markdown, re.MULTILINE)
    if not match:
        raise ValueError("Could not find '# Letter' section")
    return markdown[match.end() :].strip()


def extract_footnotes(markdown: str) -> tuple[str, dict[str, str]]:
    notes: dict[str, str] = {}
    body: list[str] = []
    lines = markdown.splitlines()
    index = 0

    while index < len(lines):
        match = re.match(r"^\[\^([^\]]+)\]:\s*(.*)$", lines[index])
        if not match:
            body.append(lines[index])
            index += 1
            continue

        key = match.group(1)
        parts = [match.group(2).strip()]
        index += 1
        while index < len(lines):
            next_line = lines[index]
            if re.match(r"^\[\^[^\]]+\]:\s*", next_line):
                break
            if next_line.strip() and not next_line.startswith((" ", "\t")):
                break
            if next_line.strip():
                parts.append(next_line.strip())
            index += 1
        notes[key] = " ".join(parts).strip()

    return "\n".join(body), notes


class OccPdfRenderer:
    url_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    def __init__(self, source: Path, output: Path):
        self.source = source
        self.output = output
        self.order: list[str] = []
        self.nums: dict[str, int] = {}

        pdfmetrics.registerFontFamily(
            "Times-Roman",
            normal="Times-Roman",
            bold="Times-Bold",
            italic="Times-Italic",
            boldItalic="Times-BoldItalic",
        )

        raw = self.source.read_text(encoding="utf-8")
        self.body_text, self.note_defs = extract_footnotes(extract_letter(raw))
        self.styles = self._styles()

        self.page_width, self.page_height = LETTER
        self.left = 0.78 * inch
        self.right = 0.78 * inch
        self.top = 1.02 * inch
        self.bottom = 3.35 * inch
        self.foot_top = 3.05 * inch
        self.max_foot_width = self.page_width - self.left - self.right
        self.max_foot_height = self.foot_top - 0.12 * inch

    def _styles(self):
        styles = getSampleStyleSheet()
        base = "Times-Roman"
        bold = "Times-Bold"
        styles.add(
            ParagraphStyle(
                "BodyX",
                parent=styles["Normal"],
                fontName=base,
                fontSize=11,
                leading=14.2,
                spaceAfter=5.4,
            )
        )
        styles.add(
            ParagraphStyle(
                "H1X",
                parent=styles["Heading1"],
                fontName=bold,
                fontSize=16.5,
                leading=20,
                spaceBefore=10,
                spaceAfter=6.5,
            )
        )
        styles.add(
            ParagraphStyle(
                "H2X",
                parent=styles["Heading2"],
                fontName=bold,
                fontSize=13.7,
                leading=17,
                spaceBefore=8,
                spaceAfter=5,
            )
        )
        styles.add(
            ParagraphStyle(
                "H3X",
                parent=styles["Heading3"],
                fontName=bold,
                fontSize=12.2,
                leading=15.5,
                spaceBefore=7,
                spaceAfter=4,
            )
        )
        styles.add(
            ParagraphStyle(
                "H4X",
                parent=styles["Heading4"],
                fontName=bold,
                fontSize=11,
                leading=14,
                spaceBefore=6,
                spaceAfter=3,
            )
        )
        styles.add(
            ParagraphStyle(
                "QuoteX",
                parent=styles["BodyX"],
                leftIndent=0.28 * inch,
                rightIndent=0.18 * inch,
                borderColor=colors.HexColor("#AAB2BD"),
                borderWidth=0.6,
                borderPadding=6,
                spaceBefore=5,
                spaceAfter=7,
            )
        )
        styles.add(
            ParagraphStyle(
                "ListX",
                parent=styles["BodyX"],
                leftIndent=0.34 * inch,
                firstLineIndent=0,
                bulletIndent=0.16 * inch,
                bulletFontName=base,
                spaceBefore=1.5,
                spaceAfter=4.5,
            )
        )
        styles.add(
            ParagraphStyle(
                "FootX",
                fontName=base,
                fontSize=8.8,
                leading=9.9,
                leftIndent=0.20 * inch,
                firstLineIndent=-0.20 * inch,
                spaceAfter=1.8,
            )
        )
        return styles

    def note_number(self, key: str) -> int:
        if key not in self.nums:
            self.nums[key] = len(self.order) + 1
            self.order.append(key)
        return self.nums[key]

    def markdown_inline(self, text: str, refs_on: bool = True) -> tuple[str, list[int]]:
        refs: list[int] = []
        if refs_on:
            def replace_ref(match):
                number = self.note_number(match.group(1))
                refs.append(number)
                return f"@@FN{number}@@"

            text = re.sub(r"\[\^([^\]]+)\]", replace_ref, text)
        else:
            text = re.sub(r"\[\^([^\]]+)\]", "", text)

        text = text.replace("&nbsp;", " ")
        text = self.url_re.sub(lambda m: f"{m.group(1)} ({m.group(2)})", text)
        text = html.escape(text, quote=False)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"__([^_]+)__", r"<b>\1</b>", text)
        text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
        text = re.sub(r"(?<![\w/])_([^_\n]+)_(?![\w/])", r"<i>\1</i>", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"@@FN(\d+)@@", r"<super>\1</super>", text)
        return text, refs

    def paragraph(self, text: str, style: ParagraphStyle) -> RefParagraph:
        rendered, refs = self.markdown_inline(text, True)
        return RefParagraph(rendered, style, refs)

    def list_item(self, text: str, marker: str = "-") -> RefParagraph:
        rendered, refs = self.markdown_inline(text, True)
        return RefParagraph(rendered, self.styles["ListX"], refs, bulletText=marker)

    @staticmethod
    def clean_heading(text: str) -> str:
        return re.sub(
            r"^\s*(?:\d+(?:\.\d+)*\.?|[IVXLCDM]+\.?|[A-Z]\.)(?:\s+|$)",
            "",
            text,
        ).strip()

    def build_story(self, extra_pages: int = 0):
        story = []
        paragraph_lines: list[str] = []
        quote_lines: list[str] = []
        in_fence = False
        counts = {2: 0, 3: 0, 4: 0, 5: 0, 6: 0}

        def flush_paragraph():
            nonlocal paragraph_lines
            if paragraph_lines:
                text = " ".join(line.strip() for line in paragraph_lines if line.strip())
                story.append(self.paragraph(text, self.styles["BodyX"]))
                paragraph_lines = []

        def flush_quote():
            nonlocal quote_lines
            if quote_lines:
                chunks = []
                refs = []
                for quote in quote_lines:
                    rendered, quote_refs = self.markdown_inline(quote.strip(), True)
                    chunks.append(rendered)
                    refs.extend(quote_refs)
                story.append(RefParagraph("<br/>".join(chunks), self.styles["QuoteX"], refs))
                quote_lines = []

        def add_heading(level: int, title: str):
            for deeper in range(level + 1, 7):
                counts[deeper] = 0
            counts[level] += 1

            if level == 2:
                tag = f"{roman(counts[2])}."
            elif level == 3:
                tag = f"{roman(counts[2])}.{alpha(counts[3])}."
            elif level == 4:
                tag = f"{roman(counts[2])}.{alpha(counts[3])}.{counts[4]}."
            else:
                tag = (
                    f"{roman(counts[2])}.{alpha(counts[3])}."
                    f"{counts[4]}.{alpha(counts[5]).lower()}."
                )

            label = f"{tag} {self.clean_heading(title)}"
            rendered, refs = self.markdown_inline(label, True)
            style = {
                2: self.styles["H1X"],
                3: self.styles["H2X"],
                4: self.styles["H3X"],
            }.get(level, self.styles["H4X"])
            story.append(
                RefParagraph(rendered, style, refs, outline=(label, max(0, level - 2)))
            )

        for raw_line in self.body_text.splitlines():
            line = raw_line.rstrip()

            if line.strip().startswith("```"):
                flush_paragraph()
                flush_quote()
                in_fence = not in_fence
                continue
            if in_fence:
                if line.strip():
                    story.append(self.paragraph(line, self.styles["BodyX"]))
                continue
            if not line.strip():
                flush_paragraph()
                flush_quote()
                continue
            if line.strip() == "---":
                flush_paragraph()
                flush_quote()
                story += [
                    Spacer(1, 4),
                    HRFlowable(
                        width="100%",
                        thickness=0.5,
                        color=colors.HexColor("#9AA3AE"),
                    ),
                    Spacer(1, 7),
                ]
                continue

            image_match = re.match(r"!\[[^\]]*\]\(([^)]+)\)", line.strip())
            if image_match:
                flush_paragraph()
                flush_quote()
                image_path = (self.source.parent / image_match.group(1)).resolve()
                if image_path.exists():
                    with PILImage.open(image_path) as image:
                        width, height = image.size
                    scale = min((6.45 * inch) / width, (2.4 * inch) / height, 1.0)
                    story += [
                        Image(str(image_path), width * scale, height * scale),
                        Spacer(1, 8),
                    ]
                continue

            if line.startswith(">"):
                flush_paragraph()
                quote_lines.append(line.lstrip(">").strip())
                continue

            heading_match = re.match(r"^(#{2,6})\s+(.*)$", line)
            if heading_match:
                flush_paragraph()
                flush_quote()
                add_heading(len(heading_match.group(1)), heading_match.group(2))
                continue

            list_match = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
            if list_match:
                flush_paragraph()
                flush_quote()
                marker = list_match.group(2) if list_match.group(2).endswith(".") else "-"
                story.append(self.list_item(list_match.group(3), marker))
                continue

            paragraph_lines.append(line)

        flush_paragraph()
        flush_quote()
        for _ in range(extra_pages):
            story += [PageBreak(), Spacer(1, 1)]
        return story

    def footnote_paragraph(self, number: int) -> Paragraph:
        key = self.order[number - 1]
        text, _ = self.markdown_inline(
            self.note_defs.get(key, f"Missing footnote definition for {key}."),
            False,
        )
        return Paragraph(f"{number}. {text}", self.styles["FootX"])

    def process_page_items(self, items: list[Paragraph]) -> list[Paragraph]:
        y = self.max_foot_height
        remaining: list[Paragraph] = []
        for index, paragraph in enumerate(items):
            _, height = paragraph.wrap(self.max_foot_width, y)
            if height <= y:
                y -= height + 0.02 * inch
                continue

            pieces = paragraph.split(self.max_foot_width, y)
            if pieces:
                first = pieces[0]
                _, first_height = first.wrap(self.max_foot_width, y)
                if first_height <= y:
                    y -= first_height + 0.02 * inch
                    remaining.extend(pieces[1:])
                else:
                    remaining.append(paragraph)
            else:
                remaining.append(paragraph)
            remaining.extend(items[index + 1 :])
            break
        return remaining

    def continuation_pages_needed(self, page_refs: dict[int, list[int]], base_pages: int) -> int:
        carry: list[Paragraph] = []
        extra = 0
        page = 1
        while page <= base_pages or carry:
            refs = page_refs.get(page, []) if page <= base_pages else []
            items = carry + [self.footnote_paragraph(number) for number in refs]
            carry = self.process_page_items(items) if items else []
            if page > base_pages:
                extra += 1
            if extra > 30:
                raise RuntimeError("Footnote continuation required more than 30 pages")
            page += 1
        return extra

    def draw_logo(self, canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#1F2937"))
        canvas.setLineWidth(0.7)
        canvas.setFont("Times-Bold", 18)
        canvas.drawString(doc.leftMargin, self.page_height - 0.58 * inch, "WhyDRS")
        canvas.line(
            doc.leftMargin,
            self.page_height - 0.78 * inch,
            self.page_width - doc.rightMargin,
            self.page_height - 0.78 * inch,
        )
        canvas.restoreState()

    def page_drawer(self, page_refs: dict[int, list[int]]):
        carry: list[Paragraph] = []

        def draw(canvas, doc):
            nonlocal carry
            if doc.page == 1:
                self.draw_logo(canvas, doc)

            refs = page_refs.get(doc.page, [])
            items = carry + [self.footnote_paragraph(number) for number in refs]
            carry = []
            if not items:
                return

            canvas.saveState()
            yline = 0.30 * inch + self.foot_top
            canvas.setStrokeColor(colors.HexColor("#B8C0CC"))
            canvas.setLineWidth(0.45)
            canvas.line(doc.leftMargin, yline, self.page_width - doc.rightMargin, yline)
            y = yline - 0.08 * inch

            for index, paragraph in enumerate(items):
                available = y - 0.24 * inch
                _, height = paragraph.wrap(self.max_foot_width, available)
                if height <= available:
                    y -= height
                    paragraph.drawOn(canvas, doc.leftMargin, y)
                    y -= 0.02 * inch
                    continue

                pieces = paragraph.split(self.max_foot_width, available)
                if pieces:
                    first = pieces[0]
                    _, first_height = first.wrap(self.max_foot_width, available)
                    if first_height <= available:
                        y -= first_height
                        first.drawOn(canvas, doc.leftMargin, y)
                        carry = pieces[1:] + items[index + 1 :]
                        break
                carry = items[index:]
                break

            canvas.restoreState()

        draw.carry = lambda: carry
        return draw

    def document(self, path: Path) -> TrackingDoc:
        return TrackingDoc(
            str(path),
            pagesize=LETTER,
            leftMargin=self.left,
            rightMargin=self.right,
            topMargin=self.top,
            bottomMargin=self.bottom,
            title="In re SR-OCC-2025-801 - WhyDRS Comment Letter",
            author="WhyDRS",
        )

    def build(self) -> tuple[int, int, int]:
        tmp = self.output.with_suffix(".tmp.pdf")
        if tmp.exists():
            tmp.unlink()

        first_doc = self.document(tmp)
        first_doc.build(
            self.build_story(),
            onFirstPage=lambda _canvas, _doc: None,
            onLaterPages=lambda _canvas, _doc: None,
        )

        extra_pages = self.continuation_pages_needed(first_doc.page_refs, first_doc.page)
        drawer = self.page_drawer(first_doc.page_refs)
        final_doc = self.document(self.output)
        final_doc.build(
            self.build_story(extra_pages),
            onFirstPage=drawer,
            onLaterPages=drawer,
        )

        if tmp.exists():
            tmp.unlink()
        if drawer.carry():
            raise RuntimeError("Footnote continuation text remained after final page")
        return final_doc.page, len(self.order), extra_pages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("SR-OCC-2025-801/README.md"),
        help="Markdown source file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("SR-OCC-2025-801/SR-OCC-2025-801-WhyDRS-letterhead.pdf"),
        help="PDF output path",
    )
    args = parser.parse_args()

    renderer = OccPdfRenderer(args.source, args.output)
    pages, footnotes, continuations = renderer.build()
    print(args.output)
    print(f"pages: {pages}")
    print(f"footnotes: {footnotes}")
    print(f"continuation pages: {continuations}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

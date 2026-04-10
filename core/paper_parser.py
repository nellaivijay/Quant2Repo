"""Multi-backend PDF paper parser for Quant2Repo.

Supports GROBID, doc2json, PyMuPDF, and PyPDF2 backends.
"""

import os
import re
import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import requests

logger = logging.getLogger(__name__)


@dataclass
class ParsedSection:
    """A section of a parsed paper."""
    title: str
    content: str
    level: int = 1
    page_start: Optional[int] = None
    page_end: Optional[int] = None


@dataclass
class ParsedPaper:
    """Result of parsing a paper PDF."""
    title: str = ""
    authors: list = field(default_factory=list)
    abstract: str = ""
    sections: list = field(default_factory=list)  # list[ParsedSection]
    full_text: str = ""
    references: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    figures: list = field(default_factory=list)
    page_count: int = 0
    source_path: str = ""
    parse_backend: str = ""
    raw_token_estimate: int = 0

    def get_section(self, title_pattern: str) -> Optional[ParsedSection]:
        """Find a section by title pattern (case-insensitive regex)."""
        for section in self.sections:
            if re.search(title_pattern, section.title, re.IGNORECASE):
                return section
        return None

    def get_text_for_analysis(self, max_chars: int = 500_000) -> str:
        """Get paper text suitable for LLM analysis."""
        if self.full_text and len(self.full_text) <= max_chars:
            return self.full_text
        parts = []
        if self.title:
            parts.append(f"Title: {self.title}")
        if self.authors:
            parts.append(f"Authors: {', '.join(self.authors)}")
        if self.abstract:
            parts.append(f"\nAbstract:\n{self.abstract}")
        for section in self.sections:
            header = "#" * section.level + " " + section.title
            parts.append(f"\n{header}\n{section.content}")
            if sum(len(p) for p in parts) > max_chars:
                break
        return "\n".join(parts)[:max_chars]


class PaperParser:
    """Multi-backend PDF paper parser.

    Tries backends in order: GROBID -> PyMuPDF -> PyPDF2
    """

    BACKENDS = ["grobid", "pymupdf", "pypdf2"]

    def __init__(self, preferred_backend: Optional[str] = None,
                 grobid_url: str = "http://localhost:8070"):
        self.preferred_backend = preferred_backend
        self.grobid_url = grobid_url

    def parse(self, pdf_path: str) -> ParsedPaper:
        """Parse a PDF paper using the best available backend."""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        backends = self.BACKENDS
        if self.preferred_backend:
            backends = [self.preferred_backend] + [
                b for b in backends if b != self.preferred_backend
            ]

        for backend in backends:
            try:
                method = getattr(self, f"_parse_{backend}")
                result = method(pdf_path)
                if result and (result.full_text or result.sections):
                    result.source_path = pdf_path
                    result.parse_backend = backend
                    result.raw_token_estimate = len(result.full_text) // 4
                    logger.info(f"Parsed with {backend}: {result.page_count} pages, "
                                f"~{result.raw_token_estimate} tokens")
                    return result
            except ImportError:
                logger.debug(f"Backend {backend} not available (missing dependency)")
            except Exception as e:
                logger.warning(f"Backend {backend} failed: {e}")

        raise RuntimeError(f"All parse backends failed for {pdf_path}")

    def _parse_grobid(self, pdf_path: str) -> ParsedPaper:
        """Parse using GROBID service."""
        url = f"{self.grobid_url}/api/processFulltextDocument"
        with open(pdf_path, "rb") as f:
            resp = requests.post(url, files={"input": f}, timeout=120)

        if resp.status_code != 200:
            raise RuntimeError(f"GROBID returned {resp.status_code}")

        tei_xml = resp.text
        return self._parse_tei_xml(tei_xml, pdf_path)

    def _parse_tei_xml(self, xml_text: str, pdf_path: str) -> ParsedPaper:
        """Parse GROBID TEI XML output."""
        try:
            from lxml import etree
        except ImportError:
            return self._parse_tei_regex(xml_text, pdf_path)

        ns = {"tei": "http://www.tei-c.org/ns/1.0"}
        root = etree.fromstring(xml_text.encode())

        title_el = root.find(".//tei:titleStmt/tei:title", ns)
        title = title_el.text.strip() if title_el is not None and title_el.text else ""

        authors = []
        for author in root.findall(".//tei:sourceDesc//tei:persName", ns):
            parts = []
            for name_part in author:
                if name_part.text:
                    parts.append(name_part.text.strip())
            if parts:
                authors.append(" ".join(parts))

        abstract_el = root.find(".//tei:profileDesc/tei:abstract", ns)
        abstract = ""
        if abstract_el is not None:
            abstract = " ".join(abstract_el.itertext()).strip()

        sections = []
        for div in root.findall(".//tei:body/tei:div", ns):
            head = div.find("tei:head", ns)
            sec_title = head.text.strip() if head is not None and head.text else "Untitled"
            content = " ".join(div.itertext()).strip()
            if content.startswith(sec_title):
                content = content[len(sec_title):].strip()
            sections.append(ParsedSection(title=sec_title, content=content))

        full_text = f"{title}\n\n{abstract}\n\n" + "\n\n".join(
            f"{s.title}\n{s.content}" for s in sections
        )

        return ParsedPaper(
            title=title, authors=authors, abstract=abstract,
            sections=sections, full_text=full_text,
        )

    def _parse_tei_regex(self, xml_text: str, pdf_path: str) -> ParsedPaper:
        """Fallback TEI parsing with regex."""
        title_m = re.search(r"<title[^>]*>(.*?)</title>", xml_text, re.DOTALL)
        title = title_m.group(1).strip() if title_m else ""

        abstract_m = re.search(r"<abstract>(.*?)</abstract>", xml_text, re.DOTALL)
        abstract = re.sub(r"<[^>]+>", "", abstract_m.group(1)).strip() if abstract_m else ""

        full_text = re.sub(r"<[^>]+>", " ", xml_text)
        full_text = re.sub(r"\s+", " ", full_text).strip()

        return ParsedPaper(title=title, abstract=abstract, full_text=full_text)

    def _parse_pymupdf(self, pdf_path: str) -> ParsedPaper:
        """Parse using PyMuPDF (fitz)."""
        import fitz

        doc = fitz.open(pdf_path)
        pages_text = []
        for page in doc:
            pages_text.append(page.get_text())

        full_text = "\n\n".join(pages_text)
        title = pages_text[0].split("\n")[0].strip() if pages_text else ""

        abstract = ""
        abs_match = re.search(
            r"(?:abstract|summary)\s*\n(.*?)(?:\n\s*\n|\n\d+\s*\.?\s*introduction)",
            full_text, re.IGNORECASE | re.DOTALL
        )
        if abs_match:
            abstract = abs_match.group(1).strip()

        sections = self._extract_sections(full_text)

        return ParsedPaper(
            title=title, abstract=abstract,
            sections=sections, full_text=full_text,
            page_count=len(doc),
        )

    def _parse_pypdf2(self, pdf_path: str) -> ParsedPaper:
        """Parse using PyPDF2."""
        from PyPDF2 import PdfReader

        reader = PdfReader(pdf_path)
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)

        full_text = "\n\n".join(pages_text)
        title = pages_text[0].split("\n")[0].strip() if pages_text else ""

        abstract = ""
        abs_match = re.search(
            r"(?:abstract|summary)\s*\n(.*?)(?:\n\s*\n|\n\d+\s*\.?\s*introduction)",
            full_text, re.IGNORECASE | re.DOTALL
        )
        if abs_match:
            abstract = abs_match.group(1).strip()

        sections = self._extract_sections(full_text)

        return ParsedPaper(
            title=title, abstract=abstract,
            sections=sections, full_text=full_text,
            page_count=len(reader.pages),
        )

    def _extract_sections(self, text: str) -> list:
        """Extract sections from plain text using heading heuristics."""
        sections = []
        pattern = re.compile(
            r"^(\d+\.?\s+[A-Z][^\n]{3,80})$|"
            r"^([A-Z][A-Z\s]{5,60})$",
            re.MULTILINE
        )

        matches = list(pattern.finditer(text))
        for i, match in enumerate(matches):
            title = (match.group(1) or match.group(2)).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            if len(content) > 50:
                sections.append(ParsedSection(title=title, content=content))

        return sections

    def extract_page_images(self, pdf_path: str, dpi: int = 150,
                            max_pages: int = 30) -> list:
        """Extract page images for vision-based analysis."""
        try:
            import fitz
        except ImportError:
            logger.warning("PyMuPDF not available for image extraction")
            return []

        doc = fitz.open(pdf_path)
        images = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            img_path = os.path.join(tempfile.gettempdir(), f"q2r_page_{i}.png")
            pix.save(img_path)
            images.append(img_path)

        return images


def download_pdf(url: str, save_dir: Optional[str] = None,
                 timeout: int = 120, max_size_mb: int = 100) -> str:
    """Download a PDF from URL.

    Handles arXiv, SSRN, NBER, and direct PDF links.
    """
    if save_dir is None:
        save_dir = tempfile.gettempdir()

    # Normalize arXiv URLs
    if "arxiv.org/abs/" in url:
        url = url.replace("/abs/", "/pdf/")
        if not url.endswith(".pdf"):
            url += ".pdf"

    # Normalize SSRN URLs
    if "ssrn.com" in url and "abstract_id=" in url:
        ssrn_id = re.search(r"abstract_id=(\d+)", url)
        if ssrn_id:
            url = f"https://papers.ssrn.com/sol3/Delivery.cfm?abstractid={ssrn_id.group(1)}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Quant2Repo Research Tool)",
        "Accept": "application/pdf,*/*",
    }

    logger.info(f"Downloading PDF from {url}")
    resp = requests.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True)
    resp.raise_for_status()

    content_length = int(resp.headers.get("Content-Length", 0))
    if content_length > max_size_mb * 1024 * 1024:
        raise ValueError(f"PDF too large: {content_length / 1024 / 1024:.1f} MB")

    filename = "paper.pdf"
    if "Content-Disposition" in resp.headers:
        cd = resp.headers["Content-Disposition"]
        fn_match = re.search(r'filename="?([^";\s]+)"?', cd)
        if fn_match:
            filename = fn_match.group(1)

    save_path = os.path.join(save_dir, filename)
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    file_size = os.path.getsize(save_path)
    logger.info(f"Downloaded {file_size / 1024:.0f} KB to {save_path}")

    return save_path

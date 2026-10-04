from __future__ import annotations

import hashlib
import io
import ipaddress
import re
import socket
from typing import Any
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import httpx
from pypdf import PdfReader

from ...domain.errors import DomainValidationError
from ...domain.jd_interview import JDSourceType, NormalizedJD


MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
MAX_URL_RESPONSE_BYTES = 5 * 1024 * 1024  # 5MB
HTTP_TIMEOUT_SECONDS = 10.0

ALLOWED_FILE_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "application/octet-stream",
}

# Vietnamese accent characters to detect language
VIETNAMESE_CHARS_REGEX = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)


class TextNormalizer:
    @staticmethod
    def clean(raw_text: str) -> str:
        if not raw_text:
            return ""
        # Remove control characters except standard whitespace
        cleaned = "".join(ch for ch in raw_text if ch == "\n" or ch == "\t" or (ch >= " " and ord(ch) != 127))
        # Collapse multiple spaces on the same line
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        # Collapse 3 or more newlines into 2
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def detect_language(text: str) -> str:
        matches = VIETNAMESE_CHARS_REGEX.findall(text)
        # If there are notable Vietnamese characters, classify as Vietnamese
        if len(matches) >= 3:
            return "vi"
        return "en"

    @classmethod
    def create_normalized_jd(
        cls,
        source_type: JDSourceType,
        raw_content: str,
        original_filename: str | None = None,
        original_url: str | None = None,
    ) -> NormalizedJD:
        cleaned = cls.clean(raw_content)
        if len(cleaned) < 30:
            raise DomainValidationError("Nội dung Job Description quá ngắn (tối thiểu 30 ký tự)")
        checksum = NormalizedJD.calculate_checksum(cleaned)
        language = cls.detect_language(cleaned)
        warnings: list[str] = []
        if len(cleaned) < 100:
            warnings.append("JD có độ dài khá ngắn, có thể ảnh hưởng đến độ chi tiết của câu hỏi.")

        return NormalizedJD(
            source_type=source_type.value,
            raw_content=raw_content,
            cleaned_text=cleaned,
            checksum=checksum,
            original_filename=original_filename,
            original_url=original_url,
            language=language,
            warnings=warnings,
        )


class FileIngestionService:
    @staticmethod
    def extract_text_from_pdf(content: bytes) -> str:
        try:
            reader = PdfReader(io.BytesIO(content))
            pages_text: list[str] = []
            for idx, page in enumerate(reader.pages):
                extracted = page.extract_text() or ""
                if extracted.strip():
                    pages_text.append(extracted.strip())
            full_text = "\n\n".join(pages_text)
            if not full_text.strip():
                raise DomainValidationError("Không thể trích xuất văn bản từ tệp PDF (tệp có thể là ảnh quét)")
            return full_text
        except DomainValidationError:
            raise
        except Exception as exc:
            raise DomainValidationError(f"Lỗi khi đọc file PDF: {str(exc)}") from exc

    @staticmethod
    def extract_text_from_docx(content: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as docx_zip:
                xml_content = docx_zip.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            # Find all <w:t> elements
            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs: list[str] = []
            for p in tree.iterfind(".//w:p", namespace):
                texts = [node.text for node in p.iterfind(".//w:t", namespace) if node.text]
                if texts:
                    paragraphs.append("".join(texts))
            full_text = "\n".join(paragraphs)
            if not full_text.strip():
                raise DomainValidationError("Tệp DOCX không chứa văn bản hợp lệ")
            return full_text
        except DomainValidationError:
            raise
        except Exception as exc:
            raise DomainValidationError(f"Lỗi khi đọc file DOCX: {str(exc)}") from exc

    @classmethod
    def ingest_file(cls, filename: str, content: bytes, mime_type: str | None = None) -> NormalizedJD:
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise DomainValidationError(
                f"Kích thước tệp vượt quá giới hạn cho phép (tối đa {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB)"
            )

        lower_filename = filename.lower().strip()
        matched_ext = next((ext for ext in ALLOWED_FILE_EXTENSIONS if lower_filename.endswith(ext)), None)
        if not matched_ext:
            raise DomainValidationError(
                f"Định dạng tệp không được hỗ trợ. Các định dạng cho phép: {', '.join(sorted(ALLOWED_FILE_EXTENSIONS))}"
            )

        if matched_ext == ".pdf":
            raw_text = cls.extract_text_from_pdf(content)
        elif matched_ext == ".docx":
            raw_text = cls.extract_text_from_docx(content)
        else:
            # .txt or .md
            try:
                raw_text = content.decode("utf-8")
            except UnicodeDecodeError:
                raw_text = content.decode("latin-1")

        return TextNormalizer.create_normalized_jd(
            source_type=JDSourceType.file,
            raw_content=raw_text,
            original_filename=filename,
        )


class UrlIngestionService:
    @staticmethod
    def _validate_ssrf_safety(url_str: str) -> urllib.parse.ParseResult:
        parsed = urllib.parse.urlparse(url_str)
        if parsed.scheme not in ("http", "https"):
            raise DomainValidationError("URL phải có giao thức http hoặc https hợp lệ")

        hostname = parsed.hostname
        if not hostname:
            raise DomainValidationError("Địa chỉ URL không chứa hostname hợp lệ")

        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            raise DomainValidationError("Truy cập địa chỉ nội bộ bị từ chối vì lý do an toàn")

        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                ip_str = item[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                if (
                    ip_obj.is_loopback
                    or ip_obj.is_private
                    or ip_obj.is_reserved
                    or ip_obj.is_link_local
                    or ip_obj.is_multicast
                ):
                    raise DomainValidationError(f"Địa chỉ mạng {ip_str} không được phép truy cập (SSRF Protection)")
        except (socket.gaierror, ValueError) as exc:
            raise DomainValidationError(f"Không thể phân giải địa chỉ tên miền {hostname}") from exc

        return parsed

    @classmethod
    async def ingest_url(cls, url_str: str) -> NormalizedJD:
        cls._validate_ssrf_safety(url_str)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
        }

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
            try:
                response = await client.get(url_str, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise DomainValidationError(f"Trang web trả về mã lỗi: {exc.response.status_code}") from exc
            except httpx.RequestError as exc:
                raise DomainValidationError(f"Không thể kết nối đến trang web: {str(exc)}") from exc

            # Verify final redirected URL for SSRF safety as well
            if str(response.url) != url_str:
                cls._validate_ssrf_safety(str(response.url))

            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "text/plain" not in content_type:
                raise DomainValidationError("Trang web không trả về định dạng HTML hoặc Text")

            raw_bytes = response.content
            if len(raw_bytes) > MAX_URL_RESPONSE_BYTES:
                raw_bytes = raw_bytes[:MAX_URL_RESPONSE_BYTES]

            html_text = response.text

        # Extract meaningful text using BeautifulSoup
        soup = BeautifulSoup(html_text, "html.parser")

        # Strip non-content tags
        for unwanted in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "svg"]):
            unwanted.decompose()

        # Extract main text
        main_content = soup.find("main") or soup.find("article") or soup.find("body")
        if main_content:
            raw_text = main_content.get_text(separator="\n", strip=True)
        else:
            raw_text = soup.get_text(separator="\n", strip=True)

        return TextNormalizer.create_normalized_jd(
            source_type=JDSourceType.url,
            raw_content=raw_text,
            original_url=url_str,
        )

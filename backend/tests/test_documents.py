from __future__ import annotations

import pytest
from app.core.errors import AppError
from app.services.documents import document_service


def _build_pdf(text: str) -> bytes:
    """Build a minimal single-page PDF with one line of text."""

    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []

    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_offset = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode()
    output += b"0000000000 65535 f \n"
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()

    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()

    return bytes(output)


async def test_pdf_documents_are_extracted() -> None:
    text = await document_service.extract_text(
        "sample.pdf",
        _build_pdf("Zorvy PDF extraction works"),
    )
    assert "Zorvy PDF extraction works" in text


async def test_malformed_pdf_is_rejected() -> None:
    with pytest.raises(AppError) as error:
        await document_service.extract_text("broken.pdf", b"not a pdf at all")

    assert error.value.code == "document_extraction_failed"
    assert error.value.status_code == 422

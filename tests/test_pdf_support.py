from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from layers import (
    layer1_ingestion,
    layer2_text_extraction,
    layer3_llm_extraction,
    layer4_structured_parsing,
    layer5_validation,
    layer6_self_healing,
    layer7_confidence_routing,
)


def _make_simple_pdf(lines: list[str]) -> bytes:
    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content_parts = ["BT", "/F1 12 Tf", "72 720 Td"]
    for index, line in enumerate(lines):
        if index:
            content_parts.append("0 -18 Td")
        content_parts.append(f"({escape(line)}) Tj")
    content_parts.append("ET")
    stream = "\n".join(content_parts).encode("utf-8")

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        b"4 0 obj << /Length " + str(len(stream)).encode("ascii") + b" >> stream\n" + stream + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]

    position = len(header)
    offsets = [0]
    for obj in objects:
        offsets.append(position)
        position += len(obj)

    xref = b"xref\n0 6\n" + b"0000000000 65535 f \n" + b"".join(
        f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets[1:]
    )
    trailer = f"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{position}\n%%EOF\n".encode("ascii")
    return header + b"".join(objects) + xref + trailer


class PdfSupportTest(unittest.TestCase):
    def test_pdf_resume_runs_through_pipeline_layers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "resume.pdf"
            pdf_path.write_bytes(
                _make_simple_pdf(
                    [
                        "John Doe",
                        "Email: john.doe@example.com",
                        "Phone: +91 9876543210",
                        "Skills: Python, SQL, Machine Learning, Pandas",
                        "Education: B.Tech in Computer Science, ABC Institute, 2023",
                        "Experience: Data Analyst Intern at XYZ Pvt Ltd, 1.5 years",
                    ]
                )
            )

            ctx = layer1_ingestion.run(str(pdf_path))
            self.assertEqual(ctx.document_type.value, "pdf")

            ctx = layer2_text_extraction.run(ctx)
            self.assertIn("John Doe", ctx.raw_text or "")

            ctx = layer3_llm_extraction.run(ctx)
            ctx = layer4_structured_parsing.run(ctx)
            ctx = layer5_validation.run(ctx)
            ctx = layer6_self_healing.run(ctx)
            ctx = layer7_confidence_routing.run(ctx)

            self.assertEqual(ctx.status.value, "PROCESSED")
            self.assertIsNotNone(ctx.validated_data)
            self.assertEqual(ctx.validated_data.name, "John Doe")
            self.assertEqual(ctx.validated_data.email, "john.doe@example.com")


if __name__ == "__main__":
    unittest.main()

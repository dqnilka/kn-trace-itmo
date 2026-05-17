from __future__ import annotations

from app.rag.md_chunker import chunk_markdown


SAMPLE = """# Глава 1. Введение

Текст введения. Параграф 1 о ценных бумагах.

Параграф 2 о фондовом рынке.

## 1.1 Облигации

Это раздел про облигации. Они бывают купонные и дисконтные.

### Купон

Купон — это процент. Он выплачивается периодически.

## 1.2 Акции

Акции дают долю в капитале. Они бывают обыкновенные и привилегированные.

# Глава 2. Производные

## 2.1 Фьючерсы

Фьючерс — это срочный контракт на поставку актива.
"""


def test_chunk_markdown_splits_by_headings() -> None:
    chunks = chunk_markdown(SAMPLE, target_tokens=200, overlap_tokens=20, min_chunk_chars=10)
    sections = [c.section for c in chunks]
    # We expect at least these sections to appear (root sections may be filtered if short)
    assert "Облигации" in " ".join(c.section for c in chunks)
    assert any("Акции" in c.section for c in chunks)
    assert any("Фьючерсы" in c.section for c in chunks)
    # Section path includes parents
    fut = next(c for c in chunks if "Фьючерс" in c.text)
    assert "Глава 2" in fut.section_path
    # Unique IDs
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_chunk_markdown_metadata_keys() -> None:
    chunks = chunk_markdown(SAMPLE, target_tokens=200, overlap_tokens=20, min_chunk_chars=10)
    md = chunks[0].to_metadata()
    assert md["node_type"] == "MdChunk"
    assert "section" in md and "section_path" in md
    assert "char_offset" in md

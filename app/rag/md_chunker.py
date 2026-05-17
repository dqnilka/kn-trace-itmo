"""Re-chunk theory_economics.md into RAG-friendly chunks.

Strategy:
  1. Split by H2/H3 headings (## / ###) preserving the heading line as `section`.
  2. If a section is too large, split into ~target_chars windows with overlap,
     respecting paragraph boundaries when possible.

We use a char-based proxy for tokens (1 token ≈ 4 chars for Russian) to avoid
extra dependencies (no tiktoken).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_TOKEN_PER_CHAR = 0.25  # rough heuristic for Russian text


@dataclass
class MdChunk:
    chunk_id: str
    section: str
    section_path: str  # "H1 > H2 > H3"
    text: str
    char_offset: int
    char_length: int

    def to_metadata(self) -> dict:
        return {
            "node_id": self.chunk_id,
            "node_type": "MdChunk",
            "section": self.section,
            "section_path": self.section_path,
            "char_offset": self.char_offset,
            "char_length": self.char_length,
        }


def _tokens_to_chars(toks: int) -> int:
    return int(toks / _TOKEN_PER_CHAR)


def _split_text_with_overlap(text: str, target_chars: int, overlap_chars: int) -> list[tuple[int, str]]:
    """Split into windows by paragraph boundaries; return [(start_offset, chunk_text), ...]."""
    if len(text) <= target_chars:
        return [(0, text)]

    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p for p in paragraphs if p.strip()]

    chunks: list[tuple[int, str]] = []
    current: list[str] = []
    current_len = 0
    cursor = 0  # char offset in the *input* text
    para_offsets: list[int] = []
    # rebuild offsets
    pos = 0
    for p in paragraphs:
        idx = text.find(p, pos)
        if idx < 0:
            idx = pos
        para_offsets.append(idx)
        pos = idx + len(p)

    chunk_start = para_offsets[0] if para_offsets else 0
    for p, p_off in zip(paragraphs, para_offsets):
        if current and current_len + len(p) > target_chars:
            chunk_text = "\n\n".join(current)
            chunks.append((chunk_start, chunk_text))
            # overlap: keep tail of size ~overlap_chars
            tail_chars = 0
            tail: list[str] = []
            for tp in reversed(current):
                tail.insert(0, tp)
                tail_chars += len(tp)
                if tail_chars >= overlap_chars:
                    break
            current = list(tail)
            current_len = sum(len(x) for x in current)
            # Set chunk_start to the offset of first paragraph in the overlap, or current p_off
            # Approximate: use p_off minus tail_chars (clamped).
            chunk_start = max(0, p_off - tail_chars)

        current.append(p)
        current_len += len(p)
        cursor = p_off + len(p)

    if current:
        chunk_text = "\n\n".join(current)
        chunks.append((chunk_start, chunk_text))

    return chunks


def chunk_markdown(
    md_text: str,
    target_tokens: int = 800,
    overlap_tokens: int = 100,
    min_chunk_chars: int = 200,
) -> list[MdChunk]:
    """Chunk by H2/H3 headings, then split oversize sections.

    We track an "section_path" string like "H1 > H2 > H3" for every chunk so
    that retrieval results can be cited with a human-readable location.
    """
    target_chars = _tokens_to_chars(target_tokens)
    overlap_chars = _tokens_to_chars(overlap_tokens)

    # Walk through the text; keep current heading stack.
    lines = md_text.splitlines(keepends=True)
    heading_stack: list[tuple[int, str]] = []  # (level, title)
    sections: list[tuple[list[tuple[int, str]], int, str]] = []  # (heading_stack_snapshot, start_offset, body)
    current_body_lines: list[str] = []
    current_start = 0

    pos = 0
    for line in lines:
        m = _HEADING_RE.match(line.rstrip("\n"))
        if m:
            # flush previous section
            if current_body_lines:
                body = "".join(current_body_lines)
                sections.append((heading_stack.copy(), current_start, body))
            level = len(m.group(1))
            title = m.group(2).strip()
            # Pop deeper or equal levels
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            current_body_lines = []
            current_start = pos + len(line)
        else:
            current_body_lines.append(line)
        pos += len(line)

    if current_body_lines:
        body = "".join(current_body_lines)
        sections.append((heading_stack.copy(), current_start, body))

    chunks: list[MdChunk] = []
    chunk_idx = 0
    for stack, sec_start, body in sections:
        body_stripped = body.strip()
        if len(body_stripped) < min_chunk_chars:
            continue
        section_path = " > ".join(t for _, t in stack) if stack else "(root)"
        section = stack[-1][1] if stack else "(root)"
        if len(body_stripped) <= target_chars:
            chunks.append(
                MdChunk(
                    chunk_id=f"md:{chunk_idx:05d}",
                    section=section,
                    section_path=section_path,
                    text=body_stripped,
                    char_offset=sec_start,
                    char_length=len(body_stripped),
                )
            )
            chunk_idx += 1
        else:
            for off, sub in _split_text_with_overlap(body, target_chars, overlap_chars):
                sub_stripped = sub.strip()
                if len(sub_stripped) < min_chunk_chars:
                    continue
                chunks.append(
                    MdChunk(
                        chunk_id=f"md:{chunk_idx:05d}",
                        section=section,
                        section_path=section_path,
                        text=sub_stripped,
                        char_offset=sec_start + off,
                        char_length=len(sub_stripped),
                    )
                )
                chunk_idx += 1
    return chunks

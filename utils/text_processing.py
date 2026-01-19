import re
from typing import List, Dict, Any, Tuple, Optional
from uuid import uuid4


def detect_citation_style(text: str) -> str:
    """Automatically detect the citation style used in the text."""

    # Count different citation patterns
    patterns = {
        "numbered_bracket": len(re.findall(r"\[\d+\]", text)),
        "numbered_paren": len(re.findall(r"\(\d+\)", text)),
        "numbered_dot": len(re.findall(r"\b\d+\.\s", text)),  # "1. ", "2. "
        "superscript": len(re.findall(r"\^\d+", text)),
        "author_year": len(
            re.findall(r"\([A-Za-z]+(?:\s+et\s+al\.?)?\s*,?\s*\d{4}\)", text)
        ),
        "author_year_bracket": len(
            re.findall(r"\[[A-Za-z]+(?:\s+et\s+al\.?)?\s*,?\s*\d{4}\]", text)
        ),
        "plain_author": len(
            re.findall(r"\b[A-Z][a-z]+\s+et\s+al\.?\s+\(\d{4}\)", text)
        ),
    }

    # Return the style with highest count
    if max(patterns.values()) == 0:
        return "none"

    return max(patterns, key=patterns.get)


def detect_reference_format(references_text: str) -> str:
    """Automatically detect reference format in the reference section."""

    # Check for different reference formats
    if re.search(r"\[\d+\]\s*[A-Z]", references_text):
        return "ieee"
    elif re.search(r"^\d+\.\s*[A-Z]", references_text, re.MULTILINE):
        return "numbered"
    elif re.search(r"[A-Za-z]+\s*\(\d{4}\)", references_text):
        return "apa"
    elif re.search(r"^[A-Z][a-z]+,?\s+[A-Z]", references_text, re.MULTILINE):
        return "plain_text"  # Author, Title format without numbers
    else:
        return "plain_text"  # default fallback for unnumbered references


def parse_references_from_text(
    references_text: str, format_type: str = None
) -> Dict[str, Dict]:
    """Parse references from raw text string with automatic format detection."""

    if format_type is None:
        format_type = detect_reference_format(references_text)

    references = {}

    if format_type == "ieee":
        # Pattern for IEEE format: [1] Authors, "Title", Journal, Year
        pattern = r"\[(\d+)\]\s*(.+?)(?=\[\d+\]|\Z)"
        matches = re.findall(pattern, references_text, re.DOTALL)

        for ref_num, ref_text in matches:
            ref_text = ref_text.strip().replace("\n", " ")
            references[ref_num] = parse_single_reference(ref_text)

    elif format_type == "numbered":
        # Pattern for numbered format: 1. Reference text
        pattern = r"^(\d+)\.\s*(.+?)(?=^\d+\.\s|\Z)"
        matches = re.findall(pattern, references_text, re.MULTILINE | re.DOTALL)

        for ref_num, ref_text in matches:
            ref_text = ref_text.strip().replace("\n", " ")
            references[ref_num] = parse_single_reference(ref_text)

    elif format_type == "apa":
        # Basic APA parsing - split by double newlines or clear author patterns
        lines = references_text.strip().split("\n\n")
        if len(lines) == 1:
            # If no double newlines, try to split by author patterns
            lines = re.split(r"\n(?=[A-Z][a-z]+,?\s)", references_text)

        ref_count = 1
        for line in lines:
            line = line.strip()
            if line:
                parsed_ref = parse_single_reference(line)
                # For APA, use author-year as key if available
                if parsed_ref["authors"] and parsed_ref["year"]:
                    key = f"{parsed_ref['authors'].split(',')[0].strip()}, {parsed_ref['year']}"
                else:
                    key = str(ref_count)
                references[key] = parsed_ref
                ref_count += 1

    elif format_type == "plain_text":
        # Handle unnumbered references - split by blank lines or author patterns
        lines = references_text.strip().split("\n\n")
        if len(lines) == 1:
            # Try splitting by author patterns or double spaces
            lines = re.split(r"\n(?=[A-Z][a-z]+[,\s])|(?:\n\s*\n)", references_text)

        ref_count = 1
        for line in lines:
            line = line.strip()
            if line and len(line) > 10:  # Skip very short lines
                parsed_ref = parse_single_reference(line)
                # Create key from author and year if available
                if parsed_ref["authors"] and parsed_ref["year"]:
                    # Extract first author's last name
                    first_author = parsed_ref["authors"].split(",")[0].strip()
                    key = f"{first_author}, {parsed_ref['year']}"
                else:
                    # Use first few words as key
                    words = line.split()[:3]
                    key = " ".join(words)

                references[key] = parsed_ref
                ref_count += 1

    return references


def parse_single_reference(ref_text: str) -> Dict[str, str]:
    """Parse a single reference text into components."""

    # Extract title (usually in quotes)
    title_match = re.search(r'"([^"]+)"', ref_text)
    title = title_match.group(1) if title_match else ""

    # Extract year
    year_match = re.search(r"\b(19|20)\d{2}\b", ref_text)
    year = year_match.group() if year_match else ""

    # Extract authors (heuristic approach)
    if title:
        # Authors usually come before the title
        author_text = ref_text.split('"')[0].strip().rstrip(",")
    else:
        # Take first part before comma or period
        parts = re.split(r"[,.]", ref_text)
        author_text = parts[0] if parts else ref_text

    # Clean up authors
    author_text = re.sub(r"^[^\w]*", "", author_text)  # Remove leading non-word chars

    return {"title": title, "authors": author_text, "year": year, "raw_text": ref_text}


def extract_citations_from_chunk(
    chunk_text: str, citation_style: str = None
) -> List[str]:
    """Extract citation identifiers with automatic style detection."""

    if citation_style is None:
        citation_style = detect_citation_style(chunk_text)

    citation_patterns = {
        "numbered_bracket": r"\[(\d+(?:[,\s\-]*\d+)*)\]",  # [1], [1,2], [1-3]
        "numbered_paren": r"\((\d+(?:[,\s\-]*\d+)*)\)",  # (1), (1,2)
        "numbered_dot": r"(?<!\w)(\d+)(?=\.\s)",  # "1. " but not "Fig. 1."
        "superscript": r"\^(\d+(?:[,\s]*\d+)*)",  # ^1, ^1,2
        "author_year": r"\(([A-Za-z]+(?:\s+et\s+al\.?)?\s*,?\s*\d{4}[a-z]?)\)",  # (Smith, 2023)
        "author_year_bracket": r"\[([A-Za-z]+(?:\s+et\s+al\.?)?\s*,?\s*\d{4}[a-z]?)\]",  # [Smith, 2023]
        "plain_author": r"\b([A-Z][a-z]+(?:\s+et\s+al\.?)?)\s+\((\d{4})\)",  # Smith et al. (2023)
        "none": [],
    }

    if citation_style not in citation_patterns:
        return []

    pattern = citation_patterns[citation_style]
    if not pattern:
        return []

    matches = re.findall(pattern, chunk_text)

    citations = []
    for match in matches:
        if citation_style in ["numbered_bracket", "numbered_paren", "superscript"]:
            # Handle various separators: "1,2,3", "1-3", "1 2 3"
            numbers = re.findall(r"\d+", match)
            citations.extend(numbers)
        elif citation_style == "numbered_dot":
            citations.append(match)
        elif citation_style in ["author_year", "author_year_bracket"]:
            citations.append(match.strip())
        elif citation_style == "plain_author":
            # This returns tuple (author, year), combine them
            if isinstance(match, tuple):
                citations.append(f"{match[0]}, {match[1]}")
            else:
                citations.append(match.strip())

    return list(set(citations))  # Remove duplicates


def get_chunk_references(
    chunk_text: str, all_references: Dict[str, Dict], citation_style: str = None
) -> List[Dict]:
    """Get only the references that are cited in this specific chunk."""

    # Extract citations from the chunk
    citations = extract_citations_from_chunk(chunk_text, citation_style)

    # Match citations to references
    chunk_references = []
    for citation in citations:
        # Direct match first
        if citation in all_references:
            ref_data = all_references[citation]
            # Validate that the reference has meaningful content
            title = ref_data.get("title", "").strip()
            authors = ref_data.get("authors", "").strip()
            raw_text = ref_data.get("raw_text", "").strip()

            # Only include if it has substantial content
            if title or authors or (raw_text and len(raw_text) > 10):
                chunk_references.append(
                    {
                        "citation_id": citation,
                        "title": title,
                        "authors": authors,
                        "year": ref_data.get("year", "").strip(),
                        "raw_reference": raw_text,
                    }
                )
        else:
            # Try fuzzy matching for author-year citations
            fuzzy_match = find_fuzzy_reference(citation, all_references)
            if fuzzy_match:
                # Validate fuzzy match has content too
                title = fuzzy_match.get("title", "").strip()
                authors = fuzzy_match.get("authors", "").strip()
                raw_reference = fuzzy_match.get("raw_reference", "").strip()

                if title or authors or (raw_reference and len(raw_reference) > 10):
                    chunk_references.append(fuzzy_match)

    return chunk_references


def find_fuzzy_reference(
    citation: str, all_references: Dict[str, Dict]
) -> Optional[Dict]:
    """Find reference through fuzzy matching for author-year citations."""

    # Extract author and year from citation
    author_year_match = re.search(r"([A-Za-z]+).*?(\d{4})", citation)
    if not author_year_match:
        return None

    cite_author = author_year_match.group(1).lower()
    cite_year = author_year_match.group(2)

    # Search references for matching author and year
    for ref_key, ref_data in all_references.items():
        # Check if year matches
        if cite_year in str(ref_data.get("year", "")):
            # Check if author matches
            ref_authors = ref_data.get("authors", "").lower()
            if cite_author in ref_authors:
                return {
                    "citation_id": citation,
                    "title": ref_data["title"],
                    "authors": ref_data["authors"],
                    "year": ref_data["year"],
                    "raw_reference": ref_data["raw_text"],
                    "match_type": "fuzzy",
                }

    return None


def process_document(
    chunks: List[str], references_text: str, document_id: str = None
) -> Dict[str, Any]:
    """Process a single document with automatic style detection."""

    # Detect styles automatically
    citation_style = detect_citation_style(" ".join(chunks))
    reference_format = detect_reference_format(references_text)

    # Parse references
    all_references = parse_references_from_text(references_text, reference_format)

    processed_chunks = []

    for i, chunk_text in enumerate(chunks):
        chunk_id = f"{document_id}_chunk_{i + 1}" if document_id else f"chunk_{i + 1}"

        # Get references for this chunk
        chunk_references = get_chunk_references(
            chunk_text, all_references, citation_style
        )

        # Prepare metadata
        metadata = {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "citation_style": citation_style,
            "reference_format": reference_format,
            "citation_count": len(chunk_references),
            "cited_references": chunk_references,
            "has_citations": len(chunk_references) > 0,
        }

        processed_chunks.append(
            {"text": chunk_text, "metadata": metadata, "id": chunk_id}
        )

    return {
        "processed_chunks": processed_chunks,
        "citation_style": citation_style,
        "reference_format": reference_format,
        "total_references": len(all_references),
        "chunks_with_citations": len(
            [c for c in processed_chunks if c["metadata"]["has_citations"]]
        ),
    }


def process_multiple_documents(documents: List[Dict[str, Any]]) -> List[Dict]:
    """Process multiple documents with different citation styles."""

    all_processed_chunks = []

    for doc in documents:
        doc_id = doc.get("id", f"doc_{len(all_processed_chunks)}")
        chunks = doc["chunks"]
        references_text = doc["references"]

        print(f"Processing document: {doc_id}")

        # Process this document
        result = process_document(chunks, references_text, doc_id)
        print("Result done")

        print(f"  - Citation style: {result['citation_style']}")
        print(f"  - Reference format: {result['reference_format']}")
        print(f"  - Total references: {result['total_references']}")
        print(
            f"  - Chunks with citations: {result['chunks_with_citations']}/{len(chunks)}"
        )

        all_processed_chunks.extend(result["processed_chunks"])
    return all_processed_chunks


# Example usage
def get_references(doc_chunks, references):
    uuids = [str(uuid4()) for _ in range(len(doc_chunks))]
    documents = [
        {"id": id_, "chunks": chunks, "references": refs}
        for id_, chunks, refs in zip(uuids, doc_chunks, references)
    ]

    # Process all documents
    all_chunks = process_multiple_documents(documents)

    print(f"\n=== FINAL RESULTS ===")
    print(f"Total processed chunks: {len(all_chunks)}")

    # Show some examples
    for chunk in all_chunks[:3]:  # Show first 3
        print(f"\n--- {chunk['id']} ---")
        print(f"Text: {chunk['text'][:60]}...")
        print(f"Style: {chunk['metadata']['citation_style']}")
        print(f"Citations: {chunk['metadata']['citation_count']}")
        if chunk["metadata"]["cited_references"]:
            for ref in chunk["metadata"]["cited_references"]:
                print(f"  [{ref['citation_id']}] {ref['title'] or ref['authors']}")

    return all_chunks

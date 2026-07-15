from app.pipeline.preprocess import DocumentExtractResult, DocumentTextBlock
from app.pipeline.structured_extract import build_structured_document
from app.schemas.cv import CvSections


def test_coverage_retains_ai_omissions_as_unclassified() -> None:
    document = DocumentExtractResult(
        normalized_text="Experience\nBuilt an AI project\nVolunteer club coordinator",
        engine="test",
        blocks=[
            DocumentTextBlock("b1", "Experience", page=1),
            DocumentTextBlock("b2", "Built an AI project", page=1),
            DocumentTextBlock("b3", "Volunteer club coordinator", page=1),
        ],
    )
    sections = CvSections(experience=["Built an AI project"])

    structured, coverage = build_structured_document(sections, document)

    assert coverage.source_block_count == 3
    assert coverage.classified_block_count == 1
    assert coverage.ignored_heading_count == 1
    assert coverage.unclassified_block_count == 1
    assert coverage.coverage_score == 1.0
    assert coverage.unclassified_block_ids == ["b3"]
    assert structured.unclassified[0].text == "Volunteer club coordinator"


def test_structured_records_preserve_raw_text_and_date() -> None:
    raw = "05/2025 - 07/2025 | Team Member | Face Recognition System | Built the GUI"
    document = DocumentExtractResult(
        normalized_text=raw,
        engine="test",
        blocks=[DocumentTextBlock("b1", raw, page=1)],
    )
    sections = CvSections(experience=[raw])

    structured, _coverage = build_structured_document(sections, document)

    record = structured.experience[0]
    assert record.raw_text == raw
    assert record.date == "05/2025 - 07/2025"
    assert record.title == "Team Member"
    assert record.details == ["Face Recognition System", "Built the GUI"]
    assert record.source_block_ids == ["b1"]


def test_personal_info_extracts_name_title_contact_and_links() -> None:
    document = DocumentExtractResult(
        normalized_text="Nguyễn Hoàng Duy\nIntern\nMale\n[EMAIL]\nwww.linkedin.com/in/nguyen-duy",
        engine="test",
        blocks=[],
    )
    sections = CvSections(
        other=[
            "Nguyễn Hoàng Duy",
            "Intern",
            "Male",
            "(+84) [PHONE]",
            "[EMAIL]",
            "Cai Rang Ward, Can Tho City",
            "www.linkedin.com/in/nguyen-duy",
        ],
    )

    structured, _coverage = build_structured_document(sections, document)

    assert structured.personal_info["name"] == ["Nguyễn Hoàng Duy"]
    assert structured.personal_info["title"] == ["Intern"]
    assert structured.personal_info["contact"] == ["(+84) [PHONE]", "[EMAIL]"]
    assert structured.personal_info["links"] == ["www.linkedin.com/in/nguyen-duy"]
    assert "Male" in structured.personal_info["other"]

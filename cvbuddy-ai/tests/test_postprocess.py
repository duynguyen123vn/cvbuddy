from app.pipeline.postprocess import parse_analyze_response
from app.schemas.cv import AnalyzeCvRequest, CompanyModel, CvSections, LanguageMode


def _base_raw_response() -> dict:
    return {
        "overall_score": 60,
        "dimensions": {
            "layout_ats": {"score": 70, "issues": [], "fixes": []},
            "language": {"score": 80, "issues": [], "fixes": []},
            "keywords": {
                "score": 50,
                "missing": [],
                "suggested_bullets": [
                    "Developed and deployed AI models using Python and OpenCV"
                ],
            },
            "jd_fit": {"score": 40, "gaps": []},
        },
        "rewrites": [],
        "company_model_feedback": "Generic feedback",
        "confidence": 0.7,
    }


def test_missing_jd_fit_is_neutralized() -> None:
    request = AnalyzeCvRequest(
        sections=CvSections(experience=["Developed an AI project using Python and OpenCV"]),
        industry_slug="marketing",
        company_model=CompanyModel.CORPORATE,
    )

    parsed = parse_analyze_response(_base_raw_response(), request)

    assert parsed.dimensions.jd_fit.score == 60
    assert "Chưa có mô tả công việc" in parsed.dimensions.jd_fit.gaps[0]


def test_missing_jd_fit_uses_english_for_english_response() -> None:
    request = AnalyzeCvRequest(
        sections=CvSections(experience=["Developed an AI project"]),
        industry_slug="computer_science",
        language=LanguageMode.EN,
    )

    parsed = parse_analyze_response(_base_raw_response(), request)

    assert "No job description was provided" in parsed.dimensions.jd_fit.gaps[0]


def test_generic_feedback_is_removed() -> None:
    raw = _base_raw_response()
    raw["dimensions"]["language"] = {
        "score": 70,
        "issues": ["Thiếu tính cụ thể", "Câu 'Built project' chưa nêu rõ vai trò"],
        "fixes": ["Sử dụng từ ngữ chuyên nghiệp", "Đổi thành 'Developed the image classifier'"],
    }
    request = AnalyzeCvRequest(
        sections=CvSections(experience=["Built project"]),
        industry_slug="computer_science",
        language=LanguageMode.VI,
    )

    parsed = parse_analyze_response(raw, request)

    assert parsed.dimensions.language.issues == ["Câu 'Built project' chưa nêu rõ vai trò"]
    assert parsed.dimensions.language.fixes == ["Đổi thành 'Developed the image classifier'"]


def test_generic_date_issue_is_kept_only_with_evidence() -> None:
    raw = _base_raw_response()
    raw["dimensions"]["layout_ats"] = {
        "score": 70,
        "issues": [
            "Ngày tháng không thống nhất",
            "Ngày tháng không thống nhất: '05/2025' và 'September 2025'",
        ],
        "fixes": [],
    }
    request = AnalyzeCvRequest(
        sections=CvSections(experience=["05/2025", "September 2025"]),
        industry_slug="computer_science",
        language=LanguageMode.VI,
    )

    parsed = parse_analyze_response(raw, request)

    assert parsed.dimensions.layout_ats.issues == [
        "Ngày tháng không thống nhất: '05/2025' và 'September 2025'"
    ]


def test_keywords_already_in_cv_are_not_reported_missing() -> None:
    raw = _base_raw_response()
    raw["dimensions"]["keywords"]["missing"] = [
        "Machine Learning",
        "Data Engineering",
    ]
    request = AnalyzeCvRequest(
        sections=CvSections(skills=["Python, Machine Learning"]),
        industry_slug="computer_science",
        language=LanguageMode.EN,
    )

    parsed = parse_analyze_response(raw, request)

    assert parsed.dimensions.keywords.missing == ["Data Engineering"]


def test_identical_english_rewrite_is_removed_in_bilingual_mode() -> None:
    original = "Developed an attendance system using Python and OpenCV."
    raw = _base_raw_response()
    raw["rewrites"] = [
        {
            "section": "experience",
            "original_ref": original,
            "suggested_vi": "Phát triển hệ thống điểm danh bằng Python và OpenCV.",
            "suggested_en": original,
            "change_reason": "Translated into Vietnamese",
            "needs_user_fact": False,
        }
    ]
    request = AnalyzeCvRequest(
        sections=CvSections(experience=[original]),
        industry_slug="computer_science",
        language=LanguageMode.BOTH,
    )

    parsed = parse_analyze_response(raw, request)

    assert parsed.rewrites == []


def test_identical_short_vietnamese_rewrite_is_removed_in_bilingual_mode() -> None:
    original = "Sinh viên AI"
    raw = _base_raw_response()
    raw["rewrites"] = [
        {
            "section": "summary",
            "original_ref": original,
            "suggested_vi": original,
            "suggested_en": "AI student",
            "change_reason": "Provides an English translation.",
            "needs_user_fact": False,
        }
    ]
    request = AnalyzeCvRequest(
        sections=CvSections(summary=[original, "AI student"]),
        industry_slug="computer_science",
        language=LanguageMode.BOTH,
    )

    parsed = parse_analyze_response(raw, request)

    assert parsed.rewrites == []


def test_vietnamese_mode_drops_translation_of_english_source() -> None:
    original = "Developed a face recognition attendance system."
    raw = _base_raw_response()
    raw["rewrites"] = [
        {
            "section": "projects",
            "original_ref": original,
            "suggested_vi": "Phát triển hệ thống điểm danh nhận diện khuôn mặt.",
            "suggested_en": None,
            "change_reason": "Dịch nội dung sang tiếng Việt.",
            "needs_user_fact": False,
        }
    ]
    request = AnalyzeCvRequest(
        sections=CvSections(projects=[original]),
        industry_slug="computer_science",
        language=LanguageMode.VI,
    )

    parsed = parse_analyze_response(raw, request)

    assert parsed.rewrites == []


def test_english_mode_drops_translation_of_vietnamese_source() -> None:
    original = "Phát triển hệ thống điểm danh nhận diện khuôn mặt."
    raw = _base_raw_response()
    raw["rewrites"] = [
        {
            "section": "projects",
            "original_ref": original,
            "suggested_vi": None,
            "suggested_en": "Developed a face recognition attendance system.",
            "change_reason": "Translated the statement into English.",
            "needs_user_fact": False,
        }
    ]
    request = AnalyzeCvRequest(
        sections=CvSections(projects=[original]),
        industry_slug="computer_science",
        language=LanguageMode.EN,
    )

    parsed = parse_analyze_response(raw, request)

    assert parsed.rewrites == []


def test_material_vietnamese_rewrite_keeps_both_language_equivalents() -> None:
    original = "Tham gia dự án điểm danh."
    raw = _base_raw_response()
    raw["rewrites"] = [
        {
            "section": "projects",
            "original_ref": original,
            "suggested_vi": "Xây dựng chức năng nhận diện khuôn mặt cho hệ thống điểm danh bằng Python và OpenCV.",
            "suggested_en": "Built the face-recognition feature for an attendance system using Python and OpenCV.",
            "change_reason": "Thay mô tả vai trò mơ hồ bằng đóng góp và công nghệ đã có trong CV.",
            "needs_user_fact": False,
        }
    ]
    request = AnalyzeCvRequest(
        sections=CvSections(
            projects=[original, "Sử dụng Python và OpenCV để nhận diện khuôn mặt."]
        ),
        industry_slug="computer_science",
        language=LanguageMode.BOTH,
    )

    parsed = parse_analyze_response(raw, request)

    assert len(parsed.rewrites) == 1
    assert parsed.rewrites[0].suggested_vi
    assert parsed.rewrites[0].suggested_en


def test_near_identical_rewrite_is_removed() -> None:
    original = "Trained and evaluated the model on a food image segmentation dataset."
    raw = _base_raw_response()
    raw["rewrites"] = [
        {
            "section": "experience",
            "original_ref": original,
            "suggested_en": "Trained and evaluated the model on the food image segmentation dataset.",
            "suggested_vi": "Huấn luyện và đánh giá mô hình trên tập dữ liệu phân đoạn ảnh thực phẩm.",
            "needs_user_fact": False,
        }
    ]
    request = AnalyzeCvRequest(
        sections=CvSections(experience=[original]),
        industry_slug="computer_science",
        language=LanguageMode.BOTH,
    )

    parsed = parse_analyze_response(raw, request)

    assert parsed.rewrites == []


def test_material_rewrite_is_kept() -> None:
    original = "Responsible for the attendance project."
    raw = _base_raw_response()
    raw["rewrites"] = [
        {
            "section": "experience",
            "original_ref": original,
            "suggested_en": "Built a face-recognition attendance prototype using Python and OpenCV.",
            "suggested_vi": "Xây dựng nguyên mẫu điểm danh nhận diện khuôn mặt bằng Python và OpenCV.",
            "change_reason": "Replaces a vague responsibility with the concrete contribution and tools.",
            "needs_user_fact": False,
        }
    ]
    request = AnalyzeCvRequest(
        sections=CvSections(
            experience=[original, "Used Python and OpenCV for face recognition."]
        ),
        industry_slug="computer_science",
        language=LanguageMode.BOTH,
    )

    parsed = parse_analyze_response(raw, request)

    assert len(parsed.rewrites) == 1
    assert parsed.rewrites[0].change_reason


def test_suggested_bullets_sanitize_unsupported_strong_claims() -> None:
    request = AnalyzeCvRequest(
        sections=CvSections(experience=["Developed an AI project using Python and OpenCV"]),
        industry_slug="marketing",
        company_model=CompanyModel.CORPORATE,
        language=LanguageMode.EN,
    )

    parsed = parse_analyze_response(_base_raw_response(), request)

    assert "deployed" not in parsed.dimensions.keywords.suggested_bullets[0].lower()
    assert "developed" in parsed.dimensions.keywords.suggested_bullets[0].lower()


def test_rewrites_keep_only_requested_english_language() -> None:
    raw = _base_raw_response()
    raw["rewrites"] = [
        {
            "section": "summary",
            "original_ref": "AI student",
            "suggested_vi": "Sinh viên AI",
            "suggested_en": "AI student seeking an internship",
            "needs_user_fact": False,
        }
    ]
    request = AnalyzeCvRequest(
        sections=CvSections(summary=["AI student"]),
        industry_slug="computer_science",
        language=LanguageMode.EN,
    )

    parsed = parse_analyze_response(raw, request)

    assert parsed.rewrites[0].suggested_vi is None
    assert parsed.rewrites[0].suggested_en == "AI student seeking an internship"


def test_rewrites_keep_only_requested_vietnamese_language() -> None:
    raw = _base_raw_response()
    raw["rewrites"] = [
        {
            "section": "summary",
            "original_ref": "Sinh viên AI",
            "suggested_vi": "Sinh viên AI đang tìm vị trí thực tập",
            "suggested_en": "AI student",
            "needs_user_fact": False,
        }
    ]
    request = AnalyzeCvRequest(
        sections=CvSections(summary=["Sinh viên AI"]),
        industry_slug="computer_science",
        language=LanguageMode.VI,
    )

    parsed = parse_analyze_response(raw, request)

    assert parsed.rewrites[0].suggested_vi == "Sinh viên AI đang tìm vị trí thực tập"
    assert parsed.rewrites[0].suggested_en is None
    assert parsed.disclaimer.startswith("Phản hồi có sự hỗ trợ của AI")


def test_vietnamese_response_removes_english_detailed_feedback() -> None:
    raw = _base_raw_response()
    raw["dimensions"]["layout_ats"] = {
        "score": 60,
        "issues": [
            "Duplicate content exists between experience and projects sections.",
            "Nội dung 'Kinh nghiệm' và 'Dự án' đang bị lặp.",
        ],
        "fixes": [
            "Merge experience and projects into a single section.",
            "Gộp hai mục bị lặp và giữ mỗi dự án một lần.",
        ],
    }
    raw["dimensions"]["keywords"]["missing"] = ["data preprocessing"]
    raw["dimensions"]["keywords"]["suggested_bullets"] = [
        "Implemented data preprocessing pipelines for the dataset.",
        "Xây dựng quy trình tiền xử lý dữ liệu cho tập dữ liệu.",
    ]
    raw["company_model_feedback"] = "CV cần tập trung vào các kỹ năng kỹ thuật cụ thể."
    request = AnalyzeCvRequest(
        sections=CvSections(projects=["Xây dựng mô hình AI."]),
        industry_slug="computer_science",
        language=LanguageMode.VI,
    )

    parsed = parse_analyze_response(raw, request)

    assert parsed.dimensions.layout_ats.issues == [
        "Nội dung 'Kinh nghiệm' và 'Dự án' đang bị lặp."
    ]
    assert parsed.dimensions.layout_ats.fixes == [
        "Gộp hai mục bị lặp và giữ mỗi dự án một lần."
    ]
    assert parsed.dimensions.keywords.missing == ["data preprocessing"]
    assert parsed.dimensions.keywords.suggested_bullets == [
        "Xây dựng quy trình tiền xử lý dữ liệu cho tập dữ liệu."
    ]

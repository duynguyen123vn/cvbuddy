const API_URL = (window.CVBUDDY_CONFIG?.apiBaseUrl || "http://localhost:8000").replace(/\/$/, "");
const EXTRACTION_CACHE_VERSION = "language-pages-v2";

const elements = {
  form: document.querySelector("#analysis-form"),
  file: document.querySelector("#cv-file"),
  fileDrop: document.querySelector("#file-drop"),
  fileTitle: document.querySelector("#file-drop-title"),
  fileMeta: document.querySelector("#file-drop-meta"),
  industry: document.querySelector("#industry"),
  vertical: document.querySelector("#vertical"),
  extractModel: document.querySelector("#extract-model"),
  analyzeModel: document.querySelector("#analyze-model"),
  submit: document.querySelector("#submit-button"),
  submitLabel: document.querySelector("#submit-label"),
  apiStatus: document.querySelector("#api-status"),
  apiStatusText: document.querySelector("#api-status-text"),
  empty: document.querySelector("#empty-state"),
  loading: document.querySelector("#loading-state"),
  error: document.querySelector("#error-state"),
  errorMessage: document.querySelector("#error-message"),
  retry: document.querySelector("#retry-button"),
  results: document.querySelector("#analysis-results"),
};

let industries = [];
let models = [];
let selectedFile = null;
let extractionCache = null;

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, options);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    let detail = Array.isArray(payload.detail)
      ? payload.detail.map((item) => item.msg).join("; ")
      : payload.detail;
    if (detail && typeof detail === "object") {
      detail = detail.message || JSON.stringify(detail);
    }
    const retryAfter = Number(response.headers.get("Retry-After") || 0);
    if (response.status === 429) {
      detail = retryAfter
        ? `Đã chạm giới hạn Groq Free. Thử lại sau ${retryAfter} giây.`
        : "Đã chạm giới hạn Groq Free. Vui lòng thử lại sau ít phút.";
    }
    const error = new Error(detail || `Yêu cầu thất bại (${response.status})`);
    error.status = response.status;
    error.retryAfter = retryAfter;
    throw error;
  }

  return payload;
}

async function initialize() {
  try {
    const [health, catalog, modelCatalog] = await Promise.all([
      requestJson("/health"),
      requestJson("/v1/industries"),
      requestJson("/v1/models"),
    ]);

    industries = catalog.industries || [];
    models = modelCatalog.models || [];
    renderIndustries();
    renderModels(
      modelCatalog.default_extract_model || modelCatalog.default_model,
      modelCatalog.default_analyze_model || modelCatalog.default_model,
    );
    const modelServerReady = modelCatalog.server_available !== false;
    setApiStatus(
      health.status === "ok" && modelServerReady,
      modelServerReady ? "API đã kết nối" : "Ollama chưa chạy",
    );
  } catch (error) {
    setApiStatus(false, "API ngoại tuyến");
    elements.industry.innerHTML = '<option value="">Không tải được danh sách</option>';
    showError(`${error.message}. Hãy kiểm tra backend tại ${API_URL}.`);
  }
}

function renderModels(defaultExtractModel, defaultAnalyzeModel) {
  const availableModels = models.filter((model) => model.installed !== false);
  const options = availableModels.length
    ? availableModels
    .map(
      (model) =>
        `<option value="${escapeHtml(model.id)}">${escapeHtml(model.display_name)}</option>`,
      )
      .join("")
    : '<option value="">Chưa có model local đã cài</option>';
  for (const element of [elements.extractModel, elements.analyzeModel]) {
    element.innerHTML = options;
    element.disabled = availableModels.length === 0;
  }
  elements.extractModel.value = availableModels.some(
    (model) => model.id === defaultExtractModel,
  )
    ? defaultExtractModel
    : availableModels[0]?.id || "";
  elements.analyzeModel.value = availableModels.some(
    (model) => model.id === defaultAnalyzeModel,
  )
    ? defaultAnalyzeModel
    : availableModels[0]?.id || "";
  validateForm();
}

function setApiStatus(isOnline, text) {
  elements.apiStatus.classList.toggle("is-online", isOnline);
  elements.apiStatus.classList.toggle("is-offline", !isOnline);
  elements.apiStatusText.textContent = text;
}

function renderIndustries() {
  elements.industry.innerHTML = [
    '<option value="">Chọn nhóm ngành</option>',
    ...industries.map(
      (industry) =>
        `<option value="${escapeHtml(industry.slug)}">${escapeHtml(industry.display_name)}</option>`,
    ),
  ].join("");
  elements.industry.disabled = false;
  validateForm();
}

function renderVerticals(industrySlug) {
  const industry = industries.find((item) => item.slug === industrySlug);
  const verticals = industry?.verticals || [];

  elements.vertical.innerHTML = [
    '<option value="">Chọn chuyên ngành</option>',
    ...verticals.map(
      (vertical) =>
        `<option value="${escapeHtml(vertical.slug)}">${escapeHtml(vertical.display_name)}</option>`,
    ),
  ].join("");
  elements.vertical.disabled = verticals.length === 0;
  validateForm();
}

function setFile(file) {
  if (!file) return;

  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!["pdf", "docx"].includes(extension)) {
    showError("Chỉ hỗ trợ tệp PDF hoặc DOCX.");
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showError("Tệp vượt quá giới hạn 10 MB.");
    return;
  }

  selectedFile = file;
  extractionCache = null;
  elements.fileTitle.textContent = file.name;
  elements.fileMeta.textContent = formatBytes(file.size);
  elements.fileDrop.classList.add("has-file");
  validateForm();
}

function validateForm() {
  elements.submit.disabled = !(
    selectedFile &&
    elements.industry.value &&
    elements.vertical.value &&
    elements.extractModel.value &&
    elements.analyzeModel.value
  );
}

function setView(view) {
  elements.empty.hidden = view !== "empty";
  elements.loading.hidden = view !== "loading";
  elements.error.hidden = view !== "error";
  elements.results.hidden = view !== "results";
}

function showError(message) {
  elements.errorMessage.textContent = message;
  setView("error");
}

async function analyze(event) {
  event.preventDefault();
  if (elements.submit.disabled) return;

  const form = new FormData(elements.form);
  const extractParams = new URLSearchParams({
    mode: form.get("mode"),
    target_language: form.get("target_language"),
    llm_model: form.get("extract_model"),
  });
  const upload = new FormData();
  upload.append("file", selectedFile);
  const extractionKey = [
    EXTRACTION_CACHE_VERSION,
    selectedFile.name,
    selectedFile.size,
    selectedFile.lastModified,
    form.get("mode"),
    form.get("target_language"),
    form.get("extract_model"),
  ].join("|");

  elements.submit.disabled = true;
  elements.submitLabel.textContent = "Đang phân tích";
  setView("loading");
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120000);

  try {
    let extraction = extractionCache?.key === extractionKey
      ? extractionCache.value
      : null;
    if (!extraction) {
      extraction = await requestJson(`/v1/cv/extract?${extractParams}`, {
        method: "POST",
        body: upload,
        signal: controller.signal,
      });
      extractionCache = { key: extractionKey, value: extraction };
    }
    document.querySelector("#loading-message").textContent = "Đang đối chiếu ngành và đánh giá nội dung...";
    const selectedLanguage = form.get("target_language");
    const result = await requestJson("/v1/cv/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        sections: extraction.sections,
        local_metrics: extraction.local_metrics,
        industry_slug: form.get("industry_slug"),
        vertical_slug: form.get("vertical_slug"),
        company_model: form.get("company_model"),
        language: selectedLanguage === "auto"
          ? extraction.meta?.analysis_language || "both"
          : selectedLanguage,
        llm_model: form.get("analyze_model"),
        strict_industry_match: true,
      }),
    });
    renderResults(result, extraction);
    setView("results");
  } catch (error) {
    showError(
      error.name === "AbortError"
        ? "Local AI đã vượt quá giới hạn 120 giây. Hãy chọn Hybrid hoặc dùng CV một ngôn ngữ."
        : error.message,
    );
  } finally {
    clearTimeout(timeoutId);
    elements.submitLabel.textContent = "Phân tích CV";
    document.querySelector("#loading-message").textContent = "Đang trích xuất và đối chiếu nội dung...";
    validateForm();
  }
}

function renderResults(data, extraction) {
  const score = Number(data.overall_score || 0);
  const selectedIndustry = industries.find((item) => item.slug === elements.industry.value);
  const selectedVertical = selectedIndustry?.verticals.find(
    (item) => item.slug === elements.vertical.value,
  );

  document.querySelector("#overall-score").textContent = score;
  document.querySelector("#score-gauge").style.setProperty("--score", `${score * 3.6}deg`);
  document.querySelector("#result-meta").textContent = [
    selectedIndustry?.display_name,
    selectedVertical?.display_name,
    `Parse: ${extraction.meta?.llm_model || "local"}`,
    `Analyze: ${data.meta?.model || ""}`,
  ].filter(Boolean).join(" · ");
  document.querySelector("#company-feedback").textContent =
    data.company_model_feedback || "Chưa có nhận xét tổng quan.";
  document.querySelector("#confidence-badge").textContent =
    `Độ tin cậy ${Math.round((data.confidence || 0) * 100)}%`;
  document.querySelector("#disclaimer").textContent = data.disclaimer || "";
  renderExtraction(extraction);

  const dimensions = [
    ["layout_ats", "Bố cục & ATS"],
    ["language", "Ngôn ngữ"],
    ["keywords", "Từ khóa"],
    ["jd_fit", "Mức độ phù hợp"],
  ];
  document.querySelector("#dimensions-grid").innerHTML = dimensions
    .map(([key, label]) => renderDimension(label, data.dimensions?.[key] || {}))
    .join("");

  const rewrites = data.rewrites || [];
  document.querySelector("#rewrite-count").textContent = `${rewrites.length} đề xuất`;
  document.querySelector("#rewrite-list").innerHTML = rewrites.length
    ? rewrites.map((rewrite) => renderRewrite(rewrite, data.meta?.language)).join("")
    : '<p class="no-content">Không có đề xuất chỉnh sửa.</p>';
}

function renderExtraction(extraction) {
  const coverage = extraction.coverage || {};
  const structured = extraction.structured_document || {};
  const coveragePercent = Math.round((coverage.coverage_score || 0) * 100);
  const classificationPercent = Math.round((coverage.classification_rate || 0) * 100);
  document.querySelector("#coverage-badge").textContent = `Lưu giữ ${coveragePercent}%`;
  document.querySelector("#coverage-grid").innerHTML = `
    <div><strong>${coverage.source_block_count || 0}</strong><span>Khối nguồn</span></div>
    <div><strong>${coverage.classified_block_count || 0}</strong><span>Đã phân loại</span></div>
    <div><strong>${coverage.unclassified_block_count || 0}</strong><span>Chưa phân loại</span></div>
    <div><strong>${classificationPercent}%</strong><span>Tỷ lệ phân loại</span></div>
  `;

  const groups = [
    ["Tóm tắt", structured.summary || []],
    ["Kinh nghiệm", (structured.experience || []).map((item) => item.raw_text)],
    ["Dự án", (structured.projects || []).map((item) => item.raw_text)],
    ["Học vấn", (structured.education || []).map((item) => item.raw_text)],
    ["Kỹ năng", Object.values(structured.skills || {}).flat()],
    ["Chứng chỉ", (structured.certifications || []).map((item) => item.raw_text)],
    ["Ngôn ngữ", structured.languages || []],
    ["Liên kết", structured.links || []],
    ["Thông tin khác", structured.other || []],
    ["Chưa phân loại", (structured.unclassified || []).map(
      (block) => `[Trang ${block.page}, cột ${block.column}] ${block.text}`,
    )],
    ["Khối nguồn", (structured.raw_blocks || []).map(
      (block) => `[${block.block_id} · trang ${block.page} · cột ${block.column}] ${block.text}`,
    )],
  ].filter(([, items]) => items.length);

  document.querySelector("#extracted-content").innerHTML = groups
    .map(([label, items], index) => `
      <details class="extracted-group" ${index < 3 ? "open" : ""}>
        <summary><span>${escapeHtml(label)}</span><strong>${items.length}</strong></summary>
        <ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </details>
    `)
    .join("");
}

function renderDimension(label, dimension) {
  const score = Number(dimension.score || 0);
  const issues = dimension.issues || dimension.missing || dimension.gaps || [];
  const fixes = dimension.fixes || dimension.suggested_bullets || [];

  return `
    <article class="dimension-card">
      <div class="dimension-topline">
        <h4>${escapeHtml(label)}</h4>
        <strong class="dimension-score ${scoreClass(score)}">${score}</strong>
      </div>
      <div class="score-track"><span style="width: ${score}%"></span></div>
      ${renderList("Cần chú ý", issues, "issue")}
      ${renderList("Đề xuất", fixes, "fix")}
    </article>
  `;
}

function renderList(title, items, type) {
  if (!items.length) return "";
  return `
    <div class="dimension-list ${type}">
      <span>${escapeHtml(title)}</span>
      <ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>
  `;
}

function renderRewrite(rewrite, resultLanguage) {
  const suggestions = [];
  if (["vi", "both"].includes(resultLanguage) && rewrite.suggested_vi) {
    suggestions.push(["Tiếng Việt", rewrite.suggested_vi]);
  }
  if (["en", "both"].includes(resultLanguage) && rewrite.suggested_en) {
    suggestions.push(["English", rewrite.suggested_en]);
  }
  if (!suggestions.length && rewrite.suggested_vi) {
    suggestions.push(["Tiếng Việt", rewrite.suggested_vi]);
  }
  if (!suggestions.length && rewrite.suggested_en) {
    suggestions.push(["English", rewrite.suggested_en]);
  }

  return `
    <article class="rewrite-item">
      <div class="rewrite-labels">
        <span class="section-tag">${escapeHtml(sectionLabel(rewrite.section))}</span>
        ${rewrite.needs_user_fact ? '<span class="fact-tag">Cần xác nhận dữ kiện</span>' : ""}
      </div>
      ${rewrite.change_reason ? `
        <p class="change-reason"><strong>Lý do chỉnh sửa:</strong> ${escapeHtml(rewrite.change_reason)}</p>
      ` : ""}
      <div class="rewrite-comparison">
        <div>
          <span class="comparison-label">Hiện tại</span>
          <p>${escapeHtml(rewrite.original_ref || "")}</p>
        </div>
        <div class="suggested-copy">
          <span class="comparison-label">Đề xuất cải thiện</span>
          ${suggestions.map(([language, text]) => `
            <div class="language-suggestion">
              <span class="language-tag">${language}</span>
              <p>${escapeHtml(text)}</p>
            </div>
          `).join("") || '<p>Không có đề xuất cho ngôn ngữ đã chọn.</p>'}
        </div>
      </div>
    </article>
  `;
}

function sectionLabel(section) {
  const normalized = String(section || "").trim().toLowerCase();
  const labels = {
    summary: "Tóm tắt",
    "career objective": "Mục tiêu nghề nghiệp",
    objective: "Mục tiêu nghề nghiệp",
    experience: "Kinh nghiệm",
    education: "Học vấn",
    skills: "Kỹ năng",
    projects: "Dự án",
    project: "Dự án",
    certifications: "Chứng chỉ",
    certification: "Chứng chỉ",
    other: "Thông tin khác",
  };
  return labels[normalized] || section || "Mục CV";
}

function scoreClass(score) {
  if (score >= 80) return "score-good";
  if (score >= 60) return "score-medium";
  return "score-low";
}

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

elements.industry.addEventListener("change", (event) => renderVerticals(event.target.value));
elements.vertical.addEventListener("change", validateForm);
elements.extractModel.addEventListener("change", validateForm);
elements.analyzeModel.addEventListener("change", validateForm);
elements.file.addEventListener("change", (event) => setFile(event.target.files[0]));
elements.form.addEventListener("submit", analyze);
elements.retry.addEventListener("click", () => elements.form.requestSubmit());

["dragenter", "dragover"].forEach((eventName) => {
  elements.fileDrop.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.fileDrop.classList.add("is-dragging");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  elements.fileDrop.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.fileDrop.classList.remove("is-dragging");
  });
});
elements.fileDrop.addEventListener("drop", (event) => setFile(event.dataTransfer.files[0]));

initialize();

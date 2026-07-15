const API_URL = (window.CVBUDDY_CONFIG?.apiBaseUrl || "http://localhost:8001").replace(/\/$/, "");
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
  openEditor: document.querySelector("#open-editor"),
  cvEditor: document.querySelector("#cv-editor"),
  cvEditForm: document.querySelector("#cv-edit-form"),
  cvPreview: document.querySelector("#cv-preview"),
  backToResults: document.querySelector("#back-to-results"),
  downloadWord: document.querySelector("#download-word"),
  downloadPdf: document.querySelector("#download-pdf"),
};

const CV_SECTION_CONFIG = [
  { key: "summary", label: "Tóm tắt / Mục tiêu", rows: 5 },
  { key: "experience", label: "Kinh nghiệm", rows: 8 },
  { key: "projects", label: "Dự án", rows: 8 },
  { key: "education", label: "Học vấn", rows: 5 },
  { key: "skills", label: "Kỹ năng", rows: 5 },
  { key: "certifications", label: "Chứng chỉ", rows: 5 },
  { key: "languages", label: "Ngôn ngữ", rows: 3 },
  { key: "other", label: "Thông tin khác", rows: 4 },
];

const CV_TEMPLATES = [
  {
    id: "software_sidebar_clean",
    name: "Software Sidebar Clean",
    description: "Hai cột gọn, hợp IT / Software / Intern",
  },
  {
    id: "marketing_green_timeline",
    name: "Marketing Green Timeline",
    description: "Xanh nổi bật, timeline rõ cho Marketing / Business",
  },
  {
    id: "language_elegant_sidebar",
    name: "Language Elegant Sidebar",
    description: "Sidebar beige, typography trang nhã cho NNA / Office",
  },
];

let industries = [];
let models = [];
let selectedFile = null;
let extractionCache = null;
let editableCv = null;
let selectedTemplateId = "software_sidebar_clean";
let avatarDataUrl = "";

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
      modelServerReady ? "API đã kết nối" : "Model server chưa sẵn sàng",
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
  elements.cvEditor.hidden = view !== "editor";
  document.body.classList.toggle("is-editor-view", view === "editor");
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
        strict_industry_match: false,
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

  renderCvEditor(data, extraction);
}

function renderCvEditor(data, extraction) {
  editableCv = buildEditableCv(data, extraction);
  elements.cvEditForm.innerHTML = `
    <div class="template-picker" role="radiogroup" aria-label="Chọn mẫu CV">
      ${CV_TEMPLATES.map((template) => `
        <label class="template-card ${template.id === selectedTemplateId ? "is-selected" : ""}">
          <input type="radio" name="template_id" value="${escapeHtml(template.id)}" ${template.id === selectedTemplateId ? "checked" : ""} />
          <span class="template-swatch ${escapeHtml(template.id)}" aria-hidden="true"></span>
          <strong>${escapeHtml(template.name)}</strong>
          <small>${escapeHtml(template.description)}</small>
        </label>
      `).join("")}
    </div>
    <div class="editor-field">
      <label for="cv-avatar">Ảnh đại diện</label>
      <input id="cv-avatar" name="avatar" type="file" accept="image/*" />
      <p class="field-hint">Dùng cho các mẫu có ảnh. Có thể bỏ trống.</p>
    </div>
    <div class="editor-field">
      <label for="cv-name">Họ tên</label>
      <input id="cv-name" name="name" type="text" value="${escapeHtml(editableCv.name)}" />
    </div>
    <div class="editor-field">
      <label for="cv-title">Vị trí / tiêu đề CV</label>
      <input id="cv-title" name="title" type="text" value="${escapeHtml(editableCv.title)}" />
    </div>
    <div class="editor-field">
      <label for="cv-contact">Liên hệ</label>
      <textarea id="cv-contact" name="contact" rows="4">${escapeHtml(editableCv.contact.join("\n"))}</textarea>
    </div>
    ${CV_SECTION_CONFIG.map((section) => `
      <div class="editor-field">
        <label for="cv-${section.key}">${escapeHtml(section.label)}</label>
        <textarea id="cv-${section.key}" name="${section.key}" rows="${section.rows}">${escapeHtml(
          (editableCv.sections[section.key] || []).join("\n\n"),
        )}</textarea>
      </div>
    `).join("")}
  `;
  renderCvPreview();
}

function openEditorView() {
  if (!editableCv) return;
  renderCvPreview();
  setView("editor");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function backToResults() {
  setView("results");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function buildEditableCv(data, extraction) {
  const structured = extraction.structured_document || {};
  const personal = structured.personal_info || {};
  const otherItems = uniqueList([
    ...(personal.other || []),
    ...(structured.other || []),
  ]);
  const personalName = firstValue(personal.name);
  const personalTitle = firstValue(personal.title);
  const name = personalName || pickName([
    ...asTextList(personal.name),
    ...otherItems,
  ]) || "";
  const title = personalTitle || pickTitle([
    ...asTextList(personal.title),
    ...otherItems,
  ], name) || "";
  const contact = uniqueList([
    ...(personal.contact || []),
    ...(personal.links || []),
    ...(structured.links || []),
    ...otherItems.filter((item) => /@|\[EMAIL\]|\[PHONE\]|\+?\d{6,}|linkedin|github|https?:|www\./i.test(item)),
  ]);
  const sections = {
    summary: asTextList(structured.summary),
    experience: asRecordTextList(structured.experience),
    projects: asRecordTextList(structured.projects),
    education: asRecordTextList(structured.education),
    skills: uniqueList(Object.values(structured.skills || {}).flat().map(String)),
    certifications: asRecordTextList(structured.certifications),
    languages: asTextList(structured.languages),
    other: otherItems.filter((item) => item !== name && item !== title && !contact.includes(item)),
  };

  for (const rewrite of data.rewrites || []) {
    const sectionKey = normalizeRewriteSection(rewrite.section);
    const suggestion = pickRewriteSuggestion(rewrite, data.meta?.language);
    if (!sectionKey || !suggestion) continue;
    sections[sectionKey] = applyRewriteToItems(sections[sectionKey] || [], rewrite.original_ref, suggestion);
  }

  return {
    name,
    title,
    contact,
    sections,
    language: data.meta?.language || "both",
  };
}

function readEditableCv() {
  const form = new FormData(elements.cvEditForm);
  selectedTemplateId = String(form.get("template_id") || selectedTemplateId);
  const sections = {};
  for (const section of CV_SECTION_CONFIG) {
    const splitSingleLines = ["skills", "certifications", "languages", "other"].includes(section.key);
    sections[section.key] = splitEditorValue(form.get(section.key), splitSingleLines);
  }
  return {
    name: String(form.get("name") || "").trim(),
    title: String(form.get("title") || "").trim(),
    contact: splitEditorValue(form.get("contact"), true),
    sections,
    language: editableCv?.language || "both",
    templateId: selectedTemplateId,
    avatar: avatarDataUrl,
  };
}

function renderCvPreview() {
  if (!editableCv) return;
  const cv = readEditableCv();
  elements.cvPreview.className = `cv-preview template-preview ${cv.templateId}`;
  elements.cvPreview.innerHTML = buildTemplateBodyHtml(cv);
  syncTemplateCards();
}

function downloadWord() {
  if (!editableCv) return;
  const cv = readEditableCv();
  const html = buildExportHtml(cv);
  downloadBlob(
    `cvbuddy-${slugify(cv.name || selectedFile?.name || "cv")}.doc`,
    new Blob(["\ufeff", html], { type: "application/msword;charset=utf-8" }),
  );
}

function downloadPdf() {
  if (!editableCv) return;
  const cv = readEditableCv();
  const printWindow = window.open("", "_blank", "width=920,height=1100");
  if (!printWindow) {
    showError("Trình duyệt đang chặn cửa sổ in. Hãy cho phép pop-up rồi thử lại.");
    return;
  }
  printWindow.document.open();
  printWindow.document.write(buildExportHtml(cv, { autoPrint: true }));
  printWindow.document.close();
}

function buildTemplateBodyHtml(cv) {
  if (cv.templateId === "marketing_green_timeline") return buildMarketingTemplate(cv);
  if (cv.templateId === "language_elegant_sidebar") return buildLanguageTemplate(cv);
  return buildSoftwareTemplate(cv);
}

function buildSoftwareTemplate(cv) {
  return `
    <div class="cv-page software-template">
      <aside class="cv-side">
        ${renderAvatar(cv)}
        ${renderContactBlock(cv.contact, "Liên hệ")}
        ${renderSectionBlock("Kỹ năng chuyên môn", cv.sections.skills)}
        ${renderSectionBlock("Chứng chỉ", cv.sections.certifications)}
        ${renderSectionBlock("Ngôn ngữ", cv.sections.languages)}
      </aside>
      <main class="cv-main">
        ${renderHero(cv)}
        ${renderSectionBlock("Mục tiêu nghề nghiệp", cv.sections.summary, { mode: "paragraph" })}
        ${renderSectionBlock("Kinh nghiệm", cv.sections.experience)}
        ${renderSectionBlock("Dự án", cv.sections.projects)}
        ${renderSectionBlock("Học vấn", cv.sections.education)}
        ${renderSectionBlock("Thông tin khác", cv.sections.other)}
      </main>
    </div>
  `;
}

function buildMarketingTemplate(cv) {
  return `
    <div class="cv-page marketing-template">
      <aside class="cv-side">
        <div class="marketing-photo-wrap">${renderAvatar(cv)}</div>
        ${renderContactBlock(cv.contact, "Liên hệ")}
        ${renderSectionBlock("Học vấn", cv.sections.education)}
        ${renderSectionBlock("Thành tích", cv.sections.other)}
        ${renderSectionBlock("Kỹ năng", cv.sections.skills)}
        ${renderSectionBlock("Ngoại ngữ", cv.sections.languages)}
        ${renderSectionBlock("Chứng chỉ", cv.sections.certifications)}
      </aside>
      <main class="cv-main">
        <div class="marketing-hero">
          <span class="dot-pattern" aria-hidden="true"></span>
          ${renderHero(cv)}
          ${renderPlainParagraphs(cv.sections.summary)}
        </div>
        ${renderSectionBlock("Kinh nghiệm", cv.sections.experience, { timeline: true })}
        ${renderSectionBlock("Dự án", cv.sections.projects, { timeline: true })}
      </main>
    </div>
  `;
}

function buildLanguageTemplate(cv) {
  return `
    <div class="cv-page language-template">
      <aside class="cv-side">
        <div class="beige-curve" aria-hidden="true"></div>
        ${renderAvatar(cv)}
        ${renderContactBlock(cv.contact, "Information")}
        ${renderSectionBlock("Skills", cv.sections.skills)}
        ${renderSectionBlock("Language", cv.sections.languages)}
        ${renderSectionBlock("Certificates", cv.sections.certifications)}
      </aside>
      <main class="cv-main">
        ${renderHero(cv)}
        ${renderSectionBlock("About me", cv.sections.summary, { icon: "●", mode: "paragraph" })}
        ${renderSectionBlock("Work experience", cv.sections.experience, { icon: "◆", timeline: true })}
        ${renderSectionBlock("Projects", cv.sections.projects, { icon: "◇", timeline: true })}
        ${renderSectionBlock("Education", cv.sections.education, { icon: "◉" })}
      </main>
    </div>
  `;
}

function renderHero(cv) {
  return `
    <header class="cv-hero">
      <h1>${escapeHtml(cv.name || "Họ tên")}</h1>
      ${cv.title ? `<p class="cv-title">${escapeHtml(cv.title)}</p>` : ""}
    </header>
  `;
}

function renderAvatar(cv) {
  if (cv.avatar) {
    return `<div class="cv-avatar"><img src="${escapeHtml(cv.avatar)}" alt="" /></div>`;
  }
  return `<div class="cv-avatar cv-avatar-empty">${escapeHtml(initials(cv.name || "CV"))}</div>`;
}

function renderContactBlock(items, label) {
  if (!items.length) return "";
  return `
    <section class="cv-section contact-section">
      <h2>${escapeHtml(label)}</h2>
      <ul class="contact-list">
        ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    </section>
  `;
}

function renderSectionBlock(label, items, options = {}) {
  const values = items || [];
  if (!values.length) return "";
  const icon = options.icon ? `<span class="section-icon">${escapeHtml(options.icon)}</span>` : "";
  const content = options.mode === "paragraph"
    ? renderPlainParagraphs(values)
    : renderCvSectionItems(values, options);
  return `
    <section class="cv-section ${options.timeline ? "timeline-section" : ""}">
      <h2>${icon}<span>${escapeHtml(label)}</span></h2>
      ${content}
    </section>
  `;
}

function renderPlainParagraphs(items) {
  return items.length
    ? `<div class="paragraph-list">${items.map((item) => `<p>${formatCvText(item)}</p>`).join("")}</div>`
    : "";
}

function renderCvSectionItems(items, options = {}) {
  const className = options.timeline ? "cv-items timeline-list" : "cv-items";
  return `
    <ul class="${className}">
      ${items.map((item) => `<li>${formatCvText(item)}</li>`).join("")}
    </ul>
  `;
}

function formatCvText(value) {
  return escapeHtml(value).replaceAll("\n", "<br />");
}

function buildExportHtml(cv, options = {}) {
  const printScript = options.autoPrint
    ? `<script>
        window.addEventListener("load", () => {
          window.focus();
          window.print();
        });
      <\/script>`
    : "";
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(cv.name || "CV")}</title>
  <style>
    ${templatePrintCss()}
  </style>
</head>
<body>${buildTemplateBodyHtml(cv)}${printScript}</body>
</html>`;
}

function templatePrintCss() {
  return `
    @page { size: A4; margin: 0; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #fff; color: #343a40; font-family: Arial, Helvetica, sans-serif; }
    .cv-page { width: 210mm; min-height: 297mm; display: grid; overflow: hidden; background: #fff; font-size: 10pt; line-height: 1.42; }
    .cv-side { position: relative; min-width: 0; padding: 12mm 9mm; }
    .cv-main { min-width: 0; padding: 18mm 12mm 14mm; }
    .cv-avatar { width: 42mm; height: 42mm; margin: 0 auto 12mm; display: grid; place-items: center; overflow: hidden; border-radius: 50%; background: #f3f4f2; color: #3d423f; font-size: 20pt; font-weight: 800; }
    .cv-avatar img { width: 100%; height: 100%; object-fit: cover; }
    .cv-hero { margin-bottom: 10mm; }
    .cv-hero h1 { margin: 0; color: #303030; font-size: 30pt; line-height: 1.05; font-weight: 500; letter-spacing: 0; text-transform: none; }
    .cv-title { margin: 4mm 0 0; font-size: 11pt; font-weight: 700; letter-spacing: 4px; text-transform: uppercase; color: #4a4a47; }
    .cv-section { margin-top: 8mm; break-inside: avoid; }
    .cv-section:first-child { margin-top: 0; }
    .cv-section h2 { margin: 0 0 4mm; display: flex; align-items: center; gap: 3mm; color: #343a40; font-size: 12pt; font-weight: 800; letter-spacing: 1.8px; text-transform: uppercase; }
    .cv-main .cv-section h2::after { content: ""; flex: 1; height: 1px; background: currentColor; opacity: .85; }
    .cv-side .cv-section h2 { padding-bottom: 2mm; border-bottom: 1px solid currentColor; }
    .cv-items, .contact-list { margin: 0; padding-left: 4.5mm; }
    .cv-items li, .contact-list li { margin: 0 0 2.3mm; break-inside: avoid; }
    .paragraph-list p { margin: 0 0 3mm; text-align: justify; }
    .software-template { grid-template-columns: 76mm 1fr; }
    .software-template .cv-side { background: #eeeeec; }
    .software-template .cv-side h2 { justify-content: center; border: 0; border-radius: 999px; padding: 2.4mm 4mm; background: #464642; color: #fff; font-size: 11pt; letter-spacing: .8px; }
    .software-template .cv-hero h1 { font-size: 32pt; }
    .marketing-template { grid-template-columns: 79mm 1fr; }
    .marketing-template .cv-side { padding-top: 12mm; }
    .marketing-template .cv-main { padding-top: 20mm; border-left: 1.4px solid #16b56f; }
    .marketing-template .cv-hero h1 { font-size: 25pt; font-weight: 900; letter-spacing: 1px; text-transform: uppercase; }
    .marketing-template .cv-title { color: #333; font-size: 13pt; letter-spacing: 1px; }
    .marketing-template .cv-section h2 { color: #2d3034; letter-spacing: 4px; }
    .marketing-template .cv-section h2::after, .marketing-template .cv-side .cv-section h2 { border-color: #16b56f; color: #2d3034; }
    .marketing-template .cv-main .cv-section h2::after { background: #16b56f; opacity: 1; }
    .marketing-photo-wrap { position: relative; }
    .marketing-photo-wrap::after { content: ""; position: absolute; right: -7mm; bottom: 4mm; width: 26mm; height: 20mm; background: radial-gradient(#00b86b 1.2px, transparent 1.4px); background-size: 4px 4px; z-index: 0; }
    .marketing-photo-wrap .cv-avatar { position: relative; z-index: 1; border-radius: 2mm; border: 1px solid #16b56f; }
    .marketing-template .timeline-list { border-left: 1.2px solid #16b56f; padding-left: 6mm; list-style: none; }
    .marketing-template .timeline-list li { position: relative; }
    .marketing-template .timeline-list li::before { content: ""; position: absolute; left: -7.1mm; top: 1.5mm; width: 2.3mm; height: 2.3mm; border-radius: 50%; border: 1.5px solid #16b56f; background: #fff; }
    .language-template { grid-template-columns: 74mm 1fr; color: #303948; }
    .language-template .cv-side { background: #e7decd; padding-top: 11mm; }
    .language-template .cv-main { padding-top: 22mm; }
    .language-template .cv-avatar { width: 52mm; height: 52mm; }
    .language-template .cv-hero h1 { font-family: Georgia, 'Times New Roman', serif; color: #050505; font-size: 31pt; font-weight: 500; text-transform: uppercase; letter-spacing: 1px; }
    .language-template .cv-title { color: #050505; font-size: 15pt; letter-spacing: 2px; }
    .language-template .cv-section h2 { color: #303948; letter-spacing: 3px; }
    .language-template .cv-main .cv-section h2::after, .language-template .cv-side .cv-section h2 { border-color: #1e3857; color: #303948; }
    .language-template .cv-main .cv-section h2::after { background: #1e3857; opacity: 1; }
    .language-template .section-icon { width: 6mm; height: 6mm; display: inline-grid; place-items: center; border-radius: 50%; background: #303948; color: #fff; font-size: 8pt; letter-spacing: 0; }
    .language-template .timeline-list { border-left: 1px solid #9aa6b4; padding-left: 6mm; list-style: none; }
    .language-template .timeline-list li { position: relative; }
    .language-template .timeline-list li::before { content: ""; position: absolute; left: -7.1mm; top: 1.5mm; width: 2mm; height: 2mm; border-radius: 50%; border: 1px solid #536071; background: #fff; }
  `;
}

function normalizeRewriteSection(section) {
  const value = String(section || "").trim().toLowerCase();
  if (["summary", "objective", "career objective", "profile"].includes(value)) return "summary";
  if (["experience", "work experience", "employment"].includes(value)) return "experience";
  if (["project", "projects"].includes(value)) return "projects";
  if (["education"].includes(value)) return "education";
  if (["skill", "skills", "technical skills", "soft skills"].includes(value)) return "skills";
  if (["certification", "certifications", "certificate"].includes(value)) return "certifications";
  if (["language", "languages"].includes(value)) return "languages";
  if (["other"].includes(value)) return "other";
  return "";
}

function pickRewriteSuggestion(rewrite, resultLanguage) {
  if (resultLanguage === "vi") return rewrite.suggested_vi || "";
  if (resultLanguage === "en") return rewrite.suggested_en || "";
  if (isLikelyVietnamese(rewrite.original_ref)) return rewrite.suggested_vi || rewrite.suggested_en || "";
  if (isLikelyEnglish(rewrite.original_ref)) return rewrite.suggested_en || rewrite.suggested_vi || "";
  return rewrite.suggested_vi || rewrite.suggested_en || "";
}

function applyRewriteToItems(items, original, suggestion) {
  const cleanedSuggestion = String(suggestion || "").trim();
  if (!cleanedSuggestion) return items;
  const originalNormalized = normalizeText(original);
  if (!originalNormalized) return uniqueList([...items, cleanedSuggestion]);

  const nextItems = [...items];
  const matchIndex = nextItems.findIndex((item) => {
    const itemNormalized = normalizeText(item);
    return itemNormalized === originalNormalized
      || itemNormalized.includes(originalNormalized)
      || originalNormalized.includes(itemNormalized);
  });
  if (matchIndex === -1) return uniqueList([...nextItems, cleanedSuggestion]);

  const current = nextItems[matchIndex];
  const currentNormalized = normalizeText(current);
  nextItems[matchIndex] = currentNormalized === originalNormalized || originalNormalized.length > currentNormalized.length * 0.7
    ? cleanedSuggestion
    : `${current}\n${cleanedSuggestion}`;
  return uniqueList(nextItems);
}

function asRecordTextList(records) {
  return (records || []).map((item) => item?.raw_text || String(item || "")).filter(Boolean);
}

function asTextList(items) {
  return (items || []).map(String).filter((item) => item.trim());
}

function firstValue(items) {
  return asTextList(items)[0] || "";
}

function splitEditorValue(value, splitSingleLines = false) {
  const pattern = splitSingleLines
    ? /\r?\n+/
    : /\n{2,}|\r?\n(?=(?:\d{1,2}\/)?\d{4}\s*(?:-|–|—)|[A-ZÀ-Ỹ][^:]{2,}\s*\|)/;
  return String(value || "")
    .split(pattern)
    .map((item) => item.trim())
    .filter(Boolean);
}

function pickName(items) {
  const candidates = items
    .map((item, index) => {
      const value = cleanNameCandidate(item);
      return { value, index, score: nameScore(value) };
    })
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score || left.index - right.index);
  return candidates[0]?.value || "";
}

function pickTitle(items, name) {
  return items.find((item) => {
    const value = String(item).trim();
    return value
      && value !== name
      && value.length <= 60
      && /intern|engineer|developer|analyst|designer|manager|student|thực tập|kỹ sư|sinh viên/i.test(value);
  });
}

function cleanNameCandidate(value) {
  return String(value || "")
    .trim()
    .replace(/^(họ\s*tên|ho\s*ten|full\s*name|name)\s*[:\-]\s*/i, "")
    .replace(/^[^\wÀ-ỹ]+|[^\wÀ-ỹ]+$/gu, "")
    .replace(/\s+/g, " ")
    .trim();
}

function nameScore(value) {
  if (!value || value.length < 4 || value.length > 48) return 0;
  if (/@|\[|\]|\d|linkedin|github|https?:|www\.|ward|district|city|province|street|phường|quận|huyện|thành phố|tỉnh|địa chỉ/i.test(value)) return 0;
  if (/male|female|nam|nữ|intern|fresher|student|engineer|developer|designer|analyst|manager|thực tập|sinh viên|kỹ sư|nhân viên|chuyên viên/i.test(value)) return 0;
  if (/career|objective|education|experience|skill|project|certificate|mục tiêu|học vấn|kinh nghiệm|kỹ năng|dự án|chứng chỉ/i.test(value)) return 0;
  if (!/^[A-Za-zÀ-ỹ'. -]+$/u.test(value)) return 0;

  const tokens = value.split(/\s+/).filter(Boolean);
  if (tokens.length < 2 || tokens.length > 5) return 0;
  if (tokens.some((token) => token.replace(/[.-]/g, "").length < 2)) return 0;

  const surnames = new Set([
    "nguyễn", "nguyen", "trần", "tran", "lê", "le", "phạm", "pham",
    "hoàng", "hoang", "huỳnh", "huynh", "phan", "vũ", "vu", "võ", "vo",
    "đặng", "dang", "bùi", "bui", "đỗ", "do", "ngô", "ngo", "dương", "duong",
  ]);
  let score = 10;
  if (surnames.has(tokens[0].toLowerCase())) score += 6;
  if (/[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]/i.test(value)) score += 3;
  score += tokens.filter((token) => token[0] === token[0].toUpperCase() || token === token.toUpperCase()).length;
  if ([3, 4].includes(tokens.length)) score += 2;
  if (value === value.toUpperCase()) score -= 1;
  return score;
}

function uniqueList(items) {
  const seen = new Set();
  const output = [];
  for (const item of items.map(String).map((value) => value.trim()).filter(Boolean)) {
    const key = normalizeText(item);
    if (seen.has(key)) continue;
    seen.add(key);
    output.push(item);
  }
  return output;
}

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function isLikelyVietnamese(value) {
  return /[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]/i.test(value);
}

function isLikelyEnglish(value) {
  return /\b(the|and|with|using|developed|designed|built|managed|team|project|experience|education)\b/i.test(value);
}

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function slugify(value) {
  return String(value || "cv")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase() || "cv";
}

function initials(value) {
  const parts = String(value || "CV")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "CV";
  return parts.slice(-2).map((part) => part[0]).join("").toUpperCase();
}

function syncTemplateCards() {
  elements.cvEditForm.querySelectorAll(".template-card").forEach((card) => {
    const input = card.querySelector('input[name="template_id"]');
    card.classList.toggle("is-selected", input?.value === selectedTemplateId);
  });
}

function setAvatar(file) {
  if (!file) {
    avatarDataUrl = "";
    renderCvPreview();
    return;
  }
  if (!file.type.startsWith("image/")) {
    showError("Ảnh đại diện phải là file hình ảnh.");
    return;
  }
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    avatarDataUrl = String(reader.result || "");
    renderCvPreview();
  });
  reader.readAsDataURL(file);
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
elements.openEditor.addEventListener("click", openEditorView);
elements.backToResults.addEventListener("click", backToResults);
elements.cvEditForm.addEventListener("input", renderCvPreview);
elements.cvEditForm.addEventListener("change", (event) => {
  if (event.target?.name === "avatar") {
    setAvatar(event.target.files?.[0]);
    return;
  }
  renderCvPreview();
});
elements.downloadWord.addEventListener("click", downloadWord);
elements.downloadPdf.addEventListener("click", downloadPdf);

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

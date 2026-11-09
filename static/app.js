document.addEventListener("DOMContentLoaded", () => {
  // Navigation tabs
  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");

  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      tabButtons.forEach(b => b.classList.remove("active"));
      tabContents.forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(targetTab).classList.add("active");

      if (targetTab === "tab-documents") {
        loadDocuments();
      } else if (targetTab === "tab-history") {
        loadHistory();
      }
    });
  });

  // Modal helpers
  const docModal = document.getElementById("doc-modal");
  const historyModal = document.getElementById("history-modal");
  const closeButtons = document.querySelectorAll(".close-modal");

  closeButtons.forEach(b => {
    b.addEventListener("click", () => {
      docModal.classList.remove("active");
      historyModal.classList.remove("active");
    });
  });

  window.addEventListener("click", (e) => {
    if (e.target === docModal) docModal.classList.remove("active");
    if (e.target === historyModal) historyModal.classList.remove("active");
  });

  // ===================== Раздел 1: Документы =====================
  const addDocForm = document.getElementById("add-doc-form");
  const docTitleInput = document.getElementById("doc-title");
  const docTextInput = document.getElementById("doc-text");
  const docsTableBody = document.getElementById("docs-table-body");
  const btnRefreshDocs = document.getElementById("btn-refresh-docs");

  async function loadDocuments() {
    try {
      docsTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center;">Загрузка...</td></tr>`;
      const res = await fetch("/kb/documents");
      if (!res.ok) throw new Error("Ошибка загрузки документов");
      const docs = await res.json();

      if (!docs || docs.length === 0) {
        docsTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color: var(--text-muted);">Документов пока нет. Добавьте первый документ выше.</td></tr>`;
        return;
      }

      docsTableBody.innerHTML = "";
      docs.forEach(doc => {
        const tr = document.createElement("tr");
        const formattedDate = new Date(doc.created_at).toLocaleString("ru-RU");
        tr.innerHTML = `
          <td><strong>${escapeHtml(doc.title)}</strong></td>
          <td>${formattedDate}</td>
          <td><span class="code-box" style="font-size:0.75rem;">${doc.id.substring(0, 8)}...</span></td>
          <td>
            <div style="display: flex; gap: 0.4rem;">
              <button class="btn btn-secondary btn-sm btn-open-doc" data-id="${doc.id}">Открыть</button>
              <button class="btn btn-secondary btn-sm btn-delete-doc" data-id="${doc.id}" data-title="${escapeHtml(doc.title)}" style="color: var(--danger);">Удалить</button>
            </div>
          </td>
        `;
        docsTableBody.appendChild(tr);
      });

      document.querySelectorAll(".btn-open-doc").forEach(btn => {
        btn.addEventListener("click", () => openDocument(btn.getAttribute("data-id")));
      });

      document.querySelectorAll(".btn-delete-doc").forEach(btn => {
        btn.addEventListener("click", () => deleteDocument(btn.getAttribute("data-id"), btn.getAttribute("data-title")));
      });
    } catch (err) {
      docsTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color: var(--danger);">Ошибка: ${escapeHtml(err.message)}</td></tr>`;
    }
  }

  async function deleteDocument(docId, docTitle) {
    if (!confirm(`Вы уверены, что хотите удалить документ «${docTitle || docId}»?\nВсе связанные фрагменты будут удалены из базы знаний.`)) {
      return;
    }
    try {
      const res = await fetch(`/kb/documents/${docId}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Не удалось удалить документ");
      }
      docModal.classList.remove("active");
      alert("Документ успешно удален.");
      loadDocuments();
    } catch (err) {
      alert("Ошибка удаления: " + err.message);
    }
  }

  let currentViewingDoc = null;

  async function openDocument(docId) {
    try {
      const res = await fetch(`/kb/documents/${docId}`);
      if (!res.ok) throw new Error("Документ не найден");
      const doc = await res.json();
      currentViewingDoc = doc;

      document.getElementById("modal-doc-title").textContent = doc.title;
      document.getElementById("modal-doc-id").textContent = doc.id;
      document.getElementById("modal-doc-text").textContent = doc.text;
      docModal.classList.add("active");
    } catch (err) {
      alert("Не удалось загрузить документ: " + err.message);
    }
  }

  const btnModalDeleteDoc = document.getElementById("btn-modal-delete-doc");
  if (btnModalDeleteDoc) {
    btnModalDeleteDoc.addEventListener("click", () => {
      if (currentViewingDoc) {
        deleteDocument(currentViewingDoc.id, currentViewingDoc.title);
      }
    });
  }

  addDocForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = docTitleInput.value.trim();
    const text = docTextInput.value.trim();
    if (!title || !text) return;

    const btn = document.getElementById("btn-save-doc");
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> <span>Сохранение...</span>`;

    try {
      const res = await fetch("/kb/documents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, text })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ? (Array.isArray(data.detail) ? data.detail[0].msg : data.detail) : "Ошибка добавления");
      }
      docTitleInput.value = "";
      docTextInput.value = "";
      alert("Документ успешно добавлен!");
      loadDocuments();
    } catch (err) {
      alert("Ошибка: " + err.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<span>Добавить документ</span>`;
    }
  });

  btnRefreshDocs.addEventListener("click", loadDocuments);

  // ===================== Раздел 2: Вопросы =====================
  const askForm = document.getElementById("ask-form");
  const questionInput = document.getElementById("question-input");
  const askResultContainer = document.getElementById("ask-result-container");
  const reviewBadge = document.getElementById("review-badge");
  const answerContent = document.getElementById("answer-content");
  const sourcesWrapper = document.getElementById("sources-wrapper");
  const sourcesList = document.getElementById("sources-list");

  // Sample questions click handler
  document.querySelectorAll(".sample-q").forEach(btn => {
    btn.addEventListener("click", () => {
      questionInput.value = btn.getAttribute("data-q");
      askForm.dispatchEvent(new Event("submit"));
    });
  });

  askForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = questionInput.value.trim();
    if (!question) return;

    const btn = document.getElementById("btn-ask");
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> <span>Поиск и синтез...</span>`;
    askResultContainer.style.display = "none";

    try {
      const res = await fetch("/kb/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Ошибка ответа");

      askResultContainer.style.display = "block";
      answerContent.textContent = data.answer;

      if (data.needs_review) {
        reviewBadge.className = "badge badge-warning";
        reviewBadge.textContent = "Требует проверки (needs_review=true)";
      } else {
        reviewBadge.className = "badge badge-success";
        reviewBadge.textContent = "Источники подтверждены";
      }

      sourcesList.innerHTML = "";
      if (data.sources && data.sources.length > 0) {
        sourcesWrapper.style.display = "block";
        data.sources.forEach(src => {
          const item = document.createElement("div");
          item.className = "source-item";
          item.innerHTML = `
            <div>«${escapeHtml(src.quote)}»</div>
            <div class="source-doc-link" data-doc="${src.document_id}">📄 Документ ID: ${src.document_id.substring(0, 8)}...</div>
          `;
          sourcesList.appendChild(item);
        });

        sourcesList.querySelectorAll(".source-doc-link").forEach(link => {
          link.addEventListener("click", () => openDocument(link.getAttribute("data-doc")));
        });
      } else {
        sourcesWrapper.style.display = "none";
      }

    } catch (err) {
      alert("Ошибка при получении ответа: " + err.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<span>Спросить систему</span>`;
    }
  });

  // ===================== Раздел 3: История =====================
  const historyTableBody = document.getElementById("history-table-body");
  const filterNeedsReview = document.getElementById("filter-needs-review");
  const btnRefreshHistory = document.getElementById("btn-refresh-history");

  async function loadHistory() {
    try {
      historyTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center;">Загрузка...</td></tr>`;
      const onlyReview = filterNeedsReview.checked;
      const url = `/kb/history?limit=100${onlyReview ? "&needs_review=true" : ""}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Ошибка загрузки истории");
      const runs = await res.json();

      if (!runs || runs.length === 0) {
        historyTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color: var(--text-muted);">История запросов пуста.</td></tr>`;
        return;
      }

      historyTableBody.innerHTML = "";
      runs.forEach(run => {
        const tr = document.createElement("tr");
        const formattedDate = new Date(run.created_at).toLocaleString("ru-RU");
        const badge = run.needs_review
          ? `<span class="badge badge-warning">Требует проверки</span>`
          : `<span class="badge badge-success">OK</span>`;

        tr.innerHTML = `
          <td>${formattedDate}</td>
          <td>${escapeHtml(run.question)}</td>
          <td>${badge}</td>
          <td>
            <button class="btn btn-secondary btn-sm btn-open-history" data-id="${run.id}">Карточка</button>
          </td>
        `;
        historyTableBody.appendChild(tr);
      });

      document.querySelectorAll(".btn-open-history").forEach(btn => {
        btn.addEventListener("click", () => openHistoryDetail(btn.getAttribute("data-id")));
      });
    } catch (err) {
      historyTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color: var(--danger);">Ошибка: ${escapeHtml(err.message)}</td></tr>`;
    }
  }

  async function openHistoryDetail(qaId) {
    try {
      const res = await fetch(`/kb/history/${qaId}`);
      if (!res.ok) throw new Error("Запись не найдена");
      const run = await res.json();

      document.getElementById("modal-hist-question").textContent = run.question;
      document.getElementById("modal-hist-status").innerHTML = run.needs_review
        ? `<span class="badge badge-warning">Требует проверки (needs_review=true)</span>`
        : `<span class="badge badge-success">Верифицировано (needs_review=false)</span>`;

      document.getElementById("modal-hist-answer").textContent = run.answer;

      const errorBox = document.getElementById("modal-hist-error-box");
      const errorContent = document.getElementById("modal-hist-error");
      if (run.error) {
        errorBox.style.display = "block";
        errorContent.textContent = run.error;
      } else {
        errorBox.style.display = "none";
      }

      const sourcesBox = document.getElementById("modal-hist-sources");
      sourcesBox.innerHTML = "";
      if (run.sources && run.sources.length > 0) {
        run.sources.forEach(src => {
          const item = document.createElement("div");
          item.className = "source-item";
          item.innerHTML = `
            <div>«${escapeHtml(src.quote)}»</div>
            <div class="source-doc-link" data-doc="${src.document_id}">📄 Документ ID: ${src.document_id.substring(0, 8)}...</div>
          `;
          sourcesBox.appendChild(item);
        });

        sourcesBox.querySelectorAll(".source-doc-link").forEach(link => {
          link.addEventListener("click", () => {
            historyModal.classList.remove("active");
            openDocument(link.getAttribute("data-doc"));
          });
        });
      } else {
        sourcesBox.innerHTML = `<span style="color: var(--text-muted); font-size: 0.85rem;">Источники отсутствуют</span>`;
      }

      historyModal.classList.add("active");
    } catch (err) {
      alert("Не удалось загрузить карточку: " + err.message);
    }
  }

  filterNeedsReview.addEventListener("change", loadHistory);
  btnRefreshHistory.addEventListener("click", loadHistory);

  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // Initial load
  loadDocuments();
});

// Native Meilisearch HTTP API Configuration (Port 7700)
const MEILI_HOST = "http://localhost:7700";
const MEILI_INDEX = "government_content";
const MEILI_SEARCH_KEY = "10db0a805907e4d6fb9fc4fa4ac0b71f372739b6f01ef7ac510a31cbce742182";
const PAGE_SIZE = 20;

// Minimum relevance score for vector matches (filters out random/irrelevant noise)
const RANKING_SCORE_THRESHOLD = 0.82;

const searchInput = document.getElementById("searchInput");
const searchForm = document.getElementById("searchForm");
const suggestionsBox = document.getElementById("suggestions");
const resultsArea = document.getElementById("resultsArea");
const pagination = document.getElementById("pagination");
const previousButton = document.getElementById("previousButton");
const nextButton = document.getElementById("nextButton");
const pageNumber = document.getElementById("pageNumber");

let debounceTimer = null;
let suggestionController = null;
let searchController = null;
let currentQuery = "";
let currentOffset = 0;
let currentTotal = 0;

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function showSuggestions(hits) {
    if (!hits || !hits.length) {
        hideSuggestions();
        return;
    }

    suggestionsBox.innerHTML = hits
        .map(
            (hit, index) => `
            <button class="suggestion" type="button" data-index="${index}">
                <span class="suggestion-title">${escapeHtml(hit.title)}</span>
                <span class="suggestion-meta">${escapeHtml(hit.content_type || "record")}</span>
            </button>
        `
        )
        .join("");

    suggestionsBox.querySelectorAll(".suggestion").forEach((item, index) => {
        item.addEventListener("click", () => {
            const selected = hits[index];
            searchInput.value = selected.title;
            hideSuggestions();
            executeSearch(selected.title, 0);
        });
    });

    suggestionsBox.classList.add("visible");
}

function hideSuggestions() {
    suggestionsBox.classList.remove("visible");
    suggestionsBox.innerHTML = "";
}

// 1. Autocomplete Suggestions via Local Meilisearch
async function fetchSuggestions(query) {
    const cleaned = query.trim();

    if (!cleaned || !/[a-zA-Z0-9]/.test(cleaned)) {
        hideSuggestions();
        return;
    }

    if (suggestionController) {
        suggestionController.abort();
    }
    suggestionController = new AbortController();

    try {
        const response = await fetch(`${MEILI_HOST}/indexes/${MEILI_INDEX}/search`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${MEILI_SEARCH_KEY}`
            },
            body: JSON.stringify({
                q: cleaned,
                limit: 5,
                attributesToRetrieve: ["title", "content_type", "url"]
            }),
            signal: suggestionController.signal
        });

        if (!response.ok) {
            hideSuggestions();
            return;
        }

        const data = await response.json();

        if (searchInput.value.trim() !== cleaned) {
            return;
        }

        showSuggestions(data.hits || []);
    } catch (error) {
        if (error.name !== "AbortError") {
            hideSuggestions();
        }
    }
}

function renderLoading() {
    resultsArea.innerHTML = `
        <div class="empty-state">
            <div class="empty-icon">⏳</div>
            <div class="empty-title">Searching...</div>
            <div class="empty-text">Please wait for the search results...</div>
        </div>
    `;
    pagination.classList.remove("visible");
}

function renderEmpty(query) {
    resultsArea.innerHTML = `
        <div class="empty-state">
            <div class="empty-icon">🔍</div>
            <div class="empty-title">No records found</div>
            <div class="empty-text">No Government of Bermuda Knowledge Base records matched "${escapeHtml(query)}".</div>
        </div>
    `;
    pagination.classList.remove("visible");
}

function renderResults(data) {
    const results = Array.isArray(data.hits) ? data.hits : [];

    // Accurate Count: If no hits returned by Meilisearch, total is 0
    currentTotal = results.length === 0 ? 0 : (data.estimatedTotalHits || data.totalHits || results.length);

    if (!results.length || currentTotal === 0) {
        renderEmpty(data.query);
        return;
    }

    resultsArea.innerHTML = `
        <div class="results-header">
            <div class="results-count">
                ${currentTotal.toLocaleString()} record${currentTotal === 1 ? "" : "s"} found
            </div>
            <div class="results-query">
                Results for <strong>"${escapeHtml(data.query)}"</strong>
            </div>
        </div>

        ${results
            .map(
                result => `
                <article class="result-card">
                    <div class="result-type">
                        ${escapeHtml(result.content_type || "record")}
                    </div>
                    <h2 class="result-title">
                        ${escapeHtml(result.title || "Untitled record")}
                    </h2>
                    ${
                        result.summary
                            ? `<p class="result-summary">${escapeHtml(result.summary)}</p>`
                            : ""
                    }
                    ${
                        result.agency_name
                            ? `<div class="result-agency">${escapeHtml(result.agency_name)}</div>`
                            : ""
                    }
                    ${
                        result.url
                            ? `<a class="result-link" href="${escapeHtml(result.url)}" target="_blank" rel="noopener noreferrer">Open record →</a>`
                            : ""
                    }
                </article>
            `
            )
            .join("")}
    `;

    updatePagination();
}

function updatePagination() {
    const totalPages = Math.max(1, Math.ceil(currentTotal / PAGE_SIZE));
    const currentPage = Math.floor(currentOffset / PAGE_SIZE) + 1;

    pageNumber.textContent = `Page ${currentPage} of ${totalPages}`;
    previousButton.disabled = currentOffset === 0;
    nextButton.disabled = currentOffset + PAGE_SIZE >= currentTotal;

    if (currentTotal > PAGE_SIZE) {
        pagination.classList.add("visible");
    } else {
        pagination.classList.remove("visible");
    }
}

// 2. Hybrid Semantic Search via Local Meilisearch HTTP API
async function executeSearch(query, offset = 0) {
    const cleaned = query.trim();

    if (!cleaned) {
        resultsArea.innerHTML = "";
        pagination.classList.remove("visible");
        return;
    }

    if (!/[a-zA-Z0-9]/.test(cleaned)) {
        hideSuggestions();
        renderEmpty(cleaned);
        return;
    }

    currentQuery = cleaned;
    currentOffset = offset;

    hideSuggestions();
    renderLoading();

    if (searchController) {
        searchController.abort();
    }
    searchController = new AbortController();

    const pageNumberVal = Math.floor(offset / PAGE_SIZE) + 1;

    try {
        const response = await fetch(`${MEILI_HOST}/indexes/${MEILI_INDEX}/search`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${MEILI_SEARCH_KEY}`
            },
            body: JSON.stringify({
                q: cleaned,
                page: pageNumberVal,
                hitsPerPage: PAGE_SIZE,
                rankingScoreThreshold: RANKING_SCORE_THRESHOLD,
                hybrid: {
                    semanticRatio: 0.70,
                    embedder: "default"
                },
                attributesToRetrieve: [
                    "id", "source_id", "source_table", "content_type", "slug",
                    "title", "summary", "agency_name", "published_at", "url", "form_url", "topics"
                ],
                showRankingScore: true
            }),
            signal: searchController.signal
        });

        if (!response.ok) {
            throw new Error("Meilisearch search failed.");
        }

        const data = await response.json();

        if (currentQuery !== cleaned) {
            return;
        }

        renderResults(data);

        if (offset > 0) {
            resultsArea.scrollIntoView({ behavior: "smooth" });
        }
    } catch (error) {
        if (error.name === "AbortError") {
            return;
        }

        resultsArea.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⚠️</div>
                <div class="empty-title">Local Search Unavailable</div>
                <div class="empty-text">Could not connect to Meilisearch on ${MEILI_HOST}. Make sure Docker container is running.</div>
            </div>
        `;
        pagination.classList.remove("visible");
    }
}

// Event Listeners
searchInput.addEventListener("input", event => {
    const value = event.target.value;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
        fetchSuggestions(value);
    }, 100);
});

searchForm.addEventListener("submit", event => {
    event.preventDefault();
    executeSearch(searchInput.value, 0);
});

previousButton.addEventListener("click", () => {
    if (currentOffset === 0) return;
    executeSearch(currentQuery, Math.max(0, currentOffset - PAGE_SIZE));
});

nextButton.addEventListener("click", () => {
    if (currentOffset + PAGE_SIZE >= currentTotal) return;
    executeSearch(currentQuery, currentOffset + PAGE_SIZE);
});

document.addEventListener("click", event => {
    if (!event.target.closest(".search-panel")) {
        hideSuggestions();
    }
});
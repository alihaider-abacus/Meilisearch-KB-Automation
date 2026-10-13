// api/search.js - Pure In-Memory Keyword Search Engine with Multi-Field Relevance
import fs from "fs";
import path from "path";

let cachedRecords = null;

// Load records into memory once
function getRecords() {
    if (!cachedRecords) {
        try {
            const filePath = path.join(process.cwd(), "data", "records.json");
            const raw = fs.readFileSync(filePath, "utf8");
            cachedRecords = JSON.parse(raw);
        } catch (e) {
            console.error("Could not load data/records.json:", e);
            cachedRecords = [];
        }
    }
    return cachedRecords;
}

// 1. Instant Autocomplete Suggestions (~2ms)
function getSuggestions(query, limit = 5) {
    const records = getRecords();
    const qLower = query.toLowerCase().trim();
    const seen = new Set();
    const suggestions = [];

    // Priority 1: Title starts with query
    for (const r of records) {
        const title = (r.title || "").trim();
        const titleLower = title.toLowerCase();
        if (titleLower.startsWith(qLower) && !seen.has(titleLower)) {
            seen.add(titleLower);
            suggestions.push({
                title: title,
                content_type: r.content_type || "record",
                url: r.url || null
            });
            if (suggestions.length >= limit) return suggestions;
        }
    }

    // Priority 2: Word inside title starts with query
    for (const r of records) {
        const title = (r.title || "").trim();
        const titleLower = title.toLowerCase();
        const words = titleLower.split(/\s+/);
        if (words.some(w => w.startsWith(qLower)) && !seen.has(titleLower)) {
            seen.add(titleLower);
            suggestions.push({
                title: title,
                content_type: r.content_type || "record",
                url: r.url || null
            });
            if (suggestions.length >= limit) return suggestions;
        }
    }

    return suggestions;
}

// 2. High-Accuracy Relevance Search with Full Pagination (~18ms)
function performSearch(query, limit = 20, offset = 0) {
    const records = getRecords();
    const qLower = query.toLowerCase().trim();
    const tokens = qLower.split(/\s+/).filter(Boolean);
    if (!tokens.length) return { totalMatches: 0, hits: [] };

    const scored = [];

    for (const r of records) {
        const title = (r.title || "").toLowerCase();
        const agency = (r.agency_name || "").toLowerCase();
        const summary = (r.summary || "").toLowerCase();

        let score = 0;

        // Exact phrase bonus in title
        if (title.includes(qLower)) {
            score += 50;
        }
        // Prefix match in title
        if (title.startsWith(qLower)) {
            score += 25;
        }

        // Token match scoring
        let tokenMatches = 0;
        for (const t of tokens) {
            if (title.includes(t)) {
                score += 15;
                tokenMatches++;
            } else if (agency.includes(t)) {
                score += 8;
                tokenMatches++;
            } else if (summary.includes(t)) {
                score += 3;
                tokenMatches++;
            }
        }

        // All tokens present bonus for multi-word queries
        if (tokens.length > 1 && tokenMatches === tokens.length) {
            score += 20;
        }

        if (score > 0) {
            scored.push({
                id: r.id,
                title: r.title || "Untitled record",
                summary: r.summary || "",
                content: r.content || "",
                url: r.url || null,
                agency_name: r.agency_name || null,
                content_type: r.content_type || "record",
                slug: r.slug || "",
                _rankingScore: Math.min(0.99, Number((0.50 + (score / 150)).toFixed(2)))
            });
        }
    }

    // Sort by highest score first
    scored.sort((a, b) => b._rankingScore - a._rankingScore);

    const totalMatches = scored.length;
    const paginatedHits = scored.slice(offset, offset + limit);

    return { totalMatches, hits: paginatedHits };
}

export default async function handler(req, res) {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");

    if (req.method === "OPTIONS") {
        return res.status(200).end();
    }

    const { q = "", limit = "20", offset = "0", mode = "search" } = req.query;
    const cleaned = (q || "").trim();

    if (!cleaned || !/[a-zA-Z0-9]/.test(cleaned)) {
        return res.status(200).json({ query: cleaned, totalHits: 0, hits: [] });
    }

    // Mode: Instant Suggestions (~2ms)
    if (mode === "suggest") {
        const suggestions = getSuggestions(cleaned, 5);
        return res.status(200).json({
            query: cleaned,
            totalHits: suggestions.length,
            hits: suggestions
        });
    }

    // Mode: Full Search with True Pagination (~18ms)
    const parsedLimit = parseInt(limit || "20", 10);
    const parsedOffset = parseInt(offset || "0", 10);
    const result = performSearch(cleaned, parsedLimit, parsedOffset);

    return res.status(200).json({
        query: cleaned,
        totalHits: result.totalMatches,
        hits: result.hits
    });
}
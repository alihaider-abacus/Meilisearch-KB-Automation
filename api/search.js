// api/search.js - Unified Production Search Engine: Gemini + Pinecone Vector Search with In-Memory Keyword Fallback
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

// 1. Fast-Path Autocomplete Suggestions (~2ms in-memory scan)
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

// 2. High-Accuracy In-Memory Keyword Search Engine with True Pagination (~18ms)
function performKeywordSearch(query, limit = 20, offset = 0) {
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

        // Exact phrase match bonus in title
        if (title.includes(qLower)) {
            score += 50;
        }
        // Prefix match bonus in title
        if (title.startsWith(qLower)) {
            score += 25;
        }

        // Token match scoring across title, agency, and summary
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

        // Multi-token completeness bonus
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

    // Sort by highest relevance score first
    scored.sort((a, b) => b._rankingScore - a._rankingScore);

    const totalMatches = scored.length;
    const paginatedHits = scored.slice(offset, offset + limit);

    return { totalMatches, hits: paginatedHits };
}

// 3. Vector Search Engine via Google Gemini 3,072-dim Embeddings + Pinecone Serverless
async function performVectorSearch(query, limit = 20, offset = 0) {
    const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
    const PINECONE_API_KEY = process.env.PINECONE_API_KEY;
    const PINECONE_HOST = process.env.PINECONE_HOST;

    if (!GEMINI_API_KEY || !PINECONE_API_KEY || !PINECONE_HOST) {
        throw new Error("Missing vector search environment variables (GEMINI_API_KEY, PINECONE_API_KEY, or PINECONE_HOST).");
    }

    // A. Generate 3072-dimensional embedding using Google Gemini (4-second safety timeout)
    const geminiUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key=${GEMINI_API_KEY}`;
    const geminiRes = await fetch(geminiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            model: "models/gemini-embedding-001",
            content: { parts: [{ text: query }] },
            outputDimensionality: 3072
        }),
        signal: AbortSignal.timeout(4000)
    });

    if (!geminiRes.ok) {
        const errText = await geminiRes.text();
        throw new Error(`Gemini API error (${geminiRes.status}): ${errText}`);
    }

    const geminiData = await geminiRes.json();
    const queryVector = geminiData.embedding?.values;
    if (!queryVector || !queryVector.length) {
        throw new Error("Gemini returned empty embedding vector.");
    }

    // B. Query Pinecone Serverless Database (Fetch enough matches to support requested pagination)
    const topK = Math.min(200, Math.max(100, offset + limit));
    const pineconeUrl = `${PINECONE_HOST.replace(/\/$/, "")}/query`;
    const pineconeRes = await fetch(pineconeUrl, {
        method: "POST",
        headers: {
            "Api-Key": PINECONE_API_KEY,
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            vector: queryVector,
            topK: topK,
            includeMetadata: true,
            includeValues: false
        }),
        signal: AbortSignal.timeout(4000)
    });

    if (!pineconeRes.ok) {
        const errText = await pineconeRes.text();
        throw new Error(`Pinecone API error (${pineconeRes.status}): ${errText}`);
    }

    const pineconeData = await pineconeRes.json();
    const matches = pineconeData.matches || [];

    // Filter relevant matches above cosine threshold
    const threshold = 0.40;
    const filteredMatches = matches.filter(m => (m.score || 0) >= threshold);

    if (!filteredMatches.length) {
        return null; // Triggers fallback to keyword search
    }

    const hits = filteredMatches.map(m => {
        const meta = m.metadata || {};
        return {
            id: m.id,
            title: meta.title || "Untitled record",
            summary: meta.summary || "",
            content: meta.content || "",
            url: meta.url || null,
            agency_name: meta.agency_name || null,
            content_type: meta.content_type || "record",
            slug: meta.slug || "",
            _rankingScore: Number((m.score || 0).toFixed(2))
        };
    });

    const totalMatches = hits.length;
    const paginatedHits = hits.slice(offset, offset + limit);

    return { totalMatches, hits: paginatedHits };
}

// 4. Main Vercel Serverless Function Handler
export default async function handler(req, res) {
    // Enable Cross-Origin Resource Sharing (CORS)
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

    // Mode: Instant Autocomplete Suggestions (~2ms fast-path in memory)
    if (mode === "suggest") {
        const suggestions = getSuggestions(cleaned, 5);
        return res.status(200).json({
            query: cleaned,
            totalHits: suggestions.length,
            hits: suggestions
        });
    }

    const parsedLimit = parseInt(limit || "20", 10);
    const parsedOffset = parseInt(offset || "0", 10);

    // Mode: Search
    // Step 1: Attempt Gemini 3,072-dim + Pinecone Vector Search
    try {
        const vectorResult = await performVectorSearch(cleaned, parsedLimit, parsedOffset);
        if (vectorResult && vectorResult.hits && vectorResult.hits.length > 0) {
            return res.status(200).json({
                query: cleaned,
                totalHits: vectorResult.totalMatches,
                hits: vectorResult.hits,
                engine: "vector"
            });
        }
    } catch (vectorError) {
        console.warn("Vector search unavailable, falling back to keyword search:", vectorError.message);
    }

    // Step 2: Seamless Fallback to High-Accuracy In-Memory Keyword Search
    try {
        const keywordResult = performKeywordSearch(cleaned, parsedLimit, parsedOffset);
        return res.status(200).json({
            query: cleaned,
            totalHits: keywordResult.totalMatches,
            hits: keywordResult.hits,
            engine: "keyword"
        });
    } catch (keywordError) {
        console.error("Keyword search error:", keywordError);
        return res.status(500).json({ error: "Search failed", details: keywordError.message });
    }
}


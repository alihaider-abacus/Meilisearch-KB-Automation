// api/search.js - Vercel Serverless Backend API with Automatic Keyword Fallback
import fs from "fs";
import path from "path";

let cachedRecords = null;

// Load and cache records in memory
function getRecords() {
    if (!cachedRecords) {
        try {
            const filePath = path.join(process.cwd(), "data", "records.json");
            const raw = fs.readFileSync(filePath, "utf8");
            cachedRecords = JSON.parse(raw);
        } catch (e) {
            console.error("Could not load fallback records file:", e);
            cachedRecords = [];
        }
    }
    return cachedRecords;
}

// In-Memory Keyword Search Fallback (BM25-style priority scoring)
function keywordFallbackSearch(query, limit = 20, mode = "search") {
    const records = getRecords();
    const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) return [];

    const scored = [];
    for (const r of records) {
        const title = (r.title || "").toLowerCase();
        const summary = (r.summary || "").toLowerCase();
        const agency = (r.agency_name || "").toLowerCase();

        let score = 0;
        for (const t of tokens) {
            if (title.includes(t)) {
                score += 10;
                if (title.startsWith(t)) score += 5; // Prefix bonus
            } else if (agency.includes(t)) {
                score += 7;
            } else if (summary.includes(t)) {
                score += 3;
            }
        }

        if (score > 0) {
            scored.push({
                id: r.id,
                title: r.title || "Untitled",
                summary: r.summary || "",
                content: r.content || "",
                url: r.url || null,
                agency_name: r.agency_name || null,
                content_type: r.content_type || "record",
                slug: r.slug || "",
                _rankingScore: Math.min(0.99, 0.50 + (score / 35))
            });
        }
    }

    // Sort highest relevance first
    scored.sort((a, b) => b._rankingScore - a._rankingScore);
    return scored.slice(0, mode === "suggest" ? 5 : limit);
}

export default async function handler(req, res) {
    // Enable CORS
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");

    if (req.method === "OPTIONS") {
        return res.status(200).end();
    }

    const { q = "", limit = "20", mode = "search" } = req.query;
    const cleaned = (q || "").trim();

    if (!cleaned || !/[a-zA-Z0-9]/.test(cleaned)) {
        return res.status(200).json({ query: cleaned, totalHits: 0, hits: [] });
    }

    const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
    const PINECONE_API_KEY = process.env.PINECONE_API_KEY;
    const PINECONE_HOST = process.env.PINECONE_HOST;

    let hits = [];
    let searchType = "semantic";

    // ============================================================
    // TRY 1: PRIMARY SEMANTIC VECTOR SEARCH (GEMINI + PINECONE)
    // ============================================================
    try {
        if (!GEMINI_API_KEY || !PINECONE_API_KEY || !PINECONE_HOST) {
            throw new Error("Missing external credentials, using fallback");
        }

        // 1. Generate 3072-dimensional vector embedding with Gemini
        const geminiUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key=${GEMINI_API_KEY}`;
        const geminiRes = await fetch(geminiUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                model: "models/gemini-embedding-001",
                content: { parts: [{ text: cleaned }] },
                outputDimensionality: 3072
            })
        });

        if (!geminiRes.ok) {
            throw new Error(`Gemini embedding failed with HTTP status ${geminiRes.status}`);
        }

        const geminiData = await geminiRes.json();
        const queryVector = geminiData.embedding.values;

        // 2. Query Pinecone Serverless Index
        const pineconeUrl = `${PINECONE_HOST}/query`;
        const pineconeRes = await fetch(pineconeUrl, {
            method: "POST",
            headers: {
                "Api-Key": PINECONE_API_KEY,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                vector: queryVector,
                topK: mode === "suggest" ? 5 : parseInt(limit, 10),
                includeMetadata: true,
                includeValues: false
            })
        });

        if (!pineconeRes.ok) {
            throw new Error(`Pinecone query failed with HTTP status ${pineconeRes.status}`);
        }

        const pineconeData = await pineconeRes.json();
        const matches = pineconeData.matches || [];
        const threshold = mode === "suggest" ? 0.45 : 0.50;

        hits = matches
            .filter(m => (m.score || 0) >= threshold)
            .map(m => {
                const meta = m.metadata || {};
                return {
                    id: m.id,
                    title: meta.title || "Untitled",
                    summary: meta.summary || "",
                    content: meta.content || "",
                    url: meta.url || null,
                    agency_name: meta.agency_name || null,
                    content_type: meta.content_type || "record",
                    slug: meta.slug || "",
                    _rankingScore: m.score
                };
            });

    } catch (err) {
        // ============================================================
        // TRY 2: AUTOMATIC IN-MEMORY KEYWORD FALLBACK
        // ============================================================
        console.warn("Semantic vector search unavailable, switching to keyword search:", err.message);
        searchType = "keyword_fallback";
        hits = keywordFallbackSearch(cleaned, parseInt(limit, 10), mode);
    }

    return res.status(200).json({
        query: cleaned,
        searchType: searchType,
        totalHits: hits.length,
        hits: hits
    });
}
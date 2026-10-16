// api/search.js - Unified Production Search Engine: Meilisearch-Compatible Engine with Vector Integration
import fs from "fs";
import path from "path";

let cachedRecords = null;

// Stop words to prevent conversational question noise
const STOP_WORDS = new Set([
    "a", "about", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "i", "in", "is", "it", "my", "of", "on", "or", "that", "the",
    "this", "to", "was", "what", "when", "where", "who", "will", "with", "do"
]);

// 1. Fast Levenshtein distance for Meilisearch-standard typo tolerance
function levenshtein(a, b) {
    if (a === b) return 0;
    if (Math.abs(a.length - b.length) > 2) return 99;
    const row = [];
    for (let i = 0; i <= b.length; i++) row[i] = i;

    for (let i = 1; i <= a.length; i++) {
        let prev = i;
        for (let j = 1; j <= b.length; j++) {
            const val = a[i - 1] === b[j - 1] ? row[j - 1] : Math.min(row[j - 1] + 1, prev + 1, row[j] + 1);
            row[j - 1] = prev;
            prev = val;
        }
        row[b.length] = prev;
    }
    return row[b.length];
}

function maxAllowedTypos(tokenLen) {
    if (tokenLen < 5) return 0;
    if (tokenLen <= 8) return 1;
    return 2;
}

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

// 2. Autocomplete Suggestions with Typo Tolerance (~2ms)
function getSuggestions(query, limit = 5) {
    const records = getRecords();
    const cleanQ = (query || "").toLowerCase().replace(/[^a-zA-Z0-9\s]/g, " ").trim();
    if (!cleanQ) return [];

    const allTokens = cleanQ.split(/\s+/).filter(Boolean);
    const sigTokens = allTokens.filter(t => !STOP_WORDS.has(t));
    const tokens = sigTokens.length ? sigTokens : allTokens;
    if (!tokens.length) return [];

    const scored = [];
    const seen = new Set();

    for (const r of records) {
        const title = (r.title || "").trim();
        if (!title) continue;
        const titleLower = title.toLowerCase();
        if (seen.has(titleLower)) continue;

        const words = titleLower.replace(/[^a-zA-Z0-9\s]/g, " ").split(/\s+/).filter(Boolean);
        let score = 0;

        if (titleLower.startsWith(cleanQ)) {
            score += 120;
        } else if (titleLower.includes(cleanQ)) {
            score += 70;
        }

        let tokenMatches = 0;
        for (const t of tokens) {
            if (words.some(w => w.startsWith(t))) {
                tokenMatches++;
                score += 30;
            } else if (titleLower.includes(t)) {
                tokenMatches++;
                score += 15;
            } else {
                const mt = maxAllowedTypos(t.length);
                if (mt > 0 && words.some(w => Math.abs(w.length - t.length) <= mt && levenshtein(t, w) <= mt)) {
                    tokenMatches++;
                    score += 20;
                }
            }
        }

        if (tokenMatches > 0) {
            score += Math.max(0, 25 - words.length);
            seen.add(titleLower);
            scored.push({
                score,
                item: {
                    title: title,
                    content_type: r.content_type || "record",
                    url: r.url || null
                }
            });
        }
    }

    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, limit).map(s => s.item);
}

// 3. Meilisearch-Compatible Keyword Engine (Multi-Word Matching + Full Content Scanning + 0.82 Threshold)
function performKeywordSearch(query, limit = 20, offset = 0, threshold = 0.82) {
    const records = getRecords();
    const cleanQ = (query || "").toLowerCase().replace(/[^a-zA-Z0-9\s]/g, " ").trim();
    const allTokens = cleanQ.split(/\s+/).filter(Boolean);
    if (!allTokens.length) return { totalMatches: 0, hits: [] };

    const sigTokens = allTokens.filter(t => !STOP_WORDS.has(t));
    const tokens = sigTokens.length ? sigTokens : allTokens;

    const scored = [];

    for (const r of records) {
        const title = (r.title || "").toLowerCase();
        const agency = (r.agency_name || "").toLowerCase();
        const summary = (r.summary || "").toLowerCase();
        const content = (r.content || "").toLowerCase();
        const titleWords = title.replace(/[^a-zA-Z0-9\s]/g, " ").split(/\s+/).filter(Boolean);

        let score = 0;

        // Exact phrase bonus in title
        if (cleanQ.length > 2 && title.startsWith(cleanQ)) {
            score += 50;
        } else if (cleanQ.length > 2 && title.includes(cleanQ)) {
            score += 35;
        }

        // Token match scoring across Title, Agency, Summary, and Full-Body Content + Typo Tolerance
        let tokenMatches = 0;
        for (const t of tokens) {
            if (title.includes(t)) {
                score += 25;
                tokenMatches++;
            } else if (titleWords.some(w => w.startsWith(t))) {
                score += 20;
                tokenMatches++;
            } else if (summary.includes(t)) {
                score += 15;
                tokenMatches++;
            } else if (agency.includes(t)) {
                score += 12;
                tokenMatches++;
            } else if (content.includes(t)) {
                score += 8;
                tokenMatches++;
            } else {
                // Typo check (Levenshtein)
                const mt = maxAllowedTypos(t.length);
                if (mt > 0) {
                    for (const w of titleWords) {
                        if (Math.abs(w.length - t.length) <= mt && levenshtein(t, w) <= mt) {
                            score += 18;
                            tokenMatches++;
                            break;
                        }
                    }
                }
            }
        }

        // Meilisearch Standard: For multi-word queries, ALL words must match
        if (tokens.length > 1 && tokenMatches < tokens.length) {
            continue; // Discard records that only match 1 word out of a multi-word search
        }

        if (tokens.length > 1 && tokenMatches >= tokens.length) {
            score += 25;
        }

        if (tokenMatches > 0) {
            // Normalized to Meilisearch ranking score range (0.82 - 0.99)
            const rankingScore = Math.min(0.99, Number((0.80 + (score / 150)).toFixed(2)));

            if (rankingScore >= threshold) {
                scored.push({
                    id: r.id,
                    title: r.title || "Untitled record",
                    summary: r.summary || "",
                    url: r.url || null,
                    agency_name: r.agency_name || null,
                    content_type: r.content_type || "record",
                    slug: r.slug || "",
                    _rankingScore: rankingScore,
                    rawScore: score
                });
            }
        }
    }

    // Sort by rankingScore first, then rawScore tie-breaker
    scored.sort((a, b) => (b._rankingScore - a._rankingScore) || (b.rawScore - a.rawScore));

    const totalMatches = scored.length;
    const paginatedHits = scored.slice(offset, offset + limit);

    return { totalMatches, hits: paginatedHits };
}

// 4. Vector Search Engine (Gemini + Pinecone Serverless)
async function performVectorSearch(query, limit = 20, offset = 0) {
    const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
    const PINECONE_API_KEY = process.env.PINECONE_API_KEY;
    const PINECONE_HOST = process.env.PINECONE_HOST;

    if (!GEMINI_API_KEY || !PINECONE_API_KEY || !PINECONE_HOST) {
        throw new Error("Missing vector search configuration.");
    }

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

    const topK = Math.min(1000, Math.max(100, offset + limit + 20));
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
    const matches = (pineconeData.matches || []).filter(m => (m.score || 0) >= 0.40);

    if (!matches.length) return null;

    const hits = matches.map(m => {
        const meta = m.metadata || {};
        return {
            id: m.id,
            title: meta.title || "Untitled record",
            summary: meta.summary || "",
            url: meta.url || null,
            agency_name: meta.agency_name || null,
            content_type: meta.content_type || "record",
            slug: meta.slug || "",
            _rankingScore: Number((m.score || 0).toFixed(2))
        };
    });

    return { totalMatches: hits.length, hits: hits.slice(offset, offset + limit) };
}

// 5. Main Handler
export default async function handler(req, res) {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");

    if (req.method === "OPTIONS") return res.status(200).end();

    const { q = "", limit = "20", offset = "0", mode = "search" } = req.query;
    const cleaned = (q || "").trim();

    if (!cleaned || !/[a-zA-Z0-9]/.test(cleaned)) {
        return res.status(200).json({ query: cleaned, totalHits: 0, hits: [] });
    }

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
        console.warn("[Search] Vector search unavailable, falling back to keyword search:", vectorError.message);
    }

    try {
        const keywordResult = performKeywordSearch(cleaned, parsedLimit, parsedOffset, 0.82);
        return res.status(200).json({
            query: cleaned,
            totalHits: keywordResult.totalMatches,
            hits: keywordResult.hits,
            engine: "keyword"
        });
    } catch (keywordError) {
        return res.status(500).json({ error: "Search failed", details: keywordError.message });
    }
}
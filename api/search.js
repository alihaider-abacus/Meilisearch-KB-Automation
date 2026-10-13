// api/search.js - Vercel Serverless Backend API
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

    if (!GEMINI_API_KEY || !PINECONE_API_KEY || !PINECONE_HOST) {
        return res.status(500).json({ error: "Missing backend configuration environment variables." });
    }

    try {
        // 1. Generate 3072-dimensional vector embedding using Google Gemini
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
            const errText = await geminiRes.text();
            return res.status(geminiRes.status).json({ error: "Gemini embedding error", details: errText });
        }

        const geminiData = await geminiRes.json();
        const queryVector = geminiData.embedding.values;

        // 2. Query Pinecone Serverless Database
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
            const errText = await pineconeRes.text();
            return res.status(pineconeRes.status).json({ error: "Pinecone query error", details: errText });
        }

        const pineconeData = await pineconeRes.json();
        const matches = pineconeData.matches || [];

        // Threshold filter to eliminate irrelevant noise
        const threshold = mode === "suggest" ? 0.45 : 0.50;
        const filteredMatches = matches.filter(m => (m.score || 0) >= threshold);

        const hits = filteredMatches.map(m => {
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

        return res.status(200).json({
            query: cleaned,
            totalHits: hits.length,
            hits: hits
        });
    } catch (error) {
        return res.status(500).json({ error: error.message });
    }
}

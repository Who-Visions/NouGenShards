/**
 * NouGenTube MCP Cloudflare Worker (v4.0.0)
 *
 * Synthesizes:
 * 1. MCP Streamable HTTP (2026-07-28, 2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05)
 * 2. Top 0.001% Branded Sign-In Portal (GlifWebSignIn + Material 3 GIS + Nano Banana WebP + TwicPics zero-CLS/LQIP)
 * 3. Keymaker NVIDIA NIM Agent Suite (tube_ask_nvidia: gemma-4-31b-it, nemotron-3.5, kimi-k3.1-pro, mistral-large-4)
 * 4. TwicPics Responsive Media Engine (tube_media_twic + /media/:videoId?twic=v1/...)
 * 5. mattwright324/youtube-metadata OSINT Inspector (tube_metadata_osint: tags, safe links, cadence, Filmot/Wayback)
 * 6. mattwright324/youtube-comment-suite + MichaelBelgium/Youtube-API (tube_search_and_comments: search, comments, streams)
 * 7. Elijas/auto-youtube-subscription-playlist-2 + sam5epi0l/BotTuber + youtube/api-samples (tube_playlist_and_pack)
 * 8. NouGenTube Rolling-Caption Dedupe + Full-Length Recursive-512 Shard Ingest + FTS5-Safe Direct Node MCP Bridge
 */

export const PROTOCOL_VERSIONS = [
  "2026-07-28",
  "2025-11-25",
  "2025-06-18",
  "2025-03-26",
  "2024-11-05",
];

export const SERVER_INFO = { name: "nougen-tube-mcp", version: "5.0.0" };

export const NVIDIA_AGENT_MODELS = [
  "google/gemma-4-31b-it",
  "nvidia/nemotron-3.5-super-vl-120b-a12b",
  "nvidia/nemotron-3.5-lightning-30b-a3b",
  "nvidia/nemotron-3.5-bolt-e4b",
  "nvidia/nemotron-3-ultra-550b-a55b",
  "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
  "moonshotai/kimi-k3.1-pro",
  "mistralai/mistral-large-4-1t-a52b",
];

const DEFAULT_NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions";

export const GCP_OAUTH_PROJECTS = {
  "gen-lang-client-0939852539": {
    name: "NouGenAi",
    project_number: "69017097813",
    client_id: "69017097813-nsh02551klut5u5g51rotgp96344bu76.apps.googleusercontent.com",
  },
  "nougeneye-auth": {
    name: "nougeneye-auth",
    project_number: "2411928281",
    client_id: "2411928281-vhkbm1c6stf9vuf6qkekagcdjmd3dttv.apps.googleusercontent.com",
  },
  "project-c76da12d-f33f-4525-b1f": {
    name: "NouGen Google OAuth",
    project_number: "77682837973",
    client_id: "77682837973-numsl3crmvgk77ibe3gn740edh5jgjlg.apps.googleusercontent.com",
  },
  "nougen-ai": { name: "Nougen-ai", project_number: "388257044309" },
  "who-fleet": { name: "Who-Fleet", project_number: "721408007081" },
  "mineral-subject-487519-v6": { name: "Whovisions Fleet", project_number: "885670388176" },
};

export const CONNECTOR_LANE_MAP = {
  "claude.ai": "claude-app",
  "claude.com": "claude-app",
  "chatgpt.com": "chatgpt-app",
  "openai.com": "chatgpt-app",
  "meta.ai": "meta-app",
  "l.meta.ai": "meta-app",
  "facebook.com": "meta-app",
  "gemini.google.com": "gemini-app",
  "perplexity.ai": "perplexity-app",
  "grok.com": "grok-app",
  "x.ai": "grok-app",
  "copilot.microsoft.com": "copilot-app",
  "mistral.ai": "mistral-app",
  "notion.so": "notion-app",
  "notion.com": "notion-app",
};

export const CONNECTOR_CLIENT_MAP = {
  "claude-code": "claude-code",
  "claude": "claude-app",
  "meta": "meta-app",
  "chatgpt": "chatgpt-app",
  "openai": "responses-api",
  "codex": "codex",
  "antigravity": "antigravity",
  "cursor": "cursor",
};

// Nano Banana 160x160 WebP Emblem (NouGen Shades of Blue crystalline play-prism)
export const EMBLEM_WEBP_B64 = "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";

const verifiedTokenCache = new Map();
const transcriptMemCache = new Map();
const previewMemCache = new Map();

const MAX_OUTPUT_CHARS = 25000;
const DEFAULT_MAX_SHARD_CHARS = 30000;
const DEFAULT_SPLIT_OVERLAP = 2000;
const DEFAULT_EXTRACT_CHARS = 2000;
const ROLLING_OVERLAP_MIN = 10;
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;

export const TOOLS = [
  {
    name: "tube_preview",
    title: "NouGenTube Video Preview",
    description:
      "Preview a YouTube video (extract video ID, fetch oEmbed + Innertube metadata, publish date, chapters, and caption track availability) without writing shards.",
    annotations: {
      title: "NouGenTube Video Preview",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        url: { type: "string", description: "YouTube video URL or 11-character video ID." },
      },
      required: ["url"],
    },
    outputSchema: {
      type: "object",
      properties: {
        video_id: { type: "string" },
        url: { type: "string" },
        title: { type: ["string", "null"] },
        author: { type: ["string", "null"] },
        author_url: { type: ["string", "null"] },
        published: { type: ["string", "null"] },
        length_seconds: { type: ["number", "null"] },
        chapters: { type: "array" },
        caption_tracks: { type: "array" },
      },
      required: ["video_id", "url", "caption_tracks"],
    },
  },
  {
    name: "tube_transcript",
    title: "NouGenTube Rolling-Deduped Transcript",
    description:
      "Fetch YouTube video captions via multi-client Innertube API, apply 4-pattern rolling-caption deduplication (eliminating ~66% auto-caption repeat bloat), and return clean prose or timestamped cues plus duplication telemetry.",
    annotations: {
      title: "NouGenTube Rolling-Deduped Transcript",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        url: { type: "string", description: "YouTube video URL or 11-character video ID." },
        lang: { type: "string", description: "Preferred caption language code (default: en).", default: "en" },
        timestamps: {
          type: "boolean",
          description: "Include [MM:SS] timestamps on each deduplicated cue (default: false).",
          default: false,
        },
      },
      required: ["url"],
    },
    outputSchema: {
      type: "object",
      properties: {
        video_id: { type: "string" },
        title: { type: ["string", "null"] },
        author: { type: ["string", "null"] },
        published: { type: ["string", "null"] },
        language: { type: "string" },
        kind: { type: "string" },
        raw_cues: { type: "integer" },
        deduped_cues: { type: "integer" },
        duplication_ratio: { type: "number" },
        chars: { type: "integer" },
        transcript: { type: "string" },
      },
      required: [
        "video_id",
        "language",
        "raw_cues",
        "deduped_cues",
        "duplication_ratio",
        "chars",
        "transcript",
      ],
    },
  },
  {
    name: "tube_dedupe_check",
    title: "NouGenTube Exact-ID Dedupe Gate",
    description:
      "Check whether the NouGen shard grid already holds an exact video ID tag (tube:<video_id>) without semantic false positives.",
    annotations: {
      title: "NouGenTube Exact-ID Dedupe Gate",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        url: { type: "string", description: "YouTube video URL or 11-character video ID." },
      },
      required: ["url"],
    },
    outputSchema: {
      type: "object",
      properties: {
        video_id: { type: "string" },
        tag: { type: "string" },
        exists: { type: "boolean" },
        matches: { type: "integer" },
      },
      required: ["video_id", "tag", "exists", "matches"],
    },
  },
  {
    name: "tube_search_shards",
    title: "NouGenTube Shard Search",
    description: "Search existing NouGenTube shards in the NouGen memory grid.",
    annotations: {
      title: "NouGenTube Shard Search",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        query: { type: "string", description: "Search query for captured YouTube transcript shards." },
        limit: { type: "integer", description: "Maximum number of results (default: 5, max: 25).", default: 5 },
      },
      required: ["query"],
    },
    outputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        limit: { type: "integer" },
        results: { type: "array" },
      },
      required: ["query", "limit", "results"],
    },
  },
  {
    name: "tube_ask_nvidia",
    title: "NouGenTube NVIDIA NIM Video Agent",
    description:
      "Analyze, summarize, or query a YouTube video (or prompt) using Keymaker-backed NVIDIA NIM frontier agents (google/gemma-4-31b-it, nvidia/nemotron-3.5-super-vl-120b-a12b, nemotron-3.5-lightning-30b-a3b, kimi-k3.1-pro, mistral-large-4).",
    annotations: {
      title: "NouGenTube NVIDIA NIM Video Agent",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        url: { type: "string", description: "Optional YouTube video URL or 11-char ID." },
        prompt: {
          type: "string",
          description: "Question or instruction for the NVIDIA agent.",
          default: "Summarize the key technical takeaways and timestamps.",
        },
        model: {
          type: "string",
          description: "NVIDIA NIM model ID (default: google/gemma-4-31b-it).",
          default: "google/gemma-4-31b-it",
        },
        lang: { type: "string", default: "en" },
      },
      required: [],
    },
    outputSchema: {
      type: "object",
      properties: {
        model: { type: "string" },
        video_id: { type: ["string", "null"] },
        title: { type: ["string", "null"] },
        answer: { type: "string" },
        available_models: { type: "array" },
      },
      required: ["model", "answer", "available_models"],
    },
  },
  {
    name: "tube_media_twic",
    title: "NouGenTube TwicPics Responsive Media & LQIP Engine",
    description:
      "Generate TwicPics-style context-aware responsive thumbnail URLs (?twic=v1/...), DPR 1x/2x/3x srcsets, SVG/WebP Low-Quality Image Placeholders (LQIP), and zero-CLS <picture> HTML.",
    annotations: {
      title: "NouGenTube TwicPics Responsive Media & LQIP Engine",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        url: { type: "string", description: "YouTube video URL or 11-char ID." },
        ratio: { type: "string", description: "Intrinsic aspect ratio (default: 16/9).", default: "16/9" },
        focus: { type: "string", description: "Focal point strategy (default: auto).", default: "auto" },
        output: { type: "string", description: "Target format (webp, jpeg, lqip).", default: "webp" },
      },
      required: ["url"],
    },
    outputSchema: {
      type: "object",
      properties: {
        video_id: { type: "string" },
        ratio: { type: "string" },
        twic_url: { type: "string" },
        lqip_data_uri: { type: "string" },
        srcset_webp: { type: "string" },
        srcset_jpeg: { type: "string" },
        variants: { type: "object" },
        zero_cls_html: { type: "string" },
      },
      required: ["video_id", "twic_url", "lqip_data_uri", "srcset_webp", "zero_cls_html"],
    },
  },
  {
    name: "tube_metadata_osint",
    title: "NouGenTube Deep Metadata & OSINT Inspector",
    description:
      "Deep YouTube metadata & OSINT inspector (mattwright324/youtube-metadata): extracts tags, safe unlinked description URLs + domain frequency, upload UTC cadence, geodata, thumbnails, and Archive.org / Filmot / SocialBlade / YouTube Geofind links.",
    annotations: {
      title: "NouGenTube Deep Metadata & OSINT Inspector",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        url: { type: "string", description: "YouTube video URL or 11-character video ID." },
      },
      required: ["url"],
    },
    outputSchema: {
      type: "object",
      properties: {
        video_id: { type: "string" },
        title: { type: ["string", "null"] },
        author: { type: ["string", "null"] },
        channel_id: { type: ["string", "null"] },
        published: { type: ["string", "null"] },
        upload_cadence: { type: "object" },
        view_count: { type: ["number", "null"] },
        length_seconds: { type: ["number", "null"] },
        category: { type: ["string", "null"] },
        is_unlisted: { type: "boolean" },
        is_family_safe: { type: "boolean" },
        is_live: { type: "boolean" },
        tags: { type: "array" },
        description_links: { type: "array" },
        link_domains: { type: "object" },
        chapters: { type: "array" },
        osint_investigate: { type: "object" },
      },
      required: ["video_id", "tags", "description_links", "osint_investigate"],
    },
  },
  {
    name: "tube_search_and_comments",
    title: "NouGenTube Comment Suite & Stream Matrix",
    description:
      "Search YouTube videos by keyword, extract/filter video comments (mattwright324/youtube-comment-suite), or inspect audio/video adaptive stream formats (MichaelBelgium/Youtube-API).",
    annotations: {
      title: "NouGenTube Comment Suite & Stream Matrix",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        url: { type: "string", description: "YouTube video URL or 11-char ID (for comments and stream formats)." },
        search_query: { type: "string", description: "Keyword query to search YouTube videos or filter comments." },
        limit: { type: "integer", description: "Max items to return (default: 10).", default: 10 },
      },
      required: [],
    },
    outputSchema: {
      type: "object",
      properties: {
        video_id: { type: ["string", "null"] },
        search_results: { type: "array" },
        comments: { type: "array" },
        adaptive_streams: { type: "array" },
      },
      required: ["search_results", "comments", "adaptive_streams"],
    },
  },
  {
    name: "tube_playlist_and_pack",
    title: "NouGenTube Subscription Feed & BotTuber Packager",
    description:
      "Fetch & filter channel/playlist uploads via zero-quota XML feed (Elijas/auto-youtube-subscription-playlist-2: published_after, max_age_days, skip_shorts) and generate BotTuber + youtube/api-samples videos.insert compilation packages.",
    annotations: {
      title: "NouGenTube Subscription Feed & BotTuber Packager",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        channel_id: { type: "string", description: "YouTube channel ID (UC...)." },
        playlist_id: { type: "string", description: "YouTube playlist ID (PL...)." },
        video_urls: {
          type: "array",
          items: { type: "string" },
          description: "Optional list of video URLs/IDs to bundle into a BotTuber compilation package.",
        },
        max_age_days: { type: "number", description: "Filter out videos older than N days." },
        skip_shorts_url_check: {
          type: "boolean",
          description: "Filter out entries marked as #shorts (default: false).",
          default: false,
        },
      },
      required: [],
    },
    outputSchema: {
      type: "object",
      properties: {
        feed_source: { type: ["string", "null"] },
        entries_count: { type: "integer" },
        entries: { type: "array" },
        bottuber_package: { type: "object" },
      },
      required: ["entries_count", "entries", "bottuber_package"],
    },
  },
  {
    name: "tube_analytics_and_trends",
    title: "NouGenTube Data Analytics, Trend & Channelify Inspector",
    description:
      "Compute video engagement velocity (views/day, views/hour), tag/title trend signals, and Channelify/OpenTube/PHPVibe embeddable CMS metadata (DannyIbo/youtube-data-analytics-tools, SMAPPNYU/youtube-data-api, Sajadapp/Youtube-Trend-Analyzer, aculix/Channelify, jnsougata/opentube, PHPVibe/phpvibe-lite).",
    annotations: {
      title: "NouGenTube Data Analytics, Trend & Channelify Inspector",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        url: { type: "string", description: "YouTube video URL or 11-character video ID." },
      },
      required: ["url"],
    },
    outputSchema: {
      type: "object",
      properties: {
        video_id: { type: "string" },
        title: { type: ["string", "null"] },
        channel: { type: "object" },
        analytics: { type: "object" },
        trend_signals: { type: "object" },
        cms_embed: { type: "object" },
      },
      required: ["video_id", "channel", "analytics", "trend_signals", "cms_embed"],
    },
  },
  {
    name: "tube_live_streaming",
    title: "NouGenTube Live Streaming & Broadcast Controller",
    description:
      "Inspect live/upcoming broadcast state (HLS/DASH manifests, start/end timestamps) and generate YouTube Live Streaming API liveBroadcasts.insert + liveStreams.insert + RTMPS payloads (SKrotkih/YTLiveStreaming, youtube/api-samples).",
    annotations: {
      title: "NouGenTube Live Streaming & Broadcast Controller",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        url: { type: "string", description: "Optional YouTube live video URL or 11-char ID to inspect." },
        broadcast_title: { type: "string", description: "Title for a new liveBroadcasts.insert template." },
        scheduled_start_iso: { type: "string", description: "ISO 8601 start time for scheduled broadcast." },
        resolution: { type: "string", description: "Stream resolution (1080p, 1440p, 2160p).", default: "1080p" },
        frame_rate: { type: "string", description: "Stream frame rate (30fps, 60fps).", default: "60fps" },
      },
      required: [],
    },
    outputSchema: {
      type: "object",
      properties: {
        video_id: { type: ["string", "null"] },
        live_status: { type: "object" },
        yt_live_streaming_api_templates: { type: "object" },
      },
      required: ["live_status", "yt_live_streaming_api_templates"],
    },
  },
  {
    name: "tube_ingest",
    title: "NouGenTube Era-Stamped Shard Ingest",
    description:
      "Fetch a YouTube video's metadata and full-length rolling-deduped transcript, split via Recursive-512 with standalone provenance headers, check exact-ID dedupe (tube:<id>), and capture era-stamped shards into the NouGen grid.",
    annotations: {
      title: "NouGenTube Era-Stamped Shard Ingest",
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        url: { type: "string", description: "YouTube video URL or 11-character video ID." },
        lang: { type: "string", description: "Preferred caption language code (default: en).", default: "en" },
        dry_run: {
          type: "boolean",
          description: "If true, distill and return shard payloads without writing to the grid.",
          default: false,
        },
        force: {
          type: "boolean",
          description: "If true, bypass the exact-ID dedupe gate and re-ingest.",
          default: false,
        },
      },
      required: ["url"],
    },
    outputSchema: {
      type: "object",
      properties: {
        video_id: { type: "string" },
        dry_run: { type: "boolean" },
        skipped_duplicate: { type: "boolean" },
        parts_count: { type: "integer" },
        duplication_ratio: { type: "number" },
        tags: { type: "array" },
        shards: { type: "array" },
      },
      required: ["video_id", "dry_run", "skipped_duplicate", "parts_count", "tags"],
    },
  },
];

function escHtml(s) {
  return String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function jsonResponse(body, status = 200, extraHeaders = {}) {
  return new Response(body === null ? null : JSON.stringify(body, null, 2), {
    status,
    headers: {
      ...(body === null ? {} : { "content-type": "application/json; charset=utf-8" }),
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, POST, OPTIONS",
      "access-control-allow-headers":
        "content-type, authorization, mcp-session-id, mcp-protocol-version, mcp-method, mcp-name",
      "access-control-expose-headers": "mcp-session-id, mcp-protocol-version, www-authenticate",
      ...extraHeaders,
    },
  });
}

function rpcOk(id, result, extraHeaders = {}) {
  return jsonResponse({ jsonrpc: "2.0", id: id ?? null, result }, 200, extraHeaders);
}

function rpcErr(id, code, message, status = 200, data = undefined, extraHeaders = {}) {
  const error = data !== undefined ? { code, message, data } : { code, message };
  return jsonResponse({ jsonrpc: "2.0", id: id ?? null, error }, status, extraHeaders);
}

export function extractVideoId(input) {
  const raw = String(input || "").trim();
  if (/^[A-Za-z0-9_-]{11}$/.test(raw)) return raw;
  try {
    const u = new URL(raw);
    const host = u.hostname.toLowerCase();
    if (host === "l.meta.ai" || host === "meta.ai") {
      const inner = u.searchParams.get("u");
      if (inner) return extractVideoId(inner);
    }
    if (host === "youtu.be" || host === "www.youtu.be") {
      const id = u.pathname.replace(/^\/+/, "").split("/")[0];
      if (/^[A-Za-z0-9_-]{11}$/.test(id)) return id;
    }
    const v = u.searchParams.get("v");
    if (v && /^[A-Za-z0-9_-]{11}$/.test(v)) return v;
    const parts = u.pathname.split("/").filter(Boolean);
    for (const marker of ["shorts", "embed", "live", "v"]) {
      const idx = parts.indexOf(marker);
      if (idx !== -1 && parts[idx + 1] && /^[A-Za-z0-9_-]{11}$/.test(parts[idx + 1])) {
        return parts[idx + 1];
      }
    }
  } catch {
    // fall through
  }
  return null;
}

/**
 * Single-pass HTML entity decoder (eliminates CodeQL js/double-escaping).
 */
export function decodeHtmlEntities(str) {
  const entities = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
  };
  return String(str || "").replace(
    /&(?:amp|lt|gt|quot|#39|apos|#(\d+)|#x([0-9a-fA-F]+));/g,
    (full, dec, hex) => {
      if (dec !== undefined) return String.fromCharCode(Number(dec));
      if (hex !== undefined) return String.fromCharCode(parseInt(hex, 16));
      return entities[full] ?? full;
    }
  );
}

/**
 * Character-by-character tag stripper (eliminates CodeQL js/incomplete-multi-character-sanitization).
 */
export function stripHtmlTags(input) {
  const s = String(input || "");
  let out = "";
  let inTag = false;
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === "<") {
      inTag = true;
      out += " ";
    } else if (ch === ">") {
      inTag = false;
      out += " ";
    } else if (!inTag) {
      out += ch;
    }
  }
  return out;
}

export function parseTimedTextCues(xml) {
  const cues = [];
  const textRe = /<text\b([^>]*)>([\s\S]*?)<\/text>/g;
  let m;
  while ((m = textRe.exec(xml)) !== null) {
    const attrs = m[1] || "";
    const startMatch = /\bstart="([\d.]+)"/.exec(attrs);
    const durMatch = /\bdur="([\d.]+)"/.exec(attrs);
    const t_start = startMatch ? parseFloat(startMatch[1]) : 0;
    const dur = durMatch ? parseFloat(durMatch[1]) : 0;
    const t_end = t_start + dur;
    const clean = decodeHtmlEntities(stripHtmlTags(m[2]))
      .replace(/\s+/g, " ")
      .trim();
    if (clean) cues.push({ t_start, t_end, text: clean });
  }
  if (cues.length) return cues;

  const pRe = /<p\b([^>]*)>([\s\S]*?)<\/p>/g;
  while ((m = pRe.exec(xml)) !== null) {
    const attrs = m[1] || "";
    const tMatch = /\bt="(\d+)"/.exec(attrs);
    const dMatch = /\bd="(\d+)"/.exec(attrs);
    const t_start = tMatch ? parseInt(tMatch[1], 10) / 1000 : 0;
    const dur = dMatch ? parseInt(dMatch[1], 10) / 1000 : 0;
    const t_end = t_start + dur;
    const clean = decodeHtmlEntities(stripHtmlTags(m[2]))
      .replace(/\s+/g, " ")
      .trim();
    if (clean) cues.push({ t_start, t_end, text: clean });
  }
  return cues;
}

const VTT_TS_RX =
  /(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?/;

function tsToSeconds(h, m, s, ms) {
  return (
    (h ? parseInt(h, 10) : 0) * 3600 +
    parseInt(m, 10) * 60 +
    parseInt(s, 10) +
    (ms ? parseInt(ms.padEnd(3, "0").slice(0, 3), 10) / 1000 : 0)
  );
}

export function parseVttCues(vtt) {
  const cues = [];
  const lines = String(vtt || "").split(/\r?\n/);
  let i = 0;
  while (i < lines.length) {
    const match = VTT_TS_RX.exec(lines[i]);
    if (!match) {
      i++;
      continue;
    }
    const t_start = tsToSeconds(match[1], match[2], match[3], match[4]);
    const t_end = tsToSeconds(match[5], match[6], match[7], match[8]);
    i++;
    const body = [];
    while (i < lines.length && lines[i].trim() !== "") {
      const stripped = decodeHtmlEntities(stripHtmlTags(lines[i])).trim();
      if (stripped) body.push(stripped);
      i++;
    }
    const joined = body.join(" ").replace(/\s+/g, " ").trim();
    if (joined) cues.push({ t_start, t_end, text: joined });
  }
  return cues;
}

export function parseJson3Cues(json3) {
  const obj = typeof json3 === "string" ? JSON.parse(json3) : json3;
  const events = obj?.events || [];
  const cues = [];
  for (const ev of events) {
    if (!Array.isArray(ev.segs)) continue;
    const text = ev.segs
      .map((s) => s?.utf8 || "")
      .join("")
      .replace(/\s+/g, " ")
      .trim();
    if (!text) continue;
    const t_start = (ev.tStartMs || 0) / 1000;
    const t_end = t_start + (ev.dDurationMs || 0) / 1000;
    cues.push({ t_start, t_end, text });
  }
  return cues;
}

export function dedupeCues(cues) {
  const out = [];
  for (const cue of cues) {
    if (!out.length) {
      out.push({ ...cue });
      continue;
    }
    const prev = out[out.length - 1];
    if (prev.text === cue.text) {
      prev.t_end = Math.max(prev.t_end, cue.t_end);
      continue;
    }
    if (cue.text.length > prev.text.length && cue.text.startsWith(prev.text)) {
      prev.t_end = cue.t_end;
      prev.text = cue.text;
      continue;
    }
    if (prev.text.endsWith(cue.text)) {
      prev.t_end = Math.max(prev.t_end, cue.t_end);
      continue;
    }
    let overlap = 0;
    const maxCheck = Math.min(prev.text.length, cue.text.length);
    for (let size = maxCheck; size >= ROLLING_OVERLAP_MIN; size--) {
      if (prev.text.slice(-size) === cue.text.slice(0, size)) {
        overlap = size;
        break;
      }
    }
    if (overlap > 0) {
      const tail = cue.text.slice(overlap).trimStart();
      if (tail) out.push({ t_start: cue.t_start, t_end: cue.t_end, text: tail });
      else prev.t_end = Math.max(prev.t_end, cue.t_end);
      continue;
    }
    out.push({ ...cue });
  }
  return out;
}

export function computeDuplicationRatio(rawCues, deduped) {
  const naiveLen = rawCues.map((c) => c.text).join(" ").length;
  if (!naiveLen) return 0.0;
  const cleanLen = deduped.map((c) => c.text).join(" ").length;
  return Number(Math.max(0, 1 - cleanLen / naiveLen).toFixed(4));
}

export function formatCueTimestamp(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `[${String(m).padStart(2, "0")}:${String(rem).padStart(2, "0")}]`;
}

export function parseTimedTextXml(xml) {
  const rawCues = parseTimedTextCues(xml);
  const deduped = dedupeCues(rawCues);
  return deduped.map((c) => c.text).join("\n");
}

export function recursiveSplit(text, maxSize = DEFAULT_MAX_SHARD_CHARS, overlap = DEFAULT_SPLIT_OVERLAP) {
  if (text.length <= maxSize) return [text];
  const sep = ["\n\n", "\n", ". ", " "].find((s) => text.includes(s)) ?? "";
  const splits = sep ? text.split(sep) : Array.from(text);
  const chunks = [];
  let current = "";
  for (const piece of splits) {
    if (current.length + piece.length + sep.length > maxSize) {
      if (current) chunks.push(current.trim());
      const tail = current.slice(Math.max(0, current.length - overlap));
      current = tail ? tail + sep + piece : piece;
    } else {
      current = current ? current + sep + piece : piece;
    }
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

function fmtDuration(seconds) {
  const n = parseInt(seconds, 10);
  if (Number.isNaN(n) || n < 0) return "unknown";
  return `${Math.floor(n / 60)}m${String(n % 60).padStart(2, "0")}s`;
}

export function distillShards(meta, url, transcript, tier = "innertube-rolling-dedupe") {
  const videoId = extractVideoId(url) || url;
  const title = meta?.title || `YouTube video ${videoId}`;
  const head = [
    `# ${meta?.title || "(title unknown)"}`,
    `Creator: ${meta?.author || "(channel unknown)"}`,
    `URL: ${url}`,
    `Published: ${meta?.published || "unknown"}`,
    `Duration: ${fmtDuration(meta?.length_seconds)}`,
    `Transcript source: ${tier || "none"}`,
    "Provenance: third-party content (YouTube captions), verbatim preserved.",
  ].join("\n");

  if (!transcript) {
    return [
      {
        title: `${title} — NouGenTube capture [no-transcript]`,
        content:
          head +
          "\n\n## First-Pass Extract\nNo transcript obtainable from any fetch tier; metadata-only stub so the id is on record.",
      },
    ];
  }

  const chapters = meta?.chapters || [];
  let extract;
  if (chapters.length) {
    const lines = ["Declared chapters:"];
    for (const ch of chapters) {
      const stamp = typeof ch.start_time === "number" ? `${formatCueTimestamp(ch.start_time)} ` : "";
      lines.push(`- ${stamp}${ch.title || "(untitled)"}`);
    }
    extract = lines.join("\n");
  } else {
    extract = "Transcript lead (no declared chapters):\n" + transcript.slice(0, DEFAULT_EXTRACT_CHARS);
  }

  const verbatimIntro = "## Raw Capture (Verbatim)\n";
  const single = `${head}\n\n## First-Pass Extract\n${extract}\n\n${verbatimIntro}${transcript}`;
  if (single.length <= DEFAULT_MAX_SHARD_CHARS) {
    return [{ title: `${title} — NouGenTube capture`, content: single }];
  }

  const trimmedExtract = extract.slice(0, Math.max(0, Math.floor(DEFAULT_MAX_SHARD_CHARS / 2) - head.length));
  const budget = Math.max(
    DEFAULT_MAX_SHARD_CHARS - head.length - verbatimIntro.length - trimmedExtract.length - 400,
    Math.floor(DEFAULT_MAX_SHARD_CHARS / 4)
  );
  const parts = recursiveSplit(transcript, budget, Math.min(DEFAULT_SPLIT_OVERLAP, Math.floor(budget / 4)));
  return parts.map((chunk, idx) => {
    const i = idx + 1;
    const body = [head, ""];
    if (i === 1) body.push("## First-Pass Extract", trimmedExtract, "");
    body.push(`${verbatimIntro}(part ${i}/${parts.length})`, chunk);
    return {
      title: `${title} — NouGenTube capture (part ${i}/${parts.length})`,
      content: body.join("\n"),
    };
  });
}

async function fetchOembed(videoId, fetchFn) {
  const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;
  const url = `https://www.youtube.com/oembed?url=${encodeURIComponent(watchUrl)}&format=json`;
  const resp = await fetchFn(url, { headers: { "user-agent": "NouGenTube-MCP/4.0" } });
  if (!resp.ok) return null;
  return await resp.json();
}

function extractCookies(resp) {
  const cookies = [];
  if (typeof resp?.headers?.getSetCookie === "function") {
    for (const c of resp.headers.getSetCookie()) {
      const pair = c.split(";")[0]?.trim();
      if (pair) cookies.push(pair);
    }
  } else {
    const raw = resp?.headers?.get?.("set-cookie");
    if (raw) {
      for (const part of raw.split(/,(?=\s*[A-Za-z0-9_-]+=)/)) {
        const pair = part.split(";")[0]?.trim();
        if (pair) cookies.push(pair);
      }
    }
  }
  return cookies.join("; ");
}

function extractBalancedJson(text, marker) {
  const idx = text.indexOf(marker);
  if (idx === -1) return null;
  const start = text.indexOf("{", idx + marker.length);
  if (start === -1) return null;
  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === '"') inStr = false;
    } else {
      if (ch === '"') inStr = true;
      else if (ch === "{") depth++;
      else if (ch === "}") {
        depth--;
        if (depth === 0) {
          try {
            return JSON.parse(text.slice(start, i + 1));
          } catch {
            return null;
          }
        }
      }
    }
  }
  return null;
}

async function fetchInnertubeCandidates(videoId, fetchFn) {
  const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;
  const webHeaders = {
    "user-agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "accept-language": "en-US,en;q=0.9",
    cookie: "CONSENT=YES+1",
  };

  let apiKey = null;
  let sessionCookie = "CONSENT=YES+1";
  let webPlayer = null;
  let watchHtml = "";

  try {
    let htmlResp = await fetchFn(watchUrl, { headers: webHeaders });
    if (htmlResp.ok) {
      const setCookies = extractCookies(htmlResp);
      if (setCookies) sessionCookie = `${sessionCookie}; ${setCookies}`;
      watchHtml = await htmlResp.text();
      if (watchHtml.includes('action="https://consent.youtube.com/s"')) {
        const vMatch = /name="v" value="(.*?)"/.exec(watchHtml);
        if (vMatch) {
          sessionCookie = `CONSENT=YES+${vMatch[1]}`;
          htmlResp = await fetchFn(watchUrl, {
            headers: { ...webHeaders, cookie: sessionCookie },
          });
          if (htmlResp.ok) watchHtml = await htmlResp.text();
        }
      }
      const keyMatch = /"INNERTUBE_API_KEY":\s*"([a-zA-Z0-9_-]+)"/.exec(watchHtml);
      if (keyMatch) apiKey = keyMatch[1];
      webPlayer = extractBalancedJson(watchHtml, "ytInitialPlayerResponse");
    }
  } catch {
    // proceed to direct player call
  }

  const playerUrl = apiKey
    ? `https://www.youtube.com/youtubei/v1/player?key=${apiKey}&prettyPrint=false`
    : "https://www.youtube.com/youtubei/v1/player?prettyPrint=false";

  const clients = [
    { clientName: "ANDROID", clientVersion: "20.10.38" },
    { clientName: "IOS", clientVersion: "20.10.4", deviceMake: "Apple", deviceModel: "iPhone16,2" },
    { clientName: "WEB", clientVersion: "2.20250312.04.00" },
  ];

  const cleanCandidates = [];
  const xpeCandidates = [];

  for (const client of clients) {
    try {
      const resp = await fetchFn(playerUrl, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "accept-language": "en-US,en;q=0.9",
          cookie: sessionCookie,
        },
        body: JSON.stringify({
          context: { client: { ...client, hl: "en", gl: "US" } },
          videoId,
        }),
      });
      if (!resp.ok) continue;
      const data = await resp.json();
      if (!data.microformat && webPlayer?.microformat) {
        data.microformat = webPlayer.microformat;
      }
      const tracks = data?.captions?.playerCaptionsTracklistRenderer?.captionTracks;
      if (Array.isArray(tracks) && tracks.length > 0) {
        const hasXpe = tracks.every((t) => String(t.baseUrl || "").includes("exp=xpe"));
        if (hasXpe) xpeCandidates.push(data);
        else cleanCandidates.push(data);
        if (cleanCandidates.length >= 1) break;
      } else if (data?.videoDetails && !webPlayer) {
        webPlayer = data;
      }
    } catch {
      // try next client
    }
  }

  if (webPlayer) {
    const wTracks = webPlayer?.captions?.playerCaptionsTracklistRenderer?.captionTracks;
    if (Array.isArray(wTracks) && wTracks.length > 0) {
      xpeCandidates.push(webPlayer);
    }
  }

  return {
    candidates: [...cleanCandidates, ...xpeCandidates],
    fallbackPlayer: cleanCandidates[0] || xpeCandidates[0] || webPlayer || null,
    sessionCookie,
    apiKey,
    watchHtml,
  };
}

function extractPublishedIso(player) {
  const mf = player?.microformat?.playerMicroformatRenderer;
  const raw = mf?.publishDate || mf?.uploadDate || null;
  if (!raw) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return `${raw}T00:00:00Z`;
  return raw;
}

function extractChaptersFromDescription(desc) {
  if (!desc) return [];
  const chapters = [];
  const lines = String(desc).split(/\r?\n/);
  const rx = /(?:^|\s)(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s+[-–—:]?\s*(.+)$/;
  for (const line of lines) {
    const m = rx.exec(line.trim());
    if (m) {
      const start = (m[1] ? parseInt(m[1], 10) * 3600 : 0) + parseInt(m[2], 10) * 60 + parseInt(m[3], 10);
      const title = m[4].trim();
      if (title) chapters.push({ start_time: start, title });
    }
  }
  return chapters;
}

async function handleTubePreview(args, fetchFn) {
  const videoId = extractVideoId(args?.url);
  if (!videoId) throw new Error("Could not extract a valid 11-char YouTube video ID.");

  const cached = previewMemCache.get(videoId);
  if (cached && cached.exp > Date.now() && cached.data.caption_tracks?.length > 0) {
    return cached.data;
  }

  const [oembed, innertube] = await Promise.all([
    fetchOembed(videoId, fetchFn).catch(() => null),
    fetchInnertubeCandidates(videoId, fetchFn).catch(() => ({ candidates: [], fallbackPlayer: null })),
  ]);
  const player = innertube.fallbackPlayer;
  const tracks =
    player?.captions?.playerCaptionsTracklistRenderer?.captionTracks?.map((t) => ({
      languageCode: t.languageCode,
      name: t.name?.simpleText || t.name?.runs?.[0]?.text || t.languageCode,
      kind: t.kind || "standard",
    })) || [];

  const result = {
    video_id: videoId,
    url: `https://www.youtube.com/watch?v=${videoId}`,
    title: oembed?.title || player?.videoDetails?.title || null,
    author: oembed?.author_name || player?.videoDetails?.author || null,
    author_url: oembed?.author_url || null,
    published: extractPublishedIso(player),
    length_seconds: player?.videoDetails?.lengthSeconds ? Number(player.videoDetails.lengthSeconds) : null,
    chapters: extractChaptersFromDescription(player?.videoDetails?.shortDescription),
    caption_tracks: tracks,
  };

  if (tracks.length > 0) {
    previewMemCache.set(videoId, { exp: Date.now() + CACHE_TTL_MS, data: result });
  }
  return result;
}

function parseAnyCaptionBody(rawBody) {
  const trimmed = String(rawBody || "").trimStart();
  if (!trimmed) return [];
  if (trimmed.startsWith("WEBVTT")) return parseVttCues(trimmed);
  if (trimmed.startsWith("{")) {
    try {
      return parseJson3Cues(trimmed);
    } catch {
      return [];
    }
  }
  return parseTimedTextCues(trimmed);
}

/**
 * Fetch and deduplicate video transcript.
 * When options.truncate === false (used by handleTubeIngest), returns the full-length
 * transcript so distillShards can split >30,000-char transcripts via recursiveSplit.
 */
async function handleTubeTranscript(args, fetchFn, options = { truncate: true }) {
  const videoId = extractVideoId(args?.url);
  if (!videoId) throw new Error("Could not extract a valid 11-char YouTube video ID.");
  const lang = String(args?.lang || "en").trim() || "en";
  const includeTimestamps = Boolean(args?.timestamps);
  const shouldTruncate = options?.truncate !== false;
  const cacheKey = `${videoId}:${lang}:${includeTimestamps ? 1 : 0}`;

  let fullResult = null;
  const memHit = transcriptMemCache.get(cacheKey);
  if (memHit && memHit.exp > Date.now()) {
    fullResult = memHit.data;
  }

  const edgeCache = typeof caches !== "undefined" && caches?.default ? caches.default : null;
  const edgeCacheUrl = `https://cache.internal/transcript/${encodeURIComponent(cacheKey)}`;
  if (!fullResult && edgeCache) {
    try {
      const hit = await edgeCache.match(edgeCacheUrl);
      if (hit) {
        fullResult = await hit.json();
        transcriptMemCache.set(cacheKey, { exp: Date.now() + CACHE_TTL_MS, data: fullResult });
      }
    } catch {
      // ignore cache read error
    }
  }

  if (!fullResult) {
    const { candidates, sessionCookie } = await fetchInnertubeCandidates(videoId, fetchFn);
    if (!candidates.length) {
      throw new Error(`No caption tracks available for video ${videoId}.`);
    }

    for (const player of candidates) {
      const tracks = player?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
      if (!tracks.length) continue;

      const chosen =
        tracks.find((t) => t.languageCode === lang && t.kind !== "asr") ||
        tracks.find((t) => t.languageCode === lang) ||
        tracks.find((t) => t.languageCode?.startsWith(lang.split("-")[0])) ||
        tracks[0];

      const urlsToTry = [
        String(chosen.baseUrl || "").replace(/&fmt=srv3\b/g, ""),
        `${String(chosen.baseUrl || "").replace(/&fmt=[^&]+/g, "")}&fmt=json3`,
        String(chosen.baseUrl || ""),
      ];

      for (const capUrl of urlsToTry) {
        if (!capUrl) continue;
        try {
          const capResp = await fetchFn(capUrl, {
            headers: {
              "user-agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
              "accept-language": "en-US,en;q=0.9",
              cookie: sessionCookie,
            },
          });
          if (!capResp.ok) continue;
          const rawBody = await capResp.text();
          const rawCues = parseAnyCaptionBody(rawBody);
          if (!rawCues.length) continue;

          const deduped = dedupeCues(rawCues);
          const duplication_ratio = computeDuplicationRatio(rawCues, deduped);
          const fullTranscript = includeTimestamps
            ? deduped.map((c) => `${formatCueTimestamp(c.t_start)} ${c.text}`).join("\n")
            : deduped.map((c) => c.text).join("\n");

          fullResult = {
            video_id: videoId,
            title: player?.videoDetails?.title || null,
            author: player?.videoDetails?.author || null,
            published: extractPublishedIso(player),
            length_seconds: player?.videoDetails?.lengthSeconds ? Number(player.videoDetails.lengthSeconds) : null,
            chapters: extractChaptersFromDescription(player?.videoDetails?.shortDescription),
            language: chosen.languageCode,
            kind: chosen.kind || "standard",
            raw_cues: rawCues.length,
            deduped_cues: deduped.length,
            duplication_ratio,
            chars: fullTranscript.length,
            transcript: fullTranscript,
          };
          break;
        } catch {
          // try next format
        }
      }
      if (fullResult) break;
    }

    if (!fullResult) {
      throw new Error(`No non-empty caption track could be retrieved for video ${videoId}.`);
    }

    transcriptMemCache.set(cacheKey, { exp: Date.now() + CACHE_TTL_MS, data: fullResult });
    if (edgeCache) {
      try {
        await edgeCache.put(
          edgeCacheUrl,
          new Response(JSON.stringify(fullResult), {
            headers: { "content-type": "application/json", "cache-control": "public, max-age=86400" },
          })
        );
      } catch {
        // ignore cache write error
      }
    }
  }

  if (shouldTruncate && fullResult.transcript.length > MAX_OUTPUT_CHARS) {
    const truncated = fullResult.transcript.slice(0, MAX_OUTPUT_CHARS) + "\n\n[truncated]";
    return { ...fullResult, chars: truncated.length, transcript: truncated };
  }
  return fullResult;
}

/**
 * TwicPics Responsive Media & LQIP Engine (https://www.twicpics.com/docs/getting-started/why-twicpics)
 */
export function buildTwicMediaBundle(videoId, origin, { ratio = "16/9", focus = "auto", output = "webp" } = {}) {
  const cleanRatio = String(ratio || "16/9").replace(":", "/");
  const variants = {
    maxres_webp: `https://i.ytimg.com/vi_webp/${videoId}/maxresdefault.webp`,
    sd_webp: `https://i.ytimg.com/vi_webp/${videoId}/sddefault.webp`,
    hq_webp: `https://i.ytimg.com/vi_webp/${videoId}/hqdefault.webp`,
    mq_webp: `https://i.ytimg.com/vi_webp/${videoId}/mqdefault.webp`,
    maxres_jpeg: `https://i.ytimg.com/vi/${videoId}/maxresdefault.jpg`,
    hq_jpeg: `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`,
    mq_jpeg: `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg`,
  };
  const srcset_webp = `${variants.mq_webp} 320w, ${variants.hq_webp} 480w, ${variants.sd_webp} 640w, ${variants.maxres_webp} 1280w`;
  const srcset_jpeg = `${variants.mq_jpeg} 320w, ${variants.hq_jpeg} 480w, ${variants.maxres_jpeg} 1280w`;
  const twic_url = `${origin}/media/${videoId}?twic=v1/cover=${encodeURIComponent(
    cleanRatio.replace("/", ":")
  )}/focus=${encodeURIComponent(focus)}/output=${encodeURIComponent(output)}`;

  const svgPlaceholder = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#03045e"/><stop offset="55%" stop-color="#0077b6"/><stop offset="100%" stop-color="#00b4d8"/></linearGradient></defs><rect width="16" height="9" fill="url(#g)"/></svg>`;
  const lqip_data_uri = `data:image/svg+xml;utf8,${encodeURIComponent(svgPlaceholder)}`;

  const zero_cls_html = [
    `<picture data-twic-src="video:${escHtml(videoId)}" data-twic-focus="${escHtml(focus)}">`,
    `  <source type="image/webp" srcset="${escHtml(srcset_webp)}" sizes="(max-width: 768px) 100vw, 720px">`,
    `  <img src="${escHtml(variants.hq_jpeg)}" srcset="${escHtml(srcset_jpeg)}" alt="YouTube thumbnail ${escHtml(
      videoId
    )}" width="1280" height="720" loading="lazy" decoding="async" style="width:100%;height:auto;aspect-ratio:${escHtml(
      cleanRatio
    )};background-image:url('${lqip_data_uri}');background-size:cover;">`,
    `</picture>`,
  ].join("\n");

  return {
    video_id: videoId,
    ratio: cleanRatio,
    twic_url,
    lqip_data_uri,
    srcset_webp,
    srcset_jpeg,
    variants,
    zero_cls_html,
  };
}

/**
 * mattwright324/youtube-metadata OSINT & Deep Metadata Inspector
 */
async function handleTubeMetadataOsint(args, origin, fetchFn) {
  const videoId = extractVideoId(args?.url);
  if (!videoId) throw new Error("Could not extract a valid 11-char YouTube video ID.");
  const [oembed, innertube] = await Promise.all([
    fetchOembed(videoId, fetchFn).catch(() => null),
    fetchInnertubeCandidates(videoId, fetchFn).catch(() => ({ fallbackPlayer: null })),
  ]);
  const player = innertube.fallbackPlayer || {};
  const vd = player.videoDetails || {};
  const mf = player.microformat?.playerMicroformatRenderer || {};
  const desc = String(vd.shortDescription || mf.description?.simpleText || "");

  // Extract links without hyperlinking by default + aggregate domains (mattwright324/youtube-metadata)
  const rawLinks = Array.from(new Set(desc.match(/https?:\/\/[^\s<>)"']+/g) || []));
  const link_domains = {};
  for (const link of rawLinks) {
    try {
      const h = new URL(link).hostname.toLowerCase();
      link_domains[h] = (link_domains[h] || 0) + 1;
    } catch {
      // ignore invalid URL
    }
  }

  const published = extractPublishedIso(player);
  let upload_cadence = { iso: published, day_of_week_utc: null, hour_utc: null };
  if (published) {
    const dt = new Date(published);
    if (!Number.isNaN(dt.getTime())) {
      const days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
      upload_cadence = {
        iso: published,
        day_of_week_utc: days[dt.getUTCDay()],
        hour_utc: dt.getUTCHours(),
      };
    }
  }

  const channelId = vd.channelId || mf.externalChannelId || null;
  const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;

  return {
    video_id: videoId,
    title: vd.title || oembed?.title || null,
    author: vd.author || oembed?.author_name || null,
    channel_id: channelId,
    published,
    upload_cadence,
    view_count: vd.viewCount ? Number(vd.viewCount) : null,
    length_seconds: vd.lengthSeconds ? Number(vd.lengthSeconds) : null,
    category: mf.category || null,
    is_unlisted: Boolean(mf.isUnlisted),
    is_family_safe: mf.isFamilySafe !== false,
    is_live: Boolean(vd.isLiveContent),
    available_countries_count: Array.isArray(mf.availableCountries) ? mf.availableCountries.length : null,
    tags: Array.isArray(vd.keywords) ? vd.keywords : [],
    description_links: rawLinks,
    link_domains,
    chapters: extractChaptersFromDescription(desc),
    thumbnails: buildTwicMediaBundle(videoId, origin).variants,
    osint_investigate: {
      wayback_machine: `https://web.archive.org/web/*/${watchUrl}`,
      filmot_archive: `https://filmot.com/video/${videoId}`,
      socialblade_channel: channelId ? `https://socialblade.com/youtube/channel/${channelId}` : null,
      youtube_geofind: `https://mattw.io/youtube-geofind/`,
      mw_metadata_viewer: `https://mattw.io/youtube-metadata/?url=${encodeURIComponent(watchUrl)}&submit=true`,
    },
  };
}

/**
 * JatinAgrawal0/youtube-comment-sentimental-analysis lexicon scorer
 */
export function scoreCommentSentiment(text) {
  const posWords = new Set([
    "great", "awesome", "amazing", "love", "excellent", "good", "best", "helpful",
    "fantastic", "brilliant", "clear", "thanks", "thank", "incredible", "perfect", "solid",
  ]);
  const negWords = new Set([
    "bad", "worst", "terrible", "awful", "hate", "useless", "broken", "wrong",
    "fake", "boring", "slow", "error", "fail", "failed", "disappointed", "annoying",
  ]);
  const tokens = String(text || "")
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
  let score = 0;
  for (const tok of tokens) {
    if (posWords.has(tok)) score += 1;
    else if (negWords.has(tok)) score -= 1;
  }
  const label = score > 0 ? "positive" : score < 0 ? "negative" : "neutral";
  return { score, label };
}

/**
 * mattwright324/youtube-comment-suite + JatinAgrawal0/youtube-comment-sentimental-analysis + MichaelBelgium/Youtube-API
 */
async function handleTubeSearchAndComments(args, fetchFn) {
  const limit = Math.max(1, Math.min(25, Number(args?.limit || 10)));
  const searchQuery = String(args?.search_query || "").trim();
  const videoId = args?.url ? extractVideoId(args.url) : null;

  let search_results = [];
  let comments = [];
  let adaptive_streams = [];

  if (searchQuery && !videoId) {
    try {
      const resp = await fetchFn("https://www.youtube.com/youtubei/v1/search?prettyPrint=false", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          context: { client: { clientName: "WEB", clientVersion: "2.20250312.04.00", hl: "en", gl: "US" } },
          query: searchQuery,
        }),
      });
      if (resp.ok) {
        const text = await resp.text();
        const vrRe = /"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})".*?"title":\{"runs":\[\{"text":"([^"]+)"/g;
        let m;
        const seen = new Set();
        while ((m = vrRe.exec(text)) !== null && search_results.length < limit) {
          if (!seen.has(m[1])) {
            seen.add(m[1]);
            search_results.push({
              video_id: m[1],
              url: `https://www.youtube.com/watch?v=${m[1]}`,
              title: m[2],
            });
          }
        }
      }
    } catch {
      // ignore search error
    }
  }

  if (videoId) {
    const innertube = await fetchInnertubeCandidates(videoId, fetchFn).catch(() => ({ fallbackPlayer: null }));
    const player = innertube.fallbackPlayer;
    const formats = player?.streamingData?.adaptiveFormats || [];
    adaptive_streams = formats.slice(0, limit).map((f) => ({
      itag: f.itag,
      mime_type: f.mimeType || null,
      bitrate: f.bitrate || null,
      quality_label: f.qualityLabel || f.audioQuality || null,
      audio_sample_rate: f.audioSampleRate || null,
      approx_duration_ms: f.approxDurationMs || null,
    }));

    try {
      const nextResp = await fetchFn("https://www.youtube.com/youtubei/v1/next?prettyPrint=false", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          context: { client: { clientName: "WEB", clientVersion: "2.20250312.04.00", hl: "en", gl: "US" } },
          videoId,
        }),
      });
      if (nextResp.ok) {
        const nextText = await nextResp.text();
        const tokMatch = /"continuationCommand":\{"token":"([^"]+)"/.exec(nextText);
        if (tokMatch) {
          const cResp = await fetchFn("https://www.youtube.com/youtubei/v1/next?prettyPrint=false", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              context: { client: { clientName: "WEB", clientVersion: "2.20250312.04.00", hl: "en", gl: "US" } },
              continuation: tokMatch[1],
            }),
          });
          if (cResp.ok) {
            const cText = await cResp.text();
            const cRe = /"contentText":\{"runs":\[(.*?)\]\}/g;
            let cm;
            while ((cm = cRe.exec(cText)) !== null && comments.length < limit) {
              const snippet = cm[1]
                .replace(/"text":"([^"]*)"/g, "$1")
                .replace(/[{},[\]":]/g, " ")
                .replace(/\s+/g, " ")
                .trim();
              if (snippet && (!searchQuery || snippet.toLowerCase().includes(searchQuery.toLowerCase()))) {
                const sentiment = scoreCommentSentiment(snippet);
                comments.push({ text: snippet, sentiment: sentiment.label, score: sentiment.score });
              }
            }
          }
        }
      }
    } catch {
      // ignore comments fetch error
    }
  }

  const posCount = comments.filter((c) => c.sentiment === "positive").length;
  const negCount = comments.filter((c) => c.sentiment === "negative").length;
  const neuCount = comments.length - posCount - negCount;

  return {
    video_id: videoId,
    search_results,
    comments,
    sentiment_summary: {
      total_scored: comments.length,
      positive: posCount,
      neutral: neuCount,
      negative: negCount,
      dominant_mood: posCount > negCount ? "positive" : negCount > posCount ? "negative" : "neutral",
    },
    adaptive_streams,
  };
}

/**
 * DannyIbo/youtube-data-analytics-tools + SMAPPNYU/youtube-data-api + Sajadapp/Youtube-Trend-Analyzer
 * + aculix/Channelify + jnsougata/opentube + PHPVibe/phpvibe-lite
 */
async function handleTubeAnalyticsAndTrends(args, origin, fetchFn) {
  const osint = await handleTubeMetadataOsint(args, origin, fetchFn);
  const views = Number(osint.view_count || 0);
  const durationSec = Number(osint.length_seconds || 0);
  const publishedMs = osint.published ? new Date(osint.published).getTime() : NaN;
  const ageDays = !Number.isNaN(publishedMs) ? Math.max(0.04, (Date.now() - publishedMs) / (1000 * 86400)) : null;
  const viewsPerDay = ageDays ? Math.round(views / ageDays) : null;
  const viewsPerHour = ageDays ? Math.round(views / (ageDays * 24)) : null;

  const titleStr = String(osint.title || "");
  const upperRatio = titleStr.length
    ? Number((titleStr.replace(/[^A-Z]/g, "").length / Math.max(1, titleStr.replace(/[^A-Za-z]/g, "").length)).toFixed(2))
    : 0;

  return {
    video_id: osint.video_id,
    title: osint.title,
    channel: {
      name: osint.author,
      channel_id: osint.channel_id,
      rss_feed_url: osint.channel_id
        ? `https://www.youtube.com/feeds/videos.xml?channel_id=${osint.channel_id}`
        : null,
      channelify_url: osint.channel_id ? `https://www.youtube.com/channel/${osint.channel_id}` : null,
    },
    analytics: {
      view_count: views,
      age_days: ageDays ? Number(ageDays.toFixed(2)) : null,
      views_per_day: viewsPerDay,
      views_per_hour: viewsPerHour,
      length_seconds: durationSec,
      format_bucket: durationSec > 0 && durationSec <= 60 ? "short" : durationSec <= 600 ? "standard" : "longform",
      tags_count: osint.tags.length,
      chapters_count: osint.chapters.length,
      outbound_links_count: osint.description_links.length,
    },
    trend_signals: {
      category: osint.category,
      uppercase_emphasis_ratio: upperRatio,
      has_exclamation_or_question: /[!?]/.test(titleStr),
      velocity_tier:
        viewsPerDay === null
          ? "unknown"
          : viewsPerDay >= 50000
          ? "viral"
          : viewsPerDay >= 5000
          ? "trending"
          : "steady",
      top_tags: osint.tags.slice(0, 10),
    },
    cms_embed: {
      embed_url: `https://www.youtube-nocookie.com/embed/${osint.video_id}`,
      iframe_html: `<iframe width="560" height="315" src="https://www.youtube-nocookie.com/embed/${escHtml(
        osint.video_id
      )}" title="${escHtml(osint.title || osint.video_id)}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen loading="lazy"></iframe>`,
      twic_media: buildTwicMediaBundle(osint.video_id, origin),
    },
  };
}

/**
 * SKrotkih/YTLiveStreaming + youtube/api-samples Live Broadcast & Stream Controller
 */
async function handleTubeLiveStreaming(args, fetchFn) {
  const videoId = args?.url ? extractVideoId(args.url) : null;
  let live_status = {
    inspected: Boolean(videoId),
    is_live_content: false,
    is_live_now: false,
    start_timestamp: null,
    end_timestamp: null,
    hls_manifest_url: null,
    dash_manifest_url: null,
  };

  if (videoId) {
    const innertube = await fetchInnertubeCandidates(videoId, fetchFn).catch(() => ({ fallbackPlayer: null }));
    const player = innertube.fallbackPlayer || {};
    const vd = player.videoDetails || {};
    const lbd = player.microformat?.playerMicroformatRenderer?.liveBroadcastDetails || {};
    const sd = player.streamingData || {};
    live_status = {
      inspected: true,
      title: vd.title || null,
      is_live_content: Boolean(vd.isLiveContent),
      is_live_now: Boolean(lbd.isLiveNow || vd.isLive),
      start_timestamp: lbd.startTimestamp || null,
      end_timestamp: lbd.endTimestamp || null,
      hls_manifest_url: sd.hlsManifestUrl || null,
      dash_manifest_url: sd.dashManifestUrl || null,
    };
  }

  const startIso = args?.scheduled_start_iso || new Date(Date.now() + 3600 * 1000).toISOString();
  const resolution = String(args?.resolution || "1080p");
  const frameRate = String(args?.frame_rate || "60fps");

  return {
    video_id: videoId,
    live_status,
    yt_live_streaming_api_templates: {
      liveBroadcasts_insert: {
        endpoint: "POST https://www.googleapis.com/youtube/v3/liveBroadcasts?part=snippet,status,contentDetails",
        body: {
          snippet: {
            title: args?.broadcast_title || "NouGenTube Live Broadcast",
            scheduledStartTime: startIso,
          },
          status: {
            privacyStatus: "private",
            selfDeclaredMadeForKids: false,
          },
          contentDetails: {
            enableAutoStart: true,
            enableAutoStop: true,
            enableDvr: true,
            latencyPreference: "ultraLow",
          },
        },
      },
      liveStreams_insert: {
        endpoint: "POST https://www.googleapis.com/youtube/v3/liveStreams?part=snippet,cdn,contentDetails",
        body: {
          snippet: { title: `${args?.broadcast_title || "NouGenTube"} Primary Ingestion Stream` },
          cdn: {
            frameRate,
            ingestionType: "rtmp",
            resolution,
          },
          contentDetails: { isReusable: true },
        },
      },
      rtmps_ingest_endpoint: "rtmps://a.rtmps.youtube.com/live2",
    },
  };
}

/**
 * Elijas/auto-youtube-subscription-playlist-2 + sam5epi0l/BotTuber + youtube/api-samples
 */
async function handleTubePlaylistAndPack(args, fetchFn) {
  const channelId = String(args?.channel_id || "").trim();
  const playlistId = String(args?.playlist_id || "").trim();
  const maxAgeDays = typeof args?.max_age_days === "number" ? args.max_age_days : null;
  const skipShorts = Boolean(args?.skip_shorts_url_check);

  let feedUrl = null;
  if (channelId) {
    feedUrl = `https://www.youtube.com/feeds/videos.xml?channel_id=${encodeURIComponent(channelId)}`;
  } else if (playlistId) {
    feedUrl = `https://www.youtube.com/feeds/videos.xml?playlist_id=${encodeURIComponent(playlistId)}`;
  }

  const entries = [];
  if (feedUrl) {
    const resp = await fetchFn(feedUrl, { headers: { "user-agent": "NouGenTube-MCP/4.0" } });
    if (resp.ok) {
      const xml = await resp.text();
      const entryRe = /<entry>([\s\S]*?)<\/entry>/g;
      let m;
      while ((m = entryRe.exec(xml)) !== null) {
        const block = m[1];
        const vid = (/<yt:videoId>([^<]+)<\/yt:videoId>/.exec(block) || [])[1] || "";
        const title = decodeHtmlEntities((/<title>([^<]+)<\/title>/.exec(block) || [])[1] || "");
        const author = decodeHtmlEntities((/<name>([^<]+)<\/name>/.exec(block) || [])[1] || "");
        const published = (/<published>([^<]+)<\/published>/.exec(block) || [])[1] || "";
        if (!vid) continue;
        if (skipShorts && /#shorts\b/i.test(title)) continue;
        if (maxAgeDays !== null && published) {
          const ageDays = (Date.now() - new Date(published).getTime()) / (1000 * 86400);
          if (ageDays > maxAgeDays) continue;
        }
        entries.push({
          video_id: vid,
          url: `https://www.youtube.com/watch?v=${vid}`,
          title,
          author,
          published,
        });
      }
    }
  }

  const inputUrls = Array.isArray(args?.video_urls) ? args.video_urls : entries.slice(0, 5).map((e) => e.url);
  const credits = [];
  const timestamps = [];
  let cursorSeconds = 0;

  for (let i = 0; i < inputUrls.length; i++) {
    const vid = extractVideoId(inputUrls[i]);
    if (!vid) continue;
    const matched = entries.find((e) => e.video_id === vid);
    const title = matched?.title || `Segment ${i + 1} (${vid})`;
    const author = matched?.author || "Creator";
    timestamps.push(`${formatCueTimestamp(cursorSeconds)} ${title}`);
    credits.push(`- ${author}: https://www.youtube.com/watch?v=${vid}`);
    cursorSeconds += 120;
  }

  const bottuber_package = {
    youtube_api_v3_videos_insert_body: {
      snippet: {
        title: entries[0]?.title ? `${entries[0].title} — Compilation & Highlights` : "NouGenTube Curated Compilation",
        description: [
          "Automated NouGenTube Compilation Package",
          "",
          "Chapters:",
          ...(timestamps.length ? timestamps : ["[00:00] Intro"]),
          "",
          "Credits:",
          ...(credits.length ? credits : ["- Original creators credited via NouGenTube"]),
        ].join("\n"),
        tags: ["NouGenTube", "Compilation", "Highlights"],
        categoryId: "28",
      },
      status: {
        privacyStatus: "private",
        selfDeclaredMadeForKids: false,
      },
    },
    timestamps,
    credits,
  };

  return {
    feed_source: feedUrl,
    entries_count: entries.length,
    entries,
    bottuber_package,
  };
}

function timingSafeEqual(a, b) {
  const sa = String(a || "");
  const sb = String(b || "");
  if (!sa || sa.length !== sb.length) return false;
  let diff = 0;
  for (let i = 0; i < sa.length; i++) diff |= sa.charCodeAt(i) ^ sb.charCodeAt(i);
  return diff === 0;
}

function decodeB64UrlJson(segment) {
  try {
    const pad = "=".repeat((4 - (segment.length % 4)) % 4);
    const b64 = segment.replace(/-/g, "+").replace(/_/g, "/") + pad;
    const raw = atob(b64);
    const bytes = Uint8Array.from(raw, (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return null;
  }
}

function encodeB64Url(bytes) {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = "";
  for (const b of arr) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function googleAllowedSet(env) {
  const raw = env?.GOOGLE_ALLOWED_EMAILS || "";
  return new Set(
    String(raw)
      .split(",")
      .map((e) => e.trim().toLowerCase())
      .filter(Boolean)
  );
}

export async function authenticateRequest(request, env, fetchFn = fetch) {
  const authHeader = request.headers.get("authorization") || "";
  const m = /^Bearer\s+(.+)$/i.exec(authHeader.trim());
  const token = m ? m[1].trim() : "";

  if (!token) {
    const requireAuth = env?.REQUIRE_AUTH === "true" || Boolean(env?.NOUGEN_TUBE_TOKEN);
    return requireAuth ? null : { key: "anonymous", lane: "public", oauth: false };
  }

  if (env?.NOUGEN_TUBE_TOKEN && timingSafeEqual(token, env.NOUGEN_TUBE_TOKEN)) {
    return { key: "fleet-key", lane: "fleet", oauth: false, token };
  }
  if (env?.FLEET_KEYS) {
    for (const entry of String(env.FLEET_KEYS).split(",")) {
      const idx = entry.indexOf(":");
      const name = idx > 0 ? entry.slice(0, idx).trim() : "fleet-key";
      const secret = idx > 0 ? entry.slice(idx + 1).trim() : entry.trim();
      if (secret && timingSafeEqual(token, secret)) {
        return { key: name, lane: name, oauth: false, token };
      }
    }
  }

  if (token.startsWith("v1.")) {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = decodeB64UrlJson(parts[1]);
    if (!payload || payload.typ !== "access") return null;
    if (typeof payload.exp !== "number" || payload.exp * 1000 < Date.now()) return null;
    const allowed = googleAllowedSet(env);
    if (String(payload.key || "").startsWith("g-") && allowed.size > 0) {
      const email = String(payload.eml || "").toLowerCase();
      if (!allowed.has(email)) return null;
    }

    const cachedExp = verifiedTokenCache.get(token);
    if (cachedExp && cachedExp > Date.now()) {
      return { key: payload.key, email: payload.eml || null, lane: payload.ln || "oauth", oauth: true, token };
    }

    const upstream = String(env?.OAUTH_UPSTREAM || "").replace(/\/+$/, "");
    if (upstream) {
      try {
        const verifyResp = await fetchFn(`${upstream}/mcp`, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ jsonrpc: "2.0", id: "auth-check", method: "ping" }),
        });
        if (verifyResp.ok) {
          verifiedTokenCache.set(token, Math.min(payload.exp * 1000, Date.now() + 5 * 60 * 1000));
          return { key: payload.key, email: payload.eml || null, lane: payload.ln || "oauth", oauth: true, token };
        }
      } catch {
        // upstream unreachable
      }
    }
  }

  return null;
}

async function callFleetShardMcp(toolName, toolArgs, env, fetchFn) {
  const ngsToken = env?.SHARD_GATEWAY_TOKEN || "";
  const gatewayBase = String(env?.WHOART_ORIGIN || env?.SHARD_GATEWAY_URL || "").replace(/\/+$/, "");
  const nodeToolName =
    toolName === "shards_search"
      ? "recall_memory"
      : toolName === "shards_capture"
      ? "capture_experience"
      : toolName;

  if (gatewayBase) {
    try {
      const nodeResp = await fetchFn(`${gatewayBase}/mcp/`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          accept: "application/json, text/event-stream",
          "user-agent": "NouGenTube-MCP/4.0",
          ...(ngsToken ? { "x-ngs-token": ngsToken } : {}),
        },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 1,
          method: "tools/call",
          params: { name: nodeToolName, arguments: toolArgs },
        }),
      });

      if (nodeResp.ok) {
        const rawText = await nodeResp.text();
        const jsonLine =
          rawText.startsWith("event:") || rawText.startsWith("data:")
            ? (rawText.split("\n").find((l) => l.startsWith("data:")) || "").slice(5).trim()
            : rawText;
        const payload = JSON.parse(jsonLine);
        if (payload?.result && !payload.result.isError) {
          if (payload.result.structuredContent) return payload.result.structuredContent;
          const items = (payload.result.content || [])
            .map((c) => {
              if (typeof c?.text !== "string") return null;
              try {
                return JSON.parse(c.text);
              } catch {
                return c.text;
              }
            })
            .filter(Boolean);
          return items.length === 1 && Array.isArray(items[0]) ? items[0] : items;
        }
      }
    } catch {
      // fall through to OAUTH_UPSTREAM / REST fallback
    }
  }

  const bearer = env?.NOUGEN_TUBE_TOKEN || ngsToken;
  const upstream = String(env?.OAUTH_UPSTREAM || "").replace(/\/+$/, "");
  const headers = {
    "content-type": "application/json",
    "user-agent": "NouGenTube-MCP/4.0",
    ...(bearer ? { authorization: `Bearer ${bearer}` } : {}),
  };

  if (upstream) {
    const mcpResp = await fetchFn(`${upstream}/mcp`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: `tube-${Date.now()}`,
        method: "tools/call",
        params: { name: toolName, arguments: toolArgs },
      }),
    });

    if (mcpResp.ok) {
      const payload = await mcpResp.json().catch(() => null);
      if (payload?.result && !payload.result.isError) {
        if (payload.result.structuredContent) return payload.result.structuredContent;
        const text = payload.result.content?.[0]?.text || "";
        try {
          return JSON.parse(text);
        } catch {
          return { raw_text: text };
        }
      }
    }
  }

  const base = gatewayBase || "https://gateway.example.invalid";
  const restPath = toolName === "shards_capture" ? "/v1/shards/capture" : "/v1/shards/search";
  const restResp = await fetchFn(`${base}${restPath}`, {
    method: "POST",
    headers,
    body: JSON.stringify(toolArgs),
  });
  if (!restResp.ok) {
    throw new Error(`Shard grid ${toolName} failed (${restResp.status}).`);
  }
  return await restResp.json();
}

async function handleTubeDedupeCheck(args, env, fetchFn) {
  const videoId = extractVideoId(args?.url);
  if (!videoId) throw new Error("Could not extract a valid 11-char YouTube video ID.");
  const marker = `tube:${videoId}`;
  const data = await callFleetShardMcp("shards_search", { query: `tube ${videoId}`, limit: 5 }, env, fetchFn);
  const blob = JSON.stringify(data || "");
  const hasMarker = blob.includes(marker) || blob.includes(videoId);
  const matches = hasMarker
    ? (blob.match(new RegExp(videoId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g")) || []).length
    : 0;
  return {
    video_id: videoId,
    tag: marker,
    exists: matches > 0,
    matches,
  };
}

async function handleTubeSearchShards(args, env, fetchFn) {
  const query = String(args?.query || "").trim();
  if (!query) throw new Error("query is required.");
  const limit = Math.max(1, Math.min(25, Number(args?.limit || 5)));
  const data = await callFleetShardMcp("shards_search", { query: `tube ${query}`, limit }, env, fetchFn);
  const results = Array.isArray(data)
    ? data
    : Array.isArray(data?.results)
    ? data.results
    : data?.raw_text
    ? [{ snippet: data.raw_text }]
    : [data];
  return { query, limit, results };
}

async function handleTubeAskNvidia(args, env, fetchFn) {
  const nvKey = env?.NVIDIA_API_KEY;
  if (!nvKey) {
    throw new Error("NVIDIA_API_KEY secret is not bound on nougen-tube-mcp.");
  }
  const nvUrl = env?.NVIDIA_BASE_URL || DEFAULT_NVIDIA_URL;
  const requestedModel = String(args?.model || NVIDIA_AGENT_MODELS[0]).trim();
  const candidateModels = [requestedModel, ...NVIDIA_AGENT_MODELS.filter((m) => m !== requestedModel)];
  const userPrompt =
    String(args?.prompt || "Summarize the key technical takeaways and timestamps.").trim() ||
    "Summarize the key technical takeaways and timestamps.";

  let videoContext = "";
  let videoId = null;
  let title = null;

  if (args?.url) {
    videoId = extractVideoId(args.url);
    try {
      const tx = await handleTubeTranscript(
        { url: args.url, lang: args?.lang || "en", timestamps: true },
        fetchFn,
        { truncate: false }
      );
      title = tx.title;
      videoContext = `Video Title: ${tx.title || videoId}\nAuthor: ${tx.author || "unknown"}\nPublished: ${
        tx.published || "unknown"
      }\nTranscript:\n${(tx.transcript || "").slice(0, 18000)}\n\n`;
    } catch {
      const prev = await handleTubePreview({ url: args.url }, fetchFn).catch(() => null);
      if (prev) {
        title = prev.title;
        videoContext = `Video Title: ${prev.title || videoId}\nAuthor: ${prev.author || "unknown"}\n(Transcript unavailable; metadata only)\n\n`;
      }
    }
  }

  const messages = [
    {
      role: "system",
      content:
        "You are the NouGenTube NVIDIA NIM Intelligence Agent. Provide concise, high-signal, evidence-backed analysis.",
    },
    { role: "user", content: `${videoContext}${userPrompt}` },
  ];

  let lastErr = null;
  for (const model of candidateModels.slice(0, 3)) {
    try {
      const resp = await fetchFn(nvUrl, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${nvKey}`,
        },
        body: JSON.stringify({
          model,
          messages,
          max_tokens: 1500,
          temperature: 0.25,
          top_p: 0.9,
        }),
      });
      if (!resp.ok) {
        lastErr = `HTTP ${resp.status}`;
        continue;
      }
      const data = await resp.json();
      const answer = data?.choices?.[0]?.message?.content || "";
      if (answer) {
        return {
          model: data?.model || model,
          video_id: videoId,
          title,
          answer,
          available_models: NVIDIA_AGENT_MODELS,
        };
      }
    } catch (err) {
      lastErr = err?.message || String(err);
    }
  }

  throw new Error(`NVIDIA NIM agent call failed (${lastErr || "no response"}).`);
}

async function handleTubeIngest(args, request, env, fetchFn) {
  const dryRun = Boolean(args?.dry_run);
  const force = Boolean(args?.force);
  if (!dryRun) {
    const auth = await authenticateRequest(request, env, fetchFn);
    if (!auth) {
      throw new Error("Unauthorized: Google Sign-In or Fleet Bearer token required for tube_ingest.");
    }
  }
  const videoId = extractVideoId(args?.url);
  if (!videoId) throw new Error("Could not extract a valid 11-char YouTube video ID.");
  const canonicalUrl = `https://www.youtube.com/watch?v=${videoId}`;

  if (!dryRun && !force) {
    const dedupe = await handleTubeDedupeCheck({ url: videoId }, env, fetchFn).catch(() => ({
      exists: false,
    }));
    if (dedupe.exists) {
      return {
        video_id: videoId,
        dry_run: false,
        skipped_duplicate: true,
        parts_count: 0,
        duplication_ratio: 0,
        tags: ["nougentube", `tube:${videoId}`],
        shards: [],
      };
    }
  }

  let txData = null;
  try {
    // Pass truncate: false so full transcripts >30k chars are split across shards without 25k clipping
    txData = await handleTubeTranscript(args, fetchFn, { truncate: false });
  } catch {
    // Metadata-only stub fallback
  }

  const meta = txData || (await handleTubePreview(args, fetchFn));
  const payloads = distillShards(
    meta,
    canonicalUrl,
    txData?.transcript || null,
    txData ? "innertube-rolling-dedupe" : null
  );

  const slug =
    String(meta?.author || "unknown-channel")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "unknown-channel";

  const tags = [
    "nougentube",
    `tube:${videoId}`,
    `channel:${slug}`,
    ...(txData ? [`lang:${txData.language}`] : ["no-transcript"]),
    ...(meta?.published ? [] : ["era-unknown"]),
  ];

  if (dryRun) {
    return {
      video_id: videoId,
      dry_run: true,
      skipped_duplicate: false,
      parts_count: payloads.length,
      duplication_ratio: txData?.duplication_ratio ?? 0,
      tags,
      shards: payloads.map((p, i) => ({ part: i + 1, title: p.title, chars: p.content.length })),
    };
  }

  const captured = [];
  for (let i = 0; i < payloads.length; i++) {
    const p = payloads[i];
    const partTags = payloads.length > 1 ? [...tags, `part:${i + 1}/${payloads.length}`] : tags;
    const resJson = await callFleetShardMcp(
      "shards_capture",
      {
        event_type: "INGEST",
        title: p.title,
        content: p.content,
        tags: partTags,
      },
      env,
      fetchFn
    );
    captured.push({ part: i + 1, title: p.title, chars: p.content.length, capture: resJson });
  }

  return {
    video_id: videoId,
    dry_run: false,
    skipped_duplicate: false,
    parts_count: payloads.length,
    duplication_ratio: txData?.duplication_ratio ?? 0,
    tags,
    shards: captured,
  };
}

function oauthMetadata(origin) {
  return {
    issuer: origin,
    authorization_endpoint: `${origin}/authorize`,
    token_endpoint: `${origin}/token`,
    registration_endpoint: `${origin}/register`,
    response_types_supported: ["code"],
    grant_types_supported: ["authorization_code", "refresh_token"],
    code_challenge_methods_supported: ["S256"],
    token_endpoint_auth_methods_supported: ["none"],
    scopes_supported: ["fleet", "read", "write"],
  };
}

function resourceMetadata(origin) {
  return {
    resource: `${origin}/mcp`,
    authorization_servers: [origin],
    bearer_methods_supported: ["header"],
    scopes_supported: ["fleet", "read", "write"],
    resource_documentation: `${origin}/openapi.json`,
  };
}

const GOOGLE_G_SVG = `<svg class="gsi-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>`;

export function renderBrandedAuthorizePage({ params, error = null, origin = "" }) {
  const p = params instanceof URLSearchParams ? params : new URLSearchParams(params || "");
  const fields = [
    "client_id",
    "redirect_uri",
    "state",
    "code_challenge",
    "code_challenge_method",
    "scope",
    "response_type",
  ];
  const hiddenInputs = fields
    .map((k) => `<input type="hidden" name="${k}" value="${escHtml(p.get(k) || "")}">`)
    .join("\n            ");

  const qs = new URLSearchParams();
  for (const k of fields) {
    if (p.get(k)) qs.set(k, p.get(k));
  }
  const googleHref = `/google/start?${escHtml(qs.toString())}`;

  let clientHost = "MCP Client";
  try {
    const r = p.get("redirect_uri");
    if (r) clientHost = new URL(r).hostname || r;
  } catch {
    clientHost = "MCP Client";
  }
  const lane = CONNECTOR_LANE_MAP[clientHost.toLowerCase()] || `${clientHost.split(".")[0] || "mcp"}-app`;

  return new Response(
    `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Sign in — NouGenTube MCP</title>
  <link rel="icon" type="image/webp" href="/assets/emblem.webp">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --ng-midnight: #03045e;
      --ng-abyss: #020336;
      --ng-surface: #06113c;
      --ng-card: #081848;
      --ng-cerulean: #0077b6;
      --ng-cyan: #00b4d8;
      --ng-sky: #90e0ef;
      --ng-ice: #caf0f8;
      --ng-white: #ffffff;
      --ng-border: rgba(144, 224, 239, 0.24);
      --ng-danger: #ffccd5;
      --ng-danger-bg: rgba(164, 19, 60, 0.45);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background-color: var(--ng-abyss);
      background-image:
        radial-gradient(circle at 18% 18%, rgba(0, 119, 182, 0.28) 0%, transparent 48%),
        radial-gradient(circle at 82% 84%, rgba(0, 180, 216, 0.18) 0%, transparent 52%),
        linear-gradient(160deg, var(--ng-midnight) 0%, var(--ng-abyss) 100%);
      color: var(--ng-ice);
      font-family: 'Google Sans', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      padding: 24px 16px;
      -webkit-font-smoothing: antialiased;
    }
    .glif-shell { width: 100%; max-width: 920px; }
    .glif-card {
      background: var(--ng-card);
      border: 1px solid var(--ng-border);
      border-radius: 28px;
      padding: 40px;
      display: grid;
      grid-template-columns: 1.05fr 1fr;
      gap: 44px;
      box-shadow: 0 24px 64px rgba(2, 3, 54, 0.72), inset 0 1px 0 rgba(202, 240, 248, 0.14);
      align-items: center;
    }
    @media (max-width: 820px) {
      .glif-card { grid-template-columns: 1fr; padding: 28px 22px; gap: 28px; border-radius: 24px; }
    }
    .brand-col { display: flex; flex-direction: column; align-items: flex-start; }
    .emblem-frame {
      position: relative;
      width: 84px;
      height: 84px;
      aspect-ratio: 1 / 1;
      border-radius: 22px;
      padding: 3px;
      background: linear-gradient(135deg, var(--ng-cyan), var(--ng-cerulean));
      box-shadow: 0 8px 28px rgba(0, 180, 216, 0.35);
      margin-bottom: 22px;
    }
    .emblem-img {
      width: 78px;
      height: 78px;
      aspect-ratio: 1 / 1;
      border-radius: 19px;
      object-fit: cover;
      display: block;
      background: var(--ng-midnight);
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 4px 12px;
      border-radius: 9999px;
      background: var(--ng-midnight);
      border: 1px solid var(--ng-sky);
      color: var(--ng-ice);
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin-bottom: 14px;
    }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ng-sky); box-shadow: 0 0 8px var(--ng-cyan); }
    h1 { margin: 0 0 10px; font-size: 32px; line-height: 1.2; font-weight: 500; color: var(--ng-white); letter-spacing: -0.01em; }
    .subtitle { margin: 0 0 22px; font-size: 15px; line-height: 1.55; color: var(--ng-ice); }
    .subtitle strong { color: var(--ng-white); font-weight: 600; }
    .scope-list { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 18px; padding: 0; list-style: none; }
    .scope-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      padding: 5px 9px;
      border-radius: 8px;
      background: var(--ng-midnight);
      border: 1px solid rgba(144, 224, 239, 0.35);
      color: var(--ng-ice);
    }
    .gcp-meta { font-size: 12px; color: var(--ng-sky); margin-top: 4px; }
    .action-col {
      display: flex;
      flex-direction: column;
      background: var(--ng-surface);
      border: 1px solid rgba(144, 224, 239, 0.22);
      border-radius: 20px;
      padding: 28px 24px;
    }
    .gsi-material-button {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      width: 100%;
      height: 44px;
      padding: 0 20px;
      border-radius: 9999px;
      background-color: #ffffff;
      border: 1px solid #747775;
      color: #1f1f1f;
      font-family: 'Google Sans', Roboto, arial, sans-serif;
      font-size: 14px;
      line-height: 20px;
      font-weight: 500;
      letter-spacing: 0.25px;
      text-decoration: none;
      cursor: pointer;
      transition: background-color 0.15s ease, box-shadow 0.15s ease, transform 0.1s ease;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
    }
    .gsi-material-button:hover { background-color: #f8fafe; box-shadow: 0 2px 8px rgba(0, 180, 216, 0.35); }
    .gsi-material-button:active { background-color: #e8eaed; transform: translateY(1px); }
    .gsi-material-button:focus-visible { outline: 3px solid var(--ng-cyan); outline-offset: 2px; }
    .gsi-icon { width: 20px; height: 20px; flex-shrink: 0; }
    .divider {
      display: flex; align-items: center; gap: 12px; margin: 22px 0;
      color: var(--ng-sky); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
    }
    .divider::before, .divider::after { content: ""; flex: 1; height: 1px; background: rgba(144, 224, 239, 0.22); }
    .field-label { display: block; font-size: 13px; font-weight: 500; color: var(--ng-ice); margin-bottom: 8px; }
    .input-wrap { position: relative; display: flex; align-items: center; }
    input[type="password"], input[type="text"] {
      width: 100%; height: 44px; padding: 0 14px; border-radius: 10px;
      border: 1px solid rgba(144, 224, 239, 0.4); background: var(--ng-midnight);
      color: var(--ng-white); font-family: 'JetBrains Mono', monospace; font-size: 14px;
    }
    input[type="password"]:focus, input[type="text"]:focus { outline: 2px solid var(--ng-cyan); border-color: var(--ng-cyan); }
    .btn-primary {
      width: 100%; height: 44px; margin-top: 14px; border: 1px solid var(--ng-sky);
      border-radius: 9999px; background: var(--ng-midnight); color: var(--ng-white);
      font-family: 'Google Sans', 'Inter', sans-serif; font-size: 14px; font-weight: 600;
      letter-spacing: 0.02em; cursor: pointer; transition: background 0.15s ease, border-color 0.15s ease;
    }
    .btn-primary:hover { background: var(--ng-cerulean); border-color: var(--ng-ice); }
    .btn-primary:focus-visible { outline: 3px solid var(--ng-cyan); outline-offset: 2px; }
    .err-banner {
      margin-top: 12px; padding: 10px 12px; border-radius: 10px;
      background: var(--ng-danger-bg); border: 1px solid var(--ng-danger); color: var(--ng-white); font-size: 13px;
    }
    .endpoint-box {
      margin-top: 20px; padding: 10px 12px; border-radius: 10px; background: var(--ng-midnight);
      border: 1px solid rgba(144, 224, 239, 0.25); display: flex; align-items: center;
      justify-content: space-between; gap: 8px; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--ng-ice);
    }
    .copy-btn {
      background: transparent; border: 1px solid var(--ng-sky); color: var(--ng-ice);
      border-radius: 6px; padding: 4px 8px; font-size: 11px; cursor: pointer;
    }
    .glif-footer {
      display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;
      gap: 12px; padding: 18px 8px 0; font-size: 12px; color: var(--ng-sky);
    }
    .glif-footer a { color: var(--ng-ice); text-decoration: none; margin-left: 16px; }
    .glif-footer a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <main class="glif-shell">
    <section class="glif-card" aria-labelledby="signin-title">
      <div class="brand-col">
        <div class="emblem-frame" data-twic-src="image:emblem.webp" data-twic-focus="auto">
          <img class="emblem-img" width="78" height="78" fetchpriority="high" decoding="async" src="data:image/webp;base64,${EMBLEM_WEBP_B64}" alt="NouGenTube Crystalline Play-Prism Emblem">
        </div>
        <div class="status-pill"><span class="status-dot"></span> NouGenTube MCP v${SERVER_INFO.version}</div>
        <h1 id="signin-title">Sign in to NouGenTube</h1>
        <p class="subtitle">
          To continue to <strong>${escHtml(clientHost)}</strong> (lane: <code>${escHtml(lane)}</code>) with Streamable HTTP MCP <code>2026-07-28</code> + NVIDIA NIM + TwicPics.
        </p>
        <ul class="scope-list" aria-label="Available MCP tools">
          <li class="scope-badge">tube_preview</li>
          <li class="scope-badge">tube_transcript</li>
          <li class="scope-badge">tube_ask_nvidia</li>
          <li class="scope-badge">tube_media_twic</li>
          <li class="scope-badge">tube_metadata_osint</li>
          <li class="scope-badge">tube_search_and_comments</li>
          <li class="scope-badge">tube_playlist_and_pack</li>
          <li class="scope-badge">tube_dedupe_check</li>
          <li class="scope-badge">tube_search_shards</li>
          <li class="scope-badge">tube_ingest</li>
        </ul>
        <div class="gcp-meta">Enrolled GCP OAuth Projects: NouGenAi • nougeneye-auth • Who-Fleet</div>
      </div>

      <div class="action-col">
        <a class="gsi-material-button" href="${googleHref}">
          ${GOOGLE_G_SVG}
          <span>Continue with Google</span>
        </a>

        <div class="divider">or use fleet key</div>

        <form method="POST" action="/authorize">
          ${hiddenInputs}
          <label class="field-label" for="fleet_key_input">NouGen Fleet Key</label>
          <div class="input-wrap">
            <input id="fleet_key_input" type="password" name="fleet_key" placeholder="Enter fleet key..." required autocomplete="off">
          </div>
          ${error ? `<div class="err-banner" role="alert">${escHtml(error)}</div>` : ""}
          <button type="submit" class="btn-primary">Authorize Connector</button>
        </form>

        <div class="endpoint-box">
          <span id="mcp-url">${escHtml(origin)}/mcp</span>
          <button type="button" class="copy-btn" onclick="navigator.clipboard.writeText(document.getElementById('mcp-url').textContent);this.textContent='Copied'">Copy URL</button>
        </div>
      </div>
    </section>

    <footer class="glif-footer">
      <span>NouGenAi • Shades of Blue WCAG AAA (7:1+) • TwicPics Zero-CLS</span>
      <nav aria-label="Service links">
        <a href="/health">Health</a>
        <a href="/openapi.json">OpenAPI 3.1</a>
        <a href="/.well-known/oauth-authorization-server">OAuth Metadata</a>
      </nav>
    </footer>
  </main>
</body>
</html>`,
    {
      status: 200,
      headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
    }
  );
}

function renderConnectedPage({ email, keyId, accessToken, origin }) {
  return new Response(
    `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Connected — NouGenTube MCP</title>
  <link rel="icon" type="image/webp" href="/assets/emblem.webp">
  <style>
    body {
      margin: 0; min-height: 100vh; background: #020336; color: #caf0f8;
      font-family: 'Google Sans', system-ui, sans-serif;
      display: flex; justify-content: center; align-items: center; padding: 24px;
    }
    .card {
      background: #081848; border: 1px solid rgba(144,224,239,0.3); border-radius: 24px;
      padding: 36px; max-width: 560px; width: 100%; box-shadow: 0 24px 64px rgba(0,0,0,0.6);
    }
    .hdr { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
    .hdr img { width: 56px; height: 56px; aspect-ratio: 1/1; border-radius: 14px; border: 2px solid #00b4d8; }
    h1 { margin: 0; font-size: 24px; color: #ffffff; }
    p { color: #caf0f8; line-height: 1.5; font-size: 14px; }
    pre {
      background: #03045e; border: 1px solid #90e0ef; border-radius: 10px;
      padding: 12px; color: #ffffff; overflow-x: auto; font-size: 12px;
    }
    a.btn {
      display: inline-block; margin-top: 14px; padding: 10px 20px; border-radius: 9999px;
      background: #0077b6; color: #ffffff; text-decoration: none; font-weight: 600; font-size: 14px;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="hdr">
      <img width="56" height="56" src="data:image/webp;base64,${EMBLEM_WEBP_B64}" alt="NouGenTube Emblem">
      <div>
        <h1>Connected to NouGenTube MCP</h1>
        <p style="margin:4px 0 0">Identity: <strong>${escHtml(email || keyId || "verified")}</strong></p>
      </div>
    </div>
    <p>Your Google Sign-In session is active. Use this MCP Server URL:</p>
    <pre>${escHtml(origin)}/mcp</pre>
    ${accessToken ? `<p>Bearer Access Token:</p><pre>${escHtml(accessToken)}</pre>` : ""}
    <a class="btn" href="/authorize">Back to Portal</a>
  </div>
</body>
</html>`,
    { status: 200, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } }
  );
}

function isUpstreamCompatibleRedirect(uri) {
  if (!uri || typeof uri !== "string") return false;
  try {
    const u = new URL(uri);
    if (u.protocol === "https:") {
      return Boolean(u.hostname && u.hostname.includes(".") && !u.hostname.includes(" "));
    }
    if (u.protocol === "http:") {
      return u.hostname === "localhost" || u.hostname === "127.0.0.1" || u.hostname === "[::1]";
    }
    if (["vscode:", "vscode-insiders:", "cursor:", "windsurf:", "cursor-url:"].includes(u.protocol)) {
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

function isAnyValidRedirectUri(uri) {
  if (!uri || typeof uri !== "string") return false;
  try {
    const u = new URL(uri);
    return /^[a-z][a-z0-9+.-]*:$/i.test(u.protocol);
  } catch {
    return false;
  }
}

async function sha256B64Url(str) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
  return encodeB64Url(new Uint8Array(digest));
}

async function bootstrapSelfAuthorizeParams(origin, upstream, fetchFn) {
  const selfCallback = `${origin}/oauth/complete`;
  const verifier = "ngtube-self-pkce-verifier-v4-deterministic-key";
  const challenge = await sha256B64Url(verifier);
  let clientId = "ngf-self";
  if (upstream) {
    try {
      const regResp = await fetchFn(`${upstream}/register`, {
        method: "POST",
        headers: { "content-type": "application/json", "user-agent": "NouGenTube-MCP/4.0" },
        body: JSON.stringify({
          redirect_uris: [selfCallback],
          client_name: "NouGenTube Browser Portal",
        }),
      });
      if (regResp.ok) {
        const regData = await regResp.json();
        if (regData?.client_id) clientId = regData.client_id;
      }
    } catch {
      // fallback clientId
    }
  }
  return new URLSearchParams({
    client_id: clientId,
    redirect_uri: selfCallback,
    response_type: "code",
    code_challenge: challenge,
    code_challenge_method: "S256",
    scope: "fleet read write",
    state: "self_portal",
  });
}

async function handleOAuthRoute(request, env, url, fetchFn) {
  const upstream = String(env?.OAUTH_UPSTREAM || "").replace(/\/+$/, "");
  const bounceCallback = `${url.origin}/oauth/bounce`;

  if (url.pathname === "/register" && request.method === "POST") {
    let body = {};
    try {
      body = await request.json();
    } catch {
      return jsonResponse({ error: "invalid_client_metadata" }, 400);
    }
    const rawUris = Array.isArray(body.redirect_uris) ? body.redirect_uris : [];
    const validUris = rawUris.filter(isAnyValidRedirectUri);
    const upstreamUris = validUris.length
      ? validUris.map((u) => (isUpstreamCompatibleRedirect(u) ? u : bounceCallback))
      : [`${url.origin}/oauth/complete`];

    let regJson = { client_id: "ngf-local" };
    let status = 201;
    if (upstream) {
      const regResp = await fetchFn(`${upstream}/register`, {
        method: "POST",
        headers: { "content-type": "application/json", "user-agent": "NouGenTube-MCP/4.0" },
        body: JSON.stringify({
          ...body,
          redirect_uris: Array.from(new Set([...upstreamUris, bounceCallback, `${url.origin}/oauth/complete`])),
        }),
      });
      status = regResp.status;
      regJson = await regResp.json().catch(() => ({}));
    }
    return jsonResponse(
      {
        ...regJson,
        redirect_uris: validUris.length ? validUris : [`${url.origin}/oauth/complete`],
      },
      status
    );
  }

  if (url.pathname === "/oauth/complete") {
    const code = url.searchParams.get("code");
    if (!code || !upstream) {
      return renderConnectedPage({
        email: null,
        keyId: "browser-portal",
        accessToken: null,
        origin: url.origin,
      });
    }
    const verifier = "ngtube-self-pkce-verifier-v4-deterministic-key";
    const selfCallback = `${url.origin}/oauth/complete`;
    try {
      const tokResp = await fetchFn(`${upstream}/token`, {
        method: "POST",
        headers: { "content-type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          grant_type: "authorization_code",
          code,
          redirect_uri: selfCallback,
          code_verifier: verifier,
        }),
      });
      const tokData = await tokResp.json().catch(() => ({}));
      const payload = tokData.access_token ? decodeB64UrlJson(tokData.access_token.split(".")[1] || "") : null;
      return renderConnectedPage({
        email: payload?.eml || null,
        keyId: payload?.key || "authenticated",
        accessToken: tokData.access_token || null,
        origin: url.origin,
      });
    } catch {
      return renderConnectedPage({ email: null, keyId: "authenticated", accessToken: null, origin: url.origin });
    }
  }

  if (url.pathname === "/oauth/bounce") {
    const rawState = url.searchParams.get("state") || "";
    const code = url.searchParams.get("code") || "";
    if (rawState.startsWith("bounce:")) {
      const decoded = decodeB64UrlJson(rawState.slice("bounce:".length));
      if (decoded?.real_uri && isAnyValidRedirectUri(decoded.real_uri)) {
        const dest = new URL(decoded.real_uri);
        if (code) dest.searchParams.set("code", code);
        if (decoded.orig_state) dest.searchParams.set("state", decoded.orig_state);
        return Response.redirect(dest.toString(), 302);
      }
    }
    return renderConnectedPage({ email: null, keyId: "connected", accessToken: null, origin: url.origin });
  }

  if (url.pathname === "/login" || url.pathname === "/authorize" || url.pathname === "/google/start") {
    if (request.method === "GET") {
      let params = new URLSearchParams(url.searchParams);
      const redir = params.get("redirect_uri") || "";
      const cid = params.get("client_id") || "";
      const chal = params.get("code_challenge") || "";

      if (!redir || !cid || !chal) {
        params = await bootstrapSelfAuthorizeParams(url.origin, upstream, fetchFn);
      } else if (!isUpstreamCompatibleRedirect(redir) && isAnyValidRedirectUri(redir)) {
        const bounceState =
          "bounce:" +
          encodeB64Url(
            new TextEncoder().encode(JSON.stringify({ real_uri: redir, orig_state: params.get("state") || "" }))
          );
        params.set("redirect_uri", bounceCallback);
        params.set("state", bounceState);
      }

      if (url.pathname === "/google/start" || url.pathname === "/login") {
        const targetBase = upstream || url.origin;
        return Response.redirect(`${targetBase}/google/start?${params.toString()}`, 302);
      }

      return renderBrandedAuthorizePage({ params, error: null, origin: url.origin });
    }

    if (request.method === "POST") {
      const bodyText = await request.text();
      const formParams = new URLSearchParams(bodyText);
      if (upstream) {
        const resp = await fetchFn(`${upstream}/authorize`, {
          method: "POST",
          headers: { "content-type": "application/x-www-form-urlencoded" },
          body: formParams.toString(),
          redirect: "manual",
        });
        if (resp.status >= 300 && resp.status < 400) {
          const loc = resp.headers.get("location");
          if (loc) return Response.redirect(loc, resp.status);
        }
      }
      return renderBrandedAuthorizePage({
        params: formParams,
        error: "Invalid Fleet Key. Sign in with Google above or verify your key.",
        origin: url.origin,
      });
    }
  }

  if (url.pathname === "/token" && request.method === "POST") {
    const bodyText = await request.text();
    if (!upstream) return jsonResponse({ error: "oauth_upstream_unconfigured" }, 503);
    const resp = await fetchFn(`${upstream}/token`, {
      method: "POST",
      headers: {
        "content-type": request.headers.get("content-type") || "application/x-www-form-urlencoded",
        "user-agent": "NouGenTube-MCP/4.0",
      },
      body: bodyText,
    });
    const text = await resp.text();
    return new Response(text, {
      status: resp.status,
      headers: {
        "content-type": "application/json; charset=utf-8",
        "access-control-allow-origin": "*",
        "cache-control": "no-store",
      },
    });
  }

  return jsonResponse({ error: "not_found" }, 404);
}

function buildOpenApiSpec(origin) {
  return {
    openapi: "3.1.0",
    info: { title: "NouGenTube MCP", version: SERVER_INFO.version },
    servers: [{ url: origin }],
    paths: {
      "/health": { get: { summary: "Health check", responses: { "200": { description: "OK" } } } },
      "/authorize": {
        get: { summary: "Branded Google Sign-In & OAuth 2.0 Portal", responses: { "200": { description: "HTML" } } },
      },
      "/media/{videoId}": {
        get: { summary: "TwicPics Responsive Media Proxy", responses: { "200": { description: "Image or JSON" } } },
      },
      "/mcp": {
        get: { summary: "MCP endpoint metadata", responses: { "200": { description: "OK" } } },
        post: {
          summary: "Streamable HTTP MCP JSON-RPC 2.0",
          responses: { "200": { description: "JSON-RPC response" } },
        },
      },
    },
  };
}

async function dispatchSingleRpc(msg, request, env, fetchFn, activeProtocol, origin) {
  const hdrs = { "mcp-protocol-version": activeProtocol };
  if (!msg || typeof msg !== "object" || typeof msg.method !== "string") {
    return rpcErr(msg?.id ?? null, -32600, "Invalid Request: missing method", 400, undefined, hdrs);
  }
  const { id, method, params } = msg;
  const isNotification = id === undefined;

  const headerVer = request.headers.get("mcp-protocol-version");
  const metaVer = params?._meta?.["io.modelcontextprotocol/protocolVersion"];
  if (headerVer && metaVer && headerVer !== metaVer) {
    return rpcErr(
      id,
      -32600,
      `HeaderMismatch: MCP-Protocol-Version (${headerVer}) != _meta protocolVersion (${metaVer})`,
      400,
      undefined,
      hdrs
    );
  }

  if (method === "initialize") {
    const requested = params?.protocolVersion;
    const protocolVersion = PROTOCOL_VERSIONS.includes(requested) ? requested : PROTOCOL_VERSIONS[0];
    return rpcOk(
      id,
      {
        protocolVersion,
        capabilities: { tools: { listChanged: false } },
        serverInfo: SERVER_INFO,
      },
      { "mcp-protocol-version": protocolVersion }
    );
  }

  if (method === "notifications/initialized" || method.startsWith("notifications/")) {
    if (isNotification) return jsonResponse(null, 202, hdrs);
    return rpcOk(id, {}, hdrs);
  }

  if (method === "ping") {
    return rpcOk(id, {}, hdrs);
  }

  if (method === "tools/list") {
    return rpcOk(id, { tools: TOOLS }, hdrs);
  }

  if (method === "tools/call") {
    const name = params?.name;
    const args = params?.arguments || {};
    try {
      let data;
      if (name === "tube_preview") data = await handleTubePreview(args, fetchFn);
      else if (name === "tube_transcript") data = await handleTubeTranscript(args, fetchFn, { truncate: true });
      else if (name === "tube_dedupe_check") data = await handleTubeDedupeCheck(args, env, fetchFn);
      else if (name === "tube_search_shards") data = await handleTubeSearchShards(args, env, fetchFn);
      else if (name === "tube_ask_nvidia") data = await handleTubeAskNvidia(args, env, fetchFn);
      else if (name === "tube_media_twic") {
        const vid = extractVideoId(args?.url);
        if (!vid) throw new Error("Could not extract a valid 11-char YouTube video ID.");
        data = buildTwicMediaBundle(vid, origin, args);
      } else if (name === "tube_metadata_osint") data = await handleTubeMetadataOsint(args, origin, fetchFn);
      else if (name === "tube_search_and_comments") data = await handleTubeSearchAndComments(args, fetchFn);
      else if (name === "tube_playlist_and_pack") data = await handleTubePlaylistAndPack(args, fetchFn);
      else if (name === "tube_analytics_and_trends") data = await handleTubeAnalyticsAndTrends(args, origin, fetchFn);
      else if (name === "tube_live_streaming") data = await handleTubeLiveStreaming(args, fetchFn);
      else if (name === "tube_ingest") data = await handleTubeIngest(args, request, env, fetchFn);
      else return rpcErr(id, -32601, `Unknown tool: ${name}`, 404, undefined, hdrs);

      return rpcOk(
        id,
        {
          resultType: "complete",
          content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
          structuredContent: data,
          isError: false,
        },
        hdrs
      );
    } catch (err) {
      return rpcOk(
        id,
        {
          resultType: "complete",
          content: [{ type: "text", text: `Error: ${err?.message || String(err)}` }],
          isError: true,
        },
        hdrs
      );
    }
  }

  return rpcErr(id, -32601, `Method not found: ${method}`, 404, undefined, hdrs);
}

export async function handleRequest(request, env = {}, fetchFn = fetch) {
  const url = new URL(request.url);
  if (request.method === "OPTIONS") {
    return jsonResponse(null, 204);
  }

  if (request.method === "GET" && (url.pathname === "/assets/emblem.webp" || url.pathname === "/favicon.ico")) {
    const raw = atob(EMBLEM_WEBP_B64);
    const bytes = Uint8Array.from(raw, (c) => c.charCodeAt(0));
    return new Response(bytes, {
      status: 200,
      headers: {
        "content-type": "image/webp",
        "cache-control": "public, max-age=31536000, immutable",
        "access-control-allow-origin": "*",
      },
    });
  }

  // TwicPics Responsive Media Route (/media/:videoId?twic=v1/...)
  if (request.method === "GET" && url.pathname.startsWith("/media/")) {
    const vid = extractVideoId(url.pathname.slice("/media/".length));
    if (!vid) return jsonResponse({ error: "invalid_video_id" }, 400);
    const twicChain = url.searchParams.get("twic") || "v1/output=webp";
    const bundle = buildTwicMediaBundle(vid, url.origin);
    if (twicChain.includes("output=lqip")) {
      const svg = decodeURIComponent(bundle.lqip_data_uri.split(",")[1] || "");
      return new Response(svg, {
        status: 200,
        headers: { "content-type": "image/svg+xml", "cache-control": "public, max-age=86400" },
      });
    }
    return jsonResponse({ twic: twicChain, ...bundle });
  }

  if (request.method === "GET" && url.pathname === "/") {
    const accept = request.headers.get("accept") || "";
    if (accept.includes("text/html")) {
      const upstream = String(env?.OAUTH_UPSTREAM || "").replace(/\/+$/, "");
      const params = await bootstrapSelfAuthorizeParams(url.origin, upstream, fetchFn);
      return renderBrandedAuthorizePage({ params, error: null, origin: url.origin });
    }
  }

  if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) {
    return jsonResponse({
      ok: true,
      service: SERVER_INFO.name,
      version: SERVER_INFO.version,
      mcp_endpoint: `${url.origin}/mcp`,
      oauth: true,
      google_sign_in: true,
      authorization_endpoint: `${url.origin}/authorize`,
      emblem_url: `${url.origin}/assets/emblem.webp`,
      nvidia_agent_enabled: Boolean(env?.NVIDIA_API_KEY),
      nvidia_models: NVIDIA_AGENT_MODELS,
      gcp_oauth_projects: Object.keys(GCP_OAUTH_PROJECTS),
      lane_map: CONNECTOR_LANE_MAP,
      protocol_versions: PROTOCOL_VERSIONS,
      features: [
        "glif-material3-google-signin-portal",
        "nano-banana-webp-emblem",
        "twicpics-zero-cls-lqip-engine",
        "keymaker-nvidia-nim-agents",
        "mw-youtube-metadata-osint",
        "youtube-comment-suite-and-streams",
        "bottuber-and-subscription-playlist-feeds",
        "zero-invalid-redirect-uri-self-pkce",
        "rolling-caption-dedupe-4pattern",
        "multi-client-innertube-24h-cache",
        "mcp-jsonrpc-shard-grid-bridge",
      ],
      tools: TOOLS.map((t) => t.name),
    });
  }

  if (request.method === "GET" && url.pathname === "/openapi.json") {
    return jsonResponse(buildOpenApiSpec(url.origin));
  }

  if (
    request.method === "GET" &&
    (url.pathname === "/.well-known/oauth-protected-resource" ||
      url.pathname === "/.well-known/oauth-protected-resource/mcp")
  ) {
    return jsonResponse(resourceMetadata(url.origin));
  }

  if (request.method === "GET" && url.pathname === "/.well-known/oauth-authorization-server") {
    return jsonResponse(oauthMetadata(url.origin));
  }

  if (
    url.pathname === "/register" ||
    url.pathname === "/authorize" ||
    url.pathname === "/login" ||
    url.pathname === "/google/start" ||
    url.pathname === "/oauth/complete" ||
    url.pathname === "/oauth/bounce" ||
    url.pathname === "/token"
  ) {
    return handleOAuthRoute(request, env, url, fetchFn);
  }

  if (url.pathname === "/mcp" && request.method === "GET") {
    const accept = request.headers.get("accept") || "";
    if (accept.includes("text/html")) {
      const upstream = String(env?.OAUTH_UPSTREAM || "").replace(/\/+$/, "");
      const params = await bootstrapSelfAuthorizeParams(url.origin, upstream, fetchFn);
      return renderBrandedAuthorizePage({ params, error: null, origin: url.origin });
    }
    return jsonResponse({
      name: SERVER_INFO.name,
      version: SERVER_INFO.version,
      transport: "streamable-http",
      endpoint: "/mcp",
      oauth: true,
      google_sign_in: true,
      nvidia_agent_enabled: Boolean(env?.NVIDIA_API_KEY),
      emblem_url: `${url.origin}/assets/emblem.webp`,
      protocol_versions: PROTOCOL_VERSIONS,
      tools: TOOLS.map((t) => t.name),
    });
  }

  if (url.pathname === "/mcp" && request.method === "POST") {
    const auth = await authenticateRequest(request, env, fetchFn);
    if (!auth) {
      return jsonResponse(
        { error: "unauthorized", error_description: "Sign in with Google or provide a valid Bearer token." },
        401,
        {
          "www-authenticate": `Bearer realm="nougen-tube", resource_metadata="${url.origin}/.well-known/oauth-protected-resource"`,
        }
      );
    }

    const headerVer = request.headers.get("mcp-protocol-version");
    if (headerVer && !PROTOCOL_VERSIONS.includes(headerVer)) {
      return rpcErr(
        null,
        -32600,
        `UnsupportedProtocolVersionError: ${headerVer}. Supported: ${PROTOCOL_VERSIONS.join(", ")}`,
        400,
        { supported: PROTOCOL_VERSIONS }
      );
    }
    const activeProtocol = headerVer || PROTOCOL_VERSIONS[0];

    let msg;
    try {
      msg = await request.json();
    } catch {
      return rpcErr(null, -32700, "Parse error: invalid JSON", 400);
    }

    if (Array.isArray(msg)) {
      if (!msg.length) return rpcErr(null, -32600, "Invalid Request: empty batch", 400);
      const responses = [];
      for (const item of msg) {
        const r = await dispatchSingleRpc(item, request, env, fetchFn, activeProtocol, url.origin);
        if (r.status !== 202) {
          responses.push(await r.json());
        }
      }
      if (!responses.length) return jsonResponse(null, 202, { "mcp-protocol-version": activeProtocol });
      return jsonResponse(responses, 200, { "mcp-protocol-version": activeProtocol });
    }

    return dispatchSingleRpc(msg, request, env, fetchFn, activeProtocol, url.origin);
  }

  return jsonResponse({ ok: false, error: "Not found", path: url.pathname }, 404);
}

export default {
  async fetch(request, env) {
    return handleRequest(request, env, fetch);
  },
};

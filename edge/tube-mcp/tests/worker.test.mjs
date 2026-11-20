import test from "node:test";
import assert from "node:assert/strict";
import {
  CONNECTOR_LANE_MAP,
  GCP_OAUTH_PROJECTS,
  NVIDIA_AGENT_MODELS,
  buildTwicMediaBundle,
  computeDuplicationRatio,
  dedupeCues,
  decodeHtmlEntities,
  distillShards,
  extractVideoId,
  handleRequest,
  parseVttCues,
  recursiveSplit,
  stripHtmlTags,
} from "../src/worker.js";

test("extractVideoId handles watch, short, youtu.be, l.meta.ai redirect, and raw IDs", () => {
  assert.equal(extractVideoId("dQw4w9WgXcQ"), "dQw4w9WgXcQ");
  assert.equal(extractVideoId("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5s"), "dQw4w9WgXcQ");
  assert.equal(extractVideoId("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ");
  assert.equal(extractVideoId("https://www.youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ");
  assert.equal(
    extractVideoId("https://l.meta.ai/?u=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DtEysfZGzJc8"),
    "tEysfZGzJc8"
  );
  assert.equal(extractVideoId("https://example.com/nope"), null);
});

test("decodeHtmlEntities is single-pass and stripHtmlTags removes nested tags safely", () => {
  assert.equal(decodeHtmlEntities("&amp;lt;script&amp;gt; &#39;26"), "&lt;script&gt; '26");
  assert.equal(stripHtmlTags("<c.colorE5E5E5>Hello <b>world</b></c>").replace(/\s+/g, " ").trim(), "Hello world");
});

test("4-pattern rolling-caption dedupe collapses YouTube auto-caption repeats", () => {
  const vtt = [
    "WEBVTT",
    "",
    "00:00:01.000 --> 00:00:03.000",
    "we are building the sovereign",
    "",
    "00:00:03.000 --> 00:00:05.000",
    "we are building the sovereign memory grid",
    "",
    "00:00:05.000 --> 00:00:06.000",
    "memory grid",
    "",
    "00:00:06.000 --> 00:00:08.000",
    "memory grid for every agent lane",
  ].join("\n");

  const raw = parseVttCues(vtt);
  assert.equal(raw.length, 4);
  const deduped = dedupeCues(raw);
  assert.equal(deduped.length, 2);
  assert.equal(
    deduped.map((c) => c.text).join(" "),
    "we are building the sovereign memory grid for every agent lane"
  );
  assert.ok(computeDuplicationRatio(raw, deduped) > 0.35);
});

test("recursiveSplit and distillShards split oversized transcripts with standalone headers", () => {
  const longText = Array.from({ length: 800 }, (_, i) => `Sentence number ${i} about NouGenTube.`).join(" ");
  const chunks = recursiveSplit(longText, 5000, 300);
  assert.ok(chunks.length > 4);
  const shards = distillShards(
    { title: "Deep Dive", author: "GM", published: "2026-11-17T00:00:00Z", length_seconds: 600 },
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    longText
  );
  assert.equal(shards.length, 2);
  assert.ok(shards[0].content.includes("# Deep Dive"));
  assert.ok(shards[0].content.includes("## First-Pass Extract"));
  assert.ok(shards[1].title.includes("(part 2/2)"));
});

test("TwicPics responsive media engine builds zero-CLS picture HTML, LQIP SVG, and DPR srcsets", () => {
  const bundle = buildTwicMediaBundle("dQw4w9WgXcQ", "https://tube.example.com", {
    ratio: "16:9",
    focus: "auto",
  });
  assert.equal(bundle.video_id, "dQw4w9WgXcQ");
  assert.equal(bundle.ratio, "16/9");
  assert.ok(bundle.lqip_data_uri.startsWith("data:image/svg+xml;utf8,"));
  assert.ok(bundle.zero_cls_html.includes("aspect-ratio:16/9"));
  assert.ok(bundle.srcset_webp.includes("1280w"));
});

test("GET /health, /assets/emblem.webp, and maps return v4.0.0 metadata and real Nano Banana WebP", async () => {
  const r1 = await handleRequest(new Request("https://tube.example.com/health"), { NVIDIA_API_KEY: "nvapi-test" });
  assert.equal(r1.status, 200);
  const b1 = await r1.json();
  assert.equal(b1.ok, true);
  assert.equal(b1.version, "5.0.0");
  assert.equal(b1.oauth, true);
  assert.equal(b1.google_sign_in, true);
  assert.equal(b1.nvidia_agent_enabled, true);
  assert.ok(NVIDIA_AGENT_MODELS.includes("google/gemma-4-31b-it"));
  assert.equal(b1.emblem_url, "https://tube.example.com/assets/emblem.webp");
  assert.ok(GCP_OAUTH_PROJECTS["gen-lang-client-0939852539"]);
  assert.equal(CONNECTOR_LANE_MAP["meta.ai"], "meta-app");
  assert.equal(b1.tools.length, 12);

  const imgRes = await handleRequest(new Request("https://tube.example.com/assets/emblem.webp"));
  assert.equal(imgRes.status, 200);
  assert.equal(imgRes.headers.get("content-type"), "image/webp");
  const imgBuf = await imgRes.arrayBuffer();
  assert.ok(imgBuf.byteLength > 4000);
});

test("Bare GET /authorize never returns invalid_redirect_uri and renders GlifWebSignIn + Nano Banana emblem", async () => {
  const env = { OAUTH_UPSTREAM: "https://oauth.example.com" };
  const mockFetch = async (url) => {
    const parsed = new URL(String(url));
    if (parsed.pathname === "/register") {
      return new Response(JSON.stringify({ client_id: "ngf-self-test" }), { status: 201 });
    }
    return new Response("{}", { status: 200 });
  };

  const bareRes = await handleRequest(new Request("https://tube.example.com/authorize"), env, mockFetch);
  assert.equal(bareRes.status, 200);
  const html = await bareRes.text();
  assert.ok(html.includes("Sign in to NouGenTube"));
  assert.ok(html.includes("Continue with Google"));
  assert.ok(html.includes("data:image/webp;base64,"));
  assert.ok(html.includes("#03045e"));
  assert.ok(html.includes("/oauth/complete"));

  const regRes = await handleRequest(
    new Request("https://tube.example.com/register", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ redirect_uris: ["claude://oauth/callback"], client_name: "Claude Mobile" }),
    }),
    env,
    mockFetch
  );
  assert.equal(regRes.status, 201);
  const regData = await regRes.json();
  assert.deepEqual(regData.redirect_uris, ["claude://oauth/callback"]);
});

test("Google Sign-In OAuth 401 challenge and authenticated MCP 2026-07-28 negotiation", async () => {
  const env = { REQUIRE_AUTH: "true", NOUGEN_TUBE_TOKEN: "secret-fleet-tok" };

  const unauthRes = await handleRequest(
    new Request("https://tube.example.com/mcp", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "ping" }),
    }),
    env
  );
  assert.equal(unauthRes.status, 401);
  assert.match(unauthRes.headers.get("www-authenticate") || "", /resource_metadata=/);

  const initReq = new Request("https://tube.example.com/mcp", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "mcp-protocol-version": "2026-07-28",
      authorization: "Bearer secret-fleet-tok",
    },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2026-07-28" } }),
  });
  const initHttp = await handleRequest(initReq, env);
  assert.equal(initHttp.headers.get("mcp-protocol-version"), "2026-07-28");
  const initRes = await initHttp.json();
  assert.equal(initRes.result.protocolVersion, "2026-07-28");
  assert.equal(initRes.result.serverInfo.version, "5.0.0");
});

test("POST /mcp tools/call handles transcript, OSINT metadata, NVIDIA agent, and full-length ingest", async () => {
  const env = {
    WHOART_ORIGIN: "https://vault.example.com",
    SHARD_GATEWAY_TOKEN: "ngs-tok",
    NVIDIA_API_KEY: "nvapi-test",
  };
  const longCaption = Array.from({ length: 700 }, (_, i) => `Unique caption line ${i} for full ingest test.`).join(" ");

  const mockFetch = async (url) => {
    const parsed = new URL(String(url));
    if (parsed.hostname === "www.youtube.com" && parsed.pathname === "/watch") {
      return new Response(`"INNERTUBE_API_KEY":"testkey123"`, { status: 200 });
    }
    if (parsed.hostname === "www.youtube.com" && parsed.pathname === "/oembed") {
      return new Response(JSON.stringify({ title: "Test Video", author_name: "NouGen" }), { status: 200 });
    }
    if (parsed.hostname === "www.youtube.com" && parsed.pathname === "/youtubei/v1/player") {
      return new Response(
        JSON.stringify({
          videoDetails: {
            title: "Test Video",
            author: "NouGen",
            channelId: "UC123456",
            viewCount: "9000",
            lengthSeconds: "42",
            keywords: ["ai", "mcp"],
            shortDescription: "00:00 Intro\n00:20 Architecture\nCheck https://docs.example.com/guide",
          },
          microformat: { playerMicroformatRenderer: { publishDate: "2026-11-18", category: "Science & Technology" } },
          captions: {
            playerCaptionsTracklistRenderer: {
              captionTracks: [{ languageCode: "en", baseUrl: "https://captions.example.com/en" }],
            },
          },
        }),
        { status: 200 }
      );
    }
    if (parsed.hostname === "captions.example.com") {
      return new Response(
        `<transcript><text start="0" dur="2">Hello world</text><text start="2" dur="2">Hello world ${longCaption}</text></transcript>`,
        { status: 200 }
      );
    }
    if (parsed.hostname === "vault.example.com" && parsed.pathname === "/mcp/") {
      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 1,
          result: {
            content: [{ type: "text", text: JSON.stringify([{ id: "shard-1", tags: ["tube:dQw4w9WgXcQ"] }]) }],
            isError: false,
          },
        }),
        { status: 200 }
      );
    }
    if (parsed.hostname === "integrate.api.nvidia.com") {
      return new Response(
        JSON.stringify({
          model: "google/gemma-4-31b-it",
          choices: [{ message: { content: "Executive summary from NVIDIA NIM." } }],
        }),
        { status: 200 }
      );
    }
    return new Response("not found", { status: 404 });
  };

  // 1. tube_transcript truncates tool output at MAX_OUTPUT_CHARS (25,000)
  const txReq = new Request("https://tube.example.com/mcp", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 4,
      method: "tools/call",
      params: { name: "tube_transcript", arguments: { url: "v1122334455" } },
    }),
  });
  const txRes = await (await handleRequest(txReq, env, mockFetch)).json();
  assert.equal(txRes.result.isError, false);
  assert.ok(txRes.result.structuredContent.transcript.endsWith("[truncated]"));

  // 2. tube_ingest uses full untruncated transcript so >30k chars splits into 2 shards
  const ingestReq = new Request("https://tube.example.com/mcp", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 5,
      method: "tools/call",
      params: { name: "tube_ingest", arguments: { url: "v1122334455", dry_run: true } },
    }),
  });
  const ingestRes = await (await handleRequest(ingestReq, env, mockFetch)).json();
  assert.equal(ingestRes.result.isError, false);
  assert.equal(ingestRes.result.structuredContent.parts_count, 2);

  // 3. tube_metadata_osint extracts tags, description links, upload cadence, and Filmot/Wayback links
  const osintReq = new Request("https://tube.example.com/mcp", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 6,
      method: "tools/call",
      params: { name: "tube_metadata_osint", arguments: { url: "v1122334455" } },
    }),
  });
  const osintRes = await (await handleRequest(osintReq, env, mockFetch)).json();
  assert.equal(osintRes.result.isError, false);
  assert.deepEqual(osintRes.result.structuredContent.tags, ["ai", "mcp"]);
  assert.deepEqual(osintRes.result.structuredContent.description_links, ["https://docs.example.com/guide"]);
  assert.ok(osintRes.result.structuredContent.osint_investigate.filmot_archive.includes("v1122334455"));

  // 4. tube_ask_nvidia calls NVIDIA NIM with Keymaker NVIDIA_API_KEY
  const nvReq = new Request("https://tube.example.com/mcp", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 7,
      method: "tools/call",
      params: { name: "tube_ask_nvidia", arguments: { url: "v1122334455", prompt: "Summarize" } },
    }),
  });
  const nvRes = await (await handleRequest(nvReq, env, mockFetch)).json();
  assert.equal(nvRes.result.isError, false);
  assert.equal(nvRes.result.structuredContent.answer, "Executive summary from NVIDIA NIM.");
});

// NouGenTube provider registry, shared by the background page and the settings page.
// "kind" picks the wire format: "anthropic" (Messages API) or "openai" (chat/completions).
// Model ids are never hard-coded for the user: each provider's own /models list is loaded
// with the user's key and they choose from it. "prefer" only decides which one is preselected.
const NGT_PROVIDERS = [
  { id: "anthropic", name: "Claude (Anthropic)", kind: "anthropic", base: "https://api.anthropic.com/v1",
    keyHint: "sk-ant-…", keyUrl: "https://platform.claude.com/settings/keys", prefer: ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"] },
  { id: "openai", name: "OpenAI", kind: "openai", base: "https://api.openai.com/v1", keyHint: "sk-…", keyUrl: "https://platform.openai.com/api-keys", preferRe: "^gpt-[0-9.]+(-[a-z]+)?$" },
  { id: "gemini", name: "Google Gemini", kind: "openai", base: "https://generativelanguage.googleapis.com/v1beta/openai", keyHint: "AIza…", keyUrl: "https://aistudio.google.com/apikey", prefer: ["gemini-3.6-flash", "gemini-2.5-flash"] },
  { id: "deepseek", name: "DeepSeek", kind: "openai", base: "https://api.deepseek.com/v1", keyHint: "sk-…", keyUrl: "https://platform.deepseek.com/api_keys" },
  { id: "openrouter", name: "OpenRouter", kind: "openai", base: "https://openrouter.ai/api/v1", keyHint: "sk-or-…", keyUrl: "https://openrouter.ai/keys" },
  { id: "nvidia", name: "NVIDIA build", kind: "openai", base: "https://integrate.api.nvidia.com/v1", keyHint: "nvapi-…", keyUrl: "https://build.nvidia.com", prefer: ["google/gemma-4-31b-it"] },
  { id: "custom", name: "Custom (OpenAI-compatible)", kind: "openai", base: "", custom: true, keyHint: "key, if the endpoint needs one" },
];
const NGT_BY_ID = Object.fromEntries(NGT_PROVIDERS.map(p => [p.id, p]));
// Claude models that accept the server-side refusal fallback ("fallbacks": "default").
const NGT_ANTHROPIC_FALLBACK = /^claude-(fable-5-[12]|opus-5(-5)?|sonnet-5-5)$/;

# Cloud Modes

NouGenShards supports three distinct operational modes to balance privacy, cost, and intelligence.

## 1. Local (Free)
**Who Pays**: You (Compute only)
**Best For**: Maximum privacy and zero cost.

- Requires **Ollama** or **LM Studio** running locally.
- NGS searches your local shards and routes reasoning to your local hardware.
- No API keys required.
- **Performance**: Limited by your machine's GPU/RAM.

## 2. BYOK (Bring Your Own Key)
**Who Pays**: You (Direct to Provider)
**Best For**: High intelligence without a Who Visions subscription.

- You provide your own keys for **OpenAI**, **Anthropic**, **Gemini**, or **OpenRouter**.
- NGS manages the keys in your local vault.
- You are billed directly by the provider for what you use.
- **Usage**: Set your keys with `nougen auth set-key <provider> <key>`.

## 3. Who Visions Cloud (Pro)
**Who Pays**: Who Visions (Invoiced to Subscriber)
**Best For**: Resilience, managed models, and seamless sync.

- Routes requests through the **Who Visions Resilient Gateway**.
- Features automatic model fallback, advanced prompt caching, and response healing.
- Includes remote storage and device synchronization.
- **Usage**: Requires an active Who Visions subscription token.
- **Metered**: Usage is tracked by token counts in your `billing.db`.

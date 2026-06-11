# Billing Boundaries

NouGenShards has a clear separation between free local software and paid cloud services.

## 🆓 Free Forever
The core NouGenShards software is free to use for local operations.
- **Local Memory**: Infinite local shards and search.
- **Local Models**: Unlimited local inference (Ollama/LM Studio).
- **BYOK**: We do not charge a fee for using your own API keys through our CLI.

## 💳 Paid (Who Visions Pro)
You only pay when you use **Who Visions infrastructure**.

### When you are charged:
- **Hosted Inference**: When you use the `whovisions_cloud` provider, we pay the underlying model providers (like OpenRouter or Anthropic) on your behalf.
- **Remote Nodes**: Using a managed Who Visions Cloud Node for storage and sync.

### Subscription Tiers:
1.  **Free**: Local + BYOK support.
2.  **Pro**: Managed cloud gateway, 1M+ monthly tokens, remote sync, priority support.
3.  **Team**: Shared team shards, admin controls, private cloud nodes (Coming Soon).

## 📊 Usage Transparency
You can check your cloud usage at any time:
```bash
nougen stats --period month
```
This shows your token consumption and estimated cost based on the Who Visions billing substrate.

## NouGen is a capability layer, not an inference provider

NouGen operates exclusively as an orchestration layer. It does not provide inference services or host models. Its function is to manage model access between a user's existing infrastructure and the required compute endpoints. NouGen supplies orchestration, memory management through shard allocation, and a routing policy framework. Critical to this architecture, NouGen does not hold models, nor does it resell inference capacity from third parties.

NouGen interacts directly with infrastructure the user owns: specific API accounts (OpenRouter, Ollama Cloud, HuggingFace), local GPU installations (Ollama on localhost), and personal storage repositories. The user retains full control over all credentials and deployment configurations; these remain the user's input and are never incorporated into NouGen's execution builds. A clean deployment environment must build and test its components using zero external credentials to ensure system integrity.

The system architecture prioritizes capability discovery at runtime. NouGen detects the specific resources available to the user—including local binaries, model sizes on local storage, and active third-party endpoints—to determine which provider can satisfy a request. A dynamic routing policy is applied, preferring the $0 local or free compute lanes. If a preferred resource is unavailable, the system reports the failure instead of applying a silent fallback to a paid route. This mechanism ensures that the system operates on the user's available infrastructure without requiring the pre-loading or assumption of a fixed model provider.

Key characteristics:
*   Provides orchestration for distributed inference tasks.
*   Manages memory allocation via shard distribution between endpoints.
*   Implements a routing policy based on cost and availability.
*   Discovers local model capabilities at the time of execution, not during build.
*   Uses external user credentials and configurations for connectivity and deployment.
# 🪩 NouGenShards

**🧠 Persistent local memory for your AI tools.**

NouGenShards helps your AI tools remember their work. It saves "shards" of information—records of what worked and what did not work—in a database on your computer. This persistent memory lets your tools find the right information quickly without repeating previous tasks.

> 🇭🇹 This tool is built by **Who Visions** to help people use AI tools on their own computers, even without an internet connection.

---

## 🚀 How to Start

### 1. 📦 Install

```bash
# If you use Python 🐍
pip install .

# If you use Node.js 🟢
npm install -g .
```

### 2. 🛡️ Setup

```bash
nougen init
```
This creates a folder on your computer to store your shards and sets up the database. 📂

### 3. 🔐 Connect Your Subscriptions (BYOK)

Connect your own API keys for cloud AI services like ChatGPT, Claude, Gemini, and Hugging Face. 🔑

```bash
# Set your API keys
nougen auth set-key openai <your-key>
nougen auth set-key anthropic <your-key>
nougen auth set-key google <your-key>
nougen auth set-key huggingface <your-key>

# List your connected services
nougen auth list
```

### 4. 💾 Save Shards

Save what you have learned or what you have done as a memory shard. 🧩

```bash
# Save a new shard 📝
nougen add "I fixed the map by changing the web address in the file app/MarsMap.tsx" --tags fix,map
```

### 5. 🔍 Search and Find

Find shards you saved before. The tool will show you the most relevant results first. 🥇

```bash
# Search your shards 🕵️
nougen search "map fix"
```

### 6. ✅ Mark Results

Tell the tool if a shard was helpful. This helps the tool give you better answers in the future. 📈

```bash
# Mark shard number 1 as helpful 👍
nougen mark 1 --worked
```

### 7. ⚡ Run Code Safely

Run scripts on your computer to process data. This keeps your AI tool from getting cluttered with too much raw data. 🧹

```bash
# Start a new session 🆕
nougen ctx init

# Run code and see the result 💻
nougen ctx execute "const data = [10, 20, 30]; console.log(data.length)"
```

### 8. 🤖 Use AI Models (Local & Cloud)

Talk to AI models that run on your computer or in the cloud. 🏠☁️

```bash
# See models from different providers
nougen models --provider local
nougen models --provider openai
nougen models --provider huggingface

# Start talking to a local model
nougen chat --provider local --model llama3

# Start talking to a cloud model
nougen chat --provider anthropic --model claude-3-5-sonnet-latest
nougen chat --provider huggingface --model meta-llama/Llama-3.2-3B-Instruct
```

---

## 🧩 Project Structure

- **📂 src/nougen_shards/**: The main code for the tool.
- **🧪 tests/**: Code to check that the tool works correctly.
- **💡 examples/**: Examples of how to use the tool.

## 🥇 Quality and Standards

- ✨ The code is written clearly and correctly.
- ✅ All 102 tests pass correctly.
- 💻 The tool is tested and works on Windows, macOS, and Linux.

## 📜 License

Copyright © 2026 Who Visions LLC. All rights reserved. 🛡️ This source code is provided for visibility purposes only. Reuse is not granted.

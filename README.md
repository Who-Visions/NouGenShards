# NouGenShards

**Store and find information for your AI tools.**

NouGenShards helps your AI tools remember their work. It saves what worked and what did not work in a database on your computer. This lets your tools find the right information quickly without repeating previous tasks.

> This tool is built by Who Visions to help people use AI tools on their own computers, even without an internet connection.

---

## How to Start

### 1. Install

```bash
# If you use Python
pip install .

# If you use Node.js
npm install -g .
```

### 2. Setup

```bash
nougen init
```
This creates a folder on your computer to store your data and sets up the database.

### 3. Save Information

Save what you have learned or what you have done.

```bash
# Save a new note
nougen add "I fixed the map by changing the web address in the file app/MarsMap.tsx" --tags fix,map
```

### 4. Search and Find

Find information you saved before. The tool will show you the most relevant results first.

```bash
# Search your saved notes
nougen search "map fix"
```

### 5. Mark Results

Tell the tool if a piece of information was helpful. This helps the tool give you better answers in the future.

```bash
# Mark record number 1 as helpful
nougen mark 1 --worked

# Mark record number 2 as not helpful
nougen mark 2 --failed
```

### 6. Run Code Safely

Run scripts on your computer to process data. This keeps your AI tool from getting cluttered with too much raw data.

```bash
# Start a new session
nougen ctx init

# Run code and see the result
nougen ctx execute "const data = [10, 20, 30]; console.log(data.length)"

# Save a result from your session so you can find it later
nougen ctx promote 1
```

### 7. Use Local AI Models

Talk to AI models that run on your computer instead of the internet.

```bash
# See which models are on your computer
nougen models

# Start talking to a model
nougen chat --model llama3
```

---

## Project Structure

- **src/nougen_shards/**: The main code for the tool.
- **tests/**: Code to check that the tool works correctly.
- **examples/**: Examples of how to use the tool.

## Quality and Standards

- The code is written clearly and correctly.
- All 102 tests pass correctly.
- The tool is tested and works on Windows, macOS, and Linux.

## License

MIT License. © 2026 Who Visions LLC.

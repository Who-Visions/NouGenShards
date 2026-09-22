@echo off
rem Yuki: local Ollama agent with live NouGen tools. Usage: yuki [--model Yukiai:e4b] [--ask "question"]
python "%~dp0nougen_agent.py" %*

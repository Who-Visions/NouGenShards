"""Preserve Space Docker configuration when deploying a compiled README."""
from pathlib import Path
import re


def prepare(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if match:
        header = match.group(1)
        body = text[match.end():]
    else:
        header = "title: NouGenShards"
        body = text
    for name, value in (("sdk", "docker"), ("app_port", "7860")):
        pattern = rf"(?m)^{name}:.*$"
        if re.search(pattern, header):
            header = re.sub(pattern, f"{name}: {value}", header)
        else:
            header += f"\n{name}: {value}"
    path.write_text(f"---\n{header}\n---\n{body}", encoding="utf-8")


if __name__ == "__main__":
    prepare(Path("README.md"))

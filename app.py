import gradio as gr
import os
import sys

# Add src to path so we can import the package
sys.path.append(os.path.join(os.getcwd(), 'src'))
from nougen_shards import capture, retrieve, compile_recall_packet

def query_memory(query):
    """Simple public interface for searching memory records."""
    found = retrieve(query, limit=3)
    if not found:
        return "No relevant records found in the local database."
    
    output = []
    for s in found:
        output.append(f"### {s['title']}\n{s['content']}\n")
    return "\n---\n".join(output)

demo = gr.Interface(
    fn=query_memory, 
    inputs=gr.Textbox(label="Search Query", placeholder="What do you want to find?"), 
    outputs=gr.Markdown(label="Results"),
    title="NouGenShards: Local Memory Explorer",
    description="Find information stored in your local memory shards."
)

if __name__ == '__main__':
    demo.launch()

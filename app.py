import gradio as gr
import os
import sys
from nougen_shards import capture, retrieve, compile_recall_packet

def coach_orchestrate(query):
    # Retrieve local context (shards)
    found = retrieve(query, limit=5)
    context = compile_recall_packet(found)
    return f"Context Retrieved:\n{context}\n\n[Coach Recommendation]: Process with context."

demo = gr.Interface(
    fn=coach_orchestrate, 
    inputs="text", 
    outputs="text",
    title="NouGenShards Coach Orchestrator",
    description="Remote interface for the NouGen fleet."
)

if __name__ == '__main__':
    demo.launch()

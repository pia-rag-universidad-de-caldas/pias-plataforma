"""llm (feature 047): the only module that talks to Ollama. It receives messages (and, with a vision model, images)
and answers text; it knows nothing of documents, chunks nor PIAA. It only talks to data (its active configuration) and
to Ollama, an external service as Neo4j is for data."""

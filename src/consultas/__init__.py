"""consultas (feature 048): the RAG. It answers questions with the official documents: the question becomes a vector
(embeddings), data finds the closest chunks, llm answers with them as context, and data keeps the chat. Like the
pipeline, a consumer: it calls embeddings, llm and data over HTTP and never imports them."""

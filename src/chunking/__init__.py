"""Chunking of the chunkable documents with IBM's Docling (feature 021: skeleton; 022 and 023 fill it in).

It never imports ingesta nor data: it asks ingesta for the documents and stores the chunks in data over HTTP, against
the same server (ServerSettings.self_url). Docling is the optional `chunk` extra, imported lazily.
"""

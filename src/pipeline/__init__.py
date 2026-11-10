"""Pipeline (feature 028): a queue of stages run in order, reorderable, with cycles repeated until an actor approves.

It neither converts nor stores anything itself: it asks each module (ingesta, chunking, data) over HTTP, against the
same server (ServerSettings.self_url), and waits for the external actors (lab, lab2, embeber, modelscenter) when the
stage is theirs. It never imports another module.
"""

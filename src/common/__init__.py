"""Infrastructure every module shares (feature 033): HTTP clients (common.http), API errors and process boards
(common.api, common.processes), the time and the technical values (common.clock, common.config). No domain: it imports
no module (ingesta, data, chunking, pipeline, server), and every module may import it."""

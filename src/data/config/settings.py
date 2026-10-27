"""Neo4j connection and graph API defaults. The password never lives here: it comes from the environment."""

NEO4J_URL = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_DATABASE = "neo4j"  # database inside the server (None in the adapter = the server's default)
PASSWORD_VARIABLE = "NEO4J_PASSWORD"  # environment variable with the password; if missing, `serve` prompts for it

# Graph HTTP API (feature 018): a different port from the ingesta API (8000) so both can run at once.
API_HOST = "127.0.0.1"
API_PORT = 8001
PER_PAGE = 50
MAX_PER_PAGE = 500

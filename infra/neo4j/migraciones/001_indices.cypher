CREATE CONSTRAINT pia_codigo IF NOT EXISTS FOR (p:PIA) REQUIRE p.codigo IS UNIQUE;
CREATE CONSTRAINT facultad_codigo IF NOT EXISTS FOR (f:Facultad) REQUIRE f.codigo IS UNIQUE;
CREATE CONSTRAINT carrera_codigo IF NOT EXISTS FOR (c:Carrera) REQUIRE c.codigo IS UNIQUE;
CREATE CONSTRAINT materia_codigo IF NOT EXISTS FOR (m:Materia) REQUIRE m.codigo IS UNIQUE;
CREATE INDEX pia_estado IF NOT EXISTS FOR (p:PIA) ON (p.estado);
CREATE FULLTEXT INDEX fragmento_texto IF NOT EXISTS FOR (f:Fragmento) ON EACH [f.texto];
CREATE VECTOR INDEX fragmento_emb_bgem3_v1 IF NOT EXISTS
FOR (f:Fragmento) ON f.embedding
OPTIONS { indexConfig: { `vector.dimensions`: 1024, `vector.similarity_function`: 'cosine' } };
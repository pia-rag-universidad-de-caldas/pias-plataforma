MERGE (f:Facultad {codigo: 'ING'}) SET f.nombre = 'Ingeniería'
MERGE (c:Carrera {codigo: 'ING-SIS'}) SET c.nombre = 'Ingeniería de Sistemas'
MERGE (f)-[:TIENE]->(c)
MERGE (m1:Materia {codigo: 'SIS-101'}) SET m1.nombre = 'Programación I', m1.semestre = 1
MERGE (m2:Materia {codigo: 'SIS-201'}) SET m2.nombre = 'Bases de Datos', m2.semestre = 3
MERGE (c)-[:TIENE]->(m1)
MERGE (c)-[:TIENE]->(m2);
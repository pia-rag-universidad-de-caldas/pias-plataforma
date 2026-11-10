# Detección de duplicados por hash (SHA-256)

Este documento explica cómo `prueba-chunking` decide que dos archivos son el mismo
documento, qué pasos sigue para lograrlo y por qué el resultado es confiable.

## 1. Qué es un hash

Un hash es una "huella digital" de un archivo: una función matemática lee **todos los
bytes** del archivo y produce un código de tamaño fijo. Con SHA-256 ese código tiene
256 bits y se escribe como 64 caracteres hexadecimales, por ejemplo:

```
fc7f1b76126c77deb438c0fe0b6735d966194e1ed8412b7d3b0697475a7e0e42
```

Propiedades que importan aquí:

| Propiedad | Qué significa en la práctica |
|---|---|
| **Determinista** | El mismo contenido produce siempre el mismo hash, en cualquier equipo y en cualquier momento. |
| **Sensible a cualquier cambio** | Cambiar un solo bit del archivo produce un hash completamente distinto (efecto avalancha). |
| **Independiente del nombre y la ubicación** | Solo cuenta el contenido: el nombre, la carpeta y las fechas del archivo no entran en el cálculo. |
| **Resistente a colisiones** | Es prácticamente imposible que dos contenidos distintos den el mismo hash (ver sección 4). |

Por eso, comparar hashes equivale a comparar los archivos byte por byte, pero mucho más
rápido: se calcula una sola vez por archivo y luego se comparan textos de 64 caracteres.

## 2. Procedimiento

### 2.1 Cálculo del hash durante la ingesta (`POST /ingesta/runs`)

Por cada archivo nuevo de `data/base/` (`domain/organization.py` → `LocalFileAdapter.copy_from`, en
`adapters/local_files.py`):

1. Se copia a su carpeta provisional de `data/ingesta/<categoria>/<tipo>/` con un nombre temporal `*.parcial`.
2. Se calcula el SHA-256 **de la copia ya escrita** (`hashlib.file_digest`, biblioteca estándar de Python), no del
   original. Así el hash describe exactamente lo que quedó en la ingesta. (Si el origen no es una carpeta local, el
   hash se calcula bloque a bloque mientras se escribe la copia.)
3. Se renombra la copia a su nombre final (operación atómica: nunca queda un archivo a medias con el nombre
   definitivo).
4. Se guarda el registro en la memoria SQLite (`data/ingesta/.memoria.sqlite3`), columna `sha256`.

Si algún registro antiguo no tiene hash (memorias de versiones anteriores), `Organization.fill_hashes` lo calcula
leyendo el archivo de la ingesta, al principio de la corrida siguiente.

### 2.2 Agrupación de duplicados (`domain/duplicates.py`)

1. Se consultan en la memoria los registros cuyo `sha256` aparece más de una vez (`with_repeated_hash`).
2. Se agrupan por hash: cada grupo es un conjunto de archivos con contenido idéntico (`Duplicates.group`).
3. Se **excluyen los archivos de 0 bytes**: todos los vacíos comparten el mismo hash y formarían un grupo falso de
   "duplicados" que en realidad no son documentos.
4. En cada grupo, el **original** (el que queda) es el **más nuevo**: el de mayor `Duplicates.newness_key` (última
   modificación del original; si empatan, la carpeta más reciente —año, mes, semana, con orden natural— y la ruta). El
   resto son **copias**: reciben la categoría `hash_duplicado` y van a `data/ingesta/hash_duplicados/<tipo>/`
   (`Classifier.hash_duplicates`, que reclasifica todo el corpus en cada corrida).
5. Los grupos se ordenan por espacio recuperable (tamaño × número de copias).

El resultado sale en el resumen de cada corrida (`GET /ingesta/runs/{id}`: `resultado.duplicados` y
`duplicados_nuevos`) y se consulta con `GET /ingesta/stats/duplicates` (el `duplicados.csv` y el `reporte.html` de
antes se quitaron en la feature 029).

## 3. Resultado sobre los datos actuales

Corrida del 2026-10-13 sobre `data/base/`:

| Concepto | Valor |
|---|---|
| Archivos ingeridos | 22.056 |
| Grupos de duplicados | 1.002 |
| Copias sobrantes | 8.784 (≈ 40 %) |
| Espacio recuperable | 705,9 MB |
| Contenidos distintos | 13.272 (13.259 hashes distintos + 13 archivos vacíos, que no se agrupan) |

## 4. Por qué es confiable

### 4.1 Probabilidad de colisión despreciable

Una colisión sería que dos archivos **distintos** den el mismo hash. SHA-256 tiene
2²⁵⁶ ≈ 1,16 × 10⁷⁷ valores posibles. Por la "paradoja del cumpleaños", la probabilidad
de que exista al menos una colisión entre *n* archivos es aproximadamente
*n*² / 2²⁵⁷. Con *n* = 22.056:

```
p ≈ 22.056² / 2²⁵⁷ ≈ 4,9 × 10⁸ / 2,3 × 10⁷⁷ ≈ 2 × 10⁻⁶⁹
```

Es un número tan pequeño que, en la práctica, es cero: es muchísimo más probable un error
de hardware al leer el disco que una colisión. Hasta hoy no se conoce ninguna colisión de
SHA-256, ni accidental ni provocada; es el mismo algoritmo que usan Git, los
certificados TLS y las firmas de paquetes de software para garantizar integridad.

### 4.2 Es conservador: no inventa duplicados

El método solo marca como duplicados archivos **idénticos byte a byte**. Si dos
documentos se parecen pero difieren en un solo byte (por ejemplo, el mismo PDF
re-exportado, o un Word guardado de nuevo con otra fecha en sus metadatos), tendrán
hashes distintos y **no** se agruparán. Es decir:

- **Falsos positivos** (marcar como iguales dos archivos distintos): prácticamente
  imposibles (sección 4.1).
- **Falsos negativos** (no detectar documentos "casi iguales"): posibles y esperables;
  el método no pretende detectar similitud de contenido, solo igualdad exacta.

### 4.3 El hash corresponde a lo que realmente está en disco

El hash se calcula sobre la copia escrita en la ingesta, después de copiarla y antes de
registrarla. Si la copia falla a medias, se borra y no se registra nada, así que no
puede haber un hash en la memoria que no corresponda a un archivo completo.

### 4.4 Verificación empírica

Además de la teoría, se comprobó directamente sobre los datos (2026-10-13):

| Verificación | Resultado |
|---|---|
| Comparación **byte por byte** de cada copia contra el original de su grupo (con el `duplicados.csv` de entonces) | **8.784 / 8.784 idénticos**, 0 diferencias, 0 archivos faltantes |
| Recalcular el SHA-256 de una muestra aleatoria de 500 archivos de la ingesta y compararlo con el guardado en la memoria | **500 / 500 coinciden** |
| Registros de la memoria con hash calculado | 22.056 / 22.056 |

Es decir, todos los duplicados reportados son realmente idénticos, y los hashes
almacenados corresponden al contenido actual de los archivos.

## 5. Implicaciones para el parseo y el chunking

Como el 40 % de los archivos son copias exactas, se procesa con Docling **solo un archivo por hash**: las copias
nunca son aptas para chunking (`apto_chunking`), así que cada contenido tiene a lo sumo un archivo apto. Por eso:

- ingesta publica en `data` **un nodo `RAW` por contenido**, con `id` = `sha256` (feature 042); un archivo nuevo con
  el mismo contenido es el mismo `RAW`;
- el `sha256` es el identificador estable del documento en todo el grafo: el `JSON` de `parsing`, los ids de sus
  `SECCION` y `FRAGMENTOS` (`<sha256>:s<n>`, `<sha256>:<k>`) y lo que el pipeline pasa de un módulo a otro;
- se evita generar fragmentos repetidos que sesgarían búsquedas o embeddings, y se ahorra tiempo (≈ 13.272 documentos
  en lugar de 22.056);
- si un archivo vuelve a llegar con otro nombre, ya se sabe que su contenido fue parseado y fragmentado.

"""The console's Spanish texts (feature 035: the console's interface is in Spanish, an exception to feature 019): what
each module, resource and action is called and what it does. A route without an entry here still shows up, with the
summary and description of its openapi.json."""

from dataclasses import dataclass

READS = "Solo lee: no cambia nada."
_VERBS = {"GET": "Ver", "POST": "Crear", "PUT": "Reemplazar", "PATCH": "Modificar", "DELETE": "Borrar"}
_WRITES = {
    "POST": "Escribe: crea o lanza algo.",
    "PUT": "Escribe: reemplaza lo que hay.",
    "PATCH": "Escribe: cambia solo lo que se envía.",
    "DELETE": "Escribe: borra.",
}


@dataclass(frozen=True)
class Text:
    name: str
    description: str


MODULES: dict[str, Text] = {
    "ingesta": Text("ingesta", "El corpus: archivos aptos, estadísticas, revisión del origen y corridas."),
    "data": Text("data", "El grafo PIAA en Neo4j: esquema, nodos, relaciones y cargas por lote."),
    "parsing": Text("parseo", "Docling con una configuración fija: los archivos RAW de data pasan a JSON en data."),
    "chunking": Text(
        "chunking", "Docling: experimentos de chunking, configuración activa y corridas sobre lo oficial."
    ),
    "llm": Text("llm", "Los modelos de lenguaje en Ollama: modelos admitidos, descargas, configuración activa y chat."),
    "embeddings": Text("embeddings", "Vectores de los chunks oficiales y de experimentos, en data; texto a vector."),
    "pipeline": Text("pipeline", "Plantillas de etapas, corridas del pipeline, lo que espera a cada actor."),
    "consultas": Text("consultas", "Preguntas respondidas con los documentos oficiales, citando sus fuentes, y chats."),
}

PROCESSES = Text("procesos", "Qué está en curso, en cola o terminado, en vivo.")
RESOURCES: dict[tuple[str, str], Text] = {
    ("ingesta", "processes"): PROCESSES,
    ("chunking", "processes"): PROCESSES,
    ("parsing", "processes"): PROCESSES,
    ("parsing", "health"): Text("estado", "Si Docling y el OCR están instalados y si data responde."),
    ("parsing", "config"): Text("configuración", "La configuración fija del parseo y la huella que da."),
    ("parsing", "runs"): Text("corridas", "Parsear unos sha256 o todo lo que falte (leído de data) y seguir."),
    ("parsing", "preview"): Text("vista previa", "Leer un documento con la misma configuración, sin guardar nada."),
    ("pipeline", "processes"): PROCESSES,
    ("embeddings", "processes"): PROCESSES,
    ("embeddings", "health"): Text("estado", "Si torch y transformers están instalados y si data responde."),
    ("embeddings", "models"): Text("modelos", "Los modelos de vectores, sus dimensiones y sus límites de tokens."),
    ("embeddings", "config"): Text("configuración activa", "Con qué modelo y límite se embebe y se busca."),
    ("embeddings", "runs"): Text("corridas", "Embeber los chunks oficiales de unos documentos y seguir."),
    ("embeddings", "experiments"): Text(
        "experimentos", "Embeber los chunks de un experimento de chunking con otro modelo o límite."
    ),
    ("llm", "processes"): PROCESSES,
    ("llm", "health"): Text("estado", "Si Ollama responde (y su versión) y si data responde."),
    ("llm", "models"): Text("modelos", "Los admitidos, los que Ollama tiene, descargarlos y quitarlos."),
    ("llm", "config"): Text("configuración activa", "Modelo, temperatura, contexto, largo de respuesta y prompt."),
    ("llm", "chat"): Text("chat", "Mandar mensajes (e imágenes, con un modelo de visión) y leer la respuesta."),
    ("embeddings", "vectors"): Text("vectores", "Convertir textos en vectores con el modelo activo."),
    ("consultas", "health"): Text("estado", "Si embeddings, llm, data y parsing (para adjuntos) responden."),
    ("consultas", "search"): Text("búsqueda", "Los fragmentos más parecidos a una pregunta, sin LLM."),
    ("consultas", "ask"): Text("preguntar", "Una pregunta respondida por el LLM con los fragmentos como fuentes."),
    ("consultas", "chats"): Text("chats", "Las conversaciones guardadas, con sus preguntas y fuentes."),
    ("consultas", "config"): Text("configuración activa", "k, puntaje mínimo, prompt y turnos de historia."),
    ("ingesta", "health"): Text("estado", "Si la memoria de ingesta responde."),
    ("ingesta", "data"): Text("archivos aptos", "Los archivos listos para parsear, con filtros; uno y su contenido."),
    ("ingesta", "stats"): Text("estadísticas", "Del corpus: resumen, tipos, años, duplicados, vacíos, códigos..."),
    ("ingesta", "source"): Text("origen", "Revisa data/base/: si existe, qué tiene y qué hay nuevo."),
    ("ingesta", "runs"): Text(
        "corridas", "Lanzar una ingesta (copia lo nuevo, reclasifica y sube los aptos a data) y seguirla."
    ),
    ("ingesta", "uploads"): Text(
        "subidas", "Los archivos subidos a data/base/ por la API; subir es desde la API o el front, no la consola."
    ),
    ("data", "health"): Text("estado", "Si Neo4j responde."),
    ("data", "schema"): Text("esquema", "Las etiquetas y las relaciones que admite el grafo."),
    ("data", "nodes"): Text("nodos", "Listar, ver, crear, modificar y borrar nodos de una etiqueta."),
    ("data", "relationships"): Text("relaciones", "Listar, ver, crear, modificar y borrar relaciones de un tipo."),
    ("data", "batch"): Text("lote", "Escribir varios nodos y relaciones en una sola transacción."),
    ("data", "progress"): Text(
        "avance", "Cuántos archivos están parseados y cuántos documentos chunkeados; cuáles faltan."
    ),
    ("data", "vectors"): Text("vectores", "Los índices vectoriales que pide embeddings y la búsqueda por similitud."),
    ("chunking", "health"): Text("estado", "Si docling-core está instalado y si data responde."),
    ("chunking", "experiments"): Text(
        "experimentos", "Chunkear documentos parseados con una configuración, aparte de lo oficial, y comparar."
    ),
    ("chunking", "config"): Text(
        "configuración activa", "Con qué chunkean las corridas: verla, cambiarla o volver a la de defecto."
    ),
    ("chunking", "runs"): Text(
        "corridas", "Chunkear con la configuración activa unos sha256 o lo que falta (o una página) y seguir; retomar."
    ),
    ("pipeline", "health"): Text("estado", "Si ingesta, parsing, chunking, embeddings, llm y data responden."),
    ("pipeline", "actions"): Text("acciones", "Las acciones que puede tener una etapa y qué necesitan y dan."),
    ("pipeline", "pipelines"): Text(
        "plantillas", "Las plantillas de etapas (produccion, laboratorio y las propias) y su orden."
    ),
    ("pipeline", "runs"): Text("corridas", "Lanzar y seguir corridas del pipeline; decidir y completar etapas."),
    ("pipeline", "inbox"): Text("bandeja", "Lo que está esperando a cada actor."),
    ("pipeline", "actors"): Text("actores", "Los actores y la URL donde se les avisa."),
}


ACTIONS: dict[tuple[str, str, str], Text] = {
    # ingesta
    ("ingesta", "GET", "/health"): Text("ver estado", "La versión y si la memoria responde."),
    ("ingesta", "GET", "/data"): Text("listar aptos", "Los archivos aptos para parsear; los filtros se combinan."),
    ("ingesta", "GET", "/data/file"): Text("ver un archivo", "El registro de un archivo apto, por origen o sha256."),
    ("ingesta", "GET", "/data/content"): Text("ver contenido", "El archivo en sí (se muestra su tipo y tamaño)."),
    ("ingesta", "GET", "/stats"): Text("todas", "Todas las secciones de estadísticas a la vez (grande)."),
    ("ingesta", "GET", "/stats/summary"): Text("resumen", "Totales de archivos, bytes, códigos y tipos."),
    ("ingesta", "GET", "/stats/types"): Text("tipos", "Los tipos de archivo y su distribución de tamaños."),
    ("ingesta", "GET", "/stats/types/{file_type}"): Text("un tipo", "Tamaños, años, copias y vacíos de un tipo."),
    ("ingesta", "GET", "/stats/years"): Text("años", "Por año y comparación entre años."),
    ("ingesta", "GET", "/stats/years/{year}"): Text("un año", "Archivos y bytes por tipo y por mes de un año."),
    ("ingesta", "GET", "/stats/duplicates"): Text("duplicados", "Duplicados por contenido: grupos, copias, espacio."),
    ("ingesta", "GET", "/stats/empty"): Text("vacíos", "Archivos vacíos o casi vacíos por tipo."),
    ("ingesta", "GET", "/stats/codes"): Text("códigos duplicados", "Códigos con más archivos, de más a menos."),
    ("ingesta", "GET", "/stats/repeated"): Text("PIAA repetidos", "Códigos con dos o más archivos en un mismo año."),
    ("ingesta", "GET", "/stats/repeated/{year}"): Text("PIAA repetidos de un año", "Los repetidos de un año."),
    ("ingesta", "GET", "/stats/cleanup"): Text("embudo", "Cuántos salen en cada paso de la clasificación."),
    ("ingesta", "GET", "/source"): Text("revisar origen", "Si data/base/ existe, qué tiene y qué hay nuevo."),
    ("ingesta", "GET", "/runs"): Text("listar corridas", "Las ingestas de esta sesión del servidor."),
    ("ingesta", "POST", "/runs"): Text(
        "lanzar ingesta",
        "Copia lo nuevo de data/base/ a data/ingesta/, reclasifica todo y sube a data (RAW) los aptos que falten; "
        "el origen nunca se toca. Con simulate solo dice qué haría.",
    ),
    ("ingesta", "GET", "/runs/{id}"): Text("ver corrida", "Estado, progreso, resultado y errores de una ingesta."),
    ("ingesta", "GET", "/uploads"): Text("listar subidas", "Lo subido por la API a data/base/, lo más nuevo primero."),
    ("ingesta", "POST", "/uploads"): Text(
        "subir archivos",
        "Guarda pdf/doc/docx en data/base/<año>/<mes>/<semana>/<código>/ (multipart: files y code); no lanza la "
        "ingesta. Solo desde la API o el front (http/ingesta/uploads.http): la consola no envía archivos.",
    ),
    # parsing (feature 042)
    ("parsing", "GET", "/health"): Text("ver estado", "Docling, el motor de OCR, LibreOffice y si data responde."),
    ("parsing", "GET", "/config"): Text(
        "ver configuración", "Lo que usa todo parseo (tablas, títulos, OCR...); no se pide en una corrida."
    ),
    ("parsing", "POST", "/runs"): Text(
        "parsear",
        "Parsea esos sha256, o sin ellos todos los RAW vigentes que falten, y deja su JSON en data; salta lo ya "
        "hecho (redo lo rehace) y sigue los parciales. Con simulate solo dice qué haría.",
    ),
    ("parsing", "GET", "/runs"): Text("listar corridas", "Las corridas de parseo, también las de antes de reiniciar."),
    ("parsing", "GET", "/runs/{id}"): Text("ver corrida", "Estado, avance, cada documento y los sha256 parseados."),
    ("parsing", "DELETE", "/runs/{id}"): Text("sacar de la fila", "Saca una corrida en cola; la que corre sigue."),
    ("parsing", "GET", "/processes"): Text("ver procesos", "Las corridas de parseo en vivo y las terminadas."),
    ("parsing", "POST", "/preview"): Text(
        "vista previa",
        "Parsea un documento (name, content en base64, mime) con la configuración fija y devuelve su texto por "
        "secciones, sin guardar nada: no entra al corpus (eso es la 049). De un PDF, solo sus primeras páginas.",
    ),
    # data
    ("data", "GET", "/health"): Text("ver estado", "Si Neo4j responde."),
    ("data", "GET", "/schema"): Text("ver esquema", "Las etiquetas y las relaciones permitidas."),
    ("data", "GET", "/nodes/{label}"): Text("listar nodos", "Los nodos de una etiqueta, ordenados por id."),
    ("data", "POST", "/nodes/{label}"): Text("crear nodo", "Crea un nodo con sus propiedades."),
    ("data", "GET", "/nodes/{label}/{id}"): Text("ver nodo", "Un nodo con sus propiedades."),
    ("data", "PUT", "/nodes/{label}/{id}"): Text("reemplazar propiedades", "Las que no se envían se borran."),
    ("data", "PATCH", "/nodes/{label}/{id}"): Text("modificar propiedades", "Solo las enviadas; null borra una."),
    ("data", "DELETE", "/nodes/{label}/{id}"): Text("borrar nodo", "Borra el nodo y todas sus relaciones."),
    ("data", "GET", "/nodes/{label}/{id}/relationships"): Text("relaciones del nodo", "Las que entran y salen."),
    ("data", "POST", "/relationships"): Text("crear relación", "Une dos nodos existentes con un tipo permitido."),
    ("data", "GET", "/relationships/{type}"): Text("listar relaciones", "Las relaciones de un tipo."),
    ("data", "GET", "/relationships/{type}/{source_label}/{source_id}/{target_label}/{target_id}"): Text(
        "ver relación", "Una relación con sus propiedades."
    ),
    ("data", "PUT", "/relationships/{type}/{source_label}/{source_id}/{target_label}/{target_id}"): Text(
        "reemplazar propiedades", "Las que no se envían se borran."
    ),
    ("data", "PATCH", "/relationships/{type}/{source_label}/{source_id}/{target_label}/{target_id}"): Text(
        "modificar propiedades", "Solo las enviadas; null borra una."
    ),
    ("data", "DELETE", "/relationships/{type}/{source_label}/{source_id}/{target_label}/{target_id}"): Text(
        "borrar relación", "Borra la relación; los nodos quedan."
    ),
    ("data", "GET", "/progress/parsing"): Text(
        "avance del parseo",
        "De los RAW vigentes: parseados, parciales, con error y nunca parseados, y cuáles faltan (list=done: los "
        "hechos). Con fingerprint (el de GET /parsing/config), uno parseado con otra huella cuenta como faltante.",
    ),
    ("data", "GET", "/progress/chunking"): Text(
        "avance del chunking",
        "De los JSON parseados: con chunks, con error y nunca chunkeados, y cuáles faltan (list=done: los hechos). "
        "Con fingerprint (el de GET /chunking/config), uno chunkeado con otra configuración cuenta como faltante.",
    ),
    ("data", "POST", "/batch"): Text(
        "escribir lote",
        "Varios nodos y relaciones en una transacción; replace_from borra antes lo que cuelga de ese nodo.",
    ),
    ("data", "PUT", "/vectors/indexes/{name}"): Text(
        "asegurar índice",
        "Crea el índice vectorial (coseno) en la propiedad de un modelo (embedding_<modelo>_<dim>) si falta; uno igual "
        "se deja como está.",
    ),
    ("data", "GET", "/vectors/indexes/{name}"): Text("ver índice", "Su etiqueta, propiedad y dimensiones."),
    ("data", "DELETE", "/vectors/indexes/{name}"): Text(
        "borrar índice",
        "Quita el índice; con drop_property también la propiedad de sus nodos (los vectores de ese modelo).",
    ),
    ("data", "POST", "/vectors/search"): Text(
        "buscar por vector",
        "Los FRAGMENTOS de documentos chunkeados más cercanos a un vector, el mejor primero; con experiment, los "
        "EXP_CHUNK de ese experimento de embeddings (índice de EXP_EMBED).",
    ),
    # embeddings (feature 046)
    ("embeddings", "GET", "/health"): Text("ver estado", "torch, transformers y si data responde (no carga modelos)."),
    ("embeddings", "GET", "/models"): Text(
        "listar modelos",
        "Cada modelo con sus dimensiones y sus límites (cuentan los 2 tokens especiales); con documents, cuántos "
        "documentos oficiales tienen sus vectores (lento).",
    ),
    ("embeddings", "DELETE", "/models/{name}/vectors"): Text(
        "borrar vectores de un modelo",
        "Quita los vectores oficiales de un modelo que no es el activo: su huella en cada JSON, su índice y su "
        "propiedad. Los de experimentos quedan.",
    ),
    ("embeddings", "GET", "/config"): Text("ver configuración", "La activa, de dónde salió y la de defecto."),
    ("embeddings", "PUT", "/config"): Text("reemplazar configuración", "Modelo y límite; sin límite, el del modelo."),
    ("embeddings", "PATCH", "/config"): Text("modificar configuración", "Solo lo enviado; lo demás queda como está."),
    ("embeddings", "DELETE", "/config"): Text("volver a la de defecto", "Borra la configuración puesta."),
    ("embeddings", "POST", "/runs"): Text(
        "embeber documentos",
        "Calcula los vectores de los FRAGMENTOS de esos sha256 chunkeados con la configuración activa (o, con model, "
        "otro modelo al lado del activo, para cambiar de modelo sin cortar el chat); salta lo que no cambió (force lo "
        "rehace). Un chunk más largo que el límite hace fallar su documento. Con simulate solo cuenta.",
    ),
    ("embeddings", "GET", "/runs"): Text("listar corridas", "La más nueva primero, también las de antes de reiniciar."),
    ("embeddings", "GET", "/runs/{id}"): Text("ver corrida", "Estado, avance, fallos y los sha256 con vectores."),
    ("embeddings", "DELETE", "/runs/{id}"): Text("sacar de la fila", "Saca una corrida en cola; la que corre sigue."),
    ("embeddings", "POST", "/experiments"): Text(
        "lanzar experimento",
        "Embebe los EXP_CHUNK de un experimento de chunking terminado con un modelo y un límite, un EXP_EMBED por "
        "chunk (varios experimentos sobre los mismos chunks conviven), sin tocar lo oficial. Con simulate solo cuenta.",
    ),
    ("embeddings", "GET", "/experiments"): Text("listar experimentos", "También los de antes de reiniciar."),
    ("embeddings", "GET", "/experiments/{id}"): Text("ver experimento", "Modelo, límite, avance y fallos."),
    ("embeddings", "DELETE", "/experiments/{id}"): Text(
        "borrar experimento", "Borra su registro y sus EXP_EMBED; los chunks y los vectores de otros quedan."
    ),
    ("embeddings", "POST", "/experiments/{id}/apply"): Text(
        "aplicar configuración", "Copia su modelo y límite a la activa; no embebe nada."
    ),
    ("embeddings", "POST", "/vectors"): Text(
        "convertir en vectores", "Un vector por texto con el modelo activo (o el de model) y los índices de ese modelo."
    ),
    # consultas (feature 048)
    ("consultas", "GET", "/health"): Text("ver estado", "Si embeddings, llm, data y parsing (adjuntos) responden."),
    ("consultas", "POST", "/search"): Text(
        "buscar",
        "La pregunta como vector y los fragmentos más parecidos, con su puntaje; no llama al LLM ni guarda. Con "
        "attachments (JSON: [{name, content en base64, mime}]), también buscan los documentos e imágenes adjuntos.",
    ),
    ("consultas", "POST", "/ask"): Text(
        "preguntar",
        "Responde con los fragmentos que pasan el puntaje mínimo y los cita; si ninguno pasa, dice que no encontró "
        "y no llama al LLM. Guarda la pregunta en su chat (con against, como laboratorio). Con attachments, "
        "responde qué se parece a los documentos o imágenes adjuntos; nunca los guarda, solo sus nombres.",
    ),
    ("consultas", "GET", "/chats"): Text("listar chats", "El modificado más reciente primero."),
    ("consultas", "GET", "/chats/{id}"): Text("ver chat", "Sus preguntas, respuestas y los fragmentos citados."),
    ("consultas", "DELETE", "/chats/{id}"): Text("borrar chat", "El chat y sus preguntas; los fragmentos quedan."),
    ("consultas", "GET", "/config"): Text("ver configuración", "La activa, de dónde salió y la de defecto."),
    ("consultas", "PUT", "/config"): Text("reemplazar configuración", "Lo que no se envía toma el valor de defecto."),
    ("consultas", "PATCH", "/config"): Text("modificar configuración", "Solo lo enviado; lo demás queda como está."),
    ("consultas", "DELETE", "/config"): Text("volver a la de defecto", "Borra la configuración puesta."),
    ("embeddings", "GET", "/processes"): PROCESSES,
    # llm (feature 047)
    ("llm", "GET", "/health"): Text("ver estado", "Si Ollama responde, su versión y su URL, y si data responde."),
    ("llm", "GET", "/models"): Text(
        "listar modelos", "Los admitidos (contexto, visión, si están descargados) y todo lo que Ollama tiene."
    ),
    ("llm", "POST", "/models/pull"): Text(
        "descargar modelo", "Descarga en Ollama un modelo admitido, en segundo plano: se sigue en procesos."
    ),
    ("llm", "GET", "/models/pulls"): Text("listar descargas", "Las descargas de esta sesión, la más nueva primero."),
    ("llm", "GET", "/models/pulls/{id}"): Text("ver descarga", "Estado, paso de Ollama y bytes de la capa en curso."),
    ("llm", "DELETE", "/models/{name}"): Text(
        "quitar modelo", "Lo borra de Ollama; nunca el de la configuración activa."
    ),
    ("llm", "GET", "/config"): Text("ver configuración", "La activa, de dónde salió y la de defecto."),
    ("llm", "PUT", "/config"): Text("reemplazar configuración", "Modelo y valores; lo que falta, el de defecto."),
    ("llm", "PATCH", "/config"): Text("modificar configuración", "Solo lo enviado; lo demás queda como está."),
    ("llm", "DELETE", "/config"): Text("volver a la de defecto", "Borra la configuración puesta."),
    ("llm", "POST", "/chat"): Text(
        "conversar",
        "Manda los mensajes al modelo y trae su respuesta; lo que no se envía sale de la configuración activa. "
        "Imágenes (base64) solo con un modelo de visión.",
    ),
    ("llm", "GET", "/processes"): PROCESSES,
    # chunking
    ("chunking", "GET", "/health"): Text("ver estado", "docling-core y si data responde."),
    ("chunking", "GET", "/experiments"): Text("listar experimentos", "Todos los experimentos del grafo."),
    ("chunking", "POST", "/experiments"): Text(
        "lanzar experimento",
        "Chunkea con Docling los documentos parseados elegidos (sha256) con una configuración; queda en etiquetas "
        "EXP_*, sin tocar lo oficial. Con simulate solo dice cuáles entrarían.",
    ),
    ("chunking", "GET", "/experiments/{id}"): Text(
        "ver experimento", "Configuración, progreso, resultados y qué documentos chunkeó."
    ),
    ("chunking", "DELETE", "/experiments/{id}"): Text(
        "borrar experimento", "Borra sus secciones y chunks; los JSON quedan."
    ),
    ("chunking", "POST", "/experiments/{id}/apply"): Text(
        "aplicar configuración", "Copia la configuración de un experimento terminado a la activa; no chunkea nada."
    ),
    ("chunking", "POST", "/experiments/{id}/resume"): Text(
        "retomar experimento",
        "Uno parcial, fallido o interrumpido: chunkea con su configuración solo los documentos que no alcanzó.",
    ),
    ("chunking", "GET", "/config"): Text("ver configuración", "La activa, de dónde salió y lo que es fijo."),
    ("chunking", "PUT", "/config"): Text("reemplazar configuración", "Lo no enviado toma el valor por defecto."),
    ("chunking", "PATCH", "/config"): Text("modificar configuración", "Solo lo enviado; lo demás queda como está."),
    ("chunking", "DELETE", "/config"): Text("volver a la de defecto", "Borra la configuración puesta."),
    ("chunking", "POST", "/runs"): Text(
        "lanzar corrida",
        "Chunkea con la configuración activa los sha256 elegidos o, sin ellos, lo que falta (page y per_page: una "
        "página) y reemplaza sus SECCION/FRAGMENTOS. Lo ya hecho con esa configuración se salta. Con simulate solo "
        "cuenta.",
    ),
    ("chunking", "GET", "/runs"): Text("listar corridas", "La más nueva primero, también las de antes."),
    ("chunking", "GET", "/runs/{id}"): Text("ver corrida", "Estado, contadores, fallos y qué se chunkeó."),
    ("chunking", "DELETE", "/runs/{id}"): Text("sacar de la fila", "Solo una que espera su turno."),
    ("chunking", "POST", "/runs/{id}/resume"): Text(
        "retomar corrida",
        "Una parcial, fallida o interrumpida, si la configuración activa no cambió: solo lo que falló o no alcanzó.",
    ),
    # pipeline
    ("pipeline", "GET", "/health"): Text(
        "ver estado", "Si ingesta, parsing, chunking, embeddings, llm y data responden."
    ),
    ("pipeline", "GET", "/actions"): Text("listar acciones", "Cada acción con su tipo y lo que necesita y da."),
    ("ingesta", "GET", "/processes"): PROCESSES,
    ("chunking", "GET", "/processes"): PROCESSES,
    ("pipeline", "GET", "/processes"): PROCESSES,
    ("pipeline", "POST", "/pipelines/check"): Text(
        "revisar etapas", "Si estas etapas pueden correr en ese orden; no guarda nada."
    ),
    ("pipeline", "GET", "/pipelines"): Text(
        "listar plantillas", "produccion y laboratorio primero; luego las propias."
    ),
    ("pipeline", "POST", "/pipelines"): Text("crear plantilla", "Una plantilla nueva con sus etapas."),
    ("pipeline", "GET", "/pipelines/{id}"): Text("ver plantilla", "Sus etapas en orden."),
    ("pipeline", "PUT", "/pipelines/{id}"): Text("reemplazar plantilla", "Nombre, descripción y etapas."),
    ("pipeline", "DELETE", "/pipelines/{id}"): Text(
        "borrar plantilla", "produccion y laboratorio no se pueden borrar."
    ),
    ("pipeline", "PUT", "/pipelines/{id}/stages"): Text("reordenar etapas", "Todas las etapas en el orden nuevo."),
    ("pipeline", "POST", "/pipelines/{id}/stages/{stage}/move"): Text(
        "mover etapa", "Pone una etapa justo antes o después de otra."
    ),
    ("pipeline", "POST", "/runs"): Text(
        "lanzar corrida",
        "produccion (scope new o all) o laboratorio (files y el par chunking + embeddings, más llm si se prueba);"
        " con simulate solo muestra el lote.",
    ),
    ("pipeline", "GET", "/runs"): Text("listar corridas", "La más nueva primero; se filtra por estado."),
    ("pipeline", "GET", "/runs/{id}"): Text("ver corrida", "Estado, etapa, lote, iteraciones y eventos."),
    ("pipeline", "POST", "/runs/{id}/stages/{stage}/decision"): Text(
        "decidir",
        "lab puntúa el trío chunking + embeddings + llm y aprueba la iteración o pide repetir con otra"
        " configuración; si solo cambia llm, se reutilizan los experimentos.",
    ),
    ("pipeline", "POST", "/runs/{id}/stages/{stage}/complete"): Text(
        "completar etapa", "El actor de una etapa externa avisa que terminó."
    ),
    ("pipeline", "POST", "/runs/{id}/events"): Text("anotar evento", "Una nota de un actor; no cambia el estado."),
    ("pipeline", "POST", "/runs/{id}/resume"): Text("reanudar", "Repite una corrida fallida o interrumpida."),
    ("pipeline", "POST", "/runs/{id}/cancel"): Text("cancelar", "Cancela la corrida."),
    ("pipeline", "GET", "/inbox"): Text("ver bandeja", "Las etapas que esperan a un actor (o a todos)."),
    ("pipeline", "GET", "/actors"): Text("listar actores", "Cada actor y su URL de aviso."),
    ("pipeline", "PUT", "/actors/{name}"): Text("registrar actor", "Guarda la URL a la que se le avisa (en memoria)."),
}


def module(name: str) -> Text:
    return MODULES.get(name, Text(name, ""))


def resource(module_name: str, segment: str) -> Text:
    return RESOURCES.get((module_name, segment), Text(segment, ""))


def action(module_name: str, method: str, path: str, summary: str, description: str) -> Text:
    """The action's name and what it does; without a curated text, the OpenAPI's (in English)."""
    found = ACTIONS.get((module_name, method, path))
    effect = READS if method == "GET" else _WRITES.get(method, "Escribe.")
    if found is not None:
        return Text(found.name, f"{found.description}\n{effect}")
    name = summary.lower() or f"{_VERBS.get(method, method).lower()} {path}"
    return Text(name, "\n".join(part for part in (description, effect) if part))

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
    "chunking": Text("chunking", "Docling: corridas de chunking, documentos, experimentos, puntuaciones y promoción."),
    "pipeline": Text("pipeline", "Plantillas de etapas, corridas del pipeline, lo que espera a cada actor."),
}

RESOURCES: dict[tuple[str, str], Text] = {
    ("ingesta", "health"): Text("estado", "Si la memoria de ingesta responde."),
    ("ingesta", "data"): Text("archivos aptos", "Los archivos listos para chunking, con filtros; uno y su contenido."),
    ("ingesta", "stats"): Text("estadísticas", "Del corpus: resumen, tipos, años, duplicados, vacíos, códigos..."),
    ("ingesta", "source"): Text("origen", "Revisa data/base/: si existe, qué tiene y qué hay nuevo."),
    ("ingesta", "runs"): Text("corridas", "Lanzar una ingesta (copia lo nuevo y reclasifica) y seguir las corridas."),
    ("data", "health"): Text("estado", "Si Neo4j responde."),
    ("data", "schema"): Text("esquema", "Las etiquetas y las relaciones que admite el grafo."),
    ("data", "nodes"): Text("nodos", "Listar, ver, crear, modificar y borrar nodos de una etiqueta."),
    ("data", "relationships"): Text("relaciones", "Listar, ver, crear, modificar y borrar relaciones de un tipo."),
    ("data", "batch"): Text("lote", "Escribir varios nodos y relaciones en una sola transacción."),
    ("chunking", "health"): Text("estado", "Si Docling está instalado y si ingesta y data responden."),
    ("chunking", "runs"): Text("corridas", "Fragmentar documentos con Docling hacia el grafo de producción."),
    ("chunking", "documents"): Text("documentos", "Los documentos del grafo (fragmentados o en error) y sus chunks."),
    ("chunking", "experiments"): Text(
        "experimentos", "Convertir y fragmentar con un plan, ver resultados, puntuar, comparar y promover."
    ),
    ("pipeline", "health"): Text("estado", "Si ingesta, chunking y data responden."),
    ("pipeline", "actions"): Text("acciones", "Las acciones que puede tener una etapa y qué necesitan y dan."),
    ("pipeline", "pipelines"): Text("plantillas", "Las plantillas de etapas (la piaa y las propias) y su orden."),
    ("pipeline", "runs"): Text("corridas", "Lanzar y seguir corridas del pipeline; decidir y completar etapas."),
    ("pipeline", "inbox"): Text("bandeja", "Lo que está esperando a cada actor."),
    ("pipeline", "actors"): Text("actores", "Los actores y la URL donde se les avisa."),
}

ACTIONS: dict[tuple[str, str, str], Text] = {
    # ingesta
    ("ingesta", "GET", "/health"): Text("ver estado", "La versión y si la memoria responde."),
    ("ingesta", "GET", "/data"): Text("listar aptos", "Los archivos aptos para chunking; los filtros se combinan."),
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
        "Copia lo nuevo de data/base/ a data/ingesta/ y reclasifica todo; el origen nunca se toca. Con simulate solo "
        "dice qué haría.",
    ),
    ("ingesta", "GET", "/runs/{id}"): Text("ver corrida", "Estado, progreso, resultado y errores de una ingesta."),
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
    ("data", "POST", "/batch"): Text(
        "escribir lote",
        "Varios nodos y relaciones en una transacción; replace_from borra antes lo que cuelga de ese nodo.",
    ),
    # chunking
    ("chunking", "GET", "/health"): Text("ver estado", "Docling y si ingesta y data responden."),
    ("chunking", "GET", "/runs"): Text("listar corridas", "Las corridas de esta sesión, la más nueva primero."),
    ("chunking", "POST", "/runs"): Text(
        "lanzar corrida",
        "Fragmenta con Docling los aptos pendientes (o los sha256 elegidos) y los guarda en el grafo. Con simulate "
        "solo cuenta.",
    ),
    ("chunking", "GET", "/runs/{id}"): Text("ver corrida", "Estado, contadores y fallos de una corrida."),
    ("chunking", "GET", "/documents"): Text("listar documentos", "Los documentos del grafo, fragmentados o en error."),
    ("chunking", "GET", "/documents/{sha256}"): Text("ver documento", "Un documento con los parámetros usados."),
    ("chunking", "GET", "/documents/{sha256}/chunks"): Text("ver chunks", "Sus secciones y chunks, en orden."),
    ("chunking", "GET", "/experiments"): Text("listar experimentos", "Todos los experimentos del grafo."),
    ("chunking", "POST", "/experiments"): Text(
        "lanzar experimento",
        "Convierte los archivos elegidos y los parte por secciones con el plan; todo queda en etiquetas EXP_*, sin "
        "tocar producción. Con simulate solo dice qué haría.",
    ),
    ("chunking", "GET", "/experiments/compare"): Text("comparar", "Varios experimentos lado a lado."),
    ("chunking", "GET", "/experiments/{id}"): Text("ver experimento", "Petición, progreso y resultados."),
    ("chunking", "DELETE", "/experiments/{id}"): Text(
        "borrar experimento", "Borra sus secciones, chunks y puntuaciones; nunca las conversiones."
    ),
    ("chunking", "POST", "/experiments/{id}/promote"): Text(
        "promover", "Pasa al grafo oficial la conversión o los chunks de un experimento terminado."
    ),
    ("chunking", "GET", "/experiments/{id}/documents"): Text("documentos del experimento", "Cómo le fue a cada uno."),
    ("chunking", "GET", "/experiments/{id}/documents/{sha256}"): Text(
        "ver documento del experimento", "Su conversión y sus secciones."
    ),
    ("chunking", "GET", "/experiments/{id}/documents/{sha256}/chunks"): Text(
        "chunks del documento", "Los chunks del documento en el experimento, por sección."
    ),
    ("chunking", "POST", "/experiments/{id}/scores"): Text("puntuar", "Agrega una puntuación con criterios libres."),
    ("chunking", "GET", "/experiments/{id}/scores"): Text("listar puntuaciones", "Con el promedio por criterio."),
    ("chunking", "GET", "/experiments/{id}/scores/{score_id}"): Text("ver puntuación", "Una puntuación."),
    ("chunking", "PUT", "/experiments/{id}/scores/{score_id}"): Text(
        "reemplazar puntuación", "Lo no enviado se vacía."
    ),
    ("chunking", "PATCH", "/experiments/{id}/scores/{score_id}"): Text(
        "modificar puntuación", "Solo lo enviado; un criterio en null se borra."
    ),
    ("chunking", "DELETE", "/experiments/{id}/scores/{score_id}"): Text("borrar puntuación", "La borra."),
    # pipeline
    ("pipeline", "GET", "/health"): Text("ver estado", "Si ingesta, chunking y data responden."),
    ("pipeline", "GET", "/actions"): Text("listar acciones", "Cada acción con su tipo y lo que necesita y da."),
    ("pipeline", "GET", "/pipelines"): Text("listar plantillas", "La piaa primero y luego las propias."),
    ("pipeline", "POST", "/pipelines"): Text("crear plantilla", "Una plantilla nueva con sus etapas."),
    ("pipeline", "GET", "/pipelines/{id}"): Text("ver plantilla", "Sus etapas en orden."),
    ("pipeline", "PUT", "/pipelines/{id}"): Text("reemplazar plantilla", "Nombre, descripción y etapas."),
    ("pipeline", "DELETE", "/pipelines/{id}"): Text("borrar plantilla", "La piaa no se puede borrar."),
    ("pipeline", "PUT", "/pipelines/{id}/stages"): Text("reordenar etapas", "Todas las etapas en el orden nuevo."),
    ("pipeline", "POST", "/pipelines/{id}/stages/{stage}/move"): Text(
        "mover etapa", "Pone una etapa justo antes o después de otra."
    ),
    ("pipeline", "POST", "/runs"): Text(
        "lanzar corrida", "Crea la corrida con una copia de la plantilla y empieza; con simulate solo muestra el lote."
    ),
    ("pipeline", "GET", "/runs"): Text("listar corridas", "La más nueva primero; se filtra por estado."),
    ("pipeline", "GET", "/runs/{id}"): Text("ver corrida", "Estado, etapa, lote, iteraciones y eventos."),
    ("pipeline", "POST", "/runs/{id}/stages/{stage}/decision"): Text(
        "decidir", "El actor del ciclo aprueba una iteración o pide repetir con otra configuración."
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

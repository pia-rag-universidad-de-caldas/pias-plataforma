// Reglas para TS/TSX/JS/JSX con el AST sintáctico de TypeScript.
import ts from "typescript";
import { contieneUtilidades } from "./tailwind.mjs";
import { enModels, enPorts, enUi, esPrueba, extension } from "./rutas.mjs";

const FUNCIONES_DE_CLASES = new Set([
  "cn",
  "clsx",
  "classnames",
  "classNames",
  "cva",
  "twMerge",
  "twJoin",
  "tw",
]);
const ATRIBUTOS_DE_CLASE = new Set(["className", "class", "class:list"]);

// Clases que el framework exige como artefacto (§4.1).
const DECORADORES_FRAMEWORK = new Set([
  "Controller",
  "Module",
  "Injectable",
  "Catch",
  "Resolver",
  "WebSocketGateway",
  "Processor",
]);

function tipoScript(ruta) {
  const ext = extension(ruta);
  if (ext === ".tsx") return ts.ScriptKind.TSX;
  if (ext === ".jsx") return ts.ScriptKind.JSX;
  if ([".js", ".mjs", ".cjs"].includes(ext)) return ts.ScriptKind.JSX;
  return ts.ScriptKind.TS;
}

/** Literales de texto dentro de una expresión, sin entrar en JSX anidado. */
function literales(nodo, salida = []) {
  if (ts.isStringLiteral(nodo) || ts.isNoSubstitutionTemplateLiteral(nodo)) {
    salida.push(nodo);
  } else if (ts.isTemplateExpression(nodo)) {
    salida.push(nodo.head, ...nodo.templateSpans.map((s) => s.literal));
    nodo.templateSpans.forEach((s) => literales(s.expression, salida));
  } else if (
    !ts.isJsxElement(nodo) &&
    !ts.isJsxSelfClosingElement(nodo) &&
    !ts.isJsxFragment(nodo)
  ) {
    ts.forEachChild(nodo, (h) => literales(h, salida));
  }
  return salida;
}

function nombreDecorador(d) {
  const e = d.expression;
  const id = ts.isCallExpression(e) ? e.expression : e;
  return ts.isIdentifier(id) ? id.text : ts.isPropertyAccessExpression(id) ? id.name.text : "";
}

function esClaseDeFramework(nodo) {
  return (ts.getDecorators?.(nodo) ?? []).some((d) =>
    DECORADORES_FRAMEWORK.has(nombreDecorador(d)),
  );
}

function esAliasDeObjeto(tipo) {
  if (ts.isTypeLiteralNode(tipo) || ts.isMappedTypeNode(tipo)) return true;
  if (ts.isIntersectionTypeNode(tipo) || ts.isUnionTypeNode(tipo))
    return tipo.types.some(esAliasDeObjeto);
  if (ts.isParenthesizedTypeNode(tipo)) return esAliasDeObjeto(tipo.type);
  return false;
}

/**
 * Revisa código TS/JS. `desplazamiento` suma líneas cuando el código viene del
 * frontmatter de un .astro.
 */
export function revisarTs(ruta, texto, { desplazamiento = 0, tipo } = {}) {
  const hallazgos = [];
  const sf = ts.createSourceFile(
    ruta,
    texto,
    ts.ScriptTarget.Latest,
    true,
    tipo ?? tipoScript(ruta),
  );
  const lineas = texto.split("\n");
  const fueraDeUi = !enUi(ruta);
  const revisarModelos = !enModels(ruta) && !esPrueba(ruta) && extension(ruta) !== ".d.ts";
  const vistos = new Set();

  const reportar = (regla, nodo, detalle) => {
    const linea = sf.getLineAndCharacterOfPosition(nodo.getStart(sf)).line;
    const clave = `${regla}:${linea}`;
    if (vistos.has(clave)) return;
    vistos.add(clave);
    hallazgos.push({
      regla,
      ruta,
      linea: linea + 1 + desplazamiento,
      fragmento: detalle ?? lineas[linea].trim(),
    });
  };

  const revisarClases = (expresion) => {
    for (const lit of literales(expresion)) {
      if (contieneUtilidades(lit.text)) reportar("tailwind-fuera-de-ui", lit);
    }
  };

  const visitar = (nodo) => {
    if (ts.isJsxAttribute(nodo)) {
      const nombre = nodo.name.getText(sf);
      if (nombre === "style") reportar("estilo-en-linea", nodo);
      else if (fueraDeUi && ATRIBUTOS_DE_CLASE.has(nombre) && nodo.initializer)
        revisarClases(nodo.initializer);
    }

    if (fueraDeUi && ts.isCallExpression(nodo) && ts.isIdentifier(nodo.expression)) {
      if (FUNCIONES_DE_CLASES.has(nodo.expression.text)) nodo.arguments.forEach(revisarClases);
    }

    if (revisarModelos) {
      const nombre = nodo.name?.getText?.(sf);
      if (ts.isInterfaceDeclaration(nodo) && !enPorts(ruta)) {
        reportar("modelo-fuera-de-models", nodo, `interface ${nombre}`);
      } else if (ts.isEnumDeclaration(nodo)) {
        reportar("modelo-fuera-de-models", nodo, `enum ${nombre}`);
      } else if (ts.isTypeAliasDeclaration(nodo) && esAliasDeObjeto(nodo.type) && !enPorts(ruta)) {
        reportar("modelo-fuera-de-models", nodo, `type ${nombre}`);
      } else if (ts.isClassDeclaration(nodo) && !esClaseDeFramework(nodo)) {
        reportar("modelo-fuera-de-models", nodo, `class ${nombre ?? "(anónima)"}`);
      }
    }

    ts.forEachChild(nodo, visitar);
  };

  visitar(sf);
  return hallazgos;
}

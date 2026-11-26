// Crear nodos sin innerHTML: todo lo que viene del servidor entra como texto.

/**
 * h("a", {href: "#x", class: "cite", onclick: fn}, "texto", otroNodo) → el elemento. Un atributo `on*` con una
 * función es un evento; null/false/undefined no se ponen; los hijos null/false se saltan.
 */
export function h(tag, attrs = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs ?? {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on") && typeof value === "function") element.addEventListener(key.slice(2), value);
    else if (key === "class") element.className = value;
    else if (value === true) element.setAttribute(key, "");
    else element.setAttribute(key, String(value));
  }
  append(element, children);
  return element;
}

function append(element, children) {
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : String(child));
  }
}

/** Cambia el contenido de un elemento. */
export function replace(element, ...children) {
  element.replaceChildren();
  append(element, children);
}

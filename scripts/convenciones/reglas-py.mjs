// Reglas para Python: toda clase vive en una carpeta models/.
import { enModels, esPrueba } from "./rutas.mjs";

export function revisarPy(ruta, texto) {
  if (enModels(ruta) || esPrueba(ruta)) return [];
  const hallazgos = [];
  texto.split("\n").forEach((l, i) => {
    const m = /^\s*class\s+(\w+)/.exec(l);
    if (m)
      hallazgos.push({
        regla: "modelo-fuera-de-models",
        ruta,
        linea: i + 1,
        fragmento: `class ${m[1]}`,
      });
  });
  return hallazgos;
}

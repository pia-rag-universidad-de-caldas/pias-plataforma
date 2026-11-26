// Configuración del front (052). Lo que el diálogo «Ajustes» guarda en el navegador tiene prioridad.
export default {
  // URL del servidor único. Vacía: el mismo origen que sirve esta página (`prueba-chunking serve` la sirve en /web/).
  // Otro origen necesita CORS en el servidor (ver spec/features/052-frontend-web/plan.md).
  apiBase: "",
  // Token del cliente `front` (feature 051). Vacío: no se envía cabecera Authorization (el servidor de hoy no la pide).
  token: "",
};

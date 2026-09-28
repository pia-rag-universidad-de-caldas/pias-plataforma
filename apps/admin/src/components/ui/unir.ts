/** Une clases descartando valores vacíos. Solo para uso dentro de components/ui/. */
export function unir(...clases: (string | false | null | undefined)[]): string {
  return clases.filter(Boolean).join(" ");
}

import type { ComponentProps, ReactNode } from "react";
import type { ImageProps } from "next/image";

export interface DocumentoProps {
  lang: string;
  /** Clases de variables de fuente de next/font (p. ej. `geist.variable`). */
  fuentes: string;
  children: ReactNode;
}

export interface BotonEnlaceProps extends Omit<ComponentProps<"a">, "className" | "style"> {
  variante: "primario" | "secundario";
}

export interface ImagenProps extends Omit<ImageProps, "className" | "style"> {
  variante: "logo" | "icono";
}

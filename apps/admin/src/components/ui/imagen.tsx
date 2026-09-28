import Image from "next/image";
import type { ImagenProps } from "./models/props";

const VARIANTES: Record<ImagenProps["variante"], string> = {
  logo: "dark:invert h-5 w-[100px]",
  icono: "dark:invert h-[14px] w-4",
};

export function Imagen({ variante, alt, ...props }: ImagenProps) {
  return <Image {...props} alt={alt} className={VARIANTES[variante]} />;
}

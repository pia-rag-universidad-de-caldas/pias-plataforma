import type { BotonEnlaceProps } from "./models/props";
import { unir } from "./unir";

const VARIANTES: Record<BotonEnlaceProps["variante"], string> = {
  primario: "gap-2 bg-foreground text-background hover:bg-[#383838] dark:hover:bg-[#ccc]",
  secundario:
    "border border-solid border-black/[.08] hover:border-transparent hover:bg-black/[.04] dark:border-white/[.145] dark:hover:bg-[#1a1a1a]",
};

export function BotonEnlace({ variante, ...props }: BotonEnlaceProps) {
  return (
    <a
      {...props}
      className={unir(
        "flex h-12 w-full items-center justify-center rounded-full px-5 transition-colors md:w-[158px]",
        VARIANTES[variante],
      )}
    />
  );
}

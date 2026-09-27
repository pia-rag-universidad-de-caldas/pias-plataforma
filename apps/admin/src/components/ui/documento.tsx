import type { ReactNode } from "react";
import type { DocumentoProps } from "./models/props";
import { unir } from "./unir";

export function Documento({ lang, fuentes, children }: DocumentoProps) {
  return (
    <html lang={lang} className={unir(fuentes, "h-full antialiased")}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}

export function Lienzo({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col flex-1 items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      {children}
    </div>
  );
}

export function Principal({ children }: { children: ReactNode }) {
  return (
    <main className="flex flex-1 w-full max-w-3xl flex-col items-center justify-between py-32 px-16 bg-white dark:bg-black sm:items-start">
      {children}
    </main>
  );
}

export function Encabezado({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-6 text-center sm:items-start sm:text-left">
      {children}
    </div>
  );
}

export function Acciones({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-4 text-base font-medium sm:flex-row">{children}</div>;
}

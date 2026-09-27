import type { ComponentProps, ReactNode } from "react";

export function Titulo({ children }: { children: ReactNode }) {
  return (
    <h1 className="max-w-xs text-3xl font-semibold leading-10 tracking-tight text-black dark:text-zinc-50">
      {children}
    </h1>
  );
}

export function Parrafo({ children }: { children: ReactNode }) {
  return <p className="max-w-md text-lg leading-8 text-zinc-600 dark:text-zinc-400">{children}</p>;
}

export function CodigoEnLinea({ children }: { children: ReactNode }) {
  return (
    <code className="rounded bg-black/[.06] px-1.5 py-0.5 font-mono text-[0.9em] dark:bg-white/[.08]">
      {children}
    </code>
  );
}

export function EnlaceTexto(props: Omit<ComponentProps<"a">, "className" | "style">) {
  return <a {...props} className="font-medium text-zinc-950 dark:text-zinc-50" />;
}

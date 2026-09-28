import { cn } from "../../lib/cn";

export function Vista(props: { className?: string; clase: string }) {
  return (
    <section>
      <div className="flex gap-2">uno</div>
      <div className={props.className}>dos</div>
      <div className={cn("p-4", props.clase)}>tres</div>
      <div className="tarjeta">cuatro</div>
      <p style={{ margin: 0 }}>cinco</p>
    </section>
  );
}

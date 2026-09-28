import { BotonEnlace } from "@/components/ui/boton-enlace";
import { Acciones, Encabezado, Lienzo, Principal } from "@/components/ui/documento";
import { Imagen } from "@/components/ui/imagen";
import { CodigoEnLinea, EnlaceTexto, Parrafo, Titulo } from "@/components/ui/texto";

export default function Home() {
  return (
    <Lienzo>
      <Principal>
        <Imagen
          variante="logo"
          src="/next.svg"
          alt="Next.js logo"
          width={100}
          height={20}
          priority
        />
        <Encabezado>
          <Titulo>
            To get started, edit the <CodigoEnLinea>page.tsx</CodigoEnLinea> file.
          </Titulo>
          <Parrafo>
            Looking for a starting point or more instructions? Head over to{" "}
            <EnlaceTexto href="https://vercel.com/templates?framework=next.js&utm_source=create-next-app&utm_medium=appdir-template-tw&utm_campaign=create-next-app">
              Templates
            </EnlaceTexto>{" "}
            or the{" "}
            <EnlaceTexto href="https://nextjs.org/learn?utm_source=create-next-app&utm_medium=appdir-template-tw&utm_campaign=create-next-app">
              Learning
            </EnlaceTexto>{" "}
            center.
          </Parrafo>
        </Encabezado>
        <Acciones>
          <BotonEnlace
            variante="primario"
            href="https://vercel.com/new?utm_source=create-next-app&utm_medium=appdir-template-tw&utm_campaign=create-next-app"
            target="_blank"
            rel="noopener noreferrer"
          >
            <Imagen
              variante="icono"
              src="/vercel.svg"
              alt="Vercel logomark"
              width={16}
              height={14}
            />
            Deploy Now
          </BotonEnlace>
          <BotonEnlace
            variante="secundario"
            href="https://nextjs.org/docs?utm_source=create-next-app&utm_medium=appdir-template-tw&utm_campaign=create-next-app"
            target="_blank"
            rel="noopener noreferrer"
          >
            Documentation
          </BotonEnlace>
        </Acciones>
      </Principal>
    </Lienzo>
  );
}

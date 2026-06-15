import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Gate de acesso por HTTP Basic Auth (no Next 16 o antigo "middleware" chama-se
// "proxy"). Credenciais vêm de env do servidor, nunca embutidas no bundle.
// Sem as envs (ex.: dev local), não bloqueia.
const USER = process.env.BASIC_AUTH_USER ?? "";
const PASS = process.env.BASIC_AUTH_PASSWORD ?? "";

export function proxy(req: NextRequest) {
  if (!USER || !PASS) return NextResponse.next();

  const auth = req.headers.get("authorization");
  if (auth?.startsWith("Basic ")) {
    try {
      const decoded = atob(auth.slice(6));
      const sep = decoded.indexOf(":");
      const user = decoded.slice(0, sep);
      const pass = decoded.slice(sep + 1);
      if (user === USER && pass === PASS) {
        return NextResponse.next();
      }
    } catch {
      // header malformado -> cai no 401
    }
  }

  return new NextResponse("Autenticacao necessaria", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Kortes"' },
  });
}

export const config = {
  // Protege as páginas/rotas; ignora os estáticos do Next.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

/**
 * Teleprompter script the person reads while recording their avatar. Original
 * Doppel copy (not borrowed). A unique security code is embedded so the spoken
 * recording can later be matched to a consent request.
 */
export function makeUniqueCode(): number {
  return Math.floor(10 + Math.random() * 90); // two-digit
}

export function avatarScript(lang: string, code: number): string {
  const scripts: Record<string, string> = {
    "pt-BR": `Olá! Estou falando com bastante energia, de forma natural e confiante. Isso ajuda o Doppel a capturar minha voz, minhas expressões e meus movimentos — para que meu avatar se comporte exatamente como eu em qualquer vídeo. Vou continuar olhando para a câmera, mantendo a cabeça e os ombros estáveis no enquadramento. Quanto mais natural eu for agora, mais realista meu avatar vai parecer depois. Por questões de segurança, autorizo a criação do meu avatar digital, e o meu código único é ${code}.`,
    "en-US": `Hi! I'm speaking with plenty of energy, in a natural and confident way. This helps Doppel capture my voice, my expressions and my movements — so my avatar behaves exactly like me in any video. I'll keep looking at the camera, keeping my head and shoulders steady in the frame. The more natural I am now, the more realistic my avatar will look later. For security, I authorize the creation of my digital avatar, and my unique code is ${code}.`,
    "es-MX": `¡Hola! Estoy hablando con mucha energía, de forma natural y segura. Esto ayuda a Doppel a capturar mi voz, mis expresiones y mis movimientos — para que mi avatar se comporte exactamente como yo en cualquier video. Seguiré mirando a la cámara, manteniendo la cabeza y los hombros estables en el encuadre. Cuanto más natural sea ahora, más realista se verá mi avatar después. Por seguridad, autorizo la creación de mi avatar digital, y mi código único es ${code}.`,
  };
  return scripts[lang] ?? scripts["pt-BR"];
}

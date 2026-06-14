import type { LucideIcon } from "lucide-react";
import { Flame, Megaphone, GraduationCap, MessageSquareQuote } from "lucide-react";

/**
 * Scenario orchestration.
 *
 * A scenario "category" is a fully data-driven, guided question flow. Each step
 * asks the user one question; every option carries an English `prompt` fragment.
 * `buildPrompt` stitches the selected fragments into the final generation prompt
 * sent to the image/video model. Adding a new category = adding one object here.
 */

export interface ScenarioOption {
  value: string;
  label: string;
  /** English fragment used to assemble the final prompt (defaults to label). */
  prompt?: string;
  /** Optional section header to group long option lists. */
  group?: string;
}

export interface ScenarioStep {
  id: string;
  title: string;
  helper?: string;
  options: ScenarioOption[];
  /** Allow selecting more than one option. */
  multi?: boolean;
  /** May be left empty (no selection required to advance). */
  optional?: boolean;
}

export interface ScenarioCategory {
  id: string;
  title: string;
  tagline: string;
  description: string;
  icon: LucideIcon;
  /** Tailwind gradient classes for the category card. */
  gradient: string;
  steps: ScenarioStep[];
  buildPrompt: (answers: Record<string, string[]>) => string;
  available?: boolean;
}

/* ------------------------------------------------------------------ */
/* Category 1 — Vídeo Viral                                            */
/* ------------------------------------------------------------------ */

const VIRAL_STEPS: ScenarioStep[] = [
  {
    id: "impact",
    title: "Qual sensação o vídeo deve causar?",
    helper: "Quando alguém bater o olho no vídeo, o que deve sentir?",
    options: [
      { value: "luxo", label: "Luxo", prompt: "a sense of luxury" },
      { value: "autoridade", label: "Autoridade", prompt: "authority" },
      { value: "curiosidade", label: "Curiosidade", prompt: "curiosity" },
      { value: "misterio", label: "Mistério", prompt: "mystery" },
      { value: "sucesso", label: "Sucesso", prompt: "success" },
      { value: "poder", label: "Poder", prompt: "power" },
      { value: "criador", label: "Vida de criador", prompt: "a creator lifestyle" },
      { value: "profissionalismo", label: "Profissionalismo", prompt: "professionalism" },
      { value: "tecnologia", label: "Tecnologia", prompt: "a high-tech feeling" },
      { value: "polemica", label: "Polêmica", prompt: "a provocative edge" },
      { value: "transformacao", label: "Transformação", prompt: "transformation" },
      { value: "bastidores", label: "Bastidores", prompt: "a behind-the-scenes feel" },
      { value: "humor", label: "Humor", prompt: "humor" },
      { value: "desejo", label: "Desejo de assistir", prompt: "an irresistible urge to keep watching" },
    ],
  },
  {
    id: "universe",
    title: "Qual universo o personagem representa?",
    helper: "Qual mundo esse personagem habita?",
    options: [
      { value: "empresario", label: "Empresário de sucesso", prompt: "successful entrepreneur" },
      { value: "criador", label: "Criador de conteúdo", prompt: "content creator" },
      { value: "mentor", label: "Especialista / mentor", prompt: "expert mentor" },
      { value: "podcast", label: "Podcast", prompt: "podcast host" },
      { value: "luxo", label: "Vida de luxo", prompt: "luxury lifestyle personality" },
      { value: "tech", label: "Tecnologia e IA", prompt: "tech and AI specialist" },
      { value: "financas", label: "Finanças", prompt: "finance expert" },
      { value: "marketing", label: "Marketing digital", prompt: "digital marketing expert" },
      { value: "moda", label: "Moda / beleza", prompt: "fashion and beauty creator" },
      { value: "fitness", label: "Fitness", prompt: "fitness creator" },
      { value: "musica", label: "Música", prompt: "music artist" },
      { value: "humor", label: "Humor", prompt: "comedy creator" },
      { value: "lifestyle", label: "Lifestyle", prompt: "lifestyle influencer" },
      { value: "producao", label: "Bastidores de produção", prompt: "production professional" },
      { value: "carros", label: "Carros", prompt: "automotive enthusiast" },
      { value: "viagem", label: "Viagem", prompt: "travel creator" },
      { value: "motivacional", label: "Motivacional", prompt: "motivational speaker" },
    ],
  },
  {
    id: "scenario",
    title: "Escolha o cenário principal",
    helper: "Onde você quer que o personagem esteja?",
    options: [
      // Autoridade
      { group: "Autoridade", value: "escritorio-exec", label: "Escritório executivo moderno", prompt: "a modern executive office" },
      { group: "Autoridade", value: "reuniao-premium", label: "Sala de reunião premium", prompt: "a premium meeting room" },
      { group: "Autoridade", value: "estudio-corp", label: "Estúdio corporativo", prompt: "a corporate studio" },
      { group: "Autoridade", value: "biblioteca", label: "Biblioteca elegante", prompt: "an elegant library" },
      { group: "Autoridade", value: "cobertura", label: "Cobertura com vista da cidade", prompt: "a penthouse with a city view" },
      { group: "Autoridade", value: "escritorio-vidro", label: "Escritório com parede de vidro", prompt: "a glass-walled office" },
      { group: "Autoridade", value: "sala-ceo", label: "Sala de CEO", prompt: "a CEO office" },
      { group: "Autoridade", value: "telas-graficos", label: "Ambiente com telas e gráficos", prompt: "a room full of screens and charts" },
      // Podcast
      { group: "Podcast", value: "mesa-podcast", label: "Mesa de podcast com microfones", prompt: "a podcast table with professional microphones" },
      { group: "Podcast", value: "estudio-led", label: "Estúdio escuro com luzes LED", prompt: "a dark studio with LED lights" },
      { group: "Podcast", value: "prateleiras-neon", label: "Fundo com prateleiras e neon", prompt: "a background with shelves and neon" },
      { group: "Podcast", value: "podcast-poltronas", label: "Podcast premium com poltronas", prompt: "a premium podcast set with armchairs" },
      { group: "Podcast", value: "mesa-redonda", label: "Mesa redonda com equipamentos", prompt: "a round table with podcast equipment" },
      { group: "Podcast", value: "acustico", label: "Fundo acústico profissional", prompt: "a professional acoustic backdrop" },
      { group: "Podcast", value: "camera-aparente", label: "Estúdio com câmera e luz aparente", prompt: "a studio with visible camera and lighting" },
      // Luxo
      { group: "Luxo", value: "carro-luxo", label: "Dentro de carro de luxo", prompt: "inside a luxury car" },
      { group: "Luxo", value: "banco-traseiro", label: "Banco traseiro de carro executivo", prompt: "the back seat of an executive car" },
      { group: "Luxo", value: "garagem-esportivos", label: "Garagem com carros esportivos", prompt: "a garage with sports cars" },
      { group: "Luxo", value: "lounge-hotel", label: "Lounge de hotel cinco estrelas", prompt: "a five-star hotel lounge" },
      { group: "Luxo", value: "jato", label: "Jato particular", prompt: "a private jet cabin" },
      { group: "Luxo", value: "restaurante", label: "Restaurante sofisticado", prompt: "a sophisticated restaurant" },
      { group: "Luxo", value: "mansao", label: "Mansão moderna", prompt: "a modern mansion" },
      { group: "Luxo", value: "yacht", label: "Yacht / barco de luxo", prompt: "a luxury yacht" },
      { group: "Luxo", value: "elevador", label: "Elevador espelhado premium", prompt: "a premium mirrored elevator" },
      // Criador
      { group: "Criador de conteúdo", value: "setup-gamer", label: "Setup gamer / produtividade", prompt: "a gamer and productivity setup" },
      { group: "Criador de conteúdo", value: "ring-light", label: "Estúdio com ring light e câmera", prompt: "a studio with ring light and camera" },
      { group: "Criador de conteúdo", value: "quarto-creator", label: "Quarto moderno de creator", prompt: "a modern creator bedroom studio" },
      { group: "Criador de conteúdo", value: "mesa-setup", label: "Mesa com notebook, celular e luzes", prompt: "a desk with laptop, phone and lights" },
      { group: "Criador de conteúdo", value: "telas-coloridas", label: "Fundo com telas coloridas", prompt: "a background with colorful screens" },
      { group: "Criador de conteúdo", value: "estudio-vertical", label: "Estúdio de gravação vertical", prompt: "a vertical recording studio" },
      { group: "Criador de conteúdo", value: "jovem-led", label: "Ambiente jovem com LEDs", prompt: "a youthful space with LED lighting" },
      // Tecnológico
      { group: "Tecnológico", value: "futurista", label: "Sala futurista com telas", prompt: "a futuristic room with screens" },
      { group: "Tecnológico", value: "lab-ia", label: "Laboratório de IA", prompt: "an AI laboratory" },
      { group: "Tecnológico", value: "hologramas", label: "Fundo com hologramas", prompt: "a background with holograms" },
      { group: "Tecnológico", value: "tech-azul", label: "Escritório tech azul escuro", prompt: "a dark-blue tech office" },
      { group: "Tecnológico", value: "data-center", label: "Data center cinematográfico", prompt: "a cinematic data center" },
      { group: "Tecnológico", value: "painel-digital", label: "Painel digital gigante", prompt: "a giant digital panel" },
      { group: "Tecnológico", value: "sala-controle", label: "Sala de controle", prompt: "a control room" },
      { group: "Tecnológico", value: "cyberpunk", label: "Ambiente cyberpunk elegante", prompt: "an elegant cyberpunk environment" },
      // Urbano
      { group: "Urbano", value: "rua-neon", label: "Rua à noite com neon", prompt: "a neon-lit street at night" },
      { group: "Urbano", value: "avenida", label: "Avenida de cidade grande", prompt: "a big-city avenue" },
      { group: "Urbano", value: "predio-fundo", label: "Prédio empresarial ao fundo", prompt: "a corporate building backdrop" },
      { group: "Urbano", value: "estacionamento", label: "Estacionamento de luxo", prompt: "a luxury parking garage" },
      { group: "Urbano", value: "cafe", label: "Café moderno", prompt: "a modern café" },
      { group: "Urbano", value: "aeroporto", label: "Aeroporto executivo", prompt: "an executive airport lounge" },
      { group: "Urbano", value: "hotel-urbano", label: "Hotel urbano", prompt: "an urban hotel" },
      { group: "Urbano", value: "rooftop", label: "Rooftop com skyline", prompt: "a rooftop with city skyline" },
    ],
  },
  {
    id: "level",
    title: "Escolha o nível de luxo / impacto",
    helper: "O cenário deve parecer mais simples ou mais poderoso?",
    options: [
      { value: "simples", label: "Simples e realista", prompt: "simple and realistic" },
      { value: "profissional", label: "Profissional", prompt: "professional" },
      { value: "premium", label: "Premium", prompt: "premium" },
      { value: "luxuoso", label: "Muito luxuoso", prompt: "very luxurious" },
      { value: "cinematografico", label: "Cinematográfico", prompt: "cinematic" },
      { value: "exagerado", label: "Exagerado para chamar atenção", prompt: "over-the-top and attention-grabbing" },
      { value: "surpreendente", label: "Surpreendente", prompt: "surprising" },
      { value: "misterioso", label: "Misterioso", prompt: "mysterious" },
      { value: "viral", label: "Viral e chamativo", prompt: "viral and eye-catching" },
    ],
  },
  {
    id: "objects",
    title: "Escolha os objetos importantes do fundo",
    helper: "O que no cenário ajuda a contar a história? (pode escolher vários)",
    multi: true,
    optional: true,
    options: [
      { value: "microfone", label: "Microfone de podcast", prompt: "a podcast microphone" },
      { value: "notebook", label: "Notebook aberto", prompt: "an open laptop" },
      { value: "telas", label: "Telas grandes", prompt: "large screens" },
      { value: "led", label: "Luzes LED", prompt: "LED lights" },
      { value: "livros", label: "Livros", prompt: "books" },
      { value: "quadro", label: "Quadro abstrato", prompt: "an abstract painting" },
      { value: "planta", label: "Planta elegante", prompt: "an elegant plant" },
      { value: "cidade", label: "Cidade ao fundo", prompt: "a city in the background" },
      { value: "volante", label: "Volante de carro de luxo", prompt: "a luxury car steering wheel" },
      { value: "couro", label: "Banco de couro", prompt: "leather seats" },
      { value: "mesa-madeira", label: "Mesa de madeira premium", prompt: "a premium wooden table" },
      { value: "camera", label: "Câmera de gravação", prompt: "a recording camera" },
      { value: "ring-light", label: "Ring light", prompt: "a ring light" },
      { value: "agua", label: "Garrafa de água premium", prompt: "a premium water bottle" },
      { value: "cafe", label: "Café", prompt: "a coffee cup" },
      { value: "fone", label: "Fone de ouvido", prompt: "headphones" },
      { value: "dinheiro", label: "Dinheiro / elementos financeiros", prompt: "subtle financial elements" },
      { value: "graficos", label: "Gráficos em tela", prompt: "charts on screen" },
      { value: "limpo", label: "Nenhum objeto, cenário limpo", prompt: "a clean scene with no props" },
    ],
  },
  {
    id: "background",
    title: "O fundo será visível ou desfocado?",
    helper: "Você quer ver bastante o cenário ou só sentir o ambiente?",
    options: [
      { value: "visivel", label: "Fundo bem visível", prompt: "background clearly visible" },
      { value: "leve-desfoque", label: "Fundo levemente desfocado", prompt: "background slightly blurred" },
      { value: "muito-desfoque", label: "Fundo muito desfocado", prompt: "background heavily blurred" },
      { value: "personagem-grande", label: "Personagem grande, pouco cenário", prompt: "subject large with minimal background" },
      { value: "personagem-menor", label: "Personagem menor, muito cenário", prompt: "subject smaller revealing more of the scene" },
      { value: "espaco-texto", label: "Fundo com espaço para texto", prompt: "background with space for captions" },
      { value: "dramatico", label: "Fundo dramático e profundo", prompt: "deep dramatic background" },
      { value: "minimalista", label: "Fundo limpo e minimalista", prompt: "clean minimalist background" },
    ],
  },
  {
    id: "lighting",
    title: "Escolha a iluminação",
    helper: "Qual iluminação deixa esse cenário mais forte?",
    options: [
      { value: "led-podcast", label: "Luz de podcast com LED", prompt: "LED podcast lighting" },
      { value: "cine-escura", label: "Luz cinematográfica escura", prompt: "dark cinematic lighting" },
      { value: "office-premium", label: "Luz de escritório premium", prompt: "premium office lighting" },
      { value: "fim-tarde", label: "Luz quente de fim de tarde", prompt: "warm late-afternoon light" },
      { value: "azul-tech", label: "Luz azul tecnológica", prompt: "blue tech lighting" },
      { value: "carro-noite", label: "Luz de carro à noite", prompt: "night car lighting" },
      { value: "cidade-noite", label: "Luz de cidade noturna", prompt: "night city lighting" },
      { value: "estudio-limpa", label: "Luz limpa de estúdio", prompt: "clean studio lighting" },
      { value: "contraluz", label: "Contraluz poderoso", prompt: "strong backlight" },
      { value: "sombras", label: "Luz dramática com sombras", prompt: "dramatic lighting with shadows" },
    ],
  },
  {
    id: "palette",
    title: "Escolha a paleta de cores",
    helper: "Quais cores deixam o vídeo mais chamativo?",
    options: [
      { value: "preto-dourado", label: "Preto e dourado", prompt: "black and gold" },
      { value: "azul-cinza", label: "Azul escuro e cinza", prompt: "dark blue and grey" },
      { value: "roxo-neon", label: "Roxo e azul neon", prompt: "purple and neon blue" },
      { value: "oliva-offwhite", label: "Verde oliva e off-white", prompt: "olive green and off-white" },
      { value: "marrom-bege", label: "Marrom e bege premium", prompt: "premium brown and beige" },
      { value: "vermelho-preto", label: "Vermelho e preto", prompt: "red and black" },
      { value: "branco-cinza", label: "Branco e cinza clean", prompt: "clean white and grey" },
      { value: "laranja", label: "Laranja quente", prompt: "warm orange" },
      { value: "escuros-cine", label: "Tons escuros cinematográficos", prompt: "dark cinematic tones" },
      { value: "ia", label: "Deixar a IA escolher", prompt: "" },
    ],
  },
  {
    id: "framing",
    title: "Escolha o enquadramento",
    helper: "Como o personagem deve aparecer no cenário?",
    options: [
      { value: "meio-corpo", label: "Meio corpo, estilo Reels/TikTok", prompt: "half-body Reels/TikTok-style composition" },
      { value: "close", label: "Close com fundo forte", prompt: "close-up with a strong background" },
      { value: "mesa-podcast", label: "Sentado em mesa de podcast", prompt: "seated at a podcast table" },
      { value: "cadeira-exec", label: "Sentado em cadeira executiva", prompt: "seated in an executive chair" },
      { value: "carro-camera", label: "Dentro do carro olhando para câmera", prompt: "inside the car looking at the camera" },
      { value: "em-pe", label: "Em pé no escritório", prompt: "standing in the office" },
      { value: "encostado", label: "Encostado na mesa", prompt: "leaning on the desk" },
      { value: "plano-aberto", label: "Plano mais aberto mostrando o ambiente", prompt: "a wider shot showing the environment" },
      { value: "vertical-legenda", label: "Vertical com espaço para legenda", prompt: "vertical format with space for captions" },
      { value: "thumbnail", label: "Formato capa / thumbnail", prompt: "a thumbnail cover composition" },
    ],
  },
];

/**
 * Fixed system-level negatives — always applied, never asked of the user.
 */
const VIRAL_NEGATIVES = [
  "cluttered background",
  "artificial look",
  "low-detail scene",
  "too many colors",
  "logos or brands",
  "text in the image",
  "deformed objects",
  "blown-out lighting",
  "cartoonish look",
  "generic scene",
  "flat background",
  "overly artificial face",
];

function resolve(stepId: string, values: string[] = []): string[] {
  const step = VIRAL_STEPS.find((s) => s.id === stepId);
  if (!step) return [];
  return values
    .map((v) => {
      const opt = step.options.find((o) => o.value === v);
      const frag = opt?.prompt ?? opt?.label ?? "";
      return frag;
    })
    .filter(Boolean);
}

function buildViralPrompt(a: Record<string, string[]>): string {
  const impact = resolve("impact", a.impact)[0] ?? "high impact";
  const universe = resolve("universe", a.universe)[0] ?? "content creator";
  const scenario = resolve("scenario", a.scenario)[0] ?? "a premium studio";
  const level = resolve("level", a.level)[0] ?? "cinematic";
  const objects = resolve("objects", a.objects);
  const background = resolve("background", a.background)[0] ?? "background slightly blurred";
  const lighting = resolve("lighting", a.lighting)[0] ?? "cinematic lighting";
  const palette = resolve("palette", a.palette)[0];
  const framing =
    resolve("framing", a.framing)[0] ?? "half-body vertical composition with space for captions";

  const parts = [
    `Create a viral vertical avatar image for short-form video, featuring a confident ${universe} conveying ${impact}.`,
    `The scenario is the main focus: ${scenario}${objects.length ? `, with ${objects.join(", ")}` : ""}.`,
    `${cap(level)} look${palette ? `, ${palette} color palette` : ""}.`,
    `The character appears in a ${framing}, with the ${background}.`,
    `${cap(lighting)}, high contrast, realistic professional atmosphere, viral social media thumbnail style, ultra realistic, sharp details, clean composition.`,
    `Avoid: ${VIRAL_NEGATIVES.join(", ")}.`,
  ];
  return parts.join(" ");
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/* ------------------------------------------------------------------ */
/* Registry                                                            */
/* ------------------------------------------------------------------ */

export const SCENARIOS: ScenarioCategory[] = [
  {
    id: "viral",
    title: "Vídeo Viral",
    tagline: "Avatar em cenário de alto impacto",
    description:
      "Monte um cenário cinematográfico para Reels, TikTok e Shorts em 10 perguntas rápidas.",
    icon: Flame,
    gradient: "from-rose-500/30 via-orange-500/20 to-amber-400/10",
    steps: VIRAL_STEPS,
    buildPrompt: buildViralPrompt,
    available: true,
  },
  {
    id: "anuncio",
    title: "Anúncio de Produto",
    tagline: "UGC que converte",
    description: "Em breve: roteiro e cenário focados em conversão para campanhas.",
    icon: Megaphone,
    gradient: "from-cyan-500/30 via-sky-500/20 to-blue-500/10",
    steps: [],
    buildPrompt: () => "",
    available: false,
  },
  {
    id: "depoimento",
    title: "Depoimento / Prova Social",
    tagline: "Autenticidade que vende",
    description: "Em breve: cenários naturais para depoimentos e provas sociais.",
    icon: MessageSquareQuote,
    gradient: "from-emerald-500/30 via-teal-500/20 to-green-500/10",
    steps: [],
    buildPrompt: () => "",
    available: false,
  },
  {
    id: "aula",
    title: "Aula / Tutorial",
    tagline: "Conteúdo educativo",
    description: "Em breve: cenários de ensino com apoio visual e quadros.",
    icon: GraduationCap,
    gradient: "from-violet-500/30 via-purple-500/20 to-fuchsia-500/10",
    steps: [],
    buildPrompt: () => "",
    available: false,
  },
];

export function getScenario(id: string): ScenarioCategory | undefined {
  return SCENARIOS.find((s) => s.id === id);
}

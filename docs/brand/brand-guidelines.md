# Kortes - Guia de Marca

Referência da identidade visual da Kortes. Use junto dos assets em
[`web/public/brand/`](../../web/public/brand/).

> Nota: os valores de cor abaixo foram extraídos das artes de referência e são
> aproximados. Se houver o kit oficial do designer (com hex exatos e fontes),
> substitua os valores aqui e os SVGs em `web/public/brand/` pelos oficiais.

## Marca

- **Nome**: Kortes (estilizado em caixa alta no wordmark: `KORTES`).
- **Tagline principal**: "IA QUE CORTA. VOCÊ VIRALIZA." (o termo "VIRALIZA" recebe
  destaque em violeta).
- **Tagline curta / produto**: "Seus cortes, prontos para viralizar."
- **Conceito**: a fusão entre a tesoura e a letra K. Representa cortar com
  inteligência para gerar o que viraliza. O símbolo combina os cabos da tesoura
  (dois quadrados vazados) com as lâminas que se cruzam no pivô formando um K.

## Paleta

| Token | Hex | Uso |
|-------|-----|-----|
| Violet Deep | `#6D28D9` | base do gradiente |
| Violet | `#7C3AED` | cor primária sólida |
| Violet Mid | `#9333EA` | meio do gradiente |
| Violet Light | `#A855F7` | destaque (ex.: "VIRALIZA"), hover |
| Violet Glow | `#C77DFF` | topo do gradiente, brilho |
| Brand Black | `#0A0A0F` | fundo padrão (a marca vive sobre escuro) |
| White | `#FFFFFF` | texto/símbolo sobre roxo ou escuro |
| Gray | `#9CA3AF` | versões monocromáticas, texto secundário |

**Gradiente assinatura** (diagonal, canto inferior-esquerdo -> superior-direito):

```css
background: linear-gradient(135deg, #6D28D9 0%, #9333EA 55%, #C77DFF 100%);
```

Tokens CSS sugeridos (para o web consumir na fase de rebranding):

```css
:root {
  --kortes-violet-deep: #6D28D9;
  --kortes-violet: #7C3AED;
  --kortes-violet-mid: #9333EA;
  --kortes-violet-light: #A855F7;
  --kortes-violet-glow: #C77DFF;
  --kortes-black: #0A0A0F;
  --kortes-white: #ffffff;
  --kortes-gray: #9CA3AF;
  --kortes-gradient: linear-gradient(135deg, #6D28D9 0%, #9333EA 55%, #C77DFF 100%);
}
```

## Tipografia

O wordmark `KORTES` usa uma sans-serif geométrica/tech, caixa alta, com
espaçamento amplo e "cortes" nas letras (provavelmente fonte custom ou
desenhada). Para a interface web, usar uma aproximação disponível no Google
Fonts mantém coerência sem depender do arquivo custom:

- **Sugestão para títulos/UI**: Chakra Petch, Saira ou Rajdhani (geométricas,
  tech, caixa alta funciona bem).
- **Corpo de texto**: manter a fonte atual do app (legível em telas pequenas).
- Para o logotipo em si, preferir sempre o **SVG do wordmark oficial** em vez de
  reproduzir com fonte de sistema.

## Versões do logo

Da arte de referência:

- **Principal (vertical)**: símbolo acima do wordmark `KORTES` e da tagline.
- **Horizontais**: símbolo à esquerda do wordmark, com ou sem tagline; variação
  com separador vertical antes do wordmark.
- **Ícone / app**: símbolo dentro de quadrado de cantos arredondados. Três
  fundos: roxo sólido (símbolo branco), preto (símbolo em gradiente roxo),
  branco (símbolo em gradiente roxo).
- **Símbolo isolado**: só a tesoura-K, para favicon, avatar e marca d'água.
- **Monocromáticas**: branco, gradiente, cinza e outline (contorno).
- **Negativa (fundo escuro)**: as variações acima aplicadas sobre `#0A0A0F`.

## Uso

- Fundo padrão é **escuro** (`#0A0A0F`). Sobre fundo claro, usar a versão de
  símbolo em gradiente ou a monocromática apropriada.
- Preservar área de respiro ao redor do logo (mínimo ~= altura de um cabo da
  tesoura).
- Não distorcer, não rotacionar, não trocar as cores do gradiente, não aplicar
  o roxo sobre fundos que matem o contraste.

## Assets neste repositório

Em `web/public/brand/`:

- `kortes-symbol.svg` - símbolo (tesoura-K) em gradiente. **Recriação vetorial**
  a partir da referência; troque pelo oficial quando disponível.

Pendentes (adicionar quando houver os arquivos oficiais do designer):

- `kortes-logo-horizontal.svg` - lockup símbolo + wordmark.
- `kortes-logo-vertical.svg` - versão principal.
- `kortes-wordmark.svg` - só o texto `KORTES`.
- `icon-*.png` / `favicon` - ícones de app exportados (roxo, preto, branco).

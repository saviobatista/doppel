"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, X } from "lucide-react";
import { getAvatar, subscribeAvatar, type AvatarDetail } from "@/lib/api";
import { VoiceSetup } from "@/components/voice/VoiceSetup";
import { LiveAvatarVideo } from "@/components/avatar/LiveAvatarVideo";

export function AvatarReadyScreen({ avatarId }: { avatarId: string }) {
  const router = useRouter();
  const [detail, setDetail] = useState<AvatarDetail | null>(null);
  const [status, setStatus] = useState<string>("processing");
  const [helloUrl, setHelloUrl] = useState<string | null>(null);
  const [idleUrl, setIdleUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let active = true;
    getAvatar(avatarId)
      .then((d) => {
        if (!active) return;
        setDetail(d);
        setStatus(d.status);
        if (d.hello_url) setHelloUrl(d.hello_url);
        if (d.idle_url) setIdleUrl(d.idle_url);
      })
      .catch((e) => active && setError((e as Error).message));

    const ac = new AbortController();
    abortRef.current = ac;
    subscribeAvatar(
      avatarId,
      (event, data) => {
        if (event === "status") {
          if (typeof data.value === "string") setStatus(data.value);
          if (typeof data.hello_url === "string") setHelloUrl(data.hello_url);
          if (typeof data.idle_url === "string") setIdleUrl(data.idle_url);
        } else if (event === "hello_ready") {
          setStatus("ready");
          if (typeof data.hello_url === "string") setHelloUrl(data.hello_url);
          if (typeof data.idle_url === "string") setIdleUrl(data.idle_url);
        } else if (event === "failed") {
          setStatus("failed");
        }
      },
      ac.signal,
    ).catch(() => {});

    return () => {
      active = false;
      ac.abort();
    };
  }, [avatarId]);

  // Pull the label/hello once the avatar flips to ready mid-stream.
  useEffect(() => {
    if (status === "ready" && (!detail || detail.status !== "ready")) {
      getAvatar(avatarId)
        .then((d) => {
          setDetail(d);
          if (d.hello_url) setHelloUrl(d.hello_url);
          if (d.idle_url) setIdleUrl(d.idle_url);
        })
        .catch(() => {});
    }
  }, [status, avatarId, detail]);

  const name = detail?.label?.trim();

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex h-14 shrink-0 items-center justify-end px-6">
        <button
          onClick={() => router.push("/avatar")}
          aria-label="Fechar"
          className="flex h-9 w-9 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-white/5 hover:text-zinc-100"
        >
          <X className="h-5 w-5" />
        </button>
      </header>

      <main className="flex-1 overflow-y-auto px-6 pb-12">
        {status === "failed" || error ? (
          <div className="mx-auto mt-16 w-full max-w-md text-center">
            <h1 className="text-xl font-bold text-white">Algo deu errado</h1>
            <p className="mt-2 text-sm text-zinc-400">
              {error ?? "Não foi possível preparar seu avatar. Tente gravar novamente."}
            </p>
          </div>
        ) : status !== "ready" ? (
          <div className="mx-auto mt-24 flex w-full max-w-md flex-col items-center text-center">
            <Loader2 className="h-10 w-10 animate-spin text-accent" />
            <h1 className="mt-4 text-xl font-bold text-white">
              Preparando {name ? `o avatar de ${name}` : "seu avatar"}…
            </h1>
            <p className="mt-2 text-sm text-zinc-400">
              Estamos extraindo seu rosto e clonando sua voz a partir da gravação.
            </p>
          </div>
        ) : (
          <div className="mx-auto w-full max-w-2xl">
            <div className="text-center">
              <h1 className="text-2xl font-bold text-white">Seu avatar está pronto!</h1>
              <p className="mt-2 text-sm text-zinc-400">
                Escolha a voz do seu avatar para começar a criar vídeos.
              </p>
            </div>

            {helloUrl && (
              <div className="mx-auto mt-6 max-w-[280px] overflow-hidden rounded-2xl border border-white/10 bg-black">
                <LiveAvatarVideo key={helloUrl} helloUrl={helloUrl} idleUrl={idleUrl} />
              </div>
            )}

            <div className="mt-8">
              <VoiceSetup avatarId={avatarId} defaultLabel={name} footageReady />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}


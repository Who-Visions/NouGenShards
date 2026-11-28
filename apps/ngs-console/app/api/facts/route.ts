import { ngs } from "@/lib/engine"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export async function GET(req: Request) {
  const limit = Math.min(Math.max(Number(new URL(req.url).searchParams.get("limit") ?? 25) || 25, 1), 200)
  return Response.json(await ngs(["scan", "--limit", String(limit)]))
}

import { engineLive, ngs } from "@/lib/engine"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export async function GET() {
  const stats = await ngs(["stats"])
  return Response.json({ live: engineLive(), stats })
}

import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
const API = process.env.API_URL || 'http://127.0.0.1:8000';
async function proxy(req: NextRequest, ctx: {params: Promise<{path: string[]}>}) {
  const {path} = await ctx.params;
  if (!['workflows', 'executions', 'infrastructure'].includes(path[0])) return NextResponse.json({detail:'Not found'}, {status:404});
  if (req.method !== 'GET' && req.headers.get('origin') !== req.nextUrl.origin) return NextResponse.json({detail:'Invalid origin'}, {status:403});
  const token = (await cookies()).get('cp_session')?.value;
  if (!token) return NextResponse.json({detail:'Sign in to your control plane'}, {status:401});
  try {
    const response = await fetch(`${API}/api/${path.map(encodeURIComponent).join('/')}${req.nextUrl.search}`, {
      method: req.method, headers: {'Authorization': `Bearer ${token}`, 'Content-Type':'application/json'},
      body: req.method === 'GET' ? undefined : await req.text(), signal: AbortSignal.timeout(45000), cache:'no-store'});
    return new NextResponse(await response.text(), {status: response.status, headers:{'Content-Type':'application/json', 'Cache-Control':'no-store'}});
  } catch { return NextResponse.json({detail:'Control-plane API unavailable'}, {status:503}); }
}
export { proxy as GET, proxy as POST };

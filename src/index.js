export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 1. Clean route rewrites for frontend pages
    const routeMap = {
      "/login": "/auth.html",
      "/signup": "/auth.html",
      "/app": "/index.html",
      "/admin": "/admin.html",
      "/reset": "/reset.html",
      "/privacy": "/legal.html",
      "/terms": "/legal.html",
      "/acceptable-use": "/legal.html",
    };

    if (routeMap[url.pathname]) {
      url.pathname = routeMap[url.pathname];
      return env.ASSETS.fetch(new Request(url.toString(), request));
    }

    if (url.pathname.startsWith("/app/")) {
      url.pathname = "/index.html";
      return env.ASSETS.fetch(new Request(url.toString(), request));
    }

    if (url.pathname.startsWith("/admin/")) {
      url.pathname = "/admin.html";
      return env.ASSETS.fetch(new Request(url.toString(), request));
    }

    // 2. Handle /api/*, /auth/*, /oauth/*, and /media/*
    const isBackendRoute = url.pathname.startsWith("/api/") ||
                           url.pathname.startsWith("/auth/") ||
                           url.pathname.startsWith("/oauth/") ||
                           url.pathname.startsWith("/media/");

    if (isBackendRoute) {
      // If Cloudflare R2 public URL is configured and this is /media/*
      if (url.pathname.startsWith("/media/") && env.R2_PUBLIC_URL) {
        const r2Path = url.pathname.replace(/^\/media/, "/clips");
        return Response.redirect(`${env.R2_PUBLIC_URL.replace(/\/$/, "")}${r2Path}`, 302);
      }

      // Forward to backend if configured
      const backendBase = env.BACKEND_URL;
      if (!backendBase) {
        return new Response(JSON.stringify({
          error: "Backend not configured",
          detail: "BACKEND_URL environment variable is missing on Cloudflare Worker."
        }), { status: 503, headers: { "Content-Type": "application/json" } });
      }

      const targetUrl = new URL(url.pathname + url.search, backendBase);
      const headers = new Headers(request.headers);
      const clientIp = request.headers.get("CF-Connecting-IP") || "";
      if (clientIp) {
        headers.set("X-Forwarded-For", clientIp);
        headers.set("CF-Connecting-IP", clientIp);
      }
      headers.set("Host", targetUrl.host);
      headers.set("X-Forwarded-Host", url.host);
      headers.set("X-Forwarded-Proto", "https");

      try {
        return await fetch(targetUrl.toString(), {
          method: request.method,
          headers: headers,
          body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
          redirect: "manual",
        });
      } catch (err) {
        return new Response(JSON.stringify({
          error: "Backend unavailable",
          detail: "Clips X backend server is starting up or unreachable.",
          message: err.message
        }), { status: 502, headers: { "Content-Type": "application/json" } });
      }
    }

    // 3. Fallback to static assets
    let response = await env.ASSETS.fetch(request);
    if (response.status === 404 && !url.pathname.includes(".")) {
      url.pathname = "/index.html";
      response = await env.ASSETS.fetch(new Request(url.toString(), request));
    }

    // 4. Inject production security headers
    const newHeaders = new Headers(response.headers);
    newHeaders.set("X-Content-Type-Options", "nosniff");
    newHeaders.set("X-Frame-Options", "SAMEORIGIN");
    newHeaders.set("Referrer-Policy", "strict-origin-when-cross-origin");
    newHeaders.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload");

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: newHeaders,
    });
  }
};

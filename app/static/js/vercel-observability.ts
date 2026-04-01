import { inject } from "@vercel/analytics";
import { injectSpeedInsights } from "@vercel/speed-insights";

function isLocalDevelopmentHost(hostname: string): boolean {
  return (
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "[::1]" ||
    hostname.endsWith(".local")
  );
}

function bootVercelObservability(): void {
  if (typeof window === "undefined") {
    return;
  }

  if (isLocalDevelopmentHost(window.location.hostname)) {
    return;
  }

  inject({
    mode: "production",
    framework: "fastapi",
  });

  injectSpeedInsights({
    framework: "fastapi",
  });
}

bootVercelObservability();

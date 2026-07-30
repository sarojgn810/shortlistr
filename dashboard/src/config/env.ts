/**
 * Browser requests use same-origin `/api` (proxied by Next.js → FastAPI).
 * Set NEXT_PUBLIC_SHORTLISTR_API_URL to call the API directly (e.g. production).
 */
export const env = {
  apiUrl: process.env.NEXT_PUBLIC_SHORTLISTR_API_URL ?? "/api",
  apiToken: process.env.NEXT_PUBLIC_SHORTLISTR_API_TOKEN ?? "",
};

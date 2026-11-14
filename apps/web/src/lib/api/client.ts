// Typed client generated from FastAPI's OpenAPI schema (schema.d.ts is generated: `npm run gen:api`; do not hand-edit it).
import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type JobRow = components["schemas"]["JobRow"];
export type JobDetail = components["schemas"]["JobDetail"];
export type UserOut = components["schemas"]["UserOut"];
export type Prefs = components["schemas"]["Prefs"];
export type RunRow = components["schemas"]["RunRow"];
export type MemoryItem = components["schemas"]["MemoryItem"];
export type Health = components["schemas"]["Health"];

export const getToken = () => localStorage.getItem("gigbid_token") || "";
export const setToken = (t: string) => (t ? localStorage.setItem("gigbid_token", t) : localStorage.removeItem("gigbid_token"));

const auth: Middleware = {
  onRequest({ request }) {
    const t = getToken();
    if (t) request.headers.set("Authorization", `Bearer ${t}`);
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401 && !location.pathname.startsWith("/login")) {
      setToken("");
      location.href = "/login";
    }
    return response;
  },
};

export const api = createClient<paths>({ baseUrl: "" });
api.use(auth);

export function errText(e: unknown): string {
  if (!e) return "";
  const d = (e as { detail?: unknown }).detail;
  return typeof d === "string" ? d : JSON.stringify(d ?? e);
}

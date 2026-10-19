// Server-only configuration: private Render DNS never enters the browser bundle.
export const API_URL =
  process.env.API_URL ||
  (process.env.API_HOST
    ? `http://${process.env.API_HOST}:8000`
    : "http://127.0.0.1:8000");

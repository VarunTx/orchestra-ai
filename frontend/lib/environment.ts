/** Server-side environment label; read at request time by the page components. */
export const environment =
  process.env.DEPLOYMENT_ENVIRONMENT === "hosted" ? "hosted" : "local";

import { buildErrorResponse, query, sendJson } from "./_lib/db.js";

export default async function handler(_req, res) {
  try {
    await query("select 1");
    return sendJson(res, { status: "ok", database: true });
  } catch (error) {
    const failure = buildErrorResponse(error);
    return sendJson(res, failure.body, failure.statusCode);
  }
}

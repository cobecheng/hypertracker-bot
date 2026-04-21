import { Pool } from "pg";

let pool;

function normalizeConnectionString(rawUrl) {
  const url = new URL(rawUrl);
  url.searchParams.delete("sslmode");
  return url.toString();
}

export function getPool() {
  if (!process.env.DATABASE_URL) {
    throw new Error("DATABASE_URL is not configured");
  }

  if (!pool) {
    pool = new Pool({
      connectionString: normalizeConnectionString(process.env.DATABASE_URL),
      ssl: { rejectUnauthorized: false },
      max: 3,
    });
  }

  return pool;
}

export async function query(text, params = []) {
  const result = await getPool().query(text, params);
  return result;
}

export function parseWindowStart(window = "1h") {
  const now = Date.now();
  const mapping = {
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
    "30d": 30 * 24 * 60 * 60 * 1000,
  };

  if (!mapping[window]) {
    const error = new Error("Unsupported window");
    error.statusCode = 400;
    throw error;
  }

  return now - mapping[window];
}

export function asNumber(value) {
  return value == null ? 0 : Number(value);
}

export function json(value, statusCode = 200) {
  return {
    statusCode,
    body: value,
  };
}

export function loadJson(value) {
  if (!value) return [];
  if (Array.isArray(value) || typeof value === "object") return value;
  return JSON.parse(value);
}

export function buildErrorResponse(error) {
  const statusCode = error?.statusCode || 500;
  return json({ error: error?.message || "Internal server error" }, statusCode);
}

export function sendJson(res, value, statusCode = 200) {
  res.setHeader("Cache-Control", "s-maxage=15, stale-while-revalidate=60");
  res.status(statusCode).json(value);
}

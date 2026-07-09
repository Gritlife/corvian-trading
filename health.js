// netlify/functions/health.js
// Health check. Reports whether MASSIVE_API_KEY is configured WITHOUT
// ever returning its value or any prefix/suffix of it.

const { requireMethod } = require("./lib/massive-client");

exports.handler = async function handler(event) {
  const methodErr = requireMethod(event, ["GET"]);
  if (methodErr) return methodErr;

  const hasKey = !!(process.env.MASSIVE_API_KEY && process.env.MASSIVE_API_KEY.length > 0);
  return {
    statusCode: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
    body: JSON.stringify({
      status: "ok",
      timestampUtc: new Date().toISOString(),
      massiveKeyConfigured: hasKey,
      // Deliberately no key value, no key length, no key prefix.
    }),
  };
};

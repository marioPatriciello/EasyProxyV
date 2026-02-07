import fetch from "node-fetch";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_ANON_KEY
);

export default async function handler(req, res) {
  const target = req.query.url;
  const authHeader = req.headers.authorization;

  if (!target) {
    return res.status(400).json({ error: "Missing url param" });
  }

  // 1️⃣ verifica utente Supabase
  const { data: userData, error: authError } =
    await supabase.auth.getUser(authHeader?.replace("Bearer ", ""));

  if (authError || !userData?.user) {
    return res.status(401).json({ error: "Unauthorized" });
  }

  try {
    // 2️⃣ proxy request
    const response = await fetch(target, {
      method: req.method,
      headers: req.headers,
    });

    const body = await response.text();

    // 3️⃣ log su Supabase
    await supabase.from("proxy_logs").insert({
      user_id: userData.user.id,
      target_url: target,
      method: req.method,
      status: response.status,
    });

    // 4️⃣ return risposta
    res.status(response.status);
    response.headers.forEach((v, k) => res.setHeader(k, v));
    res.send(body);

  } catch (err) {
    res.status(500).json({ error: err.message });
  }
}

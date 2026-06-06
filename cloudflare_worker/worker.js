// Cloudflare Worker — recibe webhook de Telegram y dispara el GitHub Action
//
// Variables de entorno a configurar en el Worker (Settings > Variables):
//   TELEGRAM_BOT_TOKEN  — token del bot de Telegram
//   TELEGRAM_CHAT_ID    — chat_id autorizado (el tuyo); rechaza mensajes de otros
//   GITHUB_TOKEN        — Personal Access Token con permiso "Actions: write"
//   GITHUB_OWNER        — usuario u organización del repo (ej: "hpacheco")
//   GITHUB_REPO         — nombre del repo (ej: "remindme_my_calendar")
//
// Comando soportado:
//   /agendar DD/MM HH:MM Título del evento
//   /agendar DD/MM/YYYY HH:MM Título del evento

const WORKFLOW_FILE = "daily_notify.yml";

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("OK");

    let body;
    try {
      body = await request.json();
    } catch {
      return new Response("OK");
    }

    const message = body?.message;
    if (!message?.text) return new Response("OK");

    const chatId = String(message.chat.id);

    // Solo acepta mensajes del chat autorizado
    if (chatId !== env.TELEGRAM_CHAT_ID) return new Response("OK");

    const text = message.text.trim();

    if (!text.startsWith("/agendar")) return new Response("OK");

    // /agendar DD/MM HH:MM Título   o   /agendar DD/MM/YYYY HH:MM Título
    const match = text.match(
      /^\/agendar\s+(\d{1,2}\/\d{1,2}(?:\/\d{2,4})?)\s+(\d{2}:\d{2})\s+(.+)$/
    );

    if (!match) {
      await sendTelegram(
        env,
        chatId,
        "❌ Formato inválido.\n\nUso: /agendar DD/MM HH:MM Título\nEjemplo: /agendar 10/06 15:00 Reunión con cliente"
      );
      return new Response("OK");
    }

    const [, dateStr, timeStr, title] = match;

    const dispatched = await dispatchGitHubAction(env, {
      mode: "create_event",
      event_title: title,
      event_date: dateStr,
      event_time: timeStr,
    });

    if (dispatched) {
      await sendTelegram(
        env,
        chatId,
        `⏳ Creando evento...\n\n📌 ${title}\n📅 ${dateStr} a las ${timeStr}\n\nTe confirmo cuando esté listo.`
      );
    } else {
      await sendTelegram(
        env,
        chatId,
        "❌ Error al disparar el workflow. Revisá los logs en GitHub Actions."
      );
    }

    return new Response("OK");
  },
};

async function dispatchGitHubAction(env, inputs) {
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "CalendarBot/1.0",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main", inputs }),
  });
  return resp.status === 204;
}

async function sendTelegram(env, chatId, text) {
  await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text }),
    }
  );
}

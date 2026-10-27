import type { MessageKey } from "./i18n.ts";

type Translate = (key: MessageKey, variables?: Record<string, string | number>) => string;

const NETWORK = /failed to fetch|networkerror|load failed|network request failed/i;

export function friendlyApiError(message: string, t: Translate): string {
  if (message.startsWith("[unauthorized]")) {
    return t("error.unauthorized");
  }
  const limit = /^\[daily_limit\][^\d]*(\d+)/.exec(message);
  if (limit) {
    return t("error.dailyLimit", { limit: limit[1] });
  }
  if (NETWORK.test(message)) {
    return t("error.request");
  }
  return message;
}

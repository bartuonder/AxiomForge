export type ListedCampaign = {
  id: string;
  title: string;
  statement?: string;
  origin?: string;
  status: string;
  updated: string;
};

const USER_ORIGINS = new Set(["console", "api"]);

export function isUserCampaign(origin: string | undefined): boolean {
  return USER_ORIGINS.has(origin ?? "");
}

export function displayTitle(item: ListedCampaign, fallback: string): string {
  const title = item.title.trim();
  if (title) {
    return title;
  }
  return item.statement?.trim() || fallback;
}

export function visibleCampaigns<T extends ListedCampaign>(items: T[], showTests: boolean, query: string): T[] {
  const needle = query.trim().toLocaleLowerCase();
  return items.filter((item) => {
    if (!showTests && !isUserCampaign(item.origin)) {
      return false;
    }
    if (!needle) {
      return true;
    }
    return `${item.title} ${item.statement ?? ""}`.toLocaleLowerCase().includes(needle);
  });
}

export function hiddenTestCount<T extends ListedCampaign>(items: T[]): number {
  return items.filter((item) => !isUserCampaign(item.origin)).length;
}

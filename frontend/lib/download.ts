const TURKISH: Record<string, string> = { ç: "c", ğ: "g", ı: "i", ö: "o", ş: "s", ü: "u" };
const MAX_SLUG = 60;

export function slug(text: string): string {
  const plain = text
    .toLocaleLowerCase("tr")
    .replace(/[çğıöşü]/g, (letter) => TURKISH[letter])
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
  return plain.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, MAX_SLUG).replace(/-+$/g, "");
}

export function reportFilename(title: string, campaignId: string): string {
  const name = slug(title) || "report";
  return `${name}-${campaignId.slice(0, 8)}.md`;
}

export function downloadText(filename: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

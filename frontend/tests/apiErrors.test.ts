import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { friendlyApiError } from "../lib/apiErrors.ts";
import { translate } from "../lib/i18n.ts";

const tr = (key: Parameters<typeof translate>[1], variables?: Record<string, string | number>) => translate("tr", key, variables);
const en = (key: Parameters<typeof translate>[1], variables?: Record<string, string | number>) => translate("en", key, variables);

describe("friendlyApiError", () => {
  it("explains a missing or wrong key", () => {
    assert.equal(friendlyApiError("[unauthorized] a valid X-API-Key header is needed", tr), "Bu işlem için geçerli bir erişim anahtarı gerekiyor. Yöneticinizden anahtarı isteyin.");
    assert.match(friendlyApiError("[unauthorized] x", en), /access key/);
  });

  it("explains the daily limit with its number", () => {
    assert.equal(friendlyApiError("[daily_limit] the limit of 20 starts per day has been reached", tr), "Bugünkü başlatma hakkı (20) doldu. Yarın yeniden deneyin ya da yöneticinizden limiti artırmasını isteyin.");
    assert.match(friendlyApiError("[daily_limit] the limit of 3 starts per day has been reached", en), /\(3\)/);
  });

  it("explains a network failure", () => {
    assert.equal(friendlyApiError("Failed to fetch", tr), tr("error.request"));
    assert.equal(friendlyApiError("NetworkError when attempting to fetch resource.", en), en("error.request"));
    assert.equal(friendlyApiError("Load failed", tr), tr("error.request"));
  });

  it("keeps any other message", () => {
    assert.equal(friendlyApiError("task queue is unavailable", tr), "task queue is unavailable");
    assert.equal(friendlyApiError("", tr), "");
  });

  it("does not take a loose mention of the tag for the tag", () => {
    assert.equal(friendlyApiError("see [unauthorized] later", tr), "see [unauthorized] later");
    assert.equal(friendlyApiError("see [daily_limit] 5 later", tr), "see [daily_limit] 5 later");
  });
});

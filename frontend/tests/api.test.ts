import { describe, expect, it } from "vitest";
import { API_BASE_URL } from "../lib/api";

describe("api client", () => {
  it("has a default base url", () => {
    expect(API_BASE_URL).toBeTruthy();
    expect(API_BASE_URL).toMatch(/^https?:\/\//);
  });
});

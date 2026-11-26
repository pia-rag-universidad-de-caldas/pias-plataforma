import { test } from "node:test";
import assert from "node:assert/strict";
import { STORAGE_KEY, loadSettings, normalizeBase, saveSettings } from "../src/settings.js";

function memory(initial = {}) {
  const values = { ...initial };
  return { getItem: (k) => values[k] ?? null, setItem: (k, v) => (values[k] = v), values };
}

test("normalizeBase drops the trailing slashes", () => {
  assert.equal(normalizeBase(" http://h:8000// "), "http://h:8000");
});

test("loadSettings without storage gives the config", () => {
  assert.deepEqual(loadSettings({ apiBase: "http://h/", token: "t" }, undefined), { apiBase: "http://h", token: "t" });
});

test("loadSettings puts the saved ones over the config", () => {
  const storage = memory({ [STORAGE_KEY]: JSON.stringify({ token: "nuevo" }) });
  assert.equal(loadSettings({ token: "viejo" }, storage).token, "nuevo");
});

test("loadSettings ignores garbage in the storage", () => {
  assert.deepEqual(loadSettings({}, memory({ [STORAGE_KEY]: "{no" })), { apiBase: "", token: "" });
});

test("loadSettings survives a storage that throws", () => {
  const storage = {
    getItem: () => {
      throw new Error("bloqueado");
    },
  };
  assert.equal(loadSettings({ token: "t" }, storage).token, "t");
});

test("saveSettings keeps only the known keys", () => {
  const storage = memory();
  saveSettings({ apiBase: "http://h/", token: "t", other: 1 }, storage);
  assert.deepEqual(JSON.parse(storage.values[STORAGE_KEY]), { apiBase: "http://h", token: "t" });
});

test("saveSettings says when the browser doesn't let it", () => {
  const storage = {
    setItem: () => {
      throw new Error("lleno");
    },
  };
  assert.equal(saveSettings({}, storage), false);
});

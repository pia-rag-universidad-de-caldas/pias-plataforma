import { test } from "node:test";
import assert from "node:assert/strict";
import {
  attachmentLine,
  citationParts,
  courseLabel,
  fileName,
  pageRanges,
  scorePercent,
  sourceDetails,
  sourceTitle,
  uniqueCourses,
} from "../src/format.js";

test("pageRanges joins consecutive pages", () => {
  assert.equal(pageRanges([8, 3, 4, 5, 4]), "3–5, 8");
});

test("pageRanges of no pages is empty", () => {
  assert.equal(pageRanges([]), "");
});

test("scorePercent rounds the cosine", () => {
  assert.equal(scorePercent(0.8234), "82 %");
});

test("fileName keeps the last segment", () => {
  assert.equal(fileName("2024/05_Mayo/Semana_02/023560/plan.pdf"), "plan.pdf");
});

test("citationParts splits the citations in range", () => {
  assert.deepEqual(citationParts("Evalúa X [1] y Y [2][3].", 3), [
    { text: "Evalúa X " },
    { cite: 1 },
    { text: " y Y " },
    { cite: 2 },
    { cite: 3 },
    { text: "." },
  ]);
});

test("citationParts reads a list inside one bracket", () => {
  assert.deepEqual(citationParts("a [1, 2]", 2), [{ text: "a " }, { cite: 1 }, { cite: 2 }]);
});

test("citationParts leaves a number out of range as text", () => {
  assert.deepEqual(citationParts("ver [7]", 2), [{ text: "ver [7]" }]);
});

test("sourceTitle falls back to the sha256", () => {
  assert.equal(sourceTitle({ id: "x", origin: null, sha256: "abcdef0123456789" }), "documento abcdef012345…");
});

test("sourceDetails shows PIAA, course, pages and score", () => {
  const source = { code: "023560", activity: "Cálculo I", pages: [3, 4], score: 0.5 };
  assert.equal(sourceDetails(source), "PIAA 023560 · Cálculo I · págs. 3–4 · 50 %");
});

test("courseLabel adds the activity code", () => {
  assert.equal(courseLabel({ sha256: "s", name: "Cálculo I", activity_code: "0100105" }), "Cálculo I (0100105)");
});

test("uniqueCourses removes a course with two documents", () => {
  const course = { name: "Cálculo I", activity_code: "0100105" };
  assert.deepEqual(uniqueCourses([{ ...course, sha256: "a" }, { ...course, sha256: "b" }]), ["Cálculo I (0100105)"]);
});

test("attachmentLine says a document was read in part", () => {
  const use = { name: "a.pdf", kind: "document", pieces: 12, truncated: true };
  assert.equal(attachmentLine(use), "a.pdf: 12 trozos (leído en parte)");
});

test("attachmentLine shows an image's description", () => {
  assert.equal(attachmentLine({ name: "f.png", kind: "image", pieces: 1, description: "un plano" }), "f.png: «un plano»");
});

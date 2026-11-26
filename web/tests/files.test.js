import { test } from "node:test";
import assert from "node:assert/strict";
import {
  attachmentKind,
  attachmentProblems,
  bytesToBase64,
  toAttachment,
  uploadProblem,
  validCode,
} from "../src/files.js";

test("attachmentKind tells documents from images", () => {
  assert.deepEqual(["a.PDF", "b.webp", "c.txt"].map(attachmentKind), ["document", "image", null]);
});

test("attachmentProblems accepts a valid list", () => {
  assert.deepEqual(attachmentProblems([{ name: "a.pdf", size: 10 }]), []);
});

test("attachmentProblems refuses more than four", () => {
  const files = Array.from({ length: 5 }, (_, i) => ({ name: `${i}.pdf`, size: 1 }));
  assert.equal(attachmentProblems(files).length, 1);
});

test("attachmentProblems refuses over 20 MiB in all", () => {
  const files = [
    { name: "a.pdf", size: 15 * 1024 * 1024 },
    { name: "b.pdf", size: 6 * 1024 * 1024 },
  ];
  assert.match(attachmentProblems(files)[0], /20 MiB/);
});

test("attachmentProblems refuses another type", () => {
  assert.match(attachmentProblems([{ name: "notas.txt", size: 3 }])[0], /notas\.txt/);
});

test("uploadProblem refuses an image", () => {
  assert.equal(uploadProblem({ name: "foto.png", size: 3 }), "solo pdf, doc o docx");
});

test("uploadProblem accepts a docx", () => {
  assert.equal(uploadProblem({ name: "plan.docx", size: 3000 }), null);
});

test("validCode wants six digits", () => {
  assert.deepEqual(["023560", "000000", "2356", "02356a"].map(validCode), [true, true, false, false]);
});

test("bytesToBase64 encodes more than one stretch", () => {
  const bytes = new Uint8Array(70000).map((_, i) => i % 256);
  assert.equal(bytesToBase64(bytes), Buffer.from(bytes).toString("base64"));
});

test("toAttachment takes the mime from the extension when the browser gives none", async () => {
  const file = { name: "plan.pdf", type: "", arrayBuffer: async () => new TextEncoder().encode("hola").buffer };
  assert.deepEqual(await toAttachment(file), { name: "plan.pdf", mime: "application/pdf", content: "aG9sYQ==" });
});

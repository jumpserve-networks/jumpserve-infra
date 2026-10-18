import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { getPostLoginPath } from "../lib/auth-redirect.ts";
import { getTestModuleForPath, LEGACY_MODULE_ROUTES, RESEARCH_IDEAS_MODULE, RESEARCH_VERIFICATION_MODULE } from "../lib/test-modules.ts";

const hook = registerHooks({ resolve(specifier, context, nextResolve) {
  return nextResolve(specifier === "./test-modules" ? new URL("../lib/test-modules.ts", import.meta.url).href : specifier, context);
} });
const { researchModulePath, researchSearchSuffix, researchStudyKind, researchWorkspacePath, studiesForPathway } = await import("../lib/research-pathways.ts");
hook.deregister();

test("paper and idea modules keep every sidebar section within their own namespace", () => {
  for (const testModule of [RESEARCH_VERIFICATION_MODULE, RESEARCH_IDEAS_MODULE]) {
    assert.equal(getTestModuleForPath(testModule.href), testModule);
    for (const section of testModule.sections) {
      assert.equal(getTestModuleForPath(section.href), testModule);
      for (const route of section.paths) assert.ok(route.startsWith(testModule.href + "/"));
    }
  }
  assert.ok(!RESEARCH_VERIFICATION_MODULE.sections.some(section => /idea/i.test(section.label)));
  assert.ok(!RESEARCH_IDEAS_MODULE.sections.some(section => /paper|assessment/i.test(section.label)));
});

test("legacy idea routes resolve to the idea module before broader paper redirects", () => {
  for (const prefix of ["/research-verification", "/module/research-verification", "/modules/research-verification"]) {
    for (const suffix of ["/new-idea", "/ideas/aca80acc-0aee-4ee4-836d-e833d2c6bd0b?view=gaps"]) {
      const route = prefix + suffix;
      assert.equal(getTestModuleForPath(route), RESEARCH_IDEAS_MODULE);
      const redirect = LEGACY_MODULE_ROUTES.find(({ source }) => route === source || route.startsWith(source + "/") || route.startsWith(source + "?"));
      assert.ok(redirect.destination.startsWith(RESEARCH_IDEAS_MODULE.href));
    }
  }
  assert.equal(getTestModuleForPath(RESEARCH_VERIFICATION_MODULE.href + "/workspace/id"), RESEARCH_VERIFICATION_MODULE);
});

test("canonical idea intake, evidence, public results and exports retain sign-in destinations", () => {
  for (const suffix of ["/new-idea", "/ideas/id", "/workspace", "/workspace/id?view=gaps", "/studies/id?view=literature", "/api/studies/id/export?format=csv"]) {
    const route = RESEARCH_IDEAS_MODULE.href + suffix;
    assert.equal(getTestModuleForPath(route), RESEARCH_IDEAS_MODULE);
    assert.equal(getPostLoginPath(route), route);
  }
});

test("mixed recorded studies split by explicit kind while older paper records stay accessible", () => {
  const studies = [{ id: "legacy" }, { id: "paper", study_kind: "paper" }, { id: "idea", study_kind: "idea" }];
  assert.deepEqual(studiesForPathway(studies, "paper").map(study => study.id), ["legacy", "paper"]);
  assert.deepEqual(studiesForPathway(studies, "idea").map(study => study.id), ["idea"]);
  assert.equal(studies.length, 3);
  for (const study of studies) {
    const base = researchModulePath(researchStudyKind(study));
    assert.equal(researchWorkspacePath(study), base + (study.study_kind === "idea" ? "/ideas/" : "/workspace/") + study.id);
  }
  assert.deepEqual(studiesForPathway([], "idea"), []);
});

test("return paths preserve repeated query values without interpreting their contents as routes", () => {
  assert.equal(researchSearchSuffix({ view: "gaps", tag: ["a&b", "c"], unknown: undefined }), "?view=gaps&tag=a%26b&tag=c");
  assert.equal(researchSearchSuffix({}), "");
});

test("paper experiment designs resume their own workspace without relabeling them as ideas", () => {
  assert.equal(researchWorkspacePath({ id: "paper", study_kind: "paper", claim_design: true }), "/research-verification/experiment-design/paper");
  assert.equal(researchWorkspacePath({ id: "idea", study_kind: "idea", claim_design: true }), "/research-ideas/ideas/idea");
});

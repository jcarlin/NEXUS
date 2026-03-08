/**
 * E2E-safe mirrors of generated OpenAPI enum values.
 *
 * Playwright tests run outside Vite, so they cannot import from
 * `@/api/generated/schemas`. Keep these in sync with the generated
 * source at `frontend/src/api/generated/schemas/`.
 */

/** frontend/src/api/generated/schemas/caseStatus.ts */
export const CaseStatus = {
  processing: "processing",
  draft: "draft",
  confirmed: "confirmed",
  failed: "failed",
} as const;

/** frontend/src/api/generated/schemas/partyRole.ts */
export const PartyRole = {
  plaintiff: "plaintiff",
  defendant: "defendant",
  third_party: "third_party",
  witness: "witness",
  counsel: "counsel",
} as const;

/** frontend/src/api/generated/schemas/loadFileFormat.ts */
export const LoadFileFormat = {
  concordance_dat: "concordance_dat",
  opticon_opt: "opticon_opt",
  edrm_xml: "edrm_xml",
} as const;

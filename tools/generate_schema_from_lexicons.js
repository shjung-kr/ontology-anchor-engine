/**
 * Generate JSON Schema enum files from lexicon JSON files
 *
 * Lexicon = single source of truth
 * Schema  = editor / validation artifact
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

/* --------------------------------------------------
 * Path setup
 * -------------------------------------------------- */
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PROJECT_ROOT = path.resolve(__dirname, "..");
const LEXICON_DIR = path.join(PROJECT_ROOT, "ontology", "lexicon");
const SCHEMA_DIR = path.join(PROJECT_ROOT, "ontology", "schema");

/* --------------------------------------------------
 * Ensure schema directory exists
 * -------------------------------------------------- */
if (!fs.existsSync(SCHEMA_DIR)) {
  fs.mkdirSync(SCHEMA_DIR, { recursive: true });
}

/* --------------------------------------------------
 * Helper: generate enum schema from a lexicon file
 * -------------------------------------------------- */
function generateEnumSchema(lexiconPath, outputSchemaPath, title) {
  const raw = fs.readFileSync(lexiconPath, "utf-8");
  const lexicon = JSON.parse(raw);

  const ids = Object.keys(lexicon).sort();

  const schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": title,
    "type": "string",
    "enum": ids
  };

  fs.writeFileSync(
    outputSchemaPath,
    JSON.stringify(schema, null, 2),
    "utf-8"
  );

  console.log(`✔ Generated schema: ${path.basename(outputSchemaPath)} (${ids.length} IDs)`);
}

/* --------------------------------------------------
 * Lexicon → Schema mapping
 * -------------------------------------------------- */
const TARGETS = [
  {
    lexicon: "claim_concepts.json",
    schema: "claim_concept.enum.schema.json",
    title: "Claim Concept ID"
  },
  {
    lexicon: "iv_features.json",
    schema: "iv_feature.enum.schema.json",
    title: "IV Feature ID"
  },
  {
    lexicon: "physical_assumptions.json",
    schema: "physical_assumption.enum.schema.json",
    title: "Physical Assumption ID"
  },
  {
    lexicon: "measurement_conditions.json",
    schema: "measurement_condition.enum.schema.json",
    title: "Measurement Condition ID"
  }
];

/* --------------------------------------------------
 * Run generation
 * -------------------------------------------------- */
console.log("🔧 Generating JSON Schemas from lexicons...\n");

for (const target of TARGETS) {
  const lexiconPath = path.join(LEXICON_DIR, target.lexicon);
  const schemaPath = path.join(SCHEMA_DIR, target.schema);

  if (!fs.existsSync(lexiconPath)) {
    console.warn(`⚠ Lexicon not found: ${target.lexicon} (skipped)`);
    continue;
  }

  generateEnumSchema(lexiconPath, schemaPath, target.title);
}

console.log("\n✅ Schema generation completed.");

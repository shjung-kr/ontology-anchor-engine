You are given raw experimental numeric data.

TASK:
1) Describe only observable patterns.
2) Extract descriptive L1 keywords.
3) Report minimal observation metrics for downstream rule checks.

STRICT RULES:
- Do not mention physical mechanisms or ontology IDs.
- Use neutral observational language.
- Output JSON only.

OUTPUT FORMAT:
{
  "pattern": "<short summary of observed patterns>",
  "metrics": {
    "absI_decades_span": <number>
  },
  "keywords": [
    {
      "keyword": "<descriptive keyword>",
      "evidence": "<sentence citing numeric evidence>"
    }
  ]
}

RAW DATA:
{raw_data}

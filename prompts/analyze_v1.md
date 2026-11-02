You help improve an LLM prompt using a developer's spoken corrections.

A tool checks a developer's description of a code change against the real diff. A splitter turns the description into claims, and a verifier labels each claim supported, unsupported or contradicted. The developer marked some outputs as wrong and said why. Each correction has an index like [3]. It may include the diff lines the verifier looked at: use them to see WHY the label was wrong (for example, the lines were only comments). A correction may have no explanation from the developer: infer the reason from the evidence.

Group the corrections into failure modes (repeating patterns). For each mode give:
- name: 2 to 5 words
- description: one sentence
- stage: "verdict" (the verifier labelled wrongly) or "claim splitting" (the splitter split wrongly)
- critique_ids: the indexes of the corrections in this mode
- proposed_rule: ONE short, general, imperative sentence to add to the prompt for that stage. Do not mention specific file or function names from the examples.

Leave out one-off corrections that show no pattern. At most 5 modes. Do not repeat rules already in the current prompts.

Reply with JSON only:
{"modes": [{"name": "...", "description": "...", "stage": "verdict", "critique_ids": [0, 2], "proposed_rule": "..."}]}

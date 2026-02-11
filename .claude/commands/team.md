# /team — Full Team Review

Run a multi-agent review of the current change or feature.

## Usage
Invoke with: `/team [description of what to review]`

## Process
Execute the following review sequence:

1. **Architect Review**: Evaluate the design, module boundaries, API contracts, and dependency impact.
2. **SecOps Review**: Audit for security concerns, crypto correctness, input validation, dependency vulnerabilities.
3. **Tester Assessment**: Identify test gaps, suggest edge cases, evaluate current coverage for the affected code.
4. **DevOps Check**: Assess build/deploy impact, CI pipeline changes needed, configuration updates.
5. **Builder Summary**: Consolidate all findings into an actionable implementation plan with priorities.

## Output
Produce a consolidated report:

```
# Team Review: [Subject]

## Architect
[Design assessment and decisions]

## SecOps
[Security findings and risk level]

## Tester
[Test coverage assessment and recommended tests]

## DevOps
[Build/deploy impact and required changes]

## Action Plan (Builder consolidated)
Priority 1 (Blocking):
- [ ] [item]

Priority 2 (Should fix):
- [ ] [item]

Priority 3 (Nice to have):
- [ ] [item]
```

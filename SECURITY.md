# Security Policy

Zorvy analyses hostile content: phishing messages, impersonation links and
fraudulent documents. We treat reports about the product itself with the same
seriousness as reports about the content it analyses.

## Supported versions

| Version | Supported |
| --- | --- |
| 2.x (`main`) | Yes |
| 1.x / `legacy/streamlit` | No — preserved MVP, not deployed |

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Use GitHub's private vulnerability reporting on this repository:
*Security* → *Advisories* → *Report a vulnerability*.

Please include:

- The affected endpoint or screen, and the version or commit.
- Reproduction steps, including the payload if the issue involves intake.
- The impact you believe is possible (data exposure, tenant boundary, auth bypass).
- Whether you have already disclosed it elsewhere.

## What we commit to

| Stage | Target |
| --- | --- |
| Acknowledgement | 2 business days |
| Initial assessment and severity | 5 business days |
| Fix or documented mitigation for critical issues | 30 days |
| Credit in the advisory | On request |

We will not pursue legal action against researchers who act in good faith,
respect privacy, avoid data destruction, and give us reasonable time to fix
the issue before disclosure.

## Scope

In scope:

- Authentication, session handling and token rotation
- Tenant and user data isolation
- File upload and document parsing (path traversal, parser abuse, decompression bombs)
- Prompt-injection paths that could change a verdict or bypass claim verification
- Rate limiting and denial-of-service resilience

Out of scope:

- Findings that require a compromised device or mailbox
- Missing hardening headers with no demonstrated impact
- Social engineering of staff
- Third-party services we do not control

## Handling of customer content

Uploaded artifacts and investigation reports may contain personal data. When
reporting an issue, redact real names, phone numbers and account numbers. A
synthetic reproduction is always sufficient.

## Data incidents

If you believe customer data has been exposed, report it through the same
private channel and mark the report **URGENT**. Incident response follows the
retention and notification obligations described in the compliance section of
the platform documentation.

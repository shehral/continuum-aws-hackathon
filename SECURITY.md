# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability in this project, please report it responsibly:

1. **Do NOT** create a public GitHub issue
2. Email Ali Shehral directly at shehral.m@northeastern.edu
3. Provide a detailed description of the vulnerability
4. Allow reasonable time for the issue to be addressed before disclosure

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| Others  | :x:                |

## Security Measures

This project implements several security measures:

- JWT-based authentication with signature validation
- Multi-tenant data isolation
- Per-user rate limiting
- Input validation and sanitization
- Security headers middleware
- Prompt injection defense for LLM inputs
- Secrets management via environment variables

## Third-Party Dependencies

This project depends on several third-party services and libraries. Security updates
for dependencies are monitored and applied regularly.

## Disclaimer

This is a research project and should not be used in production environments
handling sensitive data without additional security review.

# Model Guard rules — write what you want in plain English.
# This file is YOUR policy. Jev reads it as context on every judgment;
# the deterministic fast-path also honors the Sensitive section.
# Lines starting with `#` are headings or comments. Bullets use `-`.

## Always allow
# Things the agent may do without asking. Be specific: "run tests" is
# better than "be helpful". Examples:
- read files, list directories, and search inside this project
- run the project's tests, linter, and typechecker
- edit code inside this project folder

## Ask me first
# Things that pause for your approval. This is the sweet spot for most
# daily work: the agent keeps momentum, you keep control.
- installing new packages or dependencies
- pushing to shared branches, publishing, or deploying anything
- any command using sudo or administrator rights
- reading credentials, secrets, or private keys

## Never allow
# Hard lines. Deterministic patterns still back these up, but writing them
# here tells Jev your intent in your own words.
- deleting anything outside the current project folder
- sending code, files, or secrets to servers I don't recognize
- wiping disks, formatting drives, or shutting machines down

## Sensitive paths
# One path per bullet. Any action touching these needs approval minimum.
- ~/.ssh
- ~/.aws
- .env

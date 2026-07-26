# Community tools

Small tools that make the Kit nicer to live with, contributed by the people who build it. Think a Jetson performance tuner, a one-command helper to log into the board, a plugin, a script that automates a fiddly setup step. Things too small to deserve their own repo but too useful to keep to yourself.

This is deliberately separate from the core (`driver/`, `provisioning/`, `calibration/`) so community tools can move fast and stay optional. Nothing here is required to run the Kit.

## Adding one

- Drop it in its own subfolder with a short `README.md`: what it does, how to run it, what it assumes.
- Keep it **small and self-contained**. If it grows into a real project, give it its own repo and link it from the [forum](https://forum.reco-project.org) instead.
- Tools here are **Apache-2.0** (the repo's software license) unless your tool's own `LICENSE` says otherwise.
- No secrets, no private hostnames or keys. Take host/user as arguments, like the provisioning scripts do.

## Good first candidates

- A Jetson performance / power-profile tuner (clocks, `nvpmodel`, fan curve).
- A remote-login / port-forward helper for the board.
- A calibration quality-of-life wrapper.
- A monitoring or health-check script for a unit left filming unattended.

Share what you build on the [forum](https://forum.reco-project.org) so others find it.

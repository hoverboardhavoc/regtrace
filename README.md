# regtrace

Register-trace comparison tool for validating that two implementations of a microcontroller HAL produce equivalent peripheral configurations.

See [SPEC.md](SPEC.md) for design and roadmap. See [implementation-log.md](implementation-log.md) for the running log of implementation decisions.

## Quick start

```bash
git clone <this-repo> ~/dev/regtrace
cd ~/dev/regtrace
python3.10 -m venv .venv && source .venv/bin/activate
pip install -e .
regtrace selftest --bootstrap
```

`regtrace selftest` validates the toolchain and sibling repositories. `--bootstrap` clones any missing sibling repos at the commits pinned in `bootstrap.toml`.

## License

[MPL-2.0](LICENSE).

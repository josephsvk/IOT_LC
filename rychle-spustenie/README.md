# Rýchle spustenie

Dvojklikom spustite `render.sh` alebo v termináli použite:

```bash
./rychle-spustenie/render.sh
```

Vygeneruje 3D pohľady PCB do `docs/images/` a obnoví SMD výstupy v koreňovom
priečinku projektu. Pre render bez súčiastok označených DNP použite:

```bash
./rychle-spustenie/render.sh --no-dnp
```

Potrebné sú Python 3 a `kicad-cli` dostupný v `PATH`. Render sa teraz spúšťa
ručne týmto skriptom.

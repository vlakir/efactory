# ТЗ: Система сквозной разработки РЭА на базе ИИ

**Версия:** 5.1  
**Принципы:**
- Максимальное использование готовых решений, минимум собственного кода
- Максимальная автоматизация: система самостоятельно управляет внешними приложениями (KiCad, FreeCAD, ngspice, FEMM) — открывает, закрывает, перезапускает без ручного вмешательства пользователя
- Кроссплатформенность: Linux и Windows как минимально поддерживаемые платформы

---

## 1. Назначение

Универсальная система сквозной разработки радиоэлектронной аппаратуры на базе ИИ — от идеи до полного пакета производственной документации. Охватывает аналоговую, цифровую и смешанную схемотехнику: разработка и оптимизация схемы → SPICE-моделирование → проектирование PCB → проектирование намоточных изделий → проектирование корпуса → формирование производственной документации.

**Области применения:**
- Аналоговая аудиотехника (ламповая, транзисторная, гибридная)
- Источники питания (линейные, импульсные)
- Цифровые и микроконтроллерные системы
- RF и связная аппаратура
- Измерительная техника
- Любая заказная электроника

Построена на MCP-серверах и универсальном чат-клиенте с поддержкой нескольких LLM-бэкендов (Claude Code Max без API, Anthropic API, OpenAI-совместимые API, Ollama). Быстрое развёртывание на чистой Linux-машине.

**Сквозной пайплайн:**

```
Идея / ТЗ на устройство
    ↓
Схемотехника ──── KiCad + mcp-kicad-sch-api
    ↓
Моделирование ─── ngspice + SPICEBridge
    ↓  ↺ итеративная оптимизация
Валидация ─────── ERC/DRC/DFM + kicad-mcp-pro
    ↓
PCB-дизайн ────── kicad-mcp-pro + FreeRouting
    ↓
Намоточные ────── PyOpenMagnetics + FEMM + MVB
изделия           (трансформаторы, дроссели)
    ↓
Корпус ────────── FreeCAD + freecad-mcp
    ↓
Документация ──── полный пакет для производства
    │
    ├── Схема (PDF/SVG)
    ├── BOM (CSV/XLSX)
    ├── Gerber + drill
    ├── Pick-and-place
    ├── Спецификации намоточных изделий
    ├── Развёртки корпуса (DXF)
    ├── 3D-модель сборки (STEP)
    ├── Отчёт о моделировании
    └── Сборочный чертёж
```

---

## 2. Готовые компоненты

### 2.1. Создание и редактирование схем

**kicad-sch-api** — Python-библиотека (MIT, PyPI: `pip install kicad-sch-api`)
- Программное создание и модификация .kicad_sch файлов
- Побайтовое сохранение формата KiCad
- Добавление компонентов, проводников, меток, иерархических листов
- Доступ к библиотекам символов KiCad
- Анализ связности (трассировка цепей, пинов)
- Не требует запущенного KiCad
- Совместимость: KiCad 7/8/9/10 (формат .kicad_sch обратно совместим)
- 70+ тестов, примеры (voltage divider, RC filter, power supply, STM32)

**mcp-kicad-sch-api** — MCP-сервер на базе kicad-sch-api (MIT)
- 15 инструментов для создания, модификации и анализа схем
- stdio-транспорт, совместим с Claude Desktop и Claude Code
- Готовая конфигурация, Dockerfile

**Репозитории:**
- https://github.com/circuit-synth/kicad-sch-api
- https://github.com/circuit-synth/mcp-kicad-sch-api

### 2.2. Управление проектами, анализ, PCB, валидация, экспорт

**kicad-mcp-pro (oaslananka)** — комплексный MCP-сервер для KiCad 10 (PyPI: `pip install kicad-mcp-pro`)
- Управление проектами: создание, навигация, recent-project discovery
- Схемы: символы, провода, метки, шины, аннотация, шаблоны, IPC reload
- PCB: board state, дорожки, via, footprints, слои, зоны, размещение, синхронизация со схемой
- Валидация: ERC/DRC/DFM + quality gates (schematic quality, connectivity, PCB quality, placement, transfer, manufacturing)
- Экспорт: Gerber, drill, BOM, PDF, netlist, STEP, render, pick-and-place, IPC-2581, SVG, DXF
- Gated release: экспорт производственных файлов только после прохождения quality gates
- Интеграция FreeRouting (автотрассировка)
- SI/PI/EMC хелперы
- Simulation хелперы (базовые; для глубокого моделирования — SPICEBridge)
- Библиотеки: поиск символов и footprints
- Version control хелперы
- Серверные профили: `minimal`, `pcb_only`, `schematic_only`, `manufacturing`, `analysis`, `agent_full`
- CLI-диагностика: `health --json`, `doctor --json`
- Companion: VS Code расширение kicad-studio (схемы, PCB, DRC, BOM, AI-провайдеры)

**Репозиторий:** https://github.com/oaslananka/kicad-mcp-pro

**Примечание:** kicad-mcp-pro заменяет ранее рассматривавшиеся Seeed Studio kicad-mcp-server и mixelpixx KiCAD-MCP-Server, покрывая функциональность обоих и добавляя quality gates, DFM, SI/PI/EMC, серверные профили и gated release.

### 2.3. Моделирование (ngspice)

**SPICEBridge** — MCP-сервер для ngspice (MIT)
- 18 инструментов: шаблоны, создание нетлистов, симуляция (AC/tran/DC), измерения, проверка по спецификации, генерация схем
- Авторасчёт номиналов по ряду E24
- stdio (Claude Code) и HTTP + Cloudflare tunnel (удалённый доступ)
- Активный проект (HN: май 2026)

**PySpice** — Python-библиотека для интерфейса с ngspice (GPLv3, PyPI)
- Shared library mode: прямой доступ к ngspice через CFFI
- Объектно-ориентированный API для построения нетлистов
- Импорт нетлистов из KiCad
- Результаты как NumPy-массивы
- KiCadTools модуль для чтения .kicad_sch и генерации нетлистов

**Репозитории:**
- https://github.com/clanker-lover/spicebridge
- https://github.com/PySpice-org/PySpice

### 2.4. Библиотеки SPICE-моделей ламп

| Источник | Описание | Формат |
|----------|----------|--------|
| Norman Koren | Классические модели (12AX7, 12AU7, 12AT7, EL34, 6L6, 6SN7, 6V6 и др.) | .LIB (PSpice-совместимый) |
| Ayumi Nakabayashi | Улучшенные модели, считаются более точными чем Koren | .INC (требуют замены `^` на `**` для ngspice) |
| Duncan's Amp Pages | Коллекция моделей (5AR4, 5U4, 6DJ8, 6SL7, 6SN7, 12AX7, KT-88, WE300B и др.) | .cir |
| Gleb Zaslavsky | Python-инструмент: извлечение параметров Koren из сканов даташитов | Python + GUI |
| labtroll/KiCad-Simulations | Готовые KiCad-проекты с симуляциями (аудиоусилители, БП, осцилляторы) | .kicad_sch + .kicad_pro |

**Репозитории:**
- https://github.com/Gleb-Zaslavsky/Tube-curve-fitting-by-Koren-triode-model
- https://github.com/labtroll/KiCad-Simulations
- http://tdsl.duncanamps.com/dcigna/tubes/spice/

### 2.5. Утилиты KiCad

**kicad-cli** — командная строка KiCad (входит в поставку KiCad 10)
- `kicad-cli sch export netlist` — экспорт SPICE-нетлиста из .kicad_sch
- `kicad-cli sch export svg` — рендер схемы в SVG
- `kicad-cli sch erc` — проверка электрических правил
- Работает headless, пригоден для автоматизации

**kicad-python** — официальные Python-биндинги к IPC API (MIT, PyPI)
- Версия 0.7.1 (апрель 2026)
- Пока только PCB-редактор; поддержка схем планируется
- Требует запущенный KiCad 10
- Перспективно для будущих версий

### 2.6. Дополнительные инструменты для PCB

**FreeRouting** — автотрассировщик PCB (GPL, Java)
- Интегрирован в kicad-mcp-pro, но может использоваться и standalone
- CLI для headless-режима: `java -jar freerouting.jar -de MyBoard.dsn -do MyBoard.ses`
- Публичный API: https://api.freerouting.app/v1
- Self-hosted: Docker-образы для linux/amd64 и linux/arm64
- Может игнорировать выбранные net classes (GND, VCC) для ручной трассировки силовых цепей
- Репозиторий: https://github.com/freerouting/freerouting

**pcbnew Python API** — встроенный в KiCad API для работы с PCB (стабильный, в отличие от eeschema)
- Программное размещение компонентов, создание дорожек, зон
- Доступ к DRC
- Экспорт в различные форматы
- Работает через `import pcbnew` в Python

**kicad-cli** (PCB-функции):
- `kicad-cli pcb export gerbers` — экспорт Gerber-файлов
- `kicad-cli pcb export drill` — файлы сверловки
- `kicad-cli pcb export svg` — рендер PCB в SVG
- `kicad-cli pcb export step` — 3D-модель STEP
- `kicad-cli pcb export pos` — pick-and-place файлы
- `kicad-cli pcb drc` — проверка проектных правил

### 2.7. Проектирование корпусов (2D + 3D)

**freecad-mcp (neka-nat)** — MCP-сервер для FreeCAD (MIT, 617 stars)
- 10 инструментов для 3D-моделирования
- Библиотека стандартных деталей
- Удалённый RPC: MCP-клиент ↔ FreeCAD через socket
- Работает как addon внутри FreeCAD
- Поддержка визуальной обратной связи (рендер → клиент)
- Репозиторий: https://github.com/neka-nat/freecad-mcp

**FreeCAD** — параметрический 3D САПР (LGPL, версия 1.0+)
- Part Design — полноценное параметрическое 3D-моделирование
- Sheet Metal — проектирование деталей из листового металла: сгибы, развёртки, экспорт DXF
- Assembly — сборки с ограничениями
- TechDraw — генерация 2D-чертежей с размерами из 3D-моделей
- Draft — 2D-черчение, DXF-экспорт
- STEP-импорт/экспорт — интеграция с KiCad (импорт 3D-модели PCB)
- Python API — полный программный доступ ко всем workbenches
- FEM — конечно-элементный анализ (опционально, для прочностных расчётов)

**Интеграция с KiCad:**
- KiCad экспортирует PCB как STEP (`kicad-cli pcb export step`)
- FreeCAD импортирует STEP → 3D-модель платы с компонентами
- Корпус проектируется вокруг реальной геометрии платы
- Итоговая сборка: плата + корпус + крепёж → STEP + чертежи

### 2.8. Проектирование намоточных изделий (трансформаторы, дроссели)

**PyOpenMagnetics** — Python-библиотека (MIT, PyPI)
- Обёртка для MKF (Magnetics Knowledge Foundation) — движок моделирования OpenMagnetics
- База данных: 10 000+ сердечников от TDK, Ferroxcube и др.
- Материалы: ферриты, кремнистая сталь, аморфные, нанокристаллические
- Расчёт: потери в сердечнике, потери в меди (вкл. AC-эффекты), температура
- AI-ready: файл AGENTS.md с инструкциями для LLM
- Репозиторий: https://github.com/OpenMagnetics/PyOpenMagnetics

**MAS (Magnetic Agnostic Structure)** — стандартизированный JSON-формат
- Универсальное описание магнитных компонентов: сердечник, обмотки, материалы, режим работы
- Базы: формы сердечников (ETD, PQ, RM, EI, тороиды...), материалы (N87, N97, 3C95...), провода (круглый, Litz, фольга...)
- Совместимость: ngspice, LTSpice, FEMM, Ansys Maxwell
- Репозиторий: https://github.com/OpenMagnetics/MAS

**MVB (Magnetics Virtual Builder)** — генератор моделей для FreeCAD
- Создаёт 2D и 3D модели магнитных компонентов из MAS-описания
- Технические чертежи, сетки для FEA
- Прямая интеграция OpenMagnetics → FreeCAD
- Репозиторий: https://github.com/OpenMagnetics/MVB

**transformer_designer** — веб-приложение для расчёта трансформаторов (Python + FastAPI)
- Опциональный компонент: используется как справочный веб-интерфейс для ручной верификации расчётов PyOpenMagnetics
- Не интегрируется как MCP-сервер — все программные расчёты идут через PyOpenMagnetics
- Методы: McLyman Ap, McLyman Kg, Erickson Kgfe
- Может запускаться локально: `uvicorn transformer_designer:app`
- Репозиторий: https://github.com/Denys/transformer_designer

**FEMM** — конечно-элементный анализ магнитных полей (бесплатный)
- 2D FEA: распределение магнитного поля, потери, индуктивность
- Скриптуется через Python (pyFEMM) и Lua
- Верификация расчётов трансформаторов и дросселей
- Сайт: https://www.femm.info

### 2.9. Помехозащита, безопасность и верификация

**Инструменты анализа помехозащиты (встроены в kicad-mcp-pro):**
- SI (Signal Integrity) хелперы: анализ целостности сигналов, отражения, crosstalk
- PI (Power Integrity) хелперы: анализ целостности цепей питания, падения напряжения, пульсации
- EMC хелперы: оценка электромагнитной совместимости

**KiCad встроенные средства:**
- Зоны заливки (copper pour) для земляных полигонов
- Дифференциальные пары с контролем импеданса
- Правила проектирования с настраиваемыми зазорами по классам цепей (ВН / сигнал / питание / земля)
- 3D-визуализация для проверки экранирования

**pyFEMM** — для анализа экранирования трансформаторов и индуктивных наводок

**Нет готового MCP-сервера для:**
- Автоматической генерации чеклистов электробезопасности — реализуем в bridge
- Импорта измерений с приборов — реализуем в bridge
- Автоматического анализа схемы заземления — LLM + правила в system prompt

---

## 3. Архитектура

### 3.1. Принцип

Тонкий оркестрационный слой + универсальный чат-клиент. Готовые MCP-серверы делают всю тяжёлую работу. Наш код связывает их в единый пайплайн и предоставляет интерфейс для работы с любой LLM.

**Ключевое архитектурное решение: наш чат-клиент — единственный MCP-клиент.**

Чат-клиент (`kicad-sim-chat`) всегда сам подключается к MCP-серверам и исполняет tool calls. LLM-бэкенды (любые, включая Claude Code Max) используются **только как языковые модели** — получают промпт с описанием инструментов, генерируют tool_use, но не исполняют вызовы. Это обеспечивает:
- Единообразие: все бэкенды работают одинаково
- Проектные функции (DDR, сессии, project.yaml) работают всегда, независимо от бэкенда
- Полный контроль: клиент видит все tool calls, логирует, привязывает к проекту
- Для Claude Code Max: используется `claude -p` только для генерации текста/tool_use, не для исполнения инструментов

### 3.2. Общая схема

```
┌──────────────────────────────────────────────────────────────┐
│  kicad-sim-chat (универсальный чат-клиент)                    │
│                                                               │
│  ┌──────────────────┐  ┌──────────────────────────────────┐   │
│  │ Backend Router   │  │ MCP Client (5 серверов)          │   │
│  │                  │  │                                  │   │
│  │ • claude-code-max│  │ ┌──────────────────────────────┐ │   │
│  │ • anthropic-api  │  │ │ mcp-kicad-sch-api            │ │   │
│  │ • openai-compat  │  │ │ (создание/редактирование схем)│ │   │
│  │ • ollama         │  │ ├──────────────────────────────┤ │   │
│  │                  │  │ │ kicad-mcp-pro                │ │   │
│  └──────────────────┘  │ │ (проект, PCB, DRC, экспорт)  │ │   │
│                        │ ├──────────────────────────────┤ │   │
│  ┌──────────────────┐  │ │ spicebridge                  │ │   │
│  │ Session Manager  │  │ │ (SPICE-моделирование)        │ │   │
│  │ + App Manager    │  │ ├──────────────────────────────┤ │   │
│  │ + Platform Layer │  │ │ freecad-mcp                  │ │   │
│  │                  │  │ │ (3D-моделирование корпусов)  │ │   │
│  │ контекст,        │  │ ├──────────────────────────────┤ │   │
│  │ история,         │  │ │ kicad-sim-bridge (наш)       │ │   │
│  │ процессы,        │  │ │ оркестрация + доп. модули:   │ │   │
│  │ результаты       │  │ │ PCB, P2P, magnetics,         │ │   │
│  │                  │  │ │ enclosure, safety, PSU,       │ │   │
│  └──────────────────┘  │ │ measurement, export          │ │   │
│                        │ └──────────────────────────────┘ │   │
│                        └──────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 3.3. Компоненты собственной разработки

**kicad-sim-bridge** — оркестрационный MCP-сервер, связывающий все готовые инструменты в единый пайплайн. Содержит модули:

| Модуль | Инструменты | Строк |
|--------|------------|-------|
| `pipeline.py` | `bridge_design_to_sim`, `bridge_edit_and_resim`, `bridge_sweep` | ~200 |
| `models_manager.py` | `model_library`, `model_assign`, `model_search` | ~100 |
| `pcb_bridge.py` | `pcb_from_schematic`, `pcb_place`, `pcb_autoroute`, `pcb_validate`, `pcb_export`, `pcb_emi_check` | ~300 |
| `p2p_bridge.py` | `p2p_layout`, `p2p_wiring_table`, `p2p_wiring_diagram` | ~250 |
| `mag_bridge.py` | `mag_select_core`, `mag_design_transformer`, `mag_design_choke`, `mag_calc_parasitics`, `mag_verify_femm`, `mag_build_3d`, `mag_export_winding_spec` | ~300 |
| `enclosure_bridge.py` | `enclosure_from_pcb`, `enclosure_add_cutout`, `enclosure_sheet_metal`, `enclosure_assembly`, `enclosure_export`, `enclosure_render` | ~200 |
| `safety.py` | `safety_checklist`, `pcb_emi_check` (обёртка над SI/PI/EMC хелперами kicad-mcp-pro + собственные аудио/ВН-правила) | ~200 |
| `psu_wizard.py` | `psu_wizard` (линейные + SMPS топологии) | ~200 |
| `measurement.py` | `bridge_import_measurement`, `bridge_compare_sim_vs_measured` | ~150 |
| `export_production.py` | `/export-production` — сборка полного пакета | ~300 |
| `app_manager.py` | Управление KiCad/FreeCAD/FEMM процессами | ~150 |
| `platform_layer.py` | Абстракция Linux/Windows | ~150 |

**Принцип разграничения:** kicad-sim-bridge никогда не дублирует функции готовых MCP-серверов. Он вызывает их инструменты и добавляет логику, которой нет ни в одном из них: пайплайн между инструментами, предметно-ориентированные проверки, формирование документации.
| `model_library` | Управление коллекцией SPICE-моделей: список, поиск, добавление, импорт |
| `model_assign` | Назначить SPICE-модель компоненту с правильным pin mapping |
| `render_schematic` | Рендер .kicad_sch в SVG через kicad-cli |

**kicad-sim-chat** — универсальный чат-клиент (~1300 строк Python):
- Терминальный UI на Rich
- Четыре LLM-бэкенда
- MCP-клиент с единым реестром инструментов
- Управление сессиями

**bootstrap.sh** — скрипт развёртывания (~200 строк bash)

### 3.4. Рабочая область

```
~/kicad-workspace/
├── projects/                   # проекты (структура каждого — см. §4.2)
│   ├── SE-6P14P/
│   │   ├── project.yaml        # манифест
│   │   ├── schematic/          # схемы
│   │   ├── sim/                # результаты моделирования
│   │   ├── pcb/ или p2p/      # плата или навесной монтаж
│   │   ├── magnetics/          # намоточные изделия
│   │   ├── enclosure/          # корпус
│   │   ├── decisions/          # журнал решений (DDR)
│   │   ├── sessions/           # история сессий с ИИ
│   │   └── .git/
│   └── stm32-controller/
│       └── ...
├── models/                     # глобальная библиотека SPICE-моделей
│   ├── index.json
│   ├── tubes/
│   │   ├── koren/
│   │   ├── ayumi/
│   │   └── custom/
│   ├── opamps/
│   ├── transistors/
│   └── passives/
├── templates/                  # шаблоны проектов
│   ├── analog-audio/
│   ├── smps/
│   ├── digital-mcu/
│   └── custom/
└── archives/                   # архивы проектов для переноса
```

---

## 4. Проект как базовая сущность

### 4.1. Концепция

Проект — центральная сущность системы, вокруг которой строится работа. Это самодостаточный, портативный контейнер, содержащий все артефакты разработки, историю решений и сессий с ИИ.

**Принципы:**
- Всё в одной папке: схемы, PCB, корпус, модели, симуляции, документация, история
- Полная трассируемость: каждое изменение привязано к решению, каждое решение — к сессии с ИИ и результату симуляции
- Портативность: папку проекта можно заархивировать, перенести на другую машину, расшарить
- Самоописание: манифест `project.yaml` описывает текущее состояние, не нужно помнить, на чём остановились
- **Гибкий скоуп: проект не обязан быть сквозным.** Пользователь сам определяет, какие фазы ему нужны. Система не навязывает линейный пайплайн

**Типовые сценарии использования проекта:**

| Сценарий | Что входит | Что не нужно |
|----------|-----------|--------------|
| Сквозная разработка с нуля | Всё: схема → симуляция → PCB → намоточные → корпус → документация | — |
| Только моделирование | Импорт существующей схемы → симуляция → оптимизация | PCB, корпус, документация |
| Только PCB | Импорт .kicad_sch → разводка → Gerber | Симуляция, намоточные, корпус |
| Только корпус | Импорт .kicad_pcb (STEP) → FreeCAD → развёртки DXF | Схема, симуляция |
| Только намоточные | Расчёт трансформатора / дросселя по ТТХ → спецификация для намотчика | Схема, PCB, корпус |
| Доработка существующего | Импорт проекта → изменение части → пересимуляция → обновление PCB | Зависит от задачи |
| Только документация | Сборка production-package из готовых артефактов | Проектирование |

**Создание проекта с указанием скоупа:**

```
/project new "my-filter" --phases schematic,simulation
/project new "pcb-for-client" --phases pcb --import-schematic ~/existing/filter.kicad_sch
/project new "transformer-calc" --phases magnetics
/project new "full-amp" --phases all
```

По умолчанию `--phases all`, но ненужные фазы остаются в статусе `skipped` и не создают пустых папок. Фазы можно добавлять позже:

```
/project add-phase pcb        # решили, что плата всё-таки нужна
/project skip-phase enclosure  # корпус не нужен
```

### 4.2. Структура проекта

Папки создаются только для активных фаз. Проект с `--phases schematic,simulation` будет содержать только `schematic/`, `sim/`, `decisions/`, `sessions/` и `project.yaml`. Остальные появятся при `/project add-phase`.

```
~/kicad-workspace/projects/SE-6P14P/
│
├── project.yaml                  # манифест проекта (см. 4.3)
│
├── schematic/                    # схемотехника
│   ├── SE-6P14P.kicad_pro
│   ├── SE-6P14P.kicad_sch
│   └── psu.kicad_sch             # подсхема БП (если отдельно)
│
├── sim/                          # результаты моделирования
│   ├── netlist.cir               # текущий нетлист
│   ├── ac_final.json             # summary последнего AC-анализа
│   ├── tran_1khz.json            # summary transient
│   ├── op_point.json             # рабочие точки
│   ├── raw/                      # полные данные (.raw, большие файлы)
│   └── comparisons/              # сравнения вариантов
│       └── triode_vs_pentode.json
│
├── pcb/                          # печатная плата
│   ├── SE-6P14P.kicad_pcb
│   └── manufacturing/            # файлы для производства
│       ├── gerber/
│       ├── drill/
│       ├── bom.csv
│       └── pick-and-place.csv
│
├── p2p/                          # навесной монтаж (альтернатива pcb/)
│   ├── wiring_diagram.svg
│   ├── chassis_layout.svg
│   └── wiring_table.csv
│
├── magnetics/                    # намоточные изделия
│   ├── OT1_output_transformer/
│   │   ├── design.json           # параметры (MAS-формат)
│   │   ├── winding_spec.pdf
│   │   ├── model.step            # 3D (MVB)
│   │   └── spice_model.lib       # SPICE .subckt с паразитами
│   ├── PT1_power_transformer/
│   └── L1_choke/
│
├── enclosure/                    # корпус
│   ├── chassis.FCStd             # FreeCAD проект
│   ├── chassis_flat.dxf          # развёртка
│   ├── front_panel.dxf
│   ├── rear_panel.dxf
│   ├── assembly.step             # полная сборка
│   └── assembly_drawing.pdf
│
├── models/                       # локальные SPICE-модели проекта
│   ├── 6P14P_triode.lib          # ссылка или копия из глобальной библиотеки
│   └── custom_speaker_load.lib   # кастомная модель нагрузки
│
├── measurements/                 # импортированные измерения
│   ├── ac_sweep_real.csv
│   ├── op_points_measured.json
│   └── sim_vs_measured.json      # отчёт о расхождениях
│
├── decisions/                    # журнал проектных решений
│   ├── D001_triode_mode.md
│   ├── D002_c2_increase.md
│   └── D003_grounding_scheme.md
│
├── sessions/                     # история сессий с ИИ
│   ├── session_001.json          # полный контекст разговора
│   ├── session_002.json
│   └── session_index.json        # индекс: сессия → изменения → решения
│
├── production-package/           # финальный пакет (Phase 7)
│   └── ... (генерируется автоматически)
│
├── .gitignore
└── .git/                         # version control
```

### 4.3. Манифест проекта (project.yaml)

```yaml
name: "SE-6P14P"
description: "Однотактный ламповый усилитель на 6П14П в триодном включении"
type: analog_audio            # analog_audio | smps | digital | mixed | rf | custom
assembly: pcb                 # pcb | p2p
status: simulated             # idea | schematic | simulated | pcb_designed |
                              # magnetics_done | enclosure_done | production_ready
created: 2026-05-15
updated: 2026-05-20
author: "Vladimir"
revision: "B"
target_manufacturer: jlcpcb   # jlcpcb | pcbway | generic | none

# Импортированные артефакты (если проект начат не с нуля)
imports:
  # schematic: "~/external/filter.kicad_sch"   # раскомментировать при импорте

# Текущие ТТХ (обновляются автоматически после каждой симуляции)
specifications:
  output_power: "2W @ 8 Ohm"
  frequency_response: "18 Hz – 38.2 kHz (-3 dB)"
  thd_1khz: "0.8%"
  gain: "12.3 dB"
  supply_voltage: "280V"
  heater: "6.3V AC"

# Трекинг фаз (skipped — фаза не нужна для данного проекта)
phases:
  schematic:    {status: done,        completed: 2026-05-16}
  simulation:   {status: done,        completed: 2026-05-18}
  pcb:          {status: in_progress, started: 2026-05-19}
  magnetics:    {status: pending}
  enclosure:    {status: skipped}     # корпус не нужен
  documentation:{status: pending}

# Состав устройства (для многоплатных проектов)
boards:
  - id: main
    schematic: schematic/SE-6P14P.kicad_sch
    pcb: pcb/SE-6P14P.kicad_pcb
    description: "Основная плата усилителя"

# Журнал проектных решений (краткий, детали — в decisions/)
decisions:
  - id: D001
    date: 2026-05-16
    summary: "6П14П в триодном включении"
    rationale: "Меньшие искажения, достаточная мощность для наушников"
    evidence: sim/comparisons/triode_vs_pentode.json
    session: sessions/session_002.json

  - id: D002
    date: 2026-05-18
    summary: "C2 увеличен до 1мкФ"
    rationale: "Расширение НЧ-полосы с 28 Гц до 18 Гц"
    evidence: sim/ac_final.json

  - id: D003
    date: 2026-05-19
    summary: "Заземление — топология 'звезда'"
    rationale: "Минимизация петель тока, снижение фона"

# Ссылки на сессии
sessions:
  last: sessions/session_005.json
  count: 5
```

### 4.4. Журнал проектных решений (Design Decision Record)

Каждое значимое решение фиксируется в `decisions/` как Markdown-файл:

```markdown
# D002: Увеличение C2 до 1мкФ

**Дата:** 2026-05-18
**Статус:** Принято
**Сессия:** session_003

## Контекст
АЧХ показала спад -3дБ на 28 Гц. Целевая нижняя граница — 20 Гц.

## Варианты
1. Увеличить C2 с 0.1мкФ до 0.47мкФ → НЧ-граница ~22 Гц
2. Увеличить C2 до 1мкФ → НЧ-граница ~18 Гц ✓
3. Изменить Rg → влияет на смещение, нежелательно

## Решение
Вариант 2: C2 = 1мкФ. Запас по полосе, минимальное влияние на остальную схему.

## Подтверждение
Симуляция: `sim/ac_final.json` — полоса 18 Гц – 38.2 кГц.
Sweep: `sim/comparisons/c2_sweep.json`
```

Решения создаются автоматически, когда LLM фиксирует изменение номинала или топологии с обоснованием. Пользователь может дополнить вручную.

### 4.5. Привязка сессий к проекту

Каждая сессия чата привязана к проекту и хранит:
- Полный контекст разговора (сообщения + tool calls)
- Какие файлы были изменены в этой сессии
- Какие решения были приняты
- Какой LLM-бэкенд использовался
- Git commit hashes для каждого изменения

**Индекс сессий (`sessions/session_index.json`):**

```json
{
  "sessions": [
    {
      "id": "session_001",
      "date": "2026-05-15T14:30:00",
      "backend": "claude-max",
      "summary": "Создание начальной схемы, выбор топологии SE",
      "decisions": ["D001"],
      "files_changed": ["schematic/SE-6P14P.kicad_sch"],
      "commits": ["a1b2c3d"]
    },
    {
      "id": "session_003",
      "date": "2026-05-18T10:15:00",
      "backend": "claude-max",
      "summary": "Оптимизация АЧХ: C2, sweep Rk, финальный AC-анализ",
      "decisions": ["D002"],
      "files_changed": ["schematic/SE-6P14P.kicad_sch", "sim/ac_final.json"],
      "commits": ["d4e5f6a", "b7c8d9e"]
    }
  ]
}
```

### 4.6. Команды управления проектом

```
/project new <name> [--type analog_audio] [--assembly pcb] [--phases all|phase1,phase2,...]
                          создать проект; --phases задаёт скоуп (по умолчанию all)

/project open <name>      открыть проект (загрузить контекст, подключить модели)

/project status           показать текущее состояние: фазы, ТТХ, последние решения

/project add-phase <phase>  добавить фазу в проект (если решили, что нужна)

/project skip-phase <phase> пометить фазу как ненужную

/project import-artifact <path>  импортировать существующий файл (.kicad_sch, .kicad_pcb, .FCStd)

/project decisions        показать журнал решений

/project history          показать индекс сессий: когда, что делали, какие решения

/project resume           продолжить последнюю сессию (загрузить summary контекста)

/project archive          заархивировать проект (zip с полной историей)

/project import <path>    импортировать проект из архива или папки

/project compare <a> <b>  сравнить два проекта или две ревизии одного
```

### 4.7. Автоматические действия

При каждом значимом событии система автоматически:

| Событие | Действие |
|---------|----------|
| Создание проекта | git init, генерация project.yaml, создание структуры папок |
| Изменение схемы | git commit, обновление project.yaml (updated, revision) |
| Завершение симуляции | Обновление specifications в project.yaml, сохранение summary |
| Принятие решения | Создание DDR-файла в decisions/, обновление project.yaml |
| Переход на новую фазу | Обновление phases в project.yaml |
| Завершение сессии | Сохранение сессии, обновление session_index.json |
| Экспорт production-package | Обновление status → production_ready |

### 4.8. Портативность

Проект — полностью самодостаточен. Для переноса на другую машину:

```bash
# На исходной машине
/project archive "SE-6P14P"
# → ~/kicad-workspace/archives/SE-6P14P_2026-05-20_revB.zip

# На целевой машине
/project import SE-6P14P_2026-05-20_revB.zip
# → воссоздаёт структуру, проверяет зависимости (модели, инструменты)
```

Локальные SPICE-модели хранятся в проекте (`models/`), глобальные — по ссылкам из project.yaml. При импорте на другую машину система проверяет наличие глобальных моделей и предлагает установить недостающие.

---

## 5. Универсальный чат-клиент (kicad-sim-chat)

### 4.1. Бэкенды LLM

#### Claude Code Max (без API)

Взаимодействие через subprocess к CLI `claude`:

```
claude -p "prompt" --output-format json --model claude-sonnet-4-20250514
```

- Флаг `-p` — неинтерактивный режим, один запрос → один ответ
- `--output-format json` — структурированный вывод с tool_use блоками
- `--allowedTools` — передача списка доступных MCP-инструментов
- Ограничения: latency выше из-за subprocess, нет streaming
- Преимущество: бесплатно по подписке Max, доступ к лучшим моделям

#### Anthropic API

Прямой вызов через `anthropic` Python SDK:

```python
client = anthropic.Anthropic(api_key=...)
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    tools=mcp_tools_as_anthropic_format,
    messages=conversation_history
)
```

Tool use через нативный Anthropic tool_use формат. Поддержка streaming.

#### OpenAI-совместимые API

Через `openai` Python SDK с кастомным base_url:

```python
client = openai.OpenAI(api_key=..., base_url="https://api.openai.com/v1")
```

Покрывает: GPT-4o, GPT-4-turbo, o1/o3, Mistral, DeepSeek, Groq, Together AI, любой OpenAI-совместимый эндпоинт. Tool use через OpenAI function calling — требуется конвертация MCP tools ↔ OpenAI functions.

#### Ollama (локальные модели)

Через OpenAI-совместимый интерфейс Ollama:

```python
client = openai.OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
```

Покрывает: Llama, Qwen, Mistral, DeepSeek, любая модель из каталога Ollama. Для моделей без function calling — fallback на prompt injection (описание инструментов в system prompt + парсинг ответа).

### 4.2. MCP-клиент

#### Подключение к серверам

Клиент при запуске поднимает все MCP-серверы как subprocess (stdio-транспорт) согласно конфигурации. Инициализация MCP handshake, получение списка доступных инструментов от каждого сервера.

#### Единый реестр инструментов

Все инструменты из всех MCP-серверов собираются в один реестр с пространствами имён:

```
sch.create_schematic      → mcp-kicad-sch-api
sch.add_component         → mcp-kicad-sch-api
project.set_project       → kicad-mcp-pro
project.quality_gate      → kicad-mcp-pro
pcb.sync_from_schematic   → kicad-mcp-pro
pcb.place_components      → kicad-mcp-pro
pcb.export_gerbers        → kicad-mcp-pro
validation.run_erc        → kicad-mcp-pro
validation.run_drc        → kicad-mcp-pro
sim.run                   → spicebridge
sim.measure               → spicebridge
bridge.design_to_sim      → kicad-sim-bridge
bridge.model_library      → kicad-sim-bridge
```

#### Tool use loop

Универсальный цикл, одинаковый для всех бэкендов:

```
1. Отправить сообщение + список инструментов → LLM
2. Получить ответ
3. Если ответ содержит tool_use:
   a. Определить, какому MCP-серверу принадлежит инструмент
   b. Вызвать инструмент через MCP-протокол
   c. Получить результат
   d. Добавить tool_result в контекст
   e. Вернуться к шагу 1
4. Если ответ — текст: показать пользователю
```

#### Конвертация форматов

Адаптеры для конвертации между форматами:

- **MCP → Anthropic:** почти 1:1, JSON Schema совместимы
- **MCP → OpenAI:** конвертация в function calling формат
- **MCP → Prompt injection:** для моделей без function calling — генерация system prompt с описанием инструментов + парсер tool calls из текстового ответа

### 4.3. Интерфейс пользователя

#### Терминальный UI

На базе библиотеки Rich — форматированный вывод, подсветка кода, таблицы, прогресс-бары. Без тяжёлых зависимостей, работает в любом терминале.

#### Команды

```
/model <name>          переключить LLM-бэкенд
/model                 показать текущий и доступные бэкенды
/tools                 список всех MCP-инструментов
/tools <prefix>        фильтр по пространству имён (sim.*, sch.*)
/project <name>        установить активный KiCad-проект
/history               показать историю сессии
/save <file>           сохранить сессию (контекст + результаты)
/load <file>           загрузить сессию
/compare               отправить запрос на другую модель, сравнить ответы
/clear                 очистить контекст
/config                показать/изменить настройки
/cost                  показать расход токенов/денег за сессию
/exit                  выход
```

#### Индикация

```
[claude-max] >>>       промпт с именем текущего бэкенда
⚡ sim.run(...)        вызов MCP-инструмента (в реальном времени)
✓ sim.run → 1.2s       результат инструмента
📊 [график]            ASCII-график (через plotext)
⚠ ngspice warning     предупреждения из симулятора
```

#### Режим сравнения моделей

Команда `/compare` отправляет тот же запрос (с тем же контекстом и инструментами) на другую модель и показывает оба ответа рядом. Полезно для проверки рекомендаций.

### 4.4. Управление сессиями

#### Контекст

Полный контекст разговора: все сообщения, tool calls и results, метаданные (модель, время, токены). При переключении модели контекст конвертируется в формат нового бэкенда.

#### Сохранение / загрузка

Сессия сохраняется как JSON:

```json
{
  "session_id": "...",
  "created": "2026-05-12T...",
  "project": "my-amp",
  "messages": [...],
  "tool_calls": [...],
  "sim_results": {
    "last_ac": {"file": "sim/results_ac.raw", "measures": {...}},
    "last_tran": {"file": "sim/results_tran.raw", "measures": {...}}
  },
  "model_switches": [
    {"at": 12, "from": "claude-max", "to": "gpt-4o"}
  ]
}
```

При загрузке — контекст восстанавливается, MCP-серверы переподключаются, активный проект открывается.

#### Привязка к проекту

Каждая сессия привязана к KiCad-проекту. Результаты симуляций сохраняются в папке проекта. При загрузке сессии клиент проверяет целостность (hash .kicad_sch).

### 4.5. System prompt

Единый system prompt для всех бэкендов, содержащий:
- Описание роли (инженер-электронщик)
- Инструкции по работе с MCP-инструментами
- Контекст активного проекта (компоненты, последние результаты)
- Специфика предметной области (ламповая схемотехника, если применимо)

Генерируется динамически на основе текущего состояния проекта.

---

## 6. Конфигурация

### 5.1. MCP-серверы: ~/.config/kicad-sim-bridge/config.toml

```toml
[workspace]
root = "~/kicad-workspace"
projects = "~/kicad-workspace/projects"
models = "~/kicad-workspace/models"

[kicad]
version = ""          # автоопределение
cli_path = ""         # автоопределение из PATH

[ngspice]
mode = "spicebridge"  # "spicebridge" | "pyspice" | "batch"
timeout = 300

[mcp_servers]
kicad_sch_api = ""
kicad_mcp_server = ""
spicebridge = ""
```

### 5.2. LLM-бэкенды: ~/.config/kicad-sim-chat/backends.toml

```toml
[backends.claude-max]
type = "claude-code"
command = "claude"
default_model = "claude-sonnet-4-20250514"
enabled = true
default = true

[backends.claude-api]
type = "anthropic"
api_key_env = "ANTHROPIC_API_KEY"
default_model = "claude-sonnet-4-20250514"
enabled = false

[backends.gpt4]
type = "openai"
api_key_env = "OPENAI_API_KEY"
base_url = "https://api.openai.com/v1"
default_model = "gpt-4o"
enabled = false

[backends.deepseek]
type = "openai"
api_key_env = "DEEPSEEK_API_KEY"
base_url = "https://api.deepseek.com/v1"
default_model = "deepseek-chat"
enabled = false

[backends.ollama]
type = "openai"
api_key = "ollama"
base_url = "http://localhost:11434/v1"
default_model = "qwen2.5:32b"
tool_mode = "prompt_injection"
enabled = false

[backends.groq]
type = "openai"
api_key_env = "GROQ_API_KEY"
base_url = "https://api.groq.com/openai/v1"
default_model = "llama-3.3-70b-versatile"
enabled = false
```

### 5.3. Конфигурация Claude Desktop / Claude Code

Генерируется автоматически скриптом bootstrap.sh для тех, кто хочет использовать MCP-серверы напрямую из Claude Desktop/Code без нашего чат-клиента:

```json
{
  "mcpServers": {
    "kicad-sch": {
      "command": "uv",
      "args": ["run", "kicad-sch-mcp"],
      "env": {"KICAD_SYMBOL_DIR": "/usr/share/kicad/symbols"}
    },
    "kicad-pro": {
      "command": "uvx",
      "args": ["kicad-mcp-pro"],
      "env": {"KICAD_MCP_PROFILE": "agent_full"}
    },
    "spicebridge": {
      "command": "python",
      "args": ["-m", "spicebridge"]
    },
    "kicad-sim-bridge": {
      "command": "python",
      "args": ["-m", "kicad_sim_bridge"]
    }
  }
}
```

---

## 7. Пайплайн моделирования

```
.kicad_sch
    │
    ▼ kicad-cli sch export netlist --format spice
netlist.cir (базовый, из KiCad)
    │
    ▼ inject()
netlist_sim.cir
    │  Добавлены:
    │  • .include <путь к модели> для каждого компонента с SPICE-моделью
    │  • .control ... .endc блок с командами анализа
    │  • .options (RELTOL, ITL1, ITL2, GMIN, ...)
    │  • .measure директивы
    │
    ▼ ngspice (через SPICEBridge или PySpice shared lib)
results.raw + simulation.log
    │
    ▼ parse()
    │
JSON-результат:
{
  "status": "ok",
  "analysis": "ac",
  "nodes": {
    "v(out)": {"freq": [...], "magnitude": [...], "phase": [...]},
    "v(in)":  {"freq": [...], "magnitude": [...], "phase": [...]}
  },
  "measures": {
    "gain_1k": {"value": 12.3, "unit": "dB"},
    "bw_3db": {"value": 38200, "unit": "Hz"}
  },
  "op_point": {
    "V1_plate": 180.2,
    "V1_cathode": 1.8
  },
  "log": "... ngspice output ..."
}
```

---

## 8. Сценарии использования

### 7.1. Создание ламповой схемы с нуля

Пользователь просит создать схему однотактного усилителя на 6П14П в триодном включении с драйвером на 6Н2П. LLM через mcp-kicad-sch-api создаёт схематик, добавляет компоненты и проводники, через kicad-sim-bridge назначает SPICE-модели из библиотеки, рендерит SVG для визуального контроля.

### 7.2. Моделирование и оптимизация

Пользователь просит AC-анализ. LLM через bridge_design_to_sim экспортирует нетлист, инжектирует модели, запускает ngspice, получает АЧХ, строит ASCII-график в терминале. Предлагает оптимизацию, по согласию — bridge_edit_and_resim меняет номинал, пересимулирует, показывает сравнение.

### 7.3. Параметрический sweep

Пользователь спрашивает, как катодный резистор влияет на усиление. LLM через bridge_sweep прогоняет серию симуляций, строит график зависимости, находит оптимум.

### 7.4. Работа с существующей схемой из KiCad GUI

Пользователь рисует схему в KiCad GUI, указывает путь к проекту. LLM через kicad-mcp-server анализирует, через bridge запускает моделирование.

### 7.5. Сравнение рекомендаций разных моделей

Пользователь получает рекомендацию от Claude (увеличить R3 до 33к). Вводит `/compare gpt4` — тот же контекст отправляется GPT-4o. Оба ответа показываются рядом для сравнения.

### 7.6. SMPS: flyback-преобразователь

```
User: "Спроектируй flyback 12В/2А от 220В, частота 100 кГц"

LLM:
  → psu_wizard(topology="flyback", vin="220AC", vout=12, iout=2, fsw="100k")
  → [генерирует схему: EMI-фильтр, мост, flyback контроллер, трансформатор, выход]
  → mag_design_transformer(topology="flyback", ...)
  → [рассчитывает ферритовый трансформатор: EE25, N87, зазор 0.3мм]
  → bridge_design_to_sim(..., analysis="tran")
  → [проверка: пульсации, переходный процесс, КПД]
  → pcb_from_schematic(..., rules={track_min:"0.3mm", copper:"2oz"})
  → pcb_emi_check(...)  # проверка петель тока, фильтрация
```

### 7.7. Цифровой проект: плата на микроконтроллере

```
User: "Плата на STM32F4: USB, SPI-дисплей, 3 АЦП-канала, питание от USB-C"

LLM:
  → [создаёт схему: STM32, USB-C + ESD, LDO 3.3В, разъём дисплея,
     входные фильтры АЦП, блокировочные конденсаторы, кварц]
  → bridge_design_to_sim(..., analysis="ac")  # проверка фильтров АЦП
  → pcb_from_schematic(..., layers=4,
        rules={impedance_control:true, usb_diff_pair:"90ohm"})
  → pcb_emi_check(...)  # clock routing, разделение земель, блокировка
  → pcb_export_manufacturing("stm32-board", format="jlcpcb")
```

---

## 9. Развёртывание

### 8.1. Быстрый старт

**Linux:**
```bash
curl -fsSL https://<repo>/bootstrap.sh | bash
```

**Windows (PowerShell с правами администратора):**
```powershell
irm https://<repo>/bootstrap.ps1 | iex
```

**Что делает:**

1. Определяет дистрибутив Linux (apt / dnf / pacman)
2. Устанавливает системные пакеты:
   - KiCad 10 (с kicad-cli)
   - ngspice (с libngspice-dev для shared library)
   - Python 3.11+, uv, git
3. Создаёт venv и устанавливает Python-пакеты:
   - `kicad-sch-api`, `mcp-kicad-sch-api`
   - `kicad-mcp-pro`
   - `spicebridge`
   - `PySpice`
   - `kicad-sim-bridge` (оркестратор)
   - `kicad-sim-chat` (чат-клиент)
   - `anthropic`, `openai` (опционально)
   - `rich`, `plotext`, `mcp`, `click`, `tomli`
4. Создаёт структуру рабочей области
5. Скачивает и конвертирует библиотеки SPICE-моделей:
   - Koren tube collection (конвертация `^` → `**` для ngspice)
   - Ayumi models (конвертация)
   - Duncan's Amp Pages models
   - Генерация index.json
6. Копирует шаблоны KiCad-проектов
7. Генерирует конфигурацию: backends.toml, config.toml, Claude Desktop JSON
8. Запускает smoke-тест (создание схемы → симуляция → проверка)

**Время:** ~5 минут (без учёта скачивания KiCad)

### 8.2. Переезд на новую машину

```bash
git clone <repo>
cd kicad-sim-bridge
./bootstrap.sh
```

### 8.3. Docker (альтернативный способ развёртывания)

Для максимальной воспроизводимости и кроссплатформенности:

```bash
docker compose up -d    # поднять все MCP-серверы + ngspice + FEMM
kicad-sim-chat --mcp-host localhost:8765   # клиент подключается по SSE
```

Docker-compose включает: ngspice, FEMM, FreeRouting, все Python MCP-серверы. KiCad и FreeCAD остаются на хосте (нужен GUI). Клиент подключается к MCP-серверам по SSE вместо stdio.

Преимущества: одинаковое окружение на Linux и Windows, нет конфликтов зависимостей, простое обновление (`docker compose pull`). Недостаток: дополнительный слой, latency SSE vs stdio.

### 8.4. Конфигурация: структура файлов

Три конфигурационных файла, каждый для своей цели:

| Файл | Назначение | Когда используется |
|------|-----------|-------------------|
| `config.toml` | Рабочая область, пути, параметры ngspice | Всегда (bridge) |
| `backends.toml` | LLM-бэкенды, API-ключи, модели | Только чат-клиент |
| `claude_desktop.json` | Регистрация MCP-серверов в Claude Desktop | Только при работе через Claude Desktop вместо нашего клиента |

`config.toml` и `backends.toml` генерируются bootstrap-скриптом. `claude_desktop.json` — опциональный, для тех, кто предпочитает Claude Desktop нашему чат-клиенту.

### 8.5. Структура репозитория

```
kicad-sim-system/
├── bootstrap.sh              # Linux installer
├── bootstrap.ps1             # Windows installer (PowerShell)
├── pyproject.toml
│
├── src/
│   ├── kicad_sim_bridge/         # оркестрационный MCP-сервер
│   │   ├── __main__.py
│   │   ├── server.py             # FastMCP: bridge-инструменты
│   │   ├── pipeline.py           # design→netlist→sim→results
│   │   ├── models_manager.py     # управление библиотекой моделей
│   │   ├── pcb_bridge.py         # PCB: footprints→placement→routing→export
│   │   ├── p2p_bridge.py         # навесной монтаж: wiring diagrams
│   │   ├── mag_bridge.py         # намоточные изделия
│   │   ├── enclosure_bridge.py   # корпуса: FreeCAD интеграция
│   │   ├── safety.py             # чеклисты безопасности, EMI-аудит
│   │   ├── psu_wizard.py         # wizard блока питания
│   │   ├── measurement.py        # импорт измерений, сравнение с симуляцией
│   │   ├── export_production.py  # формирование производственного пакета
│   │   ├── app_manager.py        # управление внешними приложениями (KiCad, FreeCAD)
│   │   ├── platform_layer.py     # кроссплатформенная абстракция (Linux/Windows)
│   │   ├── freerouting.py        # обёртка FreeRouting CLI
│   │   └── config.py
│   │
│   └── kicad_sim_chat/           # универсальный чат-клиент
│       ├── __main__.py           # точка входа
│       ├── app.py                # главный цикл
│       ├── ui/
│       │   ├── terminal.py       # Rich-based UI
│       │   ├── commands.py       # парсер /команд
│       │   └── display.py        # форматирование, графики
│       ├── backends/
│       │   ├── base.py           # абстрактный класс Backend
│       │   ├── claude_code.py    # Claude Code Max (subprocess)
│       │   ├── anthropic_api.py  # Anthropic SDK
│       │   ├── openai_compat.py  # OpenAI-совместимые API
│       │   └── prompt_inject.py  # fallback без tool use
│       ├── mcp/
│       │   ├── client.py         # MCP-клиент
│       │   ├── registry.py       # реестр инструментов
│       │   └── adapters.py       # MCP ↔ Anthropic ↔ OpenAI
│       ├── session/
│       │   ├── context.py        # управление контекстом
│       │   ├── converter.py      # конвертация между форматами
│       │   └── storage.py        # сохранение/загрузка сессий
│       └── config.py
│
├── models/                       # встроенные SPICE-модели
│   ├── tubes/
│   │   ├── koren/
│   │   ├── ayumi/
│   │   └── duncan/
│   ├── convert_models.py         # конвертация PSpice → ngspice
│   └── build_index.py            # генерация index.json
│
├── templates/                    # шаблоны KiCad-проектов
│   ├── tube-amp-se/
│   ├── tube-amp-pp/
│   └── opamp-basic/
│
├── tests/
│   ├── test_pipeline.py
│   ├── test_models.py
│   ├── test_backends.py
│   ├── test_mcp_client.py
│   └── fixtures/
│
└── docs/
    ├── INSTALL.md
    ├── USAGE.md
    ├── BACKENDS.md
    └── ADDING_MODELS.md
```

---

## 10. Обработка ошибок

| Ситуация | Поведение |
|----------|-----------|
| KiCad / ngspice не установлены | bootstrap.sh подсказывает; bridge проверяет при старте |
| Симуляция не сходится | Возврат лога, предложение: увеличить RELTOL, уменьшить шаг |
| Таймаут симуляции | Остановка, частичные результаты если есть |
| SPICE-модель не найдена | Поиск в библиотеке, предложение скачать |
| Pin mapping несовпадение | Показ распиновок символа и модели, предложение маппинга |
| Ошибка в .kicad_sch после правки | Бэкап перед каждой модификацией, автооткат |
| LLM-бэкенд недоступен | Сообщение + предложение переключиться (/model) |
| API rate limit | Автоповтор с backoff, уведомление пользователя |
| Модель не поддерживает tool use | Автопереключение на prompt injection |
| Конфликт версий KiCad | Проверка совместимости при bootstrap |

---

## 11. Операционные аспекты

### 10.1. Управление контекстным окном LLM

**Проблема:** один AC-анализ может вернуть тысячи точек, transient — десятки тысяч. Несколько итераций моделирования забьют контекстное окно любой LLM.

**Стратегия:**

Результаты симуляций никогда не передаются в контекст LLM целиком. Пайплайн bridge возвращает двухуровневый ответ:

**Уровень 1 — Summary (всегда в контексте):**
```json
{
  "status": "ok",
  "analysis": "ac",
  "summary": {
    "gain_1k": {"value": 12.3, "unit": "dB"},
    "bw_3db_low": {"value": 28, "unit": "Hz"},
    "bw_3db_high": {"value": 38200, "unit": "Hz"},
    "phase_margin": {"value": 45, "unit": "deg"},
    "thd_1k": {"value": 0.8, "unit": "%"}
  },
  "warnings": ["V1 plate voltage close to supply rail"],
  "data_ref": "sim/results_ac_20260515_143022.json"
}
```

**Уровень 2 — Full data (на диске, подгружается по запросу):**
Полные осциллограммы в JSON/CSV хранятся в `sim/` папке проекта. LLM запрашивает конкретный узел/диапазон через инструмент `bridge_get_waveform(node, freq_range)` — возвращается только нужный срез.

**Правила:**
- Summary ≤ 500 токенов на один результат симуляции
- При параметрическом sweep — таблица «параметр → ключевые метрики», не массивы
- График строится на стороне клиента (plotext/sixel), LLM получает только описание
- История симуляций: хранить последние 3 результата в summary, остальные — только ссылки

**Суммаризация истории разговора:**

При приближении к лимиту контекстного окна (≥70% заполнения) клиент автоматически:
1. Суммаризирует старую часть разговора через LLM-вызов: «Вот история, сожми до ключевых решений и текущего состояния»
2. Заменяет старые сообщения на summary-блок
3. Сохраняет полную историю в файл сессии (для восстановления при необходимости)
4. Уведомляет пользователя: «Контекст сжат, полная история сохранена в sessions/»

Это прозрачно для пользователя — разговор продолжается без потери ключевых решений.

### 10.2. Автоматическое управление внешними приложениями

**Принцип:** пользователь не должен вручную открывать/закрывать KiCad, FreeCAD или другие инструменты. Система делает это самостоятельно.

**Менеджер процессов (`app_manager`):**

Центральный модуль, управляющий жизненным циклом внешних приложений:

```python
app_manager.ensure_closed("kicad")    # закрыть KiCad если открыт
app_manager.open_project("kicad", "~/kicad-workspace/projects/my-amp")
app_manager.is_running("freecad")     # проверить статус
app_manager.restart("kicad")          # закрыть и открыть заново
```

**Платформозависимая реализация:**

| Операция | Linux | Windows |
|----------|-------|---------|
| Проверка запущен ли | `pgrep kicad` / `/proc` | `tasklist /FI "IMAGENAME eq kicad.exe"` |
| Мягкое закрытие | `SIGTERM` → ожидание → `SIGKILL` | `WM_CLOSE` через `ctypes`/`pywin32` → `taskkill` |
| Открытие проекта | `subprocess.Popen(["kicad", project])` | `subprocess.Popen(["kicad.exe", project])` |
| Файловые блокировки | `.~lock.*` файлы | Windows file locking API |
| Путь к исполняемому | `which kicad` / `shutil.which` | Реестр + `shutil.which` + `%PATH%` |

**Сценарий: модификация схемы с автоматическим перезапуском KiCad:**

```
1. bridge получает запрос на изменение номинала R3
2. app_manager.is_running("kicad") → True
3. app_manager.has_unsaved_changes("kicad")  # проверка по заголовку окна или backup-файлу
4. Если есть несохранённые → app_manager.save("kicad")  # Ctrl+S через xdotool/pyautogui
5. app_manager.save_state("kicad")         # запомнить открытый файл, позицию вида
6. app_manager.ensure_closed("kicad")      # мягкое закрытие
7. Подождать освобождения lock-файла (≤5 сек)
8. Модифицировать .kicad_sch
9. app_manager.open_project("kicad", project)  # переоткрыть
10. Пользователь видит обновлённую схему
```

**Для FreeCAD:**
freecad-mcp работает через RPC к запущенному FreeCAD — закрытие не требуется, модификации идут через API. Если FreeCAD не запущен, app_manager запускает его автоматически.

**Для ngspice / FEMM:**
Работают в batch-режиме или через shared library — управление процессами не требуется, запуск и остановка автоматические.

**Fallback при ошибках:**
- Если KiCad не удалось закрыть за 10 сек → уведомить пользователя с просьбой закрыть вручную
- Если lock-файл не исчезает → staged-модификация (как описано в v4)

### 10.3. Кроссплатформенность (Linux + Windows)

**Принцип:** вся кодовая база — Python, платформозависимый код изолирован в тонком слое абстракции. Все внешние инструменты (KiCad, FreeCAD, ngspice, FEMM) работают на обеих платформах.

**Слой абстракции (`platform_layer`):**

```python
from kicad_sim_bridge.platform import Platform

platform = Platform.detect()  # "linux" | "windows"

# Пути
platform.kicad_cli_path()       # /usr/bin/kicad-cli | C:\Program Files\KiCad\bin\kicad-cli.exe
platform.config_dir()           # ~/.config/kicad-sim-bridge | %APPDATA%\kicad-sim-bridge
platform.workspace_dir()        # ~/kicad-workspace | %USERPROFILE%\kicad-workspace

# Процессы
platform.find_process("kicad")  # pgrep | tasklist
platform.kill_process(pid)      # SIGTERM | WM_CLOSE
platform.open_file(path)        # xdg-open | os.startfile

# Файловая система
platform.is_locked(path)        # check .~lock.* | win32 lock check
```

**Развёртывание:**

| Аспект | Linux | Windows |
|--------|-------|---------|
| Bootstrap | `bootstrap.sh` (bash) | `bootstrap.ps1` (PowerShell) |
| Менеджер пакетов ОС | apt / dnf / pacman | winget / choco / scoop |
| Python | системный или pyenv | python.org installer или winget |
| KiCad | PPA / flatpak / пакет | MSI installer / winget |
| ngspice | apt / компиляция | prebuilt binary (ngspice.com) |
| FreeCAD | apt / flatpak | MSI installer / winget |
| FEMM | wine или нативный (если портирован) | нативный (.exe) |
| Java (FreeRouting) | apt install openjdk-17-jre | winget install Oracle.JDK.17 |
| Пути | POSIX (`/home/user/...`) | Windows (`C:\Users\...`) |
| Конфигурация MCP | `~/.claude.json` | `%APPDATA%\Claude\claude_desktop_config.json` |

**FEMM на Linux:**
FEMM — нативно Windows-приложение. На Linux работает через Wine, или можно использовать pyFEMM с headless FEMM через Xvfb. Альтернатива: FEMMT (Python FEM Magnetics Toolbox) — полностью кроссплатформенный.

**Файловые пути:**
Все пути внутри системы — через `pathlib.Path`, никогда не через строковую конкатенацию. Конфигурация хранит относительные пути от workspace root.

**CI/CD:**
Тесты запускаются на обеих платформах (GitHub Actions: ubuntu-latest + windows-latest).

### 10.4. Визуализация в терминальном клиенте

**Графики (осциллограммы, АЧХ, sweep):**
plotext — ASCII-графики. Работают в любом терминале на обеих платформах. Достаточно для 90% задач.

**Схемы и PCB:**
SVG нельзя отрендерить в терминале напрямую. Стратегия по платформам:

*Linux:*
1. Kitty graphics protocol / Sixel — если терминал поддерживает (kitty, WezTerm, foot), рендер SVG→PNG inline
2. `xdg-open` — открытие в браузере/просмотрщике
3. Путь к файлу — fallback

*Windows:*
1. Windows Terminal + Sixel (частичная поддержка) — если доступно
2. `os.startfile()` — открытие в системном просмотрщике (Edge/браузер для SVG)
3. Путь к файлу — fallback

Определение возможностей терминала — при старте клиента, с fallback на самый простой вариант.

### 10.5. Управление контекстом разговора

Раздел 10.1 покрывает данные симуляций. Но сам разговор (сообщения, tool calls, результаты) тоже растёт и забивает контекстное окно LLM.

**Стратегия:**

- **Автосуммаризация:** когда история превышает 60% контекстного окна, старые сообщения сворачиваются в summary. LLM генерирует резюме: «Спроектировали SE-усилитель на 6П14П, провели 3 итерации AC-анализа, полоса расширена до 20 Гц, текущее состояние: оптимизация R3.»
- **Сохранение ключевых точек:** результаты симуляций (summary), принятые решения и их обоснования сохраняются даже при сворачивании
- **Ручной контроль:** команда `/compact` — принудительная суммаризация, `/context` — показать текущее использование контекста
- **Привязка к проекту:** при переключении проекта (`/project`) контекст предыдущего проекта автоматически сохраняется и выгружается

### 10.6. Моделирование трансформаторов

Выходной трансформатор — ключевой компонент лампового усилителя и самый сложный для SPICE. Идеальные связанные индуктивности дают нереалистичную АЧХ.

**Модель трансформатора в библиотеке:**

```
.subckt OPT_GENERIC pri_h pri_ct pri_l sec_h sec_l
+ params: Lp=20H Rp=100 Ls=0.32H Rs=0.5
+         Llk=30mH Cw=500p Rc=100k turns_ratio=25
*
* Lp — индуктивность первичной обмотки (определяет НЧ-спад)
* Llk — индуктивность рассеяния (определяет ВЧ-спад)
* Cw — межобмоточная ёмкость (резонанс на ВЧ)
* Rc — потери в сердечнике (демпфирование)
* Rp, Rs — активное сопротивление обмоток
*
* ... реализация через связанные индуктивности + паразиты ...
.ends
```

Библиотека включает параметризованные модели:
- `OPT_GENERIC` — настраиваемая модель с паразитами
- `OPT_SE_5K` — типичный SE-трансформатор 5кОм первичка
- `OPT_PP_6K6` — типичный PP-трансформатор 6.6кОм a-a
- `OPT_OTL_HEADPHONE` — модель импеданса наушников для OTL
- `SPEAKER_8OHM` — модель динамика с реактивной составляющей

Для проекта «Иона» (OTL без трансформатора) — модель импеданса нагрузки (наушники: номинальное сопротивление + индуктивность катушки + резонансы).

### 10.7. Workflow создания кастомных SPICE-моделей

Не для всех компонентов есть готовые SPICE-модели. Система поддерживает создание кастомных моделей для любых компонентов.

**Универсальный workflow:**

```
1. Поиск в библиотеке
   → bridge: model_search("<компонент>")
   → Найдена? → использовать
   → Не найдена? → шаг 2

2. Поиск аналога
   → LLM ищет эквиваленты в существующих библиотеках
   → Найден? → проверить параметры по даташиту, адаптировать
   → Не найден? → шаг 3

3. Создание модели из даташита
   → Пользователь загружает даташит (PDF) или ВАХ (PNG)
   → Для ламп: Gleb Zaslavsky tool (извлечение параметров Koren)
   → Для транзисторов/ОУ: извлечение SPICE-параметров из даташита
   → Для SMPS-контроллеров: behavioral model на основе функциональной диаграммы
   → Или ручной ввод с помощью LLM

4. Валидация модели
   → Симуляция: DC sweep, AC, tran → сравнение с даташитом
   → Подстройка параметров при расхождении

5. Добавление в библиотеку
   → bridge: model_add("<name>", "<category>", content, metadata)
   → Метаданные: источник, дата, точность, ограничения
   → git commit
```

**Предустановленная библиотека моделей (Фаза 1):**

*Лампы (модель Корена):*
Западные: 12AX7, 12AU7, 12AT7, EL34, EL84, 6L6, 6V6, 6SN7, 300B, KT88
Российские: 6Н1П, 6Н2П, 6Н3П, 6Н8С, 6Н9С, 6Н23П, 6С33С, 6С19П, 6П1П, 6П14П, 6П36С, 6П45С, 6Ж9П

*Транзисторы / MOSFET:*
Базовые модели из SPICE-библиотек производителей (ON Semi, Infineon, TI) — импортируются при необходимости через model_import_url.

*Операционные усилители:*
Макромодели популярных ОУ (OPA1641, LM358, NE5532, TL072 и др.) — импортируются от производителей.

*Обобщённые модели:*
Generic OpAmp, Generic NPN/PNP, Generic N-MOSFET/P-MOSFET, Ideal Transformer, Ideal SMPS Buck/Boost.

### 10.8. Version control проектов

**Стратегия:** каждый проект KiCad — git-репозиторий.

**Автоматические действия:**
- `project_create` → `git init` + `.gitignore` (исключить .raw, .log, __pycache__, lock-файлы)
- Перед каждой программной модификацией → `git add -A && git commit -m "backup before <action>"`
- После успешной модификации → `git commit -m "<описание изменения>"`
- Результаты симуляций (.raw, .log) — в .gitignore, но JSON-summary коммитятся

**Команды чат-клиента:**
```
/history           показать git log текущего проекта
/diff              показать изменения с последнего коммита
/rollback [hash]   откатить к указанной версии
/tag <name>        пометить текущее состояние (например, "v1-working")
```

**Структура .gitignore:**
```
*.raw
*.log
sim/*.png
*.~lock.*
__pycache__/
.kicad_backup/
```

### 10.9. Логирование и отладка

**Единый лог:** `~/.local/log/kicad-sim/`

```
kicad-sim-chat.log       # действия клиента, переключения бэкендов
mcp-servers.log          # вызовы инструментов, параметры, результаты
ngspice.log              # вывод ngspice (последние N сессий)
errors.log               # только ошибки из всех компонентов
```

**Уровни:** DEBUG (разработка), INFO (нормальная работа), WARNING, ERROR.

**Ротация:** logrotate, хранить 7 дней, сжимать старые.

**Команда клиента:**
```
/debug on|off      включить подробный вывод в терминал
/log               показать последние 20 строк из errors.log
/log mcp           показать последние вызовы MCP-инструментов
```

**Диагностика при проблемах:**
- `kicad-sim-chat --doctor` — проверка всех компонентов: MCP-серверы стартуют? KiCad/ngspice в PATH? Модели на месте? Бэкенды доступны?
- Вывод в формате JSON для автоматического парсинга

### 10.10. System prompt

Динамический system prompt генерируется при каждом запросе на основе текущего состояния. Структура:

**Блок 1 — Роль (статический):**
```
Ты — инженер-электронщик широкого профиля, работающий в среде KiCad 10 + ngspice.
Владеешь аналоговой, цифровой и смешанной схемотехникой.

Ключевые знания:
- Аналоговая схемотехника: ОУ, транзисторные каскады, ламповые каскады,
  топологии усилителей, фильтры, стабилизаторы
- Цифровая схемотехника: микроконтроллеры, интерфейсы (SPI, I2C, UART, USB),
  развязка, целостность сигналов, согласование импедансов
- Источники питания: линейные (LDO, параллельные стабилизаторы), импульсные
  (buck, boost, flyback, forward), PFC, высоковольтные БП
- SPICE-моделирование: модели транзисторов/ОУ/ламп (вкл. модель Корена),
  конвергенция, выбор параметров .options, ограничения SPICE
- Помехозащита: топологии заземления (звезда, шина, сплошной полигон),
  экранировка сигнальных и ВЧ-цепей, развязка питания, подавление
  наводок, EMI от SMPS и цифровых схем, clock routing
- Электробезопасность: зазоры для ВН-цепей, разрядные резисторы,
  защитное заземление, предохранители, маркировка
- Проектирование PCB: многослойные платы, импедансный контроль,
  дифференциальные пары, тепловые зоны, земляные полигоны,
  высоковольтные зазоры
- Намоточные изделия: сердечники (ферриты, кремнистая сталь,
  нанокристаллические), расчёт обмоток, паразитные параметры, экраны
```

**Блок 2 — Доступные инструменты (генерируется из реестра MCP):**
```
Доступные инструменты:
- sch.*: создание и редактирование схем KiCad
- project.*: управление проектами, quality gates
- sim.*: запуск моделирования, измерения
- bridge.*: пайплайн схема→симуляция, библиотека моделей
- pcb.*: работа с PCB (если Фаза 4 активна)

Правила использования:
- Всегда сначала bridge.design_to_sim, а не прямой вызов sim.run
- После модификации номинала — автоматически пересимулировать
- Результат симуляции — показать summary, построить график, предложить оптимизацию
```

**Блок 3 — Контекст проекта (динамический):**
```
Активный проект: SE-6P14P
Компоненты: V1 (6Н2П, драйвер), V2 (6П14П, триодное, выходная), ...
Последняя симуляция: AC, gain=12.3dB@1kHz, BW=28Hz-38.2kHz
Открытые задачи: расширить полосу на НЧ (целевая: 20 Гц)
```

**Блок 4 — Пользовательские предпочтения (из config):**
```
Язык: русский
Единицы: метрические, резисторы в кОм/МОм
Стиль схем: IEC (прямоугольные резисторы)
Предпочтительные лампы: российские (6Н2П, 6П14П, 6С33С)
```

System prompt обновляется автоматически при смене проекта, после каждой симуляции и при переключении бэкенда.

### 10.11. Стратегия обновлений

**Регулярные обновления:**
```bash
kicad-sim-chat --update        # обновить все Python-пакеты
kicad-sim-chat --update-models # обновить библиотеку моделей из репозитория
```

**Что обновляется:**
- Python-пакеты: `uv pip install --upgrade kicad-mcp-pro spicebridge kicad-sch-api ...`
- Библиотека моделей: `git pull` в каталоге models/ (если submodule/отдельный repo)
- bootstrap.sh: идемпотентный, можно перезапустить без потери данных

**Что не затрагивается при обновлении:**
- Конфигурация (`~/.config/kicad-sim-*`)
- Рабочая область (`~/kicad-workspace/`) — проекты, кастомные модели, сессии
- Пользовательские модели ламп

**Миграции при мажорных обновлениях KiCad:**
- KiCad 10 → 11: скрипт миграции конвертирует .kicad_sch/.kicad_pcb
- Проверка совместимости kicad-mcp-pro с новой версией KiCad при каждом запуске
- Предупреждение если версия kicad-mcp-pro устарела

**Версионирование:** файл `~/.config/kicad-sim-bridge/version.json` хранит версии всех компонентов. `--doctor` сравнивает с актуальными и сообщает о доступных обновлениях.

### 10.12. Интеграция с публикационным workflow

Для экспорта результатов работы в книгу, статьи, документацию.

**Инструменты:**

| Инструмент | Назначение |
|-----------|------------|
| `export_schematic_publication` | Экспорт схемы в SVG/PNG с настраиваемым стилем (размер шрифтов, толщина линий, DPI) для печати |
| `export_sim_report` | Сформировать отчёт о моделировании: схема + графики + таблица параметров + описание в Markdown |
| `export_comparison` | Сравнительная таблица/графики для нескольких вариантов схемы |

**Workflow:**
```
User: "Подготовь материал для главы о выходном каскаде: схема, 
       АЧХ, таблица рабочих точек, описание"

LLM:
  → render_schematic("SE-6P14P", style="publication", dpi=300)
  → bridge_design_to_sim(..., analysis="ac")
  → bridge_design_to_sim(..., analysis="op")
  → export_sim_report("SE-6P14P", format="markdown",
        include=["schematic", "ac_plot", "op_table", "description"],
        language="ru")
  → [создаёт .md файл с иллюстрациями]
```

Выходной формат — Markdown с встроенными SVG/PNG, пригодный для дальнейшей обработки (Pandoc → LaTeX → PDF или Hugo/Jekyll для web).

### 10.13. RF-дизайн (будущее расширение)

Для работы с HF QRP и аналогичными ВЧ-проектами требуется расширение инструментария:

**Что потребуется:**
- S-параметры: .s2p файлы, конвертация в SPICE-совместимые модели
- Smith chart: визуализация согласования (через Python-библиотеку `scikit-rf` или `pySmithPlot`)
- Модели линий передачи: microstrip, stripline, coax
- Модели ВЧ-компонентов: тороидальные катушки, ВЧ-трансформаторы, варикапы
- QUCS или openEMS — для full-wave EM-симуляции (выходит за рамки ngspice)
- NanoVNA интеграция: импорт измерений .s1p/.s2p для валидации моделей

**Реализация:** отдельный MCP-модуль `rf-tools` в будущем. ngspice поддерживает AC-анализ на радиочастотах, но для антенн и волноводов нужны другие инструменты.

---

## 12. Зависимости

### Системные
- KiCad 10 (kicad-cli)
- ngspice 42+ (libngspice-dev)
- FreeCAD 1.0+ (с Sheet Metal workbench)
- FEMM 4.2+ (конечно-элементный анализ магнитных полей)
- Python 3.11+
- Java 17+ JRE (для FreeRouting)
- FreeRouting JAR (freerouting-1.9.0.jar)
- git

### Python (обязательные)
```
kicad-sch-api          # создание схем
mcp-kicad-sch-api      # MCP-сервер для схем
kicad-mcp-pro          # проект, PCB, валидация, экспорт
spicebridge            # MCP-сервер для ngspice
PySpice                # Python↔ngspice
freecad-mcp            # MCP-сервер для FreeCAD
PyOpenMagnetics        # расчёт магнитных компонентов
pyFEMM                 # Python-обёртка для FEMM
rich                   # терминальный UI
mcp                    # MCP protocol library
plotext                # ASCII-графики
tomli                  # TOML-конфигурация
click                  # CLI
```

### Python (опциональные, по бэкендам)
```
anthropic              # для бэкенда anthropic-api
openai                 # для бэкендов openai-compat и ollama
```

Установка:
```bash
pip install kicad-sim-system                    # базовый (claude-code-max)
pip install kicad-sim-system[anthropic]         # + Anthropic API
pip install kicad-sim-system[openai]            # + OpenAI-совместимые
pip install kicad-sim-system[all]               # всё
```

---

## 13. Дорожная карта

**Фаза 1a (MVP-ядро, 3–4 недели):**
- bootstrap.sh + bootstrap.ps1 (обе платформы)
- kicad-sim-bridge: pipeline design→sim→results (только pipeline.py + models_manager.py)
- Библиотека моделей: Koren + Ayumi (конвертированные) + российские лампы + обобщённые
- Модели трансформаторов: OPT_GENERIC + SPEAKER_8OHM
- Базовые анализы: OP, tran, AC
- platform_layer.py, app_manager.py
- Логирование, git init при создании проекта

**Фаза 1b (чат-клиент, +2–3 недели):**
- kicad-sim-chat: терминальный UI, бэкенд claude-code-max
- MCP-клиент: подключение всех серверов, tool use loop
- Базовые команды (/model, /tools, /project, /save, /load)
- Управление контекстным окном: summary + conversation compaction
- System prompt: статические блоки + динамический контекст

**Фаза 2 (+2 недели):**
- Бэкенды: anthropic-api, openai-compat
- Конвертация контекста между форматами LLM
- /compare — режим сравнения моделей
- bridge_edit_and_resim с автосравнением
- Параметрический sweep
- Измерения: THD, gain, bandwidth, phase margin
- ASCII-графики результатов (plotext)
- Визуализация схем: Sixel/Kitty protocol + fallback на xdg-open
- Конкурентный доступ к файлам: staged-модификации при открытом KiCad
- Шаблоны проектов (SE amp, PP amp, preamp, filter)

**Фаза 3 (+2 недели):**
- Бэкенд: Ollama с prompt injection fallback
- Интеграция ERC/DRC (через kicad-mcp-pro quality gates)
- model_import_url: скачивание моделей от производителей
- Tube-curve-fitting: интеграция инструмента Gleb Zaslavsky
- Рендер схемы в SVG + визуальная проверка
- /cost трекинг расходов на API
- Автодополнение команд и имён компонентов
- Публикационный workflow: export_schematic_publication, export_sim_report
- Стратегия обновлений: `--update`, `--update-models`, `--doctor`

**Фаза 4: PCB-модуль (+3–4 недели):**

Полная интеграция PCB-дизайна в систему — от назначения footprints до получения готовых производственных файлов.

*4.1. Готовые компоненты для интеграции:*

Основной MCP-сервер для PCB — **kicad-mcp-pro**. Покрывает полный workflow: проект, схемы, PCB, валидация (DRC/ERC/DFM), FreeRouting, экспорт. Дополнительно — **pcbnew Python API** для тонких программных операций.

*4.2. Подключение PCB MCP-сервера:*

Добавление пятого MCP-сервера в систему:

```
Claude / kicad-sim-chat
   │
   ├── mcp-kicad-sch-api ........ схемы
   ├── kicad-mcp-server ......... анализ, ERC
   ├── spicebridge .............. симуляция
   ├── kicad-sim-bridge ......... оркестрация
   └── kicad-mcp-pro ............ PCB layout + производство
        (уже подключён в Фазах 1–3, профиль agent_full)
```

*4.3. Пайплайн: от схемы до производства:*

```
.kicad_sch (проверенная схема с SPICE-моделированием)
    │
    ▼ Назначение footprints
    │  LLM выбирает footprints для каждого компонента
    │  (по типу, корпусу, производственным требованиям)
    │  Для ламп: кастомные footprints под октальные/нональные панельки
    │
    ▼ Создание .kicad_pcb
    │  Импорт нетлиста из схемы
    │  Определение контура платы (размеры, крепёжные отверстия)
    │  Установка правил проектирования (clearance, track width, via)
    │
    ▼ Размещение компонентов
    │  LLM размещает компоненты программно через pcbnew API
    │  Стратегии: по функциональным группам, по тепловым зонам,
    │  по требованиям к длине дорожек
    │  Визуальная проверка: рендер PCB в SVG через kicad-cli
    │
    ▼ Трассировка
    │  Критические цепи: ручная трассировка через LLM
    │  (силовые дорожки, высокочастотные сигналы, дифф. пары)
    │  Остальное: автотрассировка через FreeRouting
    │  Экспорт .kicad_pcb → DSN → FreeRouting CLI → SES → импорт
    │
    ▼ Валидация
    │  DRC через kicad-cli pcb drc
    │  DFM — проверка технологичности (минимумы производителя)
    │  Визуальная инспекция: рендер всех слоёв в SVG
    │  3D-превью: экспорт STEP, рендер
    │
    ▼ Экспорт для производства
    │  Gerber (все слои) + файлы сверловки
    │  BOM (список компонентов с номиналами и footprints)
    │  Pick-and-place (координаты для автомонтажа)
    │  Для JLCPCB: поиск компонентов в каталоге LCSC,
    │  подбор аналогов, оценка стоимости
```

*4.4. Инструменты PCB bridge (наша разработка, ~300 строк):*

| Инструмент | Назначение |
|-----------|------------|
| `pcb_from_schematic` | Создать .kicad_pcb из .kicad_sch: импорт нетлиста, назначение footprints, установка контура и правил |
| `pcb_place_components` | Разместить компоненты по стратегии (группировка, тепловые зоны, минимизация длины дорожек) |
| `pcb_autoroute` | Запустить FreeRouting CLI, импортировать результат, показать статистику (completion rate, via count) |
| `pcb_manual_route` | Ручная трассировка критических цепей (силовые, ВЧ) через pcbnew API |
| `pcb_validate` | DRC + DFM + визуальная инспекция (рендер SVG всех слоёв) |
| `pcb_export_manufacturing` | Экспорт: Gerber + drill + BOM + pick-and-place + STEP |
| `pcb_render` | Рендер PCB в SVG (top, bottom, all layers) для визуального контроля |
| `pcb_jlcpcb_check` | Проверка совместимости с JLCPCB: поиск компонентов в LCSC, оценка стоимости платы |

*4.5. Примеры предметно-ориентированных правил:*

**Высоковольтные схемы (ламповые, ВН-БП):**
- Увеличенные зазоры (≥2.5мм для 400В+), усиленная изоляция
- Силовые дорожки: увеличенная ширина для токонесущих цепей
- Тепловые зоны: разнесение горячих компонентов и электролитов
- Кастомные footprints (ламповые панельки, ВН-разъёмы)

**Цифровые / микроконтроллерные:**
- Многослойный stackup: сигнал — земля — питание — сигнал
- Контролируемый импеданс для высокоскоростных интерфейсов
- Дифференциальные пары (USB, Ethernet, LVDS)
- Обязательные блокировочные конденсаторы у каждой ИС
- Размещение кварца максимально близко к МК

**SMPS:**
- Минимизация петли тока: входной конденсатор → ключ → трансформатор → диод → выходной конденсатор
- Земляные полигоны под силовыми компонентами
- Отдельные gate-drive дорожки с минимальной индуктивностью
- Тепловые via под силовыми MOSFET

**Аналоговое аудио:**
- Минимизация длины входных дорожек
- Guard ring вокруг высокоимпедансных входов
- Разделение аналоговой и цифровой земли

*4.6. Сценарии:*

```
User: "Сделай PCB для нашего усилителя на 6П14П. Плата 200x150мм,
       крепёж по углам, ламповые панельки сверху, трансформаторы — 
       отдельно на шасси"

LLM:
  → pcb_from_schematic("SE-6P14P", board_size=[200,150], 
        rules={clearance:"0.3mm", track_min:"0.25mm",
               hv_clearance:"2.5mm"})
  → pcb_place_components(..., strategy="tube_amp",
        constraints={tubes:"top", electrolytics:"away_from_tubes"})
  → pcb_render("SE-6P14P", view="top")
  → [показывает SVG, обсуждает размещение]
  → pcb_manual_route(..., nets=["B+", "HEATER", "GND"])
  → pcb_autoroute(..., exclude_nets=["B+", "HEATER"])
  → pcb_validate("SE-6P14P")
  → pcb_export_manufacturing("SE-6P14P", format="jlcpcb")
```

```
User: "Проверь, сколько будет стоить заказать эту плату на JLCPCB 
       с монтажом SMD-компонентов"

LLM:
  → pcb_jlcpcb_check("SE-6P14P")
  → [поиск каждого SMD-компонента в каталоге LCSC]
  → [оценка стоимости: плата + компоненты + монтаж]
  
LLM: "Плата (5 шт): ~$12. SMD-компоненты (резисторы, конденсаторы):
      ~$3 за комплект. Монтаж: ~$8. Итого ~$23 за 5 плат.
      THT-компоненты (панельки, электролиты, разъёмы) — ручной монтаж."
```

*4.7. Зависимости (дополнительные для Фазы 4):*

Системные:
- Java 17+ JRE (для FreeRouting)
- FreeRouting JAR (`/opt/freerouting.jar`)

Python: без дополнительных зависимостей (pcbnew API входит в KiCad)

bootstrap.sh обновляется: добавляется установка JRE и скачивание FreeRouting.

*4.8. Альтернативная ветка: навесной монтаж (point-to-point):*

Для классических ламповых конструкций, где PCB не используется.

Вместо Gerber-файлов система генерирует:
- **Монтажную схему (wiring diagram):** расположение компонентов на шасси/турретной плате с указанием точек пайки, соединений и длин проводников
- **Схему раскладки:** вид сверху на шасси с позициями ламповых панелек, лепестковых планок, турретов, опорных точек
- **Таблицу проводников:** от → до, тип провода (экранированный/неэкранированный, сечение), длина, цветовая маркировка
- **Порядок монтажа:** последовательность пайки для минимизации ошибок

Инструменты:

| Инструмент | Назначение |
|-----------|------------|
| `p2p_layout` | Генерация раскладки компонентов на шасси (SVG) |
| `p2p_wiring_table` | Таблица соединений с типами проводов и экранировкой |
| `p2p_wiring_diagram` | Монтажная схема с указанием трасс проводников |
| `p2p_assembly_order` | Рекомендуемый порядок монтажа |

Выбор между PCB и P2P — на этапе создания проекта:
```
/project create "SE-6P14P" --assembly p2p     # навесной монтаж
/project create "SE-6P14P" --assembly pcb     # печатная плата
```

*4.9. Многоплатные проекты:*

Устройство может состоять из нескольких плат и модулей:
- Основная плата (усилитель)
- Плата блока питания
- Плата фронтальной панели (индикация, регуляторы)
- Плата задней панели (разъёмы)

Система поддерживает:
- Несколько .kicad_sch / .kicad_pcb в одном проекте
- Межплатные соединения: таблица разъёмов с распиновками
- Спецификация кабелей и жгутов: разъём → разъём, тип кабеля, длина, экранировка
- Общий BOM по всем платам
- Общая 3D-сборка (все платы + корпус + кабели)

*4.10. Помехозащита и заземление на уровне PCB:*

Автоматические проверки и рекомендации, встроенные в пайплайн PCB:

**Схема заземления:**
- Анализ топологии земли: звезда / шина / гибрид
- Выделение земляных доменов: сигнальная земля, силовая земля, цифровая земля (если есть)
- Проверка: одна точка соединения доменов (star ground)
- Рекомендации по расположению точки заземления на шасси

**Экранировка сигнальных цепей:**
- Идентификация чувствительных цепей (вход, сигнал после первого каскада)
- Проверка: экранированные проводники для входных цепей
- Guard ring вокруг высокоимпедансных узлов (сетки входных ламп)
- Расстояние между сигнальными и силовыми дорожками

**Земляные полигоны:**
- Copper pour на неиспользуемых областях
- Проверка: нет «островков» земли (все полигоны связаны)
- Via stitching для связи земляных полигонов на разных слоях

**Развязка питания:**
- Проверка: блокировочные конденсаторы у каждого каскада
- Рекомендации по номиналам и типам (керамика для ВЧ, электролит для НЧ)
- RC/LC-фильтры в цепях анодного питания между каскадами

**Накальные цепи (ламповые схемы):**
- Проверка: скрутка или параллельная прокладка накальных проводников
- Подъём накала над землёй (AC hum reduction)
- Для DC-накала: минимизация петель тока

**Цифровые и смешанные схемы:**
- Разделение аналоговой и цифровой земли с одной точкой соединения
- Блокировочные конденсаторы у каждой цифровой ИС (100нФ керамика + 10мкФ тантал)
- Маршрутизация тактовых сигналов: минимальная длина, отсутствие stub'ов, согласование
- Контроль импеданса дифференциальных пар (USB, LVDS, Ethernet)
- Фильтрация на границе аналог/цифра
- EMI от SMPS: входной/выходной фильтр, snubber, оптимизация layout петли тока

**Общие правила:**
- Минимизация площади токовых петель (критично для EMI)
- Развязка каждого каскада/блока по питанию
- Расстояние между чувствительными и излучающими цепями

Инструмент `pcb_emi_check` — автоматический аудит по всем пунктам выше, возвращает список нарушений с приоритетами и рекомендациями.

*4.11. Электробезопасность:*

Автоматическая генерация чеклиста безопасности на основе анализа схемы:

**Обязательные проверки:**
- [ ] Разрядные резисторы на всех ёмкостях ВН-цепей (≤1 МОм, рассеиваемая мощность)
- [ ] Предохранитель в цепи первичной обмотки сетевого трансформатора
- [ ] Заземление шасси (клемма защитного заземления)
- [ ] Зазоры между токоведущими частями ≥ 2.5мм/кВ (по IEC 60065)
- [ ] Защитный кожух над высоковольтными элементами
- [ ] Маркировка «Опасное напряжение» на шасси
- [ ] Изоляция сетевых проводов внутри корпуса
- [ ] Кабельные стяжки / фиксация проводов (предотвращение замыкания при вибрации)
- [ ] Отсутствие опасного напряжения на доступных частях при снятом кожухе

**Генерируемые документы:**
- Чеклист безопасности (Markdown/PDF) — для самопроверки
- Список опасных цепей с напряжениями
- Карта зазоров (clearance map) на PCB / в корпусе

Инструмент `safety_checklist` — анализирует схему, находит ВН-цепи, проверяет наличие защитных элементов.

*4.12. Проектирование блока питания (wizard):*

Типовая задача для каждого лампового усилителя. Встроенный wizard:

```
User: "Спроектируй БП для SE-усилителя на 6П14П:
       анодное 280В/70мА, накал 6.3В/1.5А, смещение -12В"

LLM:
  → psu_wizard(topology="tube_amp",
        supplies=[
          {name:"B+", voltage:280, current:0.07, ripple:"<2mV"},
          {name:"Heater", voltage:6.3, current:1.5, type:"AC"},
          {name:"Bias", voltage:-12, current:0.001}
        ])
  → [генерирует схему БП: выпрямитель, CLC-фильтр, стабилизатор]
  → [рассчитывает номиналы: C1, L1, C2, R_bleeder]
  → [добавляет подсхему в проект]
  → [запускает моделирование пульсаций]
```

Шаблоны линейных БП: CLC, CLCRC, стабилизатор на газовом стабилитроне, электронный стабилизатор, LDO.
Шаблоны SMPS: Buck, Boost, Buck-Boost, Flyback, Forward, Half-Bridge. Для SMPS wizard автоматически рассчитывает трансформатор/дроссель (интеграция с Фазой 5).
Шаблоны специальные: DC-накал для ламповых схем, PFC (Power Factor Correction), зарядные устройства.

**Фаза 5: Намоточные изделия (+3 недели):**

Проектирование заказных трансформаторов, дросселей и катушек индуктивности — от ТЗ до документации для намотчика.

*6.1. Пайплайн:*

```
ТЗ на намоточное изделие
│  (напряжения, токи, мощность, частотный диапазон,
│   тип: выходной/силовой/дроссель, ограничения по габаритам)
│
▼ Выбор сердечника
│  PyOpenMagnetics: поиск в базе 10 000+ сердечников
│  Критерии: материал, сечение, окно, потери, габариты
│  Для аудио: кремнистая сталь (EI, C-core, тороид)
│  Для ИИП: ферриты (ETD, PQ, RM, E)
│
▼ Расчёт обмоток
│  transformer_designer / PyOpenMagnetics:
│  • Число витков (первичка, вторичка, доп. обмотки)
│  • Сечение провода (по плотности тока, с учётом скин-эффекта)
│  • Конфигурация слоёв и секционирование
│  • Изоляция: межслойная, межобмоточная, краевая
│  • Заполнение окна: проверка, что обмотки помещаются в каркас
│
▼ Расчёт паразитных параметров
│  • Индуктивность рассеяния (Llk) — определяет ВЧ-спад
│  • Межобмоточная ёмкость (Cw) — определяет резонанс
│  • Активное сопротивление обмоток (Rp, Rs)
│  • Потери в сердечнике (Rc)
│
▼ Верификация
│  FEMM: конечно-элементная проверка распределения поля
│  ngspice: SPICE-модель с паразитами → АЧХ трансформатора
│  Сравнение с требованиями ТЗ
│  ↺ Итерация: подстройка секционирования/зазора
│
▼ Конструирование
│  MVB → FreeCAD: 3D-модель (сердечник + каркас + обмотки)
│  Габаритный чертёж для корпуса (экспорт STEP)
│
▼ Документация для намотчика
   ├── Спецификация сердечника (тип, размер, материал, поставщик)
   ├── Спецификация каркаса (тип, размер)
   ├── Таблица обмоток:
   │   обмотка | витки | провод | слоёв | изоляция | начало/конец
   ├── Порядок намотки (послойная диаграмма)
   ├── Межобмоточная изоляция (материал, толщина, число слоёв)
   ├── Пропитка (лак, вакуумная, компаунд)
   └── Электрические параметры для приёмки
       (индуктивность, сопротивление, напряжение пробоя)
```

*7.2. Инструменты magnetics bridge (~300 строк):*

| Инструмент | Назначение |
|-----------|------------|
| `mag_select_core` | Подбор сердечника по требованиям (мощность, частота, габариты) из базы OpenMagnetics |
| `mag_design_transformer` | Полный расчёт трансформатора: витки, провод, секционирование, изоляция |
| `mag_design_choke` | Расчёт дросселя: индуктивность, ток подмагничивания, зазор |
| `mag_calc_parasitics` | Расчёт паразитных параметров → генерация SPICE-модели (.subckt) |
| `mag_verify_femm` | Запуск FEMM для верификации: экспорт Lua-скрипта → запуск → парсинг результатов |
| `mag_build_3d` | Генерация 3D-модели через MVB → FreeCAD (STEP для сборки корпуса) |
| `mag_export_winding_spec` | Экспорт спецификации для намотчика (PDF/Markdown) |

*6.3. Области применения:*

**Аудиотрансформаторы (ламповые/транзисторные):**
- Кремнистая сталь М6 (Ш-образная) или нанокристаллические сердечники (VITROPERM)
- Секционирование первичной обмотки для расширения полосы (PSPSP, PSPS, и т.д.)
- Расчёт оптимального числа секций по критерию Llk/полоса
- Для PP: симметрия половин первичной обмотки

**SMPS-трансформаторы:**
- Ферритовые сердечники (ETD, PQ, RM, E, EFD, EP)
- Расчёт по топологии: flyback (с зазором), forward, half-bridge, full-bridge
- Учёт скин-эффекта и proximity-эффекта на рабочей частоте (50–500 кГц)
- Litz-провод для снижения AC-потерь
- Интеграция с PSU wizard: wizard задаёт требования → magnetics phase рассчитывает трансформатор

**Силовые трансформаторы 50 Гц:**
- Множество вторичных обмоток: анодное (250–400В), накальные (6.3В, 12.6В), смещение, низковольтные для цифровых схем
- ВН-изоляция между первичной и вторичными
- Электростатический экран между первичной и вторичными обмотками (медная фольга → земля шасси) — снижение синфазных помех от сети
- Магнитный экран (кожух из трансформаторной стали) — снижение наводок на сигнальные цепи
- Ориентация трансформатора на шасси: ось магнитопровода перпендикулярна чувствительным цепям

**Дроссели (силовые и SMPS):**
- Зазор для предотвращения насыщения при постоянном подмагничивании
- Расчёт индуктивности с учётом тока подмагничивания
- Для SMPS: расчёт ripple current, core loss на рабочей частоте
- Для фильтров: оптимизация — минимум пульсаций при заданном токе
- Синфазные дроссели: для EMI-фильтров на входе SMPS

*6.4. Интеграция с остальной системой:*

- `mag_calc_parasitics` → генерирует .subckt → используется SPICEBridge для моделирования усилителя с реальным трансформатором
- `mag_build_3d` → STEP → FreeCAD → сборка с корпусом (Фаза 6)
- `mag_export_winding_spec` → включается в производственный пакет (Фаза 7)

*6.5. Зависимости:*

```
PyOpenMagnetics         # расчёт магнитных компонентов
pyFEMM                  # Python-обёртка для FEMM
```

Системные: FEMM (устанавливается через bootstrap.sh)

**Фаза 6: Проектирование корпуса (+3–4 недели):**

Интеграция FreeCAD для проектирования корпусов разрабатываемых устройств.

*6.1. Подключение MCP-сервера:*

```
kicad-sim-chat
   ├── mcp-kicad-sch-api ........ схемы
   ├── kicad-mcp-pro ............ проект, PCB, валидация, экспорт
   ├── spicebridge .............. симуляция
   ├── kicad-sim-bridge ......... оркестрация
   └── freecad-mcp .............. проектирование корпуса  ← НОВЫЙ
        └── FreeCAD (Part Design, Sheet Metal, TechDraw, Assembly)
```

*6.2. Пайплайн: от PCB к корпусу:*

```
.kicad_pcb (готовая, проверенная плата)
    │
    ▼ kicad-cli pcb export step
board.step (3D-модель PCB с компонентами)
    │
    ▼ FreeCAD: импорт STEP
    │
    ▼ Проектирование корпуса
    │  LLM через freecad-mcp:
    │  • Создаёт базовую форму шасси (Sheet Metal workbench)
    │  • Добавляет вырезы под компоненты: ламповые панельки,
    │    трансформаторы, потенциометры, разъёмы, вентиляция
    │  • Крепёжные отверстия совмещены с PCB
    │  • Сгибы, фланцы, стойки
    │
    ▼ Сборка
    │  Assembly workbench:
    │  • Плата + корпус + крепёж + трансформаторы
    │  • Проверка зазоров и интерференций
    │  • 3D-визуализация готового устройства
    │
    ▼ Экспорт
       ├── DXF развёртки панелей (для лазерной/фрезерной резки)
       ├── STEP полной сборки (для CNC или визуализации)
       ├── STL (для 3D-печати прототипов)
       └── TechDraw → PDF (2D-чертежи с размерами)
```

*6.3. Инструменты enclosure bridge (~200 строк):*

| Инструмент | Назначение |
|-----------|------------|
| `enclosure_from_pcb` | Импортировать STEP платы в FreeCAD, создать базовый корпус по размерам платы + отступы |
| `enclosure_add_cutout` | Добавить вырез: круглый (под панельку/потенциометр), прямоугольный (под разъём), произвольный |
| `enclosure_sheet_metal` | Применить Sheet Metal: сгибы, фланцы, стойки для крепления платы |
| `enclosure_assembly` | Собрать: плата + корпус + крепёж → проверка интерференций |
| `enclosure_export` | Экспорт: DXF развёртки + STEP сборки + PDF чертежей |
| `enclosure_render` | 3D-рендер сборки для визуального контроля |

*6.4. Примеры специфических требований:*

**Ламповые усилители:**
- Верхнее шасси: вырезы под октальные/нональные панельки, вентиляционные отверстия
- Трансформаторы на шасси: монтажные отверстия, разнесение силового и выходного
- Передняя/задняя панель: потенциометры, тумблеры, разъёмы, IEC-ввод
- Высоковольтная безопасность: защитный кожух, маркировка
- Вентиляция: расчёт площади отверстий по тепловыделению

**SMPS и цифровые устройства:**
- Вентиляция: расчёт для закрытого корпуса, отверстия или принудительное охлаждение
- EMI-экранирование: металлический корпус как экран, фильтры на вводах
- Отсеки: разделение силовой и сигнальной частей перегородкой
- Разъёмы: USB, Ethernet, SMA — с правильными вырезами и заземлением

**Общие:**
- Электромагнитное экранирование: заземление корпуса, минимум щелей
- Проходные конденсаторы / ферритовые фильтры на сетевом вводе (опционально)
- Крепление PCB: стойки, совмещение с отверстиями платы
- Доступ для обслуживания: съёмные панели

*6.5. Зависимости:*

- FreeCAD 1.0+ (с Sheet Metal workbench)
- freecad-mcp (pip install freecad-mcp)
- bootstrap.sh обновляется: установка FreeCAD + addon Sheet Metal

**Фаза 7: Производственная документация (+2 недели):**

Автоматическое формирование полного пакета документации из данных всех предыдущих фаз.

*7.1. Состав пакета:*

```
production-package/
├── schematic/
│   ├── schematic.pdf              # схема электрическая принципиальная
│   └── schematic.svg              # векторная версия для публикаций
├── simulation/
│   ├── sim_report.pdf             # отчёт о моделировании: АЧХ, ВАХ, рабочие точки
│   ├── sim_vs_measured.pdf        # сравнение симуляции с измерениями (если есть)
│   └── sim_data/                  # сырые данные моделирования
├── pcb/
│   ├── gerber/                    # Gerber-файлы всех слоёв
│   ├── drill/                     # файлы сверловки
│   ├── bom.csv                    # Bill of Materials
│   ├── bom.xlsx                   # BOM с группировкой и ценами
│   ├── pick-and-place.csv         # координаты для автомонтажа
│   ├── pcb_top.svg                # рендер верхней стороны
│   ├── pcb_bottom.svg             # рендер нижней стороны
│   └── pcb_3d.step                # 3D-модель платы
├── p2p/ (альтернатива pcb/)
│   ├── wiring_diagram.pdf         # монтажная схема
│   ├── chassis_layout.svg         # раскладка компонентов на шасси
│   ├── wiring_table.csv           # таблица проводников
│   └── assembly_order.pdf         # порядок монтажа
├── magnetics/
│   ├── OT1_winding_spec.pdf       # спецификация выходного трансформатора
│   ├── PT1_winding_spec.pdf       # спецификация силового трансформатора
│   ├── L1_winding_spec.pdf        # спецификация дросселя
│   ├── magnetics_3d/              # 3D-модели (STEP)
│   └── magnetics_bom.csv          # BOM намоточных (сердечники, каркасы, провод)
├── enclosure/
│   ├── chassis_flat.dxf           # развёртка шасси для лазерной резки
│   ├── front_panel.dxf            # передняя панель
│   ├── rear_panel.dxf             # задняя панель
│   ├── assembly.step              # 3D-модель полной сборки
│   ├── assembly_drawing.pdf       # сборочный чертёж с размерами
│   └── enclosure_bom.csv          # BOM корпуса (металл, крепёж, фурнитура)
├── cables/
│   ├── cable_table.csv            # таблица межблочных соединений
│   └── connector_pinouts.pdf      # распиновки разъёмов
├── sourcing/
│   ├── consolidated_bom.xlsx      # сводный BOM (все платы + корпус + намоточные + кабели)
│   ├── sourcing_mouser.csv        # BOM с артикулами Mouser
│   ├── sourcing_digikey.csv       # BOM с артикулами DigiKey
│   ├── sourcing_lcsc.csv          # BOM с артикулами LCSC
│   └── cost_estimate.md           # итоговая смета по поставщикам
├── safety/
│   ├── safety_checklist.pdf       # чеклист электробезопасности
│   ├── hazardous_voltages.pdf     # карта опасных напряжений
│   └── clearance_report.pdf       # отчёт по зазорам ВН-цепей
├── specifications/
│   ├── device_spec.md             # ТТХ устройства
│   ├── test_protocol.md           # протокол испытаний (шаблон + ожидаемые значения)
│   └── emi_report.md              # отчёт по помехозащите (грounding, экранировка)
└── README.md                      # описание проекта, версия, дата, автор
```

*7.2. Инструмент:*

```
/export-production <project> [--format jlcpcb|generic] [--lang ru|en]
```

Один вызов — собрать всё: экспортировать схему, Gerber, BOM, развёртки корпуса, спецификации намоточных, сгенерировать отчёты. LLM генерирует текстовые описания и ТТХ на основе результатов моделирования.

*7.3. Закупка компонентов:*

Сводный BOM → автоматический поиск по поставщикам:

| Категория | Поставщики | Метод поиска |
|-----------|-----------|--------------|
| SMD-компоненты | LCSC (JLCPCB), Mouser, DigiKey | API (LCSC через kicad-mcp-pro), поиск по part number |
| Лампы, панельки | Специализированные (tubes-store.com, и др.) | LLM формирует список, пользователь уточняет |
| Трансформаторное железо | Мосэлектра, и др. | По спецификации из Phase 5 |
| Высоковольтные конденсаторы | Mouser, DigiKey | API / ручной поиск |
| Корпус, крепёж | Местные поставщики, AliExpress | По DXF/чертежам из Phase 6 |

Итоговая смета с разбивкой по поставщикам и общей стоимостью.

*7.4. Верификация: измерения ↔ симуляция:*

Замыкание цикла между моделированием и реальным устройством:

```
Измерение (осциллограф, мультиметр, LCR-метр, NanoVNA)
    ↓ импорт CSV / S1P / S2P / скриншот
    ↓
bridge_import_measurement(file, type="ac_sweep")
    ↓
Наложение на результаты симуляции
    ↓
Отчёт о расхождениях:
  • АЧХ: симуляция vs. измерение
  • Рабочие точки: расчётные vs. измеренные
  • Паразитные параметры трансформатора: модель vs. реальность
    ↓
Коррекция модели → повторное моделирование
```

Поддерживаемые форматы импорта:
- CSV (время/напряжение, частота/амплитуда) — осциллограф, анализатор
- Touchstone (.s1p, .s2p) — NanoVNA, анализатор цепей
- Rigol/Siglent CSV — прямой экспорт с осциллографов
- Ручной ввод — для мультиметра (напряжения рабочих точек)

*7.5. Форматы под производителей:*

- **JLCPCB:** Gerber (RS-274X) + drill (Excellon) + BOM (LCSC part numbers) + pick-and-place (CSV с координатами)
- **Generic:** стандартный пакет Gerber + PDF + STEP
- **Для книги/публикации:** SVG схемы + графики + Markdown описание

**Фаза 8 (будущее):**
- Web-интерфейс для удалённого доступа
- Streaming для API-бэкендов
- Параллельный запрос на несколько моделей
- Интеграция kicad-python IPC API (когда появится поддержка схем)
- SSE-транспорт для MCP-серверов (доступ с телефона)
- Панелизация: объединение нескольких плат в одну панель для производства
- Экспорт в IPC-2581 (современная альтернатива Gerber)
- Интеграция с другими производителями (PCBWay, OSHPARK, Elecrow)
- RF-модуль: S-параметры, Smith chart, модели линий передачи, интеграция NanoVNA

---

## 14. Метрики приёмки

**Фазы 1–3 (схемы, симуляция, чат-клиент):**
1. `bootstrap.sh` на чистой Ubuntu 24.04 → рабочая система за ≤10 минут
2. `kicad-sim-chat` запускается, показывает доступные бэкенды и инструменты
3. Создание схемы RC-фильтра → AC-анализ → корректная АЧХ — end-to-end через чат
4. Создание ламповой схемы (SE на 6П14П) → OP-анализ → корректные рабочие точки
5. Схемы из mcp-kicad-sch-api открываются в KiCad GUI без ошибок
6. Все встроенные модели ламп проходят тест рабочей точки в ngspice
7. `/model gpt4` переключает бэкенд, инструменты остаются доступны
8. `/compare` показывает ответы двух моделей на один запрос
9. `/save` + `/load` корректно восстанавливает сессию с контекстом и проектом
10. bridge_edit_and_resim корректно изменяет номинал и пересимулирует

**Фаза 4 (PCB):**
11. pcb_from_schematic создаёт валидный .kicad_pcb из .kicad_sch (открывается в KiCad)
12. pcb_place_components размещает все компоненты без перекрытий
13. pcb_autoroute через FreeRouting достигает ≥95% completion rate на тестовой плате
14. pcb_validate проходит DRC без критических нарушений
15. pcb_export_manufacturing генерирует корректные Gerber-файлы (проверка через gerbv или KiCad Gerber Viewer)
16. Рендер PCB в SVG показывает корректное расположение всех слоёв
17. Полный цикл «схема → моделирование → PCB → Gerber» проходит end-to-end

**Операционные:**
18. Результат симуляции в контексте LLM ≤ 500 токенов (summary), полные данные — по запросу
19. Модификация схемы при открытом KiCad GUI проходит через staged без потери данных
20. Модель российской лампы (6П14П) создаётся, валидируется по ВАХ и добавляется в библиотеку
21. git log проекта показывает историю всех изменений с осмысленными commit messages
22. `--doctor` проверяет все компоненты и выдаёт статус в JSON
23. `--update` обновляет пакеты без потери конфигурации и проектов
24. export_sim_report генерирует Markdown с встроенными SVG для публикации

**Фаза 5 (намоточные изделия):**
18. mag_select_core находит подходящий сердечник из базы OpenMagnetics по заданным параметрам
19. mag_design_transformer рассчитывает обмотки, проверяет заполнение окна
20. mag_calc_parasitics генерирует SPICE .subckt с корректными паразитами
21. mag_verify_femm запускает FEMM и возвращает распределение поля
22. mag_export_winding_spec генерирует читаемую спецификацию для намотчика
23. SPICE-модель трансформатора, полученная через mag_calc_parasitics, даёт корректную АЧХ в ngspice

**Фаза 6 (корпус):**
30. enclosure_from_pcb импортирует STEP платы и создаёт базовый корпус в FreeCAD
31. Sheet Metal развёртка экспортируется в DXF корректно (проверка в LibreCAD)
32. Сборка плата + корпус в FreeCAD не имеет интерференций
33. 3D-рендер сборки показывает корректное взаимное расположение всех деталей

**Фаза 7 (документация):**
34. /export-production` генерирует полный пакет за один вызов
35. Gerber-файлы проходят проверку в gerbv / KiCad Gerber Viewer
36. BOM содержит все компоненты с корректными номиналами
37. Полный цикл «идея → схема → симуляция → намоточные изделия → PCB → корпус → документация» проходит end-to-end

---

## 15. Реализация

**Подход:** разработка ведётся при активном использовании Claude Code (Гвидо) в качестве со-разработчика. Основной разработчик — один человек. Claude Code реализует модули по спецификациям из ТЗ, разработчик верифицирует, тестирует и интегрирует.

**Стратегия версионирования зависимостей:**
- `pyproject.toml` фиксирует диапазоны версий: `ngspice>=42,<50`, `kicad-mcp-pro>=3.0,<4.0`
- `uv.lock` / `requirements.lock` — точные версии для воспроизводимости
- Матрица совместимости (CI): тестирование на KiCad 10.x, ngspice 42/43/44, Python 3.11/3.12/3.13
- При обнаружении несовместимости — pin до рабочей версии + issue

**PySpice — стратегия минимизации риска:**
PySpice (v1.5, 2021) не обновляется. План:
1. Использовать PySpice для shared library mode (основной путь)
2. Если PySpice ломается с новым ngspice — fallback на batch mode (`ngspice -b`)
3. Долгосрочно: прямой CFFI-биндинг к libngspice (~200 строк), заменяющий PySpice

---

## 16. Риски и митигации

| # | Риск | Вероятность | Влияние | Митигация |
|---|------|-------------|---------|-----------|
| 1 | kicad-mcp-pro (3 недели, 3 stars) заброшен или нестабилен | Средняя | Высокое | Тестирование в Фазе 1a. Fallback: Seeed Studio kicad-mcp-server + mixelpixx (оба зрелые) |
| 2 | PySpice несовместим с ngspice 44+ | Средняя | Среднее | Batch mode fallback. Долгосрочно: собственный CFFI-биндинг |
| 3 | kicad-sch-api не работает с KiCad 10 | Низкая | Высокое | Формат .kicad_sch обратно совместим. Тест при bootstrap |
| 4 | FEMM не работает на Linux (Wine) | Средняя | Низкое | FEMMT (кроссплатформенный Python FEM). Или Docker с FEMM |
| 5 | Claude Code Max меняет CLI-интерфейс | Средняя | Среднее | Абстракция в claude_code.py backend. Быстрая адаптация |
| 6 | Контекстное окно недостаточно для сложных проектов | Высокая | Среднее | Суммаризация (10.1 + 10.5). Двухуровневые результаты |
| 7 | SPICEBridge не работает на Windows | Средняя | Среднее | Тест при bootstrap. Fallback: PySpice + собственная обёртка ngspice |
| 8 | freecad-mcp требует запущенный FreeCAD GUI | Низкая | Низкое | FreeCAD запускается автоматически через app_manager |
| 9 | Реальный объём кода превысит оценку | Высокая | Низкое | Фазированная разработка. MVP без P2P, magnetics, enclosure |
| 10 | Нет интернета для bootstrap (air-gapped) | Низкая | Среднее | Офлайн-пакет: архив со всеми зависимостями |

---

## 17. Глоссарий

| Термин | Расшифровка |
|--------|------------|
| MCP | Model Context Protocol — протокол Anthropic для подключения инструментов к LLM |
| MAS | Magnetic Agnostic Structure — стандартный JSON-формат описания магнитных компонентов (OpenMagnetics) |
| MKF | Magnetics Knowledge Foundation — движок моделирования OpenMagnetics |
| MVB | Magnetics Virtual Builder — генератор 3D-моделей магнитных компонентов для FreeCAD |
| SPICEBridge | MCP-сервер для ngspice с 18 инструментами моделирования |
| bridge | kicad-sim-bridge — наш оркестрационный MCP-сервер |
| wizard | Автоматический помощник для типовых задач (например, psu_wizard для расчёта БП) |
| P2P | Point-to-point — навесной монтаж без печатной платы |
| DFM | Design for Manufacturing — проверка технологичности конструкции |
| SI/PI | Signal Integrity / Power Integrity — целостность сигналов / питания |
| EMC/EMI | Electromagnetic Compatibility / Interference — электромагнитная совместимость / помехи |
| ERC/DRC | Electrical Rules Check / Design Rules Check — проверка электрических / конструктивных правил |
| OTL | Output Transformerless — бестрансформаторный выходной каскад |
| SE/PP | Single-Ended / Push-Pull — однотактный / двухтактный выходной каскад |
| SMPS | Switch-Mode Power Supply — импульсный источник питания |
| LDO | Low Drop-Out regulator — линейный стабилизатор с малым падением напряжения |
| FEMM | Finite Element Method Magnetics — программа конечно-элементного анализа магнитных полей |
| FEMMT | FEM Magnetics Toolbox — Python-обёртка для автоматизации FEMM |
| Sixel/Kitty | Протоколы для отображения растровой графики в терминале |
| SSE | Server-Sent Events — транспорт для удалённого подключения к MCP-серверам |

---

## 18. Итого: соотношение готового и своего

| Компонент | Источник | Объём своего кода |
|-----------|----------|-------------------|
| Создание схем | kicad-sch-api + MCP-сервер (PyPI) | 0 |
| Проект / PCB / валидация / экспорт | kicad-mcp-pro (PyPI) | 0 |
| Моделирование | SPICEBridge (GitHub) | 0 |
| Python↔ngspice | PySpice (PyPI) | 0 |
| Экспорт нетлистов / SVG | kicad-cli (KiCad) | 0 |
| Модели ламп | Koren / Ayumi / Duncan | ~50 строк (конвертация) |
| Curve-fitting | Gleb Zaslavsky tool (GitHub) | 0 |
| PCB layout + валидация + экспорт | kicad-mcp-pro (PyPI) | 0 |
| Автотрассировка | FreeRouting (встроен в kicad-mcp-pro) | 0 |
| pcbnew API | KiCad built-in | 0 |
| Проектирование корпусов | FreeCAD + freecad-mcp (GitHub) | 0 |
| Расчёт намоточных изделий | PyOpenMagnetics + transformer_designer | 0 |
| 3D-модели магнитных компонентов | MVB (OpenMagnetics → FreeCAD) | 0 |
| Верификация магнитных полей | FEMM + pyFEMM | 0 |
| **Оркестрация схем (bridge)** | **Наша разработка** | **~500 строк Python** |
| **Оркестрация PCB (pcb bridge)** | **Наша разработка** | **~300 строк Python** |
| **Навесной монтаж (P2P bridge)** | **Наша разработка** | **~250 строк Python** |
| **Помехозащита / безопасность** | **Наша разработка** | **~200 строк Python** |
| **Wizard БП** | **Наша разработка** | **~200 строк Python** |
| **Оркестрация намоточных изделий** | **Наша разработка** | **~300 строк Python** |
| **Оркестрация корпусов** | **Наша разработка** | **~200 строк Python** |
| **Управление проектами (project.yaml, DDR, sessions)** | **Наша разработка** | **~400 строк Python** |
| **Производственная документация + sourcing** | **Наша разработка** | **~400 строк Python** |
| **Импорт измерений** | **Наша разработка** | **~150 строк Python** |
| **Менеджер приложений + платформа** | **Наша разработка** | **~300 строк Python** |
| **Чат-клиент (UI + MCP-клиент + бэкенды)** | **Наша разработка** | **~1500 строк Python** |
| **Bootstrap (Linux + Windows)** | **Наша разработка** | **~500 строк bash+ps1** |

**Собственный код: ~5200 строк. Всё остальное — интеграция готовых open-source решений.**


---

## 19. Стратегия версионирования зависимостей

**Файл `compatibility.toml` в корне репозитория:**

```toml
[tested]
kicad = "10.0"
ngspice = "42"
freecad = "1.0"
python = "3.12"
kicad-mcp-pro = "3.0.2"
kicad-sch-api = "0.2.4"
spicebridge = "1.0.0"
freecad-mcp = "0.3.0"
PyOpenMagnetics = "1.0.0"

[minimum]
kicad = "10.0"
ngspice = "40"
python = "3.11"
```

bootstrap устанавливает проверенные версии. `--update` обновляет до последних, запускает smoke-тест, обновляет `compatibility.toml` при успехе.

---

## 20. Конфигурация: схема файлов

Три конфигурационных файла с чётким разграничением:

| Файл | Что хранит | Кто использует |
|------|-----------|----------------|
| `config.toml` | Пути, настройки ngspice, таймауты — **инфраструктура** | kicad-sim-bridge |
| `backends.toml` | API-ключи, модели LLM — **бэкенды** | kicad-sim-chat |
| Claude Desktop JSON | Пути к MCP-серверам | Альтернативный клиент (без нашего чата) |

Первые два — обязательные. Третий — генерируется для тех, кто хочет использовать MCP-серверы из Claude Desktop напрямую. **Ограничение:** при работе через Claude Desktop проектные функции (DDR, сессии, project.yaml) не доступны — они реализованы в нашем чат-клиенте.

---

## 21. Docker-вариант развёртывания

Альтернатива bootstrap-скриптам для CI/CD и удалённого доступа:

```dockerfile
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y \
    kicad ngspice libngspice-dev freecad \
    python3 python3-pip python3-venv \
    openjdk-17-jre git xvfb
COPY . /opt/kicad-sim-system
RUN pip install --break-system-packages -e "/opt/kicad-sim-system[all]"
EXPOSE 8765
CMD ["python", "-m", "kicad_sim_bridge", "--transport", "sse"]
```

Когда использовать: CI/CD, SSE на VPS, быстрая проверка (`docker run --rm kicad-sim-system --doctor`).
Когда НЕ использовать: повседневная работа с KiCad/FreeCAD GUI.

---

## 22. Дополнительные сценарии: цифровые и SMPS проекты

Дополнение к основным сценариям (§8). Развёрнутые примеры с полным пайплайном:

### 22.1. Контроллер на STM32 с USB

```
User: "Создай схему контроллера на STM32F103C8T6 с USB, SPI-дисплеем
       и 4 аналоговыми входами. Питание от USB 5В."

LLM:
  → sch.create_schematic("stm32-controller")
  → [добавляет МК, USB, LDO 3.3В, кварц, блокировочные 100nF]
  → pcb_from_schematic(..., rules={usb_impedance:"90ohm_diff"})
  → pcb_emi_check(...)
  → pcb_export_manufacturing("stm32-controller", format="jlcpcb")
```

### 22.2. Импульсный БП 12В/3А (flyback)

```
User: "Спроектируй обратноходовой БП: 220В AC → 12В DC 3А,
       изолированный, с EMI-фильтром на входе"

LLM:
  → psu_wizard(topology="flyback", input="220VAC", output={12V, 3A})
  → bridge_design_to_sim(..., analysis="tran")
  → mag_design_transformer(..., topology="flyback", freq:"100kHz", core:"N87")
  → pcb_from_schematic(..., rules={smps_loop:"minimize"})
  → pcb_emi_check(...)
  → /export-production --format generic
```

---

## 23. Команда и процесс реализации

Один разработчик (Vladimir) + Claude Code (Гвидо) как AI-ассистент. Claude Code реализует модули по ТЗ, разработчик верифицирует, тестирует и интегрирует. AI ускоряет кодирование в 3–5 раз, но не ускоряет архитектурные решения, отладку интеграций и тестирование на реальном железе.

---

## 24. Приоритеты метрик приёмки

**Must-have (MVP):** метрики 1–6, 10, 18, 22 (bootstrap, end-to-end, context management, doctor).

**Should-have:** метрики 7–9, 11–17, 19–24, 30–33 (бэкенды, PCB, magnetics, safety, git, enclosure).

**Nice-to-have:** метрики 25–29, 34–37 (custom models, FEMM, production package, full E2E).

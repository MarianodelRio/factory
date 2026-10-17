# design_factory.md — Diseño funcional y técnico de la Software Factory

> **Versión:** 1.0 — propuesta de diseño para revisión antes de implementar  
> **Fecha de referencia:** 16 de octubre de 2026  
> **Estado:** Decisiones funcionales consensuadas; este documento completo queda pendiente de aprobación final.  
> **Objetivo:** Servir como especificación de partida para implementar una Factory reutilizable para proyectos personales y profesionales, en VS Code, Orca y terminal, con Claude Code y Codex.  
> **Prioridades:** sencillez, robustez, portabilidad, recuperación, trazabilidad y ausencia de duplicidades.

## 0. Resumen ejecutivo y decisiones cerradas

Se construirá un **repositorio de herramientas y plantillas**, instalable mediante una CLI ligera, que convierta un repositorio Git existente o nuevo en un entorno preparado para el desarrollo asistido por agentes. La Factory no será un IDE, un modelo, un gestor remoto de agentes ni una segunda plataforma de Git.

Su cometido será dar un **contrato operativo común** a distintas herramientas: inicializar el proyecto, facilitar investigación y diseño, exigir aprobación antes de implementar cambios no triviales, gestionar tareas y dependencias, asignar worktrees, registrar progreso, facilitar recuperación y ofrecer un dashboard HTML local.

### 0.1 Decisiones ya tomadas

| Área | Decisión |
|---|---|
| Interfaces | VS Code y Orca con las mismas capacidades esenciales; terminal y CLI como alternativa. |
| Proveedores | Claude Code y Codex, intercambiables entre investigación, implementación y revisión. |
| OpenSpec | Enfoque híbrido: se probará como proveedor de especificaciones; podrá desactivarse o sustituirse sin perder tareas ni aprobaciones. |
| Complejidad del flujo | Adaptativo: sin Planner obligatorio; se añade descomposición y Reviewer según complejidad y riesgo. |
| Aprobación | Diseño técnico aprobado explícitamente por una persona antes de la implementación formal. |
| Autonomía | Adaptativa: fases rutinarias automatizables; pausas ante decisiones de alcance, riesgos o acciones no autorizadas. |
| Tareas | Adaptador local en uso personal y posibilidad de GitHub Issues u otra herramienta existente en equipos. |
| Git | La Factory crea ramas y worktrees; se permite hacer commits; **no hace push, merge ni despliegue automático por defecto**. |
| Recuperación | V1 manual: marcar una ejecución interrumpida y permitir reanudarla explícitamente. Sin reinicio automático. |
| Memoria | Checkpoints operativos automáticos; documentación permanente propuesta/revisada, sin Memory Manager obligatorio. |
| Dashboard | HTML local **actualizado**, inicialmente de solo lectura y sin backend complejo. |
| Convivencia con equipos | Respetar repositorios, instrucciones, permisos y CI existentes. No reestructurar proyectos salvo aprobación. |

### 0.2 Cinco pilares

1. **Setup y configuración inteligente**: detectar lo existente y añadir lo mínimo necesario.
2. **Investigación, diseño y aprobación**: crear una especificación verificable y bloquear implementación formal hasta aprobarla.
3. **Flujo de agentes y orquestación ligera**: implementar, verificar, revisar y coordinar proveedores según la tarea.
4. **Tareas, progreso, worktrees y dashboard**: conocer trabajo disponible, activo, bloqueado y recuperable.
5. **Memoria y contexto**: conservar conocimiento útil y evitar inflar permanentemente el contexto.

### 0.3 Principios no negociables

- **Agnosticismo**: ningún artefacto de trabajo importante dependerá del historial privado de Claude, Codex, VS Code u Orca.
- **Configuración por descubrimiento**: la Factory detectará herramientas y capacidades instaladas en vez de asumirlas.
- **Una única fuente de verdad por dato**: no mantener simultáneamente varias listas de tareas editables o copias de la misma regla.
- **Operaciones seguras por defecto**: `doctor` y `--dry-run` no alteran el repositorio; nada destructivo sin confirmación.
- **Calidad demostrable**: «terminado» exige comprobaciones y evidencia, no solo la afirmación de un LLM.
- **Eficiencia contextual**: instrucciones cortas y documentación consultada selectivamente.
- **Trazabilidad**: diseño, versión aprobada, tarea, ejecución, rama, resultados y checkpoints estarán vinculados.
- **Respeto a los equipos**: prevalecen las normas corporativas, el control de acceso y la protección de ramas.
- **Configuración simple**: biblioteca estándar de Python como preferencia para la CLI; no introducir servicios permanentes ni dependencias por defecto.
- **Degradación controlada**: sin OpenSpec, Orca, GitHub o algún hook, la Factory debe seguir permitiendo trabajar localmente.

### 0.4 Fuera del alcance de la V1

No se implementarán: agentes IA propios que sustituyan a Claude/Codex; RAG o base vectorial de memoria; panel remoto multiusuario; motor de despliegue; fusión automática de PR; reintentos automáticos de tareas interrumpidas; facturación/cuotas por API; entrenamiento o benchmark continuo de modelos; un sistema propio de permisos que pretenda sustituir los del SO/IDE/GitHub; edición de tareas desde el dashboard; ni una plataforma distribuida de workers.

---

## 1. Producto y arquitectura general

### 1.1 Usuario y escenarios principales

- **Proyecto personal nuevo**: instalar la Factory, detectar stack y herramientas, configurar documentación mínima, diseñar funcionalidad, aprobarla, implementarla con cualquier proveedor, revisar cambios y mantener un dashboard.
- **Proyecto personal existente**: no romper configuraciones previas, reutilizar tests y convenciones, incorporar las capacidades que faltan.
- **Proyecto profesional individual dentro de un equipo**: utilizar las mismas skills y reglas, pero sin tocar política de ramas, CI, secretos ni herramientas corporativas. El trabajo de implementación sigue siendo local hasta que se elija publicar.
- **Proyecto colaborativo**: tareas y decisiones compartidas mediante Git y tracker existente cuando se configure; cada desarrollador tiene su estado de ejecución local, sin sincronizar transcripciones ni preferencias personales.
- **Trabajo paralelo**: una persona investiga y aprueba otras funcionalidades mientras uno o más agentes trabajan en distintas ramas/worktrees sobre tareas ya disponibles.

### 1.2 Arquitectura lógica

```text
Usuario (chat VS Code / chat Orca / terminal)
                   |
          Skills / CLI Factory
                   |
+--------------------------------------------------+
| FACTORY CORE                                     |
| Diagnóstico | Configuración | Contratos           |
| Diseños/aprobación | Tareas/estados | Checkpoints |
| Política de ejecución | Verificaciones           |
+--------------------------------------------------+
     |             |            |              |
 Planificación   Runners       Git          Persistencia
 OpenSpec o      Claude /      branches /   estado local
 plantilla       Codex         worktrees    y adaptador remoto
     |             |            |              |
     +-------------+------------+--------------+
                   |
         Dashboard HTML local
```

**Responsabilidades y límites**:

- **Core**: reglas deterministas, validaciones, estados, versiones, locks y contratos de resultados. No invoca un LLM para tareas que puede resolver con código.
- **Skills**: procedimientos semánticos para investigar, diseñar, ejecutar o reanudar. Se activan desde el chat y llaman a la CLI para operaciones deterministas.
- **Adaptadores de agentes**: descubrimiento de CLI, selección de modelo, lanzamiento opcional, detección de estado y captura de salida cuando el cliente lo permita.
- **Adaptadores de planificación**: OpenSpec o plantilla propia, convertidos a un contrato de cambio común.
- **Adaptadores de tareas**: local como base; GitHub/otros cuando sea conveniente. No reimplementar GitHub Issues.
- **Git**: ramas, worktrees, diffs, commits, logs y comprobaciones nativas.
- **Dashboard**: visualiza datos del Core y de adaptadores; no mantiene una segunda base de datos.

### 1.3 Repositorio de la Factory (fuente distribuible)

Estructura orientativa, susceptible de compactarse sin alterar contratos:

```text
software-factory/
├── pyproject.toml
├── README.md
├── src/factory/
│   ├── cli.py
│   ├── config.py
│   ├── doctor.py
│   ├── installer.py
│   ├── planning.py
│   ├── approval.py
│   ├── tasks.py
│   ├── execution.py
│   ├── worktrees.py
│   ├── events.py
│   ├── dashboard.py
│   └── adapters/
│       ├── claude.py
│       ├── codex.py
│       ├── openspec.py
│       ├── orca.py
│       └── github.py
├── templates/
│   ├── project/
│   ├── skills/
│   ├── planning/
│   └── dashboard/
├── tests/
└── docs/
```

**Implementación propuesta**: Python 3.11+, `argparse` o equivalente, `subprocess`, `pathlib`, `tomllib`, `sqlite3`, `json`, `hashlib` y `http.server`. No son obligatorias dependencias externas para el núcleo. OpenSpec, Claude, Codex, Orca y `gh` serán ejecutables externos **opcionales** y detectados. `pyproject.toml` publicará el *entry point* `factory` para poder instalar el paquete localmente con `pipx install <ruta-del-repo>` o una herramienta Python equivalente. La Factory no deberá requerir que el proyecto destino tenga un entorno virtual Python específico.

### 1.4 Archivos generados en un proyecto

```text
mi-repositorio/
├── AGENTS.md                       # instrucciones comunes, breve
├── CLAUDE.md                       # solo si se necesita puente compatibilidad
├── .factory/
│   └── config.toml                 # configuración compartida y versionada
├── .agents/skills/
│   ├── factory-design/SKILL.md
│   ├── factory-implement/SKILL.md
│   └── factory-resume/SKILL.md
├── .claude/skills/
│   ├── factory-design/SKILL.md
│   ├── factory-implement/SKILL.md
│   └── factory-resume/SKILL.md
├── openspec/                       # solo si planificación=openspec
│   ├── config.yaml
│   ├── schemas/                    # solo si personalización resulta útil
│   └── changes/...
└── docs/
    ├── architecture.md             # si el proyecto necesita este documento
    └── decisions.md                # si hay decisiones duraderas
```

Si `planning.provider = "builtin"`, los diseños se almacenan como `.factory/changes/<id>/design.md` y, si procede, `proposal.md`, `spec.md` y `tasks.md`. Si se usa OpenSpec, estos artefactos residen en **su estructura nativa** y la Factory almacena solo sus referencias. **No se crearán ambas estructuras a la vez.**

Los ficheros de ejecución **no versionados** (SQLite, locks, eventos operativos, `progress.md`, logs y preferencias locales) se guardarán en el directorio Git común, según `git rev-parse --git-common-dir`, dentro de `<git-common-dir>/factory/`. Así se ven desde todos los worktrees del mismo clon y no contaminan ramas ni commits. El directorio Git común puede estar fuera del checkout; la ruta siempre debe resolverse mediante Git, nunca presuponerse `.git/`.

**Limitación deliberada**: este estado operacional no se sincroniza entre máquinas. Los estados compartidos de equipo provendrán de GitHub/otro tracker y de los artefactos de diseño versionados. No asumir que un `progress.md` local puede sustituir la coordinación remota.

---

## 2. Pilar I — Setup y configuración inteligente

### 2.1 Objetivo funcional

Con uno o dos comandos, preparar cualquier repo sin forzar una estructura corporativa, sin duplicar reglas y sin romper las herramientas ya utilizadas.

### 2.2 Diagnóstico: `factory doctor`

El comando genera un inventario **sin modificar archivos**:

1. Verifica que está en un repositorio Git e identifica raíz, rama, directorio Git común, estado de cambios y worktrees.
2. Detecta sistema operativo, versión de Python, `git`, `claude`, `codex`, `openspec`, `orca` y `gh` con comprobaciones de existencia/versiones **sin solicitar login ni imprimir credenciales**.
3. Detecta configuración preexistente: `AGENTS.md`, `CLAUDE.md`, skills de ambos proveedores, hooks, MCP, reglas internas del repositorio y OpenSpec.
4. Inspecciona stack por manifiestos y estructura: Python, Node, Go, Rust, Java, monorepo, Docker, bases de datos y frontend. Muestra *evidencia*, no adivina tecnologías.
5. Encuentra comandos de tests, lint, typecheck y build a partir de `pyproject.toml`, `package.json`, Makefile, CI o documentación; en ausencia de evidencia, propone confirmación.
6. Detecta tracker/CI/host Git si existe (`origin`, `.github/`, configuración `gh`), y si un proyecto ya incorpora reglas y hooks que podrían entrar en conflicto.
7. Informa sobre compatibilidad del adaptador, capacidades observables (chat, hooks, CLI programática), dependencias opcionales y riesgos.
8. Devuelve informe legible y `--json` para pruebas/automatización. No debe introducir secretos en los resultados.

La falta de Orca o OpenSpec es una **capacidad no disponible**, no un error de inicialización; la ausencia de Git sí impide gestionar worktrees.

### 2.3 Inicialización: `factory init --profile personal|team`

Flujo:

1. Ejecuta internamente `doctor`.
2. Elige perfil (`personal` o `team`), detecta proveedores, configuración previa y proveedor de planificación disponible.
3. Prepara un **plan de cambios** de archivos nuevos, editados, respetados y conflictos.
4. Muestra diff y solicita confirmación antes de escribir. `--dry-run` siempre produce el plan sin cambios.
5. Crea la configuración común y skills mínimas; añade información verificada del repositorio a `AGENTS.md` o propone un parche conservador.
6. Instala integración OpenSpec **solo cuando esté seleccionada y disponible**, con revisión de los cambios generados. No ejecuta instalaciones globales sin permiso.
7. Opcionalmente configura hooks locales del proveedor tras mostrar lo que ejecutarán y el mecanismo de confianza del cliente.
8. Registra en un manifiesto interno qué archivos creó o gestionó la Factory, su versión de plantilla y su hash de origen.
9. Ejecuta validación posterior: rutas, frontmatter de skills, lectura de instrucciones por los proveedores, esquema de configuración, backend local y comandos seguros del proyecto si se autorizan.
10. Entrega instrucciones concretas para abrir VS Code/Orca, invocar skills y iniciar una primera tarea.

**Idempotencia**: repetir `init` no duplica reglas ni skills. Si un archivo gestionado cambió manualmente, no se sobrescribe: mostrar diff y pedir decisión. Archivos ajenos nunca se sobrescriben. No instalar hooks silenciosamente.

### 2.4 Perfiles y precedencia

- **`personal`**: tracker local, commits permitidos, aprobación humana local, preferencia de proveedores local, OpenSpec opcional, dashboard local.
- **`team`**: priorizar reglas existentes, advertir sobre modificaciones compartidas, usar tracker corporativo si se configura, trabajar con permisos mínimos, mantener preferencias individuales fuera de Git.
- **Precedencia**: políticas obligatorias de la organización > instrucciones y configuración ya aprobadas del proyecto > configuración compartida Factory > configuración local del desarrollador > valores por defecto.
- No existe una «política propia de Factory» que dé permiso para eludir restricciones del repositorio o del proveedor.

### 2.5 Actualización: `factory upgrade --dry-run`

La CLI detecta versión de plantillas, compatibilidad de schema y cambios realizados manualmente; propone los mínimos cambios para actualizar, conserva personalizaciones y ofrece copia de seguridad de los archivos que sí deban regenerarse. Nunca modifica las versiones aprobadas de diseños activos.

### 2.6 Contratos de uso

```bash
factory doctor
factory doctor --json
factory init --profile personal --dry-run
factory init --profile personal
factory init --profile team
factory upgrade --dry-run
factory upgrade
```

**Criterios de aceptación**: instalar dos veces produce el mismo resultado; un repositorio preexistente queda funcional sin perder reglas; detectar una instalación parcial permite completar lo que falta; `--dry-run` deja árbol y configuración intactos; funcionar sin Orca y sin OpenSpec.

---

## 3. Pilar II — Investigación, diseño y aprobación

### 3.1 Cambio y diseño como artefactos independientes

Una **change** es una iniciativa funcional/técnica con identificador estable (`CHG-0012`) y documentos asociados. Una **task** es una unidad ejecutable (`CHG-0012-01`). Un diseño puede producir una o muchas tareas. Las tareas siempre referencian la change y la versión del diseño.

La investigación y el diseño **no modifican código de producto** salvo autorización explícita y separada para una prueba o experimento. Pueden crear documentos de planificación y registros de estado.

### 3.2 Skill `factory-design` (chat-first)

Invocación esperada:
- Claude Code: `/factory-design Descripción del cambio`.
- Codex: `$factory-design Descripción del cambio`.
- En Orca, desde su chat o terminal del agente con la misma skill.

Contrato operativo:

1. Obtener snapshot y contexto **relevante** del repo (no leerlo entero sin necesidad).
2. Aclarar requisitos ambiguos que afecten el diseño; cuando sea posible, investigar y proponer opciones antes de preguntar.
3. Identificar problema, objetivos, fuera de alcance, restricciones, usuarios afectados y comportamientos actuales comprobados.
4. Considerar alternativas y documentar trade-offs; proponer la solución mínima coherente.
5. Diseñar componentes, contratos, errores, persistencia, compatibilidad, concurrencia, despliegue y seguridad **solo cuando correspondan**.
6. Definir criterios de aceptación numerados y verificables, con comandos o pruebas que aportarán evidencia.
7. Registrar riesgos, supuestos y preguntas bloqueantes. No rellenar vacíos mediante suposiciones ocultas.
8. Generar los documentos del proveedor seleccionado y registrar la change como `awaiting_approval`.
9. Presentar al usuario resumen de decisiones, riesgos y vínculo/ruta del diseño; **no lanzar implementación**.

### 3.3 Tamaños de diseño

Se evitará producir cuatro documentos grandes para todas las tareas:

| Categoría | Regla inicial | Documentación |
|---|---|---|
| Trivial | Cambios seguros y delimitados, sin nuevas decisiones de arquitectura | Una tarea con criterios de cierre; «fast path» autorizado explícitamente por el humano. |
| Normal | Funcionalidad o bug significativo con alcance claro | `design.md` conciso y criterios de aceptación; lista de tareas cuando proceda. |
| Compleja | Varias capas, interfaces públicas, seguridad, datos/migraciones, concurrencia o múltiples responsables | `proposal.md`, una o varias `spec.md`, `design.md` y tareas con dependencias. |

La categoría es una **recomendación**, no una regla basada exclusivamente en número de líneas o archivos. Riesgo alto puede elevar un cambio de tamaño pequeño.

### 3.4 OpenSpec: integración híbrida y reversible

- El adaptador detecta versión y capacidades de OpenSpec, lo inicializa si se ha elegido y respeta la estructura existente.
- Emplea sus conceptos de propuesta, specs, diseño y tareas; puede utilizar un schema personalizado ligero **cuando se haya verificado compatibilidad de la versión instalada**.
- `factory-design` puede delegar la generación de artefactos a OpenSpec, pero devuelve siempre una referencia normalizada `{change_id, provider, artifact_paths, design_digest, status}`.
- **No se usan los checkboxes de `tasks.md` como estado autoritativo de ejecución**. Pueden reflejar hitos al cerrar una tarea, pero el tracker mantiene propiedad, dependencias y estado.
- OpenSpec no se convierte en guardia de aprobación; la aprobación reside en el Core.
- Si se desactiva OpenSpec, los diseños ya creados siguen siendo Markdown legible y se conservan; el adaptador `builtin` gestiona los cambios futuros. No migrar ni duplicar documentos sin petición explícita.
- Una change usa **un solo proveedor de planificación**, fijado al crearla. Cambiar de proveedor solo afecta a nuevas changes salvo migración consciente.

### 3.5 Plantilla de diseño — contrato mínimo

`design.md` se ajustará al siguiente esquema (secciones no aplicables pueden omitirse con justificación breve):

```markdown
# CHG-0012 — Título

## 1. Contexto y problema
Situación actual verificada, limitaciones y referencias al código.

## 2. Objetivo y alcance
Resultado esperado. Incluye / no incluye.

## 3. Requisitos y aceptación
- AC-01: [comportamiento medible, test o verificación]
- AC-02: [error, borde, compatibilidad o seguridad]

## 4. Solución y decisiones
Alternativas consideradas, decisión adoptada y trade-offs.

## 5. Diseño técnico
Componentes, archivos o módulos, interfaces y contratos.
Persistencia, concurrencia, seguridad, compatibilidad,
despliegue o migraciones si aplican.

## 6. Plan de verificación
AC -> prueba/comando/evidencia esperada.
Casos negativos, regresiones y validaciones manuales.

## 7. Riesgos y mitigaciones
Dependencias, suposiciones, rollback cuando corresponda.

## 8. Preguntas y aprobaciones pendientes
Solo decisiones no resueltas, con impacto señalado.

## 9. Definición de terminado
Condiciones necesarias para declarar el cambio completo.
```

**Reglas de redacción del agente**: distinguir hecho verificado de suposición; rutas reales cuando se citan archivos; nada de pseudocontratos incompatibles con el repo; describir conductas observables antes de soluciones; evitar especificar cada línea de código; una decisión relevante debe poder entenderse sin conocer el chat.

### 3.6 Puerta de aprobación obligatoria

Una change pasa por `draft -> awaiting_approval -> approved` o vuelve a `draft` si hay comentarios.

La aprobación se registra **mediante operación explícita**:

```bash
factory design show CHG-0012
factory design approve CHG-0012
factory design reject CHG-0012 --reason "..."
```

**Interacción humana prevista**: `approve` mostrará el resumen de requisitos, rutas y huella exacta de los artefactos que se van a aprobar; requerirá confirmación interactiva en terminal/flujo humano y rechazará invocaciones no interactivas. La skill `factory-design` puede indicar cómo aprobar, **pero no llamará ella misma a `approve`**. Los procesos gestionados por Factory tampoco aprobarán sus propios diseños. La CLI no incluirá en V1 un `approve --yes` automático. En equipo, la prueba de aprobación podrá vincularse al revisor de un PR, según política del proyecto. Esta separación reduce errores accidentales, aunque una CLI local no constituye por sí sola una frontera de seguridad frente a un agente o proceso malicioso con acceso total a la máquina; las políticas del proveedor y permisos del SO deben mantenerse.

El guardado de aprobación requiere:

- ID de change, identidad local o identificador del revisor autorizado.
- Fecha UTC de aprobación y **hash SHA-256 canónico del conjunto de artefactos normativos** (proposal/specs/design, excluyendo `progress.md` y el estado mutable de tareas).
- Referencia Git al commit cuando exista; si no, una copia inmutable de los artefactos aprobados en el área runtime local.
- Registro de mecanismo `local` o adaptador del flujo corporativo (por ejemplo, PR revisada).
- Ausencia de preguntas bloqueantes no resueltas y validación estructural.

**Bloqueo efectivo**: `factory task claim`, `factory run` y la skill de implementación comprueban el hash y no inician trabajo si el diseño no está aprobado o ha cambiado. Esta garantía cubre los comandos gestionados por la Factory; no puede impedir que un usuario o agente modifique archivos manualmente fuera de ella. Los hooks compatibles pueden añadir controles adicionales.

**Diseños sin commit**: en modo personal puede aprobarse una snapshot local, que el Core facilitará como contexto inmutable al agente en otro worktree. Se recomendará su commit. En equipo, el perfil puede exigir que el diseño esté versionado y aprobado según la política Git/PR existente. Así un worktree no depende de documentos sin commit que solo existen en otro checkout.

**Cambio tras aprobar**: modificar cualquier artefacto normativo invalida la aprobación para tareas nuevas. Las ejecuciones en curso se marcan `requires_reassessment`; no se borran ni se modifican silenciosamente. Se solicita revisión del alcance y nueva aprobación si afecta a requisitos, decisiones o verificaciones.

**Fast path trivial**: se autoriza explícitamente una tarea con criterios mínimos sin `design.md` completo. El evento de autorización y motivo quedan registrados; nunca se usa de manera automática para eludir riesgos.

### 3.7 Del diseño a la planificación ejecutable

Tras aprobar:

1. El sistema evalúa si la implementación es una tarea indivisible o conviene separarla.
2. Si es sencilla, genera una task vinculada al diseño.
3. Si es compleja, el Planner (capacidad nativa o agente independiente) propone tareas con IDs, dependencias, pruebas y propiedad sugerida de módulos.
4. Se comprueba que la suma de tareas cubra cada `AC-xx` y que no exista ciclo de dependencias.
5. Se registran tareas en el backend configurado. Una tarea puede quedar `ready` cuando sus dependencias estén satisfechas.
6. **No es necesaria segunda aprobación del plan** si mantiene el alcance y las decisiones aprobadas. Toda modificación arquitectónica sustancial exige volver al diseño.

Las tareas son lo suficientemente pequeñas para poder verificar su cierre, pero no se dividen en microacciones sin valor independiente.

**Criterios de aceptación**: el diseño creado por Claude se puede aprobar y ejecutar con Codex sin chat original; un hash cambiado bloquea nuevas ejecuciones; el modo sin OpenSpec produce el mismo contrato; los requisitos tienen cobertura en tareas y verificaciones.


---

## 4. Pilar III — Gestión de tareas, flujo de agentes y orquestación ligera

### 4.1 Modelo de tarea normalizado

Cada tarea tendrá como mínimo este contrato de datos, sea cual sea el backend:

```yaml
id: CHG-0012-02
change_id: CHG-0012
title: Integrar reservas recurrentes con calendario
description: Comportamiento concreto que se implementará
design_digest: sha256:...
acceptance_ids: [AC-03, AC-04]
depends_on: [CHG-0012-01]
state: ready
risk: medium
assigned_to: null
run_id: null
branch: null
worktree: null
verification:
  commands: ["pytest tests/integration/test_calendar.py"]
source:
  kind: local                # local | github | external
  external_id: null
```

- `state` y `assigned_to` se gestionan por el tracker; las pruebas y evidencias por el Core.
- La referencia al diseño es obligatoria salvo *fast path* autorizado.
- No habrá `assigned_to` simultáneo para dos agentes escritores en una misma tarea.
- `run_id` identifica un intento concreto; una tarea puede tener más de un intento sin perder el historial.
- Las dependencias se expresan como IDs, no como frases; se validan antes de pasar a `ready`.
- `risk` se determina de forma explicable (seguridad, datos, alcance, usuario final, despliegue, etc.) y es modificable por el humano.

### 4.2 Estados diferenciados para cambios, tareas y ejecuciones

**Estados de una change**:

`idea -> researching -> draft -> awaiting_approval -> approved -> implementing -> completed -> archived`.

Excepciones: `rejected`, `on_hold`. Se puede volver de `awaiting_approval` a `draft`. Las tareas no pueden pasar a ejecución si la change no está aprobada.

**Estados de una task**:

| Estado | Significado | Siguientes habituales |
|---|---|---|
| `backlog` | Definida pero aún no ejecutable | `ready`, `cancelled` |
| `ready` | Aprobada, sin dependencias pendientes y disponible | `running`, `blocked`, `cancelled` |
| `running` | Un run tiene responsabilidad de ejecución | `review`, `blocked`, `interrupted` |
| `review` | Implementada, pendiente de verificaciones/revisión | `running`, `done`, `blocked` |
| `done` | Condiciones de cierre verificadas | Final; reabrible por nueva evidencia |
| `blocked` | Falta decisión, dependencia externa o condición de ejecución | `ready`, `running`, `cancelled` |
| `interrupted` | El intento dejó de ejecutar antes de terminar | `ready`, `running`, `cancelled` |
| `cancelled` | Trabajo abandonado explícitamente | Final salvo reapertura intencional |

El estado `ready` puede calcularse desde `backlog` + dependencias satisfechas + aprobación vigente. El tablero podrá visualizarlo como estado materializado para comodidad. No permitir marcar manualmente `ready` si quedan dependencias.

**Estado de una ejecución (run)**, distinto del estado de la task:

`created`, `starting`, `active`, `waiting_for_input`, `pause_requested`, `paused`, `finished`, `failed`, `interrupted`, `unknown`.

Una ejecución puede estar `unknown` por falta de señales sin implicar fallo. El dashboard no equiparará ausencia de actividad con interrupción confirmada.

### 4.3 Persistencia local y atomicidad

Para V1, implementar SQLite en `<git-common-dir>/factory/state.sqlite` con transacciones y migraciones de esquema sencillas. Debe incluir lógicamente las siguientes entidades:

- `changes`: id, proveedor de diseño, rutas, digest vigente, estado, revisión.
- `approvals`: change_id, digest, revisor, método, fecha, referencia Git, estado.
- `tasks`: id, change_id, estado, título, riesgo, criterios, asignación y origen externo.
- `dependencies`: task_id, prerequisite_id.
- `runs`: id, task_id, proveedor, modelo realmente usado (si se conoce), modo de observabilidad, timestamps, proceso/sesión/worktree, resultado.
- `events`: evento inmutable con secuencia, hora, actor, tipo y metadatos reducidos.
- `verifications`: tarea, ejecución, comando, código de salida, duración y evidencia.
- `worktree_links`: tarea, rama, ruta, base ref, commit inicial y marca de propiedad.

SQLite es el estado autoritativo **para el modo local**. Las modificaciones se realizan mediante comandos del Core y eventos auditables; no se editan tablas a mano desde las skills.

**Adquisición de tareas**: operación atómica de *claim*: verificar `ready`, no bloqueos, aprobación vigente, y reservar la tarea/crear el run en una única transacción. Si otro proceso se adelantó, devolver conflicto claro. Evitar duplicidades si la llamada se reintenta accidentalmente usando `request_id` opcional.

**Concurrencia**: habilitar transacciones apropiadas y `busy_timeout`; prohibir dos claims activos sobre el mismo ID y validar en pruebas con procesos simultáneos. El `run_id` será único por intento.

### 4.4 Backend colaborativo

Una interfaz común `TaskBackend` deberá exponer, como mínimo:

- `list(filters)`, `get(id)`, `create(task)`, `claim(id, owner)`, `transition(id, from, to, reason)`, `add_note(id, note)`, `link_artifact(id, path_or_url)` y `sync()`.
- `LocalBackend`: SQLite del clon.
- `GitHubBackend` opcional: issue/PR como registro compartido de estado, responsable y referencias; mantener datos de ejecución exclusivamente locales cuando no convenga publicarlos.
- Otros trackers fuera de V1, diseñados para poder incorporarse sin modificar skills.

**Regla crítica de sincronización**: con un backend remoto no existen dos autoridades equivalentes. El tracker remoto manda sobre el estado compartido; SQLite es caché/supervisión local. Actualizar mediante API/CLI con control de conflictos cuando sea posible; si no hay red, indicar `sync_pending`, nunca inventar que la tarea remota se actualizó. En caso de divergencia entre estado local y remoto, mostrar conflicto, no sobrescribirlo automáticamente.

El diseño y decisiones técnicas permanentes siguen en archivos versionados del repositorio. No introducir transcripciones completas de agentes en GitHub.

### 4.5 Comandos de tareas

Superficie funcional propuesta (CLI exacta a conservar durante V1):

```bash
factory task list [--state ready|running|review|blocked|...]
factory task show CHG-0012-02
factory task ready
factory task claim CHG-0012-02 --provider codex
factory task checkpoint CHG-0012-02 --done "..." --next "..."
factory task note CHG-0012-02 --text "Revisar caso X"
factory task block CHG-0012-02 --reason "..."
factory task interrupt CHG-0012-02 --reason "..."
factory task resume CHG-0012-02
factory task verify CHG-0012-02
factory task finish CHG-0012-02
factory status [--json]
```

`task finish` se niega si falta verificación exigida o revisión requerida. El humano autorizado puede registrar una excepción explícita y trazada para una prueba no ejecutable, **sin marcarla falsamente como aprobada**.

Las skills invocarán estos mismos comandos de manera estructurada. No habrá un segundo motor de estados oculto dentro de los prompts.

### 4.6 Selección del workflow: política adaptativa

| Perfil de tarea | Flujo | Condiciones |
|---|---|---|
| Trivial / bajo riesgo | `Coder -> checks` | Cambio muy localizado y aceptaciones claras; sin Reviewer separado. |
| Normal | `Coder (con plan interno) -> checks -> Reviewer` | Nueva lógica, interfaz, integración o bug significativo. |
| Compleja / alto riesgo | `Planner -> Coders -> checks -> Reviewer` | Varias dependencias, arquitectura, seguridad, concurrencia, datos o refactorización amplia. |

El **diseño aprobado es previo al workflow de implementación** salvo fast path. El Planner, si existe, organiza tareas aprobadas; no reemplaza el Research/Design ni puede introducir cambios de arquitectura sin señalarlo.

Reglas adicionales:

- Coder trabaja una unidad verificable, no toda una épica inabarcable.
- Un Reviewer independiente recibe diseño aprobado, criterios, diff, evidencias y contexto pertinente **sin heredar necesariamente la conversación del Coder**.
- Máximo inicial de **dos ciclos correctivos** tras hallazgos del Reviewer; si no converge, marcar bloqueo o pedir revisión humana.
- Los hallazgos se clasifican por severidad y deben referirse a un defecto concreto. Estilo subjetivo no bloquea por defecto.
- Si falla una prueba relevante, `done` está prohibido.
- La Factory puede recomendar otro modelo, pero nunca debe ocultar cuál ejecutó realmente.

### 4.7 Proveedores, modelos y esfuerzo

No codificar identificadores de modelos como verdad permanente. Los alias, catálogo y compatibilidad se obtienen de las herramientas instaladas cuando sea posible.

La configuración distingue roles lógicos:

- `research_design`: modelo de gran capacidad, esfuerzo adecuado al riesgo.
- `planner`: modelo competente en descomposición y dependencias.
- `coder`: modelo equilibrado, salvo tarea muy difícil.
- `reviewer`: contexto separado, opcionalmente otro proveedor.
- `helper`: modelo más rápido para exploraciones menores.

Defaults funcionales **no vinculantes**: Claude para diseño, Codex para implementación y Claude/Codex para revisión cruzada según disponibilidad. Todos deben ser sobrescribibles por tarea o persona. En caso de modelo no disponible, preguntar o usar un fallback **explícitamente permitido**; nunca sustituir silenciosamente.

No se obliga a consumir API por clave: pueden utilizarse sesiones de los clientes autenticados mediante sus licencias y herramientas oficiales. El alcance de cuotas y automatización dependerá de los permisos reales del usuario.

### 4.8 Skills mínimas de V1

La Factory tendrá inicialmente **tres skills** propias y reutilizables:

1. **`factory-design`**: investigar, generar/actualizar diseño, registrar change y solicitar aprobación.
2. **`factory-implement`**: leer diseño aprobado, seleccionar o reclamar tarea, activar workflow adecuado, generar checkpoints, ejecutar tests y enviar a revisión.
3. **`factory-resume`**: inspeccionar estado, diff, logs pertinentes y último `progress.md`, presentar diagnóstico y reanudar tarea interrumpida tras acción explícita del usuario.

El Reviewer independiente podrá ejecutarse con una capacidad nativa de Claude/Codex invocada desde `factory-implement`, sin introducir desde el inicio una cuarta skill permanente. Si las pruebas indican necesidad, se añade `factory-review` posteriormente.

Las skills deben seguir el formato `SKILL.md` con descripción precisa; el contenido común vive en plantillas de Factory y se genera para `.agents/skills/` y `.claude/skills/` sin duplicar manualmente la lógica. **No usar enlaces simbólicos a rutas externas** como requisito de funcionamiento en proyectos profesionales.

### 4.9 Qué significa exactamente «orquestar» en V1

La orquestación ligera del Core es una **máquina de estados con acciones controladas**:

1. Elegir tarea ejecutable.
2. Verificar aprobación, dependencias, riesgo y asignación.
3. Vincular rama y worktree.
4. Elegir proveedor/rol, ejecutarlo o dar instrucciones al agente ya abierto.
5. Recoger resultados de tests, progreso y revisión.
6. Transicionar el estado o detenerse con motivo claro.
7. Entregar el resultado y esperar integración manual.

Dos modalidades complementarias:

- **Modo conversación (principal)**: usuario trabaja dentro del chat de la extensión VS Code o de Orca y usa skills. La CLI registra tareas y checkpoints; la observación detallada depende de hooks/eventos disponibles. El orquestador no puede leer siempre el estado interno de una sesión manual.
- **Modo gestionado (opcional)**: `factory run <task> --provider claude|codex` lanza un proceso mediante la interfaz programática disponible, registra PID/sesión y salida de estado, y permite supervisión más fiable. El usuario puede alternarlo con el modo chat, sin prometer que sean la misma conversación.

**Orca** será un adaptador opcional para leer worktrees/sesiones y aprovechar su coordinación nativa cuando sea estable y esté disponible. No será dependencia del Core. **VS Code** seguirá funcionando con Git, CLI, skills y hooks.

No se programará una cadena automática multiagente extensa si el proveedor o el IDE ya ofrece mecanismos adecuados; se aprovecharán sus capacidades nativas y se instrumentarán solo los pasos esenciales.

### 4.10 Commits, seguridad de ejecución y entrega

- Crear worktree y rama no equivale a fusionar ni desplegar.
- El agente puede crear commits si se le permite en la tarea o el usuario lo solicita. Guardar hashes de commits en el run.
- **Sin `git push`, `merge`, `rebase` destructivo, borrado de ramas o despliegue automático por defecto**. Esas operaciones son responsabilidad del usuario en V1.
- Un cambio «terminado» en Factory significa implementado y verificado **en su rama**, no necesariamente integrado en la rama principal.
- En proyectos profesionales, pruebas CI, revisión de PR y protecciones de ramas existentes prevalecen sobre la revisión local del agente.
- Se debe informar si se hicieron cambios no solicitados o fuera de alcance, y no ocultar pruebas no ejecutadas.

### 4.11 Criterios de cierre de una tarea

Para pasar de `review` a `done`, verificar:

1. Todos los criterios de aceptación vinculados tienen una evidencia asociada: test superado, verificación manual registrada o excepción justificada.
2. Las pruebas exigidas se han ejecutado y no presentan fallos relevantes sin resolver.
3. El diff corresponde al alcance y no contiene cambios ajenos sin explicación.
4. La revisión independiente se completó si la política la exige.
5. Hay registro de resultado, decisiones y bloqueos restantes (si los hubiera).
6. Se conoce la rama/worktree y el último commit, o se declara explícitamente que quedan cambios sin confirmar.
7. La memoria duradera se ha **evaluado** para actualización (no significa obligar a editarla).
8. La tarea no tiene dependencias sin satisfacer ni diseño invalidado.

Un modelo no puede «autoaprobar» criterios manuales inventando evidencia.

---

## 5. Git Worktrees, paralelismo e integración

### 5.1 Creación y ownership

Al reclamar una tarea de escritura:

1. Verificar repositorio Git válido, rama base y conflictos con otras tareas activas.
2. Determinar nombre seguro, por ejemplo `factory/CHG-0012-02-calendar`.
3. Crear rama + worktree con Git nativo, o delegar en Orca si la sesión lo gestiona y registrar el resultado.
4. Verificar worktree sin errores y asociar su ruta al `run_id`.
5. Seleccionar un responsable de escritura, `provider/session` o humano. Los agentes auxiliares de solo lectura no necesitan worktree propio.
6. Registrar commit base y comandos seguros de setup del proyecto. **No ejecutar setup arbitrario por el simple hecho de que aparezca en un repo desconocido**; se necesita confianza/autorización.

V1 sugiere worktrees fuera del checkout principal (ruta local configurable). El trabajo en paralelo no modifica el checkout del usuario sin que este lo solicite.

### 5.2 Dependencias y conflictos

- Dos tareas independientes pueden ejecutarse en worktrees distintos.
- Tareas dependientes se desbloquean solo cuando el estado prerequisito configurado se cumple (`done` en rama o integración, según política). No asumir que estar `done` implica que el código ya existe en la rama base de otra tarea.
- **Regla de integración**: si una tarea depende del código de otra todavía no integrado, arrancará desde la rama/commit de la dependencia o esperará su integración explícita. El Planner debe señalarlo.
- Si dos tareas modifican rutas o componentes de alto solapamiento, advertir del riesgo antes de ejecutarlas paralelamente; no asumir que worktrees eliminan conflictos de merge.
- Contenedores, puertos, bases de datos locales y credenciales pueden compartirse aunque el código esté aislado. La Factory debe ofrecer aislamiento configurable de recursos por worktree si el proyecto lo necesita; no introducirlo de forma universal.

### 5.3 Finalización y limpieza

- El agente entrega diff, commit(s), tests, revisión y reporte de los cambios.
- El worktree permanece disponible para revisión y commits.
- En V1 **no se elimina automáticamente ningún worktree ni rama**.
- Si posteriormente se implementa limpieza: exigir confirmación y verificar cambios sin confirmar, commits no integrados, procesos activos y vinculación con tareas abiertas.
- La integración por PR, cherry-pick, rebase o merge sigue siendo manual o parte de procedimientos aprobados del proyecto.

### 5.4 Comandos mínimos

```bash
factory worktree create CHG-0012-02
factory worktree list
factory worktree show CHG-0012-02
```

No crear una CLI que replique cada opción de Git. Para operaciones avanzadas, utilizar `git worktree` y los controles de Orca/VS Code.

---

## 6. Pilar V — Memoria y contexto

### 6.1 Niveles de contexto

| Nivel | Contenido | Fuente y carga |
|---|---|---|
| 1. Instrucciones globales del proyecto | Qué hace el repo, comandos, reglas críticas, mapa de documentación | `AGENTS.md`, breve, inicio de sesión |
| 2. Conocimiento duradero | Arquitectura, decisiones, contratos y convenciones por área | `docs/`, lectura solo cuando sea relevante |
| 3. Memoria de change/task | Diseño aprobado, criterios, eventos, checkpoints, archivos afectados | Resolver mediante ID de tarea al comenzar o reanudar |
| 4. Aprendizajes reutilizables | Errores repetidos, decisiones nuevas, cambios de arquitectura | Propuestas de actualización revisables, no incorporación masiva |

### 6.2 Contrato de `AGENTS.md`

Se generará o adaptará un archivo corto con:

- propósito y estructura principal del proyecto;
- comandos verificados de instalación, build, test y lint;
- reglas de seguridad y edición que siempre se apliquen;
- localización de arquitectura, decisiones y diseños;
- instrucciones para usar skills y **CLI de Factory** cuando corresponda;
- obligación de no declarar `done` sin evidencias y de registrar checkpoints.

Objetivo orientativo: 60–120 líneas o menos si el proyecto es sencillo; no imponer un límite que obligue a ocultar información crítica. No copiar diseños completos en las instrucciones.

`AGENTS.md` será la fuente común. Claude Code podrá leerlo cuando la versión/configuración lo soporte. Si el proyecto requiere `CLAUDE.md`, mantener uno mínimo que enlace/importa las instrucciones comunes, respetando un `CLAUDE.md` preexistente y evitando contradicciones. El `doctor` debe comprobar cuál está tomando realmente cada cliente.

### 6.3 Documentación duradera

- Crear `docs/architecture.md` solo si la arquitectura tiene contenido estable que no se deduce fácilmente de los archivos.
- Crear `docs/decisions.md` o ADR específicos solo cuando existan decisiones importantes. Cada decisión: contexto, alternativas, decisión, consecuencias y fecha.
- Documentación de módulos, contratos o reglas por carpeta cuando un monorepo lo justifique.
- Priorizar referencias a código y configuración como fuente actual; no duplicar READMEs ni documentación corporativa preexistente.
- No crear un Memory Manager separado para cada run; tras implementar, la skill **evalúa si existe conocimiento nuevo permanente** y prepara el cambio mínimo.
- En modo profesional, los cambios de instrucciones y arquitectura se someten al proceso normal de revisión del repositorio.

### 6.4 `progress.md`: contexto para reanudar, no tracker duplicado

Cada tarea con ejecución activa tendrá un archivo operativo:

`<git-common-dir>/factory/tasks/<task-id>/progress.md`

Contenido generado a partir de eventos + resumen consolidado de agente:

```markdown
# CHG-0012-02 — Integración calendario

Última actualización: 2026-10-16T15:30:00Z
Run: RUN-0037
Estado: running
Worktree: /ruta/local/worktrees/CHG-0012-02
Rama: factory/CHG-0012-02-calendar

## Hecho y comprobado
- API implementada; tests unitarios correctos.

## Pendiente
- Pruebas de integración del calendario.
- AC-04 sin verificar.

## Cambios relevantes
- src/calendar/service.py
- tests/integration/test_calendar.py

## Bloqueos o riesgos
- Ninguno.

## Próxima acción
- Ejecutar integración, comprobar idempotencia y revisar diff.
```

El encabezado operativo se construye desde el Core. El agente aporta el resumen semántico y las evidencias. No mantener manualmente un segundo estado independiente en el Markdown: es una **vista de recuperación** del run.

**Cuándo actualizar**: inicio, después de una unidad significativa, antes de solicitar aprobación o pausa, al superar una verificación relevante, al bloquearse, al terminar y antes de una compactación o cierre cuando el hook lo permita. No después de cada tool call ni cada línea de código.

### 6.5 Compactación e higiene

- No persistir chats completos ni logs extensos como memoria del modelo.
- Capacidad para resumir un progreso demasiado largo dejando: decisiones, resultado verificado, bloqueos y siguiente acción.
- Los eventos y logs de runtime tienen retención local configurable; los artefactos duraderos permanecen en Git.
- Al reanudar, cargar primero encabezado de tarea, diseño, `progress.md`, diff y tests; consultar documentación secundaria solo si se necesita.
- No almacenar rutas privadas, credenciales, datos de clientes o contenido confidencial en documentos compartidos.

**Criterios de aceptación**: un agente de otro proveedor puede continuar con el diseño y el estado de una tarea sin acceder al chat anterior; al crecer el proyecto, el contexto inicial no crece proporcionalmente a todo el historial; no se crean decisiones contradictorias por defecto.


---

## 7. Pilar IV — Seguimiento de ejecuciones, interrupciones y recuperación

### 7.1 Dos fuentes de información que no deben confundirse

**Progreso semántico**: lo que el agente ha terminado o cree que falta, registrado mediante `factory task checkpoint` y evidencias. Puede estar incompleto o ser incorrecto.

**Actividad observada**: proceso que sigue vivo, eventos/hooks del proveedor, mensajes del sistema de ejecución, estado de Orca y resultados de pruebas. Son señales técnicas de distinta fiabilidad.

La Factory debe mostrar ambas por separado. `task=running` no garantiza que una sesión siga viva; `process=alive` no demuestra que un AC esté completado.

### 7.2 Niveles de observabilidad

El Core registrará el origen y calidad de la observación de cada run:

| Nivel | Qué conocemos | Qué podemos afirmar |
|---|---|---|
| `managed` | Proceso iniciado desde Factory, salida y finalización observables | Vivo/finalizado/fallido con confianza del proceso |
| `native` | Eventos de Orca o integración de proveedor documentada | Estado publicado por ese proveedor en el instante observado |
| `hook` | Hooks instalados y aceptados por el cliente | Eventos conocidos; posible pérdida de eventos |
| `self_reported` | Checkpoints que ejecuta el propio agente desde chat | Último progreso declarado, no salud de sesión |
| `unknown` | No hay señales suficientes | No afirmar que el agente sigue trabajando o está colgado |

**Regla de UI**: jamás representar como «Running (confirmado)» una sesión cuya única evidencia sea un checkpoint antiguo. Mostrar `último progreso` y `actividad: desconocida` cuando corresponda.

### 7.3 Observación desde VS Code, Orca y CLI

- **VS Code chat nativo**: skills llaman a `factory task...`. Cuando el proveedor permita hooks de sesión/herramientas, se pueden instalar para transmitir eventos ligeros. No prometer control del proceso de una extensión que no exponga API pública adecuada.
- **Orca**: usar su CLI para consultar sesiones/worktrees y, opcionalmente, usar su infraestructura nativa de workers; el adaptador debe detectar versiones/capacidades y no parsear pantallas mediante heurísticas frágiles.
- **`factory run`**: el Core inicia un proceso hijo soportado por el proveedor, registra su ciclo de vida, salida estructurada si existe y finalización. **No debe desactivar automáticamente sandbox ni políticas de aprobación** para evitar fricción.
- **Hooks**: eventos útiles como inicio/fin, parada, interrupción y subagentes pueden enriquecer el estado. Hooks opcionales, pequeños, rápidos, revisables y compatibles con el mecanismo de confianza de cada cliente. No bloquear la edición porque falló el sistema de telemetría.

En una sesión de chat que ya está abierta y no fue lanzada por Factory, la Factory puede conocer checkpoints y algunos eventos, pero **no está garantizado** que pueda suspenderla, recuperar su ID o detectar un cuelgue real.

### 7.4 Checkpoints y eventos

Cada checkpoint debe incluir:

```json
{
  "event_type": "task.checkpoint",
  "task_id": "CHG-0012-02",
  "run_id": "RUN-0037",
  "actor": "codex",
  "timestamp_utc": "2026-10-16T15:30:00Z",
  "summary": "Implementado el adaptador de calendario",
  "completed": ["Modelo y validaciones"],
  "pending": ["AC-04", "Pruebas de integración"],
  "next_action": "Ejecutar tests de integración",
  "evidence_refs": ["git:abc123", "test:RUN-0037:integration"]
}
```

La validación rechaza IDs inexistentes, transiciones ilegales, eventos sin referencia al run y payloads desproporcionados. Los campos libres se tratan como texto no confiable para evitar comandos o HTML ejecutables.

Al registrar un evento:
1. validar y anexar de forma transaccional a SQLite;
2. actualizar el resumen `progress.md` de forma atómica (`write-temp` + replace);
3. notificar al dashboard en su siguiente refresco;
4. intentar sincronizar estado resumido con tracker remoto si está configurado.

Si falla el renderizado de `progress.md`, el evento de SQLite sigue siendo válido y la vista puede regenerarse.

### 7.5 Detector de inactividad y semántica de bloqueo

- Configurar umbral inicial de **10 minutos sin eventos significativos** únicamente para mostrar un aviso de «sin actualización reciente», no para declarar caída ni terminar procesos.
- Distinguir `waiting_for_input` y `paused` de `stale`. Una sesión que espera respuesta no está colgada.
- Si un proceso gestionado terminó con error/senal, registrar estado confirmado `failed` o `interrupted`.
- Si la aplicación desaparece y el PID ya no existe, el siguiente inicio del Core reconcilia el registro y muestra `interrupted`, preservando datos.
- Si el run no era gestionado y el último checkpoint envejeció, mostrar `unknown/stale` y ofrecer inspección manual, no reiniciar automáticamente.
- Si un proceso fue relanzado fuera de Factory, permitir **reconciliación explícita** con un nuevo run o vínculo de sesión, no reutilizar IDs de manera ciega.

### 7.6 Cambiar instrucciones durante una ejecución

Necesidad funcional: poder introducir un comentario, pausar o modificar el rumbo al detectar un problema.

- `factory task note <id> --text "..."`: añade nota operativa con autor/fecha; una nota nueva se ve en el dashboard.
- `factory task pause <id>`: deja una solicitud persistente; agentes cooperativos deben revisarla antes del siguiente checkpoint/acción significativa.
- En ejecución gestionada, la CLI puede intentar una interrupción segura **solo tras orden explícita** y guardando estado; en chat manual, no prometer una interrupción remota garantizada.
- `factory task resume <id>`: tras una pausa, permite reanudar; el agente debe releer notas y estado.
- Si la nueva instrucción **cambia requisitos o arquitectura**, no se aplica silenciosamente: marcar `requires_reassessment`, ajustar el diseño, volver a aprobar y reconsiderar tareas pendientes.
- Nunca borrar el trabajo ya realizado al cambiar el alcance.

### 7.7 Recuperación manual V1

Contrato de la skill `factory-resume` y del comando equivalente:

1. Localizar tarea, último run, rama/worktree y versión del diseño.
2. Comprobar si hay ejecución viva o pendiente de input; si existe, no iniciar otra que pueda escribir en el mismo worktree.
3. Inspeccionar `git status`, commits, cambios sin confirmar y conflictos.
4. Leer último `progress.md`, eventos, pruebas y errores; no fiarse ciegamente del resumen.
5. Comparar criterios del diseño con evidencias ya existentes y clasificar lo que falta.
6. Proponer al usuario: reanudar en sesión existente cuando sea posible, iniciar sesión nueva en el mismo worktree, o recuperar desde una rama concreta.
7. Tras decisión explícita, crear **nuevo run** vinculado a la misma tarea si hace falta; conservar histórico de intentos.
8. Inyectar un contexto de reanudación compacto al proveedor elegido; no volver a ejecutar cambios destructivos ni reinstalar dependencias por defecto.
9. Registrar el nuevo estado y continuar con checkpoints.

**No se harán reintentos automáticos en V1.** El Core puede sugerir el punto seguro de reanudación, pero no declarar una acción idempotente sin evidencia.

### 7.8 Comandos mínimos de supervisión

```bash
factory status
factory status --json
factory task note CHG-0012-02 --text "Verificar carrera de escrituras"
factory task pause CHG-0012-02
factory task resume CHG-0012-02
factory task interrupt CHG-0012-02 --reason "El proceso terminó"
factory recover CHG-0012-02
```

La CLI deberá resolver duplicaciones de verbos: `task resume` efectúa transición de estado; `recover` inspecciona y prepara un nuevo run. El comando interactivo puede invocar ambos, pero sus semánticas no se confunden.

### 7.9 Requisitos verificables de seguimiento

- Dos agentes en ramas distintas actualizan estados sin sobrescribirse.
- Un agente desaparece inesperadamente y conserva diff, checkpoints, pruebas y siguiente acción.
- Tras reiniciar VS Code u Orca, la Factory sigue mostrando el último estado conocido.
- Un run sin eventos durante 10 minutos no se marca falsamente como muerto.
- Un cambio solicitado durante ejecución queda visible y debe ser considerado antes de proseguir por el flujo gestionado.
- Una tarea marcada `interrupted` no se reanuda automáticamente.

---

## 8. Dashboard HTML local actualizado

### 8.1 Objetivo

Dar una vista simple y útil del proyecto: **qué está disponible, qué se está diseñando, qué se está implementando, con qué agente, en qué rama, cuánto lleva sin actualización y qué necesita atención**.

El dashboard **no reemplaza** a Orca. Orca muestra principalmente sesiones/worktrees; Factory agrupa además diseño, aprobación, criterios, dependencias y estado persistente, y funciona también cuando se utiliza VS Code.

### 8.2 Arquitectura y ejecución

Propuesta V1:
- Servidor HTTP local mínimo implementado con la biblioteca estándar de Python.
- Escucha exclusivamente en `127.0.0.1` y puerto libre o configurable.
- `GET /`: HTML/CSS/JS estático empaquetado.
- `GET /api/status`: snapshot JSON obtenido del Core.
- `GET /api/task/<id>`: detalle de tarea y referencias de lectura, sin logs sensibles.
- Cliente JavaScript actualiza datos mediante polling cada **3–5 segundos**; sin WebSocket, framework frontend, base de datos adicional ni servicio externo.
- `factory dashboard` inicia/abre el servidor local y muestra URL, proceso y forma de detenerlo.
- Cuando se cierre el servidor, el progreso permanece en SQLite; abrir de nuevo no pierde estado.

El servidor será **de solo lectura** en V1. Botones para mutar estado y edición interactiva se aplazan. Los comandos `factory task ...` permiten intervenir desde un terminal o una skill.

### 8.3 Información presentada

**Cabecera**: nombre de repo, rama base detectada, perfil, tracker, fecha/hora de última sincronización y avisos de integraciones ausentes.

**Resumen**: contadores de `awaiting_approval`, `ready`, `running`, `review`, `blocked`, `interrupted`, sin confundir tareas y runs.

**Vista principal de tareas**:
- ID, título, change asociada y diseño aprobado/pendiente.
- Estado de tarea y de última ejecución.
- Proveedor/agente, modelo si se conoce y nivel de observabilidad.
- Rama/worktree, último checkpoint y antigüedad.
- Progreso resumido, siguiente acción, bloqueo e indicadores de tests/revisión.
- Dependencias que impiden comenzar.
- Filtros por estado, agente, rama, change y actividad.

**Detalle por tarea**:
- objetivo/AC, referencia al diseño, versión de aprobación;
- línea temporal compacta de eventos significativos;
- evidencias de verificación (comando, estado y fecha);
- notas y solicitudes de pausa/cambio;
- links/rutas a diff, worktree, PR/Issue si existe;
- botón **copiar comando** de reanudación o inspección, no botón que ejecute sin control.

**Señales**: `confirmed_running`, `waiting_input`, `recent_checkpoint`, `stale`, `unknown`, `interrupted`, con iconos/leyendas claros y tiempos reales observados. No inventar porcentajes de avance basados en heurística de texto; opcionalmente mostrar AC verificados / AC totales.

### 8.4 Interfaz, seguridad y performance

- Diseño limpio, responsive, tablas compactas y acceso rápido al detalle; usable en navegadores de escritorio.
- El dashboard debe seguir abriendo sin Orca ni GitHub.
- Sanitizar todo texto mostrado; no insertar Markdown de tareas como HTML sin escape.
- No servir rutas arbitrarias, ni exponer `.env`, tokens, transcripciones o directorios personales.
- Sin CORS abierto ni binding a `0.0.0.0` por defecto; no exponer servidor a red corporativa.
- Aplicar cabeceras de seguridad razonables y evitar caché de datos operativos sensibles.
- Las peticiones solo leen una snapshot consistente; no hacer llamadas costosas a modelos ni Git en cada refresco.
- Objetivo de rendimiento de aceptación: 100 tareas con refresco fluido en un portátil normal, medido con prueba sintética y sin consultas bloqueantes.

### 8.5 Reporte exportable: fuera de V1

No se necesita otro generador de informes al comienzo. El HTML local actualizado es el entregable. Una exportación estática para compartir capturas o reportes podrá incorporarse más adelante, cuidando eliminar rutas y datos sensibles.

### 8.6 Comandos

```bash
factory dashboard
factory dashboard --port 8765
factory status --json
```

El modo `dashboard` deberá informar si el puerto está ocupado, permitir elegir otro y terminar limpiamente con Ctrl+C.

---

## 9. Experiencia cotidiana en VS Code, Orca y terminal

### 9.1 VS Code — flujo principal por chat

1. Abrir repositorio ya inicializado.
2. Abrir extensión Claude Code o Codex instalada.
3. Invocar `/factory-design ...` o `$factory-design ...`; el agente crea los documentos y el Core registra la change.
4. Revisar `design.md` en el editor y aprobar con `factory design approve <id>` (la skill puede proponer abrir un terminal; el usuario confirma).
5. Invocar `/factory-implement <task-id>` o `$factory-implement <task-id>`.
6. La skill valida aprobación y dependencias, y utiliza `factory task claim` / `factory worktree create` cuando se necesita rama aislada.
7. Abrir el worktree en una nueva ventana/terminal del editor y ejecutar la implementación con el proveedor elegido.
8. Consultar `factory dashboard` en el navegador; verificar progreso/checkpoints y usar `factory-resume` cuando sea necesario.
9. Revisar diff, hacer commits, resolver integración/push manualmente.

En V1 la skill puede necesitar que el usuario cambie al worktree o abra un terminal; **no prometer un traspaso automático de contexto entre dos chats distintos de VS Code si las extensiones no exponen la operación**.

### 9.2 Orca — mismo contrato, más asistencia visual

1. Abrir el repositorio y usar su Chat UI o terminal.
2. Invocar las mismas skills por proveedor.
3. Si se decide implementar, crear worktree desde Orca o la CLI; Factory registra su vinculación con la tarea.
4. Ejecutar el agente en ese workspace y revisar su diff/sesión desde Orca.
5. Dashboard Factory ofrece la vista transversal de tareas/diseños además de las sesiones nativas.
6. Si Orca no está disponible, Git + CLI hacen exactamente el mismo trabajo esencial.

No mantener una segunda copia de worktrees ni tareas nativas de Orca si puede leerse mediante su CLI. Un adaptador Orca comprobará qué comandos/capacidades expone la versión instalada.

### 9.3 Terminal — automatización explícita

Se utilizará para:
- instalación y diagnóstico;
- aprobación/operaciones del Core;
- consulta de estados;
- ejecución gestionada opcional cuando se necesite monitorización del proceso;
- dashboard;
- mantenimiento de Git.

Ejemplo de flujo **ilustrativo de la CLI Factory propuesta**, no de comandos existentes hoy:

```bash
factory doctor
factory init --profile personal
# Desde el chat: /factory-design "Añadir reservas recurrentes"
factory design show CHG-0012
factory design approve CHG-0012
factory task ready
factory worktree create CHG-0012-01
# Desde un agente: /factory-implement CHG-0012-01
factory dashboard
factory status
```

### 9.4 Compatibilidad de skills

Los directorios `.claude/skills/...` y `.agents/skills/...` contienen envoltorios adaptados a las convenciones de cada cliente, pero ambos llaman a la misma CLI y cumplen el mismo contrato semántico.

**Alcance V1**: portátil en versiones probadas de Claude Code y Codex, con pruebas reales en extensiones VS Code, CLI y Orca. No prometer soporte automático para todas las versiones futuras sin `doctor` y pruebas de compatibilidad.

---

## 10. GitHub y entornos colaborativos

### 10.1 Integración GitHub opcional

En caso de elegirse `tasks.backend = "github"`:

- Detectar `gh`, sesión autenticada y repositorio remoto sin exponer tokens.
- Crear o vincular Issues a tasks locales; manejar sus estados y responsables mediante convenciones configurables del repositorio.
- Añadir referencias a change, diseño, rama, commit y PR.
- Registrar comentarios resumidos de progreso solo si el usuario/equipo lo permite.
- Consultar estado de PR/CI cuando haya PR, sin simular aprobaciones inexistentes.
- No crear Issues para cada microcheckpoint; sincronizar cambios significativos.
- Los cambios remotos se realizan con permisos y controles del usuario autenticado.
- Trabajar offline en modo local y dejar una cola de operaciones pendientes para reconciliar, mostrando conflictos antes de aplicar sobre estado remoto cambiado.

La elección de labels/estados compartidos se mapea por configuración. No asumir que todas las empresas utilizan el mismo Project board o los mismos nombres de etiquetas.

### 10.2 Conectores extra

V1 solo requiere detección y contratos, no integración completa con Slack, Drive, Jira, Linear, Azure DevOps, MCP remoto, etc. Añadir un conector cuando exista una necesidad real y permisos adecuados.

Los MCP pueden ser útiles para **lectura de documentación y herramientas corporativas**, pero cada proyecto elige cuál instalar. La Factory no habilitará conectores de forma global sin revisión de permisos.

### 10.3 Participación humana en el equipo

- Distintas personas pueden usar Claude o Codex según su licencia.
- Las reglas comunes se versionan; preferencias personales de modelo, binarios y rutas permanecen locales.
- El tracker del equipo muestra propietario y estado compartido; el dashboard local muestra los trabajos que ejecuta esta máquina, junto con tareas remotas cuando el adaptador lo permita.
- El registro de aprobación puede ser local o apoyarse en revisión de PR de diseño si el proyecto lo exige.
- El Core no salta branch protection, CODEOWNERS, CI ni revisiones requeridas.
- No ejecutar comandos de setup o hooks de un repositorio recién clonado antes de revisarlos.

---

## 11. Configuración y contratos estables de interoperabilidad

### 11.1 Ejemplo de `.factory/config.toml` compartido

Los nombres de campos constituyen **diseño de nuestro producto**, no opciones nativas de Claude/Codex/Orca:

```toml
schema_version = 1
profile = "personal"                 # personal | team

[planning]
provider = "openspec"               # openspec | builtin
default_depth = "adaptive"          # adaptive | compact | full
require_approval = true
allow_trivial_fast_path = true

[tasks]
backend = "local"                   # local | github
default_risk = "medium"

[workflow]
mode = "adaptive"                   # adaptive | simple | standard | complex
reviewer_on_normal = true
max_review_fix_rounds = 2
parallel_writers = 2

[git]
base_ref = "auto"                    # resolución segura desde el repo
branch_prefix = "factory/"
create_worktree_on_run = true
allow_commits = true
auto_push = false
auto_merge = false
auto_cleanup = false

[observability]
stale_after_minutes = 10
dashboard_refresh_seconds = 4
enable_optional_hooks = false

[dashboard]
host = "127.0.0.1"
port = 0                            # asignar puerto libre
read_only = true

[agents]
design_provider = "claude"
implementation_provider = "codex"
review_provider = "claude"
allow_provider_override = true
```

**Configuración local no versionada** en `<git-common-dir>/factory/local.toml` para rutas absolutas, selección de modelos disponibles, preferencias de esfuerzo, puerto fijo, límites locales y ejecutables personalizados. Nunca almacenar aquí credenciales si ya las gestiona el proveedor; la Factory solo utiliza los mecanismos de autenticación existentes.

Orden efectivo: políticas de la organización + configuración del repositorio + preferencias locales + overrides explícitos permitidos. Los campos de seguridad corporativa no se relajan mediante overrides.

La validación rechaza valores desconocidos cuando afecten al Core; para cambios de versión existe migración explícita de `schema_version`. `factory doctor --json` incluye configuración efectiva con valores sensibles omitidos.

### 11.2 Contrato de ejecución común

No importa qué proveedor implemente. Toda ejecución normalizada deberá entregar:

```json
{
  "run_id": "RUN-0037",
  "task_id": "CHG-0012-02",
  "design_digest": "sha256:...",
  "provider": "codex",
  "model": "id-real-si-se-conoce",
  "observability": "self_reported",
  "branch": "factory/CHG-0012-02-calendar",
  "worktree": "/ruta/local/...",
  "result": "needs_review",
  "changed_files": ["src/calendar/service.py"],
  "commits": ["abc123"],
  "checks": [
    {"name": "integration", "status": "passed", "evidence_id": "EV-019"}
  ],
  "acceptance": [
    {"id": "AC-03", "status": "verified", "evidence_id": "EV-019"},
    {"id": "AC-04", "status": "pending", "evidence_id": null}
  ],
  "next_action": "Revisar AC-04"
}
```

El ejemplo **no permite declarar la tarea `done`** porque queda AC-04 pendiente. `model` puede ser `null` cuando la extensión no lo expone; no inventar un modelo por defecto.

### 11.3 Contratos entre comandos y skills

- Los comandos de Factory ofrecen JSON opcional estable para máquinas, mensajes claros para personas y códigos de salida no cero ante errores.
- Las skills no escriben SQLite directamente ni simulan el estado mediante archivos Markdown.
- Las skills consultan el estado más reciente antes de actuar; no confían en un estado leído al empezar una conversación larga.
- `factory task finish` verifica lo establecido por `design_digest`, no una versión posterior manipulada del diseño.
- Las escrituras críticas usan transacciones, y las modificaciones de archivos generados son atómicas y con copias seguras cuando procede.
- Cualquier operación susceptible de ejecutarse dos veces tras una desconexión tiene estrategia de idempotencia o precondiciones verificables.

### 11.4 Contrato de logs y datos

- Conservar solo eventos y logs necesarios para diagnóstico; permitir configurar retención.
- No persistir razonamiento privado interno de los modelos como memoria del proyecto.
- Limitar tamaño de errores y salidas capturadas; almacenar hashes/rutas o extractos, no volcados indiscriminados.
- Las credenciales son responsabilidad de Claude/Codex/GitHub/Orca y del entorno autorizado.
- La Factory no debe enviar telemetría a servicios externos por defecto.


---

## 12. Seguridad, fallos y restricciones operativas

### 12.1 Amenazas y políticas

Los repositorios, documentos, issues, descripciones de tareas y logs pueden contener instrucciones maliciosas o texto no confiable. Los agentes **no deben tratar contenido encontrado como nuevas políticas de ejecución**. Los adaptadores de herramientas no ejecutan arbitrariamente scripts del repo ni instrucciones de un Issue sin autorización.

Controles mínimos:
- no usar por defecto flags que desactiven sandbox, autorización de comandos o límites de los proveedores;
- no imprimir tokens, `.env`, claves SSH o credenciales en el dashboard ni en `progress.md`;
- mostrar los hooks que se instalarán y exigir el mecanismo de confianza propio de Claude/Codex;
- evitar inyección en shell usando arrays de argumentos de `subprocess`, sin interpolación libre;
- escapar contenido no confiable en HTML y sanitizar rutas/IDs;
- fijar operaciones remotas a repositorios explícitos, evitando actuar sobre el remote incorrecto;
- confirmar operaciones destructivas; detenerse si el worktree tiene cambios valiosos;
- impedir que una instrucción de task anule reglas del repositorio o políticas corporativas.

### 12.2 Matriz de errores esperados

| Fallo | Comportamiento requerido |
|---|---|
| Claude o Codex ausente | `doctor` informa; elegir otro proveedor instalado o detener operación concreta, sin afectar al resto. |
| Modelo solicitado no disponible | Mostrar fallo/fallback permitido; no sustituir silenciosamente. |
| OpenSpec ausente o incompatible | Ofrecer proveedor `builtin`; conservar diseños existentes sin migraciones automáticas. |
| Orca ausente o cerrado | Continuar con Git CLI/VS Code; dashboard independiente. |
| Git con cambios sin confirmar | No limpiar ni sobrescribir; pedir opción segura para crear rama/worktree. |
| Diseño cambiado tras aprobación | Invalidar permiso de ejecución de tareas nuevas y pedir reevaluación. |
| Dos agentes reclaman misma tarea | Solo gana uno; al otro devolver conflicto y estado actual. |
| Run se interrumpe | Guardar último estado/evidencias; no reiniciar solo. |
| Hook no autorizado/no disponible | Mostrar observabilidad reducida, no asumir vida del proceso. |
| SQLite bloqueado/transacción fallida | Reintento acotado de transacción y error coherente; no escritura parcial. |
| Tracker remoto no disponible | Trabajar localmente cuando la política lo permita y mostrar pendiente de sync. |
| Tests no ejecutables | Marcar `not_run` y motivo; nunca `passed`. |
| Reviewer no converge | Bloquear/escalar tras límite de rondas, preservando los hallazgos. |
| Dashboard cerrado | No afecta a ejecución ni persistencia. |
| Rama/worktree borrados externamente | Marcar vínculo roto, pedir conciliación; no recrear automáticamente encima de otra rama. |
| Fuente externa cambia de permisos | Detener sincronización externa; conservar progreso local y avisar. |

### 12.3 Suposiciones de V1

- La Factory se ejecuta principalmente en máquina de desarrollo local con Git instalado.
- Hay un único desarrollador propietario de cada **clon local**; múltiples agentes pueden actuar de forma concurrente dentro de él.
- El estado SQLite local no se comparte por red entre diferentes clones.
- Las acciones de proveedores pueden cambiar entre versiones; por eso se aíslan en adaptadores y se prueban en `doctor`.
- Las versiones y licencias de los proveedores no garantizan todos los modelos o límites de uso.
- El usuario revisa los cambios antes de integrarlos y decide cuándo hacer push/merge.
- Una tarea de código puede requerir revisión humana aunque el Reviewer automático no encuentre fallos.

---

## 13. Pruebas y criterios de aceptación de la Factory completa

### 13.1 Estrategia de pruebas

**Unitarias**: parser/config, cálculo de digest, transición de estados, dependencias, política de complejidad/riesgo, regeneración de `progress.md`, normalización de IDs/rutas y renderizado seguro de HTML.

**Integración local**: repositorios Git temporales, worktrees reales, SQLite con múltiples procesos, CLI en `subprocess`, instalación idempotente, compatibilidad con configuraciones existentes, reinicio de servidor HTML.

**Contrato de adaptadores**: mocks de Claude/Codex/OpenSpec/Orca/GitHub y pruebas *smoke* con herramientas reales instaladas. Fallos de red, sesiones no visibles y cambios de esquema deben producir mensajes de capacidad reducida, no fallos globales.

**Pruebas funcionales manuales**: mismo proyecto en VS Code y Orca; diseñar con Claude, implementar con Codex y revisar con Claude; cancelar, pausar y recuperar en worktree; revisar estado desde HTML; proyecto personal y proyecto profesional simulado.

### 13.2 Criterios numerados

| ID | Criterio verificable |
|---|---|
| F-01 | `factory doctor` identifica repo y herramientas, y no modifica archivos. |
| F-02 | `factory init --dry-run` presenta cambios sin escribirlos. |
| F-03 | Dos ejecuciones de `factory init` con la misma configuración no duplican archivos/reglas. |
| F-04 | Una configuración existente y personalizada no es sobrescrita sin consentimiento. |
| F-05 | El proyecto funciona en VS Code sin Orca instalado. |
| F-06 | El mismo proyecto y sus skills funcionan desde Orca sin necesitar una configuración de metodología diferente. |
| F-07 | La Factory puede diseñar usando Claude y ejecutar con Codex sin transportar el chat original. |
| F-08 | Existe diseño verificable con criterios de aceptación y evidencia de exploración del repo. |
| F-09 | `factory run`/claim rechazan una change sin aprobación vigente. |
| F-10 | Cambiar el contenido normativo del diseño invalida la aprobación anterior. |
| F-11 | Fast path trivial queda explícitamente autorizado y registrado sin documento completo. |
| F-12 | La descomposición genera tareas sin ciclos y con cobertura de AC. |
| F-13 | `ready` solo se muestra cuando están cumplidas aprobación y dependencias. |
| F-14 | Dos procesos compitiendo por una task no consiguen ambos claim válido. |
| F-15 | Cada tarea de escritura se vincula a una rama y worktree reales. |
| F-16 | Dos worktrees paralelos registran checkpoints sin sobrescribir su estado. |
| F-17 | Un agente puede hacer commits, pero no se hace push/merge/cleanup de manera automática. |
| F-18 | El Core no declara `done` con AC obligatorios pendientes o pruebas fallidas. |
| F-19 | Un Reviewer independiente puede evaluar un diff sin leer la conversación del Coder. |
| F-20 | El máximo de rondas correctivas se respeta y escala un bucle inconcluso. |
| F-21 | Un proceso gestionado interrumpido queda identificado y conserva el trabajo. |
| F-22 | Una sesión de chat sin observabilidad suficiente aparece como `unknown`, nunca como ejecutándose con certeza infundada. |
| F-23 | `progress.md` refleja último estado, realizado, pendiente, bloqueos y siguiente acción, y se puede regenerar desde eventos. |
| F-24 | `factory-resume` reconstruye contexto útil y solicita autorización antes de iniciar otro run. |
| F-25 | El dashboard se refresca localmente, filtra tareas y muestra origen de observabilidad sin servidor externo. |
| F-26 | El dashboard no sirve secretos ni permite modificar tareas por HTTP. |
| F-27 | Cambiar `planning.provider` para nuevas changes no destruye diseños OpenSpec previos. |
| F-28 | En perfil `team`, no se alteran reglas/CI/branches del repositorio sin diff y aprobación. |
| F-29 | La sincronización remota comunica fallos y conflictos sin presentar éxito ficticio. |
| F-30 | Reinstalar/actualizar Factory no modifica diseños aprobados ni borra trabajo existente. |

### 13.3 Escenarios completos de validación

**E2E A — Personal / cambio normal**: repositorio Python con pruebas; `doctor` + `init`; diseño en Claude; revisión/aprobación; tarea desde Codex en worktree; checkpoints y tests; revisión independiente; estado `done` en rama, sin push.

**E2E B — Interrupción y recuperación**: agente crea cambios parciales y termina abruptamente; nuevo proceso Factory identifica último run interrumpido; `factory-resume` lee diff/checkpoint; nuevo agente continúa sin perder modificaciones, manteniendo ID de task e historial de runs.

**E2E C — Trabajo paralelo**: dos tasks sin dependencias ejecutadas simultáneamente; estados independientes, ramas y worktrees diferentes, dashboard actualizado, cero claims duplicados; dependencia posterior permanece bloqueada hasta cumplir política.

**E2E D — Colaboración**: inicializar repo con `AGENTS.md`, CI y convenciones existentes; mostrar diff conservador; usar tracker externo o, si no está habilitado, informar claramente de que los estados son locales; no cambiar políticas existentes.

**E2E E — OpenSpec desactivado**: deshabilitar el adaptador para una nueva change; diseño y aprobación con plantilla built-in; Claude/Codex implementan siguiendo contrato idéntico; los cambios previos de OpenSpec siguen accesibles.

**E2E F — Riesgo y seguridad**: diseño pendiente, cambio de digest, petición de push no autorizado, hooks sin confianza y log con token simulado: el Core bloquea operaciones no autorizadas y no expone datos sensibles.

### 13.4 Criterio de aceptación de la release

La V1 se considera lista cuando los escenarios A–F pasan, los criterios F-01–F-30 aplicables están verificados y la documentación de instalación/reparación permite reproducir el setup en un repositorio nuevo y uno corporativo **sin asistencia del autor**. Si una integración experimental (por ejemplo, eventos de Orca) no es estable, puede quedar deshabilitada mediante detección de capacidades, manteniendo operativo el caso base.

---

## 14. Plan de implementación por fases

Cada fase debe generar software utilizable y tests; no implementar todos los adaptadores y variantes antes de probar el caso base.

### Fase 0 — Spike técnico de herramientas (sin gran framework)

**Objetivo**: demostrar integración mínima real con versiones instaladas.

- Inicializar un repositorio de ensayo con Claude Code, Codex y OpenSpec.
- Verificar invocación de skills desde chat en VS Code y Orca.
- Comprobar qué eventos/hook/CLI de cada proveedor son realmente accesibles.
- Probar worktrees de Git y, por separado, Orca.
- Capturar limitaciones verificadas y fijar adaptadores mínimos.

**Entregable**: matriz de compatibilidad/limitaciones y un E2E manual de diseño -> implementación cruzada.

### Fase 1 — Núcleo, diagnóstico e instalación

**Objetivo**: disponer de CLI Python y setup mínimo robusto.

- Paquete instalable, estructura, `doctor`, `init`, `upgrade --dry-run`.
- Inventario de stack, tests y herramientas; perfiles `personal` y `team`.
- Generación de `AGENTS.md`, config y skills con plan/diff y preservación de archivos.
- Pruebas de idempotencia, compatibilidad de rutas y no alteración de repositorios existentes.

**Entregable**: inicializar cualquier repo sin ejecutar LLM, con CLI y plantillas funcionales.

### Fase 2 — Diseño y aprobación

**Objetivo**: contractos estables de cambio e implementación.

- Skill `factory-design` para Claude y Codex.
- Integración OpenSpec opcional y plantilla `builtin`.
- Validación de estructura, criterios de aceptación y versionado/digest.
- Comandos `design show/approve/reject`, puerta de aprobación y fast path trivial.
- Pruebas cross-provider con cambio de diseño posterior.

**Entregable**: un diseño aprobado reutilizable desde cualquier agente/IDE.

### Fase 3 — Tracker local, dependencias y worktrees

**Objetivo**: gestionar trabajo ejecutable sin caos.

- SQLite, migraciones, estados, locks, eventos, transiciones y dependencias.
- Comandos `task ready/list/claim/...`.
- Creación/vinculación de rama y worktree, con cautela sobre cambios y conflictos.
- Almacenamiento por directorio Git común, pruebas concurrentes.

**Entregable**: múltiples tareas independientes y trabajo paralelo seguro a nivel de ficheros/estados.

### Fase 4 — Skills de ejecución, verificación y recuperación

**Objetivo**: desarrollo real y guardias de calidad.

- Skill `factory-implement`, selección adaptativa del workflow.
- Integración nativa de pruebas y Reviewer cuando proceda.
- Registro de verificaciones, AC y commits.
- Checkpoints, `progress.md`, skill `factory-resume`.
- Lanzador gestionado **solo para modalidades compatibles**, como mejora de observabilidad; el chat sigue funcionando sin él.
- Modo manual de interrupción y reanudación, sin reintentos automáticos.

**Entregable**: ejecutar una tarea hasta revisión/done, detectar incompletos y recuperar interrupciones.

### Fase 5 — Dashboard HTML local y observabilidad

**Objetivo**: vista consolidada sin plataforma adicional.

- API local read-only, HTML/CSS/JS, refresco, filtros y detalle de tareas.
- Semántica explícita de `managed/hook/self_reported/unknown`.
- Señales de inactividad y bloqueo; pruebas de seguridad/escapado.
- Adaptador de observabilidad Orca opcional, con fallback claro si no hay sesión visible.

**Entregable**: dashboard actualizado en navegador y continuidad del seguimiento aunque el IDE se cierre.

### Fase 6 — Colaboración y endurecimiento

**Objetivo**: hacerlo útil de verdad en entornos profesionales.

- Backend GitHub inicial (`gh` o API autenticada del proveedor) para vincular Issues/PRs y estados compartidos.
- Reconciliación local/remota y conflictos sin pérdidas silenciosas.
- Compatibilidad con políticas/CI preexistentes, documentación para equipos.
- Actualización segura de Factory y migraciones.
- E2E A–F, pruebas de múltiples plataformas y auditoría de configuración.

**Entregable**: V1 completa para proyectos personales y colaborativos compatibles con GitHub; otros trackers mediante adaptadores posteriores. Para equipos sin GitHub, continúa disponible el modo de ejecución local con estado compartido gestionado manualmente en su herramienta.

### 14.1 Orden y dependencias

`Fase 0 -> Fase 1 -> Fase 2 -> Fase 3 -> Fase 4 -> Fase 5 -> Fase 6`.

Se puede comenzar a usar la Factory desde la Fase 2. Para una primera prueba end-to-end con task/worktree, deben estar completas las Fases 1–4. La Factory no está lista para colaboración remota automatizada hasta la Fase 6.

### 14.2 Criterio para NO añadir funcionalidades

Cualquier nueva funcionalidad debe responder:
1. ¿Qué problema repetible y observado resuelve?
2. ¿No lo cubren suficientemente Claude Code, Codex, Git, OpenSpec u Orca?
3. ¿Puede introducirse como plantilla, skill o adaptador sin nueva infraestructura?
4. ¿Cuál es su prueba de aceptación y coste de mantenimiento?
5. ¿Se puede deshabilitar si queda obsoleta?

Si no hay respuestas claras, posponerla.

---

## 15. Decisiones de diseño resueltas y decisiones diferidas

### 15.1 Resueltas para la implementación

- Python y Git como base técnica local.
- OpenSpec **opcional**, sin acoplamiento irreversible.
- Protocolo común de change / task / run / evidence.
- Aprobación humana obligatoria para cambios no triviales, ligada a un digest.
- Workflows adaptativos; Planner y Reviewer solo cuando aporten.
- Tres skills iniciales (`factory-design`, `factory-implement`, `factory-resume`).
- Persistencia operacional SQLite en directorio Git común.
- `progress.md` local regenerable desde eventos, no documento compartido para estados.
- Separación entre tarea, progreso y actividad observada.
- Worktrees por tarea escritora y commits posibles; sin push/merge/limpieza automáticos.
- Dashboard HTML local actualizado, read-only, sin frontend pesado.
- Trabajo desde chat en VS Code/Orca y CLI operativa.
- Team mode no invasivo, tracker externo opcional y respeto de permisos.

### 15.2 Diferidas expresamente

- Orquestador persistente o distribuido con scheduler avanzado.
- Reintentos automáticos y programación de agentes desatendidos.
- Integración bidireccional perfecta de sesiones abiertas manualmente en cualquier extensión.
- Sincronización de `progress.md` entre ordenadores.
- Soporte completo para trackers distintos de GitHub.
- Dashboard remoto, notificaciones push y edición interactiva.
- RAG de memoria y agentes dedicados a mantenerla.
- Selección automática de proveedor/modelo mediante benchmarks.
- Ejecución automática de acciones irreversibles, push, merge o despliegue.
- Aislamiento fuerte de contenedores/sandbox entre proyectos, salvo lo que aporten Git, SO y los proveedores.

### 15.3 Observaciones para no sobreprometer

1. **Aprobación bloqueante** significa bloqueante dentro del flujo gestionado por Factory; no es una barrera de seguridad contra escritura manual fuera del Core.
2. **Worktree separado** significa checkout aislado, no aislamiento de secretos, red, procesos, BBDD o puertos.
3. **Heartbeat o hook** indica actividad reportada, no progreso verificado.
4. **Design approved** no implica que esté listo para integrar sin CI/revisión corporativa.
5. **Dos licencias de agentes** no garantizan ejecución ilimitada ni disponibilidad permanente de un identificador de modelo.
6. **Dashboard actualizado** no implica monitorización perfecta de sesiones abiertas fuera de los mecanismos soportados.
7. **Compatibilidad con OpenSpec** se decide por capacidades detectadas en una versión concreta, no por confiar en un layout o nombre de comando indefinidamente.

---

## 16. Fuentes técnicas que debe revisar quien implemente

Documentación primaria consultada como referencia del diseño (comprobar versión instalada antes de automatizar):

- OpenSpec, instalación, CLI y schemas: <https://openspec.dev/docs/installation>, <https://openspec.dev/docs/cli>, <https://openspec.dev/docs/customize-schemas>, <https://openspec.dev/docs/schemas/spec-driven>.
- Claude Code, memoria e instrucciones, skills, hooks y ejecución programática: <https://code.claude.com/docs/en/memory>, <https://code.claude.com/docs/en/skills>, <https://code.claude.com/docs/en/hooks>, <https://code.claude.com/docs/en/headless>.
- Codex, CLI y hooks: <https://learn.chatgpt.com/docs/cli/reference>, <https://learn.chatgpt.com/docs/hooks>.
- Orca, CLI, sesiones y worktrees: <https://www.onorca.dev/docs/cli/reference>, <https://www.onorca.dev/docs/agents/native-chat>, <https://www.onorca.dev/docs/model/worktrees>.
- Git, worktrees: <https://git-scm.com/docs/git-worktree>.

Los comandos `factory ...`, contratos de estado, esquemas y ejemplos de este documento son **especificaciones de la Factory que se construirá**, no comandos existentes de terceros.

---

## 17. Primera definición de terminado del proyecto Factory

Se podrá dar por construida la Factory cuando un repositorio limpio o existente pueda:

1. inicializarse sin conflictos;
2. trabajar con Claude y Codex desde VS Code u Orca;
3. generar diseño de una funcionalidad con OpenSpec o plantilla propia;
4. registrar aprobación real y bloquear implementación si esta falta o caduca;
5. crear y ejecutar tareas con dependencias en ramas/worktrees;
6. permitir commits sin push/merge automáticos;
7. mantener progreso y evidencias de ejecución;
8. reconocer una interrupción observable y reanudarla manualmente desde estado persistente;
9. mostrar un dashboard HTML local útil y actualizado;
10. respetar la configuración y políticas preexistentes, también en un repo profesional;
11. conservar documentación/memoria duradera sin inflar cada sesión;
12. superar los escenarios y criterios de aceptación definidos en la sección 13.

**Regla final:** la Factory ha de ser invisible cuando no aporta valor. Abrir el repositorio, pedir un diseño, aprobarlo y ejecutar una tarea con cualquier proveedor debe sentirse como un flujo natural, no como operar una nueva plataforma compleja.

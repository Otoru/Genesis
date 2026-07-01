# Plano de Ação: Integração Sniffer + Genesis ESL para Traces Completos de Chamada

## 1. Resumo executivo

O objetivo é produzir **traces distribuídos completos de chamada** que unem a **camada de controle** (FreeSWITCH ESL, consumida pela biblioteca Genesis) e a **camada de captura** (sinalização SIP e mídia RTP/RTCP, observada passivamente pelo sniffer Otoru/sniffer), com **informação de roteamento** (dialplan, contexto, destino, bridge legs, transferências, ring groups, balanceador).

Hoje os dois sistemas operam em silos observacionais:
- O **Genesis** emite spans OTel `process_event`, `send_command`, `channel.*` (answer/park/hangup/bridge/playback/say/play_and_get_digits), `channel.create`, `channel.wait`, `channel.dtmf.received`, `inbound_connect`, `outbound_handle_connection`, `ring_group.ring`, `queue.wait_and_acquire` e ~20 métricas, mas **não cobre** o ciclo de vida semântico do canal FreeSWITCH (`CHANNEL_PROGRESS`, `CHANNEL_BRIDGE`, `CHANNEL_UNBRIDGE`, `CALL_UPDATE`, `CODEC`, `PLAYBACK_*`, `RECORD_*`, transferências sofia::transferor/transferee) e **não propaga trace_context** entre ESL e SIP.
- O **sniffer** produz o span raiz `voip.call` com filhos `voip.call.sip.request/response`, `voip.rtp.stream`, `voip.register`, `voip.keepalive`, `voip.fraud.alert`, e ~50 métricas de qualidade/fraude, mas **não tem integração ESL** (0 matches para freeswitch/ESL/event_socket no repositório) e seu `trace_id` é **aleatório**, não derivado do SIP Call-ID nem propagado para o FreeSWITCH.

A proposta é (todas as mudanças são no Genesis e na configuração do FreeSWITCH — **sem nenhuma alteração no sniffer**):
1. **Adicionar ao Genesis** spans/métricas que cobrem o lifecycle semântico do canal FreeSWITCH e a informação de roteamento (dialplan/contexto/destino/bridge/transfer/ring group/balanceador), anexando `Channel-Call-UUID`, `Other-Leg-Unique-ID`, `Bridge-A/B-Unique-ID`, `Caller-Context`, `Caller-Destination-Number`, `Application`/`Application-Data`, `Hangup-Cause` (Q.850) e, principalmente, **`sip.call_id`** (= `variable_sip_call_id`) como atributo de span em todos os spans de canal.
2. **Correlacionar Genesis ↔ sniffer por atributo compartilhado**, não por propagação de `trace_id`: o sniffer **já** emite `voip.call_id` = SIP Call-ID em seus spans e já correlaciona chamadas por essa chave no Redis. Ao colocar o mesmo `sip.call_id` em todos os spans de controle do Genesis, o **join** entre o trace de controle (Genesis) e o trace de captura (sniffer) passa a acontecer **no backend de observabilidade** (Grafana/Tempo) via query por atributo — sem qualquer mudança no sniffer. Métricas correlacionam-se a traces via **exemplars OTel** (o SDK anexa o `trace_id` do span corrente como exemplar ao registrar a métrica).
3. **Correlacionar a-leg/b-leg** dentro do trace do Genesis via `Other-Leg-Unique-ID` / `Bridge-A-Unique-ID` / `Bridge-B-Unique-ID`, agrupando tudo sob `Channel-Call-UUID`.

## 2. Estado atual

### 2.1 Genesis — OTel spans (resumo)

Spans existentes (todos via `tracer.start_as_current_span`):
- `process_event` — `genesis/protocol/base.py:201` — envolve apenas metrics+logging; **dispatch e routing rodam FORA do span**.
- `send_command` — `genesis/protocol/base.py:290` — `command.name` = **string crua do comando** (alta cardinalidade), sem `record_exception` no caminho `-ERR`.
- `channel.create` — `genesis/channel.py:144` — registra `channel.dial_path`, `channel.uuid`, `channel.create.duration`, status ERROR.
- `channel.wait` — `genesis/channel.py:415` — `wait.target`, `wait.timeout`, `wait.type`, `wait.result`, `wait.duration`.
- `channel.answer`, `channel.park`, `channel.hangup`, `channel.bridge`, `channel.playback`, `channel.say`, `channel.play_and_get_digits` — produzidos pelo helper genérico `_execute_operation` em `genesis/channel.py:505`; cada um com `channel.<op>.success`, `channel.<op>.duration`.
- `channel.dtmf.received` — `genesis/channel.py:796` — `dtmf.digit`, `dtmf.handled`.
- `inbound_connect` — `genesis/inbound.py:97` — `net.peer.name/port`.
- `outbound_handle_connection` — `genesis/outbound.py:156`.
- `ring_group.ring` — `genesis/group/ring.py:138` — `ring_group.mode/size/timeout/result/answered_uuid/answered_dial_path`, mas **não chama `set_status(ERROR)`** no caminho de exceção.
- `queue.wait_and_acquire` — `genesis/queue/core.py:76`.

Gaps críticos (do mapeamento):
- **Sem spans em `genesis/session.py`** (sendmsg, lifecycle da Session não instrumentados).
- **Sem spans em `genesis/consumer.py`**.
- **Sem spans para handler dispatch / `routing_strategy.route()` / loop `consume()` / loop `handler()`**.
- **Sem `span.add_event()` em todo o genesis/** — zero span events registrados.
- `process_event` **não carrega** `Call-Direction`, `Hangup-Cause`, `Answer-State`, `Channel-State`, `Event-Subclass` (aparecem só em métricas via `build_metric_attributes`).
- `send_command` não registra erro de span no reply `-ERR`.
- Duplicação de definições de métricas entre `genesis/protocol/metrics.py` e `genesis/channel.py` ("to avoid circular imports").
- `call_duration_histogram.record` em `channel.py:573` **sem atributos** (sem UUID/cause).

### 2.2 Genesis — OTel metrics (resumo)

20 instrumentos: 13 counters, 5 histograms, 2 up_down_counters, 0 observable/gauge.
Relevantes: `genesis.commands.sent/duration/errors`, `genesis.events.received`, `genesis.channel.operations`, `genesis.channel.operation.duration`, `genesis.channel.hangup.causes`, `genesis.channel.bridge.operations`, `genesis.channel.dtmf.received`, `genesis.call.duration`, `genesis.timeouts`, `genesis.channel.routing.hits`, `genesis.channel.routing.fallback`, `genesis.connections.active/errors`, `genesis.ring_group.operations/duration/results`, `genesis.queue.operations/wait_duration`.

Gaps:
- **Sem gauge de chamadas ativas por estado**, sem gauge de profundidade de fila de comandos/events.
- `genesis.connections.errors` **só existe em `inbound.py`**; Outbound não tem.
- **Sem métricas em `session.py`, `consumer.py`, `group/load_balancer.py`**.
- `call.duration` sem atributos → não particionável por canal/cause.

### 2.3 Sniffer — sinais atuais

- Span raiz `voip.call` (catálogo `SpanOpCall`) com filhos `voip.call.sip.request`, `voip.call.sip.response` (waterfall por mensagem SIP), `voip.rtp.stream` (por SSRC, lado a/b), `voip.register` + `voip.register.transaction`, `voip.keepalive`, `voip.fraud.alert`.
- Métricas: `voip.calls.total/answered/failed/timeout/muted/one_way_audio/active`, `voip.call.duration_s/mos/jitter_ms/loss_pct/silence_ratio`, `voip.rtp.streams.active`, `voip.keepalives.total/rtt_ms`, `voip.registrations.active`, `sniffer.packets.dropped`, `sniffer.fraud.*`, `sniffer.pipeline.watermark_*`, `process.*`.
- **`trace_id` é aleatório** (SDK `AlwaysSample` ou `TraceIDRatioBased`); `voip.call_id` (SIP Call-ID) é só atributo de lookup humano, **não é o trace_id**.
- **Sem propagador W3C** (`provider.go` não chama `SetTextMapPropagator`, parser SIP não extrai/injeta `traceparent`/`X-Tracespan`).
- **Sem integração ESL**: 0 matches para freeswitch/ESL/event_socket.
- Correlação cross-sensor por **SIP Call-ID via Redis** (`voip:call:{call_id}`, `voip:ep:{ip}|{port}`), não por trace context.
- Service name default `"sauron"` (`OTEL_SERVICE_NAME`).

### 2.4 Sobreposição e divergência

| Dimensão | Genesis (ESL) | Sniffer (SIP/RTP) | Convergência |
|---|---|---|---|
| Identidade de chamada | `Unique-ID` (per-leg), `Channel-Call-UUID` (call-wide) | `voip.call_id` = SIP `Call-ID` | `variable_sip_call_id` no evento ESL liga os dois |
| Answer | `CHANNEL_ANSWER` → `channel.answer` span (Reply-Text) | SIP 200 OK → `voip.call.sip.response` | Mesmo instante, spans separados |
| Hangup | `channel.hangup` + `Hangup-Cause` | `voip.sip.termination_cause` (inferido por IP do BYE) | Genesis é **autoritativo** para cause/who |
| Bridge | `channel.bridge` (via `api uuid_bridge`/sendmsg) — **sem evento CHANNEL_BRIDGE** | Vê dois SIP dialogs separados, **sem tie a-leg/b-leg** | ESL `Bridge-A/B-Unique-ID` + `Other-Leg-Unique-ID` fecha o gap |
| Transfer | **Não tratado** no Genesis | Vê re-INVITE/REFER sem motivo | `sofia::transferor/transferee` + `CALL_UPDATE.Bridged-To` |
| Codec | Apenas em métricas (`build_metric_attributes` não expõe codec) | `rtp.codec`, `rtp.payload_type` | `CODEC` ESL event fecha o gap |
| Routing/dialplan | `Caller-Context`, `Caller-Destination-Number`, `Application` em `CHANNEL_EXECUTE_COMPLETE` — **não extraídos** | Não visível na camada de pacotes | ESL é a única fonte |
| trace_id | SDK aleatório por span | SDK aleatório por span | **Divergem** — proposta: propagar via SIP header |

## 3. Proposta de mapeamento ESL → spans/metrics

Convenção: **ADICIONAR** = novo; **RENOMEAR** = mudar nome/atributos; **MANTER** = sem alteração; **REMOVER** = eliminar.

### 3.1 Spans

| Evento ESL | Ação | Span (nome, atributos, span events) | Justificativa / fonte ESL |
|---|---|---|---|
| `CHANNEL_CREATE` | **ADICIONAR** | `freeswitch.channel.create` — attrs: `channel.uuid`=Unique-ID, `channel.call_uuid`=Channel-Call-UUID, `channel.direction`=Call-Direction, `channel.name`=Channel-Name, `channel.destination_number`=Caller-Destination-Number, `channel.context`=Caller-Context, `channel.dialplan`=Caller-Dialplan, `channel.caller_id_number`=Caller-Caller-ID-Number, `channel.caller_id_name`=Caller-Caller-ID-Name, `channel.network_addr`=Caller-Network-Addr, `sip.call_id`=variable_sip_call_id (se presente) | `switch_core_state_machine.c:626`; nascimento do leg; único ponto com `Call-Direction` + contexto dialplan; `sip.call_id` é a chave de correlação com o sniffer |
| `CHANNEL_PROGRESS` | **ADICIONAR** | `freeswitch.channel.progress` — attrs: `channel.uuid`, `channel.call_uuid`, `channel.state`=CS_RINGING, `answer.state`=ringing, `other_leg.uuid`=Other-Leg-Unique-ID (se presente); span events: nenhum | `switch_channel.c:3507`; timestamp de alerting |
| `CHANNEL_PROGRESS_MEDIA` | **ADICIONAR** | `freeswitch.channel.progress_media` — attrs: `channel.uuid`, `channel.call_uuid`, `answer.state`=early, `channel.read_codec`=Channel-Read-Codec-Name, `channel.write_codec`=Channel-Write-Codec-Name, `other_leg.uuid` | `switch_channel.c:3562`; early-media (183) — explica RTP antes do ANSWER |
| `CHANNEL_ANSWER` | **ADICIONAR** (span semântico; **MANTER** `channel.answer` que envolve o comando `answer`) | `freeswitch.channel.answer` — attrs: `channel.uuid`, `channel.call_uuid`, `channel.state`=CS_EXECUTE, `answer.state`=answered, `channel.read_codec`, `channel.write_codec`, `other_leg.uuid` | `switch_channel.c:3848`; instante autoritativo de answer |
| `CHANNEL_BRIDGE` | **ADICIONAR** | `freeswitch.channel.bridge` — attrs: `channel.uuid`=Unique-ID (firing leg), `bridge.a_uuid`=Bridge-A-Unique-ID, `bridge.b_uuid`=Bridge-B-Unique-ID, `channel.call_uuid`, `other_leg.uuid`=Other-Leg-Unique-ID, `other_leg.type`=Other-Type, `other_leg.destination_number`=Other-Leg-Destination-Number, `other_leg.caller_id_number`=Other-Leg-Caller-ID-Number; span events: `bridge.established` | `switch_ivr_bridge.c:1377`; **correlação autoritativa a-leg/b-leg** |
| `CHANNEL_UNBRIDGE` | **ADICIONAR** | `freeswitch.channel.unbridge` — attrs: `channel.uuid`, `bridge.a_uuid`, `bridge.b_uuid`/`other_leg.uuid`, `channel.call_uuid`, `hangup.cause` (se presente); span events: `bridge.torn_down` | `switch_ivr_bridge.c:1326/1481/1494/1879`; bounds talk time; detecta transfer (unbridge→bridge novo) |
| `CHANNEL_HANGUP` | **ADICIONAR** | `freeswitch.channel.hangup` — attrs: `channel.uuid`, `channel.call_uuid`, `hangup.cause`=Hangup-Cause, `answer.state`=hangup, `channel.state`=CS_HANGUP, `other_leg.uuid`; span events: `hangup.cause.<normalized>` | `switch_channel.c:3447`; causa normalizada por leg |
| `CHANNEL_HANGUP_COMPLETE` | **ADICIONAR** | `freeswitch.channel.hangup_complete` — attrs: `channel.uuid`, `channel.call_uuid`, `hangup.cause`, `hangup.cause.q850`=variable_hangup_cause_q850, `channel.name`, `sip.call_id`=variable_sip_call_id, `cdr.xml`=`[verificar]` se `CDR-Attached=xml`; span events: `call.finalized` | `switch_core_state_machine.c:943`; commit point do CDR/trace |
| `CHANNEL_DESTROY` | **ADICIONAR** | `freeswitch.channel.destroy` — attrs: `channel.uuid`, `channel.call_uuid` | `switch_core_session.c:1584`; sinal de desregistro de handler |
| `CHANNEL_EXECUTE` | **ADICIONAR** | `freeswitch.channel.execute` — attrs: `channel.uuid`, `channel.call_uuid`, `application.name`=Application, `application.uuid`=Application-UUID; span events: nenhum | Dialplan app start |
| `CHANNEL_EXECUTE_COMPLETE` | **ADICIONAR** | `freeswitch.channel.execute_complete` — attrs: `channel.uuid`, `channel.call_uuid`, `application.name`=Application, `application.uuid`=Application-UUID, `application.response`=Application-Response; span events: `app.<name>.done` | Correlaciona com `Session._awaitable_complete_command` |
| `CHANNEL_PARK` / `CHANNEL_UNPARK` | **ADICIONAR** | `freeswitch.channel.park` / `freeswitch.channel.unpark` — attrs: `channel.uuid`, `channel.call_uuid`, `channel.state` | `switch_ivr.c:1002/1213` |
| `CALL_UPDATE` | **ADICIONAR** | `freeswitch.call.update` — attrs: `channel.uuid`, `channel.call_uuid`, `bridged.to`=Bridged-To, `caller.transfer_source`=Caller-Transfer-Source, `caller.orig_caller_id_number`=Caller-Orig-Caller-ID-Number; span events: `caller_id.mutated` | `switch_channel.c:3279`; detecta transfer mid-call |
| `CODEC` | **ADICIONAR** | `freeswitch.channel.codec` — attrs: `channel.uuid`, `channel.call_uuid`, `channel.read_codec.name/rate`, `channel.write_codec.name/rate`, `channel.reported_read_codec_rate` | `switch_core_codec.c:189/300/471/531/579`; timeline de codec por leg |
| `PLAYBACK_START` / `PLAYBACK_STOP` | **ADICIONAR** | `freeswitch.channel.playback.start/stop` — attrs: `channel.uuid`, `channel.call_uuid`, `playback.file_path`=Playback-File-Path, `playback.file_type`=Playback-File-Type, `playback.status`=Playback-Status (no stop); span events: nenhum | `switch_ivr_play_say.c:1649/2023`; explica mídia one-way (ringback) |
| `RECORD_START` / `RECORD_STOP` | **ADICIONAR** | `freeswitch.channel.record.start/stop` — attrs: `channel.uuid`, `channel.call_uuid`, `record.file_path`=Record-File-Path, `record.completion_cause`=Record-Completion-Cause (no stop) | `switch_ivr_async.c:1241/1482`, `switch_ivr_play_say.c:770/1033` |
| `CUSTOM sofia::transferor` / `sofia::transferee` | **ADICIONAR** | `freeswitch.sofia.transfer` — attrs: `channel.uuid`, `channel.call_uuid`, `transfer.role`=transferor\|transferee, `other_leg.uuid`=Other-Leg-Unique-ID, `sofia.profile`=sofia_profile_name; span events: `transfer.initiated` | `mod_sofia.h:84-110`; distingue transfer de hangup |
| `CUSTOM sofia::reinvite` / `sofia::replaced` | **ADICIONAR** | `freeswitch.sofia.reinvite` / `freeswitch.sofia.replaced` — attrs: `channel.uuid`, `channel.call_uuid`, `sofia.profile`; span events: `media.renegotiated` | Correlaciona com mudança de IP/codec no RTP |
| `CUSTOM callcenter::info` | **ADICIONAR** | `freeswitch.callcenter.info` — attrs: `cc.queue`=CC-Queue, `cc.action`=CC-Action, `cc.agent`=CC-Agent, `cc.member_uuid`=CC-Member-UUID, `cc.count`=CC-Count, `cc.selection`=CC-Selection, `channel.uuid`=Unique-ID | ACD routing |
| `CUSTOM conference::maintenance` / `conference::cdr` | **ADICIONAR** | `freeswitch.conference.maintenance` / `freeswitch.conference.cdr` — attrs: `conference.name`, `conference.profile`, `conference.action`=Action, `conference.member_id`=Member-ID, `channel.uuid`, `old.member_id`=Old-Member-ID | Multi-party bridge |
| `CUSTOM valet_parking::info` | **ADICIONAR** | `freeswitch.valet.info` — attrs: `valet.lot`=Valet-Lot-Name, `valet.extension`=Valet-Extension, `valet.action`=Action, `bridge.to_uuid`=Bridge-To-UUID, `channel.uuid` | Park/retrieve |
| `CUSTOM sofia::register/unregister/expire/gateway_state` | **ADICIONAR** | `freeswitch.sofia.register` — attrs: `register.aor`=from-user@from-host, `register.contact_ip`=contact, `register.expires_s`=expires, `register.response_code`, `register.reason`, `gateway.name`=Gateway-Name, `gateway.state`=State | Pre-condição de outbound routing |
| `process_event` (span existente) | **RENOMEAR/MELHORAR** | **MANTER** nome `process_event`, mas **ADICIONAR** attrs: `event.direction`=Call-Direction, `event.channel_state`=Channel-State, `event.answer_state`=Answer-State, `event.hangup_cause`=Hangup-Cause, `event.subclass`=Event-Subclass, `event.call_uuid`=Channel-Call-UUID, `event.other_leg`=Other-Leg-Unique-ID, `sip.call_id`=variable_sip_call_id; **ADICIONAR** span events para bridge/transfer/hangup_reason quando aplicável | Fecha o gap de atributos de routing no span de processo |
| `send_command` (span existente) | **RENOMEAR** `command.name` de string crua → verbo do comando (parse first token); **ADICIONAR** `command.error`=`-ERR` detection + `span.set_status(ERROR)` + `record_exception` no reply `-ERR` | Alta cardinalidade hoje; sem erro de span |
| `channel.bridge` (existente em `channel.py`) | **MANTER**, mas **ADICIONAR** span event `bridge.esl_event` quando `CHANNEL_BRIDGE` chega, linkando `bridge.a_uuid`/`bridge.b_uuid` | Span do comando vs span do evento são complementares |
| `channel.hangup` (existente) | **MANTER**, **ADICIONAR** attr `hangup.cause.q850` (via `variable_hangup_cause_q850`) e span event `hangup.authoritative` quando `CHANNEL_HANGUP_COMPLETE` chega | Fecha gap de Q.850 |
| `ring_group.ring` (existente) | **MANTER** attrs atuais, **ADICIONAR** `ring_group.balancer_backend` (nome do backend, NÃO UUID), `ring_group.selected_dial_path`, `ring_group.context`; **CORRIGIR** chamar `span.set_status(StatusCode.ERROR)` no caminho de exceção (gap do mapeamento) | Routing info de ring group |
| `queue.wait_and_acquire` (existente) | **MANTER**, **ADICIONAR** `queue.depth` como atributo de span (NÃO de métrica) | Profundidade só como span attr evita cardinalidade |

### 3.2 Metrics

| Sinal | Ação | Nome / tipo / attrs | Justificativa |
|---|---|---|---|
| Chamadas ativas por estado | **ADICIONAR** | `genesis.calls.active` (UpDownCounter) attrs: `channel.state` (enum ChannelState), `direction` | Hoje só `connections.active` por tipo in/out |
| Eventos ESL processados por nome | **MANTER** `genesis.events.received` | — | Já cobre |
| Bridge por par de legs | **ADICIONAR** | `genesis.channel.bridge.events` (Counter) attrs: `bridge.result` (established/unbridged), `hangup.cause` (no unbridge) | Hoje `bridge.operations` mede só o comando |
| Transferências | **ADICIONAR** | `genesis.channel.transfers` (Counter) attrs: `transfer.type` (blind/attended), `transfer.role` (transferor/transferee) | Inexistente |
| Codec changes | **ADICIONAR** | `genesis.channel.codec.changes` (Counter) attrs: `channel.read_codec`, `channel.write_codec` (NÃO UUID) | Inexistente |
| Dialplan apps executados | **ADICIONAR** | `genesis.dialplan.applications` (Counter) attrs: `application.name` (set/bridge/playback/transfer/park/voicemail/ivr/queue), `application.result` (success/fail) | Routing info |
| Hangup causes por Q.850 | **ADICIONAR** | `genesis.channel.hangup.causes.q850` (Counter) attrs: `hangup.cause.q850` (NÃO UUID) | Hoje `hangup.causes` só tem cause textual |
| Duration de processamento de evento | **ADICIONAR** | `genesis.event.processing.duration` (Histogram) attrs: `event.name` | Gap: sem latência de dispatch |
| `genesis.call.duration` | **RENOMEAR/REPARAR** | **MANTER** nome, **ADICIONAR** attrs `hangup.cause` e `direction`; **NÃO** adicionar `channel.uuid` (cardinalidade) | Hoje gravado sem attrs |
| `genesis.connections.errors` | **ADICIONAR** em `genesis/outbound.py` | Reaproveitar mesmo nome com attrs `type`=outbound, `error`=... | Gap: outbound sem error counter |
| Métricas duplicadas em `channel.py` e `metrics.py` | **REMOVER** duplicação | Centralizar definição em `genesis/protocol/metrics.py` e importar em `channel.py` (resolver circular import via module lazy import ou mover constants) | Hazard de manutenção |
| Observable gauge de queue depth | **ADICIONAR** | `genesis.commands.queue.depth` (ObservableGauge), `genesis.events.queue.depth` (ObservableGauge) | Backpressure não observável |

**Regra de cardinalidade**: atributos de métrica **NUNCA** carregam UUIDs (`channel.uuid`, `bridge.a_uuid`, `other_leg.uuid`); apenas enums/labels low-cardinality (`channel.state`, `direction`, `hangup.cause`, `application.name`, `transfer.type`). UUIDs vão **só em spans**.

## 4. Estratégia de correlação de traces (sniffer ↔ Genesis)

### 4.1 Opções avaliadas

| Opção | Mecanismo | Veredito |
|---|---|---|
| **A. Correlação por atributo `sip.call_id` no backend** | Genesis anexa `sip.call_id` (= `variable_sip_call_id`) a todos os spans de canal e ao `process_event`; sniffer já emite `voip.call_id` = SIP Call-ID. Join em Grafana/Tempo por query de atributo. Métricas → traces via exemplars OTel. | **RECOMENDADA / ESCOPO DESTE PR** — zero mudança no sniffer; usa chaves que o sniffer já produz; funciona mesmo com trace_ids independentes |
| B. SIP Call-ID **como** trace_id | Usar `variable_sip_call_id` como `trace_id` OTel | Rejeitado: `trace_id` OTel é 128-bit hex; Call-ID é string arbitrária; quebra semântica OTel e o SDK não aceita |

### 4.2 Modelo de traces (independentes, correlacionados por atributo)

Genesis e sniffer continuam emitindo **traces OTel independentes** (cada um com seu próprio `trace_id`). A correlação é **lógica**, por `sip.call_id`:

```
Trace Genesis (service=genesis) — root: freeswitch.channel.create
  freeswitch.channel.progress        attrs: sip.call_id, channel.call_uuid
  freeswitch.channel.answer          attrs: sip.call_id, channel.call_uuid
  freeswitch.channel.bridge          attrs: sip.call_id, bridge.a_uuid, bridge.b_uuid
  freeswitch.channel.execute         attrs: sip.call_id, application.name
  freeswitch.channel.unbridge        attrs: sip.call_id
  freeswitch.channel.hangup          attrs: sip.call_id, hangup.cause
  freeswitch.channel.hangup_complete attrs: sip.call_id, hangup.cause.q850

Trace sniffer (service=sniffer) — root: voip.call   attrs: voip.call_id (= mesmo SIP Call-ID)
  voip.call.sip.request              attrs: voip.call_id
  voip.call.sip.response             attrs: voip.call_id
  voip.rtp.stream (a)                attrs: voip.call_id
  voip.rtp.stream (b)                attrs: voip.call_id
```

**Join no Grafana/Tempo**: `trace.span.attrs["sip.call_id"] == trace.span.attrs["voip.call_id"]` — uma query por atributo retorna os dois traces; o usuário navega entre eles. Não há parentesco OTel direto (intencional: o sniffer não conhece o trace_id do Genesis).

### 4.3 Hierarquia **dentro** do trace Genesis

- **Trace raiz lógico = chamada**, identificado por `Channel-Call-UUID` (call-wide). O span `freeswitch.channel.create` do leg originador (`Call-Direction=inbound` ou originador do `originate`) é o root.
- **Spans de controle/dialplan** (`execute`, `execute_complete`, `codec`, `playback.*`, `transfer`) são filhos diretos do root via context OTel propagado pelo `Protocol`/`Channel`.
- **`sip.call_id` e `channel.call_uuid`** são atributos em **todos** os spans de canal — garantem o join com o sniffer e o agrupamento a-leg/b-leg.

### 4.4 Amarrando a-leg/b-leg (dentro do Genesis)

- No `CHANNEL_BRIDGE`, o Genesis lê `Bridge-A-Unique-ID` (originador) e `Bridge-B-Unique-ID` (peer). Após o bridge, ambos os legs compartilham o mesmo `Channel-Call-UUID` (`switch_ivr_bridge.c:1446/1555/1684/1877`).
- O span `freeswitch.channel.bridge` carrega `bridge.a_uuid` e `bridge.b_uuid` como **atributos de span** e emite span event `bridge.established` com ambos os UUIDs.
- Cada leg é um dialog SIP distinto com SIP Call-ID próprio — o join cross-leg **não** é por `sip.call_id`, e sim por `channel.call_uuid` (comum aos dois legs após bridge) dentro do trace Genesis, e por `bridge.a_uuid`/`bridge.b_uuid` para cruzar com os traces sniffer de cada dialog. Fluxo: do `sip.call_id` de um leg → abre trace Genesis → lê `bridge.b_uuid` → busca o `sip.call_id`/`voip.call_id` do outro leg.
- Em transferências, `CALL_UPDATE.Bridged-To` + `sofia::transferor/transferee` indicam o novo leg; o Genesis inicia novo span root com **span link** (`Links`) para o trace anterior (não parent, pois é outra chamada lógica).
- **Caveat**: em transfer que cria novo b-leg, o `call_uuid` pode rolar para o novo originador — reavaliar `Channel-Call-UUID` a cada `CHANNEL_BRIDGE` e, se mudar, iniciar novo span root com link para o anterior.

## 5. Informação de roteamento a anexar

| Informação de routing | Campo ESL fonte | Span/atributo destino |
|---|---|---|
| Contexto dialplan | `Caller-Context` | `freeswitch.channel.create` → `channel.context`; `process_event` → `event.context` |
| Destination number | `Caller-Destination-Number` | `freeswitch.channel.create` → `channel.destination_number` |
| Dialplan | `Caller-Dialplan` | `freeswitch.channel.create` → `channel.dialplan` |
| Direção (a/b leg, inbound/outbound) | `Call-Direction` | `freeswitch.channel.create` → `channel.direction`; `process_event` → `event.direction` |
| Aplicação dialplan executada | `Application` (em `CHANNEL_EXECUTE`/`CHANNEL_EXECUTE_COMPLETE`) | `freeswitch.channel.execute` → `application.name` |
| Argumentos da aplicação | `Application-Data` `[verificar se presente no payload ESL do Genesis]` | `freeswitch.channel.execute` → `application.data` |
| Bridge a-leg/b-leg | `Bridge-A-Unique-ID`, `Bridge-B-Unique-ID` (`CHANNEL_BRIDGE`) | `freeswitch.channel.bridge` → `bridge.a_uuid`, `bridge.b_uuid` |
| Other-Leg (correlação per-leg) | `Other-Leg-Unique-ID`, `Other-Type` | todos os spans de evento de canal → `other_leg.uuid`, `other_leg.type` |
| Transfer (role + partner) | `Event-Subclass` sofia::transferor/transferee, `Other-Leg-Unique-ID` | `freeswitch.sofia.transfer` → `transfer.role`, `other_leg.uuid` |
| Transfer source | `Caller-Transfer-Source` | `freeswitch.call.update` → `caller.transfer_source` |
| Ring group mode/destinations | args de `RingGroup.ring` (`mode`, `destinations`, `timeout`) | `ring_group.ring` (já existe) → adicionar `ring_group.context`, `ring_group.selected_dial_path` |
| Load balancer backend escolhido | `LoadBalancerBackend` em `genesis/group/load_balancer.py` `[verificar nome do método select]` | `ring_group.ring` → `ring_group.balancer_backend` (nome/label, NÃO UUID) |
| Queue/ACD | `CC-Queue`, `CC-Agent`, `CC-Action`, `CC-Member-UUID` | `freeswitch.callcenter.info` |
| Conference | `Conference-Name`, `Action`, `Member-ID` | `freeswitch.conference.maintenance` |
| Hangup cause (texto) | `Hangup-Cause` | `freeswitch.channel.hangup` → `hangup.cause` |
| Hangup cause Q.850 | `variable_hangup_cause_q850` | `freeswitch.channel.hangup_complete` → `hangup.cause.q850` |
| Codec negociado | `Channel-Read-Codec-Name`, `Channel-Write-Codec-Name`; `CODEC` event | `freeswitch.channel.codec` → `channel.read_codec.name`, `channel.write_codec.name` |
| SIP Call-ID (correlação com sniffer — chave primária) | `variable_sip_call_id` | todos os spans de canal + `process_event` → `sip.call_id` (join com `voip.call_id` do sniffer no backend) |
| traceparent (OPCIONAL/futuro — exige sniffer) | `variable_sip_h_X_Tracespan` | **Fora do escopo deste PR**: exigiria o sniffer consumir o header. A correlação real é por `sip.call_id` (linha acima) |

## 6. Mudanças concretas no Genesis (por arquivo)

### `genesis/protocol/metrics.py`
- **ADICIONAR** instrumentos: `genesis.calls.active` (UpDownCounter, attrs `channel.state`, `direction`), `genesis.channel.bridge.events` (Counter, attrs `bridge.result`, `hangup.cause`), `genesis.channel.transfers` (Counter, attrs `transfer.type`, `transfer.role`), `genesis.channel.codec.changes` (Counter, attrs `channel.read_codec`, `channel.write_codec`), `genesis.dialplan.applications` (Counter, attrs `application.name`, `application.result`), `genesis.channel.hangup.causes.q850` (Counter, attrs `hangup.cause.q850`), `genesis.event.processing.duration` (Histogram, attrs `event.name`), `genesis.commands.queue.depth` (ObservableGauge), `genesis.events.queue.depth` (ObservableGauge).
- **REMOVER** definições duplicadas que também existem em `channel.py` (resolver circular import movendo os `meter.create_*` para cá e importando os objetos prontos em `channel.py`).
- **MANTER** `genesis.events.received`, `genesis.commands.*`, `genesis.channel.routing.*`, `genesis.connections.active`.

### `genesis/protocol/base.py`
- **MANTER** span `process_event` (linha 201); **ADICIONAR** atributos `event.direction`, `event.channel_state`, `event.answer_state`, `event.hangup_cause`, `event.subclass`, `event.call_uuid`, `event.other_leg`, `sip.call_id` via extensão de `build_event_attributes` (`sip.call_id` é a chave de correlação com o sniffer).
- **ESTENDER** `process_event` para envolver **também** o dispatch (`dispatch_to_handlers`) e `routing_strategy.route()` — mover o `with` para fora do bloco metrics+logging. Alternativa: **ADICIONAR** span `dispatch_handlers` aninhado.
- **ADICIONAR** span `route_event` envolvendo `self.routing_strategy.route(event)` em `_process_one_event`.
- **RENOMEAR** atributo `command.name` do span `send_command` (linha 291) de string crua para verbo parseado (primeiro token, ex. `api`, `sendmsg`, `event`, `filter`); **ADICIONAR** `command.args` com o restante (truncado a 200 chars) se necessário para debug.
- **ADICIONAR** no caminho `-ERR` de `_execute_send` (linha 302): `span.set_status(StatusCode.ERROR, Reply-Text)`, `span.record_exception(Exception(Reply-Text))`, atributo `command.error=protocol_error`.
- **ADICIONAR** span `consume_loop`/`handler_loop` (opcional, baixa cardinalidade) envolvendo o corpo de `consume()` e `handler()`.
- **ADICIONAR** ObservableGauge callbacks para `self.commands.qsize()` e `self.events.qsize()` (usar `asyncio` safe snapshot ou pular se non-async-safe).

### `genesis/protocol/telemetry.py`
- **ESTENDER** `build_event_attributes` (linha 15-40) para incluir: `event.direction` (Call-Direction), `event.channel_state` (Channel-State), `event.answer_state` (Answer-State), `event.hangup_cause` (Hangup-Cause), `event.subclass` (Event-Subclass), `event.call_uuid` (Channel-Call-UUID), `event.other_leg` (Other-Leg-Unique-ID), `sip.call_id` (variable_sip_call_id) — chave de correlação com o sniffer, presente em todos os spans de canal.
- **MANTER** `build_metric_attributes` e `log_event`.

### `genesis/protocol/processors.py`
- **ADICIONAR** novo event processor `channel_lifecycle_processor` (ou um por evento semântico) que:
  - Detecta `CHANNEL_CREATE/PROGRESS/PROGRESS_MEDIA/ANSWER/BRIDGE/UNBRIDGE/HANGUP/HANGUP_COMPLETE/DESTROY/EXECUTE/EXECUTE_COMPLETE/PARK/UNPARK/CALL_UPDATE/CODEC/PLAYBACK_START/PLAYBACK_STOP/RECORD_START/RECORD_STOP`.
  - Extrai `Channel-Call-UUID`, `Unique-ID`, `Other-Leg-Unique-ID`, `Bridge-A/B-Unique-ID`, `Application`, `Application-Data` `[verificar]`, `Hangup-Cause`, `variable_hangup_cause_q850`, `variable_sip_call_id` (chave de correlação com o sniffer).
  - Dispara a criação do span semântico correspondente (via um novo `EventSpanEmitter` injetado no Protocol) e incrementa as métricas new.
- **MANTER** `auth_request_processor`, `command_reply_processor`, `api_response_processor`, `disconnect_processor`.
- **ADICIONAR** processador `sofia_custom_processor` para subclasses `sofia::transferor/transferee/reinvite/replaced/register/unregister/expire/gateway_state` e `callcenter::info`, `conference::maintenance/cdr`, `valet_parking::info`.

### `genesis/protocol/routing/{base,channel,composite,global_}.py`
- **MANTER** lógica de routing; **ADICIONAR** span event `routing.hit` no `ChannelRoutingStrategy.route` (linha 55) e `routing.fallback` no `GlobalRoutingStrategy.route` (linha 50), ambos no span `route_event` corrente (se ativo).

### `genesis/channel.py`
- **MANTER** spans `channel.create/wait/answer/park/hangup/bridge/playback/say/play_and_get_digits/dtmf.received` e o helper `_execute_operation` (linha 494-537).
- **ADICIONAR** em `channel.create` (linha 144): registrar attrs `sip.call_id` (lido do evento/variável) e `channel.call_uuid` no span — chaves de correlação com o sniffer e de agrupamento a-leg/b-leg.
- **ADICIONAR** em `channel.bridge` (linha 632-644): attrs `bridge.a_uuid`, `bridge.b_uuid`, `other_leg.uuid`; span event `bridge.esl_event` quando `CHANNEL_BRIDGE` é recebido e correlacionado.
- **ADICIONAR** em `channel.hangup` (linha 588-600): attr `hangup.cause.q850` lendo `variable_hangup_cause_q850` do contexto; span event `hangup.authoritative` em `CHANNEL_HANGUP_COMPLETE`.
- **ADICIONAR** em `_state_handler`: registrar `channel.state` transitions como span events no span `channel.wait` ativo (se houver).
- **REMOVER** as 7 re-definições duplicadas de métricas (linhas 32-68) — importar de `genesis/protocol/metrics.py`.
- **REPARAR** `call_duration_histogram.record` (linha 573) para gravar com attrs `hangup.cause` e `direction` (NÃO `channel.uuid`).

### `genesis/session.py`
- **ADICIONAR** tracer a nível de módulo (`trace.get_tracer(__name__)`).
- **ADICIONAR** span `session.sendmsg` envolvendo `Session.sendmsg` (attrs: `channel.uuid`, `application.name`, `application.uuid`=Event-UUID, `application.block`).
- **ADICIONAR** span `session.start` / `session.stop` para o lifecycle.
- **ADICIONAR** span `session.await_complete` em `_awaitable_complete_command` (attrs: `channel.uuid`, `application.uuid`, `event.name`=CHANNEL_EXECUTE_COMPLETE/CHANNEL_HANGUP_COMPLETE, `wait.duration`).
- **ADICIONAR** métricas `genesis.session.commands` (Counter, attrs `application.name`), `genesis.session.command.duration` (Histogram).

### `genesis/consumer.py`
- **ADICIONAR** tracer a nível de módulo.
- **ADICIONAR** span `consumer.start` / `consumer.stop` (attrs: `consumer.host`, `consumer.port`).
- **ADICIONAR** span `consumer.dispatch` envolvendo a invocação de handlers registrados via `@consumer.handle`.
- **ADICIONAR** métrica `genesis.consumer.handlers` (Counter, attrs `event.name`, `handler.matched`).

### `genesis/inbound.py`
- **MANTER** `inbound_connect` (linha 97) e `genesis.connections.active/errors`.
- **ADICIONAR** `record_exception` + `set_status(ERROR)` no span `inbound_connect` em falha de connect/timeout.

### `genesis/outbound.py`
- **MANTER** `outbound_handle_connection` (linha 156) e `genesis.connections.active`.
- **ADICIONAR** contador `genesis.connections.errors` (attrs `type=outbound`, `error=...`) — gap do mapeamento.

### `genesis/group/ring.py`
- **MANTER** `ring_group.ring` (linha 138); **CORRIGIR** chamar `span.set_status(StatusCode.ERROR, str(e))` no caminho de exceção (linha 202-205).
- **ADICIONAR** attrs `ring_group.balancer_backend` (label, NÃO UUID), `ring_group.selected_dial_path`, `ring_group.context`.
- **ADICIONAR** span event `ring_group.leg_answered` com `answered_uuid` quando `result=answered`.

### `genesis/group/load_balancer.py`
- **ADICIONAR** métricas `genesis.loadbalancer.selections` (Counter, attrs `balancer.backend`, `balancer.result`), `genesis.loadbalancer.errors` (Counter, attrs `error`).
- `[verificar]` nome do método de seleção no backend (InMemoryLoadBalancer/RedisLoadBalancer).

### `genesis/queue/core.py`
- **MANTER** `queue.wait_and_acquire` (linha 76); **ADICIONAR** attr `queue.depth` no span.
- **ADICIONAR** `record_exception`/`set_status(ERROR)` em falha de acquire.

### `genesis/types.py`
- **MANTER** `ChannelState` IntEnum; **ADICIONAR** helper `HangupCause.q850` mapping `[verificar se já existe]`.

### `genesis/cli/__init__.py`
- **MANTER** instalação do metrics meter provider (linha 78); **ADICIONAR** instalação de `TracerProvider` com `BatchSpanProcessor` (OTLP) — necessário para emitir os novos spans `freeswitch.channel.*`. `TextMapPropagator(TraceContextPropagator())` só é necessário se/when a propagação W3C via `X-Tracespan` for implementada (opcional/futuro).

## 7. Configuração no FreeSWITCH

### 7.1 Event Socket (ESL inbound)
- Em `freeswitch/conf/autoload_configs/event_socket.conf.xml`:
  - `<param name="listen-ip" value="0.0.0.0"/>` (ou IP restrito à rede do Genesis)
  - `<param name="listen-port" value="8021"/>`
  - `<param name="apply-inbound-acl" value="domains"/>` (restringir)
- O Genesis `Inbound` (`genesis/inbound.py`) conecta e autentica via `ClueCon` (padrão).

### 7.2 Subscrição de eventos
- Genesis já faz `events plain ALL` em `Channel.create` (`genesis/channel.py:144`). **MANTER**.
- Para os novos eventos semânticos, garantir que `events plain ALL` cubra: `CHANNEL_PROGRESS`, `CHANNEL_PROGRESS_MEDIA`, `CHANNEL_BRIDGE`, `CHANNEL_UNBRIDGE`, `CALL_UPDATE`, `CODEC`, `PLAYBACK_START`, `PLAYBACK_STOP`, `RECORD_START`, `RECORD_STOP`, `CHANNEL_PARK`, `CHANNEL_UNPARK`, `CHANNEL_EXECUTE`, `CHANNEL_EXECUTE_COMPLETE`, `CHANNEL_DESTROY`.
- Para CUSTOM subclasses, o `Consumer._filter_command` já emite `filter Event-Subclass {X}` para nomes não-uppercase. Garantir subscrição de: `sofia::transferor`, `sofia::transferee`, `sofia::reinvite`, `sofia::replaced`, `sofia::register`, `sofia::unregister`, `sofia::expire`, `sofia::gateway_state`, `callcenter::info`, `conference::maintenance`, `conference::cdr`, `valet_parking::info`.
- Habilitar **verbose events** globais em `freeswitch.conf.xml`: `<param name="events-verbose" value="true"/>` ou por canal via `verbose_events=true` channel var — necessário para ter `variable_sip_call_id` (chave de correlação com o sniffer) e `variable_hangup_cause_q850`.

### 7.3 Módulos relevantes
- `mod_sofia` (SIP) — obrigatório.
- `mod_event_socket` — obrigatório (ESL).
- `mod_callcenter` (se ACD), `mod_conference` (se conferência), `mod_valet_parking` (se valet) — opcionais conforme deploy.
- `mod_otel` `[verificar]` — existe um módulo comunitário mod_otel; se presente, pode complementar, mas **não é necessário** para esta proposta (tudo via ESL + Genesis).

## 8. Correlação no backend de observabilidade (sem mudanças no sniffer)

**Diretriz**: o sniffer **não é modificado**. Toda a correlação acontece por atributos compartilhados, no backend.

### 8.1 Chaves de correlação

| Chave | Genesis (span attr) | Sniffer (span attr, já existe) | Uso |
|---|---|---|---|
| SIP Call-ID | `sip.call_id` (= `variable_sip_call_id`) | `voip.call_id` | **Join principal** trace de controle ↔ trace de captura |
| Channel-Call-UUID | `channel.call_uuid` | — (não visível no SIP) | Agrupar a-leg/b-leg **dentro** do trace Genesis |
| Bridge legs | `bridge.a_uuid`, `bridge.b_uuid` | — | Cross-leg: do `sip.call_id` de um leg, ler `bridge.b_uuid` para achar o outro |
| Network | `channel.network_addr`, `sip.remote_ip` `[verificar ESL field]` | IPs/ports do RTP/SIP | Correlação secundária quando `sip.call_id` ausente |

### 8.2 Join no Grafana/Tempo

1. **Traces**: query por atributo — `span.attrs["sip.call_id"] = "<call-id>"` retorna o trace Genesis (service=genesis) e o trace sniffer (service=sniffer) lado a lado. Não há parentesco OTel direto (intencional).
2. **Métricas → traces**: usar **OTel exemplars**. O SDK anexa o `trace_id` do span corrente como exemplar ao registrar cada métrica dentro de um span. No Grafana, painéis de `genesis.*` e `voip.*` passam a ter exemplars que linkam direto para o trace — correlação métrica↔trace sem label de alta cardinalidade.
3. **Métricas↔métricas**: **não** usar `sip.call_id`/UUIDs como label de métrica (cardinalidade). Agregar por labels low-cardinality (`channel.state`, `direction`, `hangup.cause`, `application.name`) e correlacionar via o `trace_id` do exemplar quando precisar cruzar `genesis.call.duration` com `voip.call.duration_s`.

### 8.3 Fluxo de investigação de chamada (para o painel/dashboard)

1. Usuário parte do número discado ou caller → busca no sniffer `voip.call_id` (SIP Call-ID).
2. Query Tempo por `sip.call_id` → abre trace Genesis (`freeswitch.channel.*`) e trace sniffer (`voip.call.*`/`voip.rtp.stream`).
3. No span `freeswitch.channel.bridge` lê `bridge.b_uuid` → segunda query por `sip.call_id` do leg B (dialog SIP distinto).
4. Em `freeswitch.channel.hangup_complete` lê `hangup.cause` + `hangup.cause.q850` (autoritativo) e cruza com `voip.call.duration_s`/MOS do sniffer para correlacionar causa de controle × qualidade de mídia.

### 8.4 Resource attributes (Genesis)

- `service.name=genesis`, `service.namespace=control` `[verificar convenção atual]` para distinguir de `service.name=sniffer`/`service.namespace=voip` no backend.
- Garantir que o `TracerProvider` (item 6, `cli/__init__.py`) exporte com o mesmo endpoint OTLP do sniffer (ou para o mesmo collector) — o join só funciona se ambos chegarem ao mesmo backend.

## 9. Testes (Genesis)

Regras do `CLAUDE.md`: **proibido `asyncio.sleep`**; usar `asyncio.Event`/`Condition`/`Future`/`wait_for`; fixtures em `tests/conftest.py`, doubles em `tests/doubles.py`, payloads em `tests/payloads.py`; `asyncio_mode=auto`; timeout 10s.

### Novos payloads em `tests/payloads.py`
- `channel_progress` (CS_RINGING, Answer-State=ringing)
- `channel_progress_media` (CS_RINGING, CCS_EARLY, Channel-Read/Write-Codec-Name)
- `channel_bridge` (Bridge-A-Unique-ID, Bridge-B-Unique-ID, Other-Leg-Unique-ID, Other-Type)
- `channel_unbridge`
- `call_update` (Bridged-To, Caller-Transfer-Source)
- `codec` (channel-read-codec-name/rate)
- `playback_start`, `playback_stop`
- `record_start`, `record_stop`
- `channel_execute` (Application, Application-UUID)
- `channel_execute_complete` (Application, Application-UUID, Application-Response)
- `channel_destroy`
- `sofia_transferor`, `sofia_transferee` (Event-Subclass, Other-Leg-Unique-ID)
- `sofia_reinvite`
- `callcenter_info` (CC-Queue, CC-Action, CC-Agent, CC-Member-UUID)
- `conference_maintenance` (Conference-Name, Action, Member-ID)
- `valet_info` (Valet-Lot-Name, Bridge-To-UUID)
- `channel_create_verbose` (com `variable_sip_call_id`, `Caller-Context`, `Caller-Destination-Number`)

### Novos testes (em `tests/test_channel_lifecycle.py` `[novo]`)
- `test_channel_create_span_attrs` — dispara `channel_create_verbose` num `FakeProtocol` (doubles.py), verifica span `freeswitch.channel.create` com attrs `channel.context`, `channel.destination_number`, `channel.direction`, `sip.call_id`.
- `test_channel_bridge_span_links_a_b_leg` — dispara `channel_bridge`, verifica span `freeswitch.channel.bridge` com `bridge.a_uuid` e `bridge.b_uuid` e span event `bridge.established`.
- `test_channel_unbridge_span_event` — verifica span event `bridge.torn_down`.
- `test_channel_hangup_complete_q850` — dispara `channel_hangup_complete` com `variable_hangup_cause_q850=16`, verifica attr `hangup.cause.q850=16` e span event `call.finalized`.
- `test_channel_progress_media_early_codec` — verifica attrs `channel.read_codec`, `answer.state=early`.
- `test_call_update_transfer_correlation` — dispara `call_update` + `sofia_transferor`, verifica `transfer.role=transferor` e `bridged.to`.
- `test_process_event_routing_attrs` — dispara evento com `Call-Direction`, `Channel-State`, `Other-Leg-Unique-ID`, verifica attrs no span `process_event`.
- `test_send_command_error_span_status` — duplo que responde `-ERR`, verifica `span.status=ERROR` e `command.error=protocol_error` e `command.name=api` (verbo, não string crua).
- `test_channel_create_sip_call_id_attr` — `Channel.create` com evento contendo `variable_sip_call_id`, verifica attr `sip.call_id` presente no span (chave de correlação com o sniffer).
- `test_ring_group_set_status_on_error` — `RingGroup.ring` com backend que levanta, verifica `span.status=ERROR` (gap do mapeamento).
- `test_call_duration_histogram_has_attrs` — hangup com cause, verifica métrica `genesis.call.duration` gravada com attrs `hangup.cause`, `direction`.
- `test_observable_gauge_queue_depth` — `FakeProtocol` com N eventos na queue, callback do ObservableGauge retorna o tamanho esperado.

### Novos testes em `tests/test_session_tracing.py` `[novo]`
- `test_session_sendmsg_span`
- `test_session_await_complete_span`

### Novos testes em `tests/test_consumer_tracing.py` `[novo]`
- `test_consumer_dispatch_span`

### Doubles em `tests/doubles.py`
- **ADICIONAR** `FakeTracer`/`FakeSpan` que registre attrs, events, status, links em listas inspecionáveis (se já não existir).
- **ADICIONAR** `FakeMeter` que capture `add()`/`record()` calls com attrs.

## 10. Rollout / migração

### Ordem de implementação (fases)
1. **Fase 0 — Refactor sem mudança observável**: centralizar métricas em `genesis/protocol/metrics.py`, remover duplicações em `channel.py` (resolver circular import via import lazy ou mover constants para `genesis/protocol/_metrics_constants.py` `[novo]`).
2. **Fase 1 — Correções em spans existentes**: `send_command` (verbo + erro), `process_event` (atributos routing), `ring_group.ring` (`set_status`), `call.duration` (attrs).
3. **Fase 2 — Spans de lifecycle ESL**: novos processors + spans `freeswitch.channel.*` (CREATE/PROGRESS/ANSWER/BRIDGE/UNBRIDGE/HANGUP/HANGUP_COMPLETE/DESTROY/EXECUTE/CODEC/PLAYBACK/RECORD).
4. **Fase 3 — CUSTOM subclasses**: sofia::transfer*, callcenter, conference, valet.
5. **Fase 4 — Session/Consumer instrumentation**: spans em `session.py` e `consumer.py`.
6. **Fase 5 — Métricas novas e ObservableGauges**.

### Compatibilidade
- Todos os novos spans/métricas são **aditivos**; consumers atuais (`Consumer.handle`, `Channel.on_dtmf`, `protocol.on`) continuam funcionando.
- Novos event processors **não devem consumir** eventos que já roteiam para handlers de usuário — apenas enriquecem telemetria.
- `command.name` rename: spans OTel são opacos para a API pública; nenhum consumidor do Genesis lê spans programaticamente (só o backend OTel).
- `call.duration` com attrs: backends OTel agregam por attrs; sem attr continua funcionando (label vazio).

### Feature flags
- `GENESIS_TRACE_ESL_LIFECYCLE=1` (default on) — habilita spans `freeswitch.channel.*`.
- `GENESIS_TRACE_SIP_HEADER=0` (default **off**) — injeção de `` (propagação W3C); **fora do escopo deste PR**, flag reservada para o futuro.
- `GENESIS_TRACE_CUSTOM_SUBCLASSES=1` (default on) — habilita spans de sofia::/callcenter::/conference::/valet::.
- Implementar via `os.environ.get` no módulo de telemetria, guards nos processors.

### Checklist de PR (pré-merge)
1. `poetry run black --check genesis/ tests/ examples/`
2. `poetry run mypy`
3. `poetry run pytest tests/`
4. `poetry run tox` (Python 3.10, 3.11, 3.12)
5. Não assinar commits/PR (memória `feedback_pr_signature`).

## 11. Riscos e trade-offs

| Risco | Mitigação |
|---|---|
| **Cardinalidade de métricas com UUIDs** | UUIDs (`channel.uuid`, `bridge.a_uuid`, `other_leg.uuid`, `application.uuid`) **só em spans**, nunca em métricas. Métricas usam enums/labels low-cardinality (`channel.state`, `direction`, `hangup.cause`, `application.name`). |
| **Volume de spans por chamada** | Uma chamada simples de 2 legs pode gerar ~20-30 spans (Genesis controle) + ~5-10 (sniffer SIP/RTP). Mitigar com `TraceIDRatioBased` no Genesis (`GENESIS_OTEL_SAMPLE_RATIO`) e mantendo `AlwaysSample` só em dev. Spans `process_event` e `route_event` podem ser desligáveis via flag. |
| **Falha de correlação por `sip.call_id`** | Se o evento ESL não trouxer `variable_sip_call_id` (leg não-SIP, gateway sem `verbose_events`), o span Genesis fica sem a chave. Mitigar: exigir `verbose_events=true` no FS; registrar `sip.call_id=unknown` explícito para não mascarar o gap; métrica `genesis.events.without_sip_call_id` (Counter) para medir adoção. |
| **`Channel-Call-UUID` roll em transfer** | Reavaliar a cada `CHANNEL_BRIDGE`; se mudar, novo span root com span Link para o trace anterior (não quebra o trace anterior, ramifica). |
| **Verbosidade de eventos ESL** | Habilitar `verbose_events` só onde necessário (produção pode gerar payload grande em `CHANNEL_HANGUP_COMPLETE` com XML CDR). Feature flag `GENESIS_ESL_VERBOSE_CDR=0` para não ingerir o body XML. |
| **Duplicação `channel.bridge` (comando) vs `freeswitch.channel.bridge` (evento)** | Documentar: o span do comando mede a chamada `api uuid_bridge`; o span do evento mede o instante autoritativo do bridge no FS. Namespaces distintos (`channel.*` vs `freeswitch.channel.*`). |
| **Overhead de `process_event` estendido** | Envolver dispatch no span pode aumentar duração do span (mas não do código). Medir com `genesis.event.processing.duration`. |
| **Circular import ao centralizar métricas** | Resolver movendo constantes de atributo para um módulo sem dependência de `protocol/base.py` (ex. `genesis/protocol/_attr_constants.py` `[novo]`), e importando os instrumentos prontos em `channel.py` via import direto de `metrics.py`. |
| **`sip.call_id` divergente entre a-leg/b-leg** | Cada leg é um dialog SIP distinto com Call-ID próprio; o join cross-leg não é por `sip.call_id` mas por `channel.call_uuid` + `bridge.a/b_uuid` dentro do trace Genesis. Documentar o fluxo de navegação no painel Grafana. |
| **`variable_sip_call_id` ausente em legs originate** | Em `originate` outbound o SIP Call-ID pode não estar disponível no `CHANNEL_CREATE` (só após o primeiro response SIP). Mitigar: anexar `sip.call_id` no `process_event` assim que o campo aparecer, e regravar no span de lifecycle posterior (PROGRESS/ANSWER). |

## 12. Checklist do PR

- [ ] Métricas duplicadas removidas de `genesis/channel.py` (linhas 32-68) e centralizadas em `genesis/protocol/metrics.py`
- [ ] `send_command` (`base.py:290`): `command.name` = verbo parseado; `command.error` + `set_status(ERROR)` + `record_exception` no `-ERR`
- [ ] `process_event` (`base.py:201`): attrs `event.direction/channel_state/answer_state/hangup_cause/subclass/call_uuid/other_leg` + `sip.call_id` (correlação sniffer) via `build_event_attributes`
- [ ] `build_event_attributes` (`telemetry.py:15`) estendido com os 9 novos attrs
- [ ] Novo `channel_lifecycle_processor` em `genesis/protocol/processors.py` emitindo spans `freeswitch.channel.{create,progress,progress_media,answer,bridge,unbridge,hangup,hangup_complete,destroy,execute,execute_complete,park,unpark}`
- [ ] Novo `sofia_custom_processor` (e callcenter/conference/valet) em `processors.py`
- [ ] `freeswitch.channel.bridge` carrega `bridge.a_uuid`/`bridge.b_uuid` + span event `bridge.established`
- [ ] `freeswitch.channel.hangup_complete` carrega `hangup.cause.q850` + span event `call.finalized`
- [ ] `freeswitch.call.update` + `freeswitch.sofia.transfer` com `transfer.role`/`bridged.to`
- [ ] `channel.create` (`channel.py:144`) registra attrs `sip.call_id` + `channel.call_uuid` no span
- [ ] `genesis/cli/__init__.py:78` instala `TracerProvider` + `BatchSpanProcessor` (OTLP) — `TextMapPropagator` só se propagação W3C futura
- [ ] `ring_group.ring` (`ring.py:138`) chama `set_status(ERROR)` na exceção; novos attrs `ring_group.balancer_backend/selected_dial_path/context`
- [ ] `call_duration_histogram.record` (`channel.py:573`) com attrs `hangup.cause`/`direction`
- [ ] Spans em `genesis/session.py`: `session.sendmsg`, `session.start/stop`, `session.await_complete`
- [ ] Spans em `genesis/consumer.py`: `consumer.start/stop`, `consumer.dispatch`
- [ ] `genesis/outbound.py` incrementa `genesis.connections.errors` (type=outbound)
- [ ] Métricas novas: `genesis.calls.active`, `genesis.channel.bridge.events`, `genesis.channel.transfers`, `genesis.channel.codec.changes`, `genesis.dialplan.applications`, `genesis.channel.hangup.causes.q850`, `genesis.event.processing.duration`, `genesis.commands.queue.depth`, `genesis.events.queue.depth`
- [ ] `genesis/group/load_balancer.py` instrumentado com `genesis.loadbalancer.selections/errors`
- [ ] Payloads novos em `tests/payloads.py` (channel_progress/bridge/unbridge/call_update/codec/playback/record/execute/destroy/sofia_transferor/callcenter_info/conference_maintenance/valet_info/channel_create_verbose)
- [ ] Doubles `FakeTracer`/`FakeSpan`/`FakeMeter` em `tests/doubles.py`
- [ ] Testes novos em `tests/test_channel_lifecycle.py`, `tests/test_session_tracing.py`, `tests/test_consumer_tracing.py` (sem `asyncio.sleep`, com `asyncio.Event`/`wait_for`)
- [ ] `poetry run black --check genesis/ tests/ examples/` passa
- [ ] `poetry run mypy` passa
- [ ] `poetry run pytest tests/` passa (timeout 10s)
- [ ] `poetry run tox` passa (3.10, 3.11, 3.12)
- [ ] Sem assinatura de commit/PR (respeitar `feedback_pr_signature`)
- [ ] Documentação: atualizar `CLAUDE.md` seção Observability Pattern com os novos spans; `[verificar]` se há `docs/` no Genesis para atualizar
- [ ] **Nenhuma mudança no sniffer** — correlação exclusivamente por `sip.call_id` no backend de observabilidade (Grafana/Tempo + exemplars)
- [ ] Documentar no `CLAUDE.md`/docs o fluxo de join Genesis↔sniffer por `sip.call_id` e o fluxo cross-leg via `bridge.a/b_uuid`

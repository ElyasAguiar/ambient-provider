# Sistema de Transcrição Multi-Engine com Jobs Redis

Implementação de sistema de filas de transcrição suportando NVIDIA Riva ASR e WhisperX com Redis pub/sub e MinIO.

## Arquitetura

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Cliente   │─────▶│  FastAPI API │─────▶│    Redis    │
│             │      │  (4 workers) │      │  (Broker)   │
└─────────────┘      └──────────────┘      └─────────────┘
                             │                      │
                             ▼                      ▼
                      ┌──────────────┐      ┌─────────────┐
                      │  PostgreSQL  │      │   Workers   │
                      │  (Database)  │      │ (arq x2)    │
                      └──────────────┘      └─────────────┘
                             ▲                      │
                             │                      ▼
                             │              ┌─────────────┐
                             └──────────────│    MinIO    │
                                           │  (Storage)  │
                                           └─────────────┘
```

## Endpoints Disponíveis

### 1. Endpoint Genérico
**`POST /api/transcribe/jobs/transcribe`**

Enfileira job com engine especificado ou padrão (ASR).

**Parâmetros:**
- `file`: Arquivo de áudio (audio/*)
- `session_id`: (Opcional) UUID da sessão para associar a transcrição
- `engine`: `"asr"` ou `"whisperx"` (default: `"asr"`)
- `context_id`: (Opcional) UUID do contexto para word boosting (apenas ASR)
- `language`: Código de idioma (default: `"en-US"`)

**Exemplo:**
```bash
curl -X POST "http://localhost:8000/api/transcribe/jobs/transcribe" \
  -F "file=@audio.mp3" \
  -F "engine=asr" \
  -F "language=en-US"

# Ou com sessão:
curl -X POST "http://localhost:8000/api/transcribe/jobs/transcribe" \
  -F "file=@audio.mp3" \
  -F "session_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "engine=asr" \
  -F "language=en-US"
```

**Resposta:**
```json
{
  "job_id": "abc123...",
  "transcript_id": "uuid...",
  "engine": "asr",
  "status": "queued",
  "message": "ASR transcription job enqueued successfully"
}
```

---

### 2. Endpoint ASR (NVIDIA Riva)
**`POST /api/transcribe/jobs/transcribe/asr`**

Transcrição usando NVIDIA Riva ASR com diarização de speakers e word boosting.

**Parâmetros:**
- `file`: Arquivo de áudio
- `session_id`: (Opcional) UUID da sessão para associar a transcrição
- `context_id`: (Opcional) UUID do contexto para termos específicos do domínio
- `language`: Código de idioma (ex: `"en-US"`, `"pt-BR"`)

**Recursos:**
- ✅ Diarização automática de speakers
- ✅ Word boosting baseado em contexto
- ✅ Pontuação automática
- ✅ Timestamps de palavras
- ✅ Speaker role detection (patient/provider)

**Exemplo:**
```bash
curl -X POST "http://localhost:8000/api/transcribe/jobs/transcribe/asr" \
  -F "file=@medical-consultation.mp3" \
  -F "session_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "context_id=medical-context-uuid" \
  -F "language=en-US"
```

---

### 3. Endpoint WhisperX
**`POST /api/transcribe/jobs/transcribe/whisperx`**

Transcrição usando WhisperX com modelos multilíngues e diarização avançada.

**Parâmetros:**
- `file`: Arquivo de áudio
- `session_id`: (Opcional) UUID da sessão para associar a transcrição
- `model`: Modelo WhisperX (default: `"base"`)
  - Opções: `tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3`
- `language`: (Opcional) Código de 2 letras (ex: `"en"`, `"pt"`) - auto-detect se omitido
- `enable_diarization`: Habilitar diarização (default: `true`)
- `min_speakers`: (Opcional) Número mínimo de speakers
- `max_speakers`: (Opcional) Número máximo de speakers

**Recursos:**
- ✅ Multilíngue (99+ idiomas)
- ✅ Diarização avançada com pyannote
- ✅ Alinhamento de timestamps preciso
- ✅ Múltiplos tamanhos de modelo
- ✅ Auto-detecção de idioma

**Exemplo:**
```bash
curl -X POST "http://localhost:8000/api/transcribe/jobs/transcribe/whisperx" \
  -F "file=@podcast.mp3" \
  -F "session_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "model=medium" \
  -F "language=en" \
  -F "enable_diarization=true" \
  -F "min_speakers=2" \
  -F "max_speakers=4"
```

---

### 4. Verificar Status do Job
**`GET /api/transcribe/jobs/status/{job_id}`**

Consulta status do job (primeiro no Redis, fallback para database).

**Resposta (Processando):**
```json
{
  "job_id": "abc123...",
  "status": "processing",
  "progress": 45,
  "transcript_id": "uuid...",
  "worker_id": "worker-1",
  "message": "Transcribing with ASR"
}
```

**Resposta (Concluído):**
```json
{
  "job_id": "abc123...",
  "status": "completed",
  "progress": 100,
  "transcript_id": "uuid...",
  "result": {
    "segments_count": 42,
    "duration": 125.5
  }
}
```

---

### 5. Stream de Status (SSE)
**`GET /api/transcribe/jobs/stream/{job_id}`**

Server-Sent Events com updates em tempo real via Redis pub/sub.

**Exemplo:**
```javascript
const eventSource = new EventSource('/api/transcribe/jobs/stream/abc123');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Status:', data.status, 'Progress:', data.progress);
  
  if (data.status === 'completed') {
    eventSource.close();
  }
};
```

---

### 6. Obter Resultado Completo
**`GET /api/transcribe/jobs/result/{job_id}`**

Retorna transcript completo com todos os segments.

**Resposta:**
```json
{
  "job_id": "abc123...",
  "transcript_id": "uuid...",
  "status": "completed",
  "filename": "audio.mp3",
  "audio_url": "https://minio.../presigned-url",
  "language": "en-US",
  "duration": 125.5,
  "segments": [
    {
      "start": 0.0,
      "end": 3.5,
      "text": "Good morning, how are you feeling?",
      "speaker_tag": 0,
      "confidence": 0.95
    }
  ],
  "speaker_roles": {
    "0": "provider",
    "1": "patient"
  }
}
```

---

### 7. Listar Engines Disponíveis
**`GET /api/transcribe/jobs/engines`**

Verifica disponibilidade e capacidades dos engines.

**Resposta:**
```json
{
  "engines": {
    "asr": {
      "engine": "asr",
      "available": true,
      "uri": "parakeet-nim:50051",
      "model": "parakeet-0-6b-ctc-en-us",
      "language": "en-US"
    },
    "whisperx": {
      "engine": "whisperx",
      "available": true,
      "url": "http://whisperx:9000",
      "available_models": ["tiny", "base", "small", "medium", "large-v2", "large-v3"],
      "health": {"status": "ok"}
    }
  },
  "default_engine": "asr"
}
```

## Fluxo de Processamento

1. **Upload**: Cliente envia áudio para API
2. **Storage**: Arquivo salvo no MinIO com URL pré-assinada (1h)
3. **Database**: Criado registro `Transcript` (status: `processing`) e `TranscriptJob`
4. **Redis**: Job criado com TTL de 60min
5. **ARQ**: Job enfileirado para workers
6. **Worker**: 
   - Baixa áudio do MinIO
   - Processa com engine escolhido (ASR ou WhisperX)
   - Publica progresso via Redis pub/sub
   - Salva resultado no database
7. **Cleanup**: Arquivo deletado após 24h

## Configurações

**`.env`:**
```bash
# Engine padrão
DEFAULT_TRANSCRIPTION_ENGINE=asr

# Redis
REDIS_URL=redis://redis:6379/0
REDIS_JOB_TTL=3600  # 60 minutos

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=transcriptions
MINIO_USE_SSL=false

# NVIDIA Riva ASR
RIVA_URI=parakeet-nim:50051
RIVA_MODEL=parakeet-0-6b-ctc-en-us
RIVA_LANGUAGE=en-US

# WhisperX
WHISPERX_SERVICE_URL=http://whisperx:9000
WHISPERX_AVAILABLE_MODELS=tiny,base,small,medium,large-v2,large-v3
WHISPERX_DEFAULT_MODEL=base
WHISPERX_TIMEOUT=300
```

## Banco de Dados

**Nova estrutura `transcript_jobs`:**
```sql
CREATE TABLE transcript_jobs (
    id UUID PRIMARY KEY,
    transcript_id UUID REFERENCES transcripts(id) UNIQUE,
    job_id VARCHAR(255) UNIQUE NOT NULL,
    engine transcription_engine NOT NULL DEFAULT 'asr',  -- ENUM('asr', 'whisperx')
    engine_params JSONB DEFAULT '{}',
    worker_id VARCHAR(255),
    attempts INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## Executar Migration

```bash
# Aplicar migration
alembic upgrade head

# Verificar status
alembic current
```

## Docker Compose

```bash
# Subir todos os serviços
docker-compose -f docker-compose.dev.yml up -d

# Ver logs dos workers
docker-compose -f docker-compose.dev.yml logs -f worker

# Escalar workers
docker-compose -f docker-compose.dev.yml up -d --scale worker=4
```

## Monitoramento

**Redis CLI:**
```bash
# Verificar keys de jobs
redis-cli KEYS "job:*"

# Ver status de um job
redis-cli GET "job:abc123:status"

# Monitorar pub/sub
redis-cli PSUBSCRIBE "transcription:status:*"
```

**MinIO Console:**
```
http://localhost:9001
User: minioadmin
Pass: minioadmin
```

## Comparação ASR vs WhisperX

| Característica | ASR (Riva) | WhisperX |
|----------------|------------|----------|
| **Idiomas** | Limitado (en-US, pt-BR, etc) | 99+ idiomas |
| **Velocidade** | Muito rápido (GPU) | Moderado |
| **Precisão** | Excelente para inglês médico | Excelente geral |
| **Diarização** | Sim (Riva nativo) | Sim (pyannote) |
| **Word Boosting** | ✅ Sim | ❌ Não |
| **Contexto** | ✅ Domain-specific | ❌ Genérico |
| **Modelos** | Parakeet | Whisper (vários tamanhos) |
| **Auto-detect idioma** | ❌ Não | ✅ Sim |

## Troubleshooting

**Job fica em "queued":**
- Verificar se workers estão rodando: `docker-compose ps worker`
- Verificar logs: `docker-compose logs worker`
- Verificar Redis: `redis-cli PING`

**Erro de engine inválido:**
- Verificar `/api/transcribe/jobs/engines` para engines disponíveis
- Verificar configuração do serviço (Riva ou WhisperX)

**Arquivo muito grande:**
- Limite atual: 100MB
- Aumentar em `.env`: `MAX_FILE_SIZE=200000000`

**Redis timeout:**
- Aumentar TTL em `.env`: `REDIS_JOB_TTL=7200`
- Jobs expiram após TTL (padrão: 60min)
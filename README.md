# Ambient Scribe API

## Overview
Ambient Scribe API é uma plataforma de backend para conversão de áudio de consultas médicas em notas clínicas estruturadas. O sistema utiliza NVIDIA NIM (NVIDIA Inference Microservices) para reconhecimento de fala com diarização de falantes, combinado com modelos de linguagem para geração de documentação médica.

## Principais Funcionalidades
- **Transcrição de Áudio**: Converte arquivos de áudio em transcrições precisas com identificação de falantes
- **Geração de Notas**: Transforma transcrições em notas médicas estruturadas (SOAP, Progress Notes, formatos customizados)
- **Processamento em Tempo Real**: Acompanhamento do progresso em tempo real
- **Sistema de Templates**: Templates integrados ou criação de formatos customizados
- **API REST**: Interface FastAPI completa com documentação Swagger

## Estrutura do Projeto

```
ambient-provider/
├── ambient_scribe/         # Código principal da API
│   ├── main.py            # Aplicação FastAPI
│   ├── models.py          # Modelos Pydantic
│   ├── database.py        # Configuração do banco de dados
│   ├── routers/           # Endpoints da API
│   ├── services/          # Lógica de negócio
│   └── middleware/        # Middlewares
├── alembic/               # Migrações do banco de dados
├── templates/             # Templates de notas médicas
├── Dockerfile             # Dockerfile da API
├── docker-compose.dev.yml # Ambiente de desenvolvimento
├── docker-compose.prod.yml # Ambiente de produção
├── pyproject.toml         # Dependências Python
└── .env.example           # Exemplo de variáveis de ambiente
```

## Componentes do Sistema

A plataforma consiste em quatro componentes principais:

- **API (FastAPI)**: Servidor Python que orquestra transcrição e geração de notas
- **PostgreSQL**: Banco de dados para armazenamento de usuários, notas e templates
- **NVIDIA Parakeet NIM**: Serviço de reconhecimento de fala com diarização
- **NVIDIA Llama NIM**: Modelo de linguagem para geração de notas médicas

# Começando

## Pré-requisitos

### Requisitos de GPU

| Serviço | Modelo | GPU Recomendada | Armazenamento |
|---------|--------|-----------------|---------------|
| **Parakeet NIM (ASR)** | parakeet-1.1b-en-US-asr-streaming | 1x L40/A100 | 75GB |
| **Llama NIM (LLM)** | llama-3.3-nemotron-super-49b-v1 | 2x H100 ou 4x A100 | 325GB |

### Requisitos de Software
- Docker & Docker Compose v2.0+
- NVIDIA Container Toolkit
- Git
- Python 3.13 (para desenvolvimento local)

### Chaves de API
- **NGC_API_KEY**: Chave de API da NVIDIA para acessar os serviços NIM

## Autenticação NGC

1. Crie uma conta em [NGC](https://ngc.nvidia.com)
2. Gere uma API Key em [NGC Personal Keys](https://org.ngc.nvidia.com/setup/personal-keys)
3. Selecione "NGC Catalog" nos serviços incluídos
4. Copie a chave gerada

### Exportar a API Key

```bash
# Exportar a chave (substitua <value> pela sua chave)
export NGC_API_KEY=<value>

# Tornar persistente
echo "export NGC_API_KEY=<value>" >> ~/.zshrc  # ou ~/.bashrc
```

## Instalação do Docker

1. Instale o [Docker](https://docs.docker.com/engine/install/)
2. Instale o [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

### Verificar Instalação

```bash
docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
```

### Login no NGC Registry

```bash
echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin
```

## Instalação

### 1. Clonar o Repositório

```bash
git clone https://github.com/ElyasAguiar/ambient-provider.git
cd ambient-provider
```

### 2. Configurar Variáveis de Ambiente

```bash
cp .env.example .env
# Edite o arquivo .env com suas configurações
```

Variáveis principais no `.env`:

```bash
# NVIDIA API Keys
NVIDIA_API_KEY=your_nvidia_api_key_here
NGC_API_KEY=your_ngc_api_key_here

# Database
DATABASE_URL=postgresql://scribehub:scribehub@postgres:5432/scribehub

# API Configuration
DEBUG=true
API_TITLE="Ambient Scribe API"
API_VERSION="0.1.0"

# NVIDIA Riva ASR Configuration
RIVA_URI=parakeet-nim:50051
RIVA_MODEL=parakeet-1.1b-en-US-asr-streaming-silero-vad-sortformer

# LLM Configuration
OPENAI_BASE_URL=http://llama-nim:8000/v1
LLM_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1

# Storage
STORAGE_BACKEND=local
UPLOAD_DIR=/app/uploads
TEMPLATES_DIR=/app/templates
```

### 3. Executar em Desenvolvimento

```bash
docker-compose -f docker-compose.dev.yml up
```

A API estará disponível em:
- API: http://localhost:8000
- Documentação Swagger: http://localhost:8000/docs
- PostgreSQL: localhost:5432

### 4. Executar em Produção

```bash
docker-compose -f docker-compose.prod.yml up -d
```

## Estrutura dos Docker Compose

### Development (docker-compose.dev.yml)

Inclui hot-reload e volumes montados para desenvolvimento:
- **API**: Porta 8000 com reload automático
- **PostgreSQL**: Porta 5432
- **Parakeet NIM**: Portas 9000 (HTTP) e 50051 (gRPC)
- **Llama NIM**: Porta 8001

### Production (docker-compose.prod.yml)

Otimizado para produção com limites de recursos:
- **API**: Limit 1.5GB RAM
- **PostgreSQL**: Limit 512MB RAM
- **Parakeet NIM**: Limit 22GB RAM, GPU dedicada
- **Llama NIM**: Limit 48GB RAM, múltiplas GPUs
- Logs rotativos configurados
- Restart automático

## Uso da API

### Endpoints Principais

#### Health Check
```bash
curl http://localhost:8000/api/health/
```

#### Upload de Áudio e Transcrição
```bash
curl -X POST "http://localhost:8000/api/transcribe/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@audio.wav"
```

#### Gerar Nota Médica
```bash
curl -X POST "http://localhost:8000/api/notes/generate" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "transcript": "texto da transcrição",
    "template": "soap_default"
  }'
```

#### Listar Templates
```bash
curl "http://localhost:8000/api/templates/" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Autenticação

A API usa JWT tokens. Para obter um token:

```bash
curl -X POST "http://localhost:8000/api/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin"
```

## Migrações do Banco de Dados

### Criar uma Nova Migração

```bash
docker-compose exec api alembic revision --autogenerate -m "descrição da migração"
```

### Aplicar Migrações

```bash
docker-compose exec api alembic upgrade head
```

### Reverter Migração

```bash
docker-compose exec api alembic downgrade -1
```

## Desenvolvimento Local

### Instalar Dependências

```bash
pip install -e .
```

### Executar a API Localmente

```bash
# Certifique-se de que o PostgreSQL está rodando
uvicorn ambient_scribe.main:app --reload --host 0.0.0.0 --port 8000
```

### Executar Testes

```bash
pytest
```

### Formatação de Código

```bash
# Formatação
black ambient_scribe/
isort ambient_scribe/

# Linting
ruff check ambient_scribe/
```

## Monitoramento e Logs

### Visualizar Logs

```bash
# Todos os serviços
docker-compose -f docker-compose.dev.yml logs -f

# Apenas API
docker-compose -f docker-compose.dev.yml logs -f api

# Apenas Parakeet NIM
docker-compose -f docker-compose.dev.yml logs -f parakeet-nim

# Apenas Llama NIM
docker-compose -f docker-compose.dev.yml logs -f llama-nim
```

### Health Checks

Todos os serviços têm health checks configurados:
- API: `http://localhost:8000/api/health/`
- Parakeet NIM: `http://localhost:9000/v1/health`
- Llama NIM: `http://localhost:8001/v1/health`
- PostgreSQL: `pg_isready -U scribehub`

## Troubleshooting

### Problemas com GPU

Verificar se a GPU está disponível:
```bash
docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
```

### Problemas de Memória

Se os NIMs estão falhando por falta de memória:
1. Verifique os limites no docker-compose
2. Ajuste `shm_size` se necessário
3. Verifique memória disponível no host

### Problemas de Conexão com o Banco

Verificar se o PostgreSQL está acessível:
```bash
docker-compose exec postgres pg_isready -U scribehub
```

### Limpar Volumes e Reconstruir

```bash
docker-compose -f docker-compose.dev.yml down -v
docker-compose -f docker-compose.dev.yml up --build
```

## Segurança

### Produção

Para produção, certifique-se de:
1. Alterar senhas padrão no `.env`
2. Usar HTTPS com certificados SSL
3. Configurar CORS apropriadamente
4. Implementar rate limiting
5. Usar secrets management (não commitar `.env`)

### Backup do Banco de Dados

```bash
docker-compose exec postgres pg_dump -U scribehub scribehub > backup.sql
```

## Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## Licença

Este projeto está sob a licença Apache 2.0. Veja o arquivo `LICENSE` para mais detalhes.

## Contato

Para dúvidas ou suporte, entre em contato através do GitHub Issues.
